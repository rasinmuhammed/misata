"""
SpecBench baseline adapters.

Every generator is wrapped behind one interface so metrics treat them identically.
A baseline reports its *capabilities* honestly: a generator that cannot ingest an
outcome target says so (it does not silently pretend), and a generator that needs
source data declares `cold_start = False`.

Baselines that require an optional package (SDV) are constructed only when the
package is importable; otherwise `available()` returns False and the runner records
"not run (reason)" — never a fabricated number.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class GenResult:
    """What a baseline returns for one task."""
    tables: Dict[str, pd.DataFrame]
    ran: bool = True
    reason: str = ""                      # why it didn't run, if ran=False
    wall_seconds: float = 0.0


@dataclass
class Capabilities:
    cold_start: bool                      # can run with zero source rows?
    ingests_outcomes: bool                # can take aggregate/rate/group targets?
    deterministic: bool                   # bitwise identical under fixed seed?
    relational: bool                      # native multi-table with FK awareness?


class Baseline:
    """Adapter interface. Subclasses implement `generate` and declare capabilities."""
    name: str = "baseline"
    capabilities: Capabilities

    def available(self) -> bool:
        return True

    def generate(self, task: "Any", seed: int) -> GenResult:  # noqa: F821
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Misata — the specification, cold-start, closed-form reference system
# --------------------------------------------------------------------------- #

class MisataBaseline(Baseline):
    name = "misata"
    capabilities = Capabilities(
        cold_start=True, ingests_outcomes=True, deterministic=True, relational=True,
    )

    def generate(self, task, seed: int) -> GenResult:
        import time
        import misata
        t0 = time.perf_counter()
        # Misata consumes the natural-language / declarative spec directly.
        tables = misata.generate(task.story, rows=task.rows, seed=seed)
        # For reference-mode AME we compare like-for-like: expose the generator's
        # metric-bearing table under the task's metric_table name. Pick the table
        # that actually contains the metric column.
        if task.metric_table not in tables:
            for name, df in tables.items():
                if task.metric_col in df.columns and task.time_col in df.columns:
                    tables[task.metric_table] = df
                    break
        return GenResult(tables=tables, wall_seconds=time.perf_counter() - t0)


# --------------------------------------------------------------------------- #
# Faker + hand-wired FK — the manual-templating baseline
# --------------------------------------------------------------------------- #

class FakerBaseline(Baseline):
    name = "faker"
    capabilities = Capabilities(
        cold_start=True, ingests_outcomes=False, deterministic=True, relational=False,
    )

    def generate(self, task, seed: int) -> GenResult:
        tables, secs = _faker_scaffold(task, seed, rescale_to_targets=False)
        return GenResult(tables=tables, wall_seconds=secs)


def _faker_scaffold(task, seed: int, rescale_to_targets: bool = False):
    """Build the task's schema with Faker-style independent columns + FK by parent
    sampling. If rescale_to_targets, multiply the metric within each declared period to
    hit the aggregate target exactly (the NaiveRescale strategy).

    Fairness (review M4): the metric column is drawn with mean = the spec's *implied*
    per-row mean (target-total / declared-rows), NOT an arbitrary scale. A baseline's
    only disadvantage is then missing the *temporal shape*, never a scale we picked.
    """
    import time
    from faker import Faker
    t0 = time.perf_counter()
    fake = Faker(); Faker.seed(seed)
    rng = np.random.default_rng(seed)

    implied_mean = None
    if task.period_targets:
        tot = sum(task.period_targets.values())
        mrows = next((t["rows"] for t in task.schema_tables
                      if t["name"] == task.metric_table), None)
        if mrows:
            implied_mean = tot / mrows

    tables: Dict[str, pd.DataFrame] = {}
    for tbl in task.schema_tables:
        n = tbl["rows"]
        cols: Dict[str, Any] = {}
        cols[tbl["pk"]] = np.arange(1, n + 1)
        for col in tbl["columns"]:
            kind, name = col["kind"], col["name"]
            if kind == "metric":
                mean = implied_mean if (implied_mean and tbl["name"] == task.metric_table) \
                    else col.get("scale", 100)
                s = 0.6
                cols[name] = rng.lognormal(mean=np.log(mean) - 0.5 * s * s, sigma=s, size=n)
            elif kind == "category":
                cols[name] = rng.choice(col["choices"], size=n)
            elif kind == "date":
                start = np.datetime64(col.get("start", "2024-01-01"))
                span = int(col.get("span_days", 365))
                cols[name] = start + rng.integers(0, span, size=n).astype("timedelta64[D]")
            elif kind == "fk":
                parent_ids = tables[col["parent"]][col["parent_pk"]].to_numpy()
                cols[name] = rng.choice(parent_ids, size=n)
            else:
                cols[name] = [fake.word() for _ in range(n)]
        tables[tbl["name"]] = pd.DataFrame(cols)

    if rescale_to_targets and task.period_targets and \
            task.metric_table in tables and \
            task.time_col in tables[task.metric_table].columns:
        df = tables[task.metric_table]
        month = pd.to_datetime(df[task.time_col]).dt.strftime("%m")
        for label, target in task.period_targets.items():
            mask = (month == label)
            cur = df.loc[mask, task.metric_col].sum()
            if cur > 0:
                df.loc[mask, task.metric_col] *= target / cur   # exact-sum by blind rescale
    return tables, time.perf_counter() - t0


class NaiveRescaleBaseline(Baseline):
    """Faker scaffold + per-period multiply to hit each aggregate exactly.

    The point (review B2): this ALSO achieves AME = 0 — proving hitting one aggregate is
    trivial. What it does NOT do: respect *other* declared hard constraints (range /
    inequality → CSAT), and it needs a hand-built schema, not a natural-language spec.
    It isolates exactly what is, and is not, the contribution.
    """
    name = "naive_rescale"
    capabilities = Capabilities(
        cold_start=True, ingests_outcomes=True, deterministic=True, relational=False,
    )

    def generate(self, task, seed: int) -> GenResult:
        tables, secs = _faker_scaffold(task, seed, rescale_to_targets=True)
        return GenResult(tables=tables, wall_seconds=secs)


# --------------------------------------------------------------------------- #
# SDV — the imitation comparator (needs real data; cannot ingest outcomes)
# --------------------------------------------------------------------------- #

def _sdv_available() -> bool:
    return importlib.util.find_spec("sdv") is not None


class SDVBaseline(Baseline):
    """SDV GaussianCopula / CTGAN. Imitation: requires a reference dataset.

    On cold-start (spec-mode) tasks it has no training data and reports
    ran=False with reason — the honest record of CSC=0. On reference-mode tasks it
    trains on the supplied real table and samples; we then measure its conformance
    to the outcomes (which it never saw as targets) plus fidelity context.
    """
    def __init__(self, synthesizer: str = "gaussian_copula"):
        self.synthesizer = synthesizer
        self.name = f"sdv_{synthesizer}"
        # deterministic=True: reproducible UNDER A FIXED SEED once we seed torch/numpy
        # (verified). The honest differentiator vs the engine is therefore NOT
        # determinism but conformance (AME) and cold-start capability (CSC).
        self.capabilities = Capabilities(
            cold_start=False, ingests_outcomes=False,
            deterministic=True, relational=(synthesizer == "hma"),
        )

    def available(self) -> bool:
        return _sdv_available()

    def _seed_everything(self, seed: int) -> None:
        """Seed all RNGs SDV may touch so runs are reproducible under a fixed seed
        (review B3). Without this, CTGAN's torch RNG is uncontrolled and DET is
        meaningless. GaussianCopula is a fitted parametric model and is deterministic
        regardless; seeding makes CTGAN reproducible too."""
        import random
        random.seed(seed)
        np.random.seed(seed)
        try:
            import torch
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
        except Exception:
            pass

    def generate(self, task, seed: int) -> GenResult:
        import time
        # Cold-start tasks: SDV structurally cannot run (no training data).
        reference = getattr(task, "reference_tables", None)
        if not reference:
            return GenResult(tables={}, ran=False,
                             reason="SDV requires source data; task is cold-start (CSC=0)")
        self._seed_everything(seed)
        t0 = time.perf_counter()

        # --- HMA: multi-table relational synthesizer (review M2) ---
        if self.synthesizer == "hma":
            from sdv.metadata import Metadata
            from sdv.multi_table import HMASynthesizer
            # needs the full relational reference + FK metadata
            md = Metadata.detect_from_dataframes(reference)
            try:
                for (pt, pk, ct, ck) in getattr(task, "fks", []):
                    md.add_relationship(parent_table_name=pt, child_table_name=ct,
                                        parent_primary_key=pk, child_foreign_key=ck)
            except Exception:
                pass  # detect_from_dataframes may already infer them
            synth = HMASynthesizer(md)
            synth.fit(reference)
            sample = synth.sample(scale=1.0)
            return GenResult(tables=dict(sample), wall_seconds=time.perf_counter() - t0)

        # --- single-table synthesizers ---
        from sdv.metadata import Metadata
        primary = task.primary_table
        df = reference[primary]
        md = Metadata.detect_from_dataframe(df)
        if self.synthesizer == "gaussian_copula":
            from sdv.single_table import GaussianCopulaSynthesizer as S
            synth = S(md)
        elif self.synthesizer == "ctgan":
            from sdv.single_table import CTGANSynthesizer as S
            synth = S(md, epochs=int(getattr(task, "ctgan_epochs", 100)))
        else:
            raise ValueError(self.synthesizer)
        synth.fit(df)
        sample = synth.sample(num_rows=len(df))
        return GenResult(tables={primary: sample}, wall_seconds=time.perf_counter() - t0)


def all_baselines() -> List[Baseline]:
    """Construct the standard baseline set; SDV entries auto-skip if unavailable."""
    bl: List[Baseline] = [MisataBaseline(), FakerBaseline(), NaiveRescaleBaseline()]
    for s in ("gaussian_copula", "ctgan", "hma"):
        bl.append(SDVBaseline(s))
    return bl
