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
    # Specific score conventions must precede the generic "score" catchall
    # (first match in dict order wins): sentiment/polarity scores are -1..1,
    # NPS ranges -100..100.
    "sentiment_score": (-1, 1),
    "polarity_score": (-1, 1),
    "polarity": (-1, 1),
    "nps_score": (-100, 100),
    "nps": (-100, 100),
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
    # A name that merely contains chain tokens is not a date ("sentiment"
    # contains both "sent" and "time"); an all-NaT candidate sitting between
    # two real dates would otherwise break the adjacent-pair comparison.
    chain = [c for c in chain if not vals[c].isna().all()]
    if len(chain) < 2:
        return []
    vals = vals[chain]
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
        if s.via:
            # Multi-hop: audit through the same declared chain the generator
            # used — the DuckDB/SQL layer is the fully independent check; this
            # one catches a declared chain the generator failed to honour.
            from misata.rollups import resolve_via_frame
            child = resolve_via_frame(
                s, tables, getattr(schema, "relationships", []) or [])
            if child is None:
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


def _detect_when_then_violation(tables, schema) -> List[CoherenceFinding]:
    """Every declared when_then implication must hold in the emitted rows."""
    out: List[CoherenceFinding] = []
    for table_cfg in getattr(schema, "tables", []) or []:
        df = tables.get(table_cfg.name)
        if df is None or df.empty:
            continue
        for c in getattr(table_cfg, "constraints", []) or []:
            if getattr(c, "type", None) != "when_then":
                continue
            wc, tc = c.when_column, c.then_column
            if wc not in df.columns or tc not in df.columns or c.then is None:
                continue
            col, wv, op = df[wc], c.when_value, c.when_op
            if op == "==":
                mask = col == wv
            elif op == "!=":
                mask = col != wv
            elif op == "in":
                mask = col.isin(wv if isinstance(wv, (list, tuple, set)) else [wv])
            elif op == "not_in":
                mask = ~col.isin(wv if isinstance(wv, (list, tuple, set)) else [wv])
            else:
                continue   # ordering ops: enforcement-only for now
            mask = mask.fillna(False)
            if c.then == "null":
                bad = int((mask & df[tc].notna()).sum())
            elif c.then == "not_null":
                bad = int((mask & df[tc].isna()).sum())
            elif c.then == "set":
                bad = int((mask & (df[tc] != c.then_value)).sum())
            else:
                continue
            if bad:
                out.append(CoherenceFinding(
                    kind="when_then_violation", severity="high",
                    table=table_cfg.name, column=tc,
                    message=(f"{bad} rows violate declared rule '{c.name}': "
                             f"when {wc} {op} {wv!r} then {tc} is {c.then}"),
                    rows_affected=bad,
                ))
    return out


def _detect_lifecycle_violation(tables, schema) -> List[CoherenceFinding]:
    """Every row's state must imply a legal, fully-timestamped, ordered history.

    Checked independently of the generator: the path is re-derived from the
    declared transitions here, so a bug in the lifecycle pass surfaces as a
    finding rather than being confirmed by the code that caused it.
    """
    out: List[CoherenceFinding] = []
    for spec in (getattr(schema, "lifecycles", None) or []):
        df = tables.get(spec.table)
        if df is None or df.empty or spec.state_column not in df.columns:
            continue
        states = set(spec.state_names())
        status = df[spec.state_column]

        undeclared = int((~status.isin(states)).sum())
        if undeclared:
            out.append(CoherenceFinding(
                kind="lifecycle_illegal_state", severity="high",
                table=spec.table, column=spec.state_column,
                message=(f"{undeclared} rows hold a state not declared in "
                         f"lifecycle '{spec.name}'"),
                rows_affected=undeclared,
            ))

        for state in spec.state_names():
            path = spec.path_to(state)
            if path is None:
                continue
            on_path = {p for p in path}
            in_state = status == state
            if not in_state.any():
                continue
            for st in spec.state_names():
                col = spec.timestamp_of(st)
                if not col or col not in df.columns:
                    continue
                vals = df.loc[in_state, col]
                if st in on_path:
                    bad = int(vals.isna().sum())
                    if bad:
                        out.append(CoherenceFinding(
                            kind="lifecycle_missing_timestamp", severity="high",
                            table=spec.table, column=col,
                            message=(f"{bad} rows in state '{state}' are missing "
                                     f"'{col}', but '{st}' is on their path"),
                            rows_affected=bad,
                        ))
                else:
                    bad = int(vals.notna().sum())
                    if bad:
                        out.append(CoherenceFinding(
                            kind="lifecycle_impossible_timestamp", severity="high",
                            table=spec.table, column=col,
                            message=(f"{bad} rows in state '{state}' carry '{col}', "
                                     f"but '{st}' is not on their path"),
                            rows_affected=bad,
                        ))

            # Path order: consecutive timestamped states must ascend.
            stamped = [spec.timestamp_of(p) for p in path]
            stamped = [c for c in stamped if c and c in df.columns]
            for a_col, b_col in zip(stamped, stamped[1:]):
                pair = df.loc[in_state, [a_col, b_col]].dropna()
                if pair.empty:
                    continue
                bad = int((pair[b_col] < pair[a_col]).sum())
                if bad:
                    out.append(CoherenceFinding(
                        kind="lifecycle_out_of_order", severity="high",
                        table=spec.table, column=b_col,
                        message=(f"{bad} rows in state '{state}' have {b_col} "
                                 f"before {a_col}, against the declared path"),
                        rows_affected=bad,
                    ))

        # The chain must postdate its declared start.
        if spec.start_column and spec.start_column in df.columns:
            start = pd.to_datetime(df[spec.start_column], errors="coerce")
            for col in spec.timestamp_columns():
                if col not in df.columns:
                    continue
                ts = pd.to_datetime(df[col], errors="coerce")
                bad = int(((ts < start) & ts.notna() & start.notna()).sum())
                if bad:
                    out.append(CoherenceFinding(
                        kind="lifecycle_precedes_start", severity="high",
                        table=spec.table, column=col,
                        message=(f"{bad} rows have {col} before "
                                 f"{spec.start_column}"),
                        rows_affected=bad,
                    ))
    return out


def _detect_dynamics_violation(tables, schema) -> List[CoherenceFinding]:
    """Verify declared retention, missingness, and late arrival independently.

    Recomputed here from the emitted rows rather than trusting the pass that
    wrote them, so a bug in the generator surfaces as a finding instead of being
    confirmed by its own author.
    """
    out: List[CoherenceFinding] = []
    from misata.dynamics import exact_count

    # ---- cohort retention ------------------------------------------------
    for spec in (getattr(schema, "retention", None) or []):
        ev, co = tables.get(spec.table), tables.get(spec.cohort_table)
        if ev is None or co is None or ev.empty or co.empty:
            continue
        need = {spec.cohort_key, spec.event_time}
        if not need.issubset(ev.columns):
            continue
        if not {spec.cohort_key, spec.cohort_time}.issubset(co.columns):
            continue
        freq = {"day": "D", "week": "W", "month": "M"}[spec.unit]
        c = co[[spec.cohort_key, spec.cohort_time]].dropna().copy()
        c["_c"] = pd.to_datetime(c[spec.cohort_time]).dt.to_period(freq)
        e = ev[[spec.cohort_key, spec.event_time]].dropna().copy()
        e["_p"] = pd.to_datetime(e[spec.event_time]).dt.to_period(freq)
        m = e.merge(c[[spec.cohort_key, "_c"]], on=spec.cohort_key, how="inner")
        if m.empty:
            continue
        m["_off"] = (m["_p"] - m["_c"]).apply(lambda x: x.n)
        sizes = c.groupby("_c")[spec.cohort_key].nunique()
        for offset, frac in sorted(spec.curve.items()):
            active = (m[m["_off"] == int(offset)]
                      .groupby("_c")[spec.cohort_key].nunique())
            bad = 0
            for cohort, size in sizes.items():
                if size <= 0:
                    continue
                want = exact_count(int(size), float(frac))
                got = int(active.get(cohort, 0))
                # One entity of slack absorbs period-boundary rounding; more
                # than that is the curve not holding.
                if abs(got - want) > 1:
                    bad += 1
            if bad:
                out.append(CoherenceFinding(
                    kind="retention_mismatch", severity="high",
                    table=spec.table, column=spec.cohort_key,
                    message=(f"{bad} cohort(s) miss the declared retention of "
                             f"{frac:.0%} at offset {offset}"),
                    rows_affected=bad,
                ))

    # ---- missingness -----------------------------------------------------
    for spec in (getattr(schema, "missingness", None) or []):
        df = tables.get(spec.table)
        if df is None or df.empty or spec.column not in df.columns:
            continue
        if spec.when_column and spec.when_column in df.columns:
            col = df[spec.when_column]
            wv, op = spec.when_value, spec.when_op
            if op == "==":
                match = col == wv
            elif op == "!=":
                match = col != wv
            elif op == "in":
                match = col.isin(wv if isinstance(wv, (list, tuple, set)) else [wv])
            elif op == "not_in":
                match = ~col.isin(wv if isinstance(wv, (list, tuple, set)) else [wv])
            else:
                continue
            match = match.fillna(False)
        else:
            match = pd.Series(True, index=df.index)
        for label, mask, rate in (("matching", match, spec.rate),
                                  ("non-matching", ~match, spec.else_rate)):
            n = int(mask.sum())
            if n == 0:
                continue
            want = exact_count(n, float(rate))
            got = int(df.loc[mask, spec.column].isna().sum())
            if abs(got - want) > 1:
                out.append(CoherenceFinding(
                    kind="missingness_mismatch", severity="medium",
                    table=spec.table, column=spec.column,
                    message=(f"{got} of {n} {label} rows are null, but "
                             f"{rate:.0%} was declared ({want} rows)"),
                    rows_affected=abs(got - want),
                ))

    # ---- late arrival ----------------------------------------------------
    for spec in (getattr(schema, "late_arrivals", None) or []):
        df = tables.get(spec.table)
        if df is None or df.empty:
            continue
        if not {spec.event_time, spec.ingest_time}.issubset(df.columns):
            continue
        ev = pd.to_datetime(df[spec.event_time], errors="coerce")
        ing = pd.to_datetime(df[spec.ingest_time], errors="coerce")
        ok = ev.notna() & ing.notna()
        if not ok.any():
            continue
        # Ingest before the event is impossible, whatever the fraction says.
        impossible = int((ing[ok] < ev[ok]).sum())
        if impossible:
            out.append(CoherenceFinding(
                kind="ingest_precedes_event", severity="high",
                table=spec.table, column=spec.ingest_time,
                message=(f"{impossible} rows were recorded before they "
                         f"happened"),
                rows_affected=impossible,
            ))
        delay_days = (ing[ok] - ev[ok]).dt.total_seconds() / 86400.0
        over = int((delay_days > float(spec.max_delay_days) + 1e-9).sum())
        if over:
            out.append(CoherenceFinding(
                kind="late_arrival_exceeds_bound", severity="medium",
                table=spec.table, column=spec.ingest_time,
                message=(f"{over} rows arrive later than the declared "
                         f"{spec.max_delay_days}-day bound"),
                rows_affected=over,
            ))
        n = int(ok.sum())
        want = exact_count(n, float(spec.late_fraction))
        got = int((delay_days >= 1.0).sum())
        if abs(got - want) > 1:
            out.append(CoherenceFinding(
                kind="late_arrival_mismatch", severity="medium",
                table=spec.table, column=spec.ingest_time,
                message=(f"{got} of {n} rows arrive a day or more late, but "
                         f"{spec.late_fraction:.0%} was declared ({want} rows)"),
                rows_affected=abs(got - want),
            ))
    return out


def _detect_cross_table_bound_violation(tables, schema) -> List[CoherenceFinding]:
    """Declared lte_parent / sum_lte_parent bounds must hold under a JOIN."""
    out: List[CoherenceFinding] = []
    try:
        from misata.crosstable import collect_cross_table_constraints, _find_fk
    except Exception:
        return out
    for child_name, c in collect_cross_table_constraints(schema):
        child = tables.get(child_name)
        parent = tables.get(getattr(c, "parent_table", None))
        if child is None or parent is None:
            continue
        col, pcol = getattr(c, "column", None), getattr(c, "parent_column", None)
        link = _find_fk(schema, child_name, c.parent_table)
        if (link is None or col not in child.columns or pcol not in parent.columns):
            continue
        child_key, parent_key = link
        if child_key not in child.columns or parent_key not in parent.columns:
            continue
        parent_vals = (parent.drop_duplicates(subset=[parent_key])
                       .set_index(parent_key)[pcol])
        mapped = child[child_key].map(parent_vals)
        if c.type == "lte_parent":
            bad = int(((child[col] > mapped + 0.01) & mapped.notna()).sum())
        else:
            sums = child.groupby(child_key)[col].transform("sum")
            bad_mask = (sums > mapped + 0.01) & mapped.notna()
            bad = int(child.loc[bad_mask, child_key].nunique())
        if bad:
            out.append(CoherenceFinding(
                kind="cross_table_bound", severity="high",
                table=child_name, column=col,
                message=(f"{bad} {'rows' if c.type == 'lte_parent' else 'parents'} "
                         f"violate declared bound '{c.name}': {child_name}.{col} "
                         f"vs {c.parent_table}.{pcol}"),
                rows_affected=bad,
            ))
    return out


def _detect_temporal_eligibility_violation(tables, schema) -> List[CoherenceFinding]:
    """A declared temporal-eligibility edge must hold on the emitted rows.

    Re-derived from the tables alone, by the same JOIN a human would write:
    resolve each child row's moment, look up the referenced parent's birth, and
    count the rows where the parent had not been born yet. The generator's
    sampling logic is not consulted, which is the point.
    """
    out: List[CoherenceFinding] = []
    for rel in (getattr(schema, "relationships", None) or []):
        ptime = getattr(rel, "parent_time", None)
        ctime = getattr(rel, "child_time", None)
        if not ptime or not ctime:
            continue
        child = tables.get(rel.child_table)
        parent = tables.get(rel.parent_table)
        if child is None or parent is None or child.empty or parent.empty:
            continue
        if rel.child_key not in child.columns or rel.parent_key not in parent.columns:
            continue
        if ptime not in parent.columns:
            continue

        owner_name = getattr(rel, "child_time_table", None)
        if owner_name:
            owner = tables.get(owner_name)
            via = next((r for r in schema.relationships
                        if r.child_table == rel.child_table
                        and r.parent_table == owner_name), None)
            if owner is None or via is None or ctime not in owner.columns:
                continue
            if via.child_key not in child.columns or via.parent_key not in owner.columns:
                continue
            times = pd.Series(
                pd.to_datetime(owner[ctime], errors="coerce").values,
                index=owner[via.parent_key].values)
            times = times[~times.index.duplicated(keep="first")]
            child_when = pd.to_datetime(child[via.child_key].map(times), errors="coerce")
        else:
            if ctime not in child.columns:
                continue
            child_when = pd.to_datetime(child[ctime], errors="coerce")

        births = pd.Series(
            pd.to_datetime(parent[ptime], errors="coerce").values,
            index=parent[rel.parent_key].values)
        births = births[~births.index.duplicated(keep="first")]
        parent_when = pd.to_datetime(child[rel.child_key].map(births), errors="coerce")

        bad = int((child_when < parent_when).sum())
        if bad:
            out.append(CoherenceFinding(
                kind="temporal_eligibility", severity="high",
                table=rel.child_table, column=rel.child_key,
                message=(f"{bad} row(s) reference a {rel.parent_table} whose "
                         f"{ptime} is later than the row's own {ctime}: the "
                         f"parent did not exist yet"),
                rows_affected=bad,
            ))
    return out


def _detect_time_grid_violation(tables, schema) -> List[CoherenceFinding]:
    """Every value of a declared TimeGrid column must sit on the grid."""
    out: List[CoherenceFinding] = []
    for spec in (getattr(schema, "time_grids", None) or []):
        df = tables.get(spec.table)
        if df is None or df.empty or spec.column not in df.columns:
            continue
        col = pd.to_datetime(df[spec.column], errors="coerce").dropna()
        if col.empty:
            continue
        off_grid = int((col.dt.minute % int(spec.minute_grid) != 0).sum())
        if spec.seconds == "zero":
            off_grid += int(((col.dt.second != 0) | (col.dt.microsecond != 0)).sum())
        if off_grid:
            out.append(CoherenceFinding(
                kind="time_grid", severity="medium",
                table=spec.table, column=spec.column,
                message=(f"{off_grid} value(s) do not sit on the declared "
                         f"{spec.minute_grid}-minute grid"),
                rows_affected=off_grid,
            ))
        if spec.hours:
            lo, hi = spec.hours
            outside = int(((col.dt.hour < lo) | (col.dt.hour >= hi)).sum())
            if outside:
                out.append(CoherenceFinding(
                    kind="time_grid", severity="medium",
                    table=spec.table, column=spec.column,
                    message=(f"{outside} value(s) fall outside the declared "
                             f"{lo:02d}:00-{hi:02d}:00 window"),
                    rows_affected=outside,
                ))
    return out


def _detect_duplicate_count_mismatch(tables, schema) -> List[CoherenceFinding]:
    """The number of duplicate rows must be exactly what was declared."""
    out: List[CoherenceFinding] = []
    for spec in (getattr(schema, "duplicates", None) or []):
        df = tables.get(spec.table)
        if df is None or df.empty:
            continue
        keys = [k for k in (spec.keys or []) if k in df.columns]
        subset = [c for c in (spec.subset
                              or [c for c in df.columns if c not in keys])
                  if c in df.columns]
        if not subset:
            continue
        from misata.dynamics import exact_count
        want = (int(spec.count) if spec.count is not None
                else exact_count(len(df), spec.fraction))
        got = len(df) - len(df[subset].drop_duplicates())
        if got != want:
            out.append(CoherenceFinding(
                kind="duplicate_count", severity="high",
                table=spec.table, column=None,
                message=(f"declared {want} duplicate row(s) on {subset}, "
                         f"found {got}"),
                rows_affected=abs(got - want),
            ))
        # Overwriting must never have collided two surrogate keys.
        for k in keys:
            dup_keys = int(df[k].duplicated().sum())
            if dup_keys:
                out.append(CoherenceFinding(
                    kind="duplicate_count", severity="high",
                    table=spec.table, column=k,
                    message=(f"{dup_keys} row(s) share a key that Duplicates "
                             f"declared must stay distinct"),
                    rows_affected=dup_keys,
                ))
    return out


def _detect_partition_leak(tables, schema) -> List[CoherenceFinding]:
    """A declared partitioned key must not cross its partition.

    Re-derived by the JOIN a reviewer would write, not by asking the sampler
    what it did. This is the single most valuable check in the module for
    multi-tenant data: a leak here is a row of one customer's data attributed to
    another, and it is invisible on single-tenant test fixtures.
    """
    out: List[CoherenceFinding] = []
    for rel in (getattr(schema, "relationships", None) or []):
        cols = list(getattr(rel, "partition_by", None) or [])
        if not cols:
            continue
        child = tables.get(rel.child_table)
        parent = tables.get(rel.parent_table)
        if child is None or parent is None or child.empty or parent.empty:
            continue
        if rel.child_key not in child.columns or rel.parent_key not in parent.columns:
            continue
        if any(c not in child.columns or c not in parent.columns for c in cols):
            continue
        pmap = parent.drop_duplicates(subset=[rel.parent_key]).set_index(rel.parent_key)
        bad = None
        for c in cols:
            mapped = child[rel.child_key].map(pmap[c])
            mism = (child[c] != mapped) & mapped.notna() & child[rel.child_key].notna()
            bad = mism if bad is None else (bad | mism)
        n = int(bad.sum()) if bad is not None else 0
        if n:
            out.append(CoherenceFinding(
                kind="partition_leak", severity="high",
                table=rel.child_table, column=rel.child_key,
                message=(f"{n} row(s) reference a {rel.parent_table} in a "
                         f"different {', '.join(cols)}: the key crosses its "
                         f"declared partition"),
                rows_affected=n,
            ))
    return out


def _detect_hierarchy_violation(tables, schema) -> List[CoherenceFinding]:
    """A self-referential key must describe a forest: no cycles, and roots exist."""
    out: List[CoherenceFinding] = []
    for rel in (getattr(schema, "relationships", None) or []):
        if rel.parent_table != rel.child_table:
            continue
        df = tables.get(rel.child_table)
        if df is None or df.empty:
            continue
        if rel.child_key not in df.columns or rel.parent_key not in df.columns:
            continue
        parent_of = dict(zip(df[rel.parent_key], df[rel.child_key]))
        cyclic = 0
        for start in parent_of:
            seen = {start}
            node = parent_of.get(start)
            while node is not None and not (isinstance(node, float) and node != node):
                if node in seen:
                    cyclic += 1
                    break
                seen.add(node)
                node = parent_of.get(node)
        if cyclic:
            out.append(CoherenceFinding(
                kind="hierarchy_cycle", severity="high",
                table=rel.child_table, column=rel.child_key,
                message=(f"{cyclic} row(s) sit on a cycle in "
                         f"{rel.child_table}.{rel.child_key}: the hierarchy is "
                         f"not a forest"),
                rows_affected=cyclic,
            ))
        roots = int(df[rel.child_key].isna().sum())
        if roots == 0 and len(df) > 1:
            out.append(CoherenceFinding(
                kind="hierarchy_cycle", severity="medium",
                table=rel.child_table, column=rel.child_key,
                message=(f"no row has a null {rel.child_key}, so the hierarchy "
                         f"has no root; declare a null_rate on it"),
                rows_affected=len(df),
            ))
    return out


def _detect_event_log_mismatch(tables, schema) -> List[CoherenceFinding]:
    """A declared event log must say what its entity's state says."""
    out: List[CoherenceFinding] = []
    for spec in (getattr(schema, "event_logs", None) or []):
        events = tables.get(spec.table)
        entities = tables.get(spec.entity_table)
        if events is None or entities is None or events.empty or entities.empty:
            continue
        lc = next((l for l in (getattr(schema, "lifecycles", None) or [])
                   if l.table == spec.entity_table), None)
        if lc is None or lc.state_column not in entities.columns:
            continue
        pk = next((r.parent_key for r in (schema.relationships or [])
                   if r.child_table == spec.table
                   and r.child_key == spec.entity_key
                   and r.parent_table == spec.entity_table), None)
        if pk is None or pk not in entities.columns:
            continue
        if (spec.entity_key not in events.columns
                or spec.event_type_column not in events.columns):
            continue

        ent = entities.drop_duplicates(subset=[pk]).set_index(pk)
        state_of = ent[lc.state_column]
        by_entity = events.groupby(spec.entity_key)[spec.event_type_column].agg(set)

        missing = extra = 0
        for key, st in state_of.items():
            path = lc.path_to(st) or [st]
            required = {spec.state_events[s] for s in path
                        if s in spec.state_events}
            allowed = required | set(spec.filler_events or [])
            have = by_entity.get(key, set())
            if required - have:
                missing += 1
            if have - allowed:
                extra += 1
        if missing:
            out.append(CoherenceFinding(
                kind="event_log", severity="high",
                table=spec.table, column=spec.event_type_column,
                message=(f"{missing} {spec.entity_table} row(s) are missing an "
                         f"event their own state implies"),
                rows_affected=missing,
            ))
        if extra:
            out.append(CoherenceFinding(
                kind="event_log", severity="high",
                table=spec.table, column=spec.event_type_column,
                message=(f"{extra} {spec.entity_table} row(s) carry an event "
                         f"for a state they never reached"),
                rows_affected=extra,
            ))
    return out


def _detect_outlier_count_mismatch(tables, schema) -> List[CoherenceFinding]:
    """Exactly the declared number of rows must sit beyond the declared distance."""
    out: List[CoherenceFinding] = []
    from misata.dynamics import exact_count, robust_scale
    for spec in (getattr(schema, "outliers", None) or []):
        df = tables.get(spec.table)
        if df is None or df.empty or spec.column not in df.columns:
            continue
        col = pd.to_numeric(df[spec.column], errors="coerce")
        if col.notna().sum() < 4:
            continue
        med, sigma = robust_scale(col.to_numpy())
        z = (col.to_numpy(dtype=float) - med) / sigma
        got = int(np.sum(np.abs(z) >= spec.sigma))
        want = (int(spec.count) if spec.count is not None
                else exact_count(len(df), spec.fraction))
        if got != want:
            out.append(CoherenceFinding(
                kind="outlier_count", severity="high",
                table=spec.table, column=spec.column,
                message=(f"declared {want} value(s) beyond {spec.sigma:g} robust "
                         f"sigma, found {got}"),
                rows_affected=abs(got - want),
            ))
    return out


def _detect_typo_count_mismatch(tables, schema) -> List[CoherenceFinding]:
    """Exactly the declared number of values must fall outside the vocabulary."""
    out: List[CoherenceFinding] = []
    from misata.dynamics import exact_count
    for spec in (getattr(schema, "typos", None) or []):
        df = tables.get(spec.table)
        if df is None or df.empty or spec.column not in df.columns:
            continue
        from misata.dynamics import _typo_clean_mask, _typo_vocabulary
        choices, pattern = _typo_vocabulary(schema, spec.table, spec.column)
        if choices is None and pattern is None:
            continue
        as_str = df[spec.column].astype("string")
        clean = int(_typo_clean_mask(as_str, choices, pattern).sum())
        got = int(len(df) - clean - int(as_str.isna().sum()))
        want = (int(spec.count) if spec.count is not None
                else exact_count(len(df), spec.fraction))
        if got != want:
            out.append(CoherenceFinding(
                kind="typo_count", severity="high",
                table=spec.table, column=spec.column,
                message=(f"declared {want} value(s) outside the column's "
                         f"{'choices' if choices is not None else 'pattern'}, "
                         f"found {got}"),
                rows_affected=abs(got - want),
            ))
    return out


def _detect_bitemporal_violation(tables, schema) -> List[CoherenceFinding]:
    """Both time axes must tile, and exactly one version may be current."""
    out: List[CoherenceFinding] = []
    for spec in (getattr(schema, "bitemporal", None) or []):
        df = tables.get(spec.table)
        if df is None or df.empty:
            continue
        cols = [*spec.entity_columns, spec.valid_from, spec.valid_to,
                spec.recorded_at, spec.superseded_at]
        if any(c not in df.columns for c in cols):
            continue
        rec = pd.to_datetime(df[spec.recorded_at], errors="coerce")
        sup = pd.to_datetime(df[spec.superseded_at], errors="coerce")
        vf = pd.to_datetime(df[spec.valid_from], errors="coerce")
        vt = pd.to_datetime(df[spec.valid_to], errors="coerce")

        inverted = int(((sup.notna()) & (sup <= rec)).sum()
                       + ((vt.notna()) & (vt <= vf)).sum())
        if inverted:
            out.append(CoherenceFinding(
                kind="bitemporal", severity="high",
                table=spec.table, column=spec.superseded_at,
                message=(f"{inverted} row(s) close a time interval at or before "
                         f"it opens"),
                rows_affected=inverted,
            ))

        grouped = df.groupby(spec.entity_columns, dropna=False)
        current = grouped[spec.superseded_at].apply(lambda s: int(s.isna().sum()))
        bad = int((current != 1).sum())
        if bad:
            out.append(CoherenceFinding(
                kind="bitemporal", severity="high",
                table=spec.table, column=spec.superseded_at,
                message=(f"{bad} entity(ies) do not have exactly one current "
                         f"version; an as-of query cannot return one row"),
                rows_affected=bad,
            ))

        # System time must hand over without a gap: every supersede instant is
        # some sibling's recorded_at.
        pairs = set(zip(*(df[c] for c in spec.entity_columns), rec)) \
            if len(spec.entity_columns) > 1 else set(zip(df[spec.entity_columns[0]], rec))
        if len(spec.entity_columns) == 1:
            handover = [(e, t) for e, t in zip(df[spec.entity_columns[0]], sup)
                        if pd.notna(t)]
        else:
            handover = [(tuple(r), t) for r, t in
                        zip(df[spec.entity_columns].itertuples(index=False), sup)
                        if pd.notna(t)]
            pairs = {(tuple(r), t) for r, t in
                     zip(df[spec.entity_columns].itertuples(index=False), rec)}
        orphaned = sum(1 for k in handover if k not in pairs)
        if orphaned:
            out.append(CoherenceFinding(
                kind="bitemporal", severity="high",
                table=spec.table, column=spec.superseded_at,
                message=(f"{orphaned} version(s) are superseded at an instant no "
                         f"successor was recorded at: system time has a gap"),
                rows_affected=orphaned,
            ))
    return out


def _detect_graph_violation(tables, schema) -> List[CoherenceFinding]:
    """A declared DAG must be acyclic; a declared closure must equal its edges."""
    out: List[CoherenceFinding] = []
    from misata.graphs import _closure_of

    for spec in (getattr(schema, "dag_edges", None) or []):
        df = tables.get(spec.table)
        if df is None or df.empty:
            continue
        if spec.from_column not in df.columns or spec.to_column not in df.columns:
            continue
        frm = df[spec.from_column].to_numpy()
        to = df[spec.to_column].to_numpy()
        anc, des, _ = _closure_of(frm, to)
        cyclic = int(np.sum(anc == des))
        selfish = int(np.sum(frm == to))
        dupes = int(len(df) - len(df[[spec.from_column, spec.to_column]]
                                  .drop_duplicates()))
        if cyclic or selfish:
            out.append(CoherenceFinding(
                kind="dag_cycle", severity="high",
                table=spec.table, column=spec.from_column,
                message=(f"{cyclic + selfish} node(s) reach themselves: the "
                         f"edge table is not acyclic"),
                rows_affected=cyclic + selfish,
            ))
        if dupes:
            out.append(CoherenceFinding(
                kind="dag_cycle", severity="medium",
                table=spec.table, column=spec.from_column,
                message=f"{dupes} duplicate edge pair(s)",
                rows_affected=dupes,
            ))

    for spec in (getattr(schema, "closures", None) or []):
        clo = tables.get(spec.table)
        edges = tables.get(spec.edge_table)
        if clo is None or edges is None or edges.empty:
            continue
        if (spec.ancestor_column not in clo.columns
                or spec.descendant_column not in clo.columns):
            continue
        anc, des, dep = _closure_of(edges[spec.edge_from].to_numpy(),
                                    edges[spec.edge_to].to_numpy())
        truth = dict(zip(zip(anc.tolist(), des.tolist()), dep.tolist()))
        have = set(zip(clo[spec.ancestor_column].tolist(),
                       clo[spec.descendant_column].tolist()))
        missing = len(set(truth) - have)
        spurious = len(have - set(truth))
        wrong_depth = 0
        if spec.depth_column and spec.depth_column in clo.columns:
            for a, d, k in zip(clo[spec.ancestor_column], clo[spec.descendant_column],
                               clo[spec.depth_column]):
                t = truth.get((a, d))
                if t is not None and int(k) != t:
                    wrong_depth += 1
        if missing or spurious:
            out.append(CoherenceFinding(
                kind="closure_mismatch", severity="high",
                table=spec.table, column=spec.ancestor_column,
                message=(f"closure disagrees with its edges: {missing} reachable "
                         f"pair(s) absent, {spurious} unreachable pair(s) present"),
                rows_affected=missing + spurious,
            ))
        if wrong_depth:
            out.append(CoherenceFinding(
                kind="closure_mismatch", severity="high",
                table=spec.table, column=spec.depth_column,
                message=(f"{wrong_depth} row(s) carry a depth that is not the "
                         f"shortest path"),
                rows_affected=wrong_depth,
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
        scoped = df
        if spec.segment_column and spec.segment_value is not None:
            if spec.segment_column not in df.columns:
                continue
            scoped = df[df[spec.segment_column].astype(str)
                        == str(spec.segment_value)]
        amounts = pd.to_numeric(scoped[spec.amount_column], errors="coerce").fillna(0)
        periods = scoped[spec.period_column].astype(str)
        types = scoped[spec.type_column].astype(str)
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


def _detect_scd2_violations(tables, schema) -> List[CoherenceFinding]:
    """SCD2 invariants recomputed from the rows: within an entity, versions
    tile (no gaps, no overlaps, each valid_to equals the next valid_from);
    exactly one version per entity is current; only the last version is
    open-ended."""
    out: List[CoherenceFinding] = []
    for table_cfg in getattr(schema, "tables", None) or []:
        spec = getattr(table_cfg, "scd2", None)
        df = tables.get(table_cfg.name)
        if spec is None or df is None or df.empty:
            continue
        needed = {spec.entity_column, spec.valid_from, spec.valid_to}
        if not needed.issubset(df.columns):
            continue
        vf = pd.to_datetime(df[spec.valid_from], errors="coerce")
        vt = pd.to_datetime(df[spec.valid_to], errors="coerce")
        work = pd.DataFrame({
            "ent": df[spec.entity_column],
            "vf": vf, "vt": vt,
        }).sort_values(["ent", "vf"])
        bad_tiling = 0
        bad_open = 0
        tol = pd.Timedelta(seconds=1)
        for _ent, g in work.groupby("ent", sort=False):
            vfs = g["vf"].values
            vts = g["vt"].values
            # every non-last version must close exactly on the next opening
            for i in range(len(g) - 1):
                if pd.isna(vts[i]) or abs(pd.Timestamp(vts[i])
                                          - pd.Timestamp(vfs[i + 1])) > tol:
                    bad_tiling += 1
                    break
            # only the last version may be open-ended
            if pd.isna(vts[:-1]).any() if len(g) > 1 else False:
                bad_open += 1
        if bad_tiling:
            out.append(CoherenceFinding(
                kind="scd2_tiling", severity="high",
                table=table_cfg.name, column=spec.valid_to,
                message=(f"{bad_tiling} entities have version intervals that "
                         f"gap or overlap instead of tiling"),
                rows_affected=bad_tiling,
            ))
        if bad_open:
            out.append(CoherenceFinding(
                kind="scd2_open_versions", severity="high",
                table=table_cfg.name, column=spec.valid_to,
                message=(f"{bad_open} entities have an open-ended validity "
                         f"on a non-current version"),
                rows_affected=bad_open,
            ))
        if spec.current_flag and spec.current_flag in df.columns:
            flags = df[spec.current_flag].astype(bool)
            per_ent = flags.groupby(df[spec.entity_column]).sum()
            bad_current = int((per_ent != 1).sum())
            if bad_current:
                out.append(CoherenceFinding(
                    kind="scd2_current_flag", severity="high",
                    table=table_cfg.name, column=spec.current_flag,
                    message=(f"{bad_current} entities do not have exactly one "
                             f"current version"),
                    rows_affected=bad_current,
                ))
    return out


def _detect_stock_flow_mismatch(tables, schema) -> List[CoherenceFinding]:
    """Inventory ledger identities recomputed from the rows: closing equals
    opening + received - shipped on every row, each period opens where the
    previous closed, and no level is negative."""
    out: List[CoherenceFinding] = []
    for spec in getattr(schema, "stock_flows", None) or []:
        df = tables.get(spec.table)
        needed = {spec.sku_column, spec.period_column, spec.open_column,
                  spec.received_column, spec.shipped_column, spec.close_column}
        if df is None or df.empty or not needed.issubset(df.columns):
            continue
        order = {str(p): i for i, p in enumerate(spec.periods or [])}
        work = df.copy()
        work["__ord"] = work[spec.period_column].astype(str).map(order)
        work = work.dropna(subset=["__ord"]).sort_values(
            [spec.sku_column, "__ord"])
        o = pd.to_numeric(work[spec.open_column], errors="coerce")
        r = pd.to_numeric(work[spec.received_column], errors="coerce")
        s = pd.to_numeric(work[spec.shipped_column], errors="coerce")
        c = pd.to_numeric(work[spec.close_column], errors="coerce")
        bad_row = int((abs(o + r - s - c) > 0.001).sum())
        same_sku = work[spec.sku_column].eq(work[spec.sku_column].shift(-1))
        chain_break = int(((c - o.shift(-1)).abs() > 0.001)[same_sku].sum())
        negative = int(((o < 0) | (c < 0) | (r < 0) | (s < 0)).sum())
        if bad_row:
            out.append(CoherenceFinding(
                kind="stock_flow_arithmetic", severity="high",
                table=spec.table, column=spec.close_column,
                message=(f"{bad_row} rows fail closing = opening + received "
                         f"- shipped"),
                rows_affected=bad_row))
        if chain_break:
            out.append(CoherenceFinding(
                kind="stock_flow_chain", severity="high",
                table=spec.table, column=spec.open_column,
                message=(f"{chain_break} periods do not open where the "
                         f"previous period closed"),
                rows_affected=chain_break))
        if negative:
            out.append(CoherenceFinding(
                kind="stock_flow_negative", severity="high",
                table=spec.table, column=spec.open_column,
                message=f"{negative} rows carry a negative stock quantity",
                rows_affected=negative))
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
        report.findings.extend(_detect_lifecycle_violation(tables, schema))
        report.findings.extend(_detect_dynamics_violation(tables, schema))
        report.findings.extend(_detect_when_then_violation(tables, schema))
        report.findings.extend(_detect_cross_table_bound_violation(tables, schema))
        report.findings.extend(_detect_temporal_eligibility_violation(tables, schema))
        report.findings.extend(_detect_time_grid_violation(tables, schema))
        report.findings.extend(_detect_duplicate_count_mismatch(tables, schema))
        report.findings.extend(_detect_partition_leak(tables, schema))
        report.findings.extend(_detect_hierarchy_violation(tables, schema))
        report.findings.extend(_detect_event_log_mismatch(tables, schema))
        report.findings.extend(_detect_outlier_count_mismatch(tables, schema))
        report.findings.extend(_detect_typo_count_mismatch(tables, schema))
        report.findings.extend(_detect_bitemporal_violation(tables, schema))
        report.findings.extend(_detect_graph_violation(tables, schema))
        report.findings.extend(_detect_group_share_mismatch(tables, schema))
        report.findings.extend(_detect_waterfall_mismatch(tables, schema))
        report.findings.extend(_detect_scd2_violations(tables, schema))
        report.findings.extend(_detect_stock_flow_mismatch(tables, schema))
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
