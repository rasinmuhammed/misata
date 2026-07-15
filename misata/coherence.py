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

_REGEXY_VALUE_RE = re.compile(r"[+*|\\]|\{\d+(,\d+)?\}|\(.*\)")


def _detect_pattern_leak(table: str, df: pd.DataFrame) -> List[CoherenceFinding]:
    """Values that look like unexpanded regex patterns ('Et+( Sj+){1,2}').

    A pattern that leaks raw into rows is the loudest possible fake-data tell
    (fraud field report: 1,500 merchants named like regexes)."""
    out: List[CoherenceFinding] = []
    for col in df.columns:
        if not _is_text_dtype(df[col]):
            continue
        s = df[col].dropna().astype(str)
        if s.empty:
            continue
        sample = s.head(200)
        hits = int(sample.apply(lambda v: bool(_REGEXY_VALUE_RE.search(v))).sum())
        if hits > 0.3 * len(sample):
            out.append(CoherenceFinding(
                "pattern_leak", "high", table, col,
                f"'{col}' values look like unexpanded regex patterns "
                f"(e.g. {sample.iloc[0]!r}); a pattern failed to expand.",
                rows_affected=int(len(s) * hits / len(sample)),
            ))
    return out


def _singular_head(table_name: str) -> str:
    return table_name.lower().rstrip("s")


def _detect_denormalized_mismatch(
    tables: Dict[str, pd.DataFrame]
) -> List[CoherenceFinding]:
    """A child column duplicating a parent attribute must agree with it.

    Convention-inferred: child has `<head>_id`, a table named `<head>s`
    exists, and both share a non-key column starting with `<head>_`
    (transactions.merchant_city ↔ merchants.merchant_city). Independent
    generation makes them disagree, and the first JOIN exposes it."""
    out: List[CoherenceFinding] = []
    by_head = {_singular_head(name): name for name in tables}
    for child_name, child in tables.items():
        if not isinstance(child, pd.DataFrame) or child.empty:
            continue
        for fk in [c for c in child.columns if c.lower().endswith("_id")]:
            head = fk.lower()[:-3]
            parent_name = by_head.get(head)
            if parent_name is None or parent_name == child_name:
                continue
            parent = tables[parent_name]
            pk = "id" if "id" in parent.columns else None
            if pk is None:
                continue
            shared = [
                c for c in child.columns
                if c in parent.columns and c != fk
                and not c.lower().endswith("_id")
                and c.lower().startswith(head + "_")
            ]
            for c in shared:
                mapped = child[fk].map(parent.set_index(pk)[c])
                both = mapped.notna() & child[c].notna()
                if both.sum() < 10:
                    continue
                mism = int((child[c][both].astype(str) != mapped[both].astype(str)).sum())
                if mism > 0.05 * both.sum():
                    out.append(CoherenceFinding(
                        "denormalized_mismatch", "high", child_name, c,
                        f"'{c}' disagrees with {parent_name}.{c} on {mism} of "
                        f"{int(both.sum())} rows; a denormalized parent "
                        f"attribute must equal the parent's value.",
                        rows_affected=mism,
                    ))
    return out


# ---------------------------------------------------------------------------
# Story-level detectors: the invariants that make a MULTI-TABLE dataset tell a
# consistent story. Single-table checks catch a bad column; these catch a bad
# relationship. Each one exists because it failed in a real audit first.
# ---------------------------------------------------------------------------

_SHIPPED_OK = {"shipped", "dispatched", "in_transit", "out_for_delivery",
               "delivered", "completed", "fulfilled", "returned", "refunded"}
_DELIVERED_OK = {"delivered", "completed", "fulfilled"}
_RARE_FLAG_TOKENS = ("fraud", "chargeback", "disputed", "is_deleted", "is_spam",
                     "is_bot", "blacklist", "banned")
_COUNTISH = ("count", "quantity", "qty", "num_", "items", "units", "visits",
             "sessions", "clicks", "views", "seats", "age")


def _detect_fk_orphans(tables, schema) -> List[CoherenceFinding]:
    out: List[CoherenceFinding] = []
    for rel in getattr(schema, "relationships", []) or []:
        child = tables.get(rel.child_table)
        parent = tables.get(rel.parent_table)
        if child is None or parent is None:
            continue
        if rel.child_key not in child.columns or rel.parent_key not in parent.columns:
            continue
        fk = child[rel.child_key].dropna()
        orphans = int((~fk.isin(parent[rel.parent_key])).sum())
        if orphans:
            out.append(CoherenceFinding(
                kind="fk_orphans", severity="high",
                table=rel.child_table, column=rel.child_key,
                message=(f"{orphans} rows reference a {rel.parent_table}."
                         f"{rel.parent_key} that does not exist"),
                rows_affected=orphans,
            ))
    return out


def _detect_cross_table_causality(tables, schema) -> List[CoherenceFinding]:
    """A child row's earliest timestamp must not precede its FK parent's."""
    out: List[CoherenceFinding] = []
    for rel in getattr(schema, "relationships", []) or []:
        child = tables.get(rel.child_table)
        parent = tables.get(rel.parent_table)
        if child is None or parent is None:
            continue
        if rel.child_key not in child.columns or rel.parent_key not in parent.columns:
            continue
        cdt = [c for c in child.columns if pd.api.types.is_datetime64_any_dtype(child[c])]
        pdt = [c for c in parent.columns if pd.api.types.is_datetime64_any_dtype(parent[c])]
        if not cdt or not pdt:
            continue
        birth = parent.set_index(rel.parent_key)[pdt].min(axis=1)
        birth = birth[~birth.index.duplicated(keep="first")]
        mapped = child[rel.child_key].map(birth)
        child_min = child[cdt].min(axis=1)
        bad = int(((child_min < mapped) & mapped.notna()).sum())
        if bad:
            out.append(CoherenceFinding(
                kind="temporal_causality", severity="high",
                table=rel.child_table, column=None,
                message=(f"{bad} rows have events dated before their "
                         f"{rel.parent_table} parent existed"),
                rows_affected=bad,
            ))
    return out


def _detect_rollup_mismatch(tables, schema) -> List[CoherenceFinding]:
    """A parent aggregate column must equal what its child rows sum to."""
    out: List[CoherenceFinding] = []
    try:
        from misata.rollups import collect_declared_rollups, infer_rollups
        specs = collect_declared_rollups(schema) + infer_rollups(schema)
    except Exception:
        return out
    for s in specs:
        parent = tables.get(s.parent_table)
        child = tables.get(s.from_table)
        if parent is None or child is None:
            continue
        needed = {s.fk} | ({s.column} if s.column else set())
        if (s.target_column not in parent.columns
                or s.parent_key not in parent.columns
                or not needed.issubset(child.columns)):
            continue
        if s.agg == "count":
            expected = child.groupby(s.fk).size()
        elif s.agg in ("sum", "mean", "max", "min"):
            expected = getattr(child.groupby(s.fk)[s.column], s.agg)()
        else:
            continue
        got = parent.set_index(s.parent_key)[s.target_column]
        joined = got.to_frame("got").join(expected.to_frame("want")).dropna()
        if joined.empty:
            continue
        bad = int((abs(joined["got"] - joined["want"]) > 0.01).sum())
        if bad:
            out.append(CoherenceFinding(
                kind="rollup_mismatch", severity="high",
                table=s.parent_table, column=s.target_column,
                message=(f"{bad} rows disagree with {s.agg}({s.from_table}"
                         f".{s.column or 'rows'}) over the relationship"),
                rows_affected=bad,
            ))
    return out


def _detect_group_share_mismatch(tables, schema) -> List[CoherenceFinding]:
    """Declared group shares must hold in the data: per declared period when
    an exact-target curve pairs with the spec, over the table total otherwise.
    Targets come from the same helper the generator uses, so the audit and the
    generator cannot disagree about what a share is worth."""
    out: List[CoherenceFinding] = []
    try:
        from misata.shares import (declared_group_targets, normalized_shares,
                                    split_total_by_shares)
    except Exception:
        return out
    for spec in getattr(schema, "group_shares", None) or []:
        df = tables.get(spec.table)
        if df is None or spec.measure not in df.columns or spec.group_column not in df.columns:
            continue
        measure = pd.to_numeric(df[spec.measure], errors="coerce").fillna(0)
        per_bucket = declared_group_targets(spec, schema)
        bad_groups = 0
        if per_bucket is not None:
            curve = next((c for c in schema.outcome_curves
                          if c.table == spec.table and c.column == spec.measure), None)
            if curve is None or curve.time_column not in df.columns:
                continue
            times = pd.to_datetime(df[curve.time_column], errors="coerce")
            for start, end, targets in per_bucket:
                in_bucket = (times >= start) & (times < end)
                if not in_bucket.any():
                    continue
                got = measure[in_bucket].groupby(
                    df.loc[in_bucket, spec.group_column]).sum()
                for label, t in targets.items():
                    if abs(round(float(got.get(label, 0.0)), 2) - t) > 0.01:
                        bad_groups += 1
        else:
            shares = normalized_shares(spec)
            if not shares:
                continue
            targets = split_total_by_shares(shares, float(measure.sum()))
            got = measure.groupby(df[spec.group_column]).sum()
            for label, t in targets.items():
                if abs(round(float(got.get(label, 0.0)), 2) - t) > 0.01:
                    bad_groups += 1
        if bad_groups:
            out.append(CoherenceFinding(
                kind="group_share_mismatch", severity="high",
                table=spec.table, column=spec.measure,
                message=(f"{bad_groups} group totals disagree with the declared "
                         f"shares of {spec.measure} across {spec.group_column}"),
                rows_affected=bad_groups,
            ))
    return out


def _detect_waterfall_mismatch(tables, schema) -> List[CoherenceFinding]:
    """A declared waterfall must reconcile in the data: every period's net
    movement equals the declared delta and the running balance hits every
    declared ending value. Targets come from the same helper the generator
    uses, so audit and generator cannot disagree."""
    out: List[CoherenceFinding] = []
    try:
        from misata.waterfall import declared_movements
    except Exception:
        return out
    for spec in getattr(schema, "waterfalls", None) or []:
        df = tables.get(spec.table)
        plan = declared_movements(spec) if df is not None else []
        needed = {spec.period_column, spec.type_column, spec.amount_column}
        if not plan or df is None or not needed.issubset(df.columns):
            continue
        amounts = pd.to_numeric(df[spec.amount_column], errors="coerce").fillna(0)
        periods = df[spec.period_column].astype(str)
        types = df[spec.type_column].astype(str)
        inflow_labels = {l for _, _, ins, _ in plan for l in ins}
        signed = amounts.where(types.isin(inflow_labels), -amounts)
        bad_periods = 0
        running = round(float(spec.starting_value), 2)
        for period, end, _ins, _outs in plan:
            net = round(float(signed[periods == period].sum()), 2)
            running = round(running + net, 2)
            if abs(running - end) > 0.01:
                bad_periods += 1
        if bad_periods:
            out.append(CoherenceFinding(
                kind="waterfall_mismatch", severity="high",
                table=spec.table, column=spec.amount_column,
                message=(f"running balance misses the declared ending value "
                         f"in {bad_periods} period(s)"),
                rows_affected=bad_periods,
            ))
    return out


def _audit_capsule(schema):
    """Rebuild the capsule the generator would attach, for audit use.

    Sources, in generation's own order: registry auto-attach from the schema's
    tables/columns, then the user's capsule file. Returns None when neither
    contributes anything band-related."""
    try:
        from misata.domain_capsule import DomainCapsule
        capsule = DomainCapsule()
        try:
            from misata.capsule_registry import auto_attach_capsules
            auto_attach_capsules(schema, capsule)
        except Exception:
            pass
        capsule_file = getattr(getattr(schema, "realism", None), "capsule_file", None)
        if capsule_file:
            from misata.capsules import load_capsule, merge_into
            capsule = merge_into(capsule, load_capsule(capsule_file))
        return capsule if getattr(capsule, "price_bands", None) else None
    except Exception:
        return None


def _detect_price_band_violation(tables, schema) -> List[CoherenceFinding]:
    """A price must sit inside the band its category declares. Only fires
    when a capsule with price bands is attached; a $500 jar of honey next to
    a "Honey: 4-25" band is a defect whoever generated the row."""
    out: List[CoherenceFinding] = []
    capsule = _audit_capsule(schema)
    if capsule is None:
        return out
    for price_col, spec in capsule.price_bands.items():
        parent_name = str(spec.get("parent", "")).lower()
        bands = {str(k).strip().lower(): v for k, v in (spec.get("bands") or {}).items()}
        if not parent_name or not bands:
            continue
        for tname, df in tables.items():
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue
            p_col = next((c for c in df.columns if c.lower() == price_col), None)
            c_col = next((c for c in df.columns if c.lower() == parent_name), None)
            if p_col is None or c_col is None:
                continue
            price = pd.to_numeric(df[p_col], errors="coerce")
            cats = df[c_col].astype(str).str.strip().str.lower()
            bad = 0
            for cat, band in bands.items():
                lo, hi = float(band[0]), float(band[1])
                in_cat = cats == cat
                if not in_cat.any():
                    continue
                # Tolerance of one currency unit absorbs ending snaps at edges.
                bad += int(((price[in_cat] < lo - 1.0) | (price[in_cat] > hi + 1.0)).sum())
            if bad:
                out.append(CoherenceFinding(
                    kind="price_band_violation", severity="high",
                    table=tname, column=p_col,
                    message=(f"{bad} rows price outside their {c_col} band "
                             f"declared by the domain capsule"),
                    rows_affected=bad,
                ))
    return out


def _detect_status_gating(table: str, df: pd.DataFrame) -> List[CoherenceFinding]:
    """Ship/deliver dates and tracking codes only belong on rows whose status
    reached that stage."""
    out: List[CoherenceFinding] = []
    status_col = next((c for c in df.columns
                       if c.lower() in ("status", "order_status", "fulfillment_status")),
                      None)
    if status_col is None:
        return out
    status = df[status_col].astype(str).str.strip().str.lower()
    for col in df.columns:
        lc = col.lower()
        if "deliver" in lc and ("date" in lc or "time" in lc or lc.endswith("_at")):
            allowed = _DELIVERED_OK
        elif (("ship" in lc or "dispatch" in lc)
              and ("date" in lc or "time" in lc or lc.endswith("_at"))) \
                or "tracking" in lc:
            allowed = _SHIPPED_OK
        else:
            continue
        if not (set(status.unique()) & allowed):
            continue
        bad = int((df[col].notna() & ~status.isin(allowed)).sum())
        if bad:
            out.append(CoherenceFinding(
                kind="status_gating", severity="medium", table=table, column=col,
                message=f"{bad} rows carry {col} although their status never reached that stage",
                rows_affected=bad,
            ))
    return out


def _detect_bounds(table: str, df: pd.DataFrame) -> List[CoherenceFinding]:
    """Counts must be non-negative; percents in 0-100; rates in 0-1."""
    out: List[CoherenceFinding] = []
    for col in df.columns:
        s = _numeric(df[col])
        if s.isna().all():
            continue
        lc = col.lower()
        if any(t in lc for t in _COUNTISH) and not lc.startswith(("temp", "delta", "change", "net_")):
            bad = int((s < 0).sum())
            if bad:
                out.append(CoherenceFinding(
                    kind="bounds", severity="high", table=table, column=col,
                    message=f"{bad} negative values in a count-like column",
                    rows_affected=bad))
        if lc.endswith(("_percent", "_pct", "_percentage")):
            bad = int(((s < 0) | (s > 100)).sum())
            if bad:
                out.append(CoherenceFinding(
                    kind="bounds", severity="high", table=table, column=col,
                    message=f"{bad} values outside 0-100 in a percent column",
                    rows_affected=bad))
        if lc.endswith(("_rate", "_ratio", "_share", "_probability")):
            bad = int(((s < 0) | (s > 1.0001)).sum())
            if bad:
                out.append(CoherenceFinding(
                    kind="bounds", severity="high", table=table, column=col,
                    message=f"{bad} values outside 0-1 in a rate column",
                    rows_affected=bad))
    return out


def _detect_flag_rates(table: str, df: pd.DataFrame) -> List[CoherenceFinding]:
    """A rare-event boolean flag that is true on a third of rows is not rare."""
    out: List[CoherenceFinding] = []
    for col in df.columns:
        lc = col.lower()
        if not any(t in lc for t in _RARE_FLAG_TOKENS):
            continue
        s = df[col]
        if s.dtype != bool and not set(pd.unique(s.dropna())) <= {True, False, 0, 1}:
            continue
        rate = float(pd.Series(s).fillna(False).astype(bool).mean())
        if rate > 0.30:
            out.append(CoherenceFinding(
                kind="implausible_rate", severity="medium", table=table, column=col,
                message=f"{col} is true on {rate:.0%} of rows; rare-event flags should be rare",
                rows_affected=int(rate * len(df))))
    return out


def _detect_age_dob(table: str, df: pd.DataFrame) -> List[CoherenceFinding]:
    age_col = next((c for c in df.columns if c.lower() in ("age", "age_years")), None)
    dob_col = next((c for c in df.columns if c.lower() in
                    ("date_of_birth", "birth_date", "birthdate", "dob")), None)
    if age_col is None or dob_col is None:
        return []
    dob = pd.to_datetime(df[dob_col], errors="coerce")
    if dob.isna().all():
        return []
    ref = pd.Timestamp("2025-06-01")
    for c in df.columns:
        if c != dob_col and ("date" in c.lower() or c.lower().endswith("_at")):
            other = pd.to_datetime(df[c], errors="coerce")
            if other.notna().any():
                ref = max(ref, other.max())
    implied = ((ref - dob).dt.days / 365.25).round()
    bad = int((abs(_numeric(df[age_col]) - implied) > 2).sum())
    if bad:
        return [CoherenceFinding(
            kind="age_dob_mismatch", severity="high", table=table, column=age_col,
            message=f"{bad} rows where {age_col} disagrees with {dob_col}",
            rows_affected=bad)]
    return []


def _detect_sibling_percent_sum(table: str, df: pd.DataFrame) -> List[CoherenceFinding]:
    """Share-of-whole siblings (pct_cash, pct_card, pct_online) should sum to
    ~100 (or ~1). Advisory: detection only, never forced, because percent
    columns are not always partitions of the same whole."""
    groups: Dict[str, List[str]] = {}
    for col in df.columns:
        lc = col.lower()
        for suffix in ("_pct", "_percent", "_share", "_percentage"):
            if lc.endswith(suffix):
                groups.setdefault(suffix, []).append(col)
    out: List[CoherenceFinding] = []
    for suffix, cols in groups.items():
        if len(cols) < 2:
            continue
        total = df[cols].apply(_numeric).sum(axis=1)
        target = 1.0 if total.median() <= 1.5 else 100.0
        off = int((abs(total - target) > target * 0.05).sum())
        if off > len(df) * 0.5:
            out.append(CoherenceFinding(
                kind="sibling_percent_sum", severity="low", table=table,
                column=", ".join(cols),
                message=(f"{len(cols)} sibling share columns sum to neither "
                         f"~{target:g} nor a consistent whole on {off} rows"),
                rows_affected=off))
    return out


def story_audit(
    tables: Dict[str, pd.DataFrame],
    schema: Any = None,
    *,
    repair: bool = False,
    seed: Optional[int] = 42,
) -> CoherenceReport:
    """Grade a generated multi-table dataset against the full invariant
    catalog: everything :func:`coherence_audit` checks, plus the
    relationship-level story checks (FK orphans, cross-table temporal
    causality, roll-up agreement) that need the schema.

    This is the self-check that keeps "sells a story" honest: run it after
    generation and a dataset that contradicts itself cannot pass silently.

    Args:
        tables: mapping of table name to DataFrame.
        schema: the SchemaConfig the tables were generated from. Without it,
                only table-local checks run.
        repair: apply the safe repair subset in place (see coherence_audit).
        seed:   RNG seed for repairs that sample.

    Returns:
        A :class:`CoherenceReport`; check ``.clean`` or read ``.summary()``.
    """
    return coherence_audit(tables, repair=repair, seed=seed, schema=schema)


def coherence_audit(
    tables: Dict[str, pd.DataFrame],
    *,
    repair: bool = False,
    seed: Optional[int] = 42,
    schema: Any = None,
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

    report.findings.extend(_detect_denormalized_mismatch(tables))
    if schema is not None:
        report.findings.extend(_detect_fk_orphans(tables, schema))
        report.findings.extend(_detect_cross_table_causality(tables, schema))
        report.findings.extend(_detect_rollup_mismatch(tables, schema))
        report.findings.extend(_detect_group_share_mismatch(tables, schema))
        report.findings.extend(_detect_waterfall_mismatch(tables, schema))
        report.findings.extend(_detect_price_band_violation(tables, schema))
    for name, df in tables.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        report.findings.extend(_detect_pattern_leak(name, df))
        report.findings.extend(_detect_near_constant(name, df))
        report.findings.extend(_detect_label_filler(name, df))
        report.findings.extend(_detect_and_repair_temporal(name, df, repair))
        report.findings.extend(_detect_scale(name, df))
        report.findings.extend(_detect_and_repair_geo(name, df, repair, rng))
        report.findings.extend(_detect_tenure(name, df))
        report.findings.extend(_detect_and_repair_derived_math(name, df, repair))
        report.findings.extend(_detect_status_gating(name, df))
        report.findings.extend(_detect_bounds(name, df))
        report.findings.extend(_detect_flag_rates(name, df))
        report.findings.extend(_detect_age_dob(name, df))
        report.findings.extend(_detect_sibling_percent_sum(name, df))

    return report
