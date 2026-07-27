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
    cells: List[Tuple[Any, int]] = []
    for cohort_period, grp in c.groupby("_p", sort=True):
        members = grp[spec.cohort_key].tolist()
        # Stable order, shuffled once per cohort so membership is not tied to
        # insertion order, then reused across offsets to give nested retention.
        order = rng.permutation(len(members))
        members = [members[i] for i in order]
        size = len(members)
        for offset in sorted(spec.curve):
            keep = exact_count(size, spec.curve[offset])
            target_period = int(cohort_period) + int(offset)
            for entity in members[:keep]:
                cells.append((entity, target_period))

    if not cells:
        return tables
    if len(cells) > len(events):
        warnings.warn(
            f"CohortRetention on '{spec.table}': the curve needs {len(cells)} "
            f"active entity-periods but the table has only {len(events)} rows. "
            f"Raise {spec.table}.row_count to at least {len(cells)}; the curve "
            f"cannot be honoured as declared."
        )
        return tables

    ev = events.copy()
    n = len(ev)
    # One row per required cell first, then spread the surplus over the cells so
    # busy entities look busy rather than every entity having exactly one event.
    assign = list(cells)
    surplus = n - len(cells)
    if surplus > 0:
        idx = rng.integers(0, len(cells), size=surplus)
        assign.extend(cells[i] for i in idx)

    order = rng.permutation(n)
    keys = np.empty(n, dtype=object)
    stamps = np.empty(n, dtype="int64")
    for slot, row in enumerate(order):
        entity, period = assign[slot]
        keys[row] = entity
        start, length = _period_start_ns(period, spec.unit)
        stamps[row] = start + int(rng.integers(0, max(length, 1)))

    ev[spec.cohort_key] = keys
    ev[spec.event_time] = pd.to_datetime(stamps)
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

    existing = len(df) - len(df[subset].drop_duplicates())
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

    counts = df.groupby(subset, dropna=False, sort=False)[subset[0]].transform("size")
    unique_pos = np.flatnonzero((counts == 1).to_numpy())
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
    for spec in (getattr(config, "late_arrivals", None) or []):
        out.add(spec.table)
    return out
