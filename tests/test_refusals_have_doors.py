"""A refusal is only an improvement if it hands you the way through.

Two properties, both easy to lose:

  * Every remedy a conflict prints must actually resolve it. A remedy nobody
    checks is a guess in an error message, and following a wrong one is worse
    than being told nothing.
  * Nothing is ever hard-blocked. `strict=False` still generates, exactly as it
    did before any of these checks existed, so a refusal is a default and not a
    restriction.

And one contract: lint answers "will this generate?", so anything generation
refuses has to appear in lint. Two modules used to answer that question
separately with nothing making them agree.
"""

import warnings

import pytest

import misata
from misata.feasibility import InfeasibleSchema, find_conflicts
from misata.lint import lint_schema


def _generate(schema, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return misata.generate_from_schema(misata.from_dict_schema(schema, seed=1), **kw)


# Each case: an impossible schema, and the same schema with its own stated
# remedy applied. The remedy text is quoted in the comment so a change to the
# message that invalidates the fix shows up here.
CASES = {
    # "raise nodes above 347 rows, or lower edges to at most 19,900"
    "dag capacity": (
        {"nodes": {"__rows__": 200, "id": {"type": "integer", "primary_key": True}},
         "edges": {"__rows__": 60000, "parent": {"type": "integer"},
                   "child": {"type": "integer"}},
         "__dag_edges__": [{"name": "t", "table": "edges", "node_table": "nodes",
                            "node_key": "id", "from_column": "parent",
                            "to_column": "child"}]},
        {"nodes": {"__rows__": 400, "id": {"type": "integer", "primary_key": True}},
         "edges": {"__rows__": 60000, "parent": {"type": "integer"},
                   "child": {"type": "integer"}},
         "__dag_edges__": [{"name": "t", "table": "edges", "node_table": "nodes",
                            "node_key": "id", "from_column": "parent",
                            "to_column": "child"}]},
    ),
    # "widen the date range, use a finer minute_grid, drop unique, or lower rows"
    "grid capacity": (
        {"appt": {"__rows__": 50000,
                  "slot": {"type": "datetime", "unique": True,
                           "start": "2026-01-01", "end": "2026-12-31"}},
         "__time_grids__": [{"table": "appt", "column": "slot",
                             "minute_grid": 60, "hours": [9, 17]}]},
        {"appt": {"__rows__": 2000,
                  "slot": {"type": "datetime", "unique": True,
                           "start": "2026-01-01", "end": "2026-12-31"}},
         "__time_grids__": [{"table": "appt", "column": "slot",
                             "minute_grid": 60, "hours": [9, 17]}]},
    ),
    # "scale inflow_shares so the values total 1.0"
    "waterfall shares": (
        {"m": {"__rows__": 300, "period": {"type": "string"},
               "movement_type": {"type": "string"}, "amount": {"type": "float"}},
         "__waterfalls__": [{"table": "m", "starting_value": 1000,
                             "points": [{"period": "2026-01", "ending_value": 1200}],
                             "inflow_shares": {"new": 0.7, "expansion": 0.9},
                             "outflow_shares": {"churn": 1.0}}]},
        {"m": {"__rows__": 300, "period": {"type": "string"},
               "movement_type": {"type": "string"}, "amount": {"type": "float"}},
         "__waterfalls__": [{"table": "m", "starting_value": 1000,
                             "points": [{"period": "2026-01", "ending_value": 1200}],
                             "inflow_shares": {"new": 0.7, "expansion": 0.3},
                             "outflow_shares": {"churn": 1.0}}]},
    ),
    # "lower the count to at most 200, raise the row count, or use a fraction"
    "duplicates over rows": (
        {"t": {"__rows__": 200, "id": {"type": "integer", "primary_key": True}},
         "__duplicates__": [{"table": "t", "count": 500}]},
        {"t": {"__rows__": 200, "id": {"type": "integer", "primary_key": True}},
         "__duplicates__": [{"table": "t", "count": 40}]},
    ),
    # "raise the table to at least avg_versions rows"
    "history depth": (
        {"p": {"__rows__": 10, "sku": {"type": "string"}, "vf": {"type": "date"},
               "vt": {"type": "date"}, "ra": {"type": "datetime"},
               "sa": {"type": "datetime"}},
         "__bitemporal__": [{"name": "h", "table": "p", "entity_columns": ["sku"],
                             "valid_from": "vf", "valid_to": "vt",
                             "recorded_at": "ra", "superseded_at": "sa",
                             "avg_versions": 50}]},
        {"p": {"__rows__": 500, "sku": {"type": "string"}, "vf": {"type": "date"},
               "vt": {"type": "date"}, "ra": {"type": "datetime"},
               "sa": {"type": "datetime"}},
         "__bitemporal__": [{"name": "h", "table": "p", "entity_columns": ["sku"],
                             "valid_from": "vf", "valid_to": "vt",
                             "recorded_at": "ra", "superseded_at": "sa",
                             "avg_versions": 50}]},
    ),
}


@pytest.mark.parametrize("name", list(CASES))
def test_the_impossible_schema_is_refused(name):
    broken, _ = CASES[name]
    with pytest.raises(InfeasibleSchema):
        _generate(broken)


@pytest.mark.parametrize("name", list(CASES))
def test_the_stated_remedy_actually_resolves_it(name):
    """The property that makes a refusal a door. Following the message must
    produce a schema that generates, or the message is a guess."""
    _, fixed = CASES[name]
    tables = _generate(fixed)
    assert tables and all(len(df) for df in tables.values()), \
        f"{name}: the remedy left a schema that generates nothing"


@pytest.mark.parametrize("name", list(CASES))
def test_every_refusal_carries_a_remedy_and_the_arithmetic(name):
    broken, _ = CASES[name]
    conflicts = find_conflicts(misata.from_dict_schema(broken, seed=1))
    assert conflicts
    for conflict in conflicts:
        assert conflict.remedy.strip(), f"{name}: no remedy"
        assert any(ch.isdigit() for ch in conflict.arithmetic), \
            f"{name}: the arithmetic shows no numbers, so it proves nothing"


@pytest.mark.parametrize("name", list(CASES))
def test_nothing_is_hard_blocked(name):
    """strict=False generates exactly as it did before any of these existed.
    A refusal is the default, not a restriction."""
    broken, _ = CASES[name]
    tables = _generate(broken, strict=False)
    assert tables, f"{name}: strict=False must still generate"


@pytest.mark.parametrize("name", list(CASES))
def test_lint_reports_whatever_generation_refuses(name):
    """Lint's promise is "will this generate?". Two modules used to answer that
    separately, so lint called schemas clean that generate rejected outright."""
    broken, _ = CASES[name]
    schema = misata.from_dict_schema(broken, seed=1)
    errors = [f for f in lint_schema(schema) if f.severity == "error"]
    assert errors, f"{name}: generation refuses this and lint said nothing"


def test_a_healthy_schema_lints_clean_and_generates():
    """The other half: nothing valid is caught by any of it."""
    healthy = {
        "customers": {"__rows__": 500, "id": {"type": "integer", "primary_key": True},
                      "name": {"type": "text", "semantic": "person_name"}},
        "orders": {"__rows__": 5000, "id": {"type": "integer", "primary_key": True},
                   "customer_id": {"type": "foreign_key",
                                   "foreign_key": {"table": "customers", "column": "id"}},
                   "placed_at": {"type": "date"},
                   "category": {"type": "string", "enum": ["a", "b", "c"]},
                   "revenue": {"type": "float", "min": 10, "max": 900}},
        "__group_shares__": [{"table": "orders", "measure": "revenue",
                              "group_column": "category",
                              "shares": {"a": 0.5, "b": 0.3, "c": 0.2}}],
        "__duplicates__": [{"table": "orders", "count": 50}],
    }
    schema = misata.from_dict_schema(healthy, seed=1)
    assert not [f for f in lint_schema(schema) if f.severity == "error"]
    assert len(_generate(healthy)["orders"]) == 5000
