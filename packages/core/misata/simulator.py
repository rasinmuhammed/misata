"""
Core DataSimulator class for high-performance synthetic data generation.

This module implements vectorized data generation with support for:
- Topological sorting of table dependencies
- Vectorized column generation (NO LOOPS)
- Referential integrity enforcement
- Scenario event application
- Pure Python text generation (no external dependencies)
"""

import warnings
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from misata.generators import TextGenerator
from misata.schema import Column, Relationship, ScenarioEvent, SchemaConfig


class DataSimulator:
    """
    High-performance synthetic data simulator.

    Generates synthetic datasets based on SchemaConfig definitions,
    using vectorized operations for maximum performance.

    Attributes:
        config: Schema configuration
        data: Generated dataframes (table_name -> DataFrame)
        text_gen: TextGenerator for entity generation
        rng: NumPy random generator for reproducibility
    """

    def __init__(self, config: SchemaConfig,
                 apply_semantic_fixes: bool = True, batch_size: int = 10_000,
                 smart_mode: bool = False, use_llm: bool = True):
        """
        Initialize the simulator.

        Args:
            config: Schema configuration defining tables, columns, and relationships
            apply_semantic_fixes: Auto-fix column types based on semantic patterns
            batch_size: Number of rows to generate per batch
            smart_mode: Enable LLM-powered context-aware value generation
            use_llm: If smart_mode is True, whether to use LLM (vs curated fallbacks)
        """
        self.config = config
        self.context: Dict[str, pd.DataFrame] = {}  # Lightweight context (IDs only)
        self.text_gen = TextGenerator(seed=config.seed)
        self.batch_size = batch_size
        self.smart_mode = smart_mode
        self.use_llm = use_llm
        self._smart_gen = None  # Lazy init
        self._unique_pools: Dict[str, np.ndarray] = {}  # Store pre-generated unique values
        self._unique_counters: Dict[str, int] = {}      # Track usage of unique pools
        self._smart_pools: Dict[str, np.ndarray] = {}   # Cache smart value pools

        # Apply semantic inference to fix column types
        if apply_semantic_fixes:
            from misata.semantic import apply_semantic_inference
            self.config.columns = apply_semantic_inference(self.config.columns)

        # Set random seed if provided
        seed = config.seed if config.seed is not None else np.random.randint(0, 2**32 - 1)
        self.rng = np.random.default_rng(seed)
        np.random.seed(seed)  # For legacy numpy.random calls
    
    def _get_smart_gen(self):
        """Lazy initialize SmartValueGenerator."""
        if self._smart_gen is None:
            try:
                from misata.smart_values import SmartValueGenerator
                self._smart_gen = SmartValueGenerator()
            except Exception:
                self._smart_gen = None
        return self._smart_gen

    def topological_sort(self) -> List[str]:
        """
        Determine table generation order using topological sort.

        Parent tables must be generated before child tables to ensure
        referential integrity.

        Returns:
            List of table names in dependency order

        Raises:
            ValueError: If circular dependencies are detected
        """
        # Build adjacency list and in-degree map
        graph = defaultdict(list)
        in_degree = {table.name: 0 for table in self.config.tables}

        for rel in self.config.relationships:
            graph[rel.parent_table].append(rel.child_table)
            in_degree[rel.child_table] += 1

        # Kahn's algorithm for topological sort
        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        sorted_tables = []

        while queue:
            table_name = queue.popleft()
            sorted_tables.append(table_name)

            for neighbor in graph[table_name]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check for circular dependencies
        if len(sorted_tables) != len(self.config.tables):
            raise ValueError(
                f"Circular dependency detected in relationships. "
                f"Generated {len(sorted_tables)} / {len(self.config.tables)} tables."
            )

        return sorted_tables

    def _get_parent_ids(self, relationship: Relationship) -> np.ndarray:
        """
        Get valid parent IDs for foreign key generation, applying filters if defined.

        Args:
            relationship: Relationship definition

        Returns:
            Array of valid parent IDs
        """
        if relationship.parent_table not in self.context:
            return np.array([])

        parent_df = self.context[relationship.parent_table]
        if relationship.parent_key not in parent_df.columns:
             return np.array([])

        # Apply filters if defined (Logic Gap Fix)
        # Apply filters if defined (Logic Gap Fix)
        if relationship.filters:
            mask = np.ones(len(parent_df), dtype=bool)
            for col, val in relationship.filters.items():
                if col in parent_df.columns:
                    mask &= (parent_df[col] == val)
                else:
                    # If filter column missing from context, can't filter.
                    # Assume mismatch if column missing.
                    mask[:]=False

            valid_ids = parent_df.loc[mask, relationship.parent_key].values
        else:
            valid_ids = parent_df[relationship.parent_key].values

        return valid_ids

    def _update_context(self, table_name: str, df: pd.DataFrame) -> None:
        """
        Update the context with key columns from the generated batch.

        Smart Context Logic:
        1. Store Primary Key ('id')
        2. Store columns used as foreign keys by children (parent_key)
        3. Store columns used in Relationship filters (Logic Gap fix)
        4. Store columns used in 'relative_to' date constraints (Time Travel fix)
        """
        needed_cols = {'id'}

        # 2. FK and Filter dependencies
        for rel in self.config.relationships:
            if rel.parent_table == table_name:
                needed_cols.add(rel.parent_key)
                if rel.filters:
                    for col in rel.filters.keys():
                        needed_cols.add(col)

        # 4. Filter 'relative_to' dependencies
        # This requires scanning ALL columns of ALL child tables to see if they reference this table
        # Optimization: Build this dependency map once in __init__?
        # For now, we scan here. It's fast enough for schema sizes < 100 tables.
        for child_table in self.config.tables:
            child_cols = self.config.get_columns(child_table.name)
            for col in child_cols:
                if col.type == 'date' and 'relative_to' in col.distribution_params:
                    # Format: "parent_table.column"
                    try:
                        ptable, pcol = col.distribution_params['relative_to'].split('.')
                        if ptable == table_name:
                            needed_cols.add(pcol)
                    except:
                        pass

        cols_to_store = [c for c in needed_cols if c in df.columns]
        if not cols_to_store:
            return

        ctx_df = df[cols_to_store].copy()

        if table_name not in self.context:
            self.context[table_name] = ctx_df
        else:
            # Append to existing context
            self.context[table_name] = pd.concat([self.context[table_name], ctx_df], ignore_index=True)

    def generate_column(
        self,
        table_name: str,
        column: Column,
        size: int,
        table_data: Optional[pd.DataFrame] = None,
    ) -> np.ndarray:
        """
        Generate a single column using vectorized operations.

        Args:
            table_name: Name of the table being generated
            column: Column definition
            size: Number of values to generate
            table_data: Partially generated table (for columns that depend on other columns)

        Returns:
            Numpy array of generated values
        """
        params = column.distribution_params

        # CATEGORICAL
        if column.type == "categorical":
            choices = params.get("choices", ["A", "B", "C"])
            probabilities = params.get("probabilities", None)

            # Ensure choices is a list
            if not isinstance(choices, list):
                choices = list(choices)

            if probabilities is not None:
                # Convert to float array and normalize
                probabilities = np.array(probabilities, dtype=float)
                prob_sum = probabilities.sum()
                if prob_sum > 0:
                    probabilities = probabilities / prob_sum
                else:
                    probabilities = None

            values = self.rng.choice(choices, size=size, p=probabilities)
            return values

        # INTEGER
        elif column.type == "int":
            # Handle unique integer generation
            if column.unique:
                pool_key = f"{table_name}.{column.name}"

                # Verify we aren't asking for more uniques than possible
                low = params.get("min", 0)
                high = params.get("max", 1000)
                total_needed_for_table = self.config.get_table(table_name).row_count

                if pool_key not in self._unique_pools:
                    # Check range capacity
                    if (high - low) < total_needed_for_table:
                        # Auto-expand range to fix user error (common in tests/small ranges)
                        warnings.warn(f"Range {high-low} too small for unique column {column.name} (needs {total_needed_for_table}). Extending max.")
                        high = low + total_needed_for_table + 100

                    # Generate full permutation
                    pool = np.arange(low, high)
                    self.rng.shuffle(pool)
                    self._unique_pools[pool_key] = pool
                    self._unique_counters[pool_key] = 0

                # Fetch chunk
                current_idx = self._unique_counters[pool_key]
                if current_idx + size > len(self._unique_pools[pool_key]):
                     raise ValueError(f"Exhausted unique values for {column.name}")

                values = self._unique_pools[pool_key][current_idx : current_idx + size]
                self._unique_counters[pool_key] += size
                return values.astype(int)

            distribution = params.get("distribution", "normal")

            # Handle categorical distribution (fixed choices)
            if distribution == "categorical" or "choices" in params:
                choices = params.get("choices", [1, 2, 3, 4, 5])
                probabilities = params.get("probabilities", None)
                if probabilities is not None:
                    probabilities = np.array(probabilities)
                    probabilities = probabilities / probabilities.sum()
                values = self.rng.choice(choices, size=size, p=probabilities)
                return np.array(values).astype(int)
            elif distribution == "normal":
                mean = params.get("mean", 100)
                std = params.get("std", 20)
                values = self.rng.normal(mean, std, size=size).astype(int)
            elif distribution == "uniform":
                low = params.get("min", 0)
                high = params.get("max", 1000)
                values = self.rng.integers(low, high, size=size)
            elif distribution == "poisson":
                lam = params.get("lambda", 10)
                values = self.rng.poisson(lam, size=size)
            else:
                low = params.get("min", 0)
                high = params.get("max", 1000)
                values = self.rng.integers(low, high, size=size)

            if "min" in params:
                values = np.maximum(values, params["min"])
            if "max" in params:
                values = np.minimum(values, params["max"])

            return values

        # FLOAT
        elif column.type == "float":
            distribution = params.get("distribution", "normal")

            if distribution == "categorical" or "choices" in params:
                choices = params.get("choices", [1.0, 2.0, 3.0])
                probabilities = params.get("probabilities", None)
                if probabilities is not None:
                    probabilities = np.array(probabilities)
                    probabilities = probabilities / probabilities.sum()
                values = self.rng.choice(choices, size=size, p=probabilities)
                return np.array(values).astype(float)
            elif distribution == "normal":
                mean = params.get("mean", 100.0)
                std = params.get("std", 20.0)
                values = self.rng.normal(mean, std, size=size)
            elif distribution == "uniform":
                low = params.get("min", 0.0)
                high = params.get("max", 1000.0)
                values = self.rng.uniform(low, high, size=size)
            elif distribution == "exponential":
                scale = params.get("scale", 1.0)
                values = self.rng.exponential(scale, size=size)
            else:
                low = params.get("min", 0.0)
                high = params.get("max", 1000.0)
                values = self.rng.uniform(low, high, size=size)

            if "min" in params:
                values = np.maximum(values, params["min"])
            if "max" in params:
                values = np.minimum(values, params["max"])
            if "decimals" in params:
                values = np.round(values, params["decimals"])

            return values

        # DATE
        elif column.type == "date":
            # Parent-Relative Date Generation (Time Travel Fix)
            if "relative_to" in params:
                # Format: "parent_table.column_name"
                try:
                    rel_table, rel_col = params["relative_to"].split(".")
                    # Find relationship
                    relationship = None
                    for rel in self.config.relationships:
                        if rel.child_table == table_name and rel.parent_table == rel_table:
                            relationship = rel
                            break

                    if relationship and table_data is not None and relationship.child_key in table_data.columns:
                        # Vectorized lookup!
                        child_fk_values = table_data[relationship.child_key].values
                        parent_df = self.context.get(rel_table)

                        if parent_df is not None and rel_col in parent_df.columns:
                            # Map FK to Parent Date
                            # Create a lookup series/dict
                            parent_date_map = parent_df.set_index(relationship.parent_key)[rel_col]
                            parent_dates = parent_date_map.reindex(child_fk_values).values

                            # Generate deltas
                            min_delta = params.get("min_delta_days", 0)
                            max_delta = params.get("max_delta_days", 365)
                            deltas = self.rng.integers(min_delta, max_delta, size=size)
                            deltas_ns = deltas.astype('timedelta64[D]')

                            # Child Date = Parent Date + Delta
                            values = parent_dates + deltas_ns
                            return values
                except Exception as e:
                    warnings.warn(f"Failed to generate relative date: {e}. Falling back to random range.")

            start = pd.to_datetime(params["start"])
            end = pd.to_datetime(params["end"])

            start_int = start.value
            end_int = end.value
            random_ints = self.rng.integers(start_int, end_int, size=size)
            values = pd.to_datetime(random_ints)

            return values

        # FOREIGN KEY
        elif column.type == "foreign_key":
            relationship = None
            for rel in self.config.relationships:
                if rel.child_table == table_name and rel.child_key == column.name:
                    relationship = rel
                    break

            if relationship is None:
                warnings.warn(
                    f"No relationship defined for foreign key '{column.name}' "
                    f"in table '{table_name}'. Generating sequential IDs instead."
                )
                values = self.rng.integers(1, max(size // 10, 100), size=size)
                return values

            # Check context instead of data
            if relationship.parent_table not in self.context:
                warnings.warn(
                    f"Parent table '{relationship.parent_table}' not yet generated for "
                    f"foreign key '{column.name}'. Generating sequential IDs instead."
                )
                values = self.rng.integers(1, max(size // 10, 100), size=size)
                return values

            parent_ids = self._get_parent_ids(relationship)

            if len(parent_ids) == 0:
                warnings.warn(
                    f"Parent table '{relationship.parent_table}' has no valid IDs in context (after filters). "
                    f"Generating sequential IDs for foreign key '{column.name}'."
                )
                values = self.rng.integers(1, max(size // 10, 100), size=size)
                return values

            values = self.rng.choice(parent_ids, size=size)
            return values

        # TEXT
        elif column.type == "text":
            text_type = params.get("text_type", "sentence")
            
            # Smart value generation - check for domain-specific content
            smart_generate = params.get("smart_generate", False) or self.smart_mode
            if smart_generate:
                smart_gen = self._get_smart_gen()
                if smart_gen:
                    # Check for explicit domain hint or auto-detect
                    domain_hint = params.get("domain_hint")
                    context = params.get("context", "")
                    
                    # Create cache key for this column's pool
                    pool_key = f"{table_name}.{column.name}"
                    
                    if pool_key not in self._smart_pools:
                        pool = smart_gen.get_pool(
                            column_name=column.name,
                            table_name=table_name,
                            domain_hint=domain_hint,
                            context=context,
                            size=100,
                            use_llm=self.use_llm,
                        )
                        if pool:
                            self._smart_pools[pool_key] = np.array(pool)
                    
                    if pool_key in self._smart_pools:
                        pool = self._smart_pools[pool_key]
                        values = self.rng.choice(pool, size=size)
                        return values

            if text_type == "name":
                values = np.array([self.text_gen.name() for _ in range(size)])
            elif text_type == "email":
                values = np.array([self.text_gen.email() for _ in range(size)])
            elif text_type == "company":
                values = np.array([self.text_gen.company() for _ in range(size)])
            elif text_type == "sentence":
                values = np.array([self.text_gen.sentence() for _ in range(size)])
            elif text_type == "word":
                values = np.array([self.text_gen.word() for _ in range(size)])
            elif text_type == "address":
                values = np.array([self.text_gen.full_address() for _ in range(size)])
            elif text_type == "phone":
                values = np.array([self.text_gen.phone_number() for _ in range(size)])
            elif text_type == "url":
                values = np.array([self.text_gen.url() for _ in range(size)])
            else:
                values = np.array([self.text_gen.sentence() for _ in range(size)])

            return values

        # BOOLEAN
        elif column.type == "boolean":
            probability = params.get("probability", 0.5)
            values = self.rng.random(size) < probability
            return values

        # TIME
        elif column.type == "time":
            # Generate random times as HH:MM:SS strings
            start_hour = params.get("start_hour", 0)
            end_hour = params.get("end_hour", 24)
            hours = self.rng.integers(start_hour, end_hour, size=size)
            minutes = self.rng.integers(0, 60, size=size)
            seconds = self.rng.integers(0, 60, size=size)
            values = np.array([f"{h:02d}:{m:02d}:{s:02d}" for h, m, s in zip(hours, minutes, seconds)])
            return values

        # DATETIME
        elif column.type == "datetime":
            # Generate random datetimes within a range
            start = pd.to_datetime(params.get("start", "2020-01-01"))
            end = pd.to_datetime(params.get("end", "2024-12-31"))
            start_int = start.value
            end_int = end.value
            random_ints = self.rng.integers(start_int, end_int, size=size)
            values = pd.to_datetime(random_ints)
            return values

        else:
            raise ValueError(f"Unknown column type: {column.type}")

    def apply_event(self, df: pd.DataFrame, event: ScenarioEvent) -> pd.DataFrame:
        """Apply a scenario event to modify data based on conditions."""
        try:
            mask = df.eval(event.condition)
        except Exception as e:
            warnings.warn(f"Failed to evaluate condition '{event.condition}' for event '{event.name}': {e}")
            return df

        if event.modifier_type == "multiply":
            df.loc[mask, event.column] *= event.modifier_value
        elif event.modifier_type == "add":
            df.loc[mask, event.column] += event.modifier_value
        elif event.modifier_type == "set":
            df.loc[mask, event.column] = event.modifier_value
        elif event.modifier_type == "function":
            warnings.warn(f"Function modifiers not yet implemented for event '{event.name}'")

        return df

    def _update_context(self, table_name: str, df: pd.DataFrame) -> None:
        """
        Update the context with key columns from the generated batch.

        Smart Context Logic:
        1. Store Primary Key ('id')
        2. Store columns used as foreign keys by children (parent_key)
        3. Store columns used in Relationship filters (Logic Gap fix)
        4. Store columns used in 'relative_to' date constraints (Time Travel fix)
        """
        needed_cols = {'id'}

        # 2. FK and Filter dependencies
        for rel in self.config.relationships:
            if rel.parent_table == table_name:
                needed_cols.add(rel.parent_key)
                if rel.filters:
                    for col in rel.filters.keys():
                        needed_cols.add(col)

        # 4. Filter 'relative_to' dependencies
        # This requires scanning ALL columns of ALL child tables to see if they reference this table
        # Optimization: Build this dependency map once in __init__?
        # For now, we scan here. It's fast enough for schema sizes < 100 tables.
        for child_table in self.config.tables:
            child_cols = self.config.get_columns(child_table.name)
            for col in child_cols:
                if col.type == 'date' and 'relative_to' in col.distribution_params:
                    # Format: "parent_table.column"
                    try:
                        ptable, pcol = col.distribution_params['relative_to'].split('.')
                        if ptable == table_name:
                            needed_cols.add(pcol)
                    except Exception:
                        pass

        cols_to_store = [c for c in needed_cols if c in df.columns]
        if not cols_to_store:
            return

        ctx_df = df[cols_to_store].copy()

        if table_name not in self.context:
            self.context[table_name] = ctx_df
        else:
            # Append to existing context
            self.context[table_name] = pd.concat([self.context[table_name], ctx_df], ignore_index=True)

    def generate_batches(self, table_name: str) -> Any:
        """
        Yield batches of generated data for a table.

        Args:
            table_name: Name of the table to generate

        Yields:
            DataFrame batch
        """
        table = self.config.get_table(table_name)
        if table is None:
            raise ValueError(f"Table '{table_name}' not found in schema")

        # Reference table with inline data - yield as single batch
        if table.is_reference and table.inline_data:
            df = pd.DataFrame(table.inline_data)
            self._update_context(table_name, df)
            yield df
            return

        columns = self.config.get_columns(table_name)
        total_rows = table.row_count

        rows_generated = 0

        while rows_generated < total_rows:
            batch_size = min(self.batch_size, total_rows - rows_generated)

            # Generate batch
            data = {}
            df_batch = pd.DataFrame()

            for column in columns:
                values = self.generate_column(table_name, column, batch_size, df_batch)
                data[column.name] = values
                df_batch[column.name] = values

            df_batch = pd.DataFrame(data)

            # Apply formulas
            df_batch = self._apply_formula_columns(df_batch, table_name)

            # Post-process
            df_batch = self._fix_correlated_columns(df_batch, table_name)

            # Apply events
            table_events = [e for e in self.config.events if e.table == table_name]
            for event in table_events:
                df_batch = self.apply_event(df_batch, event)

            # Apply business rule constraints
            df_batch = self.apply_constraints(df_batch, table)

            # Update context for future batches/tables
            self._update_context(table_name, df_batch)

            yield df_batch

            rows_generated += batch_size

    def apply_constraints(self, df: pd.DataFrame, table: Any) -> pd.DataFrame:
        """
        Apply business rule constraints to generated data.

        Args:
            df: DataFrame batch to constrain
            table: Table definition containing constraints

        Returns:
            Constrained DataFrame
        """
        if not hasattr(table, 'constraints') or not table.constraints:
            return df

        for constraint in table.constraints:
            df = self._apply_single_constraint(df, constraint)

        return df

    def _apply_single_constraint(self, df: pd.DataFrame, constraint: Any) -> pd.DataFrame:
        """Apply a single constraint to the DataFrame."""

        # Validate required columns exist
        for col in constraint.group_by:
            if col not in df.columns:
                warnings.warn(f"Constraint '{constraint.name}': Column '{col}' not found. Skipping.")
                return df

        if constraint.column and constraint.column not in df.columns:
            warnings.warn(f"Constraint '{constraint.name}': Target column '{constraint.column}' not found. Skipping.")
            return df

        if constraint.type == "max_per_group":
            # Cap values per group (e.g., max 8 hours per employee per day)
            if constraint.action == "cap":
                # Simple cap: clip the value column
                df[constraint.column] = df.groupby(constraint.group_by)[constraint.column].transform(
                    lambda x: x.clip(upper=constraint.value)
                )
            elif constraint.action == "redistribute":
                # More complex: redistribute excess across the group
                # For now, just cap
                df[constraint.column] = df.groupby(constraint.group_by)[constraint.column].transform(
                    lambda x: x.clip(upper=constraint.value)
                )

        elif constraint.type == "sum_limit":
            # Limit sum per group (e.g., max 8 total hours per employee per day across projects)
            def cap_sum(group):
                total = group[constraint.column].sum()
                if total > constraint.value:
                    # Scale down proportionally
                    scale = constraint.value / total
                    group[constraint.column] = group[constraint.column] * scale
                return group

            df = df.groupby(constraint.group_by, group_keys=False).apply(cap_sum)

        elif constraint.type == "unique_combination":
            # Ensure unique combinations (e.g., one timesheet per employee-project-date)
            if constraint.action == "drop":
                df = df.drop_duplicates(subset=constraint.group_by, keep='first')

        elif constraint.type == "min_per_group":
            # Floor values per group
            if constraint.action == "cap":
                df[constraint.column] = df.groupby(constraint.group_by)[constraint.column].transform(
                    lambda x: x.clip(lower=constraint.value)
                )

        return df

    def _apply_formula_columns(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Apply formula-based derived columns using context for lookups."""
        try:
            from misata.formulas import FormulaEngine
        except ImportError:
            return df

        columns = self.config.get_columns(table_name)
        formula_cols = [c for c in columns if c.distribution_params.get("formula")]

        if not formula_cols:
            return df

        # FormulaEngine now needs context, not full data
        # BUT FormulaEngine expects full DataFrames in tables dict for lookups
        # Our self.context IS a Dict[str, pd.DataFrame], just restricted columns
        # So it should work if the formulas only ref columns in context (like id, price)
        # Note: We need to make sure context has columns needed for formulas!
        # Current _update_context only saves PK/FKs.
        # TODO: Analyze formulas to find required context columns?
        # For now, simplistic approach: formulas usually look up 'price', 'cost' etc.
        # We might need to store more in context.
        # Let's trust user or update _update_context to be smarter later.

        engine = FormulaEngine(self.context)

        for col in formula_cols:
            formula = col.distribution_params["formula"]
            # For correctness, lookups should work.
            # If context doesn't have the column, FormulaEngine raises Error.
            try:
                result = engine.evaluate_with_lookups(df, formula)
                df[col.name] = result
            except ValueError as e:
                # Warn and skip if context missing
                warnings.warn(f"Formula evaluation failed (context missing?): {e}")

        return df

    def _fix_correlated_columns(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Post-process to fix common semantically correlated columns."""
        columns = list(df.columns)
        if "plan" in columns and "price" in columns:
            plan_prices = {
                "free": 0.0, "basic": 9.99, "starter": 9.99, "premium": 19.99,
                "pro": 19.99, "professional": 29.99, "enterprise": 49.99,
                "business": 49.99, "unlimited": 99.99,
            }
            df["price"] = df["plan"].map(lambda p: plan_prices.get(str(p).lower(), df["price"].iloc[0]))
        return df

    def generate_all(self):
        """
        Generate all tables in dependency order.

        Yields:
            Tuple[str, pd.DataFrame]: (table_name, batch_df)
        """
        sorted_tables = self.topological_sort()

        for table_name in sorted_tables:
            for batch in self.generate_batches(table_name):
                yield table_name, batch

    def export_to_csv(self, output_dir: str = ".") -> None:
        """
        Export all generated tables to CSV files, creating files progressively.
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        # Track open file handles or just append?
        # Appending is safer.
        files_created = set()

        for table_name, batch_df in self.generate_all():
            output_path = os.path.join(output_dir, f"{table_name}.csv")
            mode = 'a' if table_name in files_created else 'w'
            header = table_name not in files_created

            batch_df.to_csv(output_path, mode=mode, header=header, index=False)
            files_created.add(table_name)

    def get_summary(self) -> str:
        """
        Get a summary of generated data (from context).
        Only shows context info since full data isn't kept.
        """
        summary_lines = ["Generated Context Summary (Lightweight):", "=" * 50]

        for table_name, df in self.context.items():
            summary_lines.append(f"\n{table_name}: {len(df):,} rows tracked in context")
            summary_lines.append(f"  Context Columns: {list(df.columns)}")
            summary_lines.append(f"  Context Memory: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

        return "\n".join(summary_lines)
