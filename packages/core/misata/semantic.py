"""
Semantic column inference for automatic type detection.

This module detects column semantics from names and applies
the correct data generators, even if the LLM misses it.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from misata.schema import Column


# Semantic patterns: regex -> (type, distribution_params)
SEMANTIC_PATTERNS: List[Tuple[str, str, Dict[str, Any]]] = [
    # Email patterns
    (r"^email$|^e_?mail$|^user_?email$|^customer_?email$", "text", {"text_type": "email"}),

    # Name patterns
    (r"^name$|^full_?name$|^user_?name$|^customer_?name$|^display_?name$", "text", {"text_type": "name"}),
    (r"^first_?name$", "text", {"text_type": "name"}),
    (r"^last_?name$|^surname$|^family_?name$", "text", {"text_type": "name"}),

    # Phone patterns
    (r"^phone$|^phone_?number$|^mobile$|^cell$|^telephone$", "text", {"text_type": "phone"}),

    # Address patterns
    (r"^address$|^street$|^full_?address$|^billing_?address$|^shipping_?address$", "text", {"text_type": "address"}),

    # Company patterns
    (r"^company$|^company_?name$|^organization$|^org_?name$|^employer$", "text", {"text_type": "company"}),

    # URL patterns
    (r"^url$|^website$|^web_?url$|^link$|^profile_?url$", "text", {"text_type": "url"}),

    # Price/Money patterns (must be positive)
    (r"^price$|^cost$|^amount$|^fee$|^total$|^subtotal$|^tax$", "float", {"distribution": "uniform", "min": 0, "max": 1000, "decimals": 2}),
    (r"^mrr$|^arr$|^revenue$|^income$|^salary$|^wage$", "float", {"distribution": "uniform", "min": 0, "max": 100000, "decimals": 2}),

    # Age patterns
    (r"^age$|^user_?age$|^customer_?age$", "int", {"distribution": "uniform", "min": 18, "max": 80}),

    # Count patterns (non-negative integers)
    (r"^count$|^quantity$|^qty$|^num_|^number_of_|_count$", "int", {"distribution": "poisson", "lambda": 5, "min": 0}),

    # Percentage patterns
    (r"^percent|percentage$|_pct$|_percent$|^rate$", "float", {"distribution": "uniform", "min": 0, "max": 100, "decimals": 1}),

    # Duration patterns
    (r"^duration$|^duration_?minutes$|^duration_?hours$|^length$|^time_?spent$", "int", {"distribution": "uniform", "min": 1, "max": 120}),

    # Weight/Height patterns
    (r"^weight$|^weight_?kg$", "float", {"distribution": "normal", "mean": 70, "std": 15, "min": 30, "max": 200}),
    (r"^height$|^height_?cm$", "float", {"distribution": "normal", "mean": 170, "std": 10, "min": 140, "max": 220}),

    # Rating patterns
    (r"^rating$|^score$|^stars$|^review_?score$", "float", {"distribution": "uniform", "min": 1, "max": 5, "decimals": 1}),

    # Boolean patterns
    (r"^is_|^has_|^can_|^should_|^active$|^enabled$|^verified$|^confirmed$", "boolean", {"probability": 0.5}),

    # Status patterns
    (r"^status$|^state$|^order_?status$|^subscription_?status$", "categorical", {"choices": ["active", "inactive", "pending", "cancelled"]}),

    # Date patterns (already handled by type, but ensure proper params)
    (r"^date$|^created_?at$|^updated_?at$|^start_?date$|^end_?date$|_date$|_at$", "date", {"start": "2023-01-01", "end": "2024-12-31"}),
]


class SemanticInference:
    """
    Automatically infer and fix column semantics based on naming patterns.

    This acts as a safety net - if the LLM generates incorrect column types
    or parameters, semantic inference can fix them based on column names.
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize semantic inference.

        Args:
            strict_mode: If True, always override LLM; if False, only fix obvious errors
        """
        self.strict_mode = strict_mode
        self.patterns = [(re.compile(p, re.IGNORECASE), t, params)
                         for p, t, params in SEMANTIC_PATTERNS]

    def infer_column(self, column_name: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Infer column type and parameters from name.

        Args:
            column_name: Name of the column

        Returns:
            Tuple of (type, distribution_params) or None if no match
        """
        for pattern, col_type, params in self.patterns:
            if pattern.search(column_name):
                return (col_type, params.copy())
        return None

    def fix_column(self, column: Column, table_name: str = "") -> Column:
        """
        Fix a column's type/params based on semantic inference.

        Args:
            column: Column to potentially fix
            table_name: Name of the table (for context)

        Returns:
            Fixed column (or original if no fix needed)
        """
        inferred = self.infer_column(column.name)

        if inferred is None:
            return column

        inferred_type, inferred_params = inferred

        # Determine if we should apply the fix
        should_fix = False

        if self.strict_mode:
            # Always use inferred semantics
            should_fix = True
        else:
            # Only fix if current type seems wrong
            # Case 1: Column named "email" but type is not "text" with email
            if column.type == "text":
                current_text_type = column.distribution_params.get("text_type", "sentence")
                if current_text_type == "sentence":
                    # Default sentence generation - probably wrong for semantic names
                    should_fix = True

            # Case 2: Numeric column that could be negative but shouldn't be
            if column.type in ["int", "float"]:
                if "price" in column.name.lower() or "age" in column.name.lower():
                    if "min" not in column.distribution_params:
                        should_fix = True

        if should_fix:
            # Merge inferred params with existing (inferred takes precedence)
            merged_params = {**column.distribution_params, **inferred_params}
            return Column(
                name=column.name,
                type=inferred_type,
                distribution_params=merged_params,
                nullable=column.nullable,
                unique=column.unique
            )

        return column

    def fix_schema_columns(self, columns: Dict[str, List[Column]]) -> Dict[str, List[Column]]:
        """
        Fix all columns in a schema using semantic inference.

        Args:
            columns: Dict mapping table names to column lists

        Returns:
            Fixed columns dict
        """
        fixed = {}
        for table_name, cols in columns.items():
            fixed[table_name] = [self.fix_column(c, table_name) for c in cols]
        return fixed


# Convenience function
def apply_semantic_inference(columns: Dict[str, List[Column]], strict: bool = False) -> Dict[str, List[Column]]:
    """
    Apply semantic inference to fix column definitions.

    Args:
        columns: Schema columns to fix
        strict: If True, always apply semantic rules

    Returns:
        Fixed columns
    """
    inference = SemanticInference(strict_mode=strict)
    return inference.fix_schema_columns(columns)
