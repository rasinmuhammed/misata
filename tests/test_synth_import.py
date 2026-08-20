"""synth namespace import.

The point of this importer is that someone's working synth setup survives the
project's abandonment. So the tests care about two things: the translation is
faithful for the constructs synth actually uses, and anything untranslatable is
reported rather than quietly approximated into something wrong.
"""

import json

import pytest

import misata
from misata.synth_import import build_schema_from_synth, find_synth_namespace


def _namespace(tmp_path, **collections):
    ns = tmp_path / "synth"
    ns.mkdir()
    for name, doc in collections.items():
        (ns / f"{name}.json").write_text(json.dumps(doc))
    return ns


def _collection(length, **fields):
    return {"type": "array", "length": length,
            "content": {"type": "object", **fields}}


def test_shorthand_reference_becomes_a_foreign_key(tmp_path):
    ns = _namespace(
        tmp_path,
        User=_collection(10, id={"type": "number", "id": {}}),
        Post=_collection(40, id={"type": "number", "id": {}},
                         authorId="@User.content.id"),
    )
    schema, report = build_schema_from_synth(ns)

    assert report.relationships == 1
    rel = schema.relationships[0]
    assert (rel.parent_table, rel.parent_key) == ("User", "id")
    assert (rel.child_table, rel.child_key) == ("Post", "authorId")


def test_long_form_same_as_is_equivalent(tmp_path):
    ns = _namespace(
        tmp_path,
        users=_collection(5, email={"type": "string",
                                    "faker": {"generator": "safe_email"}}),
        orders=_collection(9, buyer={"type": "same_as",
                                     "ref": "users.content.email"}),
    )
    schema, _ = build_schema_from_synth(ns)
    assert schema.relationships[0].parent_key == "email"


def test_generated_data_respects_the_imported_keys(tmp_path):
    ns = _namespace(
        tmp_path,
        User=_collection(20, id={"type": "number", "id": {}}),
        Post=_collection(80, id={"type": "number", "id": {}},
                         authorId="@User.content.id"),
    )
    schema, _ = build_schema_from_synth(ns)
    data = misata.generate_from_schema(schema)

    assert data["User"]["id"].nunique() == len(data["User"]), \
        "an `id: {}` column is a sequential counter in synth and must stay unique"
    assert data["Post"]["authorId"].isin(data["User"]["id"]).all(), \
        "every imported reference must resolve"


def test_categorical_weights_are_normalised(tmp_path):
    ns = _namespace(tmp_path, t=_collection(
        10, ccy={"type": "string", "categorical": {"USD": 8, "GBP": 1, "EUR": 1}}))
    schema, _ = build_schema_from_synth(ns)
    col = schema.columns["t"][0]
    assert col.type == "categorical"
    assert col.distribution_params["choices"] == ["USD", "GBP", "EUR"]
    assert sum(col.distribution_params["weights"]) == pytest.approx(1.0)


def test_one_of_with_null_variant_is_a_nullable_column(tmp_path):
    ns = _namespace(tmp_path, t=_collection(10, note={
        "type": "one_of",
        "variants": [{"weight": 9, "type": "string",
                      "faker": {"generator": "name"}},
                     {"weight": 1, "type": "null"}]}))
    schema, _ = build_schema_from_synth(ns)
    col = schema.columns["t"][0]
    assert col.nullable is True
    assert col.distribution_params["subtype"] == "name"


def test_number_range_maps_to_bounds(tmp_path):
    ns = _namespace(tmp_path, t=_collection(10, score={
        "type": "number", "subtype": "f64",
        "range": {"low": 1, "high": 4, "step": 1}}))
    col = build_schema_from_synth(ns)[0].columns["t"][0]
    assert col.type == "float"
    assert (col.distribution_params["min"], col.distribution_params["max"]) == (1, 4)


def test_regex_patterns_are_reported_not_invented(tmp_path):
    """synth's `pattern` is a regex generator. Misata has no equivalent, and
    silently emitting free text where a code format was required is exactly
    the kind of quiet wrongness this project exists to avoid."""
    ns = _namespace(tmp_path, t=_collection(
        10, sku={"type": "string", "pattern": "[A-Z]{3}-[0-9]{4}"}))
    _, report = build_schema_from_synth(ns)
    assert any("pattern" in u for u in report.unsupported)


def test_reference_to_a_missing_collection_is_reported(tmp_path):
    ns = _namespace(tmp_path, Post=_collection(
        10, authorId="@User.content.id"))
    schema, report = build_schema_from_synth(ns)
    assert schema.relationships == []
    assert any("not in this namespace" in u for u in report.unsupported)


def test_length_accepts_a_generator_node(tmp_path):
    ns = _namespace(tmp_path, t=_collection(
        {"type": "number", "constant": 250},
        id={"type": "number", "id": {}}))
    schema, _ = build_schema_from_synth(ns)
    assert schema.tables[0].row_count == 250


def test_scale_multiplies_row_counts(tmp_path):
    ns = _namespace(tmp_path, t=_collection(3, id={"type": "number", "id": {}}))
    schema, _ = build_schema_from_synth(ns, scale=100)
    assert schema.tables[0].row_count == 300


def test_find_namespace_ignores_a_folder_of_unrelated_json(tmp_path, monkeypatch):
    (tmp_path / "synth").mkdir()
    (tmp_path / "synth" / "tsconfig.json").write_text('{"compilerOptions": {}}')
    monkeypatch.chdir(tmp_path)
    assert find_synth_namespace(tmp_path) is None
