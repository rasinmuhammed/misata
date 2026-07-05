"""Post-generation coherence audit: does this data survive a human reading it?

The realism engine fixes contradictions as it generates. This module is the
second line of defence: an advisory pass over the FINISHED tables that a person
(or the studio Oracle panel) can read, detecting the handful of defects that
most loudly say "this is synthetic":

  1. near-constant numerics   — a "price" column that is 49.99 in every row
  2. filler in label columns  — a status/type column full of lorem sentences or
                                 "Value A"/"Item 1"
  3. temporal disorder        — dropoff_time before pickup_time
  4. scale absurdity          — a human age of 4,000; a fare of $9,000,000
  5. geographic contradiction — a city that does not belong to its row's country
  6. tenure contradiction     — a signup_date AFTER a last_seen/tenure endpoint
  7. broken derived math      — total != quantity * unit_price

Each finding is advisory by default. ``coherence_audit(tables, repair=True)``
applies the safe subset of repairs (temporal reorder, derived-math recompute,
geo remap) in place and reports what it changed. Detection never mutates.

The public surface is intentionally small::

    from misata import coherence_audit
    report = coherence_audit(tables)          # detect only
    report = coherence_audit(tables, repair=True)   # detect + repair in place
    report.to_dict()                          # studio / JSON friendly
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Severity ranks: "high" reads as obviously fake, "medium" is suspicious on a
# second look, "low" is a soft smell.
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class CoherenceFinding:
    """One coherence defect located at a table (and optionally a column)."""

    kind: str            # near_constant | label_filler | temporal_disorder | …
    severity: str        # high | medium | low
    table: str
    column: Optional[str]
    message: str
    rows_affected: int = 0
    repaired: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "table": self.table,
            "column": self.column,
            "message": self.message,
            "rows_affected": int(self.rows_affected),
            "repaired": bool(self.repaired),
        }


@dataclass
class CoherenceReport:
    """Advisory coherence report over a generated dataset."""

    findings: List[CoherenceFinding] = field(default_factory=list)
    repaired: bool = False

    @property
    def clean(self) -> bool:
        """True when no unrepaired findings remain."""
        return not any(not f.repaired for f in self.findings)

    @property
    def score(self) -> float:
        """0–100 advisory coherence score (100 = clean).

        High findings cost 12, medium 5, low 2. Repaired findings cost nothing.
        """
        penalty = 0
        for f in self.findings:
            if f.repaired:
                continue
            penalty += {"high": 12, "medium": 5, "low": 2}.get(f.severity, 5)
        return float(max(0, 100 - penalty))

    def by_severity(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for f in self.findings:
            if f.repaired:
                continue
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def summary(self) -> str:
        if self.clean:
            return "Coherence: clean — no reader-visible contradictions."
        counts = self.by_severity()
        parts = [f"{counts[s]} {s}" for s in ("high", "medium", "low") if counts.get(s)]
        n_repaired = sum(1 for f in self.findings if f.repaired)
        tail = f" ({n_repaired} repaired)" if n_repaired else ""
        return f"Coherence score {self.score:.0f}/100 — " + ", ".join(parts) + tail

    def to_dict(self) -> Dict[str, Any]:
        ordered = sorted(
            self.findings,
            key=lambda f: (f.repaired, _SEVERITY_ORDER.get(f.severity, 1)),
        )
        return {
            "misata_report": "coherence",
            "version": 1,
            "clean": self.clean,
            "score": self.score,
            "repaired": self.repaired,
            "counts": self.by_severity(),
            "summary": self.summary(),
            "findings": [f.to_dict() for f in ordered],
        }


# --------------------------------------------------------------------------- #
# Column-role heuristics
# --------------------------------------------------------------------------- #

_LABEL_NAME_TOKENS = (
    "status", "type", "category", "tier", "level", "kind", "stage", "state",
    "priority", "severity", "segment", "channel", "method", "grade", "plan",
    "mode", "reason", "label", "class",
)

# Human-scale numeric columns and their plausible [min, max] envelopes. Values
# outside these are almost certainly a unit/scale error, not a fat tail.
_SCALE_ENVELOPES = {
    "age": (0, 120),
    "year_built": (1600, 2035),
    "rating": (0, 5),
    "stars": (0, 5),
    "score": (0, 100),
    "percentage": (0, 100),
    "percent": (0, 100),
    "quantity": (0, 100000),
    "hour": (0, 24),
    "hours": (0, 10000),
    "minute": (0, 60),
    "latitude": (-90, 90),
    "longitude": (-180, 180),
}

_FILLER_SUBSTRINGS = (
    "designed for everyday use", "built for teams", "a customer favorite",
    "combines premium materials", "lorem ipsum", "reliable performance",
)
_FILLER_RE = re.compile(r"^(value|item|type|category|option|label)\s*[a-z0-9]$", re.I)


def _is_label_column(name: str) -> bool:
    low = name.lower()
    return any(low == t or low.endswith("_" + t) for t in _LABEL_NAME_TOKENS)


def _scale_envelope_for(name: str):
    low = name.lower()
    for key, env in _SCALE_ENVELOPES.items():
        if low == key or low.endswith("_" + key) or low.startswith(key + "_"):
            return env
    return None


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _is_text_dtype(series: pd.Series) -> bool:
    """String columns are ``str``/``string`` dtype (not ``object``) under
    pandas string inference; accept both so detectors don't skip them."""
    return pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)


# --------------------------------------------------------------------------- #
# Detectors  (each returns findings; repair happens in the mutating helpers)
# --------------------------------------------------------------------------- #

def _detect_near_constant(table: str, df: pd.DataFrame) -> List[CoherenceFinding]:
    out: List[CoherenceFinding] = []
    for col in df.columns:
        low = col.lower()
        if low == "id" or low.endswith("_id") or df[col].dtype == bool:
            continue
        # Datetime columns (and date/time-named columns) are the temporal
        # detector's job; a legitimately single-day sample must not read as a
        # "constant measure".
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        if any(t in low for t in ("date", "_at", "time", "timestamp")):
            continue
        s = _numeric(df[col])
        if s.notna().sum() < max(20, 0.5 * len(df)):
            continue
        vals = s.dropna()
        if vals.nunique() <= 1:
            # A genuinely constant reference value (a fee schedule) is fine on a
            # tiny lookup table; only flag it on a sizeable transactional table.
            if len(df) >= 50:
                out.append(CoherenceFinding(
                    "near_constant", "high", table, col,
                    f"'{col}' is identical in all {len(df)} rows "
                    f"(value {vals.iloc[0]!r}); real measures vary.",
                    rows_affected=len(df),
                ))
            continue
        mean = vals.mean()
        if len(df) >= 50 and abs(mean) > 1e-9:
            rel = vals.std() / abs(mean)
            # A label-like numeric (few distinct small ints) legitimately has
            # low spread; only flag continuous-looking columns.
            if rel < 0.002 and vals.nunique() > 5:
                out.append(CoherenceFinding(
                    "near_constant", "medium", table, col,
                    f"'{col}' is effectively constant "
                    f"(relative spread {rel:.4f}); looks copy-pasted.",
                    rows_affected=len(df),
                ))
    return out


def _detect_label_filler(table: str, df: pd.DataFrame) -> List[CoherenceFinding]:
    out: List[CoherenceFinding] = []
    for col in df.columns:
        if not _is_text_dtype(df[col]) or not _is_label_column(col):
            continue
        s = df[col].dropna().astype(str)
        if s.empty:
            continue
        n = len(s)
        filler = s.apply(
            lambda v: bool(_FILLER_RE.match(v.strip()))
            or any(sub in v.lower() for sub in _FILLER_SUBSTRINGS)
            or len(v.split()) > 8  # a label is not a sentence
        )
        hits = int(filler.sum())
        if hits > 0.2 * n:
            out.append(CoherenceFinding(
                "label_filler", "high", table, col,
                f"'{col}' is a label column but {hits}/{n} values look like "
                f"filler sentences or placeholders.",
                rows_affected=hits,
            ))
    return out


# Ordered event tokens: earlier tokens must not carry later timestamps.
_TIME_ORDER = ("request", "order", "created", "signup", "start", "begin",
               "pickup", "departure", "dispatch", "sent", "ship",
               "process", "update", "arrival", "deliver", "dropoff",
               "complete", "finish", "end", "close", "resolve", "cancel")


def _time_rank(col: str) -> int:
    c = col.lower()
    for i, tok in enumerate(_TIME_ORDER):
        if tok in c:
            return i
    return -1


def _time_columns(df: pd.DataFrame) -> List[str]:
    cols = []
    for c in df.columns:
        cl = c.lower()
        if _time_rank(c) >= 0 and ("time" in cl or "date" in cl or cl.endswith("_at")):
            cols.append(c)
    return sorted(cols, key=_time_rank)


def _detect_and_repair_temporal(
    table: str, df: pd.DataFrame, repair: bool
) -> List[CoherenceFinding]:
    chain = _time_columns(df)
    if len(chain) < 2:
        return []
    try:
        vals = df[chain].apply(pd.to_datetime, errors="coerce")
    except Exception:
        return []
    out: List[CoherenceFinding] = []
    for a, b in zip(chain, chain[1:]):
        both = vals[a].notna() & vals[b].notna()
        disordered = both & (vals[a] > vals[b])
        n = int(disordered.sum())
        if n > 0:
            out.append(CoherenceFinding(
                "temporal_disorder", "high", table, f"{a} → {b}",
                f"{n} rows have '{a}' after '{b}' (event out of order).",
                rows_affected=n, repaired=repair,
            ))
    if out and repair:
        # Per-row sort of the whole chain preserves marginals while removing
        # every inversion at once.
        ordered = np.sort(vals.values.astype("datetime64[ns]"), axis=1)
        valid = ~np.isnat(vals.values.astype("datetime64[ns]")).any(axis=1)
        for i, col in enumerate(chain):
            new = pd.Series(ordered[:, i], index=df.index)
            if _is_text_dtype(df[col]):
                new = new.dt.strftime("%Y-%m-%d %H:%M:%S")
            df.loc[valid, col] = new[valid]
    return out


def _detect_scale(table: str, df: pd.DataFrame) -> List[CoherenceFinding]:
    out: List[CoherenceFinding] = []
    for col in df.columns:
        env = _scale_envelope_for(col)
        if env is None:
            continue
        s = _numeric(df[col]).dropna()
        if s.empty:
            continue
        lo, hi = env
        bad = int(((s < lo) | (s > hi)).sum())
        if bad > 0:
            out.append(CoherenceFinding(
                "scale_absurdity", "high", table, col,
                f"{bad} rows of '{col}' fall outside a plausible range "
                f"[{lo}, {hi}] (min {s.min():.2f}, max {s.max():.2f}).",
                rows_affected=bad,
            ))
    return out


def _detect_and_repair_geo(
    table: str, df: pd.DataFrame, repair: bool, rng: np.random.Generator
) -> List[CoherenceFinding]:
    from misata.vocab_seeds import CITIES_BY_COUNTRY as COUNTRY_CITIES
    city_col = next((c for c in df.columns
                     if c.lower() == "city" or c.lower().endswith("_city")), None)
    country_col = next((c for c in df.columns
                        if c.lower() == "country" or c.lower().endswith("_country")), None)
    if city_col is None or country_col is None:
        return []
    countries = df[country_col].astype(str)
    known = countries.isin(COUNTRY_CITIES.keys())
    if not known.any():
        return []
    def _mismatch(row):
        c = str(row[country_col])
        return c in COUNTRY_CITIES and str(row[city_col]) not in COUNTRY_CITIES[c]
    bad_mask = known & df.apply(_mismatch, axis=1)
    n = int(bad_mask.sum())
    if n == 0:
        return []
    finding = CoherenceFinding(
        "geo_contradiction", "medium", table, f"{city_col}/{country_col}",
        f"{n} rows place '{city_col}' in a country it does not belong to.",
        rows_affected=n, repaired=repair,
    )
    if repair:
        df.loc[bad_mask, city_col] = [
            rng.choice(COUNTRY_CITIES[str(c)]) for c in countries[bad_mask]
        ]
    return [finding]


def _detect_tenure(table: str, df: pd.DataFrame) -> List[CoherenceFinding]:
    """signup/created must not come AFTER a last_seen / tenure endpoint."""
    start = next((c for c in df.columns
                  if any(t in c.lower() for t in ("signup", "sign_up", "registered", "joined", "created", "onboard"))
                  and ("date" in c.lower() or "time" in c.lower() or c.lower().endswith("_at"))), None)
    end = next((c for c in df.columns
                if any(t in c.lower() for t in ("last_seen", "last_active", "last_login", "churn", "closed", "cancel"))
                and ("date" in c.lower() or "time" in c.lower() or c.lower().endswith("_at"))), None)
    if not start or not end or start == end:
        return []
    s = pd.to_datetime(df[start], errors="coerce")
    e = pd.to_datetime(df[end], errors="coerce")
    both = s.notna() & e.notna()
    bad = int((both & (s > e)).sum())
    if bad == 0:
        return []
    return [CoherenceFinding(
        "tenure_contradiction", "medium", table, f"{start} → {end}",
        f"{bad} rows have '{start}' after '{end}' (account ends before it begins).",
        rows_affected=bad,
    )]


def _detect_and_repair_derived_math(
    table: str, df: pd.DataFrame, repair: bool
) -> List[CoherenceFinding]:
    """total ?= quantity * unit_price (- discount); amount ?= base * multiplier."""
    out: List[CoherenceFinding] = []
    lower = {c.lower(): c for c in df.columns}

    def col(name):
        return df[lower[name]] if name in lower else None

    checks = []
    # quantity * unit_price [- discount] = line_total / total
    if "quantity" in lower and "unit_price" in lower:
        target = next((lower[t] for t in ("line_total", "total", "amount", "subtotal")
                       if t in lower), None)
        if target:
            expected = _numeric(col("quantity")) * _numeric(col("unit_price"))
            if "discount" in lower:
                expected = expected - _numeric(col("discount"))
            checks.append((target, expected.clip(lower=0)))
    # base_* * *_multiplier = *_amount
    mult = next((lower[c] for c in lower if c.endswith("_multiplier") or c == "multiplier"), None)
    base = next((lower[c] for c in lower if c.startswith("base_")), None)
    if mult and base:
        stem = base[len("base_"):] if base.lower().startswith("base_") else ""
        target = next((lower[t] for t in (f"{stem}_amount", f"{stem}_total", stem, "amount", "total")
                       if t in lower and lower[t] != base and lower[t] != mult), None)
        if target:
            expected = _numeric(df[base]) * _numeric(df[mult])
            checks.append((target, expected))

    for target, expected in checks:
        actual = _numeric(df[target])
        both = actual.notna() & expected.notna()
        # Tolerance: a cent of rounding is fine; anything larger is a real break.
        bad_mask = both & ((actual - expected).abs() > 0.02)
        n = int(bad_mask.sum())
        if n > 0.02 * max(1, both.sum()):
            out.append(CoherenceFinding(
                "broken_derived_math", "high", table, target,
                f"{n} rows where '{target}' does not equal its formula "
                f"(off by up to {float((actual - expected).abs().max()):.2f}).",
                rows_affected=n, repaired=repair,
            ))
            if repair:
                df.loc[bad_mask, target] = np.round(expected[bad_mask], 2)
    return out


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def coherence_audit(
    tables: Dict[str, pd.DataFrame],
    *,
    repair: bool = False,
    seed: Optional[int] = 42,
) -> CoherenceReport:
    """Audit generated tables for reader-visible contradictions.

    Args:
        tables:  mapping of table name → DataFrame (as returned by
                 :func:`misata.generate_from_schema`).
        repair:  when True, apply the safe subset of fixes IN PLACE (temporal
                 reorder, geographic remap, derived-math recompute) and mark
                 those findings ``repaired``. Detection-only defects
                 (near-constant, filler, scale, tenure) are reported, not
                 mutated — they signal a schema problem, not a row problem.
        seed:    RNG seed for any repair that samples (geographic remap).

    Returns:
        A :class:`CoherenceReport`.
    """
    rng = np.random.default_rng(seed if seed is not None else 42)
    report = CoherenceReport(repaired=repair)

    for name, df in tables.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        report.findings.extend(_detect_near_constant(name, df))
        report.findings.extend(_detect_label_filler(name, df))
        report.findings.extend(_detect_and_repair_temporal(name, df, repair))
        report.findings.extend(_detect_scale(name, df))
        report.findings.extend(_detect_and_repair_geo(name, df, repair, rng))
        report.findings.extend(_detect_tenure(name, df))
        report.findings.extend(_detect_and_repair_derived_math(name, df, repair))

    return report
