"""Waterfall identities: movement rows that reconcile to declared balances.

The canonical case is the SaaS MRR waterfall:

    MRR_t = MRR_{t-1} + new + expansion - contraction - churn

Declare the starting value and the ending value of every period, and the
generated movement rows satisfy the identity exactly, to the cent, in every
period: gross inflow splits across the inflow types, gross outflow across
the outflow types, and the running balance recomputed from the rows lands on
every declared ending value. The same declaration drives the generator, the
evalpack questions, and the story audit, so none of them can drift.

The arithmetic reuses :func:`misata.shares.split_total_by_shares` (rounding
residual to the largest share) and the balanced-ledger residual-to-largest-row
technique, the same primitives behind exact group shares.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from misata.schema import WaterfallIdentity
from misata.shares import split_total_by_shares


def _normalized(shares: Dict[str, float], label: str, spec_table: str) -> Dict[str, float]:
    out = {str(k): float(v) for k, v in (shares or {}).items() if float(v) > 0}
    s = sum(out.values())
    if not out or s <= 0:
        return {}
    if abs(s - 1.0) > 0.005:
        warnings.warn(
            f"waterfall on {spec_table}: {label} shares sum to {s:.3f}, "
            f"normalising to 1")
    return {k: v / s for k, v in out.items()}


def declared_movements(
    spec: WaterfallIdentity,
) -> List[Tuple[str, float, Dict[str, float], Dict[str, float]]]:
    """Per-period declared plan: [(period, ending_value, inflows, outflows)].

    Everything here is derived from the declaration alone (no data), so the
    generator, evalpack, and audit share one answer key. For each period:
    gross outflow is ``outflow_rate`` of the previous balance (raised to
    cover a declared decline), gross inflow is whatever makes the net equal
    the declared delta, and each side splits by its shares with the rounding
    residual on the largest share.
    """
    inflow = _normalized(spec.inflow_shares, "inflow", spec.table)
    outflow = _normalized(spec.outflow_shares, "outflow", spec.table)
    if not inflow or not outflow:
        return []
    plan = []
    prev = round(float(spec.starting_value), 2)
    for point in spec.points:
        period = str(point.get("period"))
        end = round(float(point.get("ending_value")), 2)
        delta = round(end - prev, 2)
        gross_out = round(max(prev, 0.0) * max(float(spec.outflow_rate), 0.0), 2)
        if delta < 0:
            gross_out = max(gross_out, -delta)
        gross_in = round(delta + gross_out, 2)
        plan.append((
            period,
            end,
            split_total_by_shares(inflow, gross_in) if gross_in > 0 else {},
            split_total_by_shares(outflow, gross_out) if gross_out > 0 else {},
        ))
        prev = end
    return plan


def _spec_gross(spec: WaterfallIdentity) -> float:
    """Total gross movement a spec declares (its fair share of the rows)."""
    return sum(
        sum(ins.values()) + sum(outs.values())
        for _, _, ins, outs in declared_movements(spec)
    )


def apply_waterfalls(
    df: pd.DataFrame,
    specs: List[WaterfallIdentity],
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Apply one or many waterfalls to a movements table.

    One spec applies to the whole table (the classic case). Several specs on
    the same table must be segment-scoped ("each tenant has its own declared
    trajectory"): all share one ``segment_column`` with distinct
    ``segment_value``s, the table's rows are partitioned across specs in
    proportion to each spec's declared gross movement, and the pass writes
    the segment column alongside period/type/amount. Every segment's running
    balance then reconciles independently.
    """
    if not specs:
        return df
    if len(specs) == 1 and specs[0].segment_column is None:
        return apply_waterfall(df, specs[0], rng)

    seg_cols = {s.segment_column for s in specs}
    seg_vals = [s.segment_value for s in specs]
    if (None in seg_cols or len(seg_cols) != 1
            or None in seg_vals or len(set(seg_vals)) != len(seg_vals)):
        warnings.warn(
            f"waterfalls on {specs[0].table}: multiple specs must share one "
            f"segment_column and carry distinct segment_values; skipping all "
            f"(ambiguous)")
        return df
    seg_col = specs[0].segment_column
    if seg_col not in df.columns:
        warnings.warn(
            f"waterfalls on {specs[0].table}: segment column '{seg_col}' "
            f"does not exist; skipping")
        return df

    # Partition rows across specs by declared gross movement, min one row
    # per period-type cell so every spec stays feasible when possible.
    gross = np.array([max(_spec_gross(s), 0.01) for s in specs])
    n = len(df)
    raw = gross / gross.sum() * n
    counts = np.maximum(np.floor(raw).astype(int), 1)
    while counts.sum() > n:
        counts[int(np.argmax(counts))] -= 1
    order = np.argsort(-(raw - np.floor(raw)))
    i = 0
    while counts.sum() < n:
        counts[order[i % len(specs)]] += 1
        i += 1

    idx = rng.permutation(n)
    pos = 0
    segments = df[seg_col].astype(object).to_numpy(copy=True)
    for spec, count in zip(specs, counts):
        rows = idx[pos: pos + count]
        pos += count
        slice_df = df.iloc[rows].copy()
        slice_df = apply_waterfall(slice_df, spec, rng)
        for col in (spec.period_column, spec.type_column, spec.amount_column):
            if col in slice_df.columns:
                df.iloc[rows, df.columns.get_loc(col)] = slice_df[col].values
        segments[rows] = spec.segment_value
    df[seg_col] = segments
    return df


def apply_waterfall(
    df: pd.DataFrame, spec: WaterfallIdentity, rng: np.random.Generator
) -> pd.DataFrame:
    """Overwrite period/type/amount so the declared waterfall holds exactly.

    Rows are allocated to (period, type) cells by largest remainder on each
    cell's share of the total declared gross movement, at least one row per
    positive cell. Within a cell, amounts rescale to the cell's declared
    total with the rounding residual on the cell's largest row. When the
    table has fewer rows than positive cells, the identity is skipped with a
    warning (partial application would break the running balance).
    """
    plan = declared_movements(spec)
    needed = {spec.period_column, spec.type_column, spec.amount_column}
    if not plan or not needed.issubset(df.columns):
        return df

    cells: List[Tuple[str, str, float]] = []
    for period, _end, inflows, outflows in plan:
        for label, total in list(inflows.items()) + list(outflows.items()):
            if total > 0:
                cells.append((period, label, total))
    n = len(df)
    if n < len(cells):
        warnings.warn(
            f"waterfall on {spec.table}: {n} rows cannot host {len(cells)} "
            f"period-type movements; skipping (infeasible)")
        return df
    if not cells:
        return df

    gross = np.array([c[2] for c in cells], dtype=float)
    raw = gross / gross.sum() * n
    counts = np.maximum(np.floor(raw).astype(int), 1)
    while counts.sum() > n:
        counts[int(np.argmax(counts))] -= 1
    order = np.argsort(-(raw - np.floor(raw)))
    i = 0
    while counts.sum() < n:
        counts[order[i % len(cells)]] += 1
        i += 1

    periods = np.empty(n, dtype=object)
    types = np.empty(n, dtype=object)
    amounts = np.empty(n, dtype=float)
    idx = rng.permutation(n)
    pos = 0
    for (period, label, total), count in zip(cells, counts):
        rows = idx[pos: pos + count]
        pos += count
        periods[rows] = period
        types[rows] = label
        # Right-skewed raw draws (a few big accounts, many small ones),
        # rescaled so the cell hits its declared total to the cent.
        draws = rng.lognormal(0.0, 0.9, count)
        draws = draws / draws.sum() * total
        draws = np.round(draws, 2)
        resid = round(total - draws.sum(), 2)
        if resid:
            draws[int(np.argmax(draws))] = round(
                draws[int(np.argmax(draws))] + resid, 2)
        amounts[rows] = draws

    df[spec.period_column] = periods
    df[spec.type_column] = types
    df[spec.amount_column] = amounts
    return df
