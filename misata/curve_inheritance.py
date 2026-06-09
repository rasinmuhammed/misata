"""Temporal density propagation from parent to child tables.

When a parent table is generated via the FactEngine with exact temporal targets,
its rows are distributed non-uniformly across time (more rows in high-revenue
periods, fewer in low-revenue periods).  Child tables whose rows reference those
parent rows via FK should inherit this temporal clustering:

  Level 1 — FK weighting (automatic, zero config):
    FK values are sampled with probability proportional to the parent row's
    temporal density weight, so child rows cluster around the same time
    periods as their parents.

  Level 2 — inherits_curve_from (explicit, per-column):
    A child date column can declare ``inherits_curve_from: "parent_table.time_col"``
    in its distribution_params.  Dates are then sampled using the parent's
    temporal density instead of uniform random.

Both mechanisms share the same ``TemporalDensityMap`` primitive.

Mathematical basis
------------------
Let B_1 … B_K be the K temporal buckets of the parent FactGenerationPlan with
row counts n_1 … n_K (Σ n_k = N).  The density weight for bucket k is:

    w_k = n_k / N

For Level-1 FK sampling, each parent row i has weight w_{b(i)} where b(i) is
the bucket index of row i's timestamp.  We normalize across the N parent rows so
that FK sampling probability is proportional to row density.

For Level-2 date sampling, we use a multinomial draw over K buckets with
probabilities w_1 … w_K, then sample dates uniformly within each chosen bucket.
This matches the FactEngine's own date generation strategy exactly.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


class TemporalDensityMap:
    """Represents the temporal density of a fact table's row distribution.

    Stores the per-bucket row counts and bucket time ranges, enabling
    child tables to sample dates or FK values with matching temporal density.

    Attributes:
        table:       Parent table name.
        time_column: Name of the time column the density applies to.
        buckets:     List of (bucket_start, bucket_end, row_count) triples.
        weights:     Normalized density weights (sums to 1.0), one per bucket.
    """

    # Priority-ordered list of candidate time column names used when resolving
    # the time column for a child table that doesn't have a direct curve.
    _TIME_CANDIDATES = [
        "date", "created_at", "transaction_date", "order_date",
        "event_date", "signup_date", "timestamp", "payment_date",
        "sale_date", "order_at", "purchased_at",
    ]

    def __init__(
        self,
        table: str,
        time_column: str,
        buckets: List[Tuple[pd.Timestamp, pd.Timestamp, int]],
    ) -> None:
        self.table = table
        self.time_column = time_column
        self.buckets = buckets  # [(start, end, count), ...]

        total = sum(count for _, _, count in buckets)
        if total > 0:
            self.weights = np.array([count / total for _, _, count in buckets], dtype=float)
        else:
            n = max(len(buckets), 1)
            self.weights = np.ones(n, dtype=float) / n

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_fact_plan(cls, table: str, time_column: str, plan: "FactGenerationPlan") -> "TemporalDensityMap":  # noqa: F821
        """Construct from a ``FactGenerationPlan`` already resolved by the engine."""
        buckets = [
            (bucket.start, bucket.end, int(count))
            for bucket, count in zip(plan.buckets, plan.row_counts)
        ]
        return cls(table=table, time_column=time_column, buckets=buckets)

    @classmethod
    def from_dataframe(
        cls,
        table: str,
        time_column: str,
        df: pd.DataFrame,
        freq: str = "MS",  # month-start
    ) -> "TemporalDensityMap":
        """Construct from an already-generated DataFrame (for non-FactEngine tables).

        Bins the DataFrame's time column by month and uses the observed row
        counts per month as the density weights.
        """
        if time_column not in df.columns or df.empty:
            return cls(table=table, time_column=time_column, buckets=[])

        timestamps = pd.to_datetime(df[time_column], errors="coerce").dropna()
        if timestamps.empty:
            return cls(table=table, time_column=time_column, buckets=[])

        # Build monthly buckets covering the full observed range
        first = timestamps.min().normalize().replace(day=1)
        last = timestamps.max().normalize().replace(day=1) + pd.DateOffset(months=1)
        windows = pd.date_range(first, last, freq=freq)

        buckets: List[Tuple[pd.Timestamp, pd.Timestamp, int]] = []
        for start, end in zip(windows[:-1], windows[1:]):
            count = int(((timestamps >= start) & (timestamps < end)).sum())
            buckets.append((start, end, count))

        return cls(table=table, time_column=time_column, buckets=buckets)

    @classmethod
    def from_parent_weights(
        cls,
        child_table: str,
        child_time_column: str,
        parent_map: "TemporalDensityMap",
    ) -> "TemporalDensityMap":
        """Create a proxy density map for a child table by inheriting parent bucket weights.

        Used for deep hierarchy temporal propagation (Gap C): when a parent has
        an exact temporal curve but its child table has no direct curve, the child
        should still sample FK values and dates with matching temporal density.

        The proxy map reuses the parent's (start, end, synthetic_count) tuples
        where synthetic_count is proportional to the parent's normalized weight —
        we set it to 10000 × weight so the weight vector is preserved exactly
        through the normalisation step in ``__init__``.

        Args:
            child_table:       Name of the child table that will own this map.
            child_time_column: Name of the time column in the child table.
            parent_map:        The parent's ``TemporalDensityMap``.

        Returns:
            A new ``TemporalDensityMap`` with the same bucket structure as the
            parent but tagged for the child table.
        """
        if not parent_map.buckets:
            return cls(table=child_table, time_column=child_time_column, buckets=[])

        # Translate parent weights into synthetic row counts that preserve ratios
        proxy_buckets: List[Tuple[pd.Timestamp, pd.Timestamp, int]] = []
        for (bstart, bend, _), weight in zip(parent_map.buckets, parent_map.weights):
            synthetic_count = max(1, int(round(weight * 10_000)))
            proxy_buckets.append((bstart, bend, synthetic_count))

        return cls(
            table=child_table,
            time_column=child_time_column,
            buckets=proxy_buckets,
        )

    # ------------------------------------------------------------------
    # Core sampling API
    # ------------------------------------------------------------------

    def sample_dates(self, size: int, rng: np.random.Generator, start: Optional[pd.Timestamp] = None, end: Optional[pd.Timestamp] = None) -> np.ndarray:
        """Sample ``size`` dates with temporal density matching the parent table.

        Each date is drawn from a bucket chosen with probability proportional to
        the bucket's weight, then sampled uniformly within the bucket's
        [start, end) window.

        Args:
            size: Number of dates to generate.
            rng:  NumPy random generator (uses the simulator's seeded instance).
            start: Optional global lower bound to clip to.
            end:   Optional global upper bound to clip to.

        Returns:
            numpy array of ``pd.Timestamp`` values, length ``size``.
        """
        if not self.buckets or size <= 0:
            return np.array([], dtype="datetime64[ns]")

        active = [
            (s, e, w) for (s, e, _), w in zip(self.buckets, self.weights)
            if w > 0 and e > s
        ]
        if not active:
            return np.array([], dtype="datetime64[ns]")

        active_weights = np.array([w for _, _, w in active], dtype=float)
        active_weights /= active_weights.sum()

        # Multinomial bucket assignment
        counts = rng.multinomial(size, active_weights)
        result_ns: List[int] = []

        for (bstart, bend, _), count in zip(active, counts):
            if count <= 0:
                continue
            lo = bstart.value
            hi = bend.value
            if start is not None:
                lo = max(lo, start.value)
            if end is not None:
                hi = min(hi, end.value)
            if lo >= hi:
                lo = bstart.value
                hi = bend.value
            ns_vals = rng.integers(lo, hi, size=int(count))
            result_ns.extend(ns_vals.tolist())

        # Fill shortfall (rounding) from the densest bucket
        deficit = size - len(result_ns)
        if deficit > 0:
            bstart, bend, _ = active[int(np.argmax(active_weights))]
            lo = bstart.value
            hi = bend.value
            ns_vals = rng.integers(lo, hi, size=deficit)
            result_ns.extend(ns_vals.tolist())

        arr = np.array(result_ns[:size], dtype="int64")
        rng.shuffle(arr)
        return pd.to_datetime(arr).values

    def compute_fk_weights(self, parent_df: pd.DataFrame) -> np.ndarray:
        """Compute per-row sampling weights for FK selection from a parent DataFrame.

        Rows that fall in high-density buckets get higher weight so that FK
        sampling naturally clusters child rows around the parent's temporal peaks.

        Args:
            parent_df: The parent table's context DataFrame; must contain
                       ``self.time_column``.

        Returns:
            float array of length ``len(parent_df)``, normalised to sum 1.0.
            Returns uniform weights if the time column is absent or all zero.
        """
        n = len(parent_df)
        if n == 0:
            return np.array([], dtype=float)

        if self.time_column not in parent_df.columns or not self.buckets:
            return np.ones(n, dtype=float) / n

        timestamps = pd.to_datetime(parent_df[self.time_column], errors="coerce")
        row_weights = np.ones(n, dtype=float)  # default: uniform

        for (bstart, bend, _), weight in zip(self.buckets, self.weights):
            mask = (timestamps >= bstart) & (timestamps < bend)
            if mask.any():
                row_weights[mask.values] = weight

        total = row_weights.sum()
        if total <= 0:
            return np.ones(n, dtype=float) / n
        return row_weights / total


def resolve_inherits_curve_from(
    param_value: str,
    density_maps: Dict[str, TemporalDensityMap],
) -> Optional[TemporalDensityMap]:
    """Resolve an ``inherits_curve_from`` param string to a ``TemporalDensityMap``.

    Args:
        param_value:  Value of the ``inherits_curve_from`` distribution param,
                      expected format ``"parent_table.time_column"`` or just
                      ``"parent_table"`` (uses the density map's own time column).
        density_maps: Simulator's ``_parent_temporal_density`` registry.

    Returns:
        The resolved ``TemporalDensityMap``, or ``None`` if not found.
    """
    if not param_value or not density_maps:
        return None

    if "." in param_value:
        parent_table, _ = param_value.split(".", 1)
    else:
        parent_table = param_value

    return density_maps.get(parent_table)
