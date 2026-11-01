"""Cross-table constraint enforcement: a child's numbers bounded by its parent's.

Two constraints that cannot run inside a single-table pass because they need
the FK parent materialised:

- ``lte_parent``:     child.column <= parent.parent_column, row by row.
  A refund larger than its order's total is impossible in real data; clamping
  it against the mapped parent value makes it impossible here too.

- ``sum_lte_parent``: per parent row, sum(child.column) <= parent.parent_column.
  Payments against one order must never total more than the order. Groups that
  overshoot are rescaled proportionally, which preserves each payment's share
  of the total rather than truncating whichever row came last.

Both work in integer units of the column's declared decimals, so a capped sum
equals its cap exactly rather than to within floating-point noise.

When the column also carries a declared aggregate (an exact outcome curve, or
group shares), the amount a clamp removes is not lost: it moves to rows in the
same declared cell (the same curve period and the same group) whose bound
still has room. Every declared total and share therefore survives the clamp
exactly. When no row in a cell has room, the declared aggregate takes
precedence, as it does over per-row bounds everywhere else, and a
``ConformanceWarning`` names how many bounds yielded.

Both run in the post-generation pass (``DataSimulator.generate_all``), after
the roll-ups that produce the parent columns they clamp against and before the
roll-ups that aggregate the clamped values upward — see the ordering there.

The fk linking child to parent is resolved from the declared relationship, so
a constraint on an undeclared pair is a warning, never a guess.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from misata.exceptions import ConformanceWarning, warn

CROSS_TABLE_TYPES = ("lte_parent", "sum_lte_parent")

#: Headroom of an uncapped bound, in units. Large enough never to bind, small
#: enough that sums of a few of them stay inside int64.
_UNBOUNDED = np.int64(1) << 60


def collect_cross_table_constraints(config: Any) -> List[Tuple[str, Any]]:
    """Return [(child_table_name, constraint), ...] for every declared
    cross-table constraint in the schema."""
    out: List[Tuple[str, Any]] = []
    for table in getattr(config, "tables", []) or []:
        for c in getattr(table, "constraints", []) or []:
            if getattr(c, "type", None) in CROSS_TABLE_TYPES:
                out.append((table.name, c))
    return out


def _find_fk(config: Any, child_table: str, parent_table: str):
    """The (child_key, parent_key) linking child to parent, from the declared
    relationships. None when the pair is not declared."""
    for rel in getattr(config, "relationships", []) or []:
        if rel.child_table == child_table and rel.parent_table == parent_table:
            return rel.child_key, rel.parent_key
    return None


def declared_cells(config: Any, table: str, column: str,
                   df: pd.DataFrame) -> Optional[np.ndarray]:
    """Label each row with the declared-aggregate cell its value belongs to.

    A cell is one period of every exact-target outcome curve on the column,
    crossed with one group of every ``group_shares`` on it. Moving value
    between rows of the same cell leaves every declared total and share
    unchanged. Returns None when no declared aggregate covers the column.
    """
    from misata.engines import FactEngine

    engine = FactEngine()
    parts: List[np.ndarray] = []
    for curve in getattr(config, "outcome_curves", None) or []:
        if (curve.table != table or curve.column != column
                or getattr(curve, "value_mode", "auto") == "count"
                or not engine.curve_has_exact_targets(curve)
                or curve.time_column not in df.columns):
            continue
        # Generation already resolved this curve to place its rows, so it resolves here.
        resolved = engine._resolve_curve(curve, config.get_columns(table))
        times = pd.to_datetime(df[curve.time_column], errors="coerce")
        bucket = np.full(len(df), -1, dtype=np.int64)
        for i, b in enumerate(resolved.buckets):
            bucket[((times >= b.start) & (times < b.end)).to_numpy()] = i
        parts.append(bucket)
    for spec in getattr(config, "group_shares", None) or []:
        if spec.table == table and spec.measure == column and spec.group_column in df.columns:
            parts.append(pd.factorize(df[spec.group_column], use_na_sentinel=True)[0])
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return np.asarray(pd.MultiIndex.from_arrays(parts).factorize()[0])


def _allocate_down(values: np.ndarray, target: int) -> np.ndarray:
    """Shrink non-negative integer ``values`` to sum to ``target`` exactly,
    proportionally, settling the last units on the largest remainders."""
    total = int(values.sum())
    if total <= target:
        return values
    if target <= 0:
        return np.zeros_like(values)
    exact = values.astype(float) * (target / total)
    out = np.minimum(np.floor(exact).astype(np.int64), values)
    short = target - int(out.sum())
    if short > 0:
        frac = exact - out
        for i in np.argsort(-frac, kind="stable"):
            if short == 0:
                break
            if out[i] < values[i]:
                out[i] += 1
                short -= 1
    return np.asarray(out, dtype=np.int64)


def _distribute_up(amount: int, weights: np.ndarray, room: np.ndarray,
                   groups: np.ndarray, group_room: np.ndarray) -> Tuple[np.ndarray, int]:
    """Add up to ``amount`` units over rows, in proportion to ``weights``.

    No row receives more than its ``room``, and the rows of one group together
    receive no more than that group's ``group_room`` (which is decremented in
    place). Returns the per-row additions and the units that found no room.
    """
    add = np.zeros(len(weights), dtype=np.int64)
    remaining = int(amount)
    for _ in range(64):
        if remaining == 0:
            break
        free = np.minimum(room - add, group_room[groups])
        live = free > 0
        if not live.any():
            break
        w = np.where(live, weights, 0.0)
        share = np.minimum(np.floor(remaining * w / w.sum()).astype(np.int64), free)
        per_group = np.bincount(groups, weights=share, minlength=len(group_room)).astype(np.int64)
        over = per_group > group_room
        if over.any():
            scale = np.ones(len(group_room))
            scale[over] = group_room[over] / per_group[over]
            share = np.floor(share * scale[groups]).astype(np.int64)
            per_group = np.bincount(groups, weights=share, minlength=len(group_room)).astype(np.int64)
        if share.sum() == 0:
            # Fewer units left than rows with room: one unit at a time, to the
            # rows with the most room first.
            for i in np.argsort(-free, kind="stable"):
                if remaining == 0 or free[i] <= 0:
                    break
                g = groups[i]
                if group_room[g] > 0 and add[i] < room[i]:
                    add[i] += 1
                    group_room[g] -= 1
                    remaining -= 1
            break
        add += share
        group_room -= per_group
        remaining -= int(share.sum())
    return add, remaining


def enforce_cap(values: np.ndarray, groups: np.ndarray, group_cap: np.ndarray,
                cells: Optional[np.ndarray], row_max: np.ndarray) -> Tuple[np.ndarray, int]:
    """Hold every group's sum at or under its cap, in integer units.

    Args:
        values: non-negative-or-signed integer values, one per row.
        groups: group index per row; ``-1`` for a row bound to no group.
        group_cap: cap per group, ``_UNBOUNDED`` where the group has none.
        cells: declared-aggregate cell per row, or None. With cells, every
            unit removed from an over-cap group moves to rows of the same
            cell whose groups have room; without, removed units are dropped.
        row_max: per-row upper bound honoured while moving units, where it can
            be (``_UNBOUNDED`` for none).

    Returns:
        The new values and the number of groups left over their cap because a
        declared aggregate had nowhere else to go.
    """
    v = values.astype(np.int64).copy()
    n_groups = len(group_cap)
    bound = groups >= 0
    g = np.where(bound, groups, 0)
    sums = np.bincount(g[bound], weights=v[bound], minlength=n_groups).astype(np.int64)
    over_group = sums > np.maximum(group_cap, 0)
    if not over_group.any():
        return v, 0

    freed = np.zeros(len(v), dtype=np.int64)
    for k in np.flatnonzero(over_group):
        rows = np.flatnonzero(bound & (g == k))
        positive = rows[v[rows] > 0]
        negative_sum = int(v[rows][v[rows] < 0].sum())
        target = max(int(group_cap[k]), 0) - negative_sum
        shrunk = _allocate_down(v[positive], target)
        freed[positive] = v[positive] - shrunk
        v[positive] = shrunk
    if cells is None:
        return v, 0

    sums = np.bincount(g[bound], weights=v[bound], minlength=n_groups).astype(np.int64)
    group_room = np.where(group_cap >= _UNBOUNDED, _UNBOUNDED,
                          np.maximum(group_cap - sums, 0)).astype(np.int64)
    # A row bound to no group is bound by nothing: it sits in an extra group of
    # its own with unlimited room.
    free_group = n_groups
    group_room = np.append(group_room, _UNBOUNDED)
    g_ext = np.where(bound, g, free_group)
    leftover_groups: set = set()
    order = pd.unique(cells[freed > 0])
    for cell in order:
        in_cell = cells == cell
        amount = int(freed[in_cell].sum())
        donors = np.flatnonzero(in_cell & (freed > 0))
        # Over-cap groups now sit exactly at their cap, so their room is zero
        # and they take nothing back.
        takers = np.flatnonzero(in_cell)
        if takers.size:
            weights = np.maximum(v[takers], 0).astype(float) + 1.0
            room = np.maximum(row_max[takers] - v[takers], 0)
            add, amount = _distribute_up(amount, weights, room, g_ext[takers], group_room)
            v[takers] += add
            if amount:
                # Aggregates outrank per-row bounds: place the rest ignoring row_max.
                add, amount = _distribute_up(amount, weights, np.full(takers.size, _UNBOUNDED),
                                             g_ext[takers], group_room)
                v[takers] += add
        if amount:
            give_back = _allocate_down(freed[donors], amount)
            v[donors] += give_back
            leftover_groups.update(int(x) for x in g[donors[give_back > 0]])
    return v, len(leftover_groups)


def apply_cross_table_constraints(
    tables: Dict[str, pd.DataFrame],
    constraints: List[Tuple[str, Any]],
    config: Any,
) -> Dict[str, pd.DataFrame]:
    """Enforce every collected cross-table constraint. Mutates and returns ``tables``."""
    from misata.shares import _declared_bounds, measure_decimals

    for child_name, c in constraints:
        child = tables.get(child_name)
        parent_name: Any = getattr(c, "parent_table", None)
        parent = tables.get(parent_name)
        col = getattr(c, "column", None)
        pcol = getattr(c, "parent_column", None)
        if child is None or parent is None:
            warn(
                f"Constraint '{c.name}': table '{child_name}' or its parent "
                f"'{c.parent_table}' is not materialised. Skipping.",
                ConformanceWarning,)
            continue
        if not col or col not in child.columns or not pcol or pcol not in parent.columns:
            warn(
                f"Constraint '{c.name}': column '{col}' or parent column "
                f"'{pcol}' not found. Skipping.",
                ConformanceWarning,)
            continue
        link = _find_fk(config, child_name, c.parent_table)
        if link is None:
            warn(
                f"Constraint '{c.name}': no declared relationship between "
                f"'{child_name}' and '{c.parent_table}'. Declare one; the fk "
                "is never guessed. Skipping.",
                ConformanceWarning,)
            continue
        child_key, parent_key = link
        if child_key not in child.columns or parent_key not in parent.columns:
            continue

        decimals = measure_decimals(config, child_name, col)
        scale = 10 ** decimals
        raw = pd.to_numeric(child[col], errors="coerce")
        present = raw.notna().to_numpy()
        values = np.round(raw.fillna(0).to_numpy(dtype=float) * scale).astype(np.int64)

        parent_vals = (parent.drop_duplicates(subset=[parent_key])
                       .set_index(parent_key)[pcol])
        mapped = pd.to_numeric(child[child_key].map(parent_vals), errors="coerce").to_numpy(dtype=float)
        if c.type == "lte_parent":
            groups = np.where(present, np.arange(len(child)), -1)
            cap = np.where(np.isnan(mapped), _UNBOUNDED,
                           np.floor(np.nan_to_num(mapped) * scale + 1e-9)).astype(np.int64)
        else:
            codes = pd.factorize(child[child_key], use_na_sentinel=True)[0]
            groups = np.where(present, codes, -1)
            cap = np.full(int(codes.max()) + 1 if codes.size else 0, _UNBOUNDED, dtype=np.int64)
            has_cap = (codes >= 0) & ~np.isnan(mapped)
            cap[codes[has_cap]] = np.floor(mapped[has_cap] * scale + 1e-9).astype(np.int64)

        cells = declared_cells(config, child_name, col, child)
        if cells is not None:
            cells = np.where(present, cells, -2)
        _, hi = _declared_bounds(config, child_name, col)
        row_max = np.full(len(child), _UNBOUNDED, dtype=np.int64)
        if hi is not None:
            row_max[:] = int(np.floor(hi * scale + 1e-9))

        new, yielded = enforce_cap(values, groups, cap, cells, row_max)
        if yielded:
            warn(
                f"Constraint '{c.name}': {yielded} "
                f"{'rows' if c.type == 'lte_parent' else 'parents'} of {child_name} "
                f"exceed {c.parent_table}.{pcol}, because the declared total of "
                f"{child_name}.{col} had no room left under any bound in its period "
                f"and group. The declared aggregate takes precedence; raise "
                f"{c.parent_table}.{pcol} or lower the declared total.",
                ConformanceWarning,)
        if np.array_equal(new, values):
            continue
        if decimals == 0 and present.all() and pd.api.types.is_integer_dtype(child[col]):
            child[col] = new.astype(child[col].dtype)
        else:
            updated = raw.to_numpy(dtype=float, copy=True)
            updated[present] = new[present] / scale
            child[col] = updated
        tables[child_name] = child
    return tables
