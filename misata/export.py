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


# ---------------------------------------------------------------------------
# SQL INSERT export (#12)
# ---------------------------------------------------------------------------

def to_sql(
    tables: Dict[str, Any],
    output_dir: Union[str, Path],
    dialect: str = "ansi",
) -> Dict[str, Path]:
    """Write each table as a .sql file containing CREATE TABLE + INSERT statements.

    Args:
        tables:     Dict mapping table name -> pd.DataFrame.
        output_dir: Directory to write ``<table_name>.sql`` files into.
        dialect:    SQL dialect: ``ansi`` (default), ``mysql``, ``postgresql``.
                    Controls quoting style and type mapping.

    Returns:
        Dict mapping table name -> Path of the written file.

    Example::

        paths = misata.to_sql(tables, "./data/", dialect="postgresql")
    """
    import re

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    def _quote(name: str, dialect: str) -> str:
        # Escape the quote character itself inside the identifier to prevent
        # broken DDL from generated column/table names containing quotes.
        if dialect == "mysql":
            return f"`{name.replace('`', '``')}`"
        return f'"{name.replace(chr(34), chr(34)+chr(34))}"'

    def _py_type_to_sql(dtype, dialect: str) -> str:
        if hasattr(dtype, "name"):
            name = dtype.name
        else:
            name = str(dtype)
        name_lower = name.lower()
        # nullable pandas integers (Int8, Int16, Int32, Int64)
        if name_lower.lstrip("u") in ("int8", "int16", "int32", "int64"):
            return "INTEGER"
        if "int" in name_lower:
            return "INTEGER"
        if "float" in name_lower or "double" in name_lower:
            return "DOUBLE PRECISION" if dialect == "postgresql" else "DOUBLE"
        if "bool" in name_lower:
            return "BOOLEAN"
        if "datetime" in name_lower or "timestamp" in name_lower:
            return "TIMESTAMP"
        if "date" in name_lower:
            return "DATE"
        return "TEXT"

    import datetime as _dt

    def _val_to_sql(v) -> str:
        import pandas as _pd
        if v is None or v is _pd.NA:
            return "NULL"
        if isinstance(v, float) and v != v:   # NaN
            return "NULL"
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, int):
            return str(v)
        if isinstance(v, float):
            return repr(v)
        if isinstance(v, _dt.datetime):
            # Strip timezone — ANSI TIMESTAMP literals have no tz
            ts = v.replace(tzinfo=None) if v.tzinfo else v
            return f"TIMESTAMP '{ts.isoformat(sep=' ', timespec='seconds')}'"
        if isinstance(v, _dt.date):
            return f"DATE '{v.isoformat()}'"
        escaped = str(v).replace("'", "''")
        return f"'{escaped}'"

    written: Dict[str, Path] = {}
    for name, df in tables.items():
        path = output_dir / f"{name}.sql"
        q = lambda n: _quote(n, dialect)
        lines = [f"CREATE TABLE IF NOT EXISTS {q(name)} ("]
        col_defs = []
        for col in df.columns:
            sql_type = _py_type_to_sql(df[col].dtype, dialect)
            col_defs.append(f"    {q(col)} {sql_type}")
        lines.append(",\n".join(col_defs))
        lines.append(");\n")

        cols_sql = ", ".join(q(c) for c in df.columns)
        chunk_size = 500
        for start in range(0, len(df), chunk_size):
            chunk = df.iloc[start:start + chunk_size]
            row_strs = []
            for _, row in chunk.iterrows():
                vals = ", ".join(_val_to_sql(v) for v in row)
                row_strs.append(f"    ({vals})")
            if row_strs:
                lines.append(f"INSERT INTO {q(name)} ({cols_sql}) VALUES")
                lines.append(",\n".join(row_strs) + ";\n")

        path.write_text("\n".join(lines), encoding="utf-8")
        written[name] = path

    return written


# ---------------------------------------------------------------------------
# Apache Arrow IPC export (#12)
# ---------------------------------------------------------------------------

def to_arrow(
    tables: Dict[str, Any],
    output_dir: Union[str, Path],
) -> Dict[str, Path]:
    """Write each table as an Apache Arrow IPC file (.arrow).

    Requires ``pyarrow``. Falls back with ImportError if not installed.

    Args:
        tables:     Dict mapping table name -> pd.DataFrame.
        output_dir: Directory to write ``<table_name>.arrow`` files into.

    Returns:
        Dict mapping table name -> Path of the written file.

    Example::

        paths = misata.to_arrow(tables, "./data/")
    """
    try:
        import pyarrow as pa
        import pyarrow.ipc as ipc
    except ImportError:
        raise ImportError(
            "pyarrow is required for to_arrow(). Install it: pip install pyarrow"
        )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    import datetime as _dt

    written: Dict[str, Path] = {}
    for name, df in tables.items():
        path = output_dir / f"{name}.arrow"
        table = pa.Table.from_pandas(df, preserve_index=False)

        # pa.Table.from_pandas maps datetime64[ns] columns to TimestampType even
        # when the column logically holds calendar dates.  Cast those to date32.
        new_fields = []
        new_columns = []
        for i, field in enumerate(table.schema):
            col = table.column(i)
            if pa.types.is_timestamp(field.type):
                # Check if the underlying pandas column was a date (not datetime)
                pd_col = df[field.name]
                sample = pd_col.dropna().iloc[0] if not pd_col.dropna().empty else None
                if isinstance(sample, _dt.date) and not isinstance(sample, _dt.datetime):
                    col = col.cast(pa.date32())
                    field = field.with_type(pa.date32())
            new_fields.append(field)
            new_columns.append(col)

        table = pa.table(dict(zip([f.name for f in new_fields], new_columns)),
                         schema=pa.schema(new_fields))
        with pa.OSFile(str(path), "wb") as sink:
            with ipc.new_file(sink, table.schema) as writer:
                writer.write_table(table)
        written[name] = path

    return written
