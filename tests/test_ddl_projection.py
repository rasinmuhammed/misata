"""The DDL projection must stay honest about what it removes.

The claim this projection supports is narrow and worth protecting: a fixed set
of assertions is unreachable once the declarations are gone, because the
information is no longer in the input. If someone later widens the projection
so it quietly keeps a rollup, the claim silently becomes false. These tests
fail instead.
"""

import pytest

from benchmarks.gauntlet import build_schema
from benchmarks.gauntlet_compare import project_to_ddl


def test_projection_removes_every_cross_table_declaration():
    reduced, dropped = project_to_ddl(build_schema())

    for cols in reduced.columns.values():
        for col in cols:
            assert "rollup" not in (col.distribution_params or {}), (
                f"{col.name} kept a rollup; a CREATE TABLE cannot express an "
                f"aggregate over another table")

    for t in reduced.tables:
        for c in (t.constraints or []):
            assert c.type in {"inequality", "when_then"}, (
                f"{c.name} is a {c.type}, which no single-row CHECK can state")

    assert not reduced.missingness and not reduced.late_arrivals
    assert not reduced.duplicates
    assert dropped, "a projection that drops nothing is not a projection"


def test_projection_keeps_what_ddl_genuinely_carries():
    """Generosity is load-bearing. A baseline that strips things a real DDL
    could state would overstate the gap, so the argument does not rely on it."""
    reduced, _ = project_to_ddl(build_schema())

    assert len(reduced.relationships) == len(build_schema().relationships), \
        "foreign keys are the one cross-table thing DDL does express"

    cat = next(c for c in reduced.columns["categories"]
               if c.name == "category_name")
    assert cat.distribution_params.get("choices"), "an enum is a CHECK ... IN"

    prod = next(c for c in reduced.columns["products"] if c.name == "price")
    assert prod.distribution_params.get("formula"), \
        "a single-row formula is a legitimate CHECK and is kept on purpose"

    assert reduced.lifecycles, "a lifecycle is a single-row fact; kept"


def test_projection_does_not_mutate_the_original():
    original = build_schema()
    before = len(original.columns["customers"][10].distribution_params)
    project_to_ddl(original)
    assert len(original.columns["customers"][10].distribution_params) == before
