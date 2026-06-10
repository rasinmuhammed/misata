"""Tests for cross-table aggregate roll-ups (misata/rollups.py).

A roll-up makes a parent summary column reconcile with child rows: customers.total_spent
must equal sum(orders.amount) per customer. These tests verify exact reconciliation for
explicit declarations, conservative inference (no false positives), and that FK integrity
and aggregate exactness are untouched by the roll-up pass.
"""

import warnings

import pandas as pd
import pytest

import misata
from misata.schema import SchemaConfig, Table, Column, Relationship
from misata.rollups import infer_rollups, collect_declared_rollups

warnings.filterwarnings("ignore")


def _shop_schema(with_rollups=True, seed=1):
    rollup_spent = {"rollup": {"from_table": "orders", "fk": "customer_id",
                               "agg": "sum", "column": "amount"}} if with_rollups else {}
    rollup_count = {"rollup": {"from_table": "orders", "fk": "customer_id",
                               "agg": "count"}} if with_rollups else {}
    return SchemaConfig(
        name="shop",
        tables=[Table(name="customers", row_count=200), Table(name="orders", row_count=1000)],
        columns={
            "customers": [
                Column(name="customer_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 200}),
                Column(name="total_spent", type="float", distribution_params=rollup_spent),
                Column(name="order_count", type="int", distribution_params=rollup_count),
            ],
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 1000}),
                Column(name="customer_id", type="foreign_key",
                       distribution_params={"references": "customers.customer_id"}),
                Column(name="amount", type="float",
                       distribution_params={"distribution": "lognormal", "mu": 4, "sigma": 0.5, "min": 1}),
            ],
        },
        relationships=[Relationship(parent_table="customers", child_table="orders",
                                    parent_key="customer_id", child_key="customer_id")],
        seed=seed,
    )


class TestExplicitRollups:
    def test_sum_rollup_reconciles_exactly(self):
        tables = misata.generate_from_schema(_shop_schema())
        cust, orders = tables["customers"], tables["orders"]
        real = orders.groupby("customer_id")["amount"].sum()
        merged = cust.set_index("customer_id")
        err = (merged["total_spent"] - real.reindex(merged.index).fillna(0)).abs().max()
        assert err < 1e-6

    def test_count_rollup_reconciles_exactly(self):
        tables = misata.generate_from_schema(_shop_schema())
        cust, orders = tables["customers"], tables["orders"]
        real = orders.groupby("customer_id").size()
        merged = cust.set_index("customer_id")
        err = (merged["order_count"] - real.reindex(merged.index).fillna(0)).abs().max()
        assert err == 0

    def test_childless_parent_gets_zero(self):
        # 200 customers, 1000 orders: some customers may have no orders -> total_spent 0
        tables = misata.generate_from_schema(_shop_schema())
        cust, orders = tables["customers"], tables["orders"]
        have_orders = set(orders["customer_id"])
        childless = cust[~cust["customer_id"].isin(have_orders)]
        if len(childless):
            assert (childless["total_spent"] == 0).all()
            assert (childless["order_count"] == 0).all()

    def test_rollup_does_not_break_fk_integrity(self):
        tables = misata.generate_from_schema(_shop_schema())
        valid = set(tables["customers"]["customer_id"])
        assert tables["orders"]["customer_id"].isin(valid).all()

    def test_count_rollup_is_integer(self):
        tables = misata.generate_from_schema(_shop_schema())
        assert pd.api.types.is_integer_dtype(tables["customers"]["order_count"])


class TestInferenceIsConservative:
    """Inference must fire on table-naming nouns and decline on ambiguous names."""

    def test_no_false_positive_on_builtin_domains(self):
        # marketplace.total_sales, products.stock_count etc. must NOT be inferred as roll-ups
        for story in ["A marketplace with 500 sellers and 2000 buyers",
                      "An ecommerce store with 1000 customers and orders",
                      "A SaaS company with 5k users"]:
            schema = misata.parse(story, rows=300)
            assert infer_rollups(schema) == []

    def test_fires_when_noun_names_child_table(self):
        schema = _shop_schema(with_rollups=False)
        # add columns whose names explicitly reference the 'orders' child
        schema.columns["customers"].append(
            Column(name="num_orders", type="int"))
        schema.columns["customers"].append(
            Column(name="total_orders", type="float"))
        specs = infer_rollups(schema)
        targets = {s.target_column: (s.agg, s.from_table) for s in specs}
        assert targets.get("num_orders") == ("count", "orders")
        assert targets.get("total_orders") == ("sum", "orders")

    def test_inferred_rollup_reconciles_end_to_end(self):
        schema = _shop_schema(with_rollups=False)
        schema.columns["customers"].append(Column(name="num_orders", type="int"))
        tables = misata.generate_from_schema(schema)
        real = tables["orders"].groupby("customer_id").size()
        merged = tables["customers"].set_index("customer_id")
        err = (merged["num_orders"] - real.reindex(merged.index).fillna(0)).abs().max()
        assert err == 0


class TestDeterminism:
    def test_rollups_are_deterministic(self):
        a = misata.generate_from_schema(_shop_schema(seed=7))
        b = misata.generate_from_schema(_shop_schema(seed=7))
        pd.testing.assert_series_equal(a["customers"]["total_spent"],
                                       b["customers"]["total_spent"])


class TestFilteredRollups:
    """0.8.0.2: roll-ups support a `where` equality filter on child rows."""

    def _schema(self, where, seed=1):
        return SchemaConfig(
            name="shop",
            tables=[Table(name="customers", row_count=100), Table(name="orders", row_count=600)],
            columns={
                "customers": [
                    Column(name="customer_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 100}),
                    Column(name="completed_spend", type="float", distribution_params={
                        "rollup": {"from_table": "orders", "fk": "customer_id",
                                   "agg": "sum", "column": "amount", "where": where}}),
                ],
                "orders": [
                    Column(name="order_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 600}),
                    Column(name="customer_id", type="foreign_key",
                           distribution_params={"references": "customers.customer_id"}),
                    Column(name="amount", type="float",
                           distribution_params={"distribution": "lognormal", "mu": 4, "sigma": 0.5, "min": 1}),
                    Column(name="status", type="categorical",
                           distribution_params={"choices": ["completed", "cancelled", "pending"],
                                                "probabilities": [0.6, 0.2, 0.2]}),
                ],
            },
            relationships=[Relationship(parent_table="customers", child_table="orders",
                                        parent_key="customer_id", child_key="customer_id")],
            seed=seed,
        )

    def test_scalar_filter_reconciles(self):
        t = misata.generate_from_schema(self._schema({"status": "completed"}))
        cust, orders = t["customers"], t["orders"]
        real = orders[orders["status"] == "completed"].groupby("customer_id")["amount"].sum()
        m = cust.set_index("customer_id")
        err = (m["completed_spend"] - real.reindex(m.index).fillna(0)).abs().max()
        assert err < 1e-6

    def test_list_filter_reconciles(self):
        t = misata.generate_from_schema(self._schema({"status": ["completed", "pending"]}))
        cust, orders = t["customers"], t["orders"]
        real = orders[orders["status"].isin(["completed", "pending"])].groupby("customer_id")["amount"].sum()
        m = cust.set_index("customer_id")
        err = (m["completed_spend"] - real.reindex(m.index).fillna(0)).abs().max()
        assert err < 1e-6

    def test_filtered_le_unfiltered(self):
        t = misata.generate_from_schema(self._schema({"status": "completed"}))
        cust, orders = t["customers"], t["orders"]
        total = orders.groupby("customer_id")["amount"].sum()
        m = cust.set_index("customer_id")
        # filtered spend never exceeds total spend
        assert (m["completed_spend"] <= total.reindex(m.index).fillna(0) + 1e-6).all()


class TestYamlRoundTrip:
    """0.8.0.2: rollup + zero_inflate must survive save_yaml_schema -> load_yaml_schema."""

    def test_rollup_and_zero_inflate_survive_yaml(self, tmp_path):
        schema = _shop_schema()
        schema.columns["customers"].append(
            Column(name="spend", type="float", distribution_params={
                "distribution": "lognormal", "mu": 4, "sigma": 0.5, "zero_inflate": 0.3}))
        p = str(tmp_path / "s.yaml")
        misata.save_yaml_schema(schema, p)
        loaded = misata.load_yaml_schema(p)
        rollup = next(c.distribution_params.get("rollup")
                      for c in loaded.get_columns("customers") if c.name == "total_spent")
        zi = next(c.distribution_params.get("zero_inflate")
                  for c in loaded.get_columns("customers") if c.name == "spend")
        assert rollup is not None and rollup["agg"] == "sum"
        assert zi == 0.3

    def test_loaded_schema_rollup_reconciles(self, tmp_path):
        p = str(tmp_path / "s.yaml")
        misata.save_yaml_schema(_shop_schema(), p)
        loaded = misata.load_yaml_schema(p)
        t = misata.generate_from_schema(loaded)
        real = t["orders"].groupby("customer_id")["amount"].sum()
        m = t["customers"].set_index("customer_id")
        assert (m["total_spent"] - real.reindex(m.index).fillna(0)).abs().max() < 1e-6
