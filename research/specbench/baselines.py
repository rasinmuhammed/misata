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
        import time
        from faker import Faker
        t0 = time.perf_counter()
        fake = Faker()
        Faker.seed(seed)
        rng = np.random.default_rng(seed)

        # A *typical practitioner* Faker script for this schema: independent columns,
        # FK by sampling parent ids. It does NOT know the outcome targets — that is the
        # point. We build the same logical schema the task declares, generically.
        tables: Dict[str, pd.DataFrame] = {}
        for tbl in task.schema_tables:
            n = tbl["rows"]
            cols: Dict[str, Any] = {}
            cols[tbl["pk"]] = np.arange(1, n + 1)
            for col in tbl["columns"]:
                kind = col["kind"]
                name = col["name"]
                if kind == "metric":          # the column an outcome would target
                    # Faker has no notion of the target; draw a plausible positive value
                    cols[name] = rng.lognormal(mean=np.log(col.get("scale", 100)), sigma=0.6, size=n)
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
        return GenResult(tables=tables, wall_seconds=time.perf_counter() - t0)


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
        self.capabilities = Capabilities(
            cold_start=False, ingests_outcomes=False,
            deterministic=False, relational=(synthesizer == "hma"),
        )

    def available(self) -> bool:
        return _sdv_available()

    def generate(self, task, seed: int) -> GenResult:
        import time
        # Cold-start tasks: SDV structurally cannot run (no training data).
        reference = getattr(task, "reference_tables", None)
        if not reference:
            return GenResult(tables={}, ran=False,
                             reason="SDV requires source data; task is cold-start (CSC=0)")
        t0 = time.perf_counter()
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
    bl: List[Baseline] = [MisataBaseline(), FakerBaseline()]
    for s in ("gaussian_copula", "ctgan"):
        b = SDVBaseline(s)
        bl.append(b)
    return bl
