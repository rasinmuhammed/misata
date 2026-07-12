"""
Semantic column inference for automatic type detection.

This module detects column semantics from names and applies
the correct data generators, even if the LLM misses it.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from misata.schema import Column


# Keys that indicate a caller explicitly shaped a numeric distribution. If any
# are present (or a non-default distribution is named), semantic inference must
# not override the column's range — the user's intent wins.
_MEANINGFUL_DIST_KEYS = frozenset({
    "mean", "std", "mu", "sigma", "scale", "lambda", "choices", "probabilities",
    "alpha", "a", "b", "min", "max", "quantiles", "rate", "depends_on",
    "control_points", "profiles",
})


def _has_explicit_distribution(params: Dict[str, Any]) -> bool:
    """True when params carry a user-specified distribution shape (not the bare
    auto-injected ``{"distribution": "normal"}`` default)."""
    if not params:
        return False
    if set(params) & _MEANINGFUL_DIST_KEYS:
        return True
    dist = params.get("distribution")
    return bool(dist) and dist != "normal"


# Column names whose values must never be negative — a `min: 0` floor is safe to
# add when the caller gave an explicit distribution but no min. Word-boundary
# matched so "list_price"/"total_revenue" qualify but "coverage"/"agenda" do not.
_NONNEGATIVE_NAME_RE = re.compile(
    r"(?:^|_)(price|cost|amount|fee|total|subtotal|tax|revenue|income|salary|"
    r"wage|mrr|arr|balance|payment|charge|budget|quantity|qty|count|age|"
    r"square_footage|sqft|footage|area|distance|weight|height|duration|"
    r"discount|deposit|premium|rent|value)(?:$|_)"
)


# Semantic patterns: regex -> (type, distribution_params)
SEMANTIC_PATTERNS: List[Tuple[str, str, Dict[str, Any]]] = [
    # Email patterns
    (r"^email$|^e_?mail$|^user_?email$|^customer_?email$", "text", {"text_type": "email"}),

    # Name patterns
    (r"^name$|^full_?name$|^user_?name$|^customer_?name$|^display_?name$", "text", {"text_type": "name"}),
    (r"^first_?name$", "text", {"text_type": "first_name"}),
    (r"^last_?name$|^surname$|^family_?name$", "text", {"text_type": "last_name"}),

    # Phone patterns
    (r"^phone$|^phone_?number$|^mobile$|^cell$|^telephone$", "text", {"text_type": "phone"}),

    # Locale-specific identity documents
    (r"^national_?id$|^ssn$|^cpf$|^aadhaar$|^aadhar$|^nid$|^tax_?id$", "text", {"text_type": "national_id"}),

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
    (r"^rating$|^score$|^stars$|^review_?score$", "float", {"min": 1, "max": 5, "decimals": 1}),

    # Boolean patterns
    (r"^is_|^has_|^can_|^should_|^active$|^enabled$|^verified$|^confirmed$", "boolean", {"probability": 0.5}),

    # Status patterns. NOTE: bare `state` is deliberately excluded — in a data
    # model it is far more often a geographic region (address forms) than an
    # order state, and the realism layer fills it with country-coherent
    # provinces/states. Order state should be named `status`/`order_status`.
    (r"^status$|^order_?status$|^subscription_?status$|^payment_?status$", "categorical", {"choices": ["active", "inactive", "pending", "cancelled"]}),

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

            # Case 2: Numeric column that could be negative but shouldn't be.
            # CRITICAL: never override a distribution the user/LLM explicitly
            # parameterised. A house price declared as normal(mean=500000) must
            # NOT be silently replaced by the generic uniform(0, 1000) prior —
            # that was the root cause of "senseless values" (e.g. $500k homes
            # priced at $1–$999). Semantic inference exists to help *bare*
            # columns (e.g. from DB introspection with no distribution), so we
            # only apply it when no explicit distribution shape is present.
            if column.type in ["int", "float"]:
                if not _has_explicit_distribution(column.distribution_params):
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

        # Non-negativity floor for money/quantity columns that carry an EXPLICIT
        # distribution but no `min`. This never changes the distribution, mean,
        # or max — it only adds `min: 0` so a wide normal (e.g. house price
        # normal(500000, 150000)) can't produce a negative value in its tail.
        if (
            column.type in ("int", "float")
            and "min" not in column.distribution_params
            and _has_explicit_distribution(column.distribution_params)
            and _NONNEGATIVE_NAME_RE.search(column.name.lower())
        ):
            floored = dict(column.distribution_params)
            floored["min"] = 0
            return Column(
                name=column.name,
                type=column.type,
                distribution_params=floored,
                nullable=column.nullable,
                unique=column.unique,
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
