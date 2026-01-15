"""
Context management for Misata data generation.

Provides stateful context tracking during multi-table generation,
including parent ID tracking for foreign keys and cross-table references.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd


@dataclass
class TableContext:
    """Context for a single generated table."""
    
    name: str
    row_count: int = 0
    columns: Set[str] = field(default_factory=set)
    primary_key: Optional[np.ndarray] = None
    foreign_keys: Dict[str, np.ndarray] = field(default_factory=dict)
    cached_columns: Dict[str, np.ndarray] = field(default_factory=dict)
    
    def set_primary_key(self, values: np.ndarray) -> None:
        """Store primary key values for foreign key lookups."""
        self.primary_key = values
        self.row_count = len(values)
    
    def set_column(self, column_name: str, values: np.ndarray) -> None:
        """Cache a column for cross-table references."""
        self.cached_columns[column_name] = values
        self.columns.add(column_name)
    
    def get_column(self, column_name: str) -> Optional[np.ndarray]:
        """Get cached column values."""
        return self.cached_columns.get(column_name)
    
    def get_ids(self) -> Optional[np.ndarray]:
        """Get primary key values."""
        return self.primary_key


class GenerationContext:
    """Manages state across multi-table data generation.
    
    This context tracks:
    - Generated table data for foreign key references
    - Columns needed for cross-table lookups
    - Progress tracking for callbacks
    
    Example:
        context = GenerationContext()
        
        # After generating users table
        context.register_table("users", users_df)
        
        # When generating orders (which references users)
        user_ids = context.get_parent_ids("users", "id")
        orders_df["user_id"] = np.random.choice(user_ids, size=1000)
    """
    
    def __init__(self):
        self._tables: Dict[str, TableContext] = {}
        self._generation_order: List[str] = []
        self._progress_callbacks: List[callable] = []
        self._current_table: Optional[str] = None
        self._current_progress: float = 0.0
    
    def register_table(
        self,
        table_name: str,
        df: pd.DataFrame,
        id_column: str = "id"
    ) -> None:
        """Register a generated table in the context.
        
        Args:
            table_name: Name of the table
            df: Generated DataFrame
            id_column: Primary key column name
        """
        ctx = TableContext(name=table_name)
        
        if id_column in df.columns:
            ctx.set_primary_key(df[id_column].values)
        
        # Cache all columns for potential cross-references
        for col in df.columns:
            ctx.set_column(col, df[col].values)
        
        self._tables[table_name] = ctx
        self._generation_order.append(table_name)
    
    def register_batch(
        self,
        table_name: str,
        df: pd.DataFrame,
        id_column: str = "id"
    ) -> None:
        """Register a batch of generated data (appends to existing).
        
        Args:
            table_name: Name of the table
            df: Generated batch DataFrame
            id_column: Primary key column name
        """
        if table_name not in self._tables:
            self.register_table(table_name, df, id_column)
            return
        
        ctx = self._tables[table_name]
        
        # Append to existing
        if id_column in df.columns:
            if ctx.primary_key is not None:
                ctx.primary_key = np.concatenate([ctx.primary_key, df[id_column].values])
            else:
                ctx.set_primary_key(df[id_column].values)
        
        for col in df.columns:
            if col in ctx.cached_columns:
                ctx.cached_columns[col] = np.concatenate([
                    ctx.cached_columns[col],
                    df[col].values
                ])
            else:
                ctx.set_column(col, df[col].values)
        
        ctx.row_count = len(ctx.primary_key) if ctx.primary_key is not None else ctx.row_count + len(df)
    
    def get_parent_ids(
        self,
        table_name: str,
        column: str = "id"
    ) -> Optional[np.ndarray]:
        """Get column values from a parent table for foreign key generation.
        
        Args:
            table_name: Parent table name
            column: Column to get values from
            
        Returns:
            Array of values or None if table not found
        """
        if table_name not in self._tables:
            return None
        
        ctx = self._tables[table_name]
        
        if column == "id" and ctx.primary_key is not None:
            return ctx.primary_key
        
        return ctx.get_column(column)
    
    def get_filtered_parent_ids(
        self,
        table_name: str,
        id_column: str = "id",
        filters: Optional[Dict[str, Any]] = None
    ) -> Optional[np.ndarray]:
        """Get filtered parent IDs based on conditions.
        
        Args:
            table_name: Parent table name
            id_column: ID column to return
            filters: Dict of column -> value conditions
            
        Returns:
            Filtered array of IDs
        """
        if table_name not in self._tables:
            return None
        
        ctx = self._tables[table_name]
        
        if not filters:
            return self.get_parent_ids(table_name, id_column)
        
        # Get base IDs
        ids = ctx.get_column(id_column)
        if ids is None:
            ids = ctx.primary_key
        
        if ids is None:
            return None
        
        # Apply filters
        mask = np.ones(len(ids), dtype=bool)
        
        for filter_col, filter_val in filters.items():
            col_values = ctx.get_column(filter_col)
            if col_values is not None:
                mask &= (col_values == filter_val)
        
        return ids[mask] if mask.any() else None
    
    def get_table_context(self, table_name: str) -> Optional[TableContext]:
        """Get full context for a table."""
        return self._tables.get(table_name)
    
    def has_table(self, table_name: str) -> bool:
        """Check if a table has been generated."""
        return table_name in self._tables
    
    def get_generated_tables(self) -> List[str]:
        """Get list of generated tables in order."""
        return self._generation_order.copy()
    
    def clear(self) -> None:
        """Clear all context data."""
        self._tables.clear()
        self._generation_order.clear()
        self._current_table = None
        self._current_progress = 0.0
    
    # ============ Progress Tracking ============
    
    def add_progress_callback(self, callback: callable) -> None:
        """Add a progress callback function.
        
        Callback signature: callback(table_name: str, progress: float, message: str)
        """
        self._progress_callbacks.append(callback)
    
    def set_current_table(self, table_name: str) -> None:
        """Set the currently generating table."""
        self._current_table = table_name
        self._notify_progress(0.0, f"Starting {table_name}")
    
    def update_progress(self, progress: float, message: str = "") -> None:
        """Update generation progress (0.0 to 1.0)."""
        self._current_progress = progress
        self._notify_progress(progress, message)
    
    def _notify_progress(self, progress: float, message: str) -> None:
        """Notify all progress callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(self._current_table, progress, message)
            except Exception:
                pass  # Don't let callback errors break generation
    
    # ============ Statistics ============
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all generated data."""
        return {
            "tables": {
                name: {
                    "row_count": ctx.row_count,
                    "columns": list(ctx.columns),
                }
                for name, ctx in self._tables.items()
            },
            "generation_order": self._generation_order,
            "total_rows": sum(ctx.row_count for ctx in self._tables.values()),
        }
