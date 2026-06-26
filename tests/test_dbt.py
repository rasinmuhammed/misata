"""Tests for misata.dbt — dbt integration utilities."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Dict

import pandas as pd
import pytest
import yaml

from misata.dbt import (
    DbtProjectInfo,
    SeedSizeReport,
    DbtSeedResult,
    DbtFixtureResult,
    detect_dbt_project,
    generate_dbt_schema_yml,
    generate_dbt_fixtures,
    generate_unit_test_yml,
    write_seeds_with_report,
    _infer_pk_columns,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_schema():
    """A minimal SchemaConfig for testing."""
    from misata.schema import SchemaConfig, Table, Column, Relationship

    return SchemaConfig(
        name="test_dbt_schema",
        domain="saas",
        tables=[
            Table(name="users", row_count=100),
            Table(name="subscriptions", row_count=200),
        ],
        columns={
            "users": [
                Column(name="user_id", type="int", unique=True),
                Column(name="name", type="text"),
                Column(name="email", type="text", unique=True),
                Column(name="signup_date", type="date"),
            ],
            "subscriptions": [
                Column(name="subscription_id", type="int", unique=True),
                Column(name="user_id", type="int"),
                Column(name="plan", type="categorical", distribution_params={"choices": ["free", "pro", "enterprise"]}),
                Column(name="amount", type="float"),
                Column(name="start_date", type="date"),
            ],
        },
        relationships=[
            Relationship(
                parent_table="users",
                child_table="subscriptions",
                parent_key="user_id",
                child_key="user_id",
            ),
        ],
    )


@pytest.fixture
def sample_tables():
    """Sample DataFrames matching the simple_schema."""
    users = pd.DataFrame({
        "user_id": range(1, 11),
        "name": [f"User {i}" for i in range(1, 11)],
        "email": [f"user{i}@example.com" for i in range(1, 11)],
        "signup_date": pd.date_range("2024-01-01", periods=10, freq="D"),
    })
    subscriptions = pd.DataFrame({
        "subscription_id": range(1, 21),
        "user_id": [i % 10 + 1 for i in range(20)],
        "plan": ["free", "pro"] * 10,
        "amount": [0.0, 29.99] * 10,
        "start_date": pd.date_range("2024-01-01", periods=20, freq="D"),
    })
    return {"users": users, "subscriptions": subscriptions}


@pytest.fixture
def dbt_project_dir(tmp_path):
    """Create a mock dbt project directory."""
    dbt_yml = tmp_path / "dbt_project.yml"
    dbt_yml.write_text(textwrap.dedent("""\
        name: test_analytics
        version: '1.0.0'
        config-version: 2
        profile: test
        seed-paths: ['seeds']
        model-paths: ['models']
        test-paths: ['tests']
    """), encoding="utf-8")

    (tmp_path / "seeds").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "tests").mkdir()

    return tmp_path


# ---------------------------------------------------------------------------
# detect_dbt_project
# ---------------------------------------------------------------------------

class TestDetectDbtProject:

    def test_detects_project_in_current_dir(self, dbt_project_dir):
        info = detect_dbt_project(dbt_project_dir)
        assert info is not None
        assert info.project_name == "test_analytics"
        assert info.seeds_dir == Path("seeds")
        assert info.project_root == dbt_project_dir

    def test_detects_project_from_subdir(self, dbt_project_dir):
        subdir = dbt_project_dir / "models" / "staging"
        subdir.mkdir(parents=True, exist_ok=True)
        info = detect_dbt_project(subdir)
        assert info is not None
        assert info.project_name == "test_analytics"

    def test_returns_none_when_no_project(self, tmp_path):
        info = detect_dbt_project(tmp_path)
        assert info is None

    def test_seeds_dir_abs(self, dbt_project_dir):
        info = detect_dbt_project(dbt_project_dir)
        assert info.seeds_dir_abs == dbt_project_dir / "seeds"

    def test_fixtures_dir(self, dbt_project_dir):
        info = detect_dbt_project(dbt_project_dir)
        assert info.fixtures_dir == dbt_project_dir / "tests" / "fixtures"

    def test_custom_seed_paths(self, tmp_path):
        """Parses non-default seed-paths correctly."""
        dbt_yml = tmp_path / "dbt_project.yml"
        dbt_yml.write_text(textwrap.dedent("""\
            name: custom_project
            version: '1.0.0'
            config-version: 2
            profile: test
            seed-paths: ['data/seeds']
        """), encoding="utf-8")
        info = detect_dbt_project(tmp_path)
        assert info.seeds_dir == Path("data/seeds")


# ---------------------------------------------------------------------------
# generate_dbt_schema_yml
# ---------------------------------------------------------------------------

class TestGenerateDbtSchemaYml:

    def test_produces_valid_yaml(self, simple_schema, sample_tables):
        yml_str = generate_dbt_schema_yml(simple_schema, sample_tables)
        doc = yaml.safe_load(yml_str)
        assert doc["version"] == 2
        assert "seeds" in doc

    def test_has_all_tables(self, simple_schema, sample_tables):
        yml_str = generate_dbt_schema_yml(simple_schema, sample_tables)
        doc = yaml.safe_load(yml_str)
        table_names = {s["name"] for s in doc["seeds"]}
        assert table_names == {"users", "subscriptions"}

    def test_unique_tests_on_pks(self, simple_schema, sample_tables):
        yml_str = generate_dbt_schema_yml(simple_schema, sample_tables)
        doc = yaml.safe_load(yml_str)

        users_entry = next(s for s in doc["seeds"] if s["name"] == "users")
        user_id_col = next(c for c in users_entry["columns"] if c["name"] == "user_id")
        assert "unique" in user_id_col["tests"]

    def test_not_null_tests(self, simple_schema, sample_tables):
        yml_str = generate_dbt_schema_yml(simple_schema, sample_tables)
        doc = yaml.safe_load(yml_str)

        users_entry = next(s for s in doc["seeds"] if s["name"] == "users")
        name_col = next(c for c in users_entry["columns"] if c["name"] == "name")
        assert "not_null" in name_col["tests"]

    def test_relationship_tests(self, simple_schema, sample_tables):
        yml_str = generate_dbt_schema_yml(simple_schema, sample_tables)
        doc = yaml.safe_load(yml_str)

        subs_entry = next(s for s in doc["seeds"] if s["name"] == "subscriptions")
        user_id_col = next(c for c in subs_entry["columns"] if c["name"] == "user_id")

        # Should have a relationships test
        rel_tests = [t for t in user_id_col["tests"] if isinstance(t, dict) and "relationships" in t]
        assert len(rel_tests) == 1
        # dbt 1.9+ nests generic-test args under `arguments`
        assert rel_tests[0]["relationships"]["arguments"]["field"] == "user_id"

    def test_custom_resource_type(self, simple_schema, sample_tables):
        yml_str = generate_dbt_schema_yml(
            simple_schema, sample_tables, resource_type="sources"
        )
        doc = yaml.safe_load(yml_str)
        assert "sources" in doc
        assert "seeds" not in doc


# ---------------------------------------------------------------------------
# generate_dbt_fixtures
# ---------------------------------------------------------------------------

class TestGenerateDbtFixtures:

    def test_creates_fixture_csvs(self, simple_schema, sample_tables, tmp_path):
        result = generate_dbt_fixtures(
            simple_schema, sample_tables, tmp_path, max_rows=5,
        )
        assert len(result.fixtures_written) == 2
        for name, count, path in result.fixtures_written:
            assert path.exists()
            assert count <= 5
            df = pd.read_csv(path)
            assert len(df) <= 5

    def test_creates_unit_tests_yml(self, simple_schema, sample_tables, tmp_path):
        result = generate_dbt_fixtures(
            simple_schema, sample_tables, tmp_path, max_rows=5,
        )
        assert result.unit_tests_yml_path is not None
        assert result.unit_tests_yml_path.exists()
        content = result.unit_tests_yml_path.read_text()
        assert "unit_tests:" in content
        assert "users_fixture" in content

    def test_table_filter(self, simple_schema, sample_tables, tmp_path):
        result = generate_dbt_fixtures(
            simple_schema, sample_tables, tmp_path,
            max_rows=5, table_filter=["users"],
        )
        assert len(result.fixtures_written) == 1
        assert result.fixtures_written[0][0] == "users"

    def test_fixture_naming(self, simple_schema, sample_tables, tmp_path):
        result = generate_dbt_fixtures(
            simple_schema, sample_tables, tmp_path, max_rows=5,
        )
        filenames = {path.name for _, _, path in result.fixtures_written}
        assert "users_fixture.csv" in filenames
        assert "subscriptions_fixture.csv" in filenames


# ---------------------------------------------------------------------------
# generate_unit_test_yml
# ---------------------------------------------------------------------------

class TestGenerateUnitTestYml:

    def test_produces_valid_content(self, simple_schema, sample_tables):
        content = generate_unit_test_yml(simple_schema, sample_tables)
        assert "unit_tests:" in content
        assert "test_users_fixture_loads" in content
        assert "test_subscriptions_fixture_loads" in content

    def test_includes_fk_dependencies(self, simple_schema, sample_tables):
        content = generate_unit_test_yml(simple_schema, sample_tables)
        # subscriptions depends on users — should reference users_fixture
        assert "ref('users')" in content


# ---------------------------------------------------------------------------
# write_seeds_with_report
# ---------------------------------------------------------------------------

class TestWriteSeedsWithReport:

    def test_writes_csvs(self, sample_tables, tmp_path):
        written, skipped, reports = write_seeds_with_report(
            sample_tables, tmp_path, force=True,
        )
        assert len(written) == 2
        assert len(skipped) == 0
        assert len(reports) == 2
        for name, count, path in written:
            assert path.exists()

    def test_skips_existing(self, sample_tables, tmp_path):
        # Write once
        write_seeds_with_report(sample_tables, tmp_path, force=True)
        # Write again without force
        written, skipped, reports = write_seeds_with_report(
            sample_tables, tmp_path, force=False,
        )
        assert len(written) == 0
        assert len(skipped) == 2

    def test_force_overwrites(self, sample_tables, tmp_path):
        write_seeds_with_report(sample_tables, tmp_path, force=True)
        written, skipped, reports = write_seeds_with_report(
            sample_tables, tmp_path, force=True,
        )
        assert len(written) == 2
        assert len(skipped) == 0


# ---------------------------------------------------------------------------
# SeedSizeReport
# ---------------------------------------------------------------------------

class TestSeedSizeReport:

    def test_small_file_ok(self):
        report = SeedSizeReport("test", 100, 50_000)
        assert not report.exceeds_recommended
        assert not report.exceeds_hard_limit
        assert report.recommendation == "OK"
        assert report.file_size_human == "48.8 KB"

    def test_medium_file_warning(self):
        report = SeedSizeReport("test", 10_000, 2_000_000)
        assert report.exceeds_recommended
        assert not report.exceeds_hard_limit
        assert "1 MB" in report.recommendation
        assert report.file_size_human == "1.9 MB"

    def test_large_file_critical(self):
        report = SeedSizeReport("test", 100_000, 10_000_000)
        assert report.exceeds_recommended
        assert report.exceeds_hard_limit
        assert "5 MB" in report.recommendation
        assert report.file_size_human == "9.5 MB"

    def test_tiny_file_bytes(self):
        report = SeedSizeReport("test", 1, 500)
        assert report.file_size_human == "500 B"


# ---------------------------------------------------------------------------
# _infer_pk_columns
# ---------------------------------------------------------------------------

class TestInferPkColumns:

    def test_unique_columns(self, simple_schema):
        cols = simple_schema.get_columns("users")
        pks = _infer_pk_columns("users", cols, simple_schema)
        assert "user_id" in pks
        assert "email" in pks

    def test_relationship_parent_key(self, simple_schema):
        cols = simple_schema.get_columns("users")
        pks = _infer_pk_columns("users", cols, simple_schema)
        # user_id is parent_key in users→subscriptions relationship
        assert "user_id" in pks


# ---------------------------------------------------------------------------
# End-to-end: story → generate → schema.yml
# ---------------------------------------------------------------------------

class TestEndToEnd:

    def test_story_to_dbt_seed(self, tmp_path):
        """Full pipeline: parse story → generate → write seeds → schema.yml."""
        from misata.story_parser import StoryParser
        from misata.simulator import DataSimulator

        schema = StoryParser().parse("A SaaS company with 100 users", default_rows=100)
        schema.seed = 42

        sim = DataSimulator(schema)
        tables = {}
        for name, batch in sim.generate_all():
            if name in tables:
                tables[name] = pd.concat([tables[name], batch], ignore_index=True)
            else:
                tables[name] = batch

        # Write seeds
        written, skipped, reports = write_seeds_with_report(
            tables, tmp_path, force=True,
        )
        assert len(written) > 0

        # Generate schema.yml
        yml_str = generate_dbt_schema_yml(schema, tables)
        doc = yaml.safe_load(yml_str)
        assert doc["version"] == 2
        assert len(doc["seeds"]) > 0

        # Verify CSV files are readable
        for name, count, path in written:
            df = pd.read_csv(path)
            assert len(df) == count

    def test_story_to_dbt_fixture(self, tmp_path):
        """Full pipeline: parse story → generate → write fixtures."""
        from misata.story_parser import StoryParser
        from misata.simulator import DataSimulator

        schema = StoryParser().parse("Ecommerce with 200 orders", default_rows=200)
        schema.seed = 42

        sim = DataSimulator(schema)
        tables = {}
        for name, batch in sim.generate_all():
            if name in tables:
                tables[name] = pd.concat([tables[name], batch], ignore_index=True)
            else:
                tables[name] = batch

        result = generate_dbt_fixtures(
            schema, tables, tmp_path, max_rows=20,
        )
        assert len(result.fixtures_written) > 0
        assert result.unit_tests_yml_path.exists()

        # Verify fixtures are small
        for name, count, path in result.fixtures_written:
            assert count <= 20
            df = pd.read_csv(path)
            assert len(df) <= 20
