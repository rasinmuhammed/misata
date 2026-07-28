"""How data behaves over time and where it goes missing.

Five declarations the language could not previously express, each enforced
exactly and each re-checked independently by ``coherence_audit``:

- :class:`~misata.schema.CohortRetention` — of the entities in a cohort, exactly
  this fraction are active k periods later. The most-quoted invariant in SaaS
  and ecommerce analytics, and until now the cohort query every analyst runs
  first returned a shape nobody chose.
- :class:`~misata.schema.Missingness` — values go missing *for a reason*
  (MNAR). A flat null rate produces MCAR, the one pattern real data almost
  never has, and the difference is what breaks models in production.
- :class:`~misata.schema.LateArrival` — some events land in a later period than
  they happened. Every incremental model assumes this does not happen; every
  production system does it.

- :class:`~misata.schema.TimeGrid` — a timestamp lands on a declared grid, in
  declared hours. Misata already guessed this from column names; the guess was
  right often enough to be load-bearing and was never checkable. This is the
  declared form, and the guess stays on as a default.
- :class:`~misata.schema.Duplicates` — exactly this many rows are copies of
  another row. Deduplication is the most-written, least-tested logic in any
  pipeline, and it cannot be tested against data with no duplicates in it.

All five use largest-remainder allocation, so a declared 40% is 40% of rows
rather than 40% in expectation. That is the difference between a distribution
and a guarantee, and the guarantee is the product.
"""

from __future__ import annotations

import re
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

NS_PER_DAY = 86_400_000_000_000
NS_PER_MINUTE = 60_000_000_000


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #

def _to_ns(series: pd.Series) -> np.ndarray:
    """Datetimes as int64 nanoseconds, whatever resolution pandas handed us.

    ``Series.astype("int64")`` returns the underlying integers in the column's
    own unit, and that unit is not always nanoseconds: newer pandas builds
    hand back ``datetime64[us]`` from the same input older ones gave as
    ``datetime64[ns]``. Reading those microseconds as nanoseconds is silently
    wrong by a factor of 1000, which put a 2024 timestamp in January 1970 and
    only showed up because CI runs interpreters this machine does not.
    """
    return series.to_numpy(dtype="datetime64[ns]").astype("int64")


def _from_ns(values: np.ndarray) -> pd.Series:
    """The inverse, pinned to nanoseconds so the round trip is exact."""
    return pd.Series(np.asarray(values, dtype="int64").astype("datetime64[ns]"))


def exact_count(n: int, fraction: float) -> int:
    """Rows that must satisfy a declared fraction, rounded half-up.

    Used everywhere in this module so "40%" means a count, not a probability.
    """
    return int(np.floor(n * float(fraction) + 0.5))


def _period_index(ts: pd.Series, unit: str) -> pd.Series:
    """Integer period number, so offsets are simple arithmetic."""
    t = pd.to_datetime(ts, errors="coerce")
    if unit == "day":
        return pd.Series(_to_ns(t) // NS_PER_DAY, index=t.index).astype("Int64")
    if unit == "week":
        return pd.Series(_to_ns(t) // (7 * NS_PER_DAY), index=t.index).astype("Int64")
    return (t.dt.year.astype("Int64") * 12 + t.dt.month.astype("Int64") - 1)


def _period_start_ns(period: int, unit: str) -> Tuple[int, int]:
    """(start_ns, length_ns) for a period index produced by ``_period_index``."""
    if unit == "day":
        return period * NS_PER_DAY, NS_PER_DAY
    if unit == "week":
        return period * 7 * NS_PER_DAY, 7 * NS_PER_DAY
    year, month = divmod(int(period), 12)
    start = pd.Timestamp(year=year, month=month + 1, day=1)
    end = start + pd.offsets.MonthBegin(1)
    return start.value, end.value - start.value


def _period_bounds(periods: np.ndarray, unit: str) -> Tuple[np.ndarray, np.ndarray]:
    """(start_ns, length_ns) for a whole array of period indices at once.

    The scalar :func:`_period_start_ns` built two ``pd.Timestamp`` objects per
    call, which is fine once and ruinous per row: it made ``apply_retention``
    100x slower than every other pass in the module (147k rows/sec against
    2.4M-18M). Months are resolved by casting months-since-epoch straight to
    ``datetime64[M]``, which numpy does exactly and without pandas' deprecation
    churn around ``PeriodIndex`` ordinals.
    """
    p = np.asarray(periods, dtype="int64")
    if unit == "day":
        return p * NS_PER_DAY, np.full(p.shape, NS_PER_DAY, dtype="int64")
    if unit == "week":
        return (p * 7 * NS_PER_DAY,
                np.full(p.shape, 7 * NS_PER_DAY, dtype="int64"))
    # `_period_index` encodes months as year*12 + month - 1, i.e. months since
    # year 0; numpy counts from 1970.
    m = p - 1970 * 12
    starts = m.astype("datetime64[M]").astype("datetime64[ns]").astype("int64")
    nexts = (m + 1).astype("datetime64[M]").astype("datetime64[ns]").astype("int64")
    return starts, nexts - starts


def _condition_mask(df: pd.DataFrame, column: str, op: str, value: Any) -> pd.Series:
    col = df[column]
    if op == "==":
        m = col == value
    elif op == "!=":
        m = col != value
    elif op == "in":
        m = col.isin(value if isinstance(value, (list, tuple, set)) else [value])
    elif op == "not_in":
        m = ~col.isin(value if isinstance(value, (list, tuple, set)) else [value])
    elif op == ">":
        m = col > value
    elif op == ">=":
        m = col >= value
    elif op == "<":
        m = col < value
    else:
        m = col <= value
    return m.fillna(False)


# --------------------------------------------------------------------------- #
# cohort retention
# --------------------------------------------------------------------------- #

def apply_retention(
    tables: Dict[str, pd.DataFrame],
    spec: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Rewrite the event table's entity key and timestamp to realise the curve.

    Only those two columns are touched, because those are what a retention
    query reads. Everything else the event carries is left exactly as generated.

    The allocation is deterministic given the seed: entities are ordered within
    their cohort and the first ``n`` are the ones retained at each offset, so a
    customer active at offset 2 is also active at offset 1 whenever the curve
    is non-increasing. That nesting is what real retention looks like, and it
    falls out of using a stable order rather than an independent draw per cell.
    """
    events = tables.get(spec.table)
    cohorts = tables.get(spec.cohort_table)
    if events is None or cohorts is None or events.empty or cohorts.empty:
        return tables
    for name, df, col in ((spec.cohort_table, cohorts, spec.cohort_key),
                          (spec.cohort_table, cohorts, spec.cohort_time),
                          (spec.table, events, spec.cohort_key),
                          (spec.table, events, spec.event_time)):
        if col not in df.columns:
            warnings.warn(
                f"CohortRetention on '{spec.table}': column '{col}' missing from "
                f"'{name}'. Skipping."
            )
            return tables

    c = cohorts[[spec.cohort_key, spec.cohort_time]].dropna().copy()
    c["_p"] = _period_index(c[spec.cohort_time], spec.unit)
    c = c.dropna(subset=["_p"])
    if c.empty:
        return tables

    # (entity, period) cells that must contain at least one event.
    parts_entity: List[np.ndarray] = []
    parts_period: List[np.ndarray] = []
    offsets = sorted(spec.curve)
    for cohort_period, grp in c.groupby("_p", sort=True):
        members = grp[spec.cohort_key].to_numpy()
        # Stable order, shuffled once per cohort so membership is not tied to
        # insertion order, then reused across offsets to give nested retention.
        members = members[rng.permutation(len(members))]
        size = len(members)
        for offset in offsets:
            keep = exact_count(size, spec.curve[offset])
            if keep <= 0:
                continue
            parts_entity.append(members[:keep])
            parts_period.append(np.full(
                keep, int(cohort_period) + int(offset), dtype="int64"))

    if not parts_entity:
        return tables
    cell_entity = np.concatenate(parts_entity)
    cell_period = np.concatenate(parts_period)
    if len(cell_entity) > len(events):
        warnings.warn(
            f"CohortRetention on '{spec.table}': the curve needs "
            f"{len(cell_entity)} active entity-periods but the table has only "
            f"{len(events)} rows. Raise {spec.table}.row_count to at least "
            f"{len(cell_entity)}; the curve cannot be honoured as declared."
        )
        return tables

    ev = events.copy()
    n = len(ev)
    # One row per required cell first, then spread the surplus over the cells so
    # busy entities look busy rather than every entity having exactly one event.
    surplus = n - len(cell_entity)
    if surplus > 0:
        idx = rng.integers(0, len(cell_entity), size=surplus)
        cell_entity = np.concatenate([cell_entity, cell_entity[idx]])
        cell_period = np.concatenate([cell_period, cell_period[idx]])

    order = rng.permutation(n)
    # The key keeps the cohort table's own dtype. Building it as an object array
    # turned an int64 foreign key into object, which survives a groupby and
    # then breaks the first join someone writes against it.
    keys = np.empty(n, dtype=cell_entity.dtype)
    keys[order] = cell_entity
    periods = np.empty(n, dtype="int64")
    periods[order] = cell_period

    starts, lengths = _period_bounds(periods, spec.unit)
    within = (rng.random(n) * np.maximum(lengths, 1)).astype("int64")
    stamps = starts + np.minimum(within, np.maximum(lengths - 1, 0))

    ev[spec.cohort_key] = keys
    ev[spec.event_time] = stamps.astype("datetime64[ns]")
    tables[spec.table] = ev
    return tables


# --------------------------------------------------------------------------- #
# missingness (MNAR)
# --------------------------------------------------------------------------- #

def apply_missingness(
    tables: Dict[str, pd.DataFrame],
    spec: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Null exactly the declared fraction of matching and non-matching rows."""
    df = tables.get(spec.table)
    if df is None or df.empty or spec.column not in df.columns:
        if df is not None and spec.column not in df.columns:
            warnings.warn(
                f"Missingness on '{spec.table}': column '{spec.column}' not "
                f"found. Skipping."
            )
        return tables

    df = df.copy()
    if spec.when_column and spec.when_column in df.columns:
        match = _condition_mask(df, spec.when_column, spec.when_op, spec.when_value)
    elif spec.when_column:
        warnings.warn(
            f"Missingness on '{spec.table}.{spec.column}': condition column "
            f"'{spec.when_column}' not found; applying the rate to every row."
        )
        match = pd.Series(True, index=df.index)
    else:
        match = pd.Series(True, index=df.index)

    # An integer column cannot hold NaN, so widen before nulling rather than
    # silently coercing values.
    if pd.api.types.is_integer_dtype(df[spec.column]):
        df[spec.column] = df[spec.column].astype("float64")

    for mask, rate in ((match, spec.rate), (~match, spec.else_rate)):
        pool = df.index[mask]
        k = exact_count(len(pool), rate)
        if k <= 0 or len(pool) == 0:
            continue
        chosen = rng.choice(np.asarray(pool), size=min(k, len(pool)), replace=False)
        if pd.api.types.is_datetime64_any_dtype(df[spec.column]):
            df.loc[chosen, spec.column] = pd.NaT
        else:
            df.loc[chosen, spec.column] = np.nan

    tables[spec.table] = df
    return tables


# --------------------------------------------------------------------------- #
# late / out-of-order arrival
# --------------------------------------------------------------------------- #

def apply_late_arrival(
    tables: Dict[str, pd.DataFrame],
    spec: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Write an ingest timestamp where exactly ``late_fraction`` arrive late.

    "Late" means at least a full day after the event, which is the threshold
    that actually matters: it is the case where the row lands in a later daily
    partition than the one it belongs to, and therefore the case an incremental
    model can miss.
    """
    df = tables.get(spec.table)
    if df is None or df.empty:
        return tables
    if spec.event_time not in df.columns:
        warnings.warn(
            f"LateArrival on '{spec.table}': event column '{spec.event_time}' "
            f"not found. Skipping."
        )
        return tables
    if spec.ingest_time not in df.columns:
        warnings.warn(
            f"LateArrival on '{spec.table}': ingest column '{spec.ingest_time}' "
            f"is not declared on the table, so there is nowhere to record the "
            f"delay. Add it as a nullable datetime column."
        )
        return tables

    df = df.copy()
    event = pd.to_datetime(df[spec.event_time], errors="coerce")
    if event.isna().all():
        return tables
    base = _to_ns(event.fillna(event.min()))

    n = len(df)
    k = exact_count(n, spec.late_fraction)
    late_rows = rng.choice(n, size=min(k, n), replace=False) if k > 0 else np.array([], dtype=int)
    is_late = np.zeros(n, dtype=bool)
    is_late[late_rows] = True

    delay = np.empty(n, dtype="int64")
    # Punctual rows: minutes, never zero, so ingest is still distinguishable
    # from the event instant. Critically, the delay is also clipped so ingest
    # stays inside the event's own calendar day. "Late" has to mean "landed in
    # a later partition", because that is the case an incremental model can
    # miss; a row ingested 90 minutes after an 23:30 event is not late in any
    # sense a warehouse cares about, but a naive 24-hour rule would still count
    # the day boundary it crossed.
    on_time_cap = max(int(spec.on_time_max_minutes), 1) * NS_PER_MINUTE
    punctual = ~is_late
    if punctual.any():
        drawn = rng.integers(1, on_time_cap, size=int(punctual.sum()))
        until_midnight = (NS_PER_DAY - (base[punctual] % NS_PER_DAY)) - 1
        delay[punctual] = np.minimum(drawn, np.maximum(until_midnight, 1))
    # Late rows: at least one full day, up to the declared bound.
    if is_late.any():
        lo, hi = NS_PER_DAY, max(int(spec.max_delay_days), 1) * NS_PER_DAY
        delay[is_late] = rng.integers(lo, max(hi, lo + 1), size=int(is_late.sum()))

    df[spec.ingest_time] = pd.to_datetime(base + delay)
    tables[spec.table] = df
    return tables


# --------------------------------------------------------------------------- #
# time grids
# --------------------------------------------------------------------------- #

def apply_time_grid(
    tables: Dict[str, pd.DataFrame],
    spec: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Move each timestamp to the next slot on its declared grid.

    Forward-only, and that is the whole design. The first version folded values
    into the hour window by remainder, which is prettier and wrong: it moved
    23:50 back to 16:50 and 86 support tickets ended up opened before their
    customer had signed up. Causality is enforced earlier in the run, so a pass
    that lowers a timestamp afterwards can silently undo it, and every causal
    guarantee in Misata is a lower bound.

    Moving only forward cannot break a lower bound anywhere in the schema, by
    construction rather than by luck. What it can do is push a value past a
    same-day upper bound, and ``coherence_audit`` reports that rather than
    hiding it. A value whose next slot is past the last slot of the day moves
    to the first slot of the next day, so the date can advance by one.
    """
    df = tables.get(spec.table)
    if df is None or df.empty or spec.column not in df.columns:
        return tables
    col = pd.to_datetime(df[spec.column], errors="coerce")
    known = col.notna().values
    if not known.any():
        return tables

    grid = int(spec.minute_grid)
    lo, hi = (spec.hours if spec.hours else (0, 24))
    first = -(-(lo * 60) // grid) * grid          # first slot at or after open
    last = ((hi * 60 - 1) // grid) * grid          # last slot strictly inside
    if first > last:
        warnings.warn(
            f"TimeGrid on '{spec.table}.{spec.column}': a {grid}-minute grid "
            f"has no slot inside {lo:02d}:00-{hi:02d}:00. Use a finer grid or "
            f"a wider window; the column is left as generated.")
        return tables

    ns = _to_ns(col)
    day = np.where(known, ns // NS_PER_DAY, 0)
    # Ceil in nanoseconds, not minutes. Rounding the minute up and then zeroing
    # the seconds looks forward-only and is not: 16:30:56 became 16:30:00 and
    # four tickets slid back behind their customer's signup. The ceiling has to
    # happen at the resolution the value is actually carrying.
    within = np.where(known, ns - day * NS_PER_DAY, 0)
    grid_ns = grid * NS_PER_MINUTE
    slot = (-(-within // grid_ns) * grid_ns) // NS_PER_MINUTE
    slot = np.maximum(slot, first)
    rolled = slot > last                           # nothing left today
    slot = np.where(rolled, first, slot)
    day = day + rolled.astype("int64")

    if spec.seconds == "zero":
        sub = np.zeros(len(slot), dtype="int64")
    else:
        sub = rng.integers(0, 60, size=len(slot)) * (NS_PER_MINUTE // 60)

    out = df.copy()
    stamped = _from_ns(day * NS_PER_DAY + slot * NS_PER_MINUTE + sub)
    stamped[~known] = pd.NaT
    new_ns = _to_ns(stamped)

    # Carry the row's later timestamps along. A ticket created at 16:52 and
    # resolved at 16:58 must not come out created at 17:00 and resolved at
    # 16:58: moving one column of a row forward past another one silently
    # inverts the row. Columns that already sat at or after this one keep the
    # exact gap they had, so the row's internal shape survives the grid.
    moved = known & (new_ns > ns)
    if moved.any():
        for other in df.columns:
            if other == spec.column:
                continue
            if not pd.api.types.is_datetime64_any_dtype(df[other]):
                continue
            o = _to_ns(df[other])
            o_known = df[other].notna().to_numpy()
            follows = moved & o_known & (o >= ns) & (o < new_ns)
            if not follows.any():
                continue
            shifted = df[other].copy()
            gap = o[follows] - ns[follows]
            shifted.iloc[np.flatnonzero(follows)] = _from_ns(
                new_ns[follows] + gap).values
            out[other] = shifted

    out[spec.column] = stamped.values
    tables[spec.table] = out
    return tables


# --------------------------------------------------------------------------- #
# duplicates
# --------------------------------------------------------------------------- #

def apply_duplicates(
    tables: Dict[str, pd.DataFrame],
    spec: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Make exactly the declared number of rows duplicates of another row.

    Rows are overwritten, never appended, so the declared ``row_count`` still
    holds and ``keys`` stay unique. Only rows whose ``subset`` value is
    currently unique are eligible as donor or recipient, which is what makes
    the final excess exact rather than approximate: each copy raises
    ``len(df) - len(df[subset].drop_duplicates())`` by exactly one.
    """
    df = tables.get(spec.table)
    if df is None or df.empty:
        return tables

    keys = [k for k in (spec.keys or []) if k in df.columns]
    subset = [c for c in (spec.subset or [c for c in df.columns if c not in keys])
              if c in df.columns]
    if not subset:
        warnings.warn(
            f"Duplicates on '{spec.table}': no comparable columns left after "
            f"excluding keys {keys}. Skipping.")
        return tables

    n = int(spec.count) if spec.count is not None else exact_count(len(df), spec.fraction)
    if n <= 0:
        return tables

    # `duplicated` is one hash pass. `len(df) - len(df[subset].drop_duplicates())`
    # is the same number but materialises a deduplicated copy of every column,
    # and the groupby-transform this replaced was the slowest thing in the
    # module at scale.
    existing = int(df.duplicated(subset=subset).sum())
    if existing > n:
        warnings.warn(
            f"Duplicates on '{spec.table}': the table already contains "
            f"{existing} duplicate row(s) on {subset}, more than the {n} "
            f"declared. The subset is not distinct enough to control; add a "
            f"high-cardinality column to 'subset' or raise 'count'.")
        return tables
    need = n - existing
    if need == 0:
        return tables

    # Rows currently alone on `subset`: not a member of any duplicated group.
    in_dup_group = df.duplicated(subset=subset, keep=False).to_numpy()
    unique_pos = np.flatnonzero(~in_dup_group)
    if len(unique_pos) < 2 * need:
        warnings.warn(
            f"Duplicates on '{spec.table}': {need} more duplicate(s) declared "
            f"but only {len(unique_pos)} row(s) are currently unique on "
            f"{subset}, so at most {len(unique_pos) // 2} can be made. Lower "
            f"'count', or widen 'subset'.")
        need = len(unique_pos) // 2
        if need == 0:
            return tables

    picked = rng.permutation(unique_pos)[: 2 * need]
    donors, recipients = picked[:need], picked[need:]
    out = df.copy()
    # Column by column, in each column's own dtype. Lifting the block into a
    # single 2-D array would coerce every column to object and silently widen
    # the integer columns on the way back in.
    for col in subset:
        vals = out[col].to_numpy(copy=True)
        vals[recipients] = vals[donors]
        out[col] = vals
    tables[spec.table] = out
    return tables


# --------------------------------------------------------------------------- #
# outliers and typos: dirt with an answer key
# --------------------------------------------------------------------------- #

def robust_scale(values: np.ndarray) -> Tuple[float, float]:
    """(median, robust sigma) via MAD, scaled so it matches std for normal data.

    Used by both the generator and the audit, so they cannot disagree about what
    "six sigma out" means. Mean and standard deviation would be wrong here: the
    outliers being placed inflate the very scale they are measured against, so
    the threshold would drift as the count rose.
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return 0.0, 1.0
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med)))
    return med, (mad * 1.4826) or (float(np.std(v)) or 1.0)


def apply_outliers(
    tables: Dict[str, pd.DataFrame],
    spec: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Push exactly the declared number of rows past the declared distance."""
    df = tables.get(spec.table)
    if df is None or df.empty or spec.column not in df.columns:
        return tables
    col = pd.to_numeric(df[spec.column], errors="coerce")
    if col.notna().sum() < 4:
        warnings.warn(
            f"Outliers on '{spec.table}.{spec.column}': needs at least 4 numeric "
            f"values to have a scale at all. Skipping.")
        return tables

    n = int(spec.count) if spec.count is not None else exact_count(len(df), spec.fraction)
    if n <= 0:
        return tables

    med, sigma = robust_scale(col.to_numpy())
    already = np.flatnonzero(
        (np.abs(col.to_numpy(dtype=float) - med) / sigma >= spec.sigma))
    eligible = np.flatnonzero(col.notna().to_numpy())
    eligible = np.setdiff1d(eligible, already, assume_unique=False)
    if n < len(already):
        warnings.warn(
            f"Outliers on '{spec.table}.{spec.column}': the column already holds "
            f"{len(already)} value(s) beyond {spec.sigma:g} robust sigma, more "
            f"than the {n} declared. Raise 'count', or raise 'sigma' so the "
            f"declaration is about values you actually placed.")
        return tables
    need = n - len(already)
    if need > len(eligible):
        warnings.warn(
            f"Outliers on '{spec.table}.{spec.column}': {need} more outlier(s) "
            f"declared but only {len(eligible)} row(s) are available. Lower "
            f"'count'.")
        need = len(eligible)
    if need <= 0:
        return tables

    picked = rng.permutation(eligible)[:need]
    # Comfortably past the line, so a later rounding pass cannot pull one back
    # under it and turn an exact count into an off-by-a-few.
    dist = (spec.sigma + 1.0 + rng.random(need) * 3.0) * sigma
    if spec.direction == "high":
        sign = np.ones(need)
    elif spec.direction == "low":
        sign = -np.ones(need)
    else:
        sign = rng.choice([-1.0, 1.0], size=need)

    out = df.copy()
    # copy=True matters: to_numpy can hand back a read-only view of the block,
    # and the write then raises inside the generic handler, so the pass appears
    # to do nothing while reporting success.
    vals = pd.to_numeric(out[spec.column],
                         errors="coerce").to_numpy(dtype=float, copy=True)
    vals[picked] = med + sign * dist
    out[spec.column] = vals
    tables[spec.table] = out
    return tables


def _corrupt(text: str, rng: np.random.Generator) -> str:
    """One plausible keyboard slip: transpose, double, or drop a character."""
    if len(text) < 2:
        return text + text[-1:]
    kind = int(rng.integers(0, 3))
    i = int(rng.integers(0, len(text) - 1))
    if kind == 0:                                   # transpose
        return text[:i] + text[i + 1] + text[i] + text[i + 2:]
    if kind == 1:                                   # double a character
        return text[:i] + text[i] + text[i:]
    return text[:i] + text[i + 1:]                  # drop a character


def apply_typos(
    tables: Dict[str, pd.DataFrame],
    spec: Any,
    config: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Corrupt exactly the declared number of values away from the vocabulary."""
    df = tables.get(spec.table)
    if df is None or df.empty or spec.column not in df.columns:
        return tables

    choices, pattern = _typo_vocabulary(config, spec.table, spec.column)
    if choices is None and pattern is None:
        warnings.warn(
            f"Typos on '{spec.table}.{spec.column}': the column declares "
            f"neither 'choices' nor 'pattern', so a typo in it is "
            f"unfalsifiable and the audit could not check the count. Declare "
            f"one of them, or drop this typos entry.")
        return tables

    n = int(spec.count) if spec.count is not None else exact_count(len(df), spec.fraction)
    if n <= 0:
        return tables

    as_str = df[spec.column].astype("string")
    ok = _typo_clean_mask(as_str, choices, pattern)
    clean = np.flatnonzero(ok.to_numpy())
    dirty_now = int(len(df) - len(clean) - int(as_str.isna().sum()))
    if dirty_now > n:
        warnings.warn(
            f"Typos on '{spec.table}.{spec.column}': {dirty_now} value(s) are "
            f"already outside the declared choices, more than the {n} asked "
            f"for. Raise 'count'.")
        return tables
    need = n - dirty_now
    if need > len(clean):
        warnings.warn(
            f"Typos on '{spec.table}.{spec.column}': {need} typo(s) declared but "
            f"only {len(clean)} clean value(s) exist. Lower 'count'.")
        need = len(clean)
    if need <= 0:
        return tables

    picked = rng.permutation(clean)[:need]
    values = df[spec.column].astype(object).to_numpy().copy()
    for i in picked:
        original = str(values[i])
        for _ in range(8):                       # a slip that lands back on a
            candidate = _corrupt(original, rng)  # legal value is not a typo
            if candidate != original and not _typo_is_clean(
                    candidate, choices, pattern):
                values[i] = candidate
                break
        else:
            # Guaranteed illegal for both vocabularies: '?' is outside every
            # declared choice set, and outside any pattern that did not ask
            # for it.
            values[i] = original + "?"
    out = df.copy()
    out[spec.column] = values
    tables[spec.table] = out
    return tables


def _typo_vocabulary(config: Any, table: str, column: str):
    """(choices, compiled pattern) for a column, whichever it declares.

    A typo is only a guarantee if something can say what a legal value looks
    like. `choices` enumerates them; `pattern` describes them, and Misata's
    pattern syntax is regex-shaped already, so it doubles as the checker. A
    free-text column has neither, and a typo in it is unfalsifiable.
    """
    for c in (config.columns.get(table, []) or []):
        if c.name != column:
            continue
        p = c.distribution_params or {}
        raw = p.get("choices")
        if raw:
            return {str(x) for x in raw}, None
        pat = p.get("pattern")
        if isinstance(pat, (list, tuple)):
            pat = [str(x) for x in pat if str(x)]
            if not pat:
                return None, None
            joined = "|".join(f"(?:{x})" for x in pat)
        elif pat:
            joined = str(pat)
        else:
            return None, None
        try:
            return None, re.compile(joined)
        except re.error:
            return None, None
    return None, None


def _typo_is_clean(value: Any, choices, pattern) -> bool:
    if value is None:
        return True
    text = str(value)
    if choices is not None:
        return text in choices
    if pattern is not None:
        return pattern.fullmatch(text) is not None
    return True


def _typo_clean_mask(as_str: pd.Series, choices, pattern) -> pd.Series:
    if choices is not None:
        return as_str.isin(choices).fillna(False)
    return as_str.map(
        lambda v: pattern.fullmatch(str(v)) is not None
        if v is not None and v is not pd.NA else False).fillna(False)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def apply_dynamics(
    tables: Dict[str, pd.DataFrame],
    config: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Apply every declared retention curve, missingness rule, and late arrival.

    Order matters and is deliberate: retention rewrites entity keys and event
    timestamps, so it runs before late arrival (which reads the event
    timestamp) and before missingness (which must be the last word on which
    values are null, or a later pass would fill them back in).
    """
    for spec in (getattr(config, "retention", None) or []):
        try:
            apply_retention(tables, spec, rng)
        except Exception as e:
            warnings.warn(f"CohortRetention on '{spec.table}' failed ({e}); "
                          f"table left as generated.")
    for spec in (getattr(config, "late_arrivals", None) or []):
        try:
            apply_late_arrival(tables, spec, rng)
        except Exception as e:
            warnings.warn(f"LateArrival on '{spec.table}' failed ({e}); "
                          f"table left as generated.")
    for spec in (getattr(config, "time_grids", None) or []):
        try:
            apply_time_grid(tables, spec, rng)
        except Exception as e:
            warnings.warn(f"TimeGrid on '{spec.table}.{spec.column}' failed "
                          f"({e}); column left as generated.")
    for spec in (getattr(config, "missingness", None) or []):
        try:
            apply_missingness(tables, spec, rng)
        except Exception as e:
            warnings.warn(f"Missingness on '{spec.table}.{spec.column}' failed "
                          f"({e}); table left as generated.")
    for spec in (getattr(config, "outliers", None) or []):
        try:
            apply_outliers(tables, spec, rng)
        except Exception as e:
            warnings.warn(f"Outliers on '{spec.table}.{spec.column}' failed "
                          f"({e}); column left as generated.")
    for spec in (getattr(config, "typos", None) or []):
        try:
            apply_typos(tables, spec, config, rng)
        except Exception as e:
            warnings.warn(f"Typos on '{spec.table}.{spec.column}' failed "
                          f"({e}); column left as generated.")

    # Duplicates are last on purpose. A copy made before missingness ran would
    # have its nulls redrawn independently and stop being a copy.
    for spec in (getattr(config, "duplicates", None) or []):
        try:
            apply_duplicates(tables, spec, rng)
        except Exception as e:
            warnings.warn(f"Duplicates on '{spec.table}' failed ({e}); "
                          f"table left as generated.")
    return tables


def dynamics_tables(config: Any) -> set:
    """Tables that must be buffered because a dynamics pass rewrites them."""
    out: set = set()
    for spec in (getattr(config, "retention", None) or []):
        out.add(spec.table)
        out.add(spec.cohort_table)
    for spec in (getattr(config, "missingness", None) or []):
        out.add(spec.table)
    for spec in (getattr(config, "time_grids", None) or []):
        out.add(spec.table)
    for spec in (getattr(config, "duplicates", None) or []):
        out.add(spec.table)
    for spec in (getattr(config, "outliers", None) or []):
        out.add(spec.table)
    for spec in (getattr(config, "typos", None) or []):
        out.add(spec.table)
    for spec in (getattr(config, "late_arrivals", None) or []):
        out.add(spec.table)
    return out
