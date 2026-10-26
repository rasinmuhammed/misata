"""Throwaway SQLite databases seeded with relational data, for testing queries.

A sandbox is a SQLite file that Misata created and therefore owns. Ownership
is recorded in the file header (see :mod:`misata.sqlutil`), and it is what
makes recreating a sandbox safe: :func:`create_sandbox` replaces a file only
when that file is missing, empty, or already a Misata sandbox, and refuses any
other database rather than truncating it.

:func:`query_sandbox` runs one statement on a connection that SQLite itself
keeps read-only, so the guarantee does not depend on how the statement is
written.

Both functions are used by ``misata sandbox`` and by the MCP server's
``create_sandbox`` and ``query_sandbox`` tools.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple, Union

from misata.exceptions import MisataError
from misata.sqlutil import (
    ReadOnlyViolation,
    connect_sqlite_readonly,
    is_misata_sqlite,
    mark_misata_sqlite,
    quote_ident,
)

if TYPE_CHECKING:
    from misata.schema import SchemaConfig

__all__ = [
    "DEFAULT_SANDBOX_PATH",
    "MAX_QUERY_ROWS",
    "NotASandboxError",
    "QueryResult",
    "Sandbox",
    "SandboxError",
    "create_sandbox",
    "query_sandbox",
]

DEFAULT_SANDBOX_PATH = Path(".misata") / "sandbox.db"

#: Upper bound on rows returned by one :func:`query_sandbox` call.
MAX_QUERY_ROWS = 10_000

_DEFAULT_DOMAIN = "saas"
_TEMPLATE_BASE_ROWS = 500
_SQLITE_SIDECARS = ("-journal", "-wal", "-shm")


class SandboxError(MisataError):
    """A sandbox could not be created or queried."""


class NotASandboxError(SandboxError):
    """The target path holds a database that Misata did not create."""


@dataclass(frozen=True)
class SandboxTable:
    """Shape of one table in a sandbox."""

    rows: int
    columns: Tuple[str, ...]


@dataclass(frozen=True)
class Sandbox:
    """A created sandbox and everything needed to start querying it."""

    path: Path
    tables: Mapping[str, SandboxTable]
    total_rows: int
    foreign_keys: int
    integrity_verified: bool
    ddl: str
    sample_queries: Tuple[str, ...]

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.path}"


@dataclass(frozen=True)
class QueryResult:
    """Rows returned by :func:`query_sandbox`."""

    columns: Tuple[str, ...]
    rows: Tuple[Dict[str, Any], ...]
    truncated: bool

    @property
    def row_count(self) -> int:
        return len(self.rows)


def create_sandbox(
    *,
    domain: Optional[str] = None,
    story: Optional[str] = None,
    schema: Optional[Dict[str, Any]] = None,
    rows: int = 100,
    seed: int = 42,
    path: Union[str, Path] = DEFAULT_SANDBOX_PATH,
) -> Sandbox:
    """Create (or recreate) a seeded SQLite sandbox.

    The schema comes from the first of ``schema``, a built-in ``domain``
    template, or a ``story``; with none of them the SaaS template is used.

    Args:
        domain: Built-in template name (``saas``, ``ecommerce``, ``fintech``,
            ``healthcare``, ...).
        story: Plain-English description parsed by Misata's story parser.
        schema: A dict schema, as accepted by :func:`misata.generate_from_schema`.
        rows: Base row count. Template tables scale relative to it.
        seed: Seed for reproducible contents.
        path: Where to write the database. An existing file there must be a
            Misata sandbox or an empty database.

    Raises:
        NotASandboxError: ``path`` holds a database Misata did not create.
        SandboxError: the schema could not be built or seeded.
    """
    from misata.db import create_tables, seed_database, verify_referential_integrity

    if rows < 1:
        raise SandboxError(f"rows must be at least 1, got {rows}")
    target = Path(path).expanduser().resolve()
    if not is_misata_sqlite(target):
        raise NotASandboxError(
            f"{target} is a database that Misata did not create. A sandbox replaces "
            "its file, so choose a new path, or remove this one yourself if it is "
            "disposable."
        )

    config = _resolve_schema(domain=domain, story=story, schema=schema, rows=rows)
    config.seed = seed

    target.parent.mkdir(parents=True, exist_ok=True)
    _remove_database(target)
    with closing(sqlite3.connect(target)) as conn:
        mark_misata_sqlite(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        create_tables(config, conn, "sqlite")
        conn.commit()

    db_url = f"sqlite:///{target}"
    try:
        report = seed_database(config, db_url, create=False, truncate=False,
                               smart_mode=False, use_llm=False)
        integrity = verify_referential_integrity(config, db_url)
    except MisataError:
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced as one typed error to callers
        raise SandboxError(f"could not seed the sandbox: {exc}") from exc

    tables, ddl = _describe(target, report.table_rows)
    return Sandbox(
        path=target,
        tables=tables,
        total_rows=report.total_rows,
        foreign_keys=len(config.relationships),
        integrity_verified=integrity.verified,
        ddl=ddl,
        sample_queries=_sample_queries(tables, config),
    )


def query_sandbox(
    sql: str,
    *,
    path: Union[str, Path] = DEFAULT_SANDBOX_PATH,
    limit: int = 100,
) -> QueryResult:
    """Run one read-only statement against a sandbox.

    Args:
        sql: A single SQL statement. Anything that would modify the database,
            attach another file or change connection state is refused by
            SQLite before it runs.
        path: The sandbox file.
        limit: Maximum rows to return, between 1 and :data:`MAX_QUERY_ROWS`.

    Raises:
        FileNotFoundError: there is no database at ``path``.
        ReadOnlyViolation: the statement tried to write or change state.
        SandboxError: ``limit`` is out of range, or SQLite rejected the query.
    """
    if not 1 <= limit <= MAX_QUERY_ROWS:
        raise SandboxError(f"limit must be between 1 and {MAX_QUERY_ROWS}, got {limit}")
    statement = sql.strip().rstrip(";").strip()
    if not statement:
        raise SandboxError("the query is empty")

    with closing(connect_sqlite_readonly(path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(statement)
        except sqlite3.DatabaseError as exc:
            if "not authorized" in str(exc):
                raise ReadOnlyViolation(
                    "the statement would modify the database or its connection; "
                    "query_sandbox runs reads only"
                ) from exc
            raise SandboxError(str(exc)) from exc
        fetched = cursor.fetchmany(limit + 1)
        columns = tuple(d[0] for d in cursor.description or ())

    truncated = len(fetched) > limit
    rows = tuple({k: _json_safe(row[k]) for k in row.keys()} for row in fetched[:limit])
    return QueryResult(columns=columns, rows=rows, truncated=truncated)


def _resolve_schema(*, domain: Optional[str], story: Optional[str],
                    schema: Optional[Dict[str, Any]], rows: int) -> "SchemaConfig":
    from misata.templates.library import list_templates, load_template

    if schema:
        from misata.compat import from_dict_schema

        return from_dict_schema(schema)
    templates = set(list_templates())
    name = domain.lower() if domain else None
    if name in templates or not story:
        chosen = name if name in templates else _DEFAULT_DOMAIN
        return load_template(chosen, row_multiplier=max(0.1, rows / _TEMPLATE_BASE_ROWS))
    from misata.story_parser import StoryParser

    return StoryParser().parse(story, default_rows=rows)


def _remove_database(target: Path) -> None:
    for suffix in ("",) + _SQLITE_SIDECARS:
        Path(f"{target}{suffix}").unlink(missing_ok=True)


def _describe(target: Path, row_counts: Mapping[str, int]) -> Tuple[Dict[str, SandboxTable], str]:
    tables: Dict[str, SandboxTable] = {}
    ddl: List[str] = []
    with closing(connect_sqlite_readonly(target)) as conn:
        for name, create_sql in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' ORDER BY rowid"
        ):
            columns = tuple(
                r[1] for r in conn.execute(f"PRAGMA table_info({quote_ident(name)})")
            )
            tables[name] = SandboxTable(rows=int(row_counts.get(name, 0)), columns=columns)
            if create_sql:
                ddl.append(f"{create_sql};")
    return tables, "\n\n".join(ddl)


def _sample_queries(tables: Mapping[str, SandboxTable],
                    config: "SchemaConfig") -> Tuple[str, ...]:
    queries = [f"SELECT * FROM {quote_ident(t)} LIMIT 3;" for t in tables]
    for rel in config.relationships[:3]:
        queries.append(
            f"SELECT p.*, c.* FROM {quote_ident(rel.parent_table)} p "
            f"JOIN {quote_ident(rel.child_table)} c "
            f"ON p.{quote_ident(rel.parent_key)} = c.{quote_ident(rel.child_key)} LIMIT 3;"
        )
    return tuple(queries)


def _json_safe(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value
