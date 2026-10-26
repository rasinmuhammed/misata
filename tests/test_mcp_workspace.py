"""MCP tools only touch paths inside the allowed roots.

Agent arguments can be steered by text the agent has read, so every path a
tool accepts is resolved and checked against the workspace before use.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from misata.mcp import server, workspace  # noqa: E402
from misata.sqlutil import quote_ident  # noqa: E402


def _plain_db(path: Path, rows: int = 3) -> Path:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.executemany("INSERT INTO users (name) VALUES (?)", [(f"u{i}",) for i in range(rows)])
        conn.commit()
    return path


def _count(path: Path) -> int:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]



@pytest.fixture
def jailed(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv(workspace.ROOTS_ENV_VAR, str(root))
    monkeypatch.chdir(root)
    return root


def test_confine_accepts_paths_inside_and_rejects_paths_outside(jailed, tmp_path):
    assert workspace.confine("data") == (jailed / "data").resolve()
    with pytest.raises(workspace.PathNotAllowedError):
        workspace.confine(tmp_path / "elsewhere")
    with pytest.raises(workspace.PathNotAllowedError):
        workspace.confine("../escape")


def test_a_symlink_out_of_the_workspace_is_rejected(jailed, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (jailed / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(workspace.PathNotAllowedError):
        workspace.confine("link/file.db")


def test_filesystem_root_is_never_a_workspace(monkeypatch):
    monkeypatch.delenv(workspace.ROOTS_ENV_VAR, raising=False)
    monkeypatch.chdir(Path.cwd().anchor)
    roots = workspace.allowed_roots()
    assert Path(Path.cwd().anchor) not in roots
    assert workspace.confine("x.db").parent == workspace.workspace()


def test_mcp_sandbox_tools_refuse_paths_outside_the_workspace(jailed, tmp_path):
    victim = _plain_db(tmp_path / "victim.db")
    created = server.create_sandbox(domain="saas", rows=20, db_path=str(victim))
    queried = server.query_sandbox("SELECT 1", db_path=str(victim))
    assert created["ok"] is False and queried["ok"] is False
    assert created["error"] == "PathNotAllowedError"
    assert _count(victim) == 3


def test_mcp_query_sandbox_reports_a_write_attempt(jailed):
    made = server.create_sandbox(domain="saas", rows=20)
    assert made["ok"], made
    table = next(iter(made["tables"]))
    before = server.query_sandbox(f"SELECT COUNT(*) AS n FROM {quote_ident(table)}")
    attack = server.query_sandbox(f"WITH x AS (SELECT 1) DELETE FROM {quote_ident(table)}")
    after = server.query_sandbox(f"SELECT COUNT(*) AS n FROM {quote_ident(table)}")
    assert attack == {**attack, "ok": False, "error": "ReadOnlyViolation"}
    assert before["rows"] == after["rows"]


def test_mcp_dataset_tools_refuse_folders_outside_the_workspace(jailed, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "t.csv").write_text("a\n1\n")
    for result in (server.audit_dataset(str(outside)), server.check_realism(str(outside))):
        assert result["ok"] is False and result["error"] == "PathNotAllowedError"


def test_mcp_generation_refuses_an_output_dir_outside_the_workspace(jailed, tmp_path):
    result = server.generate_dataset(story="A small shop with 50 orders", rows=20, seed=1,
                                     output_dir=str(tmp_path / "out"))
    assert result["ok"] is False and result["error"] == "PathNotAllowedError"
    assert not (tmp_path / "out").exists()


_ATTEST_SCHEMA = {
    "customers": {"__rows__": 40, "customer_id": {"type": "integer", "primary_key": True}},
    "orders": {"__rows__": 120,
               "order_id": {"type": "integer", "primary_key": True},
               "customer_id": {"type": "foreign_key",
                               "foreign_key": {"table": "customers", "column": "customer_id"}}},
}


def test_mcp_attest_dataset_attests_a_generated_folder(jailed):
    pytest.importorskip("duckdb")
    generated = server.generate_from_schema(_ATTEST_SCHEMA, seed=3, output_dir="out")
    assert generated["ok"] is not False, generated
    result = server.attest_dataset("out", _ATTEST_SCHEMA, seed=3)
    assert result["ok"] is True and result["result"] == "PASSED"
    assert result["invariants_held"] == result["invariants_total"] > 0
    assert (jailed / "out" / "attestation.intoto.json").is_file()


def test_mcp_attest_dataset_refuses_a_folder_outside_the_workspace(jailed, tmp_path):
    result = server.attest_dataset(str(tmp_path), _ATTEST_SCHEMA)
    assert result["ok"] is False and result["error"] == "PathNotAllowedError"
