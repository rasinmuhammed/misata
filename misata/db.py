"""
Database seeding utilities for Misata.

Supports SQLite (stdlib) and Postgres (psycopg v3).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from io import StringIO
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import pandas as pd

from misata.schema import SchemaConfig
from misata.simulator import DataSimulator


@dataclass
class SeedReport:
    db_url: str
    dialect: str
    total_rows: int
    table_rows: Dict[str, int]
    created_tables: List[str] = field(default_factory=list)
    truncated_tables: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


def seed_database(
    config: SchemaConfig,
    db_url: str,
    *,
    create: bool = False,
    truncate: bool = False,
    batch_size: int = 10_000,
    smart_mode: bool = False,
    use_llm: bool = True,
) -> SeedReport:
    """
    Seed a database from a SchemaConfig.

    Args:
        config: Schema configuration
        db_url: Database URL
        create: Create tables if missing
        truncate: Truncate tables before insert
        batch_size: Batch size for generation/inserts
        smart_mode: Enable smart value generation
        use_llm: Use LLM-backed pools when smart_mode is True
    """
    start_time = time.time()
    dialect, conn = _connect(db_url)

    try:
        if create:
            created = create_tables(config, conn, dialect)
        else:
            created = []

        if truncate:
            truncated = truncate_tables(config, conn, dialect)
        else:
            truncated = []

        simulator = DataSimulator(
            config,
            batch_size=batch_size,
            smart_mode=smart_mode,
            use_llm=use_llm,
        )

        total_rows = 0
        table_rows: Dict[str, int] = {}
        validated_tables = set()

        for table_name, batch_df in simulator.generate_all():
            if table_name not in validated_tables:
                _validate_table_schema(conn, dialect, table_name, list(batch_df.columns), create)
                validated_tables.add(table_name)

            rows_inserted = _insert_batch(conn, dialect, table_name, batch_df)
            table_rows[table_name] = table_rows.get(table_name, 0) + rows_inserted
            total_rows += rows_inserted

        duration = time.time() - start_time
        return SeedReport(
            db_url=db_url,
            dialect=dialect,
            total_rows=total_rows,
            table_rows=table_rows,
            created_tables=created,
            truncated_tables=truncated,
            duration_seconds=duration,
        )
    finally:
        conn.close()


def seed_database_sqlalchemy(
    config: SchemaConfig,
    engine,
    *,
    create: bool = False,
    truncate: bool = False,
    batch_size: int = 10_000,
    smart_mode: bool = False,
    use_llm: bool = True,
) -> SeedReport:
    """
    Seed a database using a SQLAlchemy engine.
    """
    db_url = str(engine.url)
    return seed_database(
        config,
        db_url,
        create=create,
        truncate=truncate,
        batch_size=batch_size,
        smart_mode=smart_mode,
        use_llm=use_llm,
    )


def seed_from_sqlalchemy_models(
    engine,
    sqlalchemy_obj,
    *,
    default_rows: int = 1000,
    create: bool = False,
    truncate: bool = False,
    batch_size: int = 10_000,
    smart_mode: bool = False,
    use_llm: bool = True,
) -> SeedReport:
    """
    Build a schema from SQLAlchemy models/metadata and seed the database.
    """
    from misata.introspect import schema_from_sqlalchemy

    config = schema_from_sqlalchemy(sqlalchemy_obj, default_rows=default_rows)
    return seed_database_sqlalchemy(
        config,
        engine,
        create=create,
        truncate=truncate,
        batch_size=batch_size,
        smart_mode=smart_mode,
        use_llm=use_llm,
    )


def create_tables(config: SchemaConfig, conn, dialect: str) -> List[str]:
    created: List[str] = []
    for table_name in _topological_sort(config):
        ddl = _build_create_table_sql(config, table_name, dialect)
        _execute(conn, dialect, ddl)
        created.append(table_name)
    return created


def truncate_tables(config: SchemaConfig, conn, dialect: str) -> List[str]:
    truncated: List[str] = []
    for table_name in reversed(_topological_sort(config)):
        if dialect == "postgres":
            sql = f'TRUNCATE TABLE "{table_name}"'
        else:
            sql = f'DELETE FROM "{table_name}"'
        _execute(conn, dialect, sql)
        truncated.append(table_name)
    return truncated


def _connect(db_url: str) -> Tuple[str, object]:
    parsed = urlparse(db_url)
    scheme = parsed.scheme.lower()

    if scheme == "sqlite":
        if parsed.path in ("", "/"):
            raise ValueError("SQLite URL must include a file path, e.g. sqlite:///path/to.db")
        path = parsed.path
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys=ON")
        return "sqlite", conn

    if scheme in ("postgres", "postgresql"):
        try:
            import psycopg  # type: ignore
        except Exception as exc:
            raise ImportError("Postgres driver missing. Install misata[db] (psycopg).") from exc
        conn = psycopg.connect(db_url)
        return "postgres", conn

    raise ValueError(f"Unsupported database scheme: {scheme}")


def _execute(conn, dialect: str, sql: str, params: Optional[Sequence] = None) -> None:
    if dialect == "postgres":
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    else:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()


def _insert_batch(conn, dialect: str, table_name: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    columns = list(df.columns)
    placeholders = ", ".join(["?"] * len(columns)) if dialect == "sqlite" else ", ".join(["%s"] * len(columns))
    col_list = ", ".join([f'"{c}"' for c in columns])
    sql = f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'

    clean_df = df.where(pd.notnull(df), None)

    # Convert datetime/Timestamp columns to ISO strings for SQLite
    for col in clean_df.columns:
        if pd.api.types.is_datetime64_any_dtype(clean_df[col]):
            clean_df[col] = clean_df[col].apply(
                lambda x: x.isoformat() if pd.notnull(x) else None
            )

    rows = list(clean_df.itertuples(index=False, name=None))

    if dialect == "postgres":
        # Try COPY for performance, fallback to executemany
        try:
            csv_buf = StringIO()
            clean_df.to_csv(csv_buf, index=False, header=False)
            csv_buf.seek(0)
            with conn.cursor() as cur:
                copy_sql = f'COPY "{table_name}" ({col_list}) FROM STDIN WITH (FORMAT CSV)'
                cur.copy(copy_sql, csv_buf)
            conn.commit()
            return len(rows)
        except Exception:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()
    else:
        cur = conn.cursor()
        cur.executemany(sql, rows)
        conn.commit()

    return len(rows)


def load_tables_from_db(
    db_url: str,
    *,
    tables: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Load tables from a database into DataFrames.
    """
    dialect, conn = _connect(db_url)
    try:
        if tables is None:
            if dialect == "sqlite":
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = [row[0] for row in cur.fetchall()]
            else:
                sql = """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                """
                with conn.cursor() as cur:
                    cur.execute(sql)
                    tables = [row[0] for row in cur.fetchall()]

        result: Dict[str, pd.DataFrame] = {}
        for table in tables:
            limit_sql = f" LIMIT {limit}" if limit is not None else ""
            query = f'SELECT * FROM "{table}"{limit_sql}'
            result[table] = pd.read_sql_query(query, conn)
        return result
    finally:
        conn.close()


def _validate_table_schema(
    conn,
    dialect: str,
    table_name: str,
    expected_columns: List[str],
    allow_missing: bool,
) -> None:
    actual_columns = _get_table_columns(conn, dialect, table_name)
    if not actual_columns:
        if allow_missing:
            return
        raise ValueError(
            f"Table '{table_name}' not found. Use --db-create to create tables."
        )

    expected_set = set(expected_columns)
    actual_set = set(actual_columns)

    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)

    if missing or extra:
        msg = f"Schema mismatch for table '{table_name}'."
        if missing:
            msg += f" Missing columns: {missing}."
        if extra:
            msg += f" Extra columns: {extra}."
        raise ValueError(msg)


def _get_table_columns(conn, dialect: str, table_name: str) -> List[str]:
    if dialect == "sqlite":
        cur = conn.execute(f'PRAGMA table_info("{table_name}")')
        return [row[1] for row in cur.fetchall()]

    sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s AND table_schema = 'public'
        ORDER BY ordinal_position
    """
    with conn.cursor() as cur:
        cur.execute(sql, (table_name,))
        return [row[0] for row in cur.fetchall()]


def _build_create_table_sql(config: SchemaConfig, table_name: str, dialect: str) -> str:
    columns = config.get_columns(table_name)
    relationships = [r for r in config.relationships if r.child_table == table_name]

    col_defs = []
    for col in columns:
        col_type = _map_type(col.type, dialect)
        col_def = f'"{col.name}" {col_type}'

        if col.name == "id":
            col_def += " PRIMARY KEY"
        elif col.unique:
            col_def += " UNIQUE"

        if not col.nullable and col.name != "id":
            col_def += " NOT NULL"

        col_defs.append(col_def)

    fk_defs = []
    for rel in relationships:
        fk_defs.append(
            f'FOREIGN KEY ("{rel.child_key}") REFERENCES "{rel.parent_table}"("{rel.parent_key}")'
        )

    all_defs = col_defs + fk_defs
    defs_sql = ", ".join(all_defs)
    return f'CREATE TABLE IF NOT EXISTS "{table_name}" ({defs_sql})'


def _map_type(col_type: str, dialect: str) -> str:
    if col_type == "int" or col_type == "foreign_key":
        return "INTEGER"
    if col_type == "float":
        return "DOUBLE PRECISION" if dialect == "postgres" else "REAL"
    if col_type in ("text", "categorical"):
        return "TEXT"
    if col_type == "boolean":
        return "BOOLEAN" if dialect == "postgres" else "INTEGER"
    if col_type == "date":
        return "DATE"
    if col_type == "datetime":
        return "TIMESTAMP"
    if col_type == "time":
        return "TIME"
    return "TEXT"


def _topological_sort(config: SchemaConfig) -> List[str]:
    from collections import defaultdict, deque

    graph = defaultdict(list)
    in_degree = {table.name: 0 for table in config.tables}

    for rel in config.relationships:
        graph[rel.parent_table].append(rel.child_table)
        in_degree[rel.child_table] += 1

    queue = deque([name for name, degree in in_degree.items() if degree == 0])
    sorted_tables: List[str] = []

    while queue:
        table_name = queue.popleft()
        sorted_tables.append(table_name)

        for neighbor in graph[table_name]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_tables) != len(config.tables):
        raise ValueError("Circular dependency detected in relationships.")

    return sorted_tables
