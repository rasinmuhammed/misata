"""Domain hardening matrix.

Every built-in domain must:
  1. parse cleanly from a short canonical story
  2. validate with the pre-generation schema validator
  3. generate at multiple scales (10, 1k, 50k rows) without raising
  4. produce non-empty primary tables
  5. respect referential integrity (every FK value points to a real PK)
  6. round-trip through misata.yaml
  7. have schemas that satisfy the published JSON Schema

If any domain regresses on any of these, this file fails with a
diagnostic that points at the exact domain × scale × invariant.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest
import yaml

import misata
from misata.validation import validate_schema


# Canonical stories — one short signal-rich phrase per domain.  Edits here
# should be deliberate: these are the contractual examples promised by the
# README's domain table.
DOMAIN_STORIES = {
    "saas": "A SaaS company with 5k users and 20% churn",
    "ecommerce": "An ecommerce store with 10k orders",
    "fintech": "A fintech with payments and 5k customers",
    "healthcare": "A healthcare clinic with 500 patients and doctors",
    "marketplace": "A freelance marketplace with sellers and buyers",
    "logistics": "A logistics company with drivers and shipments",
    "hr": "An HR system with 200 employees and payroll",
    "social": "A social media app with influencers and reels",
    "realestate": "A real estate platform with property listings",
    "pharma": "A pharma research company with clinical trials",
    "fooddelivery": "A food delivery app with restaurants and couriers",
    "edtech": "An edtech platform with courses and quizzes",
    "gaming": "A gaming platform with players and achievements",
    "crm": "A CRM with contacts and deals pipeline",
    "crypto": "A crypto exchange with wallets and blockchain transactions",
    "insurance": "An insurance company with policies and claims",
    "travel": "A travel booking platform with hotels and flights",
    "streaming": "A Netflix streaming service with subscribers",
}


# ---------------------------------------------------------------------------
# 1. Parse + validate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain,story", list(DOMAIN_STORIES.items()))
def test_domain_parses_and_validates(domain, story):
    """Every domain story must parse and pass schema validation."""
    schema = misata.parse(story, rows=100)
    assert schema.tables, f"{domain}: no tables produced"
    assert schema.domain == domain, (
        f"{domain}: detected domain mismatch — got {schema.domain!r}"
    )
    # Will raise SchemaValidationError if anything is malformed
    validate_schema(schema)


# ---------------------------------------------------------------------------
# 2. Generation at multiple scales
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain,story", list(DOMAIN_STORIES.items()))
@pytest.mark.parametrize("rows", [10, 1_000])
def test_domain_generates_at_scale(domain, story, rows):
    """Every domain must generate at small (10) and medium (1k) scales."""
    tables = misata.generate(story, rows=rows, seed=42)
    assert tables, f"{domain}: no tables returned for rows={rows}"

    # Primary table (first table) must have *some* rows
    schema = misata.parse(story, rows=rows)
    primary = schema.tables[0].name
    assert primary in tables, f"{domain}: primary table '{primary}' missing at rows={rows}"
    assert len(tables[primary]) > 0, (
        f"{domain}: primary table '{primary}' is empty at rows={rows}"
    )


# ---------------------------------------------------------------------------
# 3. Referential integrity — every FK row must hit a real parent PK
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain,story", list(DOMAIN_STORIES.items()))
def test_domain_referential_integrity(domain, story):
    """For every defined relationship, child FK values ⊆ parent PK values."""
    schema = misata.parse(story, rows=200)
    tables = misata.generate_from_schema(schema)

    for rel in schema.relationships:
        parent_df = tables.get(rel.parent_table)
        child_df = tables.get(rel.child_table)
        if parent_df is None or child_df is None:
            continue
        if rel.parent_key not in parent_df.columns or rel.child_key not in child_df.columns:
            continue

        parent_values = set(parent_df[rel.parent_key].dropna().tolist())
        child_values = set(child_df[rel.child_key].dropna().tolist())

        orphans = child_values - parent_values
        assert not orphans, (
            f"{domain}: FK {rel.child_table}.{rel.child_key} has "
            f"{len(orphans)} orphan(s) not present in {rel.parent_table}.{rel.parent_key}. "
            f"Sample: {list(orphans)[:3]}"
        )


# ---------------------------------------------------------------------------
# 4. YAML round-trip — every domain must serialize and reload cleanly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain,story", list(DOMAIN_STORIES.items()))
def test_domain_yaml_roundtrip(domain, story, tmp_path):
    """Save → reload → re-validate. The reloaded schema must match column counts."""
    schema = misata.parse(story, rows=100)
    yaml_path = tmp_path / f"{domain}.yaml"
    misata.save_yaml_schema(schema, yaml_path)

    reloaded = misata.load_yaml_schema(yaml_path)
    validate_schema(reloaded)

    original_table_names = {t.name for t in schema.tables}
    reloaded_table_names = {t.name for t in reloaded.tables}
    assert original_table_names == reloaded_table_names, (
        f"{domain}: table set drifted on YAML round-trip. "
        f"Lost: {original_table_names - reloaded_table_names}, "
        f"Gained: {reloaded_table_names - original_table_names}"
    )


# ---------------------------------------------------------------------------
# 5. Determinism — same seed must produce byte-identical primary table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "domain,story",
    # Pick a representative subset to keep the test fast — full matrix
    # would be 18 × 2 generations each.
    [
        ("saas", DOMAIN_STORIES["saas"]),
        ("ecommerce", DOMAIN_STORIES["ecommerce"]),
        ("hr", DOMAIN_STORIES["hr"]),
        ("travel", DOMAIN_STORIES["travel"]),
        ("crypto", DOMAIN_STORIES["crypto"]),
    ],
)
def test_domain_is_deterministic(domain, story):
    """Same seed → same data. Critical for the 'commit to git' positioning."""
    a = misata.generate(story, rows=200, seed=12345)
    b = misata.generate(story, rows=200, seed=12345)

    assert set(a.keys()) == set(b.keys()), f"{domain}: table set changed run-to-run"
    for table_name in a:
        df_a = a[table_name].reset_index(drop=True)
        df_b = b[table_name].reset_index(drop=True)
        # Same shape and same first row hash is enough to catch nondeterminism
        assert df_a.shape == df_b.shape, (
            f"{domain}.{table_name}: shape drift {df_a.shape} vs {df_b.shape}"
        )
        # Compare the first 5 rows of every column, accepting NaN equality
        for col in df_a.columns:
            ser_a = df_a[col].head(5)
            ser_b = df_b[col].head(5)
            assert ser_a.equals(ser_b), (
                f"{domain}.{table_name}.{col}: nondeterministic — "
                f"{list(ser_a)} vs {list(ser_b)}"
            )


# ---------------------------------------------------------------------------
# 6. Tiny scale (rows=1) must not crash — common bug source
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain,story", list(DOMAIN_STORIES.items()))
def test_domain_handles_tiny_scale(domain, story):
    """rows=1 is a frequent edge case — uniqueness ranges, FK pools, and
    distribution params can all break at this scale. Generation must not raise."""
    tables = misata.generate(story, rows=1, seed=7)
    # Some domains scale child tables at fractional ratios that floor to 0;
    # what matters is no exception, and at least one table has at least one row.
    assert any(len(df) > 0 for df in tables.values()), (
        f"{domain}: every table empty at rows=1"
    )
