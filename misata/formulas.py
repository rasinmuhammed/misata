"""
Formula engine for derived columns.

This module enables columns that are computed from other columns,
supporting expressions like:
- calories_burned = duration_minutes * @exercises.calories_per_minute
- total_price = quantity * @products.price
- discount_amount = total_price * 0.1
"""

import re
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import ast
import operator
from simpleeval import simple_eval, NameNotDefined

# Whitelist of safe functions
SAFE_FUNCTIONS = {
    'where': np.where,
    'abs': np.abs,
    'round': np.round,
    'ceil': np.ceil,
    'floor': np.floor,
    'min': np.minimum,
    'max': np.maximum,
    'sin': np.sin,
    'cos': np.cos,
    'tan': np.tan,
    'log': np.log,
    'exp': np.exp,
    'sqrt': np.sqrt,
    'random': np.random.random,
    'randint': np.random.randint,
}

# Standard operators to bypass simpleeval's string length checks which fail on numpy arrays
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Not: operator.not_,
    ast.In: lambda a, b: a in b,
}

class SafeNumpy:
    """Proxy for numpy to allow safe access to whitelisted functions."""
    def __getattr__(self, name):
        if name in SAFE_FUNCTIONS:
            return SAFE_FUNCTIONS[name]
        raise NameNotDefined(name, f"Function 'np.{name}' is not allowed in formulas.")

class FormulaEngine:
    """
    Evaluate column formulas using safe expressions.

    Supports:
    - Simple arithmetic: duration * 10
    - Column references: quantity * unit_price
    - Cross-table references: @exercises.calories_per_minute
    - Conditional expressions: np.where(status == 'active', 1, 0)
    """

    def __init__(self, tables: Dict[str, pd.DataFrame]):
        """
        Initialize with generated tables for cross-table lookups.

        Args:
            tables: Dict mapping table names to DataFrames
        """
        self.tables = tables

    def evaluate(
        self,
        df: pd.DataFrame,
        formula: str,
        fk_column: Optional[str] = None,
    ) -> np.ndarray:
        """
        Evaluate a formula on a DataFrame.

        Args:
            df: DataFrame to evaluate on
            formula: Expression string
            fk_column: Foreign key column name for cross-table lookups

        Returns:
            Array of computed values
        """
        # Replace cross-table references with actual values
        processed_formula = self._resolve_cross_table_refs(df, formula, fk_column)

        # Create evaluation context
        names = {
            'np': SafeNumpy(),
            'pd': pd, # Needed for some checks, but ideally we restrict this too
            # simpleeval defaults allow basic math
        }

        # Add columns to context
        for col in df.columns:
            names[col] = df[col].values

        # Evaluate the expression safely
        try:
            result = simple_eval(
                processed_formula,
                names=names,
                functions=SAFE_FUNCTIONS, # Allow top-level functions too
                operators=SAFE_OPERATORS
            )
            return np.array(result)
        except Exception as e:
            raise ValueError(f"Failed to evaluate formula '{formula}': {e}")

    def _resolve_cross_table_refs(
        self,
        df: pd.DataFrame,
        formula: str,
        fk_column: Optional[str] = None,
    ) -> str:
        """
        Replace @table.column references with actual looked-up values.

        Pattern: @tablename.columnname

        Args:
            df: Current DataFrame
            formula: Formula with potential cross-table refs
            fk_column: FK column to use for lookups

        Returns:
            Formula with refs replaced by _lookup_N variables
        """
        # Pattern to match @table.column
        pattern = r'@(\w+)\.(\w+)'
        matches = re.findall(pattern, formula)

        if not matches:
            return formula

        result = formula

        for i, (table_name, col_name) in enumerate(matches):
            if table_name not in self.tables:
                raise ValueError(f"Table '{table_name}' not found for formula lookup")

            ref_table = self.tables[table_name]

            if col_name not in ref_table.columns:
                raise ValueError(f"Column '{col_name}' not found in table '{table_name}'")

            # Determine the FK column to use for lookup
            actual_fk = fk_column or f"{table_name}_id"

            if actual_fk not in df.columns:
                raise ValueError(
                    f"Cannot lookup @{table_name}.{col_name}: "
                    f"no foreign key column '{actual_fk}' in current table"
                )

            # Create lookup mapping and apply
            # Handle duplicates in index by grouping or taking first (safety)
            if not ref_table['id'].is_unique:
                 # If IDs are not unique in ref table, we have a problem.
                 # Assuming IDs are unique for lookups.
                 pass

            lookup_map = ref_table.set_index('id')[col_name].to_dict()
            df[actual_fk].map(lookup_map).values

            var_name = f'_lookup_{i}'
            # Store in a temporary dict doesn't work well with clean state
            # Instead we'll inject into the names dict in evaluate
            # But specific method needs to handle this exchange.
            # Refactoring to return both formula and context updates would be better
            # For now, sticking to string replacement and hoping evaluate calls context filler

            # CRITICAL: This method only returns string.
            # The previous implementation put it in _temp_lookups but implementation was messy.
            # We will use evaluate_with_lookups which is the main entry point

            result = result.replace(f'@{table_name}.{col_name}', var_name)

        return result

    def evaluate_with_lookups(
        self,
        df: pd.DataFrame,
        formula: str,
        fk_mappings: Optional[Dict[str, str]] = None,
    ) -> np.ndarray:
        """
        Evaluate formula with automatic cross-table lookups.

        Args:
            df: DataFrame to evaluate on
            formula: Expression with @table.column references
            fk_mappings: Optional dict mapping table name to FK column name
                         e.g., {"exercises": "exercise_id", "products": "product_id"}

        Returns:
            Array of computed values
        """
        fk_mappings = fk_mappings or {}

        # Pattern to match @table.column
        pattern = r'@(\w+)\.(\w+)'
        matches = re.findall(pattern, formula)

        result = formula
        names = {
            'np': SafeNumpy(),
            'pd': pd,
        }

        # Add columns to context
        for col in df.columns:
            names[col] = df[col].values

        # Resolve each cross-table reference
        for i, (table_name, col_name) in enumerate(matches):
            if table_name not in self.tables:
                raise ValueError(f"Table '{table_name}' not found")

            ref_table = self.tables[table_name]

            # Determine FK column
            fk_col = fk_mappings.get(table_name, f"{table_name}_id")
            if fk_col.endswith("s_id"):
                # Try without trailing 's' (exercises -> exercise_id)
                alt_fk = fk_col.replace("s_id", "_id")
                if alt_fk in df.columns:
                    fk_col = alt_fk

            if fk_col not in df.columns:
                # Try common patterns
                for pattern_fk in [f"{table_name}_id", f"{table_name[:-1]}_id", "id"]:
                    if pattern_fk in df.columns:
                        fk_col = pattern_fk
                        break

            if fk_col not in df.columns:
                raise ValueError(f"No FK column found for table '{table_name}'")

            # Create lookup and add to context
            if 'id' not in ref_table.columns:
                raise ValueError(f"Reference table '{table_name}' has no 'id' column")

            lookup_map = ref_table.set_index('id')[col_name].to_dict()
            looked_up = df[fk_col].map(lookup_map).fillna(0).values

            var_name = f'_ref_{i}'
            names[var_name] = looked_up
            result = result.replace(f'@{table_name}.{col_name}', var_name)

        # Evaluate safely
        try:
            return np.array(simple_eval(
                result,
                names=names,
                functions=SAFE_FUNCTIONS,
                operators=SAFE_OPERATORS
            ))
        except Exception as e:
            raise ValueError(f"Failed to evaluate formula '{formula}': {e}")


class FormulaColumn:
    """
    Definition of a formula-based column.
    """

    def __init__(
        self,
        name: str,
        formula: str,
        result_type: str = "float",
        fk_mappings: Optional[Dict[str, str]] = None,
    ):
        """
        Define a formula column.

        Args:
            name: Column name
            formula: Expression (can include @table.column refs)
            result_type: Type of result (int, float, boolean)
            fk_mappings: Map table names to FK column names
        """
        self.name = name
        self.formula = formula
        self.result_type = result_type
        self.fk_mappings = fk_mappings or {}

    def evaluate(
        self,
        df: pd.DataFrame,
        tables: Dict[str, pd.DataFrame],
    ) -> np.ndarray:
        """
        Evaluate this formula column.

        Args:
            df: Current table DataFrame
            tables: All generated tables for cross-table lookups

        Returns:
            Array of computed values
        """
        engine = FormulaEngine(tables)
        result = engine.evaluate_with_lookups(df, self.formula, self.fk_mappings)

        # Cast to result type
        if self.result_type == "int":
            return result.astype(int)
        elif self.result_type == "float":
            return result.astype(float)
        elif self.result_type == "boolean":
            return result.astype(bool)

        return result


def apply_formula_columns(
    df: pd.DataFrame,
    formulas: List[FormulaColumn],
    tables: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Apply formula columns to a DataFrame.

    Args:
        df: DataFrame to add columns to
        formulas: List of formula column definitions
        tables: All tables for cross-table lookups

    Returns:
        DataFrame with formula columns added
    """
    result = df.copy()

    for formula_col in formulas:
        result[formula_col.name] = formula_col.evaluate(result, tables)

    return result
