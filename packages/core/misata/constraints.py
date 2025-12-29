"""
Constraint handling for Misata data generation.

Provides constraint classes for applying business rules to generated data.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from misata.exceptions import ConstraintError


class BaseConstraint(ABC):
    """Abstract base class for all constraints."""
    
    @abstractmethod
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply the constraint to a DataFrame.
        
        Args:
            df: DataFrame to constrain
            
        Returns:
            Constrained DataFrame
        """
        pass
    
    @abstractmethod
    def validate(self, df: pd.DataFrame) -> bool:
        """Check if the constraint is satisfied.
        
        Args:
            df: DataFrame to check
            
        Returns:
            True if constraint is satisfied
        """
        pass


class SumConstraint(BaseConstraint):
    """Ensures sum of a column (optionally grouped) doesn't exceed a value."""
    
    def __init__(
        self,
        column: str,
        max_sum: float,
        group_by: Optional[List[str]] = None,
        action: str = "cap"
    ):
        self.column = column
        self.max_sum = max_sum
        self.group_by = group_by or []
        self.action = action  # 'cap', 'redistribute', 'drop'
    
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.column not in df.columns:
            return df
        
        df = df.copy()
        
        if not self.group_by:
            # Global sum constraint
            current_sum = df[self.column].sum()
            if current_sum > self.max_sum:
                if self.action == "cap":
                    scale = self.max_sum / current_sum
                    df[self.column] = df[self.column] * scale
                elif self.action == "drop":
                    # Keep first N rows that fit
                    cumsum = df[self.column].cumsum()
                    df = df[cumsum <= self.max_sum]
        else:
            # Grouped sum constraint
            def cap_group(group):
                current_sum = group[self.column].sum()
                if current_sum > self.max_sum:
                    if self.action == "cap":
                        scale = self.max_sum / current_sum
                        group = group.copy()
                        group[self.column] = group[self.column] * scale
                return group
            
            df = df.groupby(self.group_by, group_keys=False).apply(cap_group)
        
        return df
    
    def validate(self, df: pd.DataFrame) -> bool:
        if self.column not in df.columns:
            return True
        
        if not self.group_by:
            return df[self.column].sum() <= self.max_sum
        
        group_sums = df.groupby(self.group_by)[self.column].sum()
        return (group_sums <= self.max_sum).all()


class RangeConstraint(BaseConstraint):
    """Ensures values in a column stay within a range."""
    
    def __init__(self, column: str, min_val: Optional[float] = None, max_val: Optional[float] = None):
        self.column = column
        self.min_val = min_val
        self.max_val = max_val
    
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.column not in df.columns:
            return df
        
        df = df.copy()
        
        if self.min_val is not None:
            df[self.column] = df[self.column].clip(lower=self.min_val)
        
        if self.max_val is not None:
            df[self.column] = df[self.column].clip(upper=self.max_val)
        
        return df
    
    def validate(self, df: pd.DataFrame) -> bool:
        if self.column not in df.columns:
            return True
        
        values = df[self.column]
        
        if self.min_val is not None and (values < self.min_val).any():
            return False
        
        if self.max_val is not None and (values > self.max_val).any():
            return False
        
        return True


class UniqueConstraint(BaseConstraint):
    """Ensures values in column(s) are unique."""
    
    def __init__(self, columns: Union[str, List[str]]):
        self.columns = [columns] if isinstance(columns, str) else columns
    
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        # Drop duplicates
        return df.drop_duplicates(subset=self.columns)
    
    def validate(self, df: pd.DataFrame) -> bool:
        return not df.duplicated(subset=self.columns).any()


class NotNullConstraint(BaseConstraint):
    """Ensures a column has no null values."""
    
    def __init__(self, column: str, fill_value: Any = None):
        self.column = column
        self.fill_value = fill_value
    
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.column not in df.columns:
            return df
        
        df = df.copy()
        
        if self.fill_value is not None:
            df[self.column] = df[self.column].fillna(self.fill_value)
        else:
            df = df.dropna(subset=[self.column])
        
        return df
    
    def validate(self, df: pd.DataFrame) -> bool:
        if self.column not in df.columns:
            return True
        return not df[self.column].isnull().any()


class RatioConstraint(BaseConstraint):
    """Ensures ratio between categories matches target distribution."""
    
    def __init__(self, column: str, target_ratios: Dict[Any, float]):
        self.column = column
        self.target_ratios = target_ratios
        # Normalize ratios
        total = sum(target_ratios.values())
        self.target_ratios = {k: v / total for k, v in target_ratios.items()}
    
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.column not in df.columns:
            return df
        
        df = df.copy()
        n = len(df)
        
        # Calculate target counts
        target_counts = {k: int(n * v) for k, v in self.target_ratios.items()}
        
        # Randomly assign categories
        categories = []
        for cat, count in target_counts.items():
            categories.extend([cat] * count)
        
        # Fill remaining
        remaining = n - len(categories)
        if remaining > 0:
            most_common = max(self.target_ratios, key=self.target_ratios.get)
            categories.extend([most_common] * remaining)
        
        np.random.shuffle(categories)
        df[self.column] = categories[:n]
        
        return df
    
    def validate(self, df: pd.DataFrame) -> bool:
        if self.column not in df.columns:
            return True
        
        actual = df[self.column].value_counts(normalize=True)
        
        for cat, target in self.target_ratios.items():
            actual_ratio = actual.get(cat, 0)
            if abs(actual_ratio - target) > 0.05:  # 5% tolerance
                return False
        
        return True


class TemporalConstraint(BaseConstraint):
    """Ensures temporal ordering between columns."""
    
    def __init__(self, before_column: str, after_column: str, min_gap_days: int = 0):
        self.before_column = before_column
        self.after_column = after_column
        self.min_gap_days = min_gap_days
    
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.before_column not in df.columns or self.after_column not in df.columns:
            return df
        
        df = df.copy()
        
        before = pd.to_datetime(df[self.before_column])
        after = pd.to_datetime(df[self.after_column])
        
        # Fix violations
        mask = after < before
        if mask.any():
            # Swap dates where violated
            df.loc[mask, self.after_column], df.loc[mask, self.before_column] = \
                df.loc[mask, self.before_column], df.loc[mask, self.after_column]
        
        # Apply minimum gap
        if self.min_gap_days > 0:
            before = pd.to_datetime(df[self.before_column])
            after = pd.to_datetime(df[self.after_column])
            gap = (after - before).dt.days
            
            mask = gap < self.min_gap_days
            if mask.any():
                df.loc[mask, self.after_column] = (
                    before[mask] + pd.Timedelta(days=self.min_gap_days)
                ).dt.strftime('%Y-%m-%d')
        
        return df
    
    def validate(self, df: pd.DataFrame) -> bool:
        if self.before_column not in df.columns or self.after_column not in df.columns:
            return True
        
        before = pd.to_datetime(df[self.before_column])
        after = pd.to_datetime(df[self.after_column])
        
        gap = (after - before).dt.days
        return (gap >= self.min_gap_days).all()


class ConstraintEngine:
    """Engine for applying multiple constraints to a DataFrame."""
    
    def __init__(self, constraints: Optional[List[BaseConstraint]] = None):
        self.constraints = constraints or []
    
    def add(self, constraint: BaseConstraint) -> "ConstraintEngine":
        """Add a constraint."""
        self.constraints.append(constraint)
        return self
    
    def apply_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply all constraints in order."""
        for constraint in self.constraints:
            try:
                df = constraint.apply(df)
            except Exception as e:
                raise ConstraintError(
                    f"Failed to apply constraint: {e}",
                    constraint_type=type(constraint).__name__
                )
        return df
    
    def validate_all(self, df: pd.DataFrame) -> Dict[str, bool]:
        """Check all constraints and return results."""
        results = {}
        for constraint in self.constraints:
            name = type(constraint).__name__
            results[name] = constraint.validate(df)
        return results
