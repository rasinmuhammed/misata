"""
Noise injection module for realistic ML training data.

Adds real-world imperfections to synthetic data:
- Missing values (nulls/NaN)
- Outliers
- Typos and data entry errors
- Duplicates and near-duplicates
- Distribution drift over time
"""

import random
import string
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


class NoiseInjector:
    """
    Inject realistic noise and imperfections into synthetic data.

    Makes data suitable for ML training by adding real-world issues:
    - Missing values at configurable rates
    - Statistical outliers
    - Typos in text fields
    - Duplicate rows
    - Temporal distribution shifts

    Usage:
        injector = NoiseInjector(seed=42)
        noisy_df = injector.apply(df, config={
            "null_rate": 0.05,
            "outlier_rate": 0.02,
            "typo_rate": 0.01,
            "duplicate_rate": 0.03,
        })
    """

    def __init__(self, seed: Optional[int] = None):
        """Initialize with optional random seed for reproducibility."""
        self.rng = np.random.default_rng(seed)
        self.py_rng = random.Random(seed)

    def apply(
        self,
        df: pd.DataFrame,
        config: Optional[Dict[str, Any]] = None,
    ) -> pd.DataFrame:
        """
        Apply all configured noise types to a DataFrame.

        Args:
            df: Input DataFrame
            config: Noise configuration dict with rates for each type

        Returns:
            DataFrame with noise applied
        """
        if config is None:
            config = {}

        result = df.copy()

        # Apply each noise type
        if config.get("null_rate", 0) > 0:
            result = self.inject_nulls(result, rate=config["null_rate"],
                                       columns=config.get("null_columns"))

        if config.get("outlier_rate", 0) > 0:
            result = self.inject_outliers(result, rate=config["outlier_rate"],
                                          columns=config.get("outlier_columns"))

        if config.get("typo_rate", 0) > 0:
            result = self.inject_typos(result, rate=config["typo_rate"],
                                       columns=config.get("typo_columns"))

        if config.get("duplicate_rate", 0) > 0:
            result = self.inject_duplicates(result, rate=config["duplicate_rate"])

        return result

    def inject_nulls(
        self,
        df: pd.DataFrame,
        rate: float = 0.05,
        columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Inject null/missing values at a specified rate.

        Args:
            df: Input DataFrame
            rate: Probability of any cell becoming null (0.0-1.0)
            columns: Specific columns to apply to (default: all except ID columns)

        Returns:
            DataFrame with nulls injected
        """
        result = df.copy()

        # Default: skip ID columns
        if columns is None:
            columns = [c for c in df.columns if not c.endswith('_id') and c != 'id']

        for col in columns:
            if col not in result.columns:
                continue

            mask = self.rng.random(len(result)) < rate
            result.loc[mask, col] = np.nan

        return result

    def inject_outliers(
        self,
        df: pd.DataFrame,
        rate: float = 0.02,
        columns: Optional[List[str]] = None,
        multiplier: float = 5.0,
    ) -> pd.DataFrame:
        """
        Inject statistical outliers into numeric columns.

        Args:
            df: Input DataFrame
            rate: Probability of any numeric cell becoming an outlier
            columns: Specific columns (default: all numeric)
            multiplier: How extreme the outliers should be (times std dev)

        Returns:
            DataFrame with outliers injected
        """
        result = df.copy()

        # Default: all numeric columns
        if columns is None:
            columns = result.select_dtypes(include=[np.number]).columns.tolist()
            columns = [c for c in columns if not c.endswith('_id') and c != 'id']

        for col in columns:
            if col not in result.columns:
                continue

            series = result[col]
            if not np.issubdtype(series.dtype, np.number):
                continue

            mean = series.mean()
            std = series.std()

            if std == 0 or np.isnan(std):
                continue

            mask = self.rng.random(len(result)) < rate
            n_outliers = mask.sum()

            if n_outliers > 0:
                # Generate outliers above or below mean
                direction = self.rng.choice([-1, 1], size=n_outliers)
                outlier_values = mean + direction * multiplier * std * (1 + self.rng.random(n_outliers))
                result.loc[mask, col] = outlier_values

        return result

    def inject_typos(
        self,
        df: pd.DataFrame,
        rate: float = 0.01,
        columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Inject typos into text columns.

        Typo types:
        - Character swap
        - Character deletion
        - Character insertion
        - Case change

        Args:
            df: Input DataFrame
            rate: Probability of any text cell getting a typo
            columns: Specific columns (default: all object/string)

        Returns:
            DataFrame with typos injected
        """
        result = df.copy()

        # Default: all text columns
        if columns is None:
            columns = result.select_dtypes(include=['object', 'string']).columns.tolist()
            # Skip columns that look like IDs or structured data
            columns = [c for c in columns if 'id' not in c.lower() and 'email' not in c.lower()]

        for col in columns:
            if col not in result.columns:
                continue

            mask = self.rng.random(len(result)) < rate

            for idx in result.index[mask]:
                value = result.at[idx, col]
                if pd.isna(value) or not isinstance(value, str) or len(value) < 2:
                    continue

                result.at[idx, col] = self._add_typo(value)

        return result

    def _add_typo(self, text: str) -> str:
        """Add a single typo to a text string."""
        if len(text) < 2:
            return text

        typo_type = self.py_rng.choice(['swap', 'delete', 'insert', 'case'])
        chars = list(text)
        pos = self.py_rng.randint(0, len(chars) - 1)

        if typo_type == 'swap' and pos < len(chars) - 1:
            chars[pos], chars[pos + 1] = chars[pos + 1], chars[pos]
        elif typo_type == 'delete':
            chars.pop(pos)
        elif typo_type == 'insert':
            chars.insert(pos, self.py_rng.choice(string.ascii_lowercase))
        elif typo_type == 'case':
            chars[pos] = chars[pos].swapcase()

        return ''.join(chars)

    def inject_duplicates(
        self,
        df: pd.DataFrame,
        rate: float = 0.03,
        exact: bool = True,
    ) -> pd.DataFrame:
        """
        Inject duplicate rows.

        Args:
            df: Input DataFrame
            rate: Rate of rows to duplicate
            exact: If True, exact duplicates. If False, near-duplicates with slight variations.

        Returns:
            DataFrame with duplicates added
        """
        n_duplicates = int(len(df) * rate)

        if n_duplicates == 0:
            return df

        # Select random rows to duplicate
        dup_indices = self.rng.choice(df.index, size=n_duplicates, replace=True)
        duplicates = df.loc[dup_indices].copy()

        if not exact:
            # Add slight variations to numeric columns
            for col in duplicates.select_dtypes(include=[np.number]).columns:
                if col.endswith('_id') or col == 'id':
                    continue
                noise = self.rng.normal(0, 0.01, len(duplicates))
                duplicates[col] = duplicates[col] * (1 + noise)

        return pd.concat([df, duplicates], ignore_index=True)

    def apply_temporal_drift(
        self,
        df: pd.DataFrame,
        date_column: str,
        value_column: str,
        drift_rate: float = 0.1,
        drift_direction: str = "up",
    ) -> pd.DataFrame:
        """
        Apply temporal distribution drift to simulate changing trends.

        Args:
            df: Input DataFrame
            date_column: Column containing dates
            value_column: Numeric column to apply drift to
            drift_rate: Rate of drift (0.1 = 10% change over time range)
            drift_direction: "up" for increasing, "down" for decreasing

        Returns:
            DataFrame with temporal drift applied
        """
        result = df.copy()

        if date_column not in result.columns or value_column not in result.columns:
            return result

        dates = pd.to_datetime(result[date_column])
        min_date = dates.min()
        max_date = dates.max()

        if min_date == max_date:
            return result

        # Normalize dates to 0-1 range
        time_fraction = (dates - min_date) / (max_date - min_date)

        # Calculate drift multiplier
        multiplier = 1 + (drift_rate * time_fraction if drift_direction == "up"
                         else -drift_rate * time_fraction)

        result[value_column] = result[value_column] * multiplier

        return result


# Convenience function
def add_noise(
    df: pd.DataFrame,
    null_rate: float = 0.0,
    outlier_rate: float = 0.0,
    typo_rate: float = 0.0,
    duplicate_rate: float = 0.0,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """
    Convenience function to add noise to a DataFrame.

    Args:
        df: Input DataFrame
        null_rate: Rate of null value injection (0.0-1.0)
        outlier_rate: Rate of outlier injection
        typo_rate: Rate of typo injection in text
        duplicate_rate: Rate of duplicate rows
        seed: Random seed for reproducibility

    Returns:
        DataFrame with noise applied

    Example:
        noisy_df = add_noise(df, null_rate=0.05, outlier_rate=0.02)
    """
    injector = NoiseInjector(seed=seed)
    return injector.apply(df, config={
        "null_rate": null_rate,
        "outlier_rate": outlier_rate,
        "typo_rate": typo_rate,
        "duplicate_rate": duplicate_rate,
    })
