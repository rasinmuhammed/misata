"""Declaring duplicates must not orphan the rows that point at them.

Found running the branch's own guarantees end to end. A `duplicates`
declaration on a parent table overwrote whole rows including the primary key,
so the donor's id appeared twice, the recipient's id disappeared, and every
child row referencing it was orphaned. Measured on 3,000 customers with 30
declared duplicates: 2,970 distinct ids and 211 orphaned orders, against a
guarantee of zero that the README states unconditionally. Silent, and present
on main.

The mechanism to prevent it already existed. `keys` are excluded from the
copied `subset`, and the docstring said "keys stay unique"; nothing was putting
the table's own primary key in it.

Semantics improve as well as integrity: a duplicate record in the real world is
the same entity entered twice under different surrogate keys, which is exactly
what a deduplication step is asked to find. Copying the key too made it a
different and less useful fixture.
"""

import warnings

import pytest

import misata
from misata.compat import verify_integrity

SCHEMA = {
    "customers": {"__rows__": 3000,
                  "id": {"type": "integer", "primary_key": True},
                  "name": {"type": "text", "semantic": "person_name"},
                  "email": {"type": "email"}},
    "orders": {"__rows__": 20000,
               "id": {"type": "integer", "primary_key": True},
               "customer_id": {"type": "foreign_key",
                               "foreign_key": {"table": "customers", "column": "id"}}},
    "__duplicates__": [{"table": "customers", "count": 30}],
}


@pytest.fixture(scope="module")
def run():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        config = misata.from_dict_schema(SCHEMA, seed=42)
        return config, misata.generate_from_schema(config)


def test_no_child_row_is_orphaned(run):
    """The guarantee the whole engine is sold on."""
    config, tables = run
    report = verify_integrity(tables, config)
    assert sum(r["orphans"] for r in report.relationships) == 0


def test_every_primary_key_survives(run):
    _, tables = run
    customers = tables["customers"]
    assert customers["id"].nunique() == len(customers)


def test_the_declared_count_still_holds_on_the_business_columns(run):
    """Preserving identity must not cost the declaration. Thirty rows are still
    duplicates of another row in everything that is not a key."""
    _, tables = run
    customers = tables["customers"]
    business = [c for c in customers.columns if c != "id"]
    assert len(customers) - len(customers[business].drop_duplicates()) == 30


def test_an_explicit_subset_is_still_the_callers_call():
    """Only the DEFAULT changed. Someone who names the columns to copy has said
    what they want, including a key if they meant it."""
    schema = {
        "t": {"__rows__": 500, "id": {"type": "integer", "primary_key": True},
              "a": {"type": "string", "enum": ["p", "q", "r", "s"]},
              "b": {"type": "float", "min": 1, "max": 1_000_000}},
        "__duplicates__": [{"table": "t", "count": 20, "subset": ["id", "a", "b"]}],
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=3))
    df = tables["t"]
    assert len(df) - len(df.drop_duplicates()) == 20, \
        "an explicit subset naming the key must still copy the key"


def test_a_table_nobody_references_still_duplicates_whole_rows():
    """Where there is no relationship to break, the id is still protected: a
    duplicate with a distinct surrogate key is the useful fixture either way."""
    schema = {
        "events": {"__rows__": 800, "id": {"type": "integer", "primary_key": True},
                   "kind": {"type": "string", "enum": ["a", "b", "c"]},
                   "value": {"type": "float", "min": 1, "max": 1_000_000}},
        "__duplicates__": [{"table": "events", "count": 25}],
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = misata.generate_from_schema(misata.from_dict_schema(schema, seed=3))["events"]
    assert df["id"].nunique() == len(df)
    business = [c for c in df.columns if c != "id"]
    assert len(df) - len(df[business].drop_duplicates()) == 25
