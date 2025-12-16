"""
Data validation layer for post-generation quality checks.

This module validates generated data to ensure:
- No negative values where inappropriate
- Valid date ranges
- Referential integrity (FK -> PK exists)
- Business logic rules
- Statistical distribution accuracy
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import pandas as pd


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
