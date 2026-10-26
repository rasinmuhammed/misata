"""SQL construction and SQLite connection helpers shared across Misata.

Every module that interpolates a table or column name into a statement, or
opens a SQLite file on someone else's behalf, goes through this module so the
rules live in one place:

* Identifiers are quoted with :func:`quote_ident`, which escapes the quote
  character itself. Wrapping a name in quotes without escaping it lets a name
  containing ``"`` end the identifier early.
* A connection that must not write is opened with :func:`connect_sqlite_readonly`.
  Read-only is enforced by SQLite (``mode=ro``, ``query_only`` and an
  authorizer), never by inspecting the statement text, because statement text
  can always be arranged to look like a read.
* A SQLite file created by Misata carries :data:`SQLITE_APPLICATION_ID` in its
  header, so a later call can tell a Misata sandbox from a database that
  belongs to someone else before it truncates anything.
"""

from __future__ import annotations

import math
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Final, Literal, Optional, Union

__all__ = [
    "SQLITE_APPLICATION_ID",
    "Dialect",
    "ReadOnlyViolation",
    "connect_sqlite_readonly",
    "is_misata_sqlite",
    "mark_misata_sqlite",
    "quote_ident",
    "quote_literal",
    "quote_qualified",
]

Dialect = Literal["ansi", "sqlite", "postgres", "duckdb", "mysql", "spark"]

_BACKTICK_DIALECTS: Final[frozenset] = frozenset({"mysql", "spark"})

#: Value written to ``PRAGMA application_id`` in every SQLite file Misata
#: creates. The four bytes spell ``MISA``; SQLite reserves this header field
#: for exactly this purpose (identifying the application that owns the file).
SQLITE_APPLICATION_ID: Final[int] = 0x4D495341

# Statement-level actions a read-only connection may perform. Everything else,
# including ATTACH, transactions, DDL, DML and unknown future actions, is denied.
_READ_ACTIONS: Final[frozenset] = frozenset({
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
})

# Pragmas that only describe the schema. A pragma outside this set may change
# connection or database state (journal_mode, writable_schema, ...).
_READ_PRAGMAS: Final[frozenset] = frozenset({
    "foreign_key_list",
    "index_info",
    "index_list",
    "index_xinfo",
    "table_info",
    "table_list",
    "table_xinfo",
})


class ReadOnlyViolation(sqlite3.DatabaseError):
    """A statement attempted something a read-only connection does not allow."""


def quote_ident(name: str, dialect: Dialect = "ansi") -> str:
    """Quote ``name`` as a SQL identifier, escaping embedded quote characters.

    ANSI SQL, SQLite, PostgreSQL and DuckDB use double quotes and escape a
    double quote by doubling it. MySQL and Spark SQL use backticks with the
    same rule.

    Raises:
        ValueError: ``name`` is empty or contains a NUL byte, which no
            supported engine accepts inside an identifier.
    """
    if not isinstance(name, str) or not name:
        raise ValueError(f"SQL identifier must be a non-empty string, got {name!r}")
    if "\x00" in name:
        raise ValueError(f"SQL identifier contains a NUL byte: {name!r}")
    quote = "`" if dialect in _BACKTICK_DIALECTS else '"'
    return quote + name.replace(quote, quote * 2) + quote


def quote_qualified(*parts: Optional[str], dialect: Dialect = "ansi") -> str:
    """Quote a dotted name such as ``schema.table``, skipping empty parts."""
    present = [p for p in parts if p]
    if not present:
        raise ValueError("a qualified name needs at least one part")
    return ".".join(quote_ident(p, dialect) for p in present)


def quote_literal(value: Any) -> str:
    """Render ``value`` as a self-contained SQL literal.

    Booleans become ``TRUE``/``FALSE``, finite numbers keep their exact
    ``repr``, ``None`` becomes ``NULL`` and everything else is a string literal
    with embedded single quotes doubled.

    Raises:
        ValueError: ``value`` is a NaN or infinite float, which has no portable
            literal form.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return repr(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{value!r} has no portable SQL literal")
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _readonly_authorizer(action: int, arg1: Optional[str], arg2: Optional[str],
                         db_name: Optional[str], trigger: Optional[str]) -> int:
    if action in _READ_ACTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and arg1 and arg1.lower() in _READ_PRAGMAS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def connect_sqlite_readonly(path: Union[str, Path]) -> sqlite3.Connection:
    """Open an existing SQLite file so that no statement can modify anything.

    Three independent layers, each sufficient for ordinary writes on its own:
    the file is opened with ``mode=ro``, the connection sets ``query_only``,
    and an authorizer denies every action that is not a read (which is what
    stops ``ATTACH`` of a second, writable file).

    Raises:
        FileNotFoundError: ``path`` does not exist. ``mode=ro`` never creates
            a file, so this is reported before SQLite is asked.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"no SQLite database at {resolved}")
    conn = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    conn.set_authorizer(_readonly_authorizer)
    return conn


def is_misata_sqlite(path: Union[str, Path]) -> bool:
    """Whether ``path`` may be (re)written as a Misata sandbox.

    True for a missing file, an empty database, or a file whose header carries
    :data:`SQLITE_APPLICATION_ID`. False for any other SQLite database and for
    a file that is not SQLite at all.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return True
    if not resolved.is_file():
        return False
    try:
        with closing(sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)) as conn:
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            if app_id == SQLITE_APPLICATION_ID:
                return True
            tables = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
            ).fetchone()[0]
    except sqlite3.DatabaseError:
        return False
    return bool(app_id == 0 and tables == 0)


def mark_misata_sqlite(conn: sqlite3.Connection) -> None:
    """Stamp the open database as created by Misata."""
    conn.execute(f"PRAGMA application_id = {SQLITE_APPLICATION_ID}")
