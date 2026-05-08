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
pytest.importorskip("mcp")
pytest.importorskip("jsonschema")

from misata.mcp.server import (
    generate_dataset,
    inspect_schema,
    list_domains,
    preview_story,
    validate_yaml,
)


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
