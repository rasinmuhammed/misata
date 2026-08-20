"""The Smithery listing must describe the server that exists.

The published directory entry advertised `generate_from_story` and
`design_schema` for months after both were renamed, so anyone browsing
Smithery was told about tools they could not call. Nothing caught it because
nothing tied the listing to the source.
"""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def listing():
    return yaml.safe_load((ROOT / "smithery.yaml").read_text())


@pytest.fixture(scope="module")
def server_tools():
    import asyncio

    from misata.mcp.server import mcp
    return {t.name for t in asyncio.run(mcp.list_tools())}


def test_every_tool_the_server_exposes_is_described(listing, server_tools):
    described = listing["description"]
    missing = sorted(t for t in server_tools if t not in described)
    assert not missing, f"tools the listing never mentions: {missing}"


def test_the_listing_advertises_no_tool_that_does_not_exist(listing, server_tools):
    """Catches the actual failure: a renamed tool left behind in the copy."""
    claimed = set(re.findall(r"\b([a-z_]{6,})\b", listing["description"]))
    ghosts = {c for c in claimed
              if c.endswith(("_schema", "_story", "_dataset", "_domains",
                             "_database", "_yaml"))
              and c not in server_tools}
    assert not ghosts, f"listing advertises tools the server does not have: {sorted(ghosts)}"


def test_config_keys_map_to_env_vars_the_code_actually_reads(listing):
    """A config field wired to an invented env var is silently inert: the user
    pastes a key, Smithery sets a variable nothing reads, and the tool fails
    as if no key were given."""
    command_fn = listing["startCommand"]["commandFunction"]
    parser = (ROOT / "misata" / "llm_parser.py").read_text()

    env_vars = set(re.findall(r"env\.([A-Z_]+)\s*=", command_fn))
    assert env_vars, "the command function sets no environment at all"

    for var in env_vars:
        assert f'"{var}"' in parser or f"'{var}'" in parser, (
            f"{var} is set by smithery.yaml but never read by the engine")


def test_no_api_key_is_hardcoded_in_the_listing(listing):
    blob = yaml.safe_dump(listing)
    assert not re.search(r"(sk-|gsk_)[A-Za-z0-9]{16,}", blob), \
        "a real-looking API key is committed in smithery.yaml"
