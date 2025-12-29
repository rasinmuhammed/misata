"""
Streaming export utilities for Misata.

Provides streaming CSV/Parquet export to handle large datasets
without loading everything into memory.
"""

import csv
import os
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Iterator, List, Optional, Union

import numpy as np
import pandas as pd

from misata.exceptions import ExportError, FileWriteError


class StreamingExporter:
    """Export data in streaming fashion to handle large datasets.
    
    Instead of building a full DataFrame and then exporting, this writes
    batches directly to files as they are generated.
    
    Example:
        exporter = StreamingExporter(output_dir="./data")
        
        for table_name, batch_df in simulator.generate_all():
            exporter.write_batch(table_name, batch_df)
        
        exporter.finalize()
    """
    
    def __init__(
        self,
        output_dir: str,
        format: str = "csv",
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ):
        """Initialize the exporter.
        
        Args:
            output_dir: Directory to write files to
            format: Export format ('csv' or 'parquet')
            progress_callback: Optional callback(table_name, rows_written)
        """
        self.output_dir = Path(output_dir)
        self.format = format.lower()
        self.progress_callback = progress_callback
        
        self._file_handles: Dict[str, Any] = {}
        self._csv_writers: Dict[str, csv.writer] = {}
        self._rows_written: Dict[str, int] = {}
        self._headers_written: Dict[str, bool] = {}
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def write_batch(self, table_name: str, df: pd.DataFrame) -> int:
        """Write a batch of data to the appropriate file.
        
        Args:
            table_name: Name of the table
            df: Batch DataFrame to write
            
        Returns:
            Number of rows written
        """
        if self.format == "csv":
            return self._write_csv_batch(table_name, df)
        elif self.format == "parquet":
            return self._write_parquet_batch(table_name, df)
        else:
            raise ExportError(f"Unsupported format: {self.format}")
    
    def _write_csv_batch(self, table_name: str, df: pd.DataFrame) -> int:
        """Write a batch to CSV file."""
        file_path = self.output_dir / f"{table_name}.csv"
        
        try:
            # First batch: write header
            if table_name not in self._headers_written:
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(df.columns.tolist())
                self._headers_written[table_name] = True
                self._rows_written[table_name] = 0
            
            # Append data
            with open(file_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for _, row in df.iterrows():
                    writer.writerow(row.tolist())
            
            rows = len(df)
            self._rows_written[table_name] = self._rows_written.get(table_name, 0) + rows
            
            if self.progress_callback:
                self.progress_callback(table_name, self._rows_written[table_name])
            
            return rows
            
        except Exception as e:
            raise FileWriteError(f"Failed to write CSV: {e}", path=str(file_path))
    
    def _write_parquet_batch(self, table_name: str, df: pd.DataFrame) -> int:
        """Write a batch to Parquet file using append mode."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            raise ExportError(
                "PyArrow required for Parquet export",
                details={"suggestion": "pip install pyarrow"}
            )
        
        file_path = self.output_dir / f"{table_name}.parquet"
        
        try:
            table = pa.Table.from_pandas(df)
            
            if file_path.exists():
                # Append to existing file
                existing = pq.read_table(file_path)
                combined = pa.concat_tables([existing, table])
                pq.write_table(combined, file_path)
            else:
                pq.write_table(table, file_path)
            
            rows = len(df)
            self._rows_written[table_name] = self._rows_written.get(table_name, 0) + rows
            
            if self.progress_callback:
                self.progress_callback(table_name, self._rows_written[table_name])
            
            return rows
            
        except Exception as e:
            raise FileWriteError(f"Failed to write Parquet: {e}", path=str(file_path))
    
    def finalize(self) -> Dict[str, int]:
        """Finalize all exports and return summary.
        
        Returns:
            Dict mapping table names to row counts
        """
        # Close any open file handles
        for handle in self._file_handles.values():
            try:
                handle.close()
            except Exception:
                pass
        
        self._file_handles.clear()
        self._csv_writers.clear()
        
        return self._rows_written.copy()
    
    def get_file_paths(self) -> Dict[str, Path]:
        """Get paths to all exported files."""
        ext = ".csv" if self.format == "csv" else ".parquet"
        return {
            table: self.output_dir / f"{table}{ext}"
            for table in self._rows_written.keys()
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get export statistics."""
        return {
            "output_dir": str(self.output_dir),
            "format": self.format,
            "tables": self._rows_written.copy(),
            "total_rows": sum(self._rows_written.values()),
        }


def stream_to_csv(
    generator: Generator[tuple, None, None],
    output_dir: str,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> Dict[str, int]:
    """Stream data from a generator directly to CSV files.
    
    Args:
        generator: Iterator yielding (table_name, batch_df) tuples
        output_dir: Directory to write files to
        progress_callback: Optional callback(table_name, rows_written)
        
    Returns:
        Dict mapping table names to final row counts
    """
    exporter = StreamingExporter(
        output_dir=output_dir,
        format="csv",
        progress_callback=progress_callback,
    )
    
    for table_name, batch_df in generator:
        exporter.write_batch(table_name, batch_df)
    
    return exporter.finalize()


def stream_to_parquet(
    generator: Generator[tuple, None, None],
    output_dir: str,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> Dict[str, int]:
    """Stream data from a generator directly to Parquet files.
    
    Args:
        generator: Iterator yielding (table_name, batch_df) tuples
        output_dir: Directory to write files to
        progress_callback: Optional callback(table_name, rows_written)
        
    Returns:
        Dict mapping table names to final row counts
    """
    exporter = StreamingExporter(
        output_dir=output_dir,
        format="parquet",
        progress_callback=progress_callback,
    )
    
    for table_name, batch_df in generator:
        exporter.write_batch(table_name, batch_df)
    
    return exporter.finalize()
