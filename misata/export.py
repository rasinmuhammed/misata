"""
Export utilities for Misata-generated tables.

Supported targets:
  - CSV        (via pandas, always available)
  - Parquet    (via pandas + pyarrow or fastparquet)
  - DuckDB     (via duckdb library)
  - JSON Lines (via pandas; json/array columns written as nested values)
  - Polars     (via polars; json/array columns as structs and lists)
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


def json_columns(df: Any, schema: Any = None, table: Optional[str] = None) -> list:
    """Columns of ``df`` that hold JSON text (``json``/``array`` columns).

    Read from the schema when one is given; otherwise detected from the
    values: a text column whose every non-null value is a JSON object or
    array.
    """
    import json

    import pandas as pd

    if schema is not None and table is not None:
        cols = [c.name for c in (getattr(schema, "columns", {}) or {}).get(table, [])
                if c.type in ("json", "array")]
        return [c for c in cols if c in df.columns]
    found = []
    for col in df.columns:
        s = df[col]
        if not (s.dtype == object or pd.api.types.is_string_dtype(s)):
            continue
        v = s.dropna()
        if v.empty:
            continue
        sample = v.head(50).astype(str)
        if not sample.str.match(r"^\s*[\[{]").all():
            continue
        try:
            for x in sample:
                json.loads(x)
        except (TypeError, ValueError):
            continue
        found.append(col)
    return found


def decode_json_columns(df: Any, schema: Any = None, table: Optional[str] = None) -> Any:
    """A copy of ``df`` with JSON text columns parsed into dicts and lists."""
    import json

    cols = json_columns(df, schema, table)
    if not cols:
        return df
    out = df.copy()
    for col in cols:
        out[col] = out[col].map(lambda x: json.loads(x) if isinstance(x, str) else x)
    return out


def to_jsonl(
    tables: Dict[str, Any],
    output_dir: Union[str, Path],
    schema: Any = None,
) -> Dict[str, Path]:
    """Write each table to a newline-delimited JSON (JSON Lines) file.

    ``json`` and ``array`` columns are written as nested objects and lists,
    not as escaped strings.

    Args:
        tables:     Dict mapping table name -> pd.DataFrame.
        output_dir: Directory to write ``<table_name>.jsonl`` files into.
        schema:     Optional SchemaConfig, to name the nested columns exactly;
                    without it they are detected from the values.

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
        decode_json_columns(df, schema, name).to_json(
            path, orient="records", lines=True, date_format="iso", force_ascii=False)
        written[name] = path

    return written


def to_polars(tables: Dict[str, Any], schema: Any = None) -> Dict[str, Any]:
    """Convert generated tables to Polars DataFrames.

    ``json`` and ``array`` columns become Polars structs and lists. Requires
    ``polars`` (``pip install "misata[polars]"``).

    Example::

        frames = misata.to_polars(misata.generate_from_schema(schema))
        frames["orders"].group_by("customer_id").len()
    """
    try:
        import polars as pl
    except ImportError:
        raise ImportError('to_polars() needs polars: pip install "misata[polars]"') from None
    import json

    out: Dict[str, Any] = {}
    for name, df in tables.items():
        nested = json_columns(df, schema, name)
        plain = df.drop(columns=nested)
        frame = pl.from_pandas(plain)
        for col in nested:
            values = [json.loads(x) if isinstance(x, str) else x for x in df[col]]
            frame = frame.with_columns(pl.Series(col, values, strict=False))
        out[name] = frame.select(list(df.columns))
    return out


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

    dialect = {"postgres": "postgresql", "pg": "postgresql"}.get(
        str(dialect).lower(), str(dialect).lower())

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
            # DOUBLE alone is MySQL; ANSI and Postgres spell it DOUBLE PRECISION.
            return "DOUBLE" if dialect == "mysql" else "DOUBLE PRECISION"
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


def to_seed_sql(
    tables: Dict[str, Any],
    output_path: Union[str, Path],
    *,
    dialect: str = "postgresql",
    config: Optional[Any] = None,
    truncate: bool = False,
) -> Path:
    """Export all tables into a single, topologically sorted SQL seed file.

    Ideal for seeding via `psql < seed.sql` or `sqlite3 app.db < seed.sql` in CI,
    Docker entrypoints, or local development without Python dependencies.

    Args:
        tables:      Dict mapping table name -> pd.DataFrame.
        output_path: Path to the output .sql file (e.g. ``./seed.sql``).
        dialect:     SQL dialect: ``postgresql`` (default), ``sqlite``, ``mysql``, or ``ansi``.
        config:      Optional SchemaConfig to preserve foreign-key topological order.
        truncate:    If True, prepends TRUNCATE/DELETE commands to wipe tables before inserting.

    Returns:
        Path of the generated seed.sql file.
    """
    output_path = Path(output_path)
    if output_path.parent:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    dialect_clean = dialect.lower()
    if dialect_clean in ("postgres", "postgresql"):
        dialect_clean = "postgresql"
    elif dialect_clean == "sqlite":
        dialect_clean = "sqlite"

    def _quote(name: str) -> str:
        if dialect_clean == "mysql":
            return f"`{name.replace('`', '``')}`"
        return f'"{name.replace(chr(34), chr(34)+chr(34))}"'

    # Determine table ordering
    ordered_names: list[str] = []
    if config:
        from misata.db import _topological_sort
        topo = _topological_sort(config)
        for t in topo:
            if t in tables and t not in ordered_names:
                ordered_names.append(t)
    for t in tables:
        if t not in ordered_names:
            ordered_names.append(t)

    lines = [
        "-- -------------------------------------------------------------",
        "-- Misata Generated Seed Script",
        f"-- Dialect: {dialect_clean}",
        f"-- Tables: {len(ordered_names)} ({', '.join(ordered_names)})",
        "-- -------------------------------------------------------------",
        "",
    ]

    # Transaction start
    if dialect_clean == "sqlite":
        lines.append("BEGIN TRANSACTION;")
    else:
        lines.append("BEGIN;")
    lines.append("")

    # Truncate if requested (children first, i.e., reversed order)
    if truncate:
        lines.append("-- Truncate tables before inserting")
        if dialect_clean == "postgresql":
            table_list = ", ".join(_quote(t) for t in reversed(ordered_names))
            lines.append(f"TRUNCATE TABLE {table_list} CASCADE;")
        else:
            for t in reversed(ordered_names):
                lines.append(f"DELETE FROM {_quote(t)};")
        lines.append("")

    import datetime as _dt
    import pandas as _pd

    def _val_to_sql(v) -> str:
        if v is None or v is _pd.NA:
            return "NULL"
        if isinstance(v, float) and v != v:  # NaN
            return "NULL"
        if isinstance(v, bool):
            if dialect_clean == "sqlite":
                return "1" if v else "0"
            return "TRUE" if v else "FALSE"
        if isinstance(v, int):
            return str(v)
        if isinstance(v, float):
            return repr(v)
        if isinstance(v, _dt.datetime):
            ts = v.replace(tzinfo=None) if v.tzinfo else v
            if dialect_clean == "postgresql":
                return f"TIMESTAMP '{ts.isoformat(sep=' ', timespec='seconds')}'"
            return f"'{ts.isoformat(sep=' ', timespec='seconds')}'"
        if isinstance(v, _dt.date):
            if dialect_clean == "postgresql":
                return f"DATE '{v.isoformat()}'"
            return f"'{v.isoformat()}'"
        s = str(v)
        escaped = s.replace("'", "''")
        return f"'{escaped}'"

    for table_name in ordered_names:
        df = tables[table_name]
        if df.empty:
            continue
        lines.append(f"-- Table: {table_name} ({len(df):,} rows)")
        cols_sql = ", ".join(_quote(c) for c in df.columns)
        chunk_size = 500
        for start in range(0, len(df), chunk_size):
            chunk = df.iloc[start : start + chunk_size]
            row_strs = []
            for _, row in chunk.iterrows():
                vals = ", ".join(_val_to_sql(v) for v in row)
                row_strs.append(f"  ({vals})")
            if row_strs:
                lines.append(f"INSERT INTO {_quote(table_name)} ({cols_sql}) VALUES")
                lines.append(",\n".join(row_strs) + ";")
        lines.append("")

    lines.append("COMMIT;")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


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
