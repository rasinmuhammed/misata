import json
from inspect import signature
from unittest.mock import MagicMock, patch

import pytest

import misata.llm_parser as llm_parser
from misata.llm_parser import LLMSchemaGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_generator() -> LLMSchemaGenerator:
    """Return an LLMSchemaGenerator with a stubbed-out client (no real API)."""
    gen = object.__new__(LLMSchemaGenerator)
    gen.provider = "groq"
    gen.model = "test-model"
    gen.api_key = "fake"
    gen.enable_feedback = False
    gen.feedback_db_path = None
    gen.feedback_min_occurrences = 3
    gen._feedback_db = None
    gen.client = MagicMock()
    return gen


def _make_minimal_schema_dict() -> dict:
    return {
        "name": "Test Dataset",
        "tables": [{"name": "users", "row_count": 100, "is_reference": False}],
        "columns": {
            "users": [
                {"name": "user_id", "type": "int", "distribution_params": {"min": 1, "max": 100}, "unique": True},
                {"name": "email", "type": "text", "distribution_params": {"text_type": "email"}},
            ]
        },
        "relationships": [],
        "events": [],
        "outcome_curves": [],
    }


# ---------------------------------------------------------------------------
# Signature tests
# ---------------------------------------------------------------------------

def test_generate_from_story_signature_includes_research_and_temperature() -> None:
    params = list(signature(llm_parser.LLMSchemaGenerator.generate_from_story).parameters)
    assert params == ["self", "story", "use_research", "default_rows", "temperature"]


def test_groq_provider_fails_lazily_when_package_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(llm_parser, "Groq", None)

    with pytest.raises(ImportError, match="groq package required"):
        llm_parser.LLMSchemaGenerator(provider="groq", api_key="test-key")


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_strips_json_code_fence(self):
        raw = '```json\n{"a": 1}\n```'
        assert LLMSchemaGenerator._extract_json(raw) == '{"a": 1}'

    def test_strips_plain_code_fence(self):
        raw = '```\n{"a": 1}\n```'
        assert LLMSchemaGenerator._extract_json(raw) == '{"a": 1}'

    def test_extracts_object_from_prose(self):
        raw = 'Here is the schema: {"a": 1} and that is it.'
        extracted = LLMSchemaGenerator._extract_json(raw)
        assert json.loads(extracted) == {"a": 1}

    def test_passthrough_plain_json(self):
        raw = '{"a": 1}'
        assert LLMSchemaGenerator._extract_json(raw) == '{"a": 1}'


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------

class TestParseJsonResponse:
    def test_parses_clean_json(self):
        gen = _make_generator()
        result = gen._parse_json_response('{"x": 42}')
        assert result == {"x": 42}

    def test_parses_fenced_json(self):
        gen = _make_generator()
        result = gen._parse_json_response('```json\n{"x": 42}\n```')
        assert result == {"x": 42}

    def test_raises_on_unparseable(self):
        gen = _make_generator()
        with pytest.raises(ValueError, match="Could not parse LLM response"):
            gen._parse_json_response("this is not json at all !!!")


# ---------------------------------------------------------------------------
# _call_api retry behaviour
# ---------------------------------------------------------------------------

class TestCallApiRetry:
    def test_returns_content_on_success(self):
        gen = _make_generator()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"ok": true}'
        gen.client.chat.completions.create.return_value = mock_response

        result = gen._call_api([{"role": "user", "content": "hi"}])
        assert result == '{"ok": true}'

    def test_retries_on_rate_limit_then_succeeds(self):
        gen = _make_generator()
        good_response = MagicMock()
        good_response.choices[0].message.content = '{"ok": true}'

        gen.client.chat.completions.create.side_effect = [
            Exception("rate_limit exceeded"),
            good_response,
        ]

        with patch("misata.llm_parser.time.sleep"):
            result = gen._call_api([{"role": "user", "content": "hi"}], max_retries=3)
        assert result == '{"ok": true}'
        assert gen.client.chat.completions.create.call_count == 2

    def test_raises_after_all_retries_exhausted(self):
        gen = _make_generator()
        gen.client.chat.completions.create.side_effect = Exception("timeout")

        with patch("misata.llm_parser.time.sleep"):
            with pytest.raises(RuntimeError, match="LLM API call failed"):
                gen._call_api([{"role": "user", "content": "hi"}], max_retries=2)
        assert gen.client.chat.completions.create.call_count == 2

    def test_non_transient_error_does_not_retry(self):
        gen = _make_generator()
        gen.client.chat.completions.create.side_effect = Exception("invalid_api_key")

        with pytest.raises(RuntimeError):
            gen._call_api([{"role": "user", "content": "hi"}], max_retries=3)
        # Should bail after the first attempt — no retries for auth errors
        assert gen.client.chat.completions.create.call_count == 1

    def test_raises_on_empty_response(self):
        gen = _make_generator()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = ""
        gen.client.chat.completions.create.return_value = mock_response

        with patch("misata.llm_parser.time.sleep"):
            with pytest.raises(RuntimeError, match="LLM API call failed"):
                gen._call_api([{"role": "user", "content": "hi"}], max_retries=1)


# ---------------------------------------------------------------------------
# _parse_schema defensiveness
# ---------------------------------------------------------------------------

class TestParseSchemaDefensive:
    def test_skips_table_with_no_name(self):
        gen = _make_generator()
        schema_dict = {
            "tables": [
                {"row_count": 10},          # missing name — should be skipped
                {"name": "valid", "row_count": 5},
            ],
            "columns": {
                "valid": [
                    {"name": "id", "type": "int", "distribution_params": {"min": 1, "max": 5}, "unique": True},
                ]
            },
            "relationships": [],
            "events": [],
            "outcome_curves": [],
        }
        schema = gen._parse_schema(schema_dict)
        assert len(schema.tables) == 1
        assert schema.tables[0].name == "valid"

    def test_skips_malformed_relationship(self):
        gen = _make_generator()
        schema_dict = _make_minimal_schema_dict()
        # Add a second table so a valid relationship can reference two real tables
        schema_dict["tables"].append({"name": "orders", "row_count": 100, "is_reference": False})
        schema_dict["columns"]["orders"] = [
            {"name": "order_id", "type": "int", "distribution_params": {"min": 1, "max": 100}, "unique": True},
            {"name": "user_id", "type": "foreign_key", "distribution_params": {}},
        ]
        schema_dict["relationships"] = [
            {"parent_table": "users"},   # missing child_table etc. — should be skipped
            {"parent_table": "users", "child_table": "orders", "parent_key": "user_id", "child_key": "user_id"},
        ]
        schema = gen._parse_schema(schema_dict)
        assert len(schema.relationships) == 1
        assert schema.relationships[0].child_table == "orders"

    def test_skips_non_dict_columns(self):
        gen = _make_generator()
        schema_dict = _make_minimal_schema_dict()
        schema_dict["columns"]["users"].append("not_a_dict")
        schema = gen._parse_schema(schema_dict)
        # Should not raise; all valid columns parsed
        assert any(c.name == "user_id" for c in schema.columns["users"])

    def test_normalises_type_aliases(self):
        gen = _make_generator()
        schema_dict = _make_minimal_schema_dict()
        schema_dict["columns"]["users"][0]["type"] = "integer"  # LLM alias
        schema = gen._parse_schema(schema_dict)
        col = next(c for c in schema.columns["users"] if c.name == "user_id")
        assert col.type == "int"

    def test_valid_schema_round_trips(self):
        gen = _make_generator()
        schema = gen._parse_schema(_make_minimal_schema_dict())
        assert schema.name == "Test Dataset"
        assert len(schema.tables) == 1
        assert schema.tables[0].name == "users"
