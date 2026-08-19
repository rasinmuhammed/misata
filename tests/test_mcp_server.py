"""Unit tests for the Misata MCP server.

We test the tool *handlers* directly rather than spinning up a real MCP
transport — protocol-level integration is the SDK's responsibility, ours
is the contract of what each tool returns. If a tool's response shape
or behaviour drifts, AI agents calling it will silently break, so these
tests are tighter than they look.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

# The mcp extra is an optional dependency; skip the whole module if missing.
#
# `importorskip("mcp")` is not enough on its own: `mcp` can be installed and
# still not expose what the server needs, which is exactly what happened when an
# upstream release moved `FastMCP` out of `mcp.server.fastmcp`. That took CI down
# on all four interpreters over a dependency change, so the guard covers the
# import that actually matters rather than the package name.
pytest.importorskip("mcp")
pytest.importorskip("jsonschema")

try:
    from misata.mcp.server import (
        generate_dataset,
        inspect_schema,
        list_domains,
        preview_story,
        validate_yaml,
    )
except ImportError as exc:  # pragma: no cover - environment guard
    pytest.skip(f"misata.mcp.server is not importable here: {exc}",
                allow_module_level=True)


# ---------------------------------------------------------------------------
# list_domains
# ---------------------------------------------------------------------------


def test_list_domains_returns_all_18():
    result = list_domains()
    assert result["count"] == 18
    assert len(result["domains"]) == 18
    # Every entry must have these three fields populated
    for entry in result["domains"]:
        assert entry["domain"]
        assert entry["keywords"], f"{entry['domain']} has no keywords"
        assert entry["sample_story"], f"{entry['domain']} has no sample story"


def test_list_domains_includes_each_named_domain():
    result = list_domains()
    names = {d["domain"] for d in result["domains"]}
    expected = {
        "saas", "ecommerce", "fintech", "healthcare", "marketplace", "logistics",
        "hr", "social", "realestate", "pharma", "fooddelivery", "edtech",
        "gaming", "crm", "crypto", "insurance", "travel", "streaming",
    }
    assert names == expected


# ---------------------------------------------------------------------------
# preview_story
# ---------------------------------------------------------------------------


def test_preview_story_detects_known_domain():
    result = preview_story(story="A SaaS company with 5k users", rows=500)
    assert result["domain"] == "saas"
    assert "saas" in result["matched_keywords"]
    assert result["scale"]["users"] == 5000
    assert isinstance(result["tables"], list)
    assert len(result["tables"]) > 0


def test_preview_story_no_domain_returns_warning():
    result = preview_story(story="random text with nothing recognizable", rows=100)
    assert result["domain"] is None
    assert result["domain_confidence"] == "none"
    assert any("No domain detected" in w for w in result["warnings"])


def test_preview_story_includes_summary_string():
    result = preview_story(story="A SaaS company", rows=100)
    assert isinstance(result["summary"], str)
    assert len(result["summary"]) > 0


# ---------------------------------------------------------------------------
# inspect_schema
# ---------------------------------------------------------------------------


def test_inspect_schema_returns_full_structure():
    result = inspect_schema(story="A fintech with 1k customers and payments", rows=200)
    assert result["domain"] == "fintech"
    assert len(result["tables"]) >= 2
    # Every table entry must have populated columns with type+name
    for tbl in result["tables"]:
        assert tbl["name"]
        assert tbl["row_count"] > 0
        assert tbl["columns"], f"Table '{tbl['name']}' has no columns"
        for col in tbl["columns"]:
            assert col["name"]
            assert col["type"]


def test_inspect_schema_returns_relationships():
    result = inspect_schema(story="A fintech with 1k customers and payments", rows=200)
    assert isinstance(result["relationships"], list)
    if result["relationships"]:
        rel = result["relationships"][0]
        assert rel["parent_table"] and rel["child_table"]
        assert rel["parent_key"] and rel["child_key"]


# ---------------------------------------------------------------------------
# generate_dataset
# ---------------------------------------------------------------------------


def test_generate_dataset_writes_csv_files(tmp_path):
    result = generate_dataset(
        story="A SaaS company with 100 users",
        rows=100,
        seed=42,
        output_dir=str(tmp_path),
        sample_rows=3,
    )
    assert result["table_count"] >= 1
    assert result["total_rows"] >= 100

    for f in result["files"]:
        path = Path(f["path"])
        assert path.exists(), f"CSV not written for {f['table']}"
        assert path.suffix == ".csv"
        # Quick check: file has at least a header + one row
        with path.open() as fh:
            reader = csv.reader(fh)
            rows = list(reader)
        assert len(rows) >= 2, f"{f['table']}.csv has no data rows"
        # Sample list size respects sample_rows cap
        assert len(f["sample"]) <= 3


def test_generate_dataset_is_deterministic_with_seed(tmp_path):
    """Same seed → same row counts. Critical for the AI-agent use case where the
    user asks for the same dataset twice and expects the same data."""
    a = generate_dataset(
        story="A SaaS company with 50 users",
        rows=50, seed=12345,
        output_dir=str(tmp_path / "a"),
        sample_rows=0,
    )
    b = generate_dataset(
        story="A SaaS company with 50 users",
        rows=50, seed=12345,
        output_dir=str(tmp_path / "b"),
        sample_rows=0,
    )
    a_counts = sorted((f["table"], f["rows"]) for f in a["files"])
    b_counts = sorted((f["table"], f["rows"]) for f in b["files"])
    assert a_counts == b_counts


def test_generate_dataset_default_temp_dir():
    """With no output_dir, server picks a fresh temp dir."""
    result = generate_dataset(
        story="A SaaS company with 50 users",
        rows=50, seed=7, sample_rows=0,
    )
    assert Path(result["output_dir"]).exists()
    # Path must not be the cwd — that would be a footgun for agents
    assert "misata-mcp-" in result["output_dir"]


def test_generate_dataset_sample_rows_capped_at_50():
    """sample_rows is bounded at 50 to keep MCP responses small."""
    result = generate_dataset(
        story="A SaaS company with 200 users",
        rows=200, seed=1,
        sample_rows=999,
    )
    for f in result["files"]:
        assert len(f["sample"]) <= 50


# ---------------------------------------------------------------------------
# validate_yaml — three layers (parse / structural / semantic)
# ---------------------------------------------------------------------------


_GOOD_YAML = """\
name: test
tables:
  users:
    rows: 100
    columns:
      id:
        type: int
        unique: true
        min: 1
        max: 1000
      plan:
        type: categorical
        choices: [free, pro, enterprise]
        probabilities: [0.6, 0.3, 0.1]
"""


def test_validate_yaml_passes_clean_schema():
    result = validate_yaml(yaml_text=_GOOD_YAML)
    assert result["valid"] is True
    assert result["stage"] == "ok"


def test_validate_yaml_catches_malformed_yaml():
    result = validate_yaml(yaml_text="tables:\n  - this: is\n  not: a mapping")
    assert result["valid"] is False
    assert result["stage"] in ("yaml", "structural")


def test_validate_yaml_catches_structural_error():
    """Wrong type for a typed field (max should be a number)."""
    bad = """name: x
tables:
  users:
    columns:
      a:
        type: int
        max: "not_a_number"
"""
    result = validate_yaml(yaml_text=bad)
    assert result["valid"] is False
    assert result["stage"] == "structural"


def test_validate_yaml_catches_semantic_error_with_fix_hint():
    """Probabilities don't sum to 1.0 — must be caught by validate_schema with hint."""
    bad = """name: x
tables:
  users:
    rows: 100
    columns:
      plan:
        type: categorical
        choices: [free, pro, enterprise]
        probabilities: [0.5, 0.3, 0.4]
"""
    result = validate_yaml(yaml_text=bad)
    assert result["valid"] is False
    assert result["stage"] == "semantic"
    error_text = " ".join(e["message"] for e in result["errors"])
    assert "probabilities sum to 1.2" in error_text
    assert "Fix:" in error_text, "Semantic errors must include actionable fix hints"


# ---------------------------------------------------------------------------
# Error recovery contract — tools must return structured JSON, never raise
# ---------------------------------------------------------------------------


def test_generate_dataset_bad_output_dir_returns_error():
    """An unwritable output_dir should return ok=False, not raise an exception."""
    result = generate_dataset(
        story="A SaaS company with 50 users",
        rows=50,
        output_dir="/root/misata-should-not-exist-xyzzy",
        sample_rows=0,
    )
    # On macOS/Linux /root is unwritable for non-root; expect an error dict
    if not result.get("ok", True):
        assert "error" in result
        assert "suggestion" in result
        assert result["suggestion"]  # non-empty hint


def test_ok_field_present_on_success():
    """Every successful tool call must include ok=True."""
    assert list_domains()["ok"] is True
    assert preview_story(story="A SaaS company", rows=100)["ok"] is True
    assert inspect_schema(story="A fintech with 1k customers", rows=100)["ok"] is True
    result = generate_dataset(story="A SaaS company with 50 users", rows=50, seed=1, sample_rows=0)
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# generate_from_schema — the agent-designs-the-schema contract
# ---------------------------------------------------------------------------

from misata.mcp.server import generate_from_schema  # noqa: E402


def _agent_schema():
    return {
        "customers": {
            "__rows__": 30,
            "id": {"type": "integer", "primary_key": True},
            "name": {"type": "string"},
            "lifetime_value": {"rollup": {
                "from_table": "orders", "fk": "customer_id",
                "agg": "sum", "column": "total",
            }},
        },
        "orders": {
            "__rows__": 200,
            "id": {"type": "integer", "primary_key": True},
            "customer_id": {"type": "integer",
                            "foreign_key": {"table": "customers", "column": "id"}},
            "quantity": {"type": "integer", "min": 1, "max": 5},
            "unit_price": {"type": "float", "min": 5.0, "max": 50.0, "decimals": 2},
            "total": {"formula": "quantity * unit_price"},
            "placed_at": {"type": "datetime"},
        },
    }


def test_generate_from_schema_writes_files_and_verifies_integrity(tmp_path):
    result = generate_from_schema(
        schema=_agent_schema(), seed=7, output_dir=str(tmp_path), sample_rows=2
    )
    assert result["ok"] is True
    assert result["table_count"] == 2
    assert result["integrity"]["verified"] is True
    rels = result["integrity"]["relationships"]
    assert rels and rels[0]["orphans"] == 0
    assert (tmp_path / "orders.csv").exists()


def test_generate_from_schema_per_table_rows(tmp_path):
    result = generate_from_schema(
        schema=_agent_schema(), seed=7, output_dir=str(tmp_path), sample_rows=0
    )
    rows = {f["table"]: f["rows"] for f in result["files"]}
    assert rows == {"customers": 30, "orders": 200}


def test_generate_from_schema_rollup_reconciles(tmp_path):
    import pandas as pd

    result = generate_from_schema(
        schema=_agent_schema(), seed=7, output_dir=str(tmp_path), sample_rows=0
    )
    customers = pd.read_csv(tmp_path / "customers.csv")
    orders = pd.read_csv(tmp_path / "orders.csv")
    summed = orders.groupby("customer_id")["total"].sum()
    declared = customers.set_index("id")["lifetime_value"].reindex(summed.index)
    assert ((declared - summed).abs() < 0.01).all()


def test_generate_from_schema_is_deterministic(tmp_path):
    a = generate_from_schema(schema=_agent_schema(), seed=11,
                             output_dir=str(tmp_path / "a"), sample_rows=0)
    b = generate_from_schema(schema=_agent_schema(), seed=11,
                             output_dir=str(tmp_path / "b"), sample_rows=0)
    assert a["ok"] and b["ok"]
    assert (tmp_path / "a" / "orders.csv").read_text() == (tmp_path / "b" / "orders.csv").read_text()


def test_generate_from_schema_bad_schema_returns_recoverable_error():
    result = generate_from_schema(schema={"t": "not-a-dict"}, sample_rows=0)
    # Either a structured error or an empty-but-ok result; never an exception.
    assert "ok" in result
    if not result["ok"]:
        assert result["suggestion"]


class TestDirectoryAnnotations:
    """Every tool carries the annotations the Connectors Directory requires.

    Anthropic's submission portal groups tools by whether they declare
    themselves read-only or write, and flags any that declare neither. The
    honesty matters more than the paperwork: `seed_database` writes to a
    database the user points it at and can be asked to truncate tables, so a
    client that trusted a missing hint would be trusting the wrong thing.
    """

    def _tools(self):
        import asyncio
        from misata.mcp.server import mcp
        return {t.name: t for t in asyncio.run(mcp.list_tools())}

    def test_every_tool_has_a_title_and_a_hint(self):
        for name, tool in self._tools().items():
            ann = tool.annotations
            assert ann is not None, f"{name} has no annotations"
            assert ann.title, f"{name} has no title"
            assert ann.readOnlyHint is not None or ann.destructiveHint is not None, (
                f"{name} declares neither readOnlyHint nor destructiveHint")

    def test_the_only_writing_tool_says_so(self):
        """The one tool that touches a real database must not claim otherwise."""
        tools = self._tools()
        writers = [n for n, t in tools.items() if t.annotations.destructiveHint]
        assert writers == ["seed_database"], (
            f"expected seed_database to be the only destructive tool, got {writers}")
        assert tools["seed_database"].annotations.readOnlyHint is False

    def test_the_reading_tools_do_not_claim_to_write(self):
        tools = self._tools()
        for name in ["list_domains", "preview_story", "inspect_schema",
                     "generate_dataset", "generate_from_schema", "validate_yaml"]:
            ann = tools[name].annotations
            assert ann.readOnlyHint is True, f"{name} should be read-only"
            assert ann.destructiveHint is False, f"{name} should not be destructive"


class TestDesktopBundle:
    """The MCPB manifest must stay true, or the directory listing lies.

    Anthropic requires a `privacy_policies` array and a README with a Privacy
    Policy section for local connectors, and rejects submissions without them.
    The version and tool list are checked against the package because a
    manifest that drifts is worse than no manifest: it describes a connector
    that no longer exists.
    """

    def _manifest(self):
        import json
        from pathlib import Path
        return json.loads(
            (Path(__file__).resolve().parents[1] / "mcpb" / "manifest.json").read_text())

    def test_version_matches_the_package(self):
        import misata
        assert self._manifest()["version"] == misata.__version__, (
            "bump mcpb/manifest.json alongside misata.__version__")

    def test_it_declares_a_privacy_policy(self):
        policies = self._manifest().get("privacy_policies") or []
        assert policies, "a local connector without a privacy policy is rejected outright"
        assert all(u.startswith("https://") for u in policies)

    def test_the_readme_has_a_privacy_policy_section(self):
        from pathlib import Path
        readme = (Path(__file__).resolve().parents[1] / "mcpb" / "README.md").read_text()
        assert "## Privacy Policy" in readme
        assert "https://www.misata.studio/privacy" in readme

    def test_it_lists_exactly_the_tools_the_server_exposes(self):
        import asyncio
        from misata.mcp.server import mcp
        listed = {t["name"] for t in self._manifest()["tools"]}
        actual = {t.name for t in asyncio.run(mcp.list_tools())}
        assert listed == actual, (
            f"manifest and server disagree: only in manifest {listed - actual}, "
            f"only on server {actual - listed}")


class TestOptionalExtraIsGuarded:
    """`mcp` is an optional extra, so importing it must never be unguarded.

    A reviewer following the bundle README runs one pip command and launches
    the server. When `mcp.types` was imported at module top, outside the
    try/except that was written precisely to explain this, that reviewer got

        ModuleNotFoundError: No module named 'mcp'

    naming a package they never asked for, with no hint that `misata[mcp]`
    installs it. The guard existed; one import had simply escaped it, which is
    not something reading the file reliably catches. So assert it structurally.
    """

    def _tree(self):
        import ast
        from pathlib import Path
        src = Path(__file__).resolve().parents[1] / "misata" / "mcp" / "server.py"
        return ast.parse(src.read_text()), src

    def test_every_mcp_import_sits_inside_a_try(self):
        import ast
        tree, src = self._tree()

        guarded = {
            id(node)
            for handler in ast.walk(tree)
            if isinstance(handler, ast.Try)
            for stmt in handler.body
            for node in ast.walk(stmt)
        }

        escaped = [
            f"line {node.lineno}: {ast.unparse(node)}"
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            and (getattr(node, "module", "") or "").split(".")[0] == "mcp"
            and id(node) not in guarded
        ]
        assert not escaped, (
            f"{src.name} imports `mcp` outside the try/except that explains how "
            "to install it. Without the extra these fail with a bare "
            "ModuleNotFoundError:\n  " + "\n  ".join(escaped))

    def test_the_guard_names_the_extra(self):
        """The message has to carry the command, not just the diagnosis."""
        from misata.mcp import server
        assert 'pip install "misata[mcp]"' in server._INSTALL_HINT


class TestValidateYamlRefusesTheImpossible:
    """`validate_yaml` has to answer the same question generation answers.

    Its promise is "will this generate?". Shares of 0.6, 0.6 and 0.3 parse as
    perfectly good floats, satisfy the JSON Schema, and satisfy every semantic
    rule; only their sum is impossible. So it reported valid for a schema that
    `generate_from_schema` refuses outright, which is the worst answer of the
    three available: an agent trusts it and hits the wall one call later.

    Found by running the reviewer script from `mcpb/SUBMISSION.md` against the
    published package, which is the point of writing the script down.
    """

    IMPOSSIBLE = """
name: shares
tables:
  orders:
    rows: 100
    columns:
      order_id: {type: int, unique: true}
      segment: {type: categorical, choices: ["a", "b", "c"]}
      revenue: {type: float, min: 10, max: 500}
group_shares:
  - table: orders
    measure: revenue
    group_column: segment
    shares: {a: 0.6, b: 0.6, c: 0.3}
"""

    def test_it_refuses_shares_that_cannot_sum_to_one(self):
        from misata.mcp.server import validate_yaml
        result = validate_yaml(self.IMPOSSIBLE)

        assert result["valid"] is False
        assert result["stage"] == "feasibility"
        assert result["error_count"] == 1

    def test_the_refusal_shows_the_arithmetic(self):
        """A refusal an agent cannot act on is barely better than a crash."""
        from misata.mcp.server import validate_yaml
        conflict = validate_yaml(self.IMPOSSIBLE)["errors"][0]

        assert "1.5" in conflict["arithmetic"], conflict
        assert conflict["where"] == "orders.segment"
        assert conflict["remedy"]

    def test_a_satisfiable_schema_still_passes(self):
        """The guard must refuse the impossible, not everything."""
        from misata.mcp.server import validate_yaml
        ok = self.IMPOSSIBLE.replace("{a: 0.6, b: 0.6, c: 0.3}",
                                     "{a: 0.5, b: 0.3, c: 0.2}")
        assert validate_yaml(ok)["valid"] is True

    def test_it_agrees_with_what_generation_does(self):
        """The two answers must not diverge; that divergence was the bug."""
        import pytest, tempfile, pathlib
        import misata
        from misata.feasibility import InfeasibleSchema
        from misata.mcp.server import validate_yaml

        path = pathlib.Path(tempfile.mkdtemp()) / "s.yaml"
        path.write_text(self.IMPOSSIBLE)
        schema = misata.load_yaml_schema(path)

        with pytest.raises(InfeasibleSchema):
            misata.generate_from_schema(schema)
        assert validate_yaml(self.IMPOSSIBLE)["valid"] is False


class TestTheMCPServerCannotClaimAnUncheckedVerification:
    """The fifth hand-rolled copy of the integrity rule lived here, and it had
    the same defect as the other four: `all(...) if verification else True`.

    A single-table schema came back `verified: true` having checked nothing.
    That is worse on this surface than on the others, because an agent relays
    it to a user as fact and the user never sees the response. Found while
    testing whether the MCP server was fit to launch.
    """

    def _integrity(self, schema):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from misata.mcp import server
            import inspect
            fn = server.generate_from_schema
            fn = getattr(fn, "fn", fn)          # unwrap the FastMCP tool
            result = fn(schema=schema, sample_rows=1)
        return result["integrity"]

    def test_a_schema_with_no_relationships_is_not_verified(self):
        i = self._integrity({"t": {"__rows__": 10,
                                   "id": {"type": "integer", "primary_key": True}}})
        assert i["verified"] is False
        assert i["status"] == "nothing_to_verify"
        assert i["declared"] == 0 and i["checked"] == 0

    def test_a_real_relationship_is_verified(self):
        i = self._integrity({
            "customers": {"__rows__": 30,
                          "customer_id": {"type": "integer", "primary_key": True}},
            "orders": {"__rows__": 100,
                       "order_id": {"type": "integer", "primary_key": True},
                       "customer_id": {"type": "foreign_key",
                                       "references": "customers.customer_id"}}})
        assert i["verified"] is True
        assert i["status"] == "verified"
        assert i["declared"] == i["checked"] == 1
        assert i["relationships"][0]["orphans"] == 0

    def test_it_uses_the_library_verifier_rather_than_its_own(self):
        """One rule, one implementation. Five copies is how they diverge."""
        import inspect
        from misata.mcp import server
        src = inspect.getsource(server)
        assert "from misata.compat import verify_integrity" in src
        # Checks the code, not the prose: the comment explaining the removal
        # necessarily quotes the expression it removed.
        import ast
        tree = ast.parse(src)
        bad = [n for n in ast.walk(tree)
               if isinstance(n, ast.IfExp)
               and isinstance(n.orelse, ast.Constant) and n.orelse.value is True]
        assert not bad, "an `... if x else True` integrity claim is back"

    def test_the_handshake_reports_misata_s_own_version(self):
        """FastMCP takes no `version`, so the low-level server defaulted to the
        `mcp` library's and a client showed "misata 1.29.0", a release that has
        never existed."""
        import inspect
        from misata.mcp import server
        import misata
        src = inspect.getsource(server.main)
        assert "_mcp_server.version" in src
        assert "__version__" in src
