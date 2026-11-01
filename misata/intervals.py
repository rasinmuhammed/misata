"""Intervals: where each thing is, and when.

Three guarantees about rows that occupy a span of time ``[start, end)``:

- ``no_overlap``: an entity's own intervals never overlap. A resident is in
  one place at a time. An overlap is resolved by moving the later interval
  forward to where the earlier one ends, keeping its duration.
- ``capacity``: a shared resource never holds more concurrent intervals than
  its capacity. Overflow is resolved by moving the row to another resource
  the relationship allows, keeping its times.
- containment: a child's moment lies inside its parent's span. A temporal
  relationship with ``parent_time`` keeps ``child_time >= parent_time``;
  adding ``parent_end`` also keeps ``child_time <= parent_end``.

They run after time grids, because a grid moves timestamps forward and can
push a parent's start past a child that was placed after it. Containment
re-establishes every declared temporal relationship on the final clocks, so a
grid can no longer silently break one.

Each resolution respects the declared aggregates on the timestamp it moves: a
value is never moved out of its outcome-curve or rate-curve period. When a
guarantee and a declared aggregate cannot both hold, the aggregate wins, a
``ConformanceWarning`` says how many rows yielded, and ``coherence_audit``
reports them.
"""

from __future__ import annotations

import heapq
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from misata.dynamics import NS_PER_DAY, NS_PER_MINUTE, _from_ns, _to_ns
from misata.exceptions import ConformanceWarning, warn

_NAT = np.iinfo(np.int64).min


def _ns(df: pd.DataFrame, column: str) -> Tuple[np.ndarray, np.ndarray]:
    """Nanoseconds since the epoch, and which values are known."""
    values = pd.to_datetime(df[column], errors="coerce")
    known = values.notna().to_numpy()
    return np.where(known, _to_ns(values), 0), known


def _write_ns(df: pd.DataFrame, column: str, ns: np.ndarray, rows: np.ndarray,
              column_type: Optional[str]) -> None:
    """Write nanosecond values back into ``rows`` of ``column``, keeping a
    ``date`` column a calendar day."""
    stamped = _from_ns(ns[rows])
    if column_type == "date":
        stamped = stamped.dt.floor("D")
    updated = pd.to_datetime(df[column], errors="coerce").copy()
    updated.iloc[rows] = stamped.to_numpy()
    df[column] = updated


def _column_types(config: Any, table: str) -> Dict[str, str]:
    return {c.name: c.type for c in (getattr(config, "columns", None) or {}).get(table, [])}


def _period_keys(config: Any, table: str, column: str,
                 times: pd.Series) -> Optional[np.ndarray]:
    """The declared aggregate periods each timestamp falls in, one column each.

    Covers every exact outcome curve and every rate curve that buckets the
    table by ``column``: a curve contributes its bucket index, a rate curve the
    ordinal of its calendar period. Keys are comparable across calls, so a
    moved value can be checked against where it started. Returns None when no
    declared aggregate reads the column.
    """
    times = pd.to_datetime(pd.Series(times), errors="coerce").reset_index(drop=True)
    from misata.engines import FactEngine

    engine = FactEngine()
    parts: List[np.ndarray] = []
    for curve in getattr(config, "outcome_curves", None) or []:
        if (curve.table != table or curve.time_column != column
                or not engine.curve_has_exact_targets(curve)):
            continue
        # Generation already resolved this curve to place its rows, so it resolves here.
        resolved = engine._resolve_curve(curve, config.get_columns(table))
        bucket = np.full(len(times), -1, dtype=np.int64)
        for i, b in enumerate(resolved.buckets):
            bucket[((times >= b.start) & (times < b.end)).to_numpy()] = i
        parts.append(bucket)
    freq = {"day": "D", "week": "W", "month": "M", "quarter": "Q"}
    for rate in getattr(config, "rate_curves", None) or []:
        if rate.table == table and rate.time_column == column:
            parts.append(pd.PeriodIndex(times, freq=freq[rate.time_unit]).asi8)
    return np.column_stack(parts) if parts else None


def _same_period(config: Any, table: str, column: str,
                 before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Whether each moved value stays in every declared period it started in."""
    old = _period_keys(config, table, column, _from_ns(before))
    if old is None:
        return np.ones(len(before), dtype=bool)
    new = _period_keys(config, table, column, _from_ns(after))
    return np.asarray((old == new).all(axis=1), dtype=bool)


def _carry_later(df: pd.DataFrame, moved_column: str, rows: np.ndarray,
                 old: np.ndarray, new: np.ndarray, skip: Set[str]) -> None:
    """Move a row's other timestamps that a forward move would reach.

    A timestamp at or after the moved one, and at or before its new value,
    keeps its gap to it, so the row's internal order survives (the same rule
    ``time_grids`` follows).
    """
    forward = new > old
    if not forward.any():
        return
    rows, old, new = rows[forward], old[forward], new[forward]
    for other in df.columns:
        if other == moved_column or other in skip:
            continue
        if not pd.api.types.is_datetime64_any_dtype(df[other]):
            continue
        o, known = _ns(df.iloc[rows], other)
        follows = known & (o >= old) & (o <= new)
        if not follows.any():
            continue
        shifted = o.copy()
        shifted[follows] = new[follows] + (o[follows] - old[follows])
        updated = df[other].copy()
        updated.iloc[rows[follows]] = _from_ns(shifted[follows]).to_numpy()
        df[other] = updated


# --------------------------------------------------------------------------- #
# no_overlap
# --------------------------------------------------------------------------- #

def apply_no_overlap(tables: Dict[str, pd.DataFrame], spec: Any, config: Any) -> None:
    """Lay each entity's intervals end to end where they overlap."""
    df = tables.get(spec.table)
    needed = {spec.key, spec.start, spec.end}
    if df is None or df.empty or not needed.issubset(df.columns):
        return
    start, s_known = _ns(df, spec.start)
    end, e_known = _ns(df, spec.end)
    usable = s_known & e_known & df[spec.key].notna().to_numpy()
    if not usable.any():
        return
    keys = pd.factorize(df[spec.key], use_na_sentinel=True)[0]
    duration = np.maximum(end - start, 0)
    idx = np.flatnonzero(usable)
    order = idx[np.lexsort((idx, end[idx], start[idx], keys[idx]))]

    new_start = start.copy()
    prev_key, prev_end = -1, _NAT
    for i in order:
        if keys[i] != prev_key:
            prev_key, prev_end = keys[i], _NAT
        s = max(start[i], prev_end)
        new_start[i] = s
        prev_end = s + duration[i]

    moved = np.flatnonzero(usable & (new_start != start))
    if not moved.size:
        return
    keep = _same_period(config, spec.table, spec.start, start[moved], new_start[moved])
    if not keep.all():
        warn(
            f"no_overlap on {spec.table}.{spec.key}: {int((~keep).sum())} interval(s) "
            f"would leave the declared period of {spec.start}; the declared aggregate "
            f"takes precedence and they keep their time. The story audit will "
            f"report them.",
            ConformanceWarning,)
        moved = moved[keep]
    if not moved.size:
        return
    types = _column_types(config, spec.table)
    new_end = new_start + duration
    _carry_later(df, spec.start, moved, start[moved], new_start[moved], {spec.end})
    _write_ns(df, spec.start, new_start, moved, types.get(spec.start))
    _write_ns(df, spec.end, new_end, moved, types.get(spec.end))
    tables[spec.table] = df


# --------------------------------------------------------------------------- #
# capacity
# --------------------------------------------------------------------------- #

def _relationship_for(config: Any, table: str, column: str) -> Optional[Any]:
    for rel in getattr(config, "relationships", None) or []:
        if rel.child_table == table and rel.child_key == column:
            return rel
    return None


def _filter_mask(parent: pd.DataFrame, filters: Optional[Dict[str, Any]]) -> np.ndarray:
    """Parents a relationship's ``filters`` allow, read the way generation reads them."""
    mask = np.ones(len(parent), dtype=bool)
    for col, want in (filters or {}).items():
        if col not in parent.columns:
            continue
        values = parent[col]
        mask &= (values.isin(want) if isinstance(want, (list, tuple, set))
                 else values == want).to_numpy()
    return mask


def apply_capacity(tables: Dict[str, pd.DataFrame], spec: Any, config: Any,
                   rng: np.random.Generator) -> None:
    """Move rows off full resources onto ones the relationship allows."""
    df = tables.get(spec.table)
    rel = _relationship_for(config, spec.table, spec.resource)
    needed = {spec.resource, spec.start, spec.end}
    if df is None or df.empty or rel is None or not needed.issubset(df.columns):
        return
    parent = tables.get(rel.parent_table)
    if parent is None or rel.parent_key not in parent.columns:
        return
    if spec.capacity_column and spec.capacity_column not in parent.columns:
        return

    parent = parent.drop_duplicates(subset=[rel.parent_key]).reset_index(drop=True)
    pkeys = parent[rel.parent_key].to_numpy()
    if spec.capacity_column:
        caps = pd.to_numeric(parent[spec.capacity_column], errors="coerce")
        cap = np.where(caps.isna(), np.iinfo(np.int64).max,
                       caps.fillna(0).clip(lower=0).astype(np.int64)).astype(np.int64)
    else:
        cap = np.full(len(parent), int(spec.capacity), dtype=np.int64)

    # Which resources each row may move to: those passing the relationship's
    # filters, agreeing on its partition columns, and (with parent_time)
    # already existing when the interval starts.
    allowed = _filter_mask(parent, rel.filters)
    part_cols = [c for c in (rel.partition_by or []) if c in parent.columns and c in df.columns]
    if part_cols:
        parent_class = pd.MultiIndex.from_frame(parent[part_cols].astype(object)).factorize()[0] \
            if len(part_cols) > 1 else pd.factorize(parent[part_cols[0]])[0]
        class_index = {tuple(parent[part_cols].iloc[i].astype(object)): int(parent_class[i])
                       for i in range(len(parent))}
        row_class = np.array([class_index.get(tuple(r), -1)
                              for r in df[part_cols].astype(object).itertuples(index=False)],
                             dtype=np.int64)
    else:
        parent_class = np.zeros(len(parent), dtype=np.int64)
        row_class = np.zeros(len(df), dtype=np.int64)
    born = None
    if rel.parent_time and rel.parent_time in parent.columns:
        born, born_known = _ns(parent, rel.parent_time)
        born = np.where(born_known, born, _NAT)

    position = {k: i for i, k in enumerate(pkeys)}
    resource = np.array([position.get(k, -1) for k in df[spec.resource].to_numpy()], dtype=np.int64)
    start, s_known = _ns(df, spec.start)
    end, e_known = _ns(df, spec.end)
    usable = s_known & e_known & (resource >= 0) & (end > start)
    idx = np.flatnonzero(usable)
    order = idx[np.lexsort((idx, start[idx]))]

    occupancy = np.zeros(len(parent), dtype=np.int64)
    active: List[Tuple[int, int]] = []
    assigned = resource.copy()
    unplaced = 0
    for i in order:
        s = start[i]
        while active and active[0][0] <= s:
            occupancy[heapq.heappop(active)[1]] -= 1
        r = assigned[i]
        if occupancy[r] >= cap[r]:
            room = (occupancy < cap) & allowed & (parent_class == row_class[i])
            if born is not None:
                room &= born <= s
            free = np.flatnonzero(room)
            if free.size:
                r = int(free[rng.integers(free.size)])
                assigned[i] = r
            else:
                unplaced += 1
        occupancy[r] += 1
        heapq.heappush(active, (int(end[i]), int(r)))

    if unplaced:
        warn(
            f"capacity on {spec.table}.{spec.resource}: {unplaced} interval(s) found "
            f"no allowed {rel.parent_table} with room; they keep their resource and "
            f"exceed its capacity. The story audit will report them.",
            ConformanceWarning,)
    changed = np.flatnonzero(assigned != resource)
    if changed.size:
        values = df[spec.resource].to_numpy(dtype=object, copy=True)
        values[changed] = pkeys[assigned[changed]]
        df[spec.resource] = pd.Series(values, index=df.index).astype(df[spec.resource].dtype)
        tables[spec.table] = df


# --------------------------------------------------------------------------- #
# containment
# --------------------------------------------------------------------------- #

def _grid_for(config: Any, table: str, column: str) -> Optional[Any]:
    for spec in getattr(config, "time_grids", None) or []:
        if spec.table == table and spec.column == column:
            return spec
    return None


def _ceil_to(ns: np.ndarray, step: int) -> np.ndarray:
    return -(-ns // step) * step


def _contained_times(lower: np.ndarray, upper: Optional[np.ndarray], step: int,
                     rng: np.random.Generator) -> Tuple[np.ndarray, np.ndarray]:
    """A moment inside ``[lower, upper]`` on a ``step`` grid, per row.

    With an upper bound the moment is drawn uniformly over the slots the span
    offers; without, it is the first slot at or after ``lower``. Returns the
    moments and which rows had a slot at all.
    """
    first = _ceil_to(lower, step)
    if upper is None:
        return first, np.ones(len(lower), dtype=bool)
    last = (upper // step) * step
    ok = last >= first
    slots = np.where(ok, (last - first) // step + 1, 1)
    pick = (rng.random(len(lower)) * slots).astype(np.int64)
    return first + np.minimum(pick, slots - 1) * step, ok


def _relationship_depth(config: Any) -> Dict[str, int]:
    """Each table's depth in the relationship graph, roots first."""
    rels = getattr(config, "relationships", None) or []
    depth: Dict[str, int] = {}

    def visit(table: str, seen: frozenset) -> int:
        if table in depth:
            return depth[table]
        parents = [r.parent_table for r in rels
                   if r.child_table == table and r.parent_table not in seen and r.parent_table != table]
        depth[table] = 1 + max((visit(p, seen | {table}) for p in parents), default=-1)
        return depth[table]

    for t in getattr(config, "tables", None) or []:
        visit(t.name, frozenset())
    return depth


def contained_relationships(config: Any) -> List[Any]:
    """Temporal relationships whose child moment lives on the child table."""
    return [r for r in getattr(config, "relationships", None) or []
            if r.parent_time and r.child_time and not r.child_time_table]


def apply_containment(tables: Dict[str, pd.DataFrame], config: Any,
                      rng: np.random.Generator) -> None:
    """Keep every child's moment inside its parent's declared span.

    Parents are settled before their children, so a chain of contained
    relationships resolves top-down in one pass.
    """
    depth = _relationship_depth(config)
    rels = sorted(contained_relationships(config),
                  key=lambda r: (depth.get(r.parent_table, 0), r.child_table, r.child_key))
    for rel in rels:
        child, parent = tables.get(rel.child_table), tables.get(rel.parent_table)
        if child is None or parent is None or child.empty or parent.empty:
            continue
        if (rel.child_key not in child.columns or rel.child_time not in child.columns
                or rel.parent_key not in parent.columns or rel.parent_time not in parent.columns):
            continue
        if rel.parent_end and rel.parent_end not in parent.columns:
            continue
        lookup = parent.drop_duplicates(subset=[rel.parent_key]).set_index(rel.parent_key)
        p_start = pd.to_datetime(child[rel.child_key].map(lookup[rel.parent_time]), errors="coerce")
        lower = np.where(p_start.notna(), _to_ns(p_start), 0)
        t, t_known = _ns(child, rel.child_time)
        known = p_start.notna().to_numpy() & t_known
        upper = None
        if rel.parent_end:
            p_end = pd.to_datetime(child[rel.child_key].map(lookup[rel.parent_end]), errors="coerce")
            known = known & p_end.notna().to_numpy()
            upper = np.where(p_end.notna(), _to_ns(p_end), 0)

        bad = known & (t < lower)
        if upper is not None:
            bad = bad | (known & (t > upper))
        rows = np.flatnonzero(bad)
        if not rows.size:
            continue

        types = _column_types(config, rel.child_table)
        grid = _grid_for(config, rel.child_table, rel.child_time)
        if types.get(rel.child_time) == "date":
            step = NS_PER_DAY
        elif grid is not None:
            step = int(grid.minute_grid) * NS_PER_MINUTE
        else:
            step = 10 ** 9
        new, ok = _contained_times(lower[rows], None if upper is None else upper[rows], step, rng)
        ok &= _same_period(config, rel.child_table, rel.child_time, t[rows], new)
        unresolved = int((~ok).sum())
        if unresolved:
            warn(
                f"{rel.parent_table}->{rel.child_table}: {unresolved} row(s) cannot be "
                f"placed inside their parent's span without leaving the declared period "
                f"or grid of {rel.child_time}; they keep their time. The story audit "
                f"will report them.",
                ConformanceWarning,)
        rows, new = rows[ok], new[ok]
        if not rows.size:
            continue
        _carry_later(child, rel.child_time, rows, t[rows], new, set())
        full = t.copy()
        full[rows] = new
        _write_ns(child, rel.child_time, full, rows, types.get(rel.child_time))
        tables[rel.child_table] = child


# --------------------------------------------------------------------------- #
# entry points
# --------------------------------------------------------------------------- #

def _rewritten_times(config: Any) -> Set[Tuple[str, str]]:
    """Timestamp columns a pass rewrites after their table was generated."""
    out = {(g.table, g.column) for g in getattr(config, "time_grids", None) or []}
    for spec in getattr(config, "no_overlap", None) or []:
        out |= {(spec.table, spec.start), (spec.table, spec.end)}
    return out


def interval_tables(config: Any) -> Set[str]:
    """Tables these passes rewrite or read whole, so generation buffers them."""
    out: Set[str] = set()
    for spec in getattr(config, "no_overlap", None) or []:
        out.add(spec.table)
    for spec in getattr(config, "capacity", None) or []:
        out.add(spec.table)
        rel = _relationship_for(config, spec.table, spec.resource)
        if rel is not None:
            out.add(rel.parent_table)
    rewritten = _rewritten_times(config)
    for rel in contained_relationships(config):
        if rel.parent_end or (rel.parent_table, rel.parent_time) in rewritten:
            out |= {rel.parent_table, rel.child_table}
    return out


def apply_intervals(tables: Dict[str, pd.DataFrame], config: Any,
                    rng: np.random.Generator) -> None:
    """Timelines, then capacities, then containment, on the final clocks."""
    for spec in getattr(config, "no_overlap", None) or []:
        try:
            apply_no_overlap(tables, spec, config)
        except Exception as e:  # noqa: BLE001 - a failed pass warns and leaves the table as generated
            warn(f"no_overlap on '{spec.table}' failed ({e}); table left as generated.",
                 ConformanceWarning)
    for spec in getattr(config, "capacity", None) or []:
        try:
            apply_capacity(tables, spec, config, rng)
        except Exception as e:  # noqa: BLE001 - a failed pass warns and leaves the table as generated
            warn(f"capacity on '{spec.table}' failed ({e}); table left as generated.",
                 ConformanceWarning)
    try:
        apply_containment(tables, config, rng)
    except Exception as e:  # noqa: BLE001 - a failed pass warns and leaves the tables as generated
        warn(f"temporal containment failed ({e}); tables left as generated.",
             ConformanceWarning)
