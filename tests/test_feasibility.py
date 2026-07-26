"""Contradictory declarations must be refused with proof, not silently resolved.

This is the behaviour that separates a declarative engine from a generator with
a lot of options. When two declarations cannot both hold, the engine owes the
user a compiler error: which declarations conflict, what the arithmetic says,
and what to change. What it must never do is apply them in sequence and let
whichever ran last silently win, because the output then looks authoritative
while quietly violating something the user declared.

0.8.8.5 shipped exactly that bug: an inferred roll-up overwrote a declared
outcome curve, 23% off, no warning. This suite exists so the whole class is
caught by construction rather than one instance at a time.

Every test here states a contradiction and asserts that Misata REFUSES, that
the message names both conflicting declarations, and that it says what to do.
"""

import warnings

import pytest

import misata
from misata.exceptions import SchemaValidationError
from misata.feasibility import check_feasibility, InfeasibleSchema
from misata.schema import (SchemaConfig, Table, Column, Relationship, Constraint,
                           GroupShares, OutcomeCurve,
                           Lifecycle, LifecycleState)

warnings.filterwarnings("ignore")


def _base(rows=200, seed=5, **over):
    cfg = dict(
        name="feas",
        tables=[Table(name="orders", row_count=rows)],
        columns={
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": rows}),
                Column(name="order_date", type="datetime",
                       distribution_params={"start": "2024-01-01", "end": "2024-12-31"}),
                Column(name="status", type="categorical",
                       distribution_params={"choices": ["placed", "shipped", "done"]}),
                Column(name="segment", type="categorical",
                       distribution_params={"choices": ["smb", "mid", "ent"]}),
                Column(name="amount", type="float",
                       distribution_params={"min": 10.0, "max": 500.0}),
                Column(name="cost", type="float",
                       distribution_params={"min": 5.0, "max": 400.0}),
            ],
        },
        seed=seed,
    )
    cfg.update(over)
    return SchemaConfig(**cfg)


# --------------------------------------------------------------------------- #
# arithmetic contradictions
# --------------------------------------------------------------------------- #

class TestSharesArithmetic:
    def test_shares_over_one_is_refused(self):
        s = _base(group_shares=[GroupShares(
            table="orders", measure="amount", group_column="segment",
            shares={"smb": 0.6, "mid": 0.6, "ent": 0.3})])
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        msg = str(e.value)
        assert "1.5" in msg or "150" in msg
        assert "segment" in msg

    def test_shares_naming_absent_group_is_refused(self):
        s = _base(group_shares=[GroupShares(
            table="orders", measure="amount", group_column="segment",
            shares={"smb": 0.5, "enterprise_plus": 0.5})])
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        assert "enterprise_plus" in str(e.value)

    def test_valid_shares_pass(self):
        s = _base(group_shares=[GroupShares(
            table="orders", measure="amount", group_column="segment",
            shares={"smb": 0.5, "mid": 0.3, "ent": 0.2})])
        check_feasibility(s)   # must not raise


class TestBoundsArithmetic:
    def test_impossible_range_is_refused(self):
        s = _base()
        for c in s.columns["orders"]:
            if c.name == "amount":
                c.distribution_params = {"min": 500.0, "max": 10.0}
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        assert "amount" in str(e.value)

    def test_unique_column_narrower_than_row_count_is_refused(self):
        s = _base(rows=200)
        for c in s.columns["orders"]:
            if c.name == "order_id":
                c.distribution_params = {"min": 1, "max": 50}
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        m = str(e.value)
        assert "order_id" in m and ("200" in m and "50" in m)

    def test_inequality_against_disjoint_ranges_is_refused(self):
        # price must exceed cost, but price's range is entirely below cost's.
        s = _base()
        for c in s.columns["orders"]:
            if c.name == "amount":
                c.distribution_params = {"min": 1.0, "max": 5.0}
            if c.name == "cost":
                c.distribution_params = {"min": 100.0, "max": 200.0}
        s.tables[0].constraints = [Constraint(
            name="amount_over_cost", type="inequality",
            column_a="amount", operator=">", column_b="cost")]
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        m = str(e.value)
        assert "amount" in m and "cost" in m


# --------------------------------------------------------------------------- #
# declarations that fight each other over the same column
# --------------------------------------------------------------------------- #

class TestOverlappingGovernance:
    def test_curve_and_rollup_on_the_same_column_is_refused(self):
        """The 0.8.8.5 bug, as a refusal.

        A declared outcome curve is an exact promise about a column's per-period
        totals. A roll-up recomputes that column from child rows. Both cannot
        own it.
        """
        s = SchemaConfig(
            name="clash",
            tables=[Table(name="orders", row_count=200),
                    Table(name="items", row_count=600)],
            columns={
                "orders": [
                    Column(name="order_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 200}),
                    Column(name="order_date", type="datetime",
                           distribution_params={"start": "2024-01-01", "end": "2024-12-31"}),
                    Column(name="total", type="float",
                           distribution_params={"rollup": {
                               "from_table": "items", "fk": "order_id",
                               "agg": "sum", "column": "line_total"}}),
                ],
                "items": [
                    Column(name="item_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 600}),
                    Column(name="order_id", type="foreign_key",
                           distribution_params={"references": "orders.order_id"}),
                    Column(name="line_total", type="float",
                           distribution_params={"min": 1.0, "max": 100.0}),
                ],
            },
            relationships=[Relationship(parent_table="orders", child_table="items",
                                        parent_key="order_id", child_key="order_id")],
            outcome_curves=[OutcomeCurve(
                table="orders", column="total", time_column="order_date",
                curve_points=[{"month": 1, "relative_value": 1000.0},
                              {"month": 6, "relative_value": 2000.0}])],
            seed=5,
        )
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        m = str(e.value)
        assert "total" in m
        assert "rollup" in m.lower() and "curve" in m.lower()

    def test_lifecycle_and_when_then_disagreeing_is_refused(self):
        """A lifecycle already implies every status/timestamp rule. A when_then
        that contradicts the machine is a genuine conflict, not a redundancy."""
        s = _base()
        s.columns["orders"].append(
            Column(name="shipped_at", type="datetime", nullable=True,
                   distribution_params={"start": "2024-01-01", "end": "2024-12-31"}))
        s.lifecycles = [Lifecycle(
            name="lc", table="orders", state_column="status", initial="placed",
            states=[LifecycleState(name="placed"),
                    LifecycleState(name="shipped", timestamp="shipped_at"),
                    LifecycleState(name="done", terminal=True)],
            transitions=[("placed", "shipped"), ("shipped", "done")])]
        # The machine says a 'placed' row has NO shipped_at. This says it must.
        s.tables[0].constraints = [Constraint(
            name="contradicts_machine", type="when_then",
            when_column="status", when_op="==", when_value="placed",
            then_column="shipped_at", then="not_null")]
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        m = str(e.value)
        assert "contradicts_machine" in m and "lc" in m

    def test_lifecycle_agreeing_with_when_then_passes(self):
        s = _base()
        s.columns["orders"].append(
            Column(name="shipped_at", type="datetime", nullable=True,
                   distribution_params={"start": "2024-01-01", "end": "2024-12-31"}))
        s.lifecycles = [Lifecycle(
            name="lc", table="orders", state_column="status", initial="placed",
            states=[LifecycleState(name="placed"),
                    LifecycleState(name="shipped", timestamp="shipped_at"),
                    LifecycleState(name="done", terminal=True)],
            transitions=[("placed", "shipped"), ("shipped", "done")])]
        s.tables[0].constraints = [Constraint(
            name="agrees", type="when_then",
            when_column="status", when_op="==", when_value="placed",
            then_column="shipped_at", then="null")]
        check_feasibility(s)   # redundant but consistent: allowed

    def test_two_lifecycles_on_one_column_is_refused(self):
        s = _base()
        lc = lambda n: Lifecycle(
            name=n, table="orders", state_column="status", initial="placed",
            states=[LifecycleState(name="placed"), LifecycleState(name="done", terminal=True)],
            transitions=[("placed", "done")])
        s.lifecycles = [lc("first"), lc("second")]
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        assert "first" in str(e.value) and "second" in str(e.value)


# --------------------------------------------------------------------------- #
# structural impossibilities
# --------------------------------------------------------------------------- #

class TestStructural:
    def test_min_children_beyond_child_capacity_is_refused(self):
        s = SchemaConfig(
            name="cover",
            tables=[Table(name="orders", row_count=100),
                    Table(name="items", row_count=120)],
            columns={
                "orders": [Column(name="order_id", type="int", unique=True,
                                  distribution_params={"min": 1, "max": 100})],
                "items": [
                    Column(name="item_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 120}),
                    Column(name="order_id", type="foreign_key",
                           distribution_params={"references": "orders.order_id"}),
                ],
            },
            relationships=[Relationship(
                parent_table="orders", child_table="items",
                parent_key="order_id", child_key="order_id", min_children=3)],
            seed=5,
        )
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        m = str(e.value)
        assert "300" in m and "120" in m

    def test_lifecycle_weight_on_unreachable_state_is_refused(self):
        s = _base()
        s.lifecycles = [Lifecycle(
            name="lc", table="orders", state_column="status", initial="placed",
            states=[LifecycleState(name="placed"),
                    LifecycleState(name="shipped"),
                    LifecycleState(name="done", terminal=True)],
            transitions=[("placed", "shipped")],       # 'done' unreachable
            weights={"placed": .4, "shipped": .3, "done": .3})]
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        assert "done" in str(e.value)


# --------------------------------------------------------------------------- #
# the refusal contract itself
# --------------------------------------------------------------------------- #

class TestRefusalQuality:
    def test_error_names_a_remedy(self):
        s = _base(group_shares=[GroupShares(
            table="orders", measure="amount", group_column="segment",
            shares={"smb": 0.6, "mid": 0.6})])
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        # A refusal without a remedy is just a rejection.
        assert "→" in str(e.value) or "Suggestion" in str(e.value)

    def test_reports_every_conflict_not_just_the_first(self):
        s = _base(group_shares=[GroupShares(
            table="orders", measure="amount", group_column="segment",
            shares={"smb": 0.7, "mid": 0.7})])
        for c in s.columns["orders"]:
            if c.name == "order_id":
                c.distribution_params = {"min": 1, "max": 10}
        with pytest.raises(InfeasibleSchema) as e:
            check_feasibility(s)
        assert len(e.value.conflicts) >= 2

    def test_is_a_schema_validation_error(self):
        """Callers already catching SchemaValidationError keep working."""
        assert issubclass(InfeasibleSchema, SchemaValidationError)

    def test_generation_refuses_by_default(self):
        s = _base(group_shares=[GroupShares(
            table="orders", measure="amount", group_column="segment",
            shares={"smb": 0.8, "mid": 0.8})])
        with pytest.raises(InfeasibleSchema):
            misata.generate_from_schema(s)

    def test_feasible_schema_still_generates(self):
        s = _base(group_shares=[GroupShares(
            table="orders", measure="amount", group_column="segment",
            shares={"smb": 0.5, "mid": 0.3, "ent": 0.2})])
        t = misata.generate_from_schema(s)
        assert len(t["orders"]) == 200
