"""Top-down fact generation for exact aggregate targets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


PERIOD_INDEX_COLUMN = "__misata_period_index__"
TARGET_KEYS = ("target_value", "value", "target", "amount")


@dataclass
class PeriodBucket:
    """Resolved time bucket for a constrained fact table."""

    index: int
    start: pd.Timestamp
    end: pd.Timestamp
    label: str


@dataclass
class ResolvedCurve:
    """A normalized outcome curve ready for exact row generation."""

    column: str
    time_column: str
    time_unit: str
    buckets: List[PeriodBucket]
    targets: np.ndarray
    min_transactions_per_period: int = 1
    max_transactions_per_period: int = 10000
    avg_transaction_value: Optional[float] = None
    concentration: float = 2.0
    intra_period_pattern: str = "uniform"


@dataclass
class FactGenerationPlan:
    """Execution plan for exact aggregate generation."""

    time_column: str
    time_unit: str
    buckets: List[PeriodBucket]
    row_counts: np.ndarray
    curves: List[ResolvedCurve]
    intra_period_pattern: str = "uniform"

    @property
    def constrained_columns(self) -> set[str]:
        return {curve.column for curve in self.curves}


class FactEngine:
    """Generates fact rows that satisfy exact period-level targets."""

    def __init__(self, rng: Optional[np.random.Generator] = None):
        self.rng = rng or np.random.default_rng()

    @staticmethod
    def curve_has_exact_targets(curve: Any) -> bool:
        """Return True when a curve carries explicit bucket targets."""
        value_mode = getattr(curve, "value_mode", "auto")
        if value_mode == "relative":
            return False

        points = getattr(curve, "curve_points", []) or []
        return any(
            isinstance(point, dict) and any(key in point for key in TARGET_KEYS)
            for point in points
        )

    def build_plan(
        self,
        table: Any,
        columns: List[Any],
        curves: List[Any],
    ) -> Optional[FactGenerationPlan]:
        """Resolve compatible exact curves into a single generation plan."""
        exact_curves = [curve for curve in curves if self.curve_has_exact_targets(curve)]
        if not exact_curves:
            return None

        resolved_curves = [self._resolve_curve(curve, columns) for curve in exact_curves]
        time_columns = {curve.time_column for curve in resolved_curves}
        time_units = {curve.time_unit for curve in resolved_curves}
        bucket_labels = {
            tuple(bucket.label for bucket in curve.buckets)
            for curve in resolved_curves
        }

        if len(time_columns) != 1 or len(time_units) != 1 or len(bucket_labels) != 1:
            return None

        primary = resolved_curves[0]
        row_counts = self._allocate_row_counts(table.row_count, primary)
        return FactGenerationPlan(
            time_column=primary.time_column,
            time_unit=primary.time_unit,
            buckets=primary.buckets,
            row_counts=row_counts,
            curves=resolved_curves,
            intra_period_pattern=primary.intra_period_pattern,
        )

    def generate(self, plan: FactGenerationPlan, column_map: Dict[str, Any]) -> pd.DataFrame:
        """Build the base scaffold for a constrained fact table."""
        rows: List[pd.DataFrame] = []
        time_column = plan.time_column

        for bucket, row_count in zip(plan.buckets, plan.row_counts):
            if row_count <= 0:
                continue

            frame = pd.DataFrame(
                {
                    PERIOD_INDEX_COLUMN: np.full(row_count, bucket.index, dtype=int),
                    time_column: self._generate_timestamps(bucket, row_count, plan.intra_period_pattern),
                }
            )
            rows.append(frame)

        if rows:
            df = pd.concat(rows, ignore_index=True)
        else:
            df = pd.DataFrame(columns=[PERIOD_INDEX_COLUMN, time_column])

        for curve in plan.curves:
            decimals = self._column_decimals(column_map.get(curve.column))
            df[curve.column] = 0.0 if decimals else 0
            for bucket_index, target in enumerate(curve.targets):
                mask = df[PERIOD_INDEX_COLUMN] == bucket_index
                bucket_rows = int(mask.sum())
                if bucket_rows <= 0:
                    continue
                df.loc[mask, curve.column] = self._generate_exact_values(
                    target=target,
                    row_count=bucket_rows,
                    timestamps=df.loc[mask, time_column],
                    decimals=decimals,
                    concentration=curve.concentration,
                    intra_period_pattern=curve.intra_period_pattern,
                )

        return df

    def rebalance(self, df: pd.DataFrame, plan: FactGenerationPlan, column_map: Dict[str, Any]) -> pd.DataFrame:
        """Re-apply exact sums after realism/events to preserve hard targets."""
        if PERIOD_INDEX_COLUMN not in df.columns:
            return df

        for curve in plan.curves:
            decimals = self._column_decimals(column_map.get(curve.column))
            for bucket_index, target in enumerate(curve.targets):
                mask = df[PERIOD_INDEX_COLUMN] == bucket_index
                bucket_rows = int(mask.sum())
                if bucket_rows <= 0:
                    continue
                df.loc[mask, curve.column] = self._generate_exact_values(
                    target=target,
                    row_count=bucket_rows,
                    timestamps=df.loc[mask, plan.time_column],
                    decimals=decimals,
                    concentration=curve.concentration,
                    intra_period_pattern=curve.intra_period_pattern,
                )
        return df

    def drop_internal_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove internal helper columns before yielding results."""
        return df.drop(columns=[PERIOD_INDEX_COLUMN], errors="ignore")

    def _resolve_curve(self, curve: Any, columns: List[Any]) -> ResolvedCurve:
        points = getattr(curve, "curve_points", []) or []
        time_column = getattr(curve, "time_column", "date")
        time_unit = getattr(curve, "time_unit", "month")
        start_date = self._resolve_start_date(curve, columns, time_column)

        sorted_points = sorted(points, key=self._point_sort_key)
        buckets: List[PeriodBucket] = []
        targets: List[float] = []

        for index, point in enumerate(sorted_points):
            start, end, label = self._resolve_bucket_window(point, index, time_unit, start_date)
            buckets.append(PeriodBucket(index=index, start=start, end=end, label=label))
            targets.append(float(self._extract_target_value(point)))

        return ResolvedCurve(
            column=getattr(curve, "column"),
            time_column=time_column,
            time_unit=time_unit,
            buckets=buckets,
            targets=np.array(targets, dtype=float),
            min_transactions_per_period=max(1, int(getattr(curve, "min_transactions_per_period", 1))),
            max_transactions_per_period=max(1, int(getattr(curve, "max_transactions_per_period", 10000))),
            avg_transaction_value=getattr(curve, "avg_transaction_value", None),
            concentration=max(0.1, float(getattr(curve, "concentration", 2.0))),
            intra_period_pattern=getattr(curve, "intra_period_pattern", "uniform"),
        )

    def _allocate_row_counts(self, fallback_row_count: int, curve: ResolvedCurve) -> np.ndarray:
        positive_targets = np.maximum(curve.targets, 0)
        row_counts = np.zeros(len(curve.targets), dtype=int)

        if curve.avg_transaction_value and curve.avg_transaction_value > 0:
            for index, target in enumerate(positive_targets):
                if target <= 0:
                    continue
                estimated = int(round(target / curve.avg_transaction_value))
                estimated = max(curve.min_transactions_per_period, estimated)
                estimated = min(curve.max_transactions_per_period, estimated)
                row_counts[index] = self._clip_to_target_units(estimated, target)
            return row_counts

        active = positive_targets > 0
        active_count = int(active.sum())
        if active_count == 0:
            return row_counts

        total_rows = max(int(fallback_row_count), active_count)
        base_allocation = positive_targets / positive_targets.sum()
        row_counts = np.floor(base_allocation * total_rows).astype(int)
        row_counts[active] = np.maximum(row_counts[active], 1)

        delta = total_rows - int(row_counts.sum())
        if delta > 0:
            priorities = np.argsort(-(base_allocation - np.floor(base_allocation * total_rows)))
            for idx in priorities:
                if positive_targets[idx] <= 0:
                    continue
                row_counts[idx] += 1
                delta -= 1
                if delta == 0:
                    break
        elif delta < 0:
            priorities = np.argsort(base_allocation)
            for idx in priorities:
                while delta < 0 and row_counts[idx] > 1:
                    row_counts[idx] -= 1
                    delta += 1
                if delta == 0:
                    break

        for index, target in enumerate(positive_targets):
            if target <= 0:
                row_counts[index] = 0
                continue
            row_counts[index] = self._clip_to_target_units(row_counts[index], target)

        return row_counts

    def _clip_to_target_units(self, row_count: int, target: float, decimals: int = 2) -> int:
        unit_count = int(round(abs(target) * (10 ** decimals)))
        if unit_count <= 0:
            return 0
        return min(max(1, int(row_count)), unit_count)

    def _generate_timestamps(self, bucket: PeriodBucket, row_count: int, pattern: str = "uniform") -> pd.Series:
        start_ns = bucket.start.value
        end_ns = bucket.end.value
        if end_ns <= start_ns:
            return pd.Series([bucket.start] * row_count)

        if pattern == "uniform":
            random_ns = self.rng.integers(start_ns, end_ns, size=row_count)
            return pd.to_datetime(np.sort(random_ns))

        # Drop to day-level bins for weighted distribution
        days_in_bucket = (bucket.end - bucket.start).days
        if days_in_bucket <= 1:
            random_ns = self.rng.integers(start_ns, end_ns, size=row_count)
            return pd.to_datetime(np.sort(random_ns))

        days_arr = np.arange(days_in_bucket)
        dates = pd.Series([bucket.start + pd.Timedelta(days=int(d)) for d in days_arr])

        weights = np.ones(days_in_bucket, dtype=float)
        if pattern == "weekday_heavy":
            weights = np.where(dates.dt.dayofweek < 5, 5.0, 1.0)
        elif pattern == "weekend_heavy":
            weights = np.where(dates.dt.dayofweek >= 5, 5.0, 1.0)
        elif pattern == "start_heavy":
            weights = np.exp(-days_arr / (days_in_bucket / 3.0))
        elif pattern == "end_heavy":
            weights = np.exp((days_arr - days_in_bucket) / (days_in_bucket / 3.0))

        probs = weights / weights.sum()
        chosen_days = self.rng.choice(days_arr, size=row_count, p=probs)

        day_ns = 24 * 60 * 60 * 1_000_000_000
        intraday_ns = self.rng.integers(0, day_ns, size=row_count)

        base_ns = bucket.start.value + (chosen_days * day_ns)
        final_ns = base_ns + intraday_ns
        final_ns = np.clip(final_ns, start_ns, end_ns - 1)
        return pd.to_datetime(np.sort(final_ns))

    def _generate_exact_values(
        self,
        target: float,
        row_count: int,
        timestamps: pd.Series,
        decimals: int = 2,
        concentration: float = 2.0,
        intra_period_pattern: str = "uniform",
    ) -> np.ndarray:
        if row_count <= 0:
            return np.array([], dtype=float if decimals else int)

        multiplier = 10 ** decimals
        total_units = int(round(target * multiplier))
        if total_units <= 0:
            zeros = np.zeros(row_count, dtype=int)
            return zeros / multiplier if decimals else zeros

        alpha_array = np.full(row_count, concentration, dtype=float)
        if intra_period_pattern != "uniform" and len(timestamps) == row_count:
            ts = pd.to_datetime(timestamps)
            if intra_period_pattern == "weekday_heavy":
                alpha_array *= np.where(ts.dt.dayofweek < 5, 2.0, 0.5)
            elif intra_period_pattern == "weekend_heavy":
                alpha_array *= np.where(ts.dt.dayofweek >= 5, 2.0, 0.5)
            elif intra_period_pattern in ("start_heavy", "end_heavy"):
                min_t, max_t = timestamps.min(), timestamps.max()
                if max_t > min_t:
                    # timestamps might not be sorted identically to original index logic but .min()/.max() is safe
                    # wait, pandas Series might need values instead of naive max across index, but dt handles it
                    # Convert to numeric for calculation to avoid timedelta issues
                    min_ns, max_ns = min_t.value, max_t.value
                    if max_ns > min_ns:
                        ns_vals = timestamps.astype('int64')
                        progress = (ns_vals - min_ns) / (max_ns - min_ns)
                        if intra_period_pattern == "start_heavy":
                            alpha_array *= np.exp(-progress * 2)
                        else:
                            alpha_array *= np.exp((progress - 1) * 2)

        proportions = self.rng.dirichlet(alpha_array)
        raw_units = proportions * total_units
        units = np.floor(raw_units).astype(int)

        remainder = total_units - int(units.sum())
        if remainder > 0:
            fractional = raw_units - units
            priority = np.argsort(-fractional)
            units[priority[:remainder]] += 1

        units = np.maximum(units, 0)
        if units.sum() != total_units:
            units[-1] += total_units - int(units.sum())

        if decimals:
            return units / multiplier
        return units.astype(int)

    def _column_decimals(self, column: Optional[Any]) -> int:
        if column is None:
            return 2
        if getattr(column, "type", None) == "int":
            return 0
        return int(getattr(column, "distribution_params", {}).get("decimals", 2))

    def _resolve_start_date(self, curve: Any, columns: List[Any], time_column: str) -> pd.Timestamp:
        explicit_start = getattr(curve, "start_date", None)
        if explicit_start:
            return pd.to_datetime(explicit_start)

        for column in columns:
            if getattr(column, "name", None) != time_column:
                continue
            params = getattr(column, "distribution_params", {})
            if "start" in params:
                return pd.to_datetime(params["start"])

        return pd.Timestamp.now().normalize().replace(month=1, day=1)

    def _resolve_bucket_window(
        self,
        point: Dict[str, Any],
        index: int,
        time_unit: str,
        start_date: pd.Timestamp,
    ) -> tuple[pd.Timestamp, pd.Timestamp, str]:
        if "month" in point:
            month = int(point["month"])
            bucket_start = pd.Timestamp(year=start_date.year, month=month, day=1)
            bucket_end = bucket_start + pd.DateOffset(months=1)
            return bucket_start, bucket_end, f"month:{month}"

        if "date" in point:
            bucket_start = pd.to_datetime(point["date"])
            bucket_end = self._advance_time(bucket_start, time_unit)
            return bucket_start, bucket_end, f"date:{bucket_start.isoformat()}"

        bucket_start = start_date + self._time_offset(index, time_unit)
        bucket_end = self._advance_time(bucket_start, time_unit)
        return bucket_start, bucket_end, f"period:{index}"

    def _advance_time(self, timestamp: pd.Timestamp, time_unit: str) -> pd.Timestamp:
        if time_unit == "day":
            return timestamp + pd.Timedelta(days=1)
        if time_unit == "week":
            return timestamp + pd.Timedelta(weeks=1)
        return timestamp + pd.DateOffset(months=1)

    def _time_offset(self, index: int, time_unit: str) -> pd.DateOffset | pd.Timedelta:
        if time_unit == "day":
            return pd.Timedelta(days=index)
        if time_unit == "week":
            return pd.Timedelta(weeks=index)
        return pd.DateOffset(months=index)

    def _point_sort_key(self, point: Dict[str, Any]) -> Any:
        if "month" in point:
            return (0, int(point["month"]))
        if "date" in point:
            return (1, pd.to_datetime(point["date"]))
        if "period" in point:
            return (2, int(point["period"]))
        if "index" in point:
            return (3, int(point["index"]))
        return (4, 0)

    def _extract_target_value(self, point: Dict[str, Any]) -> float:
        for key in TARGET_KEYS:
            if key in point:
                return float(point[key])
        raise ValueError("Exact outcome curves require target_value/value/target/amount per point.")
