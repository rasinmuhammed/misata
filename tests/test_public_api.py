"""Tests for the top-level misata public API."""

import pytest
import misata


class TestParseFunction:
    def test_returns_schema_config(self):
        schema = misata.parse("A SaaS company with 500 users", rows=100)
        assert schema.name
        assert len(schema.tables) >= 1

    def test_summary_returns_string(self):
        schema = misata.parse("An ecommerce store with orders", rows=50)
        summary = schema.summary()
        assert isinstance(summary, str)
        assert "Table" in summary
        assert "Rows" in summary

    def test_summary_contains_table_names(self):
        schema = misata.parse("A SaaS company with users", rows=50)
        summary = schema.summary()
        assert "users" in summary

    def test_summary_shows_relationships(self):
        schema = misata.parse("A SaaS company with 500 users", rows=100)
        summary = schema.summary()
        assert "Relationships" in summary


class TestGenerateFunction:
    def test_returns_dict_of_dataframes(self):
        import pandas as pd
        tables = misata.generate("A SaaS company with 200 users", rows=50)
        assert isinstance(tables, dict)
        assert len(tables) >= 1
        for df in tables.values():
            assert isinstance(df, pd.DataFrame)

    def test_row_counts_match_schema(self):
        tables = misata.generate("An ecommerce store with orders", rows=50)
        assert all(len(df) > 0 for df in tables.values())

    def test_seed_is_reproducible(self):
        t1 = misata.generate("A fintech company with transactions", rows=50, seed=42)
        t2 = misata.generate("A fintech company with transactions", rows=50, seed=42)
        import pandas as pd
        for name in t1:
            pd.testing.assert_frame_equal(t1[name], t2[name])

    def test_different_seeds_differ(self):
        t1 = misata.generate("A SaaS company with users", rows=100, seed=1)
        t2 = misata.generate("A SaaS company with users", rows=100, seed=2)
        # At least one table should differ
        any_diff = any(
            not t1[n].equals(t2[n]) for n in t1 if n in t2
        )
        assert any_diff


class TestGenerateFromSchemaFunction:
    def test_generates_from_parsed_schema(self):
        schema = misata.parse("A healthcare system with patients", rows=50)
        tables = misata.generate_from_schema(schema)
        assert "patients" in tables
        assert len(tables["patients"]) == 50

    def test_respects_all_relationships(self):
        schema = misata.parse("A marketplace with sellers and buyers", rows=50)
        tables = misata.generate_from_schema(schema)
        # Every FK must reference a valid parent key
        for rel in schema.relationships:
            if rel.parent_table in tables and rel.child_table in tables:
                parent_ids = set(tables[rel.parent_table][rel.parent_key])
                child_fks = tables[rel.child_table][rel.child_key]
                orphans = (~child_fks.isin(parent_ids)).sum()
                assert orphans == 0, f"{rel.child_table}.{rel.child_key} has orphan FKs"


class TestSchemaValidationErrorExport:
    def test_is_importable_from_top_level(self):
        assert hasattr(misata, "SchemaValidationError")

    def test_is_exception_subclass(self):
        assert issubclass(misata.SchemaValidationError, Exception)

    def test_issues_attribute(self):
        exc = misata.SchemaValidationError(["problem one", "problem two"])
        assert exc.issues == ["problem one", "problem two"]

    def test_str_lists_all_issues(self):
        exc = misata.SchemaValidationError(["bad column", "bad table"])
        msg = str(exc)
        assert "bad column" in msg
        assert "bad table" in msg


class TestValidateSchemaExport:
    def test_validate_schema_importable(self):
        assert callable(misata.validate_schema)

    def test_valid_schema_does_not_raise(self):
        schema = misata.parse("A SaaS company with 100 users", rows=100)
        misata.validate_schema(schema)  # must not raise


class TestStoryParserExport:
    def test_story_parser_importable(self):
        assert hasattr(misata, "StoryParser")

    def test_story_parser_usable(self):
        parser = misata.StoryParser()
        schema = parser.parse("A logistics company with drivers", default_rows=50)
        assert schema.domain == "logistics"
