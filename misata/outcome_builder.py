"""
Fluent builder for OutcomeCurve and RateCurve objects.

This is the primary SDK entry point for the no-code UI backend.
The UI sends sparse anchor points (whatever the user placed on the chart);
the builder does the interpolation and returns a fully-specified
OutcomeCurve or RateCurve that the FactEngine can execute exactly.

Quick start::

    from misata import OutcomeCurveBuilder, parse, generate_from_schema

    # Build a growth curve with a mid-year push and August dip
    curve = (
        OutcomeCurveBuilder("orders", column="amount", time_column="order_date")
        .start("2024-01-01")
        .anchor("2024-01", 10_000)
        .anchor("2024-06", 45_000)
        .anchor("2024-12", 120_000)
        .dip("2024-08", factor=0.7)      # August slowdown
        .avg_value(75.0)                  # drives row-count planning (§3.1)
        .concentration(2.0)               # Dirichlet α — controls dispersion (§3.2)
        .build()
    )

    schema = parse("An ecommerce store with 10k orders")
    schema = OutcomeCurveBuilder.attach(schema, curve)
    tables = generate_from_schema(schema)

    # Verify — monthly rollups must equal the declared targets exactly
    monthly = tables["orders"].groupby(
        tables["orders"]["order_date"].dt.to_period("M")
    )["amount"].sum()
    assert monthly["2024-01"] == 10_000.00
    assert monthly["2024-12"] == 120_000.00

Rate curve variant (fraud rate / churn rate)::

    fraud_curve = (
        OutcomeCurveBuilder.rate(
            "transactions", column="is_fraud", time_column="transaction_date"
        )
        .anchor("2024-01", 0.02)
        .anchor("2024-12", 0.05)   # fraud uptick through the year
        .build()
    )
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Union

import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_period_key(period: Union[str, int]) -> tuple[str, int]:
    """Return (kind, numeric_index) for a period label.

    Supported formats:
    - ``"2024-01"``  → month 1  (kind="date")
    - ``"2024-Q1"``  → month 1  (kind="quarter")
    - ``"2024-Q4"``  → month 10 (kind="quarter")
    - ``1``          → month 1  (kind="index")
    - ``12``         → month 12 (kind="index")
    """
    if isinstance(period, int):
        return ("index", period)

    s = str(period).strip()

    # ISO month: "YYYY-MM"
    if len(s) == 7 and s[4] == "-" and s[5:].isdigit():
        return ("date", int(s[5:]))

    # Quarter: "YYYY-Q1" through "YYYY-Q4"
    if len(s) == 7 and s[4] == "-" and s[5].upper() == "Q":
        q = int(s[6])
        return ("quarter", (q - 1) * 3 + 1)

    # Plain integer string
    if s.isdigit():
        return ("index", int(s))

    raise ValueError(
        f"Unrecognised period format {period!r}. "
        "Use 'YYYY-MM', 'YYYY-Q1'–'YYYY-Q4', or an integer month index."
    )


def _interp_monthly_targets(
    anchors: Dict[int, float],
    modifiers: Dict[int, float],
    n_periods: int,
) -> List[float]:
    """Linearly interpolate anchor values across ``n_periods`` and apply modifiers."""
    months = np.arange(1, n_periods + 1)
    if not anchors:
        return [0.0] * n_periods

    x_known = np.array(sorted(anchors), dtype=float)
    y_known = np.array([anchors[int(m)] for m in x_known], dtype=float)
    values = np.interp(months, x_known, y_known)

    # Apply qualitative modifiers
    for month, factor in modifiers.items():
        if 1 <= month <= n_periods:
            values[month - 1] *= factor

    # Re-pin explicit anchors so they remain exact
    for month, exact in anchors.items():
        if 1 <= month <= n_periods:
            values[month - 1] = exact

    return [max(float(v), 0.0) for v in values]


# ---------------------------------------------------------------------------
# OutcomeCurveBuilder
# ---------------------------------------------------------------------------

class OutcomeCurveBuilder:
    """Fluent builder for :class:`~misata.schema.OutcomeCurve`.

    All mutating methods return ``self`` so calls can be chained.
    Call :meth:`build` at the end to get the :class:`~misata.schema.OutcomeCurve`.

    Args:
        table:       Name of the table that holds the metric column.
        column:      Numeric column to apply the aggregate curve to.
        time_column: Date/datetime column used to bucket rows into periods.

    Example::

        curve = (
            OutcomeCurveBuilder("subscriptions", column="mrr", time_column="start_date")
            .start("2024-01-01")
            .anchor("2024-01", 50_000)
            .anchor("2024-12", 200_000)
            .spike("2024-11", factor=1.3)   # November push
            .dip("2024-08",   factor=0.8)   # summer dip
            .avg_value(150.0)
            .concentration(2.0)
            .build()
        )
    """

    def __init__(
        self,
        table: str,
        *,
        column: str,
        time_column: str = "date",
    ) -> None:
        self._table = table
        self._column = column
        self._time_column = time_column
        self._start_date: Optional[str] = None
        self._time_unit: str = "month"
        self._pattern_type: str = "growth"
        self._intra_period_pattern: str = "uniform"
        self._avg_value: Optional[float] = None
        self._concentration: float = 2.0
        self._min_tx: int = 1
        self._max_tx: int = 10_000
        self._n_periods: int = 12
        self._description: Optional[str] = None
        # Internal state
        self._anchors: Dict[int, float] = {}   # month → exact target
        self._modifiers: Dict[int, float] = {} # month → multiplier

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def start(self, date: str) -> "OutcomeCurveBuilder":
        """Set the start date for the curve (``"YYYY-MM-DD"``)."""
        self._start_date = date
        return self

    def time_unit(self, unit: str) -> "OutcomeCurveBuilder":
        """Set granularity: ``"month"`` (default), ``"week"``, or ``"day"``."""
        self._time_unit = unit
        return self

    def periods(self, n: int) -> "OutcomeCurveBuilder":
        """Set the total number of periods (default 12 for monthly)."""
        self._n_periods = n
        return self

    def avg_value(self, mu: float) -> "OutcomeCurveBuilder":
        """Average transaction value — drives row-count planning (paper §3.1).

        Setting this makes the engine use ``n_p = round(T_p / mu)`` as the
        row count for each period, keeping per-row values realistic.
        """
        self._avg_value = mu
        return self

    def concentration(self, alpha: float) -> "OutcomeCurveBuilder":
        """Dirichlet concentration parameter α — controls per-row dispersion (§3.2).

        Higher α → tighter dispersion around the period mean.
        Lower α (→ 0) → more skewed, heavy-tailed per-row values.
        Default is 2.0 (moderate dispersion, good for monetary columns).
        """
        self._concentration = max(0.1, float(alpha))
        return self

    def row_bounds(self, min_tx: int, max_tx: int) -> "OutcomeCurveBuilder":
        """Row-count bounds per period (paper Prop. 3 distortion guard)."""
        self._min_tx = max(1, min_tx)
        self._max_tx = max(min_tx, max_tx)
        return self

    def intra_period(self, pattern: str) -> "OutcomeCurveBuilder":
        """Within-period timestamp distribution.

        Options: ``"uniform"`` (default), ``"weekday_heavy"``,
        ``"weekend_heavy"``, ``"start_heavy"``, ``"end_heavy"``.
        """
        self._intra_period_pattern = pattern
        return self

    def describe(self, text: str) -> "OutcomeCurveBuilder":
        """Attach a human-readable description to the curve."""
        self._description = text
        return self

    # ------------------------------------------------------------------
    # Anchors & modifiers
    # ------------------------------------------------------------------

    def anchor(
        self,
        period: Union[str, int],
        value: float,
    ) -> "OutcomeCurveBuilder":
        """Pin an exact aggregate target for one period.

        Args:
            period: Period label — ``"YYYY-MM"``, ``"YYYY-Q1"``, or integer month.
            value:  Exact total for that period (e.g. ``50_000.0`` dollars).

        The engine guarantees this total will be hit exactly (AME = 0).
        """
        _, month = _parse_period_key(period)
        self._anchors[month] = float(value)
        return self

    def dip(
        self,
        period: Union[str, int],
        *,
        factor: float,
    ) -> "OutcomeCurveBuilder":
        """Apply a multiplicative downward modifier to a period.

        ``factor`` should be between 0 and 1 (e.g. ``0.7`` = 30% dip).
        If the period already has an explicit anchor, the modifier is applied
        on top of the anchor value.
        """
        _, month = _parse_period_key(period)
        self._modifiers[month] = float(factor)
        return self

    def spike(
        self,
        period: Union[str, int],
        *,
        factor: float,
    ) -> "OutcomeCurveBuilder":
        """Apply a multiplicative upward modifier to a period.

        ``factor`` should be > 1 (e.g. ``1.5`` = 50% spike).
        """
        _, month = _parse_period_key(period)
        self._modifiers[month] = float(factor)
        return self

    def quarter_pattern(
        self,
        q1: float = 1.0,
        q2: float = 1.0,
        q3: float = 1.0,
        q4: float = 1.0,
    ) -> "OutcomeCurveBuilder":
        """Set relative multipliers for all four quarters at once.

        Each value is applied to all three months in the respective quarter.
        Combined with :meth:`anchor` for precise shaping::

            curve.quarter_pattern(q1=0.8, q2=1.0, q3=0.9, q4=1.4)
        """
        for q, factor in enumerate([q1, q2, q3, q4], start=1):
            start_month = (q - 1) * 3 + 1
            for m in range(start_month, start_month + 3):
                self._modifiers[m] = float(factor)
        return self

    def seasonal(
        self,
        *,
        black_friday: bool = False,
        christmas: bool = False,
        summer_dip: bool = False,
        new_year: bool = False,
    ) -> "OutcomeCurveBuilder":
        """Apply named seasonal event multipliers (convenience shorthand).

        These match the same factors the NL story parser uses internally so
        SDK-built curves behave identically to story-parsed ones.
        """
        if black_friday:
            self._modifiers[11] = self._modifiers.get(11, 1.0) * 1.55
        if christmas:
            self._modifiers[12] = self._modifiers.get(12, 1.0) * 1.40
        if summer_dip:
            for m in (7, 8):
                self._modifiers[m] = self._modifiers.get(m, 1.0) * 0.75
        if new_year:
            self._modifiers[1] = self._modifiers.get(1, 1.0) * 1.25
        return self

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> "OutcomeCurve":  # type: ignore[name-defined]
        """Interpolate anchors + modifiers and return an :class:`~misata.schema.OutcomeCurve`.

        The returned curve has ``value_mode="absolute"`` so the FactEngine
        treats every ``curve_points`` entry as an exact aggregate target.

        Raises:
            ValueError: If no anchors have been set (nothing to constrain).
        """
        from misata.schema import OutcomeCurve

        if not self._anchors:
            raise ValueError(
                "OutcomeCurveBuilder requires at least one .anchor() call "
                "before .build(). Use .anchor(period, value) to set aggregate targets."
            )

        targets = _interp_monthly_targets(
            self._anchors, self._modifiers, self._n_periods
        )
        curve_points = [
            {"month": m, "target_value": round(v, 2)}
            for m, v in enumerate(targets, start=1)
        ]

        return OutcomeCurve(
            table=self._table,
            column=self._column,
            time_column=self._time_column,
            time_unit=self._time_unit,
            pattern_type=self._pattern_type,
            intra_period_pattern=self._intra_period_pattern,
            value_mode="absolute",
            avg_transaction_value=self._avg_value,
            concentration=self._concentration,
            min_transactions_per_period=self._min_tx,
            max_transactions_per_period=self._max_tx,
            start_date=self._start_date,
            description=self._description,
            curve_points=curve_points,
        )

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def attach(schema: "SchemaConfig", *curves: Any) -> "SchemaConfig":  # type: ignore[name-defined]
        """Attach one or more curves to an existing ``SchemaConfig``.

        Accepts :class:`~misata.schema.OutcomeCurve` and
        :class:`~misata.schema.RateCurve` objects.  Returns a shallow copy
        of the schema with the curves appended (does not mutate the original).

        Example::

            schema = misata.parse("A fintech with 5k transactions")
            schema = OutcomeCurveBuilder.attach(schema, volume_curve, fraud_curve)
            tables = misata.generate_from_schema(schema)
        """
        from misata.schema import OutcomeCurve, RateCurve

        schema = copy.deepcopy(schema)
        for curve in curves:
            if isinstance(curve, RateCurve):
                schema.rate_curves.append(curve)
            elif isinstance(curve, OutcomeCurve):
                schema.outcome_curves.append(curve)
            else:
                raise TypeError(
                    f"Expected OutcomeCurve or RateCurve, got {type(curve).__name__}"
                )
        return schema

    @staticmethod
    def rate(
        table: str,
        *,
        column: str,
        time_column: str = "date",
    ) -> "RateCurveBuilder":
        """Start building a :class:`~misata.schema.RateCurve` (rate-conformance axis).

        Example::

            fraud_curve = (
                OutcomeCurveBuilder.rate(
                    "transactions",
                    column="is_fraud",
                    time_column="transaction_date",
                )
                .anchor("2024-01", 0.02)
                .anchor("2024-12", 0.05)
                .build()
            )
        """
        return RateCurveBuilder(table, column=column, time_column=time_column)

    @staticmethod
    def from_dict(spec: Dict[str, Any]) -> "OutcomeCurveBuilder":
        """Reconstruct a builder from a serialised dict (e.g. from the no-code UI).

        The dict should match the no-code UI's internal JSON representation::

            {
                "table": "orders",
                "column": "amount",
                "time_column": "order_date",
                "start_date": "2024-01-01",
                "anchors": {"2024-01": 10000, "2024-06": 45000, "2024-12": 120000},
                "modifiers": {"2024-08": 0.7},
                "avg_value": 75.0,
                "concentration": 2.0,
                "n_periods": 12
            }
        """
        builder = OutcomeCurveBuilder(
            spec["table"],
            column=spec["column"],
            time_column=spec.get("time_column", "date"),
        )
        if spec.get("start_date"):
            builder.start(spec["start_date"])
        if spec.get("avg_value"):
            builder.avg_value(spec["avg_value"])
        if spec.get("concentration"):
            builder.concentration(spec["concentration"])
        if spec.get("n_periods"):
            builder.periods(spec["n_periods"])
        for period, value in (spec.get("anchors") or {}).items():
            builder.anchor(period, value)
        for period, factor in (spec.get("modifiers") or {}).items():
            builder.dip(period, factor=factor)
        return builder


# ---------------------------------------------------------------------------
# RateCurveBuilder
# ---------------------------------------------------------------------------

class RateCurveBuilder:
    """Fluent builder for :class:`~misata.schema.RateCurve`.

    Declare exact per-period rate targets for boolean or categorical columns.
    Start via :meth:`OutcomeCurveBuilder.rate`.

    Example::

        churn_curve = (
            OutcomeCurveBuilder.rate(
                "users", column="churned", time_column="signup_date"
            )
            .anchor("2024-Q1", 0.10)
            .anchor("2024-Q3", 0.18)   # churn worsens mid-year
            .anchor("2024-Q4", 0.12)   # retention campaign kicks in
            .interpolate(True)
            .build()
        )
    """

    def __init__(
        self,
        table: str,
        *,
        column: str,
        time_column: str = "date",
    ) -> None:
        self._table = table
        self._column = column
        self._time_column = time_column
        self._time_unit: str = "month"
        self._true_value: Any = True
        self._do_interpolate: bool = True
        self._description: Optional[str] = None
        self._anchors: Dict[int, float] = {}   # month → rate (0–1)
        self._n_periods: int = 12

    def time_unit(self, unit: str) -> "RateCurveBuilder":
        self._time_unit = unit
        return self

    def true_value(self, value: Any) -> "RateCurveBuilder":
        """Set the column value counted as the positive class (default ``True``)."""
        self._true_value = value
        return self

    def interpolate(self, flag: bool) -> "RateCurveBuilder":
        """Enable or disable rate interpolation between anchor points."""
        self._do_interpolate = flag
        return self

    def periods(self, n: int) -> "RateCurveBuilder":
        self._n_periods = n
        return self

    def describe(self, text: str) -> "RateCurveBuilder":
        self._description = text
        return self

    def anchor(
        self,
        period: Union[str, int],
        rate: float,
    ) -> "RateCurveBuilder":
        """Pin an exact positive-class rate for one period.

        Args:
            period: Period label — ``"YYYY-MM"``, ``"YYYY-Q1"``, or integer month.
            rate:   Target fraction in [0, 1] (e.g. ``0.03`` = 3% fraud).
        """
        if not 0.0 <= rate <= 1.0:
            raise ValueError(f"Rate must be in [0, 1], got {rate}")
        _, month = _parse_period_key(period)
        self._anchors[month] = float(rate)
        return self

    def build(self) -> "RateCurve":  # type: ignore[name-defined]
        """Interpolate anchors and return a :class:`~misata.schema.RateCurve`.

        Raises:
            ValueError: If no anchors have been set.
        """
        from misata.schema import RateCurve

        if not self._anchors:
            raise ValueError(
                "RateCurveBuilder requires at least one .anchor() call before .build()."
            )

        if self._do_interpolate and len(self._anchors) >= 2:
            months = np.arange(1, self._n_periods + 1)
            x_known = np.array(sorted(self._anchors), dtype=float)
            y_known = np.array([self._anchors[int(m)] for m in x_known], dtype=float)
            rates = np.clip(np.interp(months, x_known, y_known), 0.0, 1.0)
            rate_points = [
                {"period": f"{m:02d}", "rate": round(float(r), 6)}
                for m, r in zip(months, rates)
            ]
        else:
            rate_points = [
                {"period": f"{m:02d}", "rate": round(r, 6)}
                for m, r in sorted(self._anchors.items())
            ]

        return RateCurve(
            table=self._table,
            column=self._column,
            time_column=self._time_column,
            time_unit=self._time_unit,
            true_value=self._true_value,
            interpolate=self._do_interpolate,
            description=self._description,
            rate_points=rate_points,
        )
