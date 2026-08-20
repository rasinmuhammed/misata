"""`generate_from_schema` must accept the shape people actually have.

A dict is what an LLM emits, what the MCP tool takes, and the first thing
anyone tries. Passing one used to reach the validator untouched and fail with
`'dict' object has no attribute 'tables'`, which names an internal detail and
no remedy.
"""

import pytest

import misata


def _schema():
    return {
        "name": "t", "seed": 1,
        "tables": {
            "parents": {"rows": 20, "columns": {
                "parent_id": {"type": "int", "unique": True, "min": 1, "max": 200}}},
            "children": {"rows": 60, "columns": {
                "child_id": {"type": "int", "unique": True, "min": 1, "max": 600},
                "parent_id": {"type": "foreign_key",
                              "references": "parents.parent_id"},
                "qty": {"type": "int", "min": 1, "max": 4},
                "price": {"type": "float", "min": 1, "max": 50},
                "total": {"type": "float", "formula": "qty * price"}}}}}


def test_a_plain_dict_generates_without_a_conversion_import():
    tables = misata.generate_from_schema(_schema())
    assert set(tables) == {"parents", "children"}
    assert len(tables["children"]) == 60


def test_the_dict_path_keeps_its_guarantees():
    tables = misata.generate_from_schema(_schema())
    child = tables["children"]

    assert child["parent_id"].isin(tables["parents"]["parent_id"]).all(), \
        "foreign keys must resolve on the dict path too"
    assert ((child["total"] - child["qty"] * child["price"]).abs() < 0.01).all(), \
        "a declared formula must hold however the schema was handed over"


def test_dict_and_converted_schema_agree():
    from misata.compat import from_dict_schema

    direct = misata.generate_from_schema(_schema())
    explicit = misata.generate_from_schema(from_dict_schema(_schema()))
    for name in direct:
        assert len(direct[name]) == len(explicit[name])
