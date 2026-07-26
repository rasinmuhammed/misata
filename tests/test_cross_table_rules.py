"""Tests for the 0.8.9.2 relational-integrity features.

Five primitives, one theme — the rules that make a multi-table dataset survive
a hostile JOIN review:

- when_then:        a status gates its dependent columns (G1)
- rollup via:       parent aggregates reached through intermediate tables (G2)
- lte_parent /
  sum_lte_parent:   child money bounded by the parent's, row and group level
- min_children:     every parent covered by at least N child rows
- relationship
  list filters:     FK sampling restricted to parents in an allowed status set

Each feature is asserted three ways where it applies: the generated data obeys
the rule, coherence_audit reports a violation when the rule is broken by
construction, and existing behaviour without the declaration is unchanged.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata.coherence import coherence_audit
from misata.schema import SchemaConfig, Table, Column, Relationship, Constraint

warnings.filterwarnings("ignore")


# --------------------------------------------------------------------------- #
# when_then
# --------------------------------------------------------------------------- #

def _subs_schema(with_rules=True, seed=11):
    constraints = []
    if with_rules:
        constraints = [
            Constraint(name="cancelled_needs_date", type="when_then",
                       when_column="status", when_op="==", when_value="cancelled",
                       then_column="cancelled_at", then="not_null"),
            Constraint(name="live_has_no_date", type="when_then",
                       when_column="status", when_op="in",
                       when_value=["active", "trial"],
                       then_column="cancelled_at", then="null"),
        ]
    return SchemaConfig(
        name="subs",
        tables=[Table(name="subscriptions", row_count=400, constraints=constraints)],
        columns={
            "subscriptions": [
                Column(name="subscription_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 400}),
                Column(name="status", type="categorical",
                       distribution_params={"choices": ["active", "trial", "cancelled"],
                                            "weights": [0.5, 0.2, 0.3]}),
                Column(name="cancelled_at", type="datetime", nullable=True,
                       distribution_params={"start": "2024-01-01", "end": "2025-06-30",
                                            "null_probability": 0.5}),
            ],
        },
        seed=seed,
    )


class TestWhenThen:
    def test_not_null_direction(self):
        df = misata.generate_from_schema(_subs_schema())["subscriptions"]
        cancelled = df[df["status"] == "cancelled"]
        assert len(cancelled) > 0
        assert cancelled["cancelled_at"].notna().all()

    def test_null_direction(self):
        df = misata.generate_from_schema(_subs_schema())["subscriptions"]
        live = df[df["status"].isin(["active", "trial"])]
        assert len(live) > 0
        assert live["cancelled_at"].isna().all()

    def test_set_semantics(self):
        schema = _subs_schema(with_rules=False)
        schema.tables[0].constraints = [
            Constraint(name="flagged", type="when_then",
                       when_column="status", when_op="==", when_value="cancelled",
                       then_column="cancelled_at", then="set",
                       then_value="2025-01-01"),
        ]
        df = misata.generate_from_schema(schema)["subscriptions"]
        cancelled = df[df["status"] == "cancelled"]
        assert (pd.to_datetime(cancelled["cancelled_at"]) ==
                pd.Timestamp("2025-01-01")).all()

    def test_audit_detects_broken_rule(self):
        schema = _subs_schema()
        tables = misata.generate_from_schema(schema)
        df = tables["subscriptions"]
        # Break the rule by hand: give an active subscription a cancel date.
        active_idx = df[df["status"] == "active"].index[:5]
        df.loc[active_idx, "cancelled_at"] = pd.Timestamp("2025-01-01")
        report = coherence_audit(tables, schema=schema)
        kinds = [f.kind for f in report.findings]
        assert "when_then_violation" in kinds

    def test_clean_data_audits_clean(self):
        schema = _subs_schema()
        tables = misata.generate_from_schema(schema)
        report = coherence_audit(tables, schema=schema)
        assert not [f for f in report.findings if f.kind == "when_then_violation"]

    def test_missing_column_warns_not_crashes(self):
        schema = _subs_schema(with_rules=False)
        schema.tables[0].constraints = [
            Constraint(name="ghost", type="when_then",
                       when_column="nope", when_op="==", when_value="x",
                       then_column="cancelled_at", then="null"),
        ]
        with pytest.warns(UserWarning):
            misata.generate_from_schema(schema)


# --------------------------------------------------------------------------- #
# multi-hop rollups (via)
# --------------------------------------------------------------------------- #

def _three_hop_schema(seed=5):
    return SchemaConfig(
        name="ltv",
        tables=[Table(name="customers", row_count=60),
                Table(name="orders", row_count=300),
                Table(name="payments", row_count=400)],
        columns={
            "customers": [
                Column(name="customer_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 60}),
                Column(name="lifetime_value", type="float",
                       distribution_params={"rollup": {
                           "from_table": "payments", "via": ["orders"],
                           "fk": "customer_id", "agg": "sum", "column": "amount"}}),
            ],
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 300}),
                Column(name="customer_id", type="foreign_key",
                       distribution_params={"references": "customers.customer_id"}),
            ],
            "payments": [
                Column(name="payment_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 400}),
                Column(name="order_id", type="foreign_key",
                       distribution_params={"references": "orders.order_id"}),
                Column(name="amount", type="float",
                       distribution_params={"distribution": "lognormal",
                                            "mu": 3.5, "sigma": 0.5, "min": 1}),
            ],
        },
        relationships=[
            Relationship(parent_table="customers", child_table="orders",
                         parent_key="customer_id", child_key="customer_id"),
            Relationship(parent_table="orders", child_table="payments",
                         parent_key="order_id", child_key="order_id"),
        ],
        seed=seed,
    )


class TestMultiHopRollup:
    def test_reconciles_through_two_joins(self):
        tables = misata.generate_from_schema(_three_hop_schema())
        cust, orders, payments = (tables["customers"], tables["orders"],
                                  tables["payments"])
        truth = (payments.merge(orders[["order_id", "customer_id"]], on="order_id")
                 .groupby("customer_id")["amount"].sum())
        got = cust.set_index("customer_id")["lifetime_value"]
        err = (got - truth.reindex(got.index).fillna(0)).abs().max()
        assert err < 1e-6

    def test_grand_total_matches(self):
        tables = misata.generate_from_schema(_three_hop_schema())
        assert abs(tables["customers"]["lifetime_value"].sum()
                   - tables["payments"]["amount"].sum()) < 1e-6

    def test_missing_relationship_is_refused_with_fix(self):
        # Removing the orders->payments relationship is refused up front by the
        # validator, with the exact Relationship(...) line to add — a wrong
        # multi-hop can never silently generate.
        from misata.validation import SchemaValidationError
        schema = _three_hop_schema()
        schema.relationships = [r for r in schema.relationships
                                if r.child_table != "payments"]
        with pytest.raises(SchemaValidationError, match="payments.order_id"):
            misata.generate_from_schema(schema)

    def test_nonexistent_hop_warns_and_leaves_column(self):
        # A via chain through a table that is not a declared parent cannot
        # resolve; the column keeps its generated values and the run warns.
        schema = _three_hop_schema()
        for col in schema.columns["customers"]:
            if col.name == "lifetime_value":
                col.distribution_params["rollup"]["via"] = ["warehouses"]
        with pytest.warns(UserWarning, match="via chain"):
            misata.generate_from_schema(schema)

    def test_audit_follows_the_chain(self):
        schema = _three_hop_schema()
        tables = misata.generate_from_schema(schema)
        tables["customers"].loc[0, "lifetime_value"] += 500.0   # sabotage
        report = coherence_audit(tables, schema=schema)
        assert any(f.kind == "rollup_mismatch" for f in report.findings)


# --------------------------------------------------------------------------- #
# lte_parent / sum_lte_parent
# --------------------------------------------------------------------------- #

def _bounded_schema(seed=9):
    return SchemaConfig(
        name="bounded",
        tables=[
            Table(name="orders", row_count=150),
            Table(name="refunds", row_count=60, constraints=[
                Constraint(name="refund_bounded", type="lte_parent",
                           column="refund_amount",
                           parent_table="orders", parent_column="total"),
            ]),
            Table(name="payments", row_count=300, constraints=[
                Constraint(name="payments_bounded", type="sum_lte_parent",
                           column="amount",
                           parent_table="orders", parent_column="total"),
            ]),
        ],
        columns={
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 150}),
                Column(name="total", type="float",
                       distribution_params={"min": 20.0, "max": 200.0}),
            ],
            "refunds": [
                Column(name="refund_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 60}),
                Column(name="order_id", type="foreign_key",
                       distribution_params={"references": "orders.order_id"}),
                Column(name="refund_amount", type="float",
                       distribution_params={"min": 1.0, "max": 500.0}),
            ],
            "payments": [
                Column(name="payment_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 300}),
                Column(name="order_id", type="foreign_key",
                       distribution_params={"references": "orders.order_id"}),
                Column(name="amount", type="float",
                       distribution_params={"min": 1.0, "max": 400.0}),
            ],
        },
        relationships=[
            Relationship(parent_table="orders", child_table="refunds",
                         parent_key="order_id", child_key="order_id"),
            Relationship(parent_table="orders", child_table="payments",
                         parent_key="order_id", child_key="order_id"),
        ],
        seed=seed,
    )


class TestCrossTableBounds:
    def test_lte_parent_holds_under_join(self):
        t = misata.generate_from_schema(_bounded_schema())
        merged = t["refunds"].merge(
            t["orders"][["order_id", "total"]], on="order_id")
        assert (merged["refund_amount"] <= merged["total"] + 1e-9).all()

    def test_sum_lte_parent_holds_per_group(self):
        t = misata.generate_from_schema(_bounded_schema())
        sums = t["payments"].groupby("order_id")["amount"].sum()
        totals = t["orders"].set_index("order_id")["total"]
        joined = pd.concat([sums, totals], axis=1, join="inner")
        assert (joined["amount"] <= joined["total"] + 1e-6).all()

    def test_proportional_rescale_preserves_shares(self):
        t = misata.generate_from_schema(_bounded_schema())
        # Any order with 2+ payments: shares of the group total stay positive
        # and no single payment was zeroed while its sibling survived.
        pay = t["payments"]
        multi = pay.groupby("order_id").filter(lambda g: len(g) >= 2)
        assert (multi["amount"] > 0).all()

    def test_audit_detects_violation(self):
        schema = _bounded_schema()
        tables = misata.generate_from_schema(schema)
        tables["refunds"].loc[0, "refund_amount"] = 10_000.0   # sabotage
        report = coherence_audit(tables, schema=schema)
        assert any(f.kind == "cross_table_bound" for f in report.findings)

    def test_undeclared_constraint_pair_warns(self):
        # The FK relationship stays intact (the validator demands it), but the
        # constraint names a parent with no declared relationship to the child:
        # the fk is never guessed, the run warns and skips the clamp.
        schema = _bounded_schema()
        for t in schema.tables:
            if t.name == "refunds":
                t.constraints[0].parent_table = "payments"
                t.constraints[0].parent_column = "amount"
        with pytest.warns(UserWarning, match="no declared relationship"):
            misata.generate_from_schema(schema)


# --------------------------------------------------------------------------- #
# min_children
# --------------------------------------------------------------------------- #

def _coverage_schema(min_children=1, child_rows=300, seed=13):
    return SchemaConfig(
        name="cover",
        tables=[Table(name="orders", row_count=100),
                Table(name="items", row_count=child_rows)],
        columns={
            "orders": [Column(name="order_id", type="int", unique=True,
                              distribution_params={"min": 1, "max": 100})],
            "items": [
                Column(name="item_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": child_rows}),
                Column(name="order_id", type="foreign_key",
                       distribution_params={"references": "orders.order_id"}),
            ],
        },
        relationships=[
            Relationship(parent_table="orders", child_table="items",
                         parent_key="order_id", child_key="order_id",
                         min_children=min_children),
        ],
        seed=seed,
    )


class TestMinChildren:
    def test_every_parent_covered(self):
        t = misata.generate_from_schema(_coverage_schema())
        covered = set(t["items"]["order_id"])
        assert set(t["orders"]["order_id"]) <= covered

    def test_min_children_two(self):
        t = misata.generate_from_schema(_coverage_schema(min_children=2))
        counts = t["items"]["order_id"].value_counts()
        assert set(t["orders"]["order_id"]) <= set(counts.index)
        assert int(counts.min()) >= 2

    def test_default_zero_changes_nothing(self):
        # Without min_children some of 100 parents stay childless at 110 rows —
        # the old behaviour, untouched.
        schema = _coverage_schema(min_children=0, child_rows=110)
        t = misata.generate_from_schema(schema)
        assert len(set(t["orders"]["order_id"]) - set(t["items"]["order_id"])) > 0

    def test_impossible_coverage_is_refused_up_front(self):
        """Since 0.8.9.5 this is a feasibility conflict, not a runtime warning:
        100 parents x 3 children needs 300 rows and only 120 exist, which is
        arithmetic the engine can check before generating anything."""
        from misata.feasibility import InfeasibleSchema
        with pytest.raises(InfeasibleSchema, match="300"):
            misata.generate_from_schema(
                _coverage_schema(min_children=3, child_rows=120))

    def test_runtime_warning_still_guards_the_unpredictable_case(self):
        """Feasibility cannot see every shortfall (filters can shrink the
        eligible parent pool at generation time), so the runtime warning in
        _ensure_min_children remains the backstop. Reached via strict=False."""
        with pytest.warns(UserWarning, match="min_children"):
            misata.generate_from_schema(
                _coverage_schema(min_children=3, child_rows=120), strict=False)

    def test_fk_integrity_survives(self):
        t = misata.generate_from_schema(_coverage_schema(min_children=2))
        assert t["items"]["order_id"].isin(set(t["orders"]["order_id"])).all()


# --------------------------------------------------------------------------- #
# relationship list filters
# --------------------------------------------------------------------------- #

def _filtered_schema(seed=17):
    return SchemaConfig(
        name="gated",
        tables=[Table(name="orders", row_count=200),
                Table(name="shipments", row_count=120)],
        columns={
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 200}),
                Column(name="status", type="categorical",
                       distribution_params={"choices": ["placed", "shipped",
                                                        "completed", "cancelled"]}),
            ],
            "shipments": [
                Column(name="shipment_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 120}),
                Column(name="order_id", type="foreign_key",
                       distribution_params={"references": "orders.order_id"}),
            ],
        },
        relationships=[
            Relationship(parent_table="orders", child_table="shipments",
                         parent_key="order_id", child_key="order_id",
                         filters={"status": ["shipped", "completed"]}),
        ],
        seed=seed,
    )


class TestRelationshipListFilters:
    def test_children_only_reference_allowed_parents(self):
        t = misata.generate_from_schema(_filtered_schema())
        merged = t["shipments"].merge(
            t["orders"][["order_id", "status"]], on="order_id")
        assert merged["status"].isin(["shipped", "completed"]).all()

    def test_scalar_filter_still_works(self):
        schema = _filtered_schema()
        schema.relationships[0].filters = {"status": "shipped"}
        t = misata.generate_from_schema(schema)
        merged = t["shipments"].merge(
            t["orders"][["order_id", "status"]], on="order_id")
        assert (merged["status"] == "shipped").all()
