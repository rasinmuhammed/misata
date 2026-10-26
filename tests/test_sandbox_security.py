"""Sandbox and SQL-boundary guarantees.

A sandbox query can never modify a database, a sandbox never replaces a
database Misata did not create, identifiers are always escaped, and MCP tools
only touch paths inside the allowed roots.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from misata.sandbox import (
    NotASandboxError,
    SandboxError,
    create_sandbox,
    query_sandbox,
)
from misata.sqlutil import (
    SQLITE_APPLICATION_ID,
    ReadOnlyViolation,
    connect_sqlite_readonly,
    is_misata_sqlite,
    quote_ident,
    quote_qualified,
)


def _plain_db(path: Path, rows: int = 3) -> Path:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.executemany("INSERT INTO users (name) VALUES (?)", [(f"u{i}",) for i in range(rows)])
        conn.commit()
    return path


def _count(path: Path, table: str = "users") -> int:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0]


# ---------------------------------------------------------------- identifiers

@pytest.mark.parametrize(
    ("name", "dialect", "expected"),
    [
        ("orders", "ansi", '"orders"'),
        ('we"ird', "ansi", '"we""ird"'),
        ('a"; DROP TABLE x; --', "postgres", '"a""; DROP TABLE x; --"'),
        ("tick`s", "mysql", "`tick``s`"),
    ],
)
def test_quote_ident_escapes_the_quote_character(name, dialect, expected):
    assert quote_ident(name, dialect) == expected


@pytest.mark.parametrize("bad", ["", "a\x00b"])
def test_quote_ident_rejects_names_no_engine_accepts(bad):
    with pytest.raises(ValueError):
        quote_ident(bad)


def test_quote_qualified_skips_a_missing_schema():
    assert quote_qualified(None, "t") == '"t"'
    assert quote_qualified("s", 't"x') == '"s"."t""x"'


def test_an_escaped_identifier_round_trips_through_sqlite(tmp_path):
    name = 'x"; DROP TABLE users; --'
    db = _plain_db(tmp_path / "q.db")
    with closing(sqlite3.connect(db)) as conn:
        conn.execute(f"CREATE TABLE {quote_ident(name)} (v INTEGER)")
        conn.execute(f"INSERT INTO {quote_ident(name)} VALUES (1)")
        assert conn.execute(f"SELECT v FROM {quote_ident(name)}").fetchone() == (1,)
    assert _count(db) == 3


# ------------------------------------------------------------ read-only reads

WRITES = [
    "WITH x AS (SELECT 1) DELETE FROM users",
    "DELETE FROM users",
    "UPDATE users SET name = 'x'",
    "INSERT INTO users (name) SELECT name FROM users",
    "DROP TABLE users",
    "CREATE TABLE t (x)",
    "PRAGMA writable_schema = 1",
    "PRAGMA journal_mode = WAL",
    "BEGIN",
    "VACUUM",
    "SELECT load_extension('anything')",
]


@pytest.mark.parametrize("statement", WRITES)
def test_query_sandbox_refuses_every_write(tmp_path, statement):
    db = _plain_db(tmp_path / "s.db")
    with pytest.raises((ReadOnlyViolation, SandboxError)):
        query_sandbox(statement, path=db)
    assert _count(db) == 3


def test_attach_cannot_reach_a_second_file(tmp_path):
    db = _plain_db(tmp_path / "s.db")
    other = tmp_path / "other.db"
    with pytest.raises(ReadOnlyViolation):
        query_sandbox(f"ATTACH DATABASE '{other}' AS o", path=db)
    assert not other.exists()


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT COUNT(*) AS n FROM users",
        "WITH x AS (SELECT id FROM users) SELECT COUNT(*) AS n FROM x",
        "WITH RECURSIVE k(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM k WHERE i < 3) "
        "SELECT MAX(i) AS n FROM k",
        "PRAGMA table_info(users)",
        "SELECT name FROM pragma_table_info('users')",
        "EXPLAIN QUERY PLAN SELECT * FROM users",
    ],
)
def test_query_sandbox_allows_reads(tmp_path, statement):
    db = _plain_db(tmp_path / "s.db")
    assert query_sandbox(statement, path=db).columns


def test_truncated_means_rows_were_left_behind(tmp_path):
    db = _plain_db(tmp_path / "s.db", rows=5)
    assert query_sandbox("SELECT * FROM users", path=db, limit=5).truncated is False
    clipped = query_sandbox("SELECT * FROM users", path=db, limit=4)
    assert clipped.truncated is True and clipped.row_count == 4


@pytest.mark.parametrize("limit", [0, -1, 10_001])
def test_limit_out_of_range_is_refused(tmp_path, limit):
    with pytest.raises(SandboxError):
        query_sandbox("SELECT 1", path=_plain_db(tmp_path / "s.db"), limit=limit)


def test_readonly_connection_never_creates_a_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        connect_sqlite_readonly(tmp_path / "missing.db")
    assert not (tmp_path / "missing.db").exists()


# ------------------------------------------------------------- ownership

def test_create_sandbox_refuses_a_database_it_did_not_create(tmp_path):
    db = _plain_db(tmp_path / "app.db")
    before = db.read_bytes()
    with pytest.raises(NotASandboxError):
        create_sandbox(domain="saas", rows=20, path=db)
    assert db.read_bytes() == before


def test_create_sandbox_refuses_a_file_that_is_not_sqlite(tmp_path):
    notes = tmp_path / "notes.db"
    notes.write_text("not a database")
    with pytest.raises(NotASandboxError):
        create_sandbox(domain="saas", rows=20, path=notes)
    assert notes.read_text() == "not a database"


def test_a_sandbox_is_marked_and_can_be_recreated_cleanly(tmp_path):
    path = tmp_path / "box.db"
    first = create_sandbox(domain="saas", rows=20, seed=1, path=path)
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("PRAGMA application_id").fetchone()[0] == SQLITE_APPLICATION_ID
    assert is_misata_sqlite(path)
    assert first.integrity_verified

    second = create_sandbox(domain="ecommerce", rows=20, seed=1, path=path)
    with closing(sqlite3.connect(path)) as conn:
        on_disk = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert on_disk == set(second.tables)


def test_sandbox_contents_are_reproducible(tmp_path):
    a = create_sandbox(domain="saas", rows=30, seed=7, path=tmp_path / "a.db")
    b = create_sandbox(domain="saas", rows=30, seed=7, path=tmp_path / "b.db")
    table = next(iter(a.tables))
    sql = f"SELECT * FROM {quote_ident(table)} ORDER BY 1"
    assert query_sandbox(sql, path=a.path).rows == query_sandbox(sql, path=b.path).rows


def test_cli_sandbox_runs_without_the_mcp_extra(tmp_path):
    script = (
        "import sys; sys.modules['mcp'] = None\n"
        "from misata.cli import main\n"
        f"main(['sandbox', '--domain', 'saas', '--rows', '20', '--db', r'{tmp_path / 'c.db'}'],"
        " standalone_mode=False)\n"
    )
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                          timeout=300)
    assert done.returncode == 0, done.stderr[-2000:]
    assert is_misata_sqlite(tmp_path / "c.db")
