"""misata.explain: the plan for a schema matches what generation then does."""

from __future__ import annotations

import json
import warnings

import pytest

import misata
from misata.attestation import derive_invariants
from misata.explain import explain
from misata.feasibility import InfeasibleSchema


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


def _curved() -> misata.SchemaConfig:
    from misata import OutcomeCurveBuilder

    schema = misata.from_dict_schema({
        "customers": {"__rows__": 80, "id": {"type": "int", "primary_key": True}},
        "orders": {
            "__rows__": 500,
            "id": {"type": "int", "primary_key": True},
            "customer_id": {"type": "foreign_key", "references": "customers.id"},
            "amount": {"type": "float", "min": 1, "max": 5000},
            "ordered_at": {"type": "date", "start": "2024-01-01", "end": "2024-06-30"},
        },
    }, seed=4)
    curve = (OutcomeCurveBuilder("orders", column="amount", time_column="ordered_at")
             .anchor("2024-01", 9_000).anchor("2024-06", 21_000)
             .avg_value(60.0).row_bounds(1, 5_000).build())
    return OutcomeCurveBuilder.attach(schema, curve)


def test_planned_rows_are_the_rows_generated():
    schema = _curved()
    plan = explain(schema)
    tables = misata.generate_from_schema(schema)
    assert {t["name"]: t["rows"] for t in plan.tables} == {k: len(v) for k, v in tables.items()}
    assert next(t for t in plan.tables if t["name"] == "orders")["rows_from"] == "outcome curve plan"


def test_invariants_are_the_ones_an_attestation_checks():
    schema = _curved()
    assert [i["id"] for i in explain(schema).invariants] == [
        i.id for i in derive_invariants(schema)]


def test_declarations_and_writers_name_the_curve():
    plan = explain(_curved())
    assert [d["key"] for d in plan.declarations] == ["outcome_curves"]
    assert plan.writers["orders.amount"] == ["outcome_curve"]


def test_conflicts_mean_it_will_not_generate():
    plan = explain({"a": {"__rows__": 10, "x": {"type": "int", "unique": True,
                                                "min": 1, "max": 5}}})
    assert plan.will_generate is False
    assert plan.conflicts[0].kind == "unique_range_too_narrow"
    assert plan.invariants == []
    with pytest.raises(InfeasibleSchema):
        misata.generate_from_schema(
            misata.from_dict_schema({"a": {"__rows__": 10, "x": {
                "type": "int", "unique": True, "min": 1, "max": 5}}}))


def test_it_is_json_and_generates_nothing(monkeypatch):
    from misata.simulator import DataSimulator

    def refuse(*_args, **_kwargs):
        raise AssertionError("explain must not generate")

    monkeypatch.setattr(DataSimulator, "generate_all", refuse)
    payload = explain(_curved()).to_dict()
    assert json.loads(json.dumps(payload))["will_generate"] is True
    assert payload["estimated_bytes"] > 0
