"""Stock-flow identities: inventory ledgers that reconcile to the unit.

For every SKU and every period:

    closing = opening + received - shipped
    opening of the next period = closing of this one

and shipments never exceed what is on hand, so no level goes negative.
Naively generated inventory data breaks all three within the first JOIN a
reviewer writes; this pass makes them true by construction, and the story
audit recomputes them from the rows.
"""

from __future__ import annotations

import warnings
from typing import List

import numpy as np
import pandas as pd

from misata.schema import StockFlowIdentity


def apply_stock_flow(
    df: pd.DataFrame, spec: StockFlowIdentity, rng: np.random.Generator
) -> pd.DataFrame:
    """Rewrite SKU/period/quantity columns so the stock ledger chains exactly.

    Rows are assigned one per (SKU, period): full histories first, and when
    the row count is not a multiple of the period count, the final SKU gets a
    shorter history starting at the first period (the chain still holds on
    every consecutive pair it has). SKU identifiers reuse the generated
    column's values so their format survives.
    """
    periods = [str(p) for p in (spec.periods or [])]
    needed = {spec.sku_column, spec.period_column, spec.open_column,
              spec.received_column, spec.shipped_column, spec.close_column}
    if not periods or not needed.issubset(df.columns):
        missing = sorted(needed - set(df.columns))
        if missing:
            warnings.warn(
                f"stock_flow on {spec.table}: missing column(s) {missing}; "
                f"skipping")
        return df
    n = len(df)
    P = len(periods)
    if n < 1:
        return df
    n_full = n // P
    remainder = n - n_full * P
    if n_full == 0:
        warnings.warn(
            f"stock_flow on {spec.table}: {n} rows cannot host even one "
            f"full {P}-period history; the last SKU gets a partial history")
    histories: List[int] = [P] * n_full + ([remainder] if remainder else [])

    pool = pd.unique(df[spec.sku_column])
    if len(pool) < len(histories):
        warnings.warn(
            f"stock_flow on {spec.table}: only {len(pool)} distinct "
            f"{spec.sku_column} values for {len(histories)} SKUs; reusing "
            f"values with a suffix")
        extra = [f"{pool[i % max(len(pool), 1)]}-{i}"
                 for i in range(len(histories) - len(pool))]
        pool = np.concatenate([pool.astype(object), np.array(extra, dtype=object)])

    skus = np.empty(n, dtype=object)
    period_out = np.empty(n, dtype=object)
    opening = np.empty(n, dtype=np.int64)
    received = np.empty(n, dtype=np.int64)
    shipped = np.empty(n, dtype=np.int64)
    closing = np.empty(n, dtype=np.int64)

    lo = min(int(spec.starting_min), int(spec.starting_max))
    hi = max(int(spec.starting_min), int(spec.starting_max))
    pos = 0
    for s_i, k in enumerate(histories):
        level = int(rng.integers(lo, hi + 1))
        # Typical flow magnitudes scale with the starting level, so a
        # high-volume SKU moves more units than a slow one.
        typical = max(level // 3, 1)
        for p_i in range(k):
            row = pos
            pos += 1
            skus[row] = pool[s_i]
            period_out[row] = periods[p_i]
            opening[row] = level
            r = int(rng.poisson(typical))
            available = level + r
            s = min(int(rng.poisson(typical)), available)
            received[row] = r
            shipped[row] = s
            level = available - s
            closing[row] = level

    df[spec.sku_column] = skus
    df[spec.period_column] = period_out
    df[spec.open_column] = opening
    df[spec.received_column] = received
    df[spec.shipped_column] = shipped
    df[spec.close_column] = closing
    return df
