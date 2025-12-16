"""
Core DataSimulator class for high-performance synthetic data generation.

This module implements vectorized data generation with support for:
- Topological sorting of table dependencies
- Vectorized column generation (NO LOOPS)
- Referential integrity enforcement
- Scenario event application
- Integration with mimesis for entity generation
"""

import warnings
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

import mimesis
import numpy as np
import pandas as pd
from mimesis.locales import Locale

from misata.schema import Column, Relationship, ScenarioEvent, SchemaConfig, Table


class DataSimulator:
    """
    High-performance synthetic data simulator.
    
    Generates synthetic datasets based on SchemaConfig definitions,
    using vectorized operations for maximum performance.
    
    Attributes:
        config: Schema configuration
        data: Generated dataframes (table_name -> DataFrame)
        generic: Mimesis generic provider for entity generation
        rng: NumPy random generator for reproducibility
    """
    
    def __init__(self, config: SchemaConfig, locale: Locale = Locale.EN, 
                 apply_semantic_fixes: bool = True):
        """
        Initialize the simulator.
        
        Args:
            config: Schema configuration defining tables, columns, and relationships
            locale: Locale for mimesis entity generation (default: English)
            apply_semantic_fixes: Auto-fix column types based on semantic patterns
        """
        self.config = config
        self.data: Dict[str, pd.DataFrame] = {}
        self.generic = mimesis.Generic(locale=locale)
        
        # Apply semantic inference to fix column types
        if apply_semantic_fixes:
            from misata.semantic import apply_semantic_inference
            self.config.columns = apply_semantic_inference(self.config.columns)
        
        # Set random seed if provided
        seed = config.seed if config.seed is not None else np.random.randint(0, 2**32 - 1)
        self.rng = np.random.default_rng(seed)
        np.random.seed(seed)  # For legacy numpy.random calls

        
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
        Get valid parent IDs for foreign key generation.
        
        Args:
            relationship: Relationship definition
        
        Returns:
            Array of valid parent IDs
        """
        parent_df = self.data[relationship.parent_table]
        parent_ids = parent_df[relationship.parent_key].values
        return parent_ids
    
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
            choices = params["choices"]
            probabilities = params.get("probabilities", None)
            
            if probabilities is not None:
                # Normalize probabilities
                probabilities = np.array(probabilities)
                probabilities = probabilities / probabilities.sum()
            
            values = self.rng.choice(choices, size=size, p=probabilities)
            return values
        
        # INTEGER
        elif column.type == "int":
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
                # Default to uniform for unknown distributions
                low = params.get("min", 0)
                high = params.get("max", 1000)
                values = self.rng.integers(low, high, size=size)
            
            # Apply min/max constraints
            if "min" in params:
                values = np.maximum(values, params["min"])
            if "max" in params:
                values = np.minimum(values, params["max"])
            
            return values

        
        # FLOAT
        elif column.type == "float":
            distribution = params.get("distribution", "normal")
            
            # Handle categorical distribution (fixed choices like prices)
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
                # Default to uniform for unknown distributions
                low = params.get("min", 0.0)
                high = params.get("max", 1000.0)
                values = self.rng.uniform(low, high, size=size)
            
            # Apply min/max constraints
            if "min" in params:
                values = np.maximum(values, params["min"])
            if "max" in params:
                values = np.minimum(values, params["max"])
            
            # Round if specified
            if "decimals" in params:
                values = np.round(values, params["decimals"])
            
            return values

        
        # DATE
        elif column.type == "date":
            start = pd.to_datetime(params["start"])
            end = pd.to_datetime(params["end"])
            
            # Generate random dates as integers, then convert
            start_int = start.value
            end_int = end.value
            random_ints = self.rng.integers(start_int, end_int, size=size)
            values = pd.to_datetime(random_ints)
            
            return values
        
        # FOREIGN KEY
        elif column.type == "foreign_key":
            # Find the relationship for this foreign key
            relationship = None
            for rel in self.config.relationships:
                if rel.child_table == table_name and rel.child_key == column.name:
                    relationship = rel
                    break
            
            if relationship is None:
                # No relationship found - treat as sequential ID (graceful degradation)
                warnings.warn(
                    f"No relationship defined for foreign key '{column.name}' "
                    f"in table '{table_name}'. Generating sequential IDs instead."
                )
                # Generate random IDs in a reasonable range
                values = self.rng.integers(1, max(size // 10, 100), size=size)
                return values
            
            # Check if parent table has been generated
            if relationship.parent_table not in self.data:
                warnings.warn(
                    f"Parent table '{relationship.parent_table}' not yet generated for "
                    f"foreign key '{column.name}'. Generating sequential IDs instead."
                )
                values = self.rng.integers(1, max(size // 10, 100), size=size)
                return values
            
            parent_ids = self._get_parent_ids(relationship)
            
            # Handle empty parent table
            if len(parent_ids) == 0:
                warnings.warn(
                    f"Parent table '{relationship.parent_table}' is empty. "
                    f"Generating sequential IDs for foreign key '{column.name}'."
                )
                values = self.rng.integers(1, max(size // 10, 100), size=size)
                return values
            
            # Randomly sample from parent IDs (with replacement)
            values = self.rng.choice(parent_ids, size=size)
            
            return values

        
        # TEXT (using mimesis)
        elif column.type == "text":
            text_type = params.get("text_type", "sentence")
            
            # Generate in batches for performance
            if text_type == "name":
                values = np.array([self.generic.person.full_name() for _ in range(size)])
            elif text_type == "email":
                values = np.array([self.generic.person.email() for _ in range(size)])
            elif text_type == "company":
                values = np.array([self.generic.finance.company() for _ in range(size)])
            elif text_type == "sentence":
                values = np.array([self.generic.text.sentence() for _ in range(size)])
            elif text_type == "word":
                values = np.array([self.generic.text.word() for _ in range(size)])
            elif text_type == "address":
                values = np.array([self.generic.address.full_address() for _ in range(size)])
            elif text_type == "phone":
                values = np.array([self.generic.person.phone_number() for _ in range(size)])
            elif text_type == "url":
                values = np.array([self.generic.internet.url() for _ in range(size)])
            else:
                # Default to sentence
                values = np.array([self.generic.text.sentence() for _ in range(size)])
            
            return values
        
        # BOOLEAN
        elif column.type == "boolean":
            probability = params.get("probability", 0.5)
            values = self.rng.random(size) < probability
            return values
        
        else:
            raise ValueError(f"Unknown column type: {column.type}")
    
    def apply_event(self, df: pd.DataFrame, event: ScenarioEvent) -> pd.DataFrame:
        """
        Apply a scenario event to modify data based on conditions.
        
        Uses pandas query/eval for high-performance conditional modifications.
        
        Args:
            df: DataFrame to modify
            event: Scenario event definition
        
        Returns:
            Modified DataFrame
        """
        try:
            # Evaluate condition to get boolean mask
            mask = df.eval(event.condition)
        except Exception as e:
            warnings.warn(
                f"Failed to evaluate condition '{event.condition}' for event '{event.name}': {e}"
            )
            return df
        
        # Apply modifier based on type
        if event.modifier_type == "multiply":
            df.loc[mask, event.column] *= event.modifier_value
        elif event.modifier_type == "add":
            df.loc[mask, event.column] += event.modifier_value
        elif event.modifier_type == "set":
            df.loc[mask, event.column] = event.modifier_value
        elif event.modifier_type == "function":
            # Custom function (stored as string, would need eval - careful!)
            warnings.warn(
                f"Function modifiers not yet implemented for event '{event.name}'"
            )
        
        return df
    
    def generate_table(self, table_name: str) -> pd.DataFrame:
        """
        Generate a complete table with all columns.
        
        For reference tables with inline_data, returns the pre-defined data.
        For transactional tables, generates data using column definitions.
        
        Args:
            table_name: Name of the table to generate
        
        Returns:
            Generated DataFrame
        """
        table = self.config.get_table(table_name)
        if table is None:
            raise ValueError(f"Table '{table_name}' not found in schema")
        
        # Check if this is a reference table with inline data
        if table.is_reference and table.inline_data:
            df = pd.DataFrame(table.inline_data)
            print(f"  [Reference table: using {len(df)} pre-defined rows]")
            return df
        
        columns = self.config.get_columns(table_name)
        size = table.row_count
        
        # Generate all columns
        data = {}
        df = pd.DataFrame()  # Empty df for progressive building
        
        for column in columns:
            values = self.generate_column(table_name, column, size, df)
            data[column.name] = values
            df[column.name] = values  # Add to df for dependent columns
        
        df = pd.DataFrame(data)
        
        # Apply formula columns if any defined
        df = self._apply_formula_columns(df, table_name)
        
        # Post-process to fix correlated columns
        df = self._fix_correlated_columns(df, table_name)
        
        # Apply scenario events for this table
        table_events = [e for e in self.config.events if e.table == table_name]
        for event in table_events:
            df = self.apply_event(df, event)
        
        return df
    
    def _apply_formula_columns(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """
        Apply formula-based derived columns.
        
        Formula columns can reference:
        - Other columns in the same table: duration * 10
        - Columns from parent tables: @exercises.calories_per_minute
        """
        try:
            from misata.formulas import FormulaEngine
        except ImportError:
            return df
        
        # Get any formula columns from config
        columns = self.config.get_columns(table_name)
        formula_cols = [c for c in columns if c.distribution_params.get("formula")]
        
        if not formula_cols:
            return df
        
        engine = FormulaEngine(self.data)
        
        for col in formula_cols:
            formula = col.distribution_params["formula"]
            result = engine.evaluate_with_lookups(df, formula)
            df[col.name] = result
        
        return df


    
    def _fix_correlated_columns(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """
        Post-process to fix common semantically correlated columns.
        
        This handles cases where columns should be aligned (e.g., plan and price).
        """
        columns = list(df.columns)
        
        # Fix plan-price correlation
        if "plan" in columns and "price" in columns:
            # Common plan-price mappings
            plan_prices = {
                "free": 0.0,
                "basic": 9.99,
                "starter": 9.99,
                "premium": 19.99,
                "pro": 19.99,
                "professional": 29.99,
                "enterprise": 49.99,
                "business": 49.99,
                "unlimited": 99.99,
            }
            
            # Apply the mapping
            df["price"] = df["plan"].map(lambda p: plan_prices.get(str(p).lower(), df["price"].iloc[0]))
        
        # Fix status-related columns (ensure paid subscriptions are active)
        if "status" in columns and "price" in columns:
            # If price > 0, there's a higher chance of being active
            pass  # Keep random for now, could add logic later
        
        return df

    
    def generate_all(self) -> Dict[str, pd.DataFrame]:
        """
        Generate all tables in dependency order.
        
        Returns:
            Dictionary mapping table names to generated DataFrames
        """
        sorted_tables = self.topological_sort()
        
        for table_name in sorted_tables:
            print(f"Generating table: {table_name}")
            self.data[table_name] = self.generate_table(table_name)
        
        return self.data
    
    def export_to_csv(self, output_dir: str = ".") -> None:
        """
        Export all generated tables to CSV files.
        
        Args:
            output_dir: Directory to save CSV files (default: current directory)
        """
        import os
        
        os.makedirs(output_dir, exist_ok=True)
        
        for table_name, df in self.data.items():
            output_path = os.path.join(output_dir, f"{table_name}.csv")
            df.to_csv(output_path, index=False)
            print(f"Exported {table_name} ({len(df)} rows) to {output_path}")
    
    def get_summary(self) -> str:
        """
        Get a summary of generated data.
        
        Returns:
            Formatted summary string
        """
        summary_lines = ["Generated Data Summary:", "=" * 50]
        
        for table_name, df in self.data.items():
            summary_lines.append(f"\n{table_name}: {len(df):,} rows, {len(df.columns)} columns")
            summary_lines.append(f"  Memory: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
        
        total_rows = sum(len(df) for df in self.data.values())
        summary_lines.append(f"\nTotal rows: {total_rows:,}")
        
        return "\n".join(summary_lines)
