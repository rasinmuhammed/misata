"""
Schema introspection utilities for Misata.

Supports database URLs and SQLAlchemy metadata.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from misata.schema import Column, Relationship, SchemaConfig, Table


def schema_from_db(
    db_url: str,
    *,
    default_rows: int = 1000,
    include_tables: Optional[List[str]] = None,
) -> SchemaConfig:
    from misata.db import _connect  # type: ignore

    dialect, conn = _connect(db_url)
    try:
        if dialect == "sqlite":
            tables = _sqlite_list_tables(conn, include_tables)
            columns_map, relationships = _sqlite_introspect(conn, tables)
        else:
            tables = _postgres_list_tables(conn, include_tables)
            columns_map, relationships = _postgres_introspect(conn, tables)
    finally:
        conn.close()

    table_defs = [Table(name=t, row_count=default_rows) for t in tables]

    return SchemaConfig(
        name="IntrospectedSchema",
        tables=table_defs,
        columns=columns_map,
        relationships=relationships,
    )


def schema_from_sqlalchemy(
    sqlalchemy_obj,
    *,
    default_rows: int = 1000,
) -> SchemaConfig:
    try:
        from sqlalchemy import MetaData  # type: ignore
    except Exception as exc:
        raise ImportError("SQLAlchemy is required. Install misata[orm].") from exc

    metadata = _extract_metadata(sqlalchemy_obj)
    if metadata is None:
        raise ValueError("Could not extract SQLAlchemy MetaData from object.")

    tables = []
    columns_map: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    for table in metadata.sorted_tables:
        tables.append(Table(name=table.name, row_count=default_rows))
        cols: List[Column] = []
        for col in table.columns:
            has_fk = bool(col.foreign_keys)
            col_type = "foreign_key" if has_fk else _map_sqlalchemy_type(col.type)
            params = {}
            cols.append(
                Column(
                    name=col.name,
                    type=col_type,
                    distribution_params=params,
                    nullable=col.nullable,
                    unique=bool(col.unique),
                )
            )

            for fk in col.foreign_keys:
                parent_table = fk.column.table.name
                parent_key = fk.column.name
                relationships.append(
                    Relationship(
                        parent_table=parent_table,
                        child_table=table.name,
                        parent_key=parent_key,
                        child_key=col.name,
                    )
                )
        columns_map[table.name] = cols

    return SchemaConfig(
        name="SQLAlchemySchema",
        tables=tables,
        columns=columns_map,
        relationships=relationships,
    )


def load_sqlalchemy_target(import_path: str):
    import importlib

    if ":" not in import_path:
        raise ValueError("SQLAlchemy target must be in form module:object")

    module_path, attr = import_path.split(":", 1)
    module = importlib.import_module(module_path)
    target = getattr(module, attr, None)
    if target is None:
        raise ValueError(f"Could not import '{attr}' from '{module_path}'")
    return target


def _extract_metadata(obj):
    if hasattr(obj, "metadata"):
        return obj.metadata
    return None


def _sqlite_list_tables(conn, include_tables: Optional[List[str]]) -> List[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = [row[0] for row in cur.fetchall()]
    if include_tables:
        tables = [t for t in tables if t in include_tables]
    return tables


def _sqlite_introspect(conn, tables: List[str]) -> Tuple[Dict[str, List[Column]], List[Relationship]]:
    columns_map: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    for table in tables:
        cur = conn.execute(f'PRAGMA table_info("{table}")')
        cols: List[Column] = []
        for row in cur.fetchall():
            name = row[1]
            sql_type = row[2] or ""
            nullable = row[3] == 0
            is_pk = row[5] == 1
            col_type = _map_sql_type(sql_type)
            cols.append(
                Column(
                    name=name,
                    type=col_type,
                    distribution_params={},
                    nullable=nullable,
                    unique=bool(is_pk),
                )
            )
        columns_map[table] = cols

        fk_cur = conn.execute(f'PRAGMA foreign_key_list("{table}")')
        for fk in fk_cur.fetchall():
            _mark_fk_column(columns_map[table], fk[3])
            relationships.append(
                Relationship(
                    parent_table=fk[2],
                    child_table=table,
                    parent_key=fk[4],
                    child_key=fk[3],
                )
            )

    return columns_map, relationships


def _postgres_list_tables(conn, include_tables: Optional[List[str]]) -> List[str]:
    sql = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        tables = [row[0] for row in cur.fetchall()]
    if include_tables:
        tables = [t for t in tables if t in include_tables]
    return tables


def _postgres_introspect(conn, tables: List[str]) -> Tuple[Dict[str, List[Column]], List[Relationship]]:
    columns_map: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    col_sql = """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
    """
    pk_sql = """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_schema = 'public'
          AND tc.table_name = %s
          AND tc.constraint_type = 'PRIMARY KEY'
    """
    fk_sql = """
        SELECT
            tc.table_name AS child_table,
            kcu.column_name AS child_column,
            ccu.table_name AS parent_table,
            ccu.column_name AS parent_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name = %s
    """

    with conn.cursor() as cur:
        for table in tables:
            cur.execute(pk_sql, (table,))
            pk_cols = {row[0] for row in cur.fetchall()}

            cur.execute(col_sql, (table,))
            cols: List[Column] = []
            for name, data_type, is_nullable in cur.fetchall():
                col_type = _map_sql_type(data_type)
                cols.append(
                    Column(
                        name=name,
                        type=col_type,
                        distribution_params={},
                        nullable=is_nullable == "YES",
                        unique=name in pk_cols,
                    )
                )
            columns_map[table] = cols

            cur.execute(fk_sql, (table,))
            for child_table, child_col, parent_table, parent_col in cur.fetchall():
                _mark_fk_column(columns_map[child_table], child_col)
                relationships.append(
                    Relationship(
                        parent_table=parent_table,
                        child_table=child_table,
                        parent_key=parent_col,
                        child_key=child_col,
                    )
                )

    return columns_map, relationships


def _map_sql_type(sql_type: str) -> str:
    t = sql_type.lower()
    if "int" in t:
        return "int"
    if any(x in t for x in ["numeric", "decimal", "real", "double", "float"]):
        return "float"
    if "bool" in t:
        return "boolean"
    if "timestamp" in t or "datetime" in t:
        return "datetime"
    if t == "date":
        return "date"
    if t == "time":
        return "time"
    return "text"


def _map_sqlalchemy_type(sql_type) -> str:
    t = str(sql_type).lower()
    return _map_sql_type(t)


def _mark_fk_column(columns: List[Column], name: str) -> None:
    for col in columns:
        if col.name == name:
            col.type = "foreign_key"
            break
