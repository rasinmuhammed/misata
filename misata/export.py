"""
Export utilities for Misata-generated tables.

Supported targets:
  - CSV        (via pandas, always available)
  - Parquet    (via pandas + pyarrow or fastparquet)
  - DuckDB     (via duckdb library)
  - JSON Lines (via pandas)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Union


def to_parquet(
    tables: Dict[str, Any],
    output_dir: Union[str, Path],
    compression: str = "snappy",
) -> Dict[str, Path]:
    """Write each table to a Parquet file.

    Args:
        tables:      Dict mapping table name -> pd.DataFrame.
        output_dir:  Directory to write ``<table_name>.parquet`` files into.
        compression: Parquet compression codec. ``"snappy"`` (default), ``"gzip"``,
                     ``"zstd"``, or ``None`` for uncompressed.

    Returns:
        Dict mapping table name -> Path of the written file.

    Raises:
        ImportError: If neither ``pyarrow`` nor ``fastparquet`` is installed.

    Example::

        tables = misata.generate("A SaaS company with 1000 users.", seed=42)
        paths  = misata.to_parquet(tables, "./data/")
        # ./data/users.parquet
        # ./data/subscriptions.parquet
    """
    try:
        import pandas as pd  # noqa: F401
    except ImportError as e:
        raise ImportError("pandas is required for Parquet export.") from e

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: Dict[str, Path] = {}
    for name, df in tables.items():
        path = output_dir / f"{name}.parquet"
        df.to_parquet(path, compression=compression, index=False)
        written[name] = path

    return written


def to_duckdb(
    tables: Dict[str, Any],
    db_path: Union[str, Path, None] = None,
    *,
    replace: bool = True,
) -> Any:
    """Load tables into a DuckDB database and return the connection.

    Args:
        tables:  Dict mapping table name -> pd.DataFrame.
        db_path: Path for a persistent DuckDB file.  Pass ``None`` or ``":memory:"``
                 for an in-memory database (default: ``None`` = in-memory).
        replace: If ``True`` (default), ``CREATE OR REPLACE TABLE`` is used so
                 existing tables are overwritten.

    Returns:
        An open ``duckdb.DuckDBPyConnection``.  Call ``.close()`` when finished,
        or use it as a context manager.

    Raises:
        ImportError: If ``duckdb`` is not installed.

    Example::

        tables = misata.generate("A fintech company with 2000 customers.", seed=42)
        conn   = misata.to_duckdb(tables)

        result = conn.execute("SELECT COUNT(*) FROM transactions WHERE is_fraud").fetchone()
        print(result[0])  # 400

        conn.close()

    Persistent file::

        conn = misata.to_duckdb(tables, db_path="./analytics.duckdb")
    """
    try:
        import duckdb
    except ImportError as e:
        raise ImportError(
            "duckdb is required for DuckDB export.  Install with: pip install duckdb"
        ) from e

    path_str = str(db_path) if db_path is not None else ":memory:"
    conn = duckdb.connect(path_str)

    for name, df in tables.items():
        verb = "CREATE OR REPLACE TABLE" if replace else "CREATE TABLE IF NOT EXISTS"
        conn.execute(f"{verb} {name} AS SELECT * FROM df")  # noqa: S608 — df is local

    return conn


def to_jsonl(
    tables: Dict[str, Any],
    output_dir: Union[str, Path],
) -> Dict[str, Path]:
    """Write each table to a newline-delimited JSON (JSON Lines) file.

    Args:
        tables:     Dict mapping table name -> pd.DataFrame.
        output_dir: Directory to write ``<table_name>.jsonl`` files into.

    Returns:
        Dict mapping table name -> Path of the written file.

    Example::

        paths = misata.to_jsonl(tables, "./data/")
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: Dict[str, Path] = {}
    for name, df in tables.items():
        path = output_dir / f"{name}.jsonl"
        df.to_json(path, orient="records", lines=True, date_format="iso")
        written[name] = path

    return written
