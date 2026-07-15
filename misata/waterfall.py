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
