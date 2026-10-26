"""
Formula engine for derived columns.

This module enables columns that are computed from other columns,
supporting expressions like:
- calories_burned = duration_minutes * @exercises.calories_per_minute
- total_price = quantity * @products.price
- discount_amount = total_price * 0.1
"""

import re
import weakref
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import ast
import operator

try:
    from simpleeval import simple_eval, NameNotDefined
except ImportError:
    simple_eval = None

    class NameNotDefined(NameError):
        """Fallback used when simpleeval is not installed."""

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


def _require_simpleeval() -> None:
    """Raise a clear error when formula support is requested without the extra dependency."""
    if simple_eval is None:
        raise ImportError(
            "Formula support requires simpleeval. "
            "Install with: pip install 'misata[formulas]'"
        )

#: Parent key column -> position index, per parent table. Building the hash
#: table is the expensive part of a lookup and the parent is the same for every
#: child batch, so it is built once, checked against the key column on every
#: use, and dropped when its table is.
_KEY_INDEXES: Dict[Tuple[int, str], Tuple[Any, pd.Index]] = {}


def _key_index(table: pd.DataFrame, key: str) -> Optional[pd.Index]:
    """``table[key]`` as a unique Index, or ``None`` when its keys repeat."""
    keys = table[key].to_numpy()
    slot = (id(table), key)
    cached = _KEY_INDEXES.get(slot)
    if cached is not None and cached[0]() is table and np.array_equal(cached[1].to_numpy(), keys):
        return cached[1]
    index = pd.Index(keys.copy())
    if not index.is_unique:
        return None
    _KEY_INDEXES[slot] = (weakref.ref(table), index)
    weakref.finalize(table, _KEY_INDEXES.pop, slot, None)
    return index


def _contiguous_positions(keys: np.ndarray, foreign: pd.Series) -> Optional[np.ndarray]:
    """Positions by arithmetic when the keys are a run of consecutive integers.

    Generated primary keys usually are, and then a key's position is its
    offset from the first one: no index to build or hold. Only numeric
    foreign keys qualify, because a dict lookup never matches ``"1"`` to
    ``1`` and neither may this.
    """
    n = len(keys)
    if n == 0 or keys.dtype.kind not in "iu" or foreign.dtype.kind not in "iuf":
        return None
    start = int(keys[0])
    if int(keys[-1]) - start != n - 1 or not bool((np.diff(keys) == 1).all()):
        return None
    offset = foreign.to_numpy(dtype=float, na_value=np.nan) - start
    with np.errstate(invalid="ignore"):
        valid = (offset >= 0) & (offset < n) & (offset == np.floor(offset))
    return np.where(valid, offset, -1).astype(np.int64)


def _lookup(table: pd.DataFrame, key: str, column: str, foreign: pd.Series) -> np.ndarray:
    """``table[column]`` for each row's foreign key, 0 where no parent matches.

    The same values and dtype as mapping the foreign key through a
    ``{key: value}`` dict, at a cost in the batch's size rather than the
    parent table's.
    """
    if table.empty:
        return np.zeros(len(foreign))
    positions = _contiguous_positions(table[key].to_numpy(), foreign)
    if positions is None:
        index = _key_index(table, key)
        if index is None:
            mapping = table.set_index(key)[column].to_dict()
            return np.asarray(foreign.map(mapping).fillna(0).values)
        positions = index.get_indexer(foreign)
    values = pd.api.extensions.take(table[column].to_numpy(), positions, allow_fill=True)
    return np.asarray(pd.Series(values).fillna(0).values)


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
        fk_mappings: Optional[Dict[str, str]] = None
        table_refs = re.findall(r'@(\w+)\.(\w+)', formula)
        if fk_column and table_refs:
            unique_tables = {table_name for table_name, _ in table_refs}
            if len(unique_tables) == 1:
                fk_mappings = {next(iter(unique_tables)): fk_column}
        return self.evaluate_with_lookups(df, formula, fk_mappings=fk_mappings)

    def _prepare_formula_context(
        self,
        df: pd.DataFrame,
        formula: str,
        fk_mappings: Optional[Dict[str, str]] = None,
    ) -> tuple[str, Dict[str, np.ndarray]]:
        """Resolve cross-table refs and return names to inject into evaluation."""
        fk_mappings = fk_mappings or {}
        pattern = r'@(\w+)\.(\w+)'
        matches = re.findall(pattern, formula)

        result = formula
        lookup_names: Dict[str, np.ndarray] = {}

        for i, (table_name, col_name) in enumerate(matches):
            if table_name not in self.tables:
                raise ValueError(f"Table '{table_name}' not found")

            ref_table = self.tables[table_name]

            if col_name not in ref_table.columns:
                raise ValueError(f"Column '{col_name}' not found in table '{table_name}'")

            # Resolve the parent's primary key (the column the FK points at). Real schemas
            # use `employee_id`, `customer_id`, etc. — not a literal `id` — so we detect the
            # actual key instead of assuming. Preference: explicit mapping value, then
            # `<singular>_id` / `<table>_id`, then a lone `id`.
            singular = table_name[:-1] if table_name.endswith("s") else table_name
            parent_key = None
            for cand in (f"{singular}_id", f"{table_name}_id", "id"):
                if cand in ref_table.columns:
                    parent_key = cand
                    break
            if parent_key is None:
                raise ValueError(
                    f"Reference table '{table_name}' has no resolvable primary key "
                    f"(looked for {singular}_id, {table_name}_id, id)"
                )

            # Resolve the FK column on THIS table that references the parent.
            # Preference: explicit mapping (authoritative, from the relationships),
            # then conventional FK names (`employee_id`, `employees_id`), then a
            # named parent key only if it is not the generic "id".
            #
            # We must NEVER fall back to a literal "id": a child's own primary key
            # is named "id", and matching it would join the child to the parent on
            # the child's PK (timesheets.id -> employees.id), silently producing
            # wrong values for every row whose id has no matching parent.
            fk_col = fk_mappings.get(table_name)
            if fk_col is None or fk_col not in df.columns:
                candidates = [f"{singular}_id", f"{table_name}_id"]
                if parent_key and parent_key != "id":
                    candidates.insert(0, parent_key)
                fk_col = None
                for cand in candidates:
                    if cand in df.columns:
                        fk_col = cand
                        break
            if fk_col is None or fk_col not in df.columns:
                raise ValueError(
                    f"No FK column on this table references '{table_name}' "
                    f"(looked for {singular}_id, {table_name}_id)"
                )

            var_name = f'_ref_{i}'
            lookup_names[var_name] = _lookup(ref_table, parent_key, col_name, df[fk_col])
            result = result.replace(f'@{table_name}.{col_name}', var_name)

        return result, lookup_names

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
        fk_mappings = None
        matches = re.findall(r'@(\w+)\.(\w+)', formula)
        if fk_column and matches:
            unique_tables = {table_name for table_name, _ in matches}
            if len(unique_tables) == 1:
                fk_mappings = {next(iter(unique_tables)): fk_column}

        result, _ = self._prepare_formula_context(df, formula, fk_mappings)
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
        _require_simpleeval()
        fk_mappings = fk_mappings or {}

        # Pattern to match @table.column
        result, lookup_names = self._prepare_formula_context(df, formula, fk_mappings)
        names = {
            'np': SafeNumpy(),
            'pd': pd,
        }

        # Add columns to context
        for col in df.columns:
            names[col] = df[col].values
        names.update(lookup_names)

        # Evaluate safely
        try:
            return np.array(simple_eval(
                result,
                names=names,
                functions=SAFE_FUNCTIONS,
                operators=SAFE_OPERATORS
            ))
        except Exception as e:
            raise ValueError(f"Failed to evaluate formula '{formula}': {e}") from e


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
