"""
Pre-generation conformance preview — no rows generated.

The no-code UI calls this after the user has set up their schema and curves
to show them *what will be generated* (period targets, estimated row counts,
clamping warnings) before committing to a full generation run.

The preview is a pure planning step. It calls ``FactEngine.build_plan()``
internally and exposes the plan as structured, serialisable data suitable
for driving a chart or summary table in the UI.

Usage::

    import misata
    from misata import conformance_preview, OutcomeCurveBuilder

    schema = misata.parse("A SaaS company with 5k users")
    preview = conformance_preview(schema)

    print(preview.summary())
    # Conformance preview: SaaS Dataset
    # Outcome curves: 1
    # ...

    # Serialise for the UI
    chart_data = preview.to_dict()

    # Check before generation
    if preview.ame_achievable:
        tables = misata.generate_from_schema(schema)
    else:
        print("Warnings:", preview.warnings)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from misata.schema import SchemaConfig


@dataclass
class PeriodPreview:
    """Planned outcome for a single period bucket."""

    period: str
    """Human-readable period label (e.g. ``"2024-01"``)."""

    target: float
    """Exact aggregate target for this period."""

    est_rows: int
    """Estimated row count planned for this period (from FactEngine)."""

    rate: Optional[float] = None
    """Declared positive-class rate, if a RateCurve is attached."""


@dataclass
class CurvePreview:
    """Preview for a single OutcomeCurve."""

    table: str
    column: str
    time_column: str
    time_unit: str
    periods: List[PeriodPreview] = field(default_factory=list)
    ame_achievable: bool = True
    bounds_respected: bool = True
    """``False`` when a period target is infeasible under the column's declared
    min/max — the aggregate target takes precedence and the bound will be
    violated at generation time."""
    warnings: List[str] = field(default_factory=list)

    @property
    def total_target(self) -> float:
        return sum(p.target for p in self.periods)

    @property
    def total_rows(self) -> int:
        return sum(p.est_rows for p in self.periods)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table": self.table,
            "column": self.column,
            "time_column": self.time_column,
            "time_unit": self.time_unit,
            "ame_achievable": self.ame_achievable,
            "bounds_respected": self.bounds_respected,
            "total_target": self.total_target,
            "total_rows": self.total_rows,
            "periods": [
                {
                    "period": p.period,
                    "target": p.target,
                    "est_rows": p.est_rows,
                    **({"rate": p.rate} if p.rate is not None else {}),
                }
                for p in self.periods
            ],
            "warnings": self.warnings,
        }


@dataclass
class ConformancePreview:
    """Structured pre-generation planning report.

    Returned by :func:`conformance_preview`. Contains the full period plan
    for every outcome curve, estimated row counts, clamping warnings, and
    a top-level flag indicating whether AME = 0 is achievable.
    """

    schema_name: str
    curves: List[CurvePreview] = field(default_factory=list)
    global_warnings: List[str] = field(default_factory=list)

    @property
    def ame_achievable(self) -> bool:
        """``True`` if all curves can reach AME = 0 with current settings."""
        return all(c.ame_achievable for c in self.curves)

    @property
    def bounds_respected(self) -> bool:
        """``True`` if no curve will need to violate a declared column min/max."""
        return all(c.bounds_respected for c in self.curves)

    @property
    def warnings(self) -> List[str]:
        """Merged list of all warnings across curves and global checks."""
        all_warnings = list(self.global_warnings)
        for c in self.curves:
            all_warnings.extend(c.warnings)
        return all_warnings

    def summary(self) -> str:
        """Return a human-readable multi-line summary."""
        lines = [
            f"Conformance preview: {self.schema_name}",
            f"Outcome curves: {len(self.curves)}",
            f"AME achievable: {'Yes ✓' if self.ame_achievable else 'No ✗ — see warnings'}",
        ]
        for c in self.curves:
            lines.append(
                f"\n  {c.table}.{c.column} over {c.time_column} ({c.time_unit})"
            )
            lines.append(
                f"    Total target: {c.total_target:,.2f}  |  "
                f"Est. rows: {c.total_rows:,}"
            )
            for p in c.periods[:6]:
                lines.append(
                    f"    {p.period:12s}  target={p.target:>12,.2f}  "
                    f"rows≈{p.est_rows:>6,}"
                )
            if len(c.periods) > 6:
                lines.append(f"    … ({len(c.periods) - 6} more periods)")
            for w in c.warnings:
                lines.append(f"    ⚠ {w}")
        if self.global_warnings:
            lines.append("\nGlobal warnings:")
            for w in self.global_warnings:
                lines.append(f"  ⚠ {w}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-serialisable dict for the no-code UI."""
        return {
            "schema_name": self.schema_name,
            "ame_achievable": self.ame_achievable,
            "bounds_respected": self.bounds_respected,
            "warnings": self.warnings,
            "curves": [c.to_dict() for c in self.curves],
        }


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def conformance_preview(schema: "SchemaConfig") -> ConformancePreview:
    """Return a :class:`ConformancePreview` without generating any rows.

    Internally calls :meth:`~misata.engines.FactEngine.build_plan` for each
    outcome curve to derive the exact period plan (targets, row counts, clamp
    warnings). This is a read-only, zero-side-effect call.

    Args:
        schema: A :class:`~misata.schema.SchemaConfig` with one or more
                ``outcome_curves``. Schemas without curves return an empty
                :class:`ConformancePreview`.

    Returns:
        :class:`ConformancePreview` — structured planning data ready for
        chart rendering or programmatic inspection.

    Example::

        import misata
        from misata import conformance_preview, OutcomeCurveBuilder

        curve = (
            OutcomeCurveBuilder("orders", column="amount", time_column="order_date")
            .anchor("2024-01", 10_000)
            .anchor("2024-12", 120_000)
            .avg_value(75.0)
            .build()
        )
        schema = misata.parse("An ecommerce store with 5k orders")
        schema = OutcomeCurveBuilder.attach(schema, curve)

        preview = conformance_preview(schema)
        print(preview.summary())

        # Render in the UI
        chart_data = preview.to_dict()
    """
    import numpy as np
    from misata.engines import FactEngine

    engine = FactEngine()
    preview = ConformancePreview(schema_name=schema.name)

    if not getattr(schema, "outcome_curves", None):
        preview.global_warnings.append(
            "No outcome curves defined. Add at least one OutcomeCurve to enable "
            "conformance-checked generation."
        )
        return preview

    # Group curves by table
    tables_seen = {t.name: t for t in schema.tables}

    for curve in schema.outcome_curves:
        table = tables_seen.get(curve.table)
        if table is None:
            curve_preview = CurvePreview(
                table=curve.table,
                column=curve.column,
                time_column=curve.time_column,
                time_unit=curve.time_unit,
                ame_achievable=False,
                warnings=[
                    f"Table '{curve.table}' not found in schema — "
                    "curve cannot be executed."
                ],
            )
            preview.curves.append(curve_preview)
            continue

        if not engine.curve_has_exact_targets(curve):
            curve_preview = CurvePreview(
                table=curve.table,
                column=curve.column,
                time_column=curve.time_column,
                time_unit=curve.time_unit,
                ame_achievable=False,
                warnings=[
                    f"Curve on '{curve.table}.{curve.column}' has no exact targets "
                    "(value_mode='relative' or missing target_value). "
                    "Set value_mode='absolute' and provide target_value per period."
                ],
            )
            preview.curves.append(curve_preview)
            continue

        columns = schema.get_columns(curve.table)
        plan = engine.build_plan(table, columns, [curve])

        if plan is None:
            curve_preview = CurvePreview(
                table=curve.table,
                column=curve.column,
                time_column=curve.time_column,
                time_unit=curve.time_unit,
                ame_achievable=False,
                warnings=[
                    f"FactEngine could not build a plan for '{curve.table}.{curve.column}'. "
                    "Check that all curves on this table share the same time_column and time_unit."
                ],
            )
            preview.curves.append(curve_preview)
            continue

        # Build period previews from the resolved plan
        resolved = engine._resolve_curve(curve, columns)
        row_counts = plan.row_counts
        period_previews: List[PeriodPreview] = []
        curve_warnings: List[str] = []

        # Declared min/max feasibility: a period with n rows and target T can
        # keep every value in [min, max] only when min·n ≤ T ≤ max·n. The
        # engine gives the aggregate target precedence, so flag the sacrifice
        # here — before any rows are generated.
        column_map = {getattr(c, "name", None): c for c in columns}
        bound_conflicts = engine.bound_conflicts(plan, column_map)
        bounds_respected = not bound_conflicts
        for conflict in bound_conflicts:
            bound_value = (
                conflict["declared_min"] if conflict["sacrificed"] == "min"
                else conflict["declared_max"]
            )
            curve_warnings.append(
                f"Period '{conflict['period']}': target={conflict['target']:,.2f} over "
                f"{conflict['rows']} planned rows is infeasible under the declared "
                f"{conflict['sacrificed']}={bound_value:g} — the aggregate target takes "
                f"precedence and per-row values will violate the "
                f"{conflict['sacrificed']} bound. Widen the bound, adjust the target, "
                f"or tune min/max_transactions_per_period."
            )

        for bucket, target, est_rows in zip(
            resolved.buckets, resolved.targets, row_counts
        ):
            # Prop. 3 clamping check
            if resolved.avg_transaction_value and target > 0:
                ideal_rows = target / resolved.avg_transaction_value
                if ideal_rows > resolved.max_transactions_per_period:
                    curve_warnings.append(
                        f"Period '{bucket.label}': target={target:,.2f} requires "
                        f"≈{ideal_rows:.0f} rows but max_transactions_per_period="
                        f"{resolved.max_transactions_per_period} — per-row values "
                        f"will be inflated (Prop. 3 upper clamp). "
                        f"Raise max_transactions_per_period to avoid distortion."
                    )
                elif ideal_rows < resolved.min_transactions_per_period:
                    curve_warnings.append(
                        f"Period '{bucket.label}': target={target:,.2f} requires "
                        f"≈{ideal_rows:.0f} rows but min_transactions_per_period="
                        f"{resolved.min_transactions_per_period} — per-row values "
                        f"will be deflated (Prop. 3 lower clamp)."
                    )

            period_previews.append(
                PeriodPreview(
                    period=bucket.label.split(":", 1)[-1],
                    target=float(target),
                    est_rows=int(est_rows),
                )
            )

        curve_preview = CurvePreview(
            table=curve.table,
            column=curve.column,
            time_column=curve.time_column,
            time_unit=curve.time_unit,
            periods=period_previews,
            ame_achievable=True,
            bounds_respected=bounds_respected,
            warnings=curve_warnings,
        )
        preview.curves.append(curve_preview)

    return preview
