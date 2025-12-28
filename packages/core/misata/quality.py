"""
Data Quality Checker for Synthetic Data Validation.

This module validates generated synthetic data for:
- Distribution plausibility
- Referential integrity
- Temporal consistency
- Domain-specific rules
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import warnings


@dataclass
class QualityIssue:
    """Represents a single data quality issue."""
    severity: str  # "error", "warning", "info"
    category: str  # "distribution", "integrity", "temporal", "domain"
    table: str
    column: Optional[str]
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityReport:
    """Complete quality report for generated data."""
    score: float  # 0-100
    issues: List[QualityIssue]
    stats: Dict[str, Any]
    
    @property
    def passed(self) -> bool:
        """Returns True if no errors (warnings OK)."""
        return not any(i.severity == "error" for i in self.issues)
    
    def summary(self) -> str:
        """Human-readable summary."""
        errors = sum(1 for i in self.issues if i.severity == "error")
        warnings = sum(1 for i in self.issues if i.severity == "warning")
        return f"Quality Score: {self.score:.1f}/100 | Errors: {errors} | Warnings: {warnings}"


class DataQualityChecker:
    """
    Validate generated synthetic data for realism and correctness.
    
    Usage:
        checker = DataQualityChecker()
        report = checker.check_all(tables, relationships, schema)
        
        if not report.passed:
            print("Issues found:", report.issues)
    """
    
    # Domain-specific plausibility rules
    PLAUSIBILITY_RULES = {
        # Column name patterns -> (min, max, description)
        "age": (0, 120, "Human age"),
        "price": (0, 1_000_000, "Price"),
        "quantity": (0, 10_000, "Quantity"),
        "rating": (1, 5, "Rating"),
        "percentage": (0, 100, "Percentage"),
        "year": (1900, 2100, "Year"),
        "month": (1, 12, "Month"),
        "day": (1, 31, "Day"),
        "hour": (0, 23, "Hour"),
        "minute": (0, 59, "Minute"),
        "score": (0, 100, "Score"),
        "count": (0, 1_000_000, "Count"),
        "duration": (0, 10_000, "Duration"),
    }
    
    def __init__(self, strict: bool = False):
        """
        Initialize the quality checker.
        
        Args:
            strict: If True, warnings become errors
        """
        self.strict = strict
        self.issues: List[QualityIssue] = []
    
    def _add_issue(
        self,
        severity: str,
        category: str,
        table: str,
        column: Optional[str],
        message: str,
        details: Optional[Dict] = None,
    ):
        """Add an issue to the list."""
        if self.strict and severity == "warning":
            severity = "error"
        
        self.issues.append(QualityIssue(
            severity=severity,
            category=category,
            table=table,
            column=column,
            message=message,
            details=details or {},
        ))
    
    def check_distribution_plausibility(
        self,
        df: "pd.DataFrame",
        table_name: str,
    ) -> None:
        """
        Check if numeric distributions are plausible for their domains.
        
        Args:
            df: DataFrame to check
            table_name: Name of the table
        """
        import pandas as pd
        import numpy as np
        
        for col in df.columns:
            col_lower = col.lower()
            
            # Check against plausibility rules
            for pattern, (min_val, max_val, description) in self.PLAUSIBILITY_RULES.items():
                if pattern in col_lower:
                    if pd.api.types.is_numeric_dtype(df[col]):
                        actual_min = df[col].min()
                        actual_max = df[col].max()
                        
                        if actual_min < min_val:
                            self._add_issue(
                                "warning", "distribution", table_name, col,
                                f"{description} column '{col}' has min {actual_min} < expected {min_val}",
                                {"actual_min": actual_min, "expected_min": min_val}
                            )
                        
                        if actual_max > max_val:
                            self._add_issue(
                                "warning", "distribution", table_name, col,
                                f"{description} column '{col}' has max {actual_max} > expected {max_val}",
                                {"actual_max": actual_max, "expected_max": max_val}
                            )
                    break
            
            # Check for all-null columns
            if df[col].isna().all():
                self._add_issue(
                    "error", "distribution", table_name, col,
                    f"Column '{col}' is entirely NULL",
                )
            
            # Check for zero variance (all same value)
            if pd.api.types.is_numeric_dtype(df[col]) and df[col].std() == 0:
                self._add_issue(
                    "warning", "distribution", table_name, col,
                    f"Column '{col}' has zero variance (all values identical)",
                    {"value": df[col].iloc[0]}
                )
    
    def check_referential_integrity(
        self,
        tables: Dict[str, "pd.DataFrame"],
        relationships: List[Any],
    ) -> None:
        """
        Verify all foreign key references are valid.
        
        Args:
            tables: Dict of table_name -> DataFrame
            relationships: List of Relationship objects
        """
        for rel in relationships:
            parent_table = rel.parent_table
            child_table = rel.child_table
            parent_key = rel.parent_key
            child_key = rel.child_key
            
            if parent_table not in tables:
                self._add_issue(
                    "error", "integrity", child_table, child_key,
                    f"Parent table '{parent_table}' not found for FK '{child_key}'",
                )
                continue
            
            if child_table not in tables:
                continue  # Child table might not exist yet
            
            parent_df = tables[parent_table]
            child_df = tables[child_table]
            
            if parent_key not in parent_df.columns:
                self._add_issue(
                    "error", "integrity", parent_table, parent_key,
                    f"Parent key '{parent_key}' not found in table '{parent_table}'",
                )
                continue
            
            if child_key not in child_df.columns:
                self._add_issue(
                    "error", "integrity", child_table, child_key,
                    f"Child key '{child_key}' not found in table '{child_table}'",
                )
                continue
            
            # Check for orphaned records
            parent_ids = set(parent_df[parent_key].dropna().unique())
            child_ids = set(child_df[child_key].dropna().unique())
            orphans = child_ids - parent_ids
            
            if orphans:
                orphan_pct = len(orphans) / len(child_ids) * 100
                self._add_issue(
                    "error" if orphan_pct > 1 else "warning",
                    "integrity", child_table, child_key,
                    f"{len(orphans)} orphaned FK values ({orphan_pct:.1f}%) in '{child_key}' -> '{parent_table}.{parent_key}'",
                    {"orphan_count": len(orphans), "orphan_pct": orphan_pct}
                )
    
    def check_temporal_consistency(
        self,
        df: "pd.DataFrame",
        table_name: str,
    ) -> None:
        """
        Ensure temporal columns are consistent.
        
        Checks:
        - created_at < updated_at
        - start_date < end_date
        - birth_date in past
        """
        import pandas as pd
        
        date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
        
        # Check created < updated
        if "created_at" in date_cols and "updated_at" in date_cols:
            violations = (df["created_at"] > df["updated_at"]).sum()
            if violations > 0:
                self._add_issue(
                    "error", "temporal", table_name, "created_at",
                    f"{violations} rows have created_at > updated_at",
                    {"violation_count": violations}
                )
        
        # Check start < end
        if "start_date" in date_cols and "end_date" in date_cols:
            violations = (df["start_date"] > df["end_date"]).sum()
            if violations > 0:
                self._add_issue(
                    "error", "temporal", table_name, "start_date",
                    f"{violations} rows have start_date > end_date",
                    {"violation_count": violations}
                )
        
        # Check birth_date is in past
        if "birth_date" in date_cols or "date_of_birth" in date_cols:
            col = "birth_date" if "birth_date" in date_cols else "date_of_birth"
            future_births = (df[col] > pd.Timestamp.now()).sum()
            if future_births > 0:
                self._add_issue(
                    "error", "temporal", table_name, col,
                    f"{future_births} rows have birth_date in the future",
                    {"violation_count": future_births}
                )
    
    def check_all(
        self,
        tables: Dict[str, "pd.DataFrame"],
        relationships: Optional[List[Any]] = None,
        schema: Optional[Any] = None,
    ) -> QualityReport:
        """
        Run all quality checks and generate a report.
        
        Args:
            tables: Dict of table_name -> DataFrame
            relationships: Optional list of Relationship objects
            schema: Optional SchemaConfig for additional checks
            
        Returns:
            QualityReport with score and issues
        """
        self.issues = []  # Reset
        
        # Check each table
        for table_name, df in tables.items():
            self.check_distribution_plausibility(df, table_name)
            self.check_temporal_consistency(df, table_name)
        
        # Check referential integrity
        if relationships:
            self.check_referential_integrity(tables, relationships)
        
        # Calculate score
        base_score = 100
        for issue in self.issues:
            if issue.severity == "error":
                base_score -= 10
            elif issue.severity == "warning":
                base_score -= 3
            else:
                base_score -= 1
        
        score = max(0, min(100, base_score))
        
        # Gather stats
        stats = {
            "tables_checked": len(tables),
            "total_rows": sum(len(df) for df in tables.values()),
            "total_columns": sum(len(df.columns) for df in tables.values()),
            "error_count": sum(1 for i in self.issues if i.severity == "error"),
            "warning_count": sum(1 for i in self.issues if i.severity == "warning"),
        }
        
        return QualityReport(
            score=score,
            issues=self.issues.copy(),
            stats=stats,
        )


def check_quality(tables: Dict[str, "pd.DataFrame"], **kwargs) -> QualityReport:
    """Convenience function for quick quality checks."""
    checker = DataQualityChecker()
    return checker.check_all(tables, **kwargs)
