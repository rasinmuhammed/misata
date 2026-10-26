"""
Database seeding utilities for Misata.

Supports SQLite (stdlib) and Postgres (psycopg v3).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import pandas as pd

from misata.schema import SchemaConfig
from misata.simulator import DataSimulator
from misata.sqlutil import quote_ident, quote_qualified


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
    append: bool = False,
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
        append: Leave already-populated tables untouched and generate only the
            empty ones, drawing their foreign keys from the existing rows.
    """
    start_time = time.time()
    dialect, conn = _connect(db_url)

    # One transaction for the whole seed: create, truncate and every insert
    # commit together or not at all, so a constraint failure in any table
    # leaves no half-seeded database behind. SQLite and Postgres both roll
    # back DDL, so a failed run leaves nothing behind.
    if dialect == "sqlite":
        conn.isolation_level = None   # manage the transaction explicitly
        conn.execute("BEGIN")
    try:
        if create:
            created = create_tables(config, conn, dialect, commit=False)
        else:
            created = []

        if truncate:
            truncated = truncate_tables(config, conn, dialect, commit=False)
        else:
            truncated = []

        preloaded_context = None
        skip_tables = None
        if append:
            preloaded_context, skip_tables = _load_existing_context(conn, dialect, config)

        # Tables owned by another schema are read, never written. This is not
        # append mode; it applies always, because generating rows for
        # Supabase's `auth.users` would be both wrong and rejected.
        ext_context, ext_skip = _load_external_context(conn, dialect, config)
        if ext_context:
            preloaded_context = {**(preloaded_context or {}), **ext_context}
            skip_tables = (skip_tables or set()) | ext_skip

        simulator = DataSimulator(
            config,
            batch_size=batch_size,
            smart_mode=smart_mode,
            use_llm=use_llm,
            preloaded_context=preloaded_context,
            skip_tables=skip_tables,
        )

        total_rows = 0
        table_rows: Dict[str, int] = {}
        validated_tables = set()

        for table_name, batch_df in simulator.generate_all():
            if table_name not in validated_tables:
                _validate_table_schema(conn, dialect, table_name, list(batch_df.columns), create)
                validated_tables.add(table_name)

            rows_inserted = _insert_batch(conn, dialect, table_name, batch_df, commit=False)
            table_rows[table_name] = table_rows.get(table_name, 0) + rows_inserted
            total_rows += rows_inserted

        # Postgres identity/serial sequences do not advance when explicit key
        # values are inserted, so the app's next insert would collide. Realign
        # each sequence to its column's current max. (SQLite rowids advance on
        # their own.)
        if dialect == "postgres" and table_rows:
            _reset_postgres_sequences(conn, list(table_rows.keys()))

        if dialect == "sqlite":
            conn.execute("COMMIT")
        else:
            conn.commit()
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
    except BaseException:
        try:
            if dialect == "sqlite":
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
            else:
                conn.rollback()
        except Exception:  # noqa: BLE001 - cleanup must not mask the original error
            pass
        raise
    finally:
        conn.close()


class _Savepoint:
    """A statement that may fail without aborting the seed's transaction.

    Postgres marks the whole transaction aborted after any failed statement,
    so a probe that is allowed to fail (a COUNT on a table that may not
    exist, a COPY with an executemany fallback) runs inside a savepoint.
    SQLite needs nothing: a failed statement leaves its transaction usable.
    """

    def __init__(self, conn, dialect: str, name: str = "misata_sp"):
        self.conn, self.dialect, self.name = conn, dialect, name

    def __enter__(self):
        if self.dialect == "postgres":
            with self.conn.cursor() as cur:
                cur.execute(f"SAVEPOINT {self.name}")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.dialect != "postgres":
            return False
        with self.conn.cursor() as cur:
            if exc_type is None:
                cur.execute(f"RELEASE SAVEPOINT {self.name}")
            else:
                cur.execute(f"ROLLBACK TO SAVEPOINT {self.name}")
                cur.execute(f"RELEASE SAVEPOINT {self.name}")
        return False


def _load_external_context(conn, dialect: str, config: SchemaConfig):
    """Read the real keys of tables owned by another schema.

    Supabase is the case this exists for. Every project has
    ``public.profiles.id`` referencing ``auth.users.id``, and auth rows belong
    to the auth service: you cannot invent them, and inserting a profile whose
    id is not already an auth user fails the foreign key. So read the ids that
    exist and let children draw from those.

    Raises if such a table is empty, because there is no honest way to continue:
    every child row would violate its foreign key.
    """
    external = [t for t in config.tables if t.external_schema]
    if not external:
        return {}, set()

    keys_needed: Dict[str, set] = {}
    for rel in config.relationships:
        keys_needed.setdefault(rel.parent_table, set()).add(rel.parent_key)

    preloaded: Dict[str, pd.DataFrame] = {}
    for table in external:
        qualified = quote_qualified(table.external_schema, table.name)
        cols = sorted(keys_needed.get(table.name, {"id"}))
        col_list = ", ".join(quote_ident(c) for c in cols)
        df = pd.read_sql_query(f"SELECT {col_list} FROM {qualified}", conn)
        if df.empty:
            raise ValueError(
                f"{table.external_schema}.{table.name} has no rows, and "
                f"{', '.join(sorted({r.child_table for r in config.relationships if r.parent_table == table.name}))} "
                f"references it. Every row generated would violate that foreign "
                f"key, so there is nothing valid to insert.\n\n"
                f"Create some {table.external_schema}.{table.name} rows first. On "
                f"Supabase that means signing up a few users (the dashboard, the "
                f"admin API, or `supabase auth` in the CLI), then run this again."
            )
        # The FK sampler's fast path looks for "id".
        if "id" not in df.columns and len(cols) == 1:
            df = df.rename(columns={cols[0]: "id"}).assign(**{cols[0]: df[cols[0]]})
        preloaded[table.name] = df

    return preloaded, {t.name for t in external}


def _load_existing_context(conn, dialect: str, config: SchemaConfig):
    """For append mode: load the key columns of already-populated tables so
    generated children can reference their real rows. Returns
    (preloaded_context, skip_tables)."""
    # Which key columns does each parent table expose to children?
    keys_needed: Dict[str, set] = {}
    for rel in config.relationships:
        keys_needed.setdefault(rel.parent_table, set()).add(rel.parent_key)
    preloaded: Dict[str, pd.DataFrame] = {}
    skip: set = set()
    for table in config.tables:
        name = table.name
        try:
            with _Savepoint(conn, dialect):
                count = _count_rows(conn, dialect, name)
        except Exception:  # noqa: BLE001 - a table the driver cannot count is treated as empty
            count = 0
        if count == 0:
            continue
        skip.add(name)
        cols = set(keys_needed.get(name, set()))
        cols.add("id")  # FK sampling fast-path uses "id"
        col_list = ", ".join(quote_ident(c) for c in sorted(cols))
        try:
            with _Savepoint(conn, dialect):
                query = f"SELECT {col_list} FROM {quote_ident(name)}"
                preloaded[name] = pd.read_sql_query(query, conn)
        except Exception:  # noqa: BLE001 - any driver error falls back to loading every column
            # A key column that doesn't exist (composite/renamed PK): load all.
            try:
                with _Savepoint(conn, dialect):
                    preloaded[name] = pd.read_sql_query(f"SELECT * FROM {quote_ident(name)}", conn)
            except Exception:  # noqa: BLE001 - an unreadable table is generated normally
                skip.discard(name)  # can't load it; let normal path handle
    return preloaded, skip


def _count_rows(conn, dialect: str, table: str) -> int:
    """Number of rows in ``table`` on an open SQLite or Postgres connection."""
    sql = f"SELECT COUNT(*) FROM {quote_ident(table)}"
    if dialect == "postgres":
        with conn.cursor() as cur:
            cur.execute(sql)
            return int(cur.fetchone()[0])
    return int(conn.execute(sql).fetchone()[0])


def _reset_postgres_sequences(conn, tables: Sequence[str]) -> None:
    """Advance each table's identity/serial sequence to its column max, so the
    application's next INSERT does not collide with a seeded key."""
    for name in tables:
        try:
            with _Savepoint(conn, "postgres", "misata_seq"), conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT a.attname
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    WHERE c.relname = %s
                      AND a.attnum > 0
                      AND NOT a.attisdropped
                      AND pg_get_serial_sequence(%s, a.attname) IS NOT NULL
                    """,
                    (name, name),
                )
                cols = [r[0] for r in cur.fetchall()]
                for col in cols:
                    cur.execute(
                        "SELECT setval(pg_get_serial_sequence(%s, %s), "
                        f"COALESCE((SELECT MAX({quote_ident(col)}) FROM {quote_ident(name)}), 1))",
                        (name, col),
                    )
        except Exception:  # noqa: BLE001 - realignment is best-effort
            # Sequence realignment is best-effort; never fail the seed over it.
            pass


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


def create_tables(config: SchemaConfig, conn, dialect: str, commit: bool = True) -> List[str]:
    created: List[str] = []
    for table_name in _topological_sort(config):
        ddl = _build_create_table_sql(config, table_name, dialect)
        _execute(conn, dialect, ddl, commit=commit)
        created.append(table_name)
    return created


def truncate_tables(config: SchemaConfig, conn, dialect: str, commit: bool = True) -> List[str]:
    """Empty every schema table, children first.

    On Postgres this is one ``TRUNCATE`` naming all the tables: truncating them
    one at a time fails as soon as a parent is referenced by a foreign key,
    even from a child that was already emptied, while a single statement may
    truncate a set of tables that reference each other. ``CASCADE`` is
    deliberately not used: it would also empty tables outside the schema that
    happen to reference these, which is someone else's data.
    """
    order = [t for t in reversed(_topological_sort(config))
             if not _is_external(config, t)]
    if dialect == "postgres":
        if order:
            names = ", ".join(quote_ident(t) for t in order)
            _execute(conn, dialect, f"TRUNCATE TABLE {names}", commit=commit)
        return order
    for table_name in order:
        _execute(conn, dialect, f"DELETE FROM {quote_ident(table_name)}", commit=commit)
    return order


def _is_external(config: SchemaConfig, table_name: str) -> bool:
    return any(t.name == table_name and t.external_schema for t in config.tables)


def _connect(db_url: str) -> Tuple[str, Any]:
    parsed = urlparse(db_url)
    scheme = parsed.scheme.lower()

    if scheme == "sqlite":
        if parsed.path in ("", "/"):
            raise ValueError("SQLite URL must include a file path, e.g. sqlite:///path/to.db")
        # SQLAlchemy's convention: three slashes then a relative path
        # (sqlite:///dev.db is ./dev.db), four for an absolute one
        # (sqlite:////var/data/dev.db).
        path = parsed.path[1:] if not parsed.netloc else parsed.path
        if path == ":memory:" or path.startswith("file:"):
            pass
        elif not path:
            raise ValueError("SQLite URL must include a file path, e.g. sqlite:///path/to.db")
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys=ON")
        return "sqlite", conn

    if scheme in ("postgres", "postgresql"):
        try:
            import psycopg  # type: ignore
        except ImportError as exc:
            raise ImportError("Postgres driver missing. Install misata[db] (psycopg).") from exc
        conn = psycopg.connect(db_url)
        return "postgres", conn

    raise ValueError(f"Unsupported database scheme: {scheme}")


def _execute(conn, dialect: str, sql: str, params: Optional[Sequence] = None,
             commit: bool = True) -> None:
    if dialect == "postgres":
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
    else:
        cur = conn.cursor()
        cur.execute(sql, params or ())
    if commit and (dialect == "postgres" or conn.in_transaction):
        conn.commit()


def _insert_batch(conn, dialect: str, table_name: str, df: pd.DataFrame,
                  commit: bool = True) -> int:
    if df.empty:
        return 0

    columns = list(df.columns)
    marker = "?" if dialect == "sqlite" else "%s"
    placeholders = ", ".join([marker] * len(columns))
    col_list = ", ".join(quote_ident(c) for c in columns)
    sql = f"INSERT INTO {quote_ident(table_name)} ({col_list}) VALUES ({placeholders})"

    clean_df = df.where(pd.notnull(df), None)

    # Convert datetime/Timestamp columns to ISO strings for SQLite
    for col in clean_df.columns:
        if pd.api.types.is_datetime64_any_dtype(clean_df[col]):
            clean_df[col] = clean_df[col].apply(
                lambda x: x.isoformat() if pd.notnull(x) else None
            )

    rows = list(clean_df.itertuples(index=False, name=None))

    if dialect == "postgres":
        # COPY for speed, executemany as the fallback.
        #
        # psycopg3's `cur.copy()` takes query parameters as its second
        # argument and returns a context manager that moves no data until it
        # is entered, so the CSV is written into the entered context.
        # A savepoint, not a rollback: rolling back the failed COPY must not
        # also discard every batch already inserted in this transaction.
        try:
            csv_buf = StringIO()
            clean_df.to_csv(csv_buf, index=False, header=False)
            with _Savepoint(conn, dialect, "misata_copy"), conn.cursor() as cur:
                copy_sql = (f"COPY {quote_ident(table_name)} ({col_list}) "
                            "FROM STDIN WITH (FORMAT CSV)")
                with cur.copy(copy_sql) as copy:
                    copy.write(csv_buf.getvalue())
        except Exception:  # noqa: BLE001 - any COPY failure falls back to executemany
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        if commit:
            conn.commit()
    else:
        cur = conn.cursor()
        cur.executemany(sql, rows)
        if commit and conn.in_transaction:
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
            limit_sql = f" LIMIT {int(limit)}" if limit is not None else ""
            query = f"SELECT * FROM {quote_ident(table)}{limit_sql}"
            if dialect == "sqlite":
                result[table] = pd.read_sql_query(query, conn)
                continue
            with conn.cursor() as cur:
                cur.execute(query)
                columns = [d[0] for d in cur.description or []]
                result[table] = pd.DataFrame(cur.fetchall(), columns=columns)
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
        cur = conn.execute(f"PRAGMA table_info({quote_ident(table_name)})")
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
        col_def = f"{quote_ident(col.name)} {col_type}"

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
            f"FOREIGN KEY ({quote_ident(rel.child_key)}) "
            f"REFERENCES {quote_ident(rel.parent_table)}({quote_ident(rel.parent_key)})"
        )

    all_defs = col_defs + fk_defs
    defs_sql = ", ".join(all_defs)
    return f"CREATE TABLE IF NOT EXISTS {quote_ident(table_name)} ({defs_sql})"


def _map_type(col_type: str, dialect: str) -> str:
    if col_type == "int" or col_type == "foreign_key":
        return "INTEGER"
    if col_type == "float":
        return "DOUBLE PRECISION" if dialect == "postgres" else "REAL"
    if col_type in ("text", "categorical"):
        return "TEXT"
    if col_type in ("json", "array"):
        # Values are canonical JSON text, which both accept.
        return "JSONB" if dialect == "postgres" else "TEXT"
    if col_type == "boolean":
        return "BOOLEAN" if dialect == "postgres" else "INTEGER"
    if col_type == "date":
        return "DATE"
    if col_type == "datetime":
        return "TIMESTAMP"
    if col_type == "time":
        return "TIME"
    return "TEXT"


@dataclass
class RelationshipIntegrity:
    parent_table: str
    parent_key: str
    child_table: str
    child_key: str
    orphans: int

    @property
    def intact(self) -> bool:
        return self.orphans == 0

    @property
    def label(self) -> str:
        return f"{self.child_table}.{self.child_key} → {self.parent_table}.{self.parent_key}"


@dataclass
class IntegrityReport:
    relationships: List[RelationshipIntegrity] = field(default_factory=list)
    # Relationships that could not be checked, and why. Kept separate from the
    # ones that passed: a check that did not run is not a check that passed.
    skipped: List[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        # `all([])` is True, so an empty result is handled first: it means the
        # verifier did not run, not that the data is clean.
        if not self.relationships:
            return False
        return all(r.intact for r in self.relationships)

    @property
    def complete(self) -> bool:
        """True when every declared relationship was actually queried."""
        return bool(self.relationships) and not self.skipped

    @property
    def total_orphans(self) -> int:
        return sum(r.orphans for r in self.relationships)


def verify_referential_integrity(config: SchemaConfig, db_url: str) -> IntegrityReport:
    """Query the live database and confirm every foreign key resolves.

    For each declared relationship, count child rows whose (non-null) foreign
    key has no matching parent. Zero orphans across the board means the seeded
    data is referentially intact *in the database itself*, not just in memory.
    """
    dialect, conn = _connect(db_url)
    report = IntegrityReport()
    # A parent living in another schema is named with it; otherwise the query
    # looks in `public` and errors, and on Postgres that error aborts the
    # transaction for every remaining check.
    schema_of = {t.name: t.external_schema for t in config.tables if t.external_schema}
    try:
        for rel in config.relationships:
            parent = rel.parent_table
            qualified = quote_qualified(schema_of.get(parent), parent)
            child_key = quote_ident(rel.child_key)
            sql = (
                f"SELECT COUNT(*) FROM {quote_ident(rel.child_table)} c "
                f"WHERE c.{child_key} IS NOT NULL "
                f"AND NOT EXISTS (SELECT 1 FROM {qualified} p "
                f"WHERE p.{quote_ident(rel.parent_key)} = c.{child_key})"
            )
            try:
                if dialect == "postgres":
                    with conn.cursor() as cur:
                        cur.execute(sql)
                        orphans = int(cur.fetchone()[0])
                else:
                    orphans = int(conn.execute(sql).fetchone()[0])
            except Exception as exc:  # noqa: BLE001 - an uncheckable relationship is reported as skipped
                # A relationship we cannot check (a view, a table we lack rights
                # to) is recorded as skipped, never as a pass. Roll back first:
                # in Postgres a failed statement poisons the transaction for
                # every later check.
                if dialect == "postgres":
                    try:
                        conn.rollback()
                    except Exception:  # noqa: BLE001 - the skip is recorded either way
                        pass
                report.skipped.append(
                    f"{rel.child_table}.{rel.child_key} -> {parent}.{rel.parent_key}: "
                    f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
                )
                continue
            report.relationships.append(
                RelationshipIntegrity(
                    parent_table=rel.parent_table,
                    parent_key=rel.parent_key,
                    child_table=rel.child_table,
                    child_key=rel.child_key,
                    orphans=orphans,
                )
            )
        return report
    finally:
        conn.close()


def table_row_counts(db_url: str, tables: Sequence[str]) -> Dict[str, int]:
    """Current row count for each named table (missing tables report as 0)."""
    dialect, conn = _connect(db_url)
    counts: Dict[str, int] = {}
    try:
        for name in tables:
            try:
                counts[name] = _count_rows(conn, dialect, name)
            except Exception:  # noqa: BLE001 - a missing table reports as 0
                counts[name] = 0
        return counts
    finally:
        conn.close()


def mask_db_url(db_url: str) -> str:
    """Mask the password in a database connection URL for safe logging and display."""
    try:
        parsed = urlparse(db_url)
        if parsed.password:
            user = parsed.username or ""
            netloc = f"{user}:***@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return parsed._replace(netloc=netloc).geturl()
    except (ValueError, TypeError):
        pass
    return db_url


def find_database_url() -> Optional[Tuple[str, str]]:
    """Auto-detect database URL from environment (.env), prisma schema, or local SQLite files.

    Returns:
        (db_url, source_description) or None
    """
    import os
    import re
    from pathlib import Path

    # 1. Try loading .env from current working directory or parents
    try:
        import dotenv
        env_path = dotenv.find_dotenv(usecwd=True)
        if env_path:
            dotenv.load_dotenv(env_path)
    except Exception:  # noqa: BLE001 - .env loading is optional and never blocks detection
        pass

    # 2. Check standard environment variables
    for var in ("DATABASE_URL", "POSTGRES_URL", "SUPABASE_DB_URL", "SQLITE_URL"):
        val = os.environ.get(var)
        if val and any(val.startswith(p) for p in ("postgres://", "postgresql://", "sqlite://")):
            return val, f"{var} in .env"

    # 3. Check for Prisma schema
    prisma_candidates = [Path("prisma/schema.prisma"), Path("schema.prisma")]
    for p in prisma_candidates:
        if p.exists():
            try:
                text = p.read_text(encoding="utf-8")
                url_match = re.search(r'url\s*=\s*(?:env\(["\']([^"\']+)["\']\)|["\']([^"\']+)["\'])', text)
                if url_match:
                    env_name, direct_val = url_match.groups()
                    if env_name and os.environ.get(env_name):
                        return os.environ[env_name], f"env('{env_name}') in {p}"
                    elif direct_val:
                        if direct_val.startswith("file:"):
                            rel_path = direct_val[5:].lstrip("/")
                            sqlite_path = (p.parent / rel_path).resolve()
                            return f"sqlite:///{sqlite_path}", f"sqlite datasource in {p}"
                        elif direct_val.startswith("postgres://") or direct_val.startswith("postgresql://"):
                            return direct_val, f"datasource in {p}"
            except (OSError, RuntimeError, ValueError):
                pass

    # 4. Check for local SQLite database files in common project locations
    local_sqlite_candidates = [
        "dev.db", "local.db", "app.db", "development.db",
        "prisma/dev.db", "db/development.sqlite3", "storage/development.sqlite3",
    ]
    for rel in local_sqlite_candidates:
        f = Path(rel)
        if f.is_file() and f.stat().st_size > 0:
            return f"sqlite:///{f.resolve()}", f"local file {rel}"

    return None


def _topological_sort(config: SchemaConfig) -> List[str]:
    from collections import defaultdict, deque

    graph = defaultdict(list)
    in_degree = {table.name: 0 for table in config.tables}

    # Map relationships, skipping self-referential foreign keys
    for rel in config.relationships:
        if rel.parent_table == rel.child_table:
            continue
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

    # If circular dependencies exist across distinct tables, break them gracefully
    if len(sorted_tables) != len(config.tables):
        remaining = [t.name for t in config.tables if t.name not in sorted_tables]
        while remaining:
            best_table = min(remaining, key=lambda t: in_degree.get(t, 0))
            sorted_tables.append(best_table)
            remaining.remove(best_table)
            for neighbor in graph[best_table]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] <= 0 and neighbor in remaining:
                    queue.append(neighbor)
            while queue:
                next_tbl = queue.popleft()
                if next_tbl in remaining:
                    sorted_tables.append(next_tbl)
                    remaining.remove(next_tbl)
                    for neighbor in graph[next_tbl]:
                        in_degree[neighbor] -= 1
                        if in_degree[neighbor] <= 0 and neighbor in remaining:
                            queue.append(neighbor)

    return sorted_tables
