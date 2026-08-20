"""MCP tool annotations must describe what the tools actually do.

Clients use these hints to decide what to auto-approve. A tool marked
readOnlyHint that writes files to disk, or openWorldHint=False on one that
calls a remote API, is not a cosmetic slip: it is a wrong answer to "is it safe
to run this without asking the user". These started out wrong in exactly that
direction, which is why they are pinned.
"""

import asyncio

import pytest

from misata.mcp.server import mcp


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in asyncio.run(mcp.list_tools())}


def test_every_tool_declares_all_four_hints(tools):
    assert tools, "the server exposes no tools"
    for name, tool in tools.items():
        a = tool.annotations
        assert a is not None, f"{name} has no annotations"
        for hint in ("readOnlyHint", "destructiveHint",
                     "idempotentHint", "openWorldHint"):
            assert getattr(a, hint) is not None, \
                f"{name}.{hint} is unset, so a client has to guess"


@pytest.mark.parametrize("name", ["generate_dataset", "generate_from_schema"])
def test_tools_that_can_write_files_are_not_read_only(tools, name):
    """Both take `output_dir` and write CSVs into it."""
    assert tools[name].annotations.readOnlyHint is False


@pytest.mark.parametrize("name", ["preview_story", "inspect_schema",
                                  "generate_dataset", "seed_database"])
def test_tools_that_reach_outside_say_so(tools, name):
    """Three of these call an LLM provider; the fourth opens a database
    connection. None of them is a closed-world computation."""
    assert tools[name].annotations.openWorldHint is True


def test_seeding_a_database_is_flagged_destructive(tools):
    a = tools["seed_database"].annotations
    assert a.destructiveHint is True
    assert a.readOnlyHint is False
    assert a.idempotentHint is False, \
        "it can truncate and re-insert, so running it twice is not a no-op"


@pytest.mark.parametrize("name", ["list_domains", "validate_yaml",
                                  "generate_from_schema"])
def test_deterministic_tools_are_idempotent(tools, name):
    assert tools[name].annotations.idempotentHint is True
