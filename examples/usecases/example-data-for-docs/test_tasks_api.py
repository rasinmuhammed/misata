"""Tests that run on the recipe's declared data, generated once per session."""

import json
import sqlite3

import pytest

pytestmark = pytest.mark.misata(schema="misata.yaml")


def open_tasks(db_url: str, workspace_id: int) -> list:
    """The code under test: the query behind GET /workspaces/{id}/tasks?open=true."""
    with sqlite3.connect(db_url.removeprefix("sqlite:///")) as conn:
        rows = conn.execute(
            "SELECT task_id, status FROM tasks WHERE workspace_id = ? AND status != 'done'",
            (workspace_id,),
        )
        return rows.fetchall()


def test_open_tasks_leave_out_finished_work(misata_sqlite):
    tasks = open_tasks(misata_sqlite, workspace_id=2)
    assert tasks
    assert all(status in ("todo", "in_progress") for _, status in tasks)


def test_every_assignee_works_in_the_task_workspace(misata_tables):
    workspace_of = misata_tables["users"].set_index("user_id")["workspace_id"]
    tasks = misata_tables["tasks"]
    assert (tasks["assignee_id"].map(workspace_of) == tasks["workspace_id"]).all()


def test_profiles_are_objects_with_a_timezone(misata_tables):
    profiles = misata_tables["users"]["profile"].map(json.loads)
    assert profiles.map(lambda p: "/" in p["timezone"]).all()
