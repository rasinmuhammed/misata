"""
Data validation layer for pre-generation schema checks and post-generation quality checks.

Pre-generation: validate_schema() catches mis-configured SchemaConfig objects before any
data is written, surfacing every problem in one human-readable error instead of a raw
Pydantic stack trace or a mid-generation crash.

Post-generation: DataValidator / StreamingDataValidator check referential integrity,
distribution plausibility, and exact outcome-curve targets after data is produced.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Pre-generation schema validation
# ---------------------------------------------------------------------------

class SchemaValidationError(Exception):
    """Raised when a SchemaConfig fails pre-generation checks.

    The message lists every problem found so users can fix them all in one go
    rather than discovering them one by one during generation.
    """

    def __init__(self, issues: List[str]) -> None:
        self.issues = issues
        bullet_list = "\n".join(f"  • {issue}" for issue in issues)
        super().__init__(f"Schema has {len(issues)} issue(s):\n{bullet_list}")


def validate_schema(schema: Any) -> None:
    """Validate a SchemaConfig before generation starts.

    Checks structural correctness and semantic consistency that Pydantic's
    field-level validators cannot catch (e.g. cross-field constraints, graph
    cycles, probability sums).

    Raises:
        SchemaValidationError: if any issues are found (all issues reported at once).
    """
    issues: List[str] = []
    table_names = {t.name for t in schema.tables}
    column_map: Dict[str, set] = {
        t.name: {c.name for c in schema.get_columns(t.name)}
        for t in schema.tables
    }

    # 1. Duplicate table names
    seen_table_names: set = set()
    for t in schema.tables:
        if t.name in seen_table_names:
            issues.append(f"Duplicate table name: '{t.name}'")
        seen_table_names.add(t.name)

    # 2. FK columns must have a backing Relationship
    rel_child_keys = {
        (r.child_table, r.child_key) for r in schema.relationships
    }
    for t in schema.tables:
        for col in schema.get_columns(t.name):
            if col.type == "foreign_key" and (t.name, col.name) not in rel_child_keys:
                issues.append(
                    f"Column '{t.name}.{col.name}' is type 'foreign_key' but has no "
                    f"matching Relationship with child_table='{t.name}', child_key='{col.name}'"
                )

    # 4. Categorical probabilities must sum to ~1.0
    for t in schema.tables:
        for col in schema.get_columns(t.name):
            probs = col.distribution_params.get("probabilities")
            choices = col.distribution_params.get("choices")
            if probs is not None and choices is not None:
                total = sum(probs)
                if abs(total - 1.0) > 0.02:
                    issues.append(
                        f"Column '{t.name}.{col.name}' probabilities sum to {total:.4f} "
                        f"(expected 1.0 ± 0.02)"
                    )
                if len(probs) != len(choices):
                    issues.append(
                        f"Column '{t.name}.{col.name}' has {len(choices)} choices but "
                        f"{len(probs)} probabilities — lengths must match"
                    )

    # 5. Outcome curves must reference existing tables and columns
    for curve in getattr(schema, "outcome_curves", []):
        if curve.table not in table_names:
            issues.append(
                f"OutcomeCurve references unknown table '{curve.table}'"
            )
            continue
        cols = column_map[curve.table]
        if curve.column not in cols:
            issues.append(
                f"OutcomeCurve references unknown column '{curve.table}.{curve.column}'"
            )
        if curve.time_column and curve.time_column not in cols:
            issues.append(
                f"OutcomeCurve references unknown time_column '{curve.table}.{curve.time_column}'"
            )

    # 6. Events must reference existing tables and columns
    for event in getattr(schema, "events", []):
        if event.table not in table_names:
            issues.append(
                f"ScenarioEvent '{getattr(event, 'name', '?')}' references unknown table '{event.table}'"
            )
            continue
        if event.column not in column_map[event.table]:
            issues.append(
                f"ScenarioEvent '{getattr(event, 'name', '?')}' references unknown column "
                f"'{event.table}.{event.column}'"
            )

    # 7. Detect cycles in the relationship graph (topological sort check)
    # Build adjacency: parent → children
    adj: Dict[str, List[str]] = {t.name: [] for t in schema.tables}
    for r in schema.relationships:
        if r.parent_table in adj:
            adj[r.parent_table].append(r.child_table)

    visited: set = set()
    in_stack: set = set()

    def _has_cycle(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        for neighbour in adj.get(node, []):
            if neighbour not in visited:
                if _has_cycle(neighbour):
                    return True
            elif neighbour in in_stack:
                return True
        in_stack.discard(node)
        return False

    for table_name in list(adj.keys()):
        if table_name not in visited:
            if _has_cycle(table_name):
                issues.append(
                    "Circular relationship detected in schema — topological sort will fail during generation"
                )
                break  # one message is enough

    if issues:
        raise SchemaValidationError(issues)

import numpy as np
import pandas as pd

from misata.engines import FactEngine


class Severity(Enum):
    """Validation issue severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ValidationIssue:
    """A single validation issue found in the data."""
    severity: Severity
    table: str
    column: Optional[str]
    message: str
    affected_rows: int = 0
    sample_values: List[Any] = field(default_factory=list)

    def __str__(self):
        severity_icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}[self.severity.value]
        col = f".{self.column}" if self.column else ""
        return f"{severity_icon} [{self.table}{col}] {self.message} ({self.affected_rows} rows)"


@dataclass
class ValidationReport:
    """Complete validation report for generated data."""
    issues: List[ValidationIssue] = field(default_factory=list)
    tables_checked: int = 0
    columns_checked: int = 0
    total_rows: int = 0

    @property
    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARNING for i in self.issues)

    @property
    def is_clean(self) -> bool:
        return len(self.issues) == 0

    def summary(self) -> str:
        """Get a summary of the validation report."""
        errors = sum(1 for i in self.issues if i.severity == Severity.ERROR)
        warnings = sum(1 for i in self.issues if i.severity == Severity.WARNING)
        info = sum(1 for i in self.issues if i.severity == Severity.INFO)

        lines = [
            "=" * 50,
            "DATA VALIDATION REPORT",
            "=" * 50,
            f"Tables checked: {self.tables_checked}",
            f"Columns checked: {self.columns_checked}",
            f"Total rows: {self.total_rows:,}",
            "-" * 50,
            f"❌ Errors: {errors}",
            f"⚠️ Warnings: {warnings}",
            f"ℹ️ Info: {info}",
            "-" * 50,
        ]

        if self.is_clean:
            lines.append("✅ All validations passed!")
        else:
            lines.append("Issues found:")
            for issue in self.issues:
                lines.append(f"  {issue}")

        lines.append("=" * 50)
        return "\n".join(lines)


class DataValidator:
    """
    Validates generated data for quality and accuracy.
    """

    def __init__(
        self,
        tables: Dict[str, pd.DataFrame],
        schema_config: Optional[Any] = None,
    ):
        """
        Initialize validator with generated tables.

        Args:
            tables: Dict mapping table name to DataFrame
            schema_config: Optional schema config for relationship checking
        """
        self.tables = tables
        self.schema_config = schema_config
        self.issues: List[ValidationIssue] = []

    def validate_all(self) -> ValidationReport:
        """
        Run all validation checks.

        Returns:
            Complete validation report
        """
        self.issues = []

        for table_name, df in self.tables.items():
            self._validate_table(table_name, df)

        # Validate referential integrity
        self._validate_referential_integrity()
        self._validate_outcome_curves()

        return ValidationReport(
            issues=self.issues,
            tables_checked=len(self.tables),
            columns_checked=sum(len(df.columns) for df in self.tables.values()),
            total_rows=sum(len(df) for df in self.tables.values()),
        )

    def _validate_table(self, table_name: str, df: pd.DataFrame) -> None:
        """Validate a single table."""
        for col in df.columns:
            self._validate_column(table_name, df, col)

    def _validate_column(self, table_name: str, df: pd.DataFrame, col: str) -> None:
        """Validate a single column."""
        col.lower()
        values = df[col]

        # Check for nulls
        null_count = values.isna().sum()
        if null_count > 0:
            self.issues.append(ValidationIssue(
                severity=Severity.INFO,
                table=table_name,
                column=col,
                message=f"Contains {null_count} null values",
                affected_rows=null_count,
            ))

        # Numeric column checks
        if pd.api.types.is_numeric_dtype(values):
            self._validate_numeric_column(table_name, col, values)

        # Date column checks
        if pd.api.types.is_datetime64_any_dtype(values):
            self._validate_date_column(table_name, col, values)

        # String column checks
        if pd.api.types.is_string_dtype(values) or pd.api.types.is_object_dtype(values):
            self._validate_string_column(table_name, col, values)

    def _validate_numeric_column(self, table_name: str, col: str, values: pd.Series) -> None:
        """Validate numeric columns."""
        col_lower = col.lower()

        # Check for negative values in columns that should be positive
        positive_patterns = ['price', 'cost', 'amount', 'age', 'quantity', 'count',
                             'duration', 'weight', 'height', 'salary', 'revenue']

        if any(p in col_lower for p in positive_patterns):
            negative_count = (values < 0).sum()
            if negative_count > 0:
                self.issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    table=table_name,
                    column=col,
                    message=f"Contains {negative_count} negative values (should be positive)",
                    affected_rows=negative_count,
                    sample_values=values[values < 0].head(5).tolist(),
                ))

        # Check for unreasonable ages
        if 'age' in col_lower:
            invalid_ages = ((values < 0) | (values > 150)).sum()
            if invalid_ages > 0:
                self.issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    table=table_name,
                    column=col,
                    message=f"Contains {invalid_ages} unrealistic age values (< 0 or > 150)",
                    affected_rows=invalid_ages,
                ))

        # Check for unreasonable prices
        if 'price' in col_lower or 'cost' in col_lower:
            very_high = (values > 1000000).sum()
            if very_high > 0:
                self.issues.append(ValidationIssue(
                    severity=Severity.INFO,
                    table=table_name,
                    column=col,
                    message=f"Contains {very_high} values over $1M",
                    affected_rows=very_high,
                ))

    def _validate_date_column(self, table_name: str, col: str, values: pd.Series) -> None:
        """Validate date columns."""
        # Check for dates too far in the future
        future_cutoff = pd.Timestamp.now() + pd.Timedelta(days=365*5)
        far_future = (values > future_cutoff).sum()
        if far_future > 0:
            self.issues.append(ValidationIssue(
                severity=Severity.WARNING,
                table=table_name,
                column=col,
                message=f"Contains {far_future} dates more than 5 years in the future",
                affected_rows=far_future,
            ))

        # Check for dates too far in the past
        past_cutoff = pd.Timestamp('1900-01-01')
        far_past = (values < past_cutoff).sum()
        if far_past > 0:
            self.issues.append(ValidationIssue(
                severity=Severity.ERROR,
                table=table_name,
                column=col,
                message=f"Contains {far_past} dates before 1900",
                affected_rows=far_past,
            ))

    def _validate_string_column(self, table_name: str, col: str, values: pd.Series) -> None:
        """Validate string columns."""
        col_lower = col.lower()

        # Check for email format
        if 'email' in col_lower:
            # Simple email check - contains @
            invalid_emails = (~values.astype(str).str.contains('@', na=False)).sum()
            if invalid_emails > 0:
                self.issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    table=table_name,
                    column=col,
                    message=f"Contains {invalid_emails} invalid email addresses",
                    affected_rows=invalid_emails,
                ))

        # Check for empty strings
        empty_count = (values.astype(str).str.strip() == '').sum()
        if empty_count > 0:
            self.issues.append(ValidationIssue(
                severity=Severity.WARNING,
                table=table_name,
                column=col,
                message=f"Contains {empty_count} empty strings",
                affected_rows=empty_count,
            ))

    def _validate_referential_integrity(self) -> None:
        """Validate foreign key relationships."""
        if not self.schema_config:
            return

        for rel in self.schema_config.relationships:
            if rel.parent_table not in self.tables or rel.child_table not in self.tables:
                continue

            parent_df = self.tables[rel.parent_table]
            child_df = self.tables[rel.child_table]

            if rel.parent_key not in parent_df.columns or rel.child_key not in child_df.columns:
                continue

            parent_ids = set(parent_df[rel.parent_key].dropna())
            child_fks = child_df[rel.child_key].dropna()

            orphans = ~child_fks.isin(parent_ids)
            orphan_count = orphans.sum()

            if orphan_count > 0:
                self.issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    table=rel.child_table,
                    column=rel.child_key,
                    message=f"Contains {orphan_count} orphan references (FK not found in {rel.parent_table})",
                    affected_rows=orphan_count,
                ))

    def _validate_outcome_curves(self) -> None:
        """Validate exact outcome curves against generated aggregates."""
        if not self.schema_config or not getattr(self.schema_config, "outcome_curves", None):
            return

        engine = FactEngine()

        for table in self.schema_config.tables:
            table_name = table.name
            if table_name not in self.tables:
                continue

            curves = [
                curve
                for curve in self.schema_config.outcome_curves
                if getattr(curve, "table", None) == table_name
                and engine.curve_has_exact_targets(curve)
            ]
            if not curves:
                continue

            plan = engine.build_plan(table, self.schema_config.get_columns(table_name), curves)
            if plan is None:
                continue

            df = self.tables[table_name]
            if plan.time_column not in df.columns:
                self.issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    table=table_name,
                    column=plan.time_column,
                    message="Missing time column required for outcome curve validation",
                    affected_rows=len(df),
                ))
                continue

            timestamps = pd.to_datetime(df[plan.time_column], errors="coerce")
            for curve in plan.curves:
                if curve.column not in df.columns:
                    self.issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        table=table_name,
                        column=curve.column,
                        message="Missing constrained column required for outcome curve validation",
                        affected_rows=len(df),
                    ))
                    continue

                actual_values: List[float] = []
                numeric_series = pd.to_numeric(df[curve.column], errors="coerce").fillna(0)

                for bucket in plan.buckets:
                    mask = (timestamps >= bucket.start) & (timestamps < bucket.end)
                    actual_values.append(float(numeric_series.loc[mask].sum()))

                tolerance = 0.01 if self._column_decimals(table_name, curve.column) else 0.0
                mismatches = [
                    (expected, actual)
                    for expected, actual in zip(curve.targets, actual_values)
                    if abs(expected - actual) > tolerance
                ]
                if mismatches:
                    sample_expected, sample_actual = mismatches[0]
                    self.issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        table=table_name,
                        column=curve.column,
                        message=(
                            "Outcome curve aggregate mismatch. "
                            f"Expected {sample_expected:.2f}, got {sample_actual:.2f} in at least one bucket"
                        ),
                        affected_rows=len(mismatches),
                    ))

    def _column_decimals(self, table_name: str, column_name: str) -> int:
        """Get numeric precision for a schema column."""
        if not self.schema_config:
            return 2

        for column in self.schema_config.get_columns(table_name):
            if column.name != column_name:
                continue
            if column.type == "int":
                return 0
            return int(column.distribution_params.get("decimals", 2))

        return 2


def validate_data(
    tables: Dict[str, pd.DataFrame],
    schema_config: Optional[Any] = None,
) -> ValidationReport:
    """
    Quick validation of generated data.

    Args:
        tables: Generated tables
        schema_config: Optional schema for FK validation

    Returns:
        Validation report
    """
    validator = DataValidator(tables, schema_config)
    return validator.validate_all()


class StreamingDataValidator:
    """
    Streaming validator for batch generation paths.

    Keeps exact validation for scalar checks, FK integrity, and exact outcome
    curves without materializing all tables in memory.
    """

    POSITIVE_PATTERNS = ['price', 'cost', 'amount', 'age', 'quantity', 'count',
                         'duration', 'weight', 'height', 'salary', 'revenue']

    def __init__(self, schema_config: Optional[Any] = None):
        self.schema_config = schema_config
        self._issue_counts: Dict[tuple[Any, str, Optional[str], str], int] = defaultdict(int)
        self._issue_samples: Dict[tuple[Any, str, Optional[str], str], List[Any]] = defaultdict(list)
        self._tables_seen: set[str] = set()
        self._columns_seen: set[tuple[str, str]] = set()
        self._total_rows = 0
        self._parent_ids: Dict[tuple[str, str], set[Any]] = defaultdict(set)
        self._outcome_plans: Dict[str, Any] = {}
        self._outcome_actuals: Dict[tuple[str, str], np.ndarray] = {}
        self._missing_outcome_columns: set[tuple[str, str]] = set()

        if self.schema_config:
            self._initialize_outcome_plans()

    def consume(self, table_name: str, df: pd.DataFrame) -> None:
        """Consume one generated batch."""
        self._tables_seen.add(table_name)
        self._total_rows += len(df)
        for column in df.columns:
            self._columns_seen.add((table_name, column))
            self._validate_column(table_name, column, df[column])

        self._accumulate_parent_ids(table_name, df)
        self._validate_child_relationships(table_name, df)
        self._accumulate_outcome_curves(table_name, df)

    def finalize(self) -> ValidationReport:
        """Build a ValidationReport from all consumed batches."""
        self._finalize_outcome_curves()

        issues = []
        for (severity, table_name, column_name, template), count in self._issue_counts.items():
            message = template.format(count=count)
            issues.append(
                ValidationIssue(
                    severity=severity,
                    table=table_name,
                    column=column_name,
                    message=message,
                    affected_rows=count,
                    sample_values=self._issue_samples.get((severity, table_name, column_name, template), [])[:5],
                )
            )

        return ValidationReport(
            issues=issues,
            tables_checked=len(self._tables_seen),
            columns_checked=len(self._columns_seen),
            total_rows=self._total_rows,
        )

    def _add_issue(
        self,
        severity: Severity,
        table_name: str,
        column_name: Optional[str],
        template: str,
        count: int,
        sample_values: Optional[List[Any]] = None,
    ) -> None:
        if count <= 0:
            return
        key = (severity, table_name, column_name, template)
        self._issue_counts[key] += int(count)
        if sample_values:
            existing = self._issue_samples[key]
            remaining = max(0, 5 - len(existing))
            if remaining:
                existing.extend(sample_values[:remaining])

    def _validate_column(self, table_name: str, column_name: str, values: pd.Series) -> None:
        null_count = int(values.isna().sum())
        self._add_issue(
            Severity.INFO,
            table_name,
            column_name,
            "Contains {count} null values",
            null_count,
        )

        if pd.api.types.is_numeric_dtype(values):
            self._validate_numeric_column(table_name, column_name, values)

        if pd.api.types.is_datetime64_any_dtype(values):
            self._validate_date_column(table_name, column_name, values)

        if pd.api.types.is_string_dtype(values) or pd.api.types.is_object_dtype(values):
            self._validate_string_column(table_name, column_name, values)

    def _validate_numeric_column(self, table_name: str, column_name: str, values: pd.Series) -> None:
        column_lower = column_name.lower()
        if any(pattern in column_lower for pattern in self.POSITIVE_PATTERNS):
            invalid = values < 0
            self._add_issue(
                Severity.ERROR,
                table_name,
                column_name,
                "Contains {count} negative values (should be positive)",
                int(invalid.sum()),
                values[invalid].head(5).tolist(),
            )

        if 'age' in column_lower:
            invalid_ages = (values < 0) | (values > 150)
            self._add_issue(
                Severity.WARNING,
                table_name,
                column_name,
                "Contains {count} unrealistic age values (< 0 or > 150)",
                int(invalid_ages.sum()),
            )

        if 'price' in column_lower or 'cost' in column_lower:
            high_values = values > 1000000
            self._add_issue(
                Severity.INFO,
                table_name,
                column_name,
                "Contains {count} values over $1M",
                int(high_values.sum()),
            )

    def _validate_date_column(self, table_name: str, column_name: str, values: pd.Series) -> None:
        future_cutoff = pd.Timestamp.now() + pd.Timedelta(days=365 * 5)
        past_cutoff = pd.Timestamp('1900-01-01')
        self._add_issue(
            Severity.WARNING,
            table_name,
            column_name,
            "Contains {count} dates more than 5 years in the future",
            int((values > future_cutoff).sum()),
        )
        self._add_issue(
            Severity.ERROR,
            table_name,
            column_name,
            "Contains {count} dates before 1900",
            int((values < past_cutoff).sum()),
        )

    def _validate_string_column(self, table_name: str, column_name: str, values: pd.Series) -> None:
        column_lower = column_name.lower()
        as_text = values.astype(str)

        if 'email' in column_lower:
            invalid = ~as_text.str.contains('@', na=False)
            self._add_issue(
                Severity.ERROR,
                table_name,
                column_name,
                "Contains {count} invalid email addresses",
                int(invalid.sum()),
            )

        empty = as_text.str.strip() == ''
        self._add_issue(
            Severity.WARNING,
            table_name,
            column_name,
            "Contains {count} empty strings",
            int(empty.sum()),
        )

    def _accumulate_parent_ids(self, table_name: str, df: pd.DataFrame) -> None:
        if not self.schema_config:
            return

        for relationship in self.schema_config.relationships:
            if relationship.parent_table != table_name or relationship.parent_key not in df.columns:
                continue
            self._parent_ids[(relationship.parent_table, relationship.parent_key)].update(df[relationship.parent_key].dropna().tolist())

    def _validate_child_relationships(self, table_name: str, df: pd.DataFrame) -> None:
        if not self.schema_config:
            return

        for relationship in self.schema_config.relationships:
            if relationship.child_table != table_name:
                continue
            if relationship.child_key not in df.columns:
                continue

            parent_ids = self._parent_ids.get((relationship.parent_table, relationship.parent_key), set())
            child_values = df[relationship.child_key].dropna()
            orphan_count = int((~child_values.isin(parent_ids)).sum())
            self._add_issue(
                Severity.ERROR,
                relationship.child_table,
                relationship.child_key,
                f"Contains {{count}} orphan references (FK not found in {relationship.parent_table})",
                orphan_count,
            )

    def _initialize_outcome_plans(self) -> None:
        if not self.schema_config or not getattr(self.schema_config, "outcome_curves", None):
            return

        engine = FactEngine()
        for table in self.schema_config.tables:
            table_name = table.name
            curves = [
                curve
                for curve in self.schema_config.outcome_curves
                if getattr(curve, "table", None) == table_name
                and engine.curve_has_exact_targets(curve)
            ]
            if not curves:
                continue
            plan = engine.build_plan(table, self.schema_config.get_columns(table_name), curves)
            if plan is None:
                continue
            self._outcome_plans[table_name] = plan
            for curve in plan.curves:
                self._outcome_actuals[(table_name, curve.column)] = np.zeros(len(plan.buckets), dtype=float)

    def _accumulate_outcome_curves(self, table_name: str, df: pd.DataFrame) -> None:
        if table_name not in self._outcome_plans:
            return

        plan = self._outcome_plans[table_name]
        if plan.time_column not in df.columns:
            key = (table_name, plan.time_column)
            if key not in self._missing_outcome_columns:
                self._missing_outcome_columns.add(key)
                self._add_issue(
                    Severity.ERROR,
                    table_name,
                    plan.time_column,
                    "Missing time column required for outcome curve validation",
                    len(df),
                )
            return

        timestamps = pd.to_datetime(df[plan.time_column], errors="coerce")
        for curve in plan.curves:
            if curve.column not in df.columns:
                key = (table_name, curve.column)
                if key not in self._missing_outcome_columns:
                    self._missing_outcome_columns.add(key)
                    self._add_issue(
                        Severity.ERROR,
                        table_name,
                        curve.column,
                        "Missing constrained column required for outcome curve validation",
                        len(df),
                    )
                continue

            numeric_values = pd.to_numeric(df[curve.column], errors="coerce").fillna(0)
            aggregates = self._outcome_actuals[(table_name, curve.column)]
            for bucket_index, bucket in enumerate(plan.buckets):
                mask = (timestamps >= bucket.start) & (timestamps < bucket.end)
                aggregates[bucket_index] += float(numeric_values.loc[mask].sum())

    def _finalize_outcome_curves(self) -> None:
        for table_name, plan in self._outcome_plans.items():
            for curve in plan.curves:
                actual_values = self._outcome_actuals[(table_name, curve.column)]
                tolerance = 0.01 if self._column_decimals(table_name, curve.column) else 0.0
                mismatches = [
                    (expected, actual)
                    for expected, actual in zip(curve.targets, actual_values)
                    if abs(expected - actual) > tolerance
                ]
                if not mismatches:
                    continue
                expected, actual = mismatches[0]
                self._add_issue(
                    Severity.ERROR,
                    table_name,
                    curve.column,
                    (
                        "Outcome curve aggregate mismatch. "
                        f"Expected {expected:.2f}, got {actual:.2f} in at least one bucket"
                    ),
                    len(mismatches),
                )

    def _column_decimals(self, table_name: str, column_name: str) -> int:
        if not self.schema_config:
            return 2

        for column in self.schema_config.get_columns(table_name):
            if column.name != column_name:
                continue
            if column.type == "int":
                return 0
            return int(column.distribution_params.get("decimals", 2))
        return 2
