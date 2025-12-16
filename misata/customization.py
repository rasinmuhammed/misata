"""
Attribute customization module for fine-grained control over data generation.

Allows users to:
- Override column values with custom generators
- Apply conditional logic to values
- Define custom value pools per column
- Apply transformations post-generation
"""

from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd


class ColumnOverride:
    """
    Define custom generation logic for a specific column.

    Usage:
        override = ColumnOverride(
            name="price",
            generator=lambda n: np.random.uniform(10, 100, n),
            post_process=lambda x: round(x, 2)
        )
    """

    def __init__(
        self,
        name: str,
        generator: Optional[Callable[[int], np.ndarray]] = None,
        value_pool: Optional[List[Any]] = None,
        conditional: Optional[Dict[str, Any]] = None,
        post_process: Optional[Callable[[Any], Any]] = None,
        null_rate: float = 0.0,
    ):
        """
        Initialize a column override.

        Args:
            name: Column name to override
            generator: Function that takes size N and returns N values
            value_pool: List of values to sample from
            conditional: Dict with {condition_column: {value: override_value}}
            post_process: Function to apply to each value after generation
            null_rate: Rate of null values to inject
        """
        self.name = name
        self.generator = generator
        self.value_pool = value_pool
        self.conditional = conditional
        self.post_process = post_process
        self.null_rate = null_rate

    def apply(self, df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
        """Apply this override to a DataFrame."""
        result = df.copy()

        if self.generator is not None:
            result[self.name] = self.generator(len(df))

        elif self.value_pool is not None:
            result[self.name] = rng.choice(self.value_pool, size=len(df))

        # Apply conditional overrides
        if self.conditional is not None:
            for cond_col, value_map in self.conditional.items():
                if cond_col not in result.columns:
                    continue
                for cond_value, override_value in value_map.items():
                    mask = result[cond_col] == cond_value
                    result.loc[mask, self.name] = override_value

        # Apply post-processing
        if self.post_process is not None:
            result[self.name] = result[self.name].apply(self.post_process)

        # Inject nulls
        if self.null_rate > 0:
            mask = rng.random(len(result)) < self.null_rate
            result.loc[mask, self.name] = np.nan

        return result


class Customizer:
    """
    Central customization engine for attribute-level control.

    Usage:
        customizer = Customizer()
        customizer.add_override("users", ColumnOverride(
            name="age",
            generator=lambda n: np.random.normal(35, 10, n).clip(18, 80).astype(int)
        ))
        customizer.add_conditional("orders", "shipping_cost", {
            "country": {"US": 5.99, "UK": 9.99, "CA": 7.99}
        })

        df = customizer.apply(df, "users")
    """

    def __init__(self, seed: Optional[int] = None):
        """Initialize the customizer."""
        self.overrides: Dict[str, List[ColumnOverride]] = {}
        self.rng = np.random.default_rng(seed)

    def add_override(self, table: str, override: ColumnOverride) -> "Customizer":
        """Add a column override for a table."""
        if table not in self.overrides:
            self.overrides[table] = []
        self.overrides[table].append(override)
        return self

    def add_conditional(
        self,
        table: str,
        column: str,
        conditions: Dict[str, Dict[Any, Any]],
    ) -> "Customizer":
        """
        Add a conditional value override.

        Args:
            table: Table name
            column: Column to override
            conditions: {condition_column: {condition_value: new_value}}

        Example:
            customizer.add_conditional("products", "tax_rate", {
                "category": {"Electronics": 0.08, "Food": 0.0, "Clothing": 0.05}
            })
        """
        override = ColumnOverride(name=column, conditional=conditions)
        return self.add_override(table, override)

    def add_value_pool(
        self,
        table: str,
        column: str,
        values: List[Any],
        probabilities: Optional[List[float]] = None,
    ) -> "Customizer":
        """
        Add a custom value pool for a column.

        Args:
            table: Table name
            column: Column to override
            values: List of possible values
            probabilities: Optional weights (must sum to 1)
        """
        if probabilities:
            def gen(n):
                return self.rng.choice(values, size=n, p=probabilities)
        else:
            def gen(n):
                return self.rng.choice(values, size=n)

        override = ColumnOverride(name=column, generator=gen)
        return self.add_override(table, override)

    def add_formula(
        self,
        table: str,
        column: str,
        formula: Callable[[pd.DataFrame], pd.Series],
    ) -> "Customizer":
        """
        Add a formula-based column using other columns.

        Args:
            table: Table name
            column: Column to create/override
            formula: Function that takes DataFrame and returns Series

        Example:
            customizer.add_formula("orders", "total",
                lambda df: df["quantity"] * df["unit_price"] * (1 + df["tax_rate"]))
        """
        # Store as a special override that uses post-processing
        class FormulaOverride(ColumnOverride):
            def __init__(self, name, formula_fn):
                super().__init__(name=name)
                self.formula_fn = formula_fn

            def apply(self, df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
                result = df.copy()
                result[self.name] = self.formula_fn(result)
                return result

        override = FormulaOverride(column, formula)
        return self.add_override(table, override)

    def apply(self, df: pd.DataFrame, table: str) -> pd.DataFrame:
        """Apply all overrides for a table to a DataFrame."""
        result = df.copy()

        if table not in self.overrides:
            return result

        for override in self.overrides[table]:
            result = override.apply(result, self.rng)

        return result


# Convenience functions for common patterns

def price_generator(min_val: float = 1.0, max_val: float = 1000.0, decimals: int = 2):
    """Create a price generator with realistic distribution."""
    def gen(n):
        # Log-normal distribution for prices (more small items than expensive ones)
        log_min = np.log(max(min_val, 0.01))
        log_max = np.log(max_val)
        log_prices = np.random.uniform(log_min, log_max, n)
        prices = np.exp(log_prices)
        return np.round(prices, decimals)
    return gen


def age_generator(mean: int = 35, std: int = 12, min_age: int = 18, max_age: int = 80):
    """Create an age generator with realistic distribution."""
    def gen(n):
        ages = np.random.normal(mean, std, n)
        return np.clip(ages, min_age, max_age).astype(int)
    return gen


def rating_generator(min_rating: float = 1.0, max_rating: float = 5.0, skew: str = "positive"):
    """Create a rating generator with configurable skew."""
    def gen(n):
        if skew == "positive":
            # Most ratings are 4-5 stars (beta distribution)
            ratings = np.random.beta(5, 2, n) * (max_rating - min_rating) + min_rating
        elif skew == "negative":
            ratings = np.random.beta(2, 5, n) * (max_rating - min_rating) + min_rating
        else:
            ratings = np.random.uniform(min_rating, max_rating, n)
        return np.round(ratings, 1)
    return gen


def percentage_generator(realistic: bool = True):
    """Create a percentage generator."""
    def gen(n):
        if realistic:
            # Most percentages cluster around common values
            common = [0, 5, 10, 15, 20, 25, 30, 50, 75, 100]
            base = np.random.choice(common, n)
            noise = np.random.uniform(-2, 2, n)
            return np.clip(base + noise, 0, 100)
        else:
            return np.random.uniform(0, 100, n)
    return gen
