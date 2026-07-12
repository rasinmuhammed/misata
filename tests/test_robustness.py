"""Degenerate-input robustness and the self-audit property.

Two quality contracts. First: the schemas users actually write when tired
(zero rows, a single day, min == max, a self-referential FK, 120 columns)
must generate, not crash. Second, the capstone property: whatever schema is
thrown at the generator, the output passes the library's own story audit,
because a generator that fails its own coherence check has shipped a defect
by definition.
"""

import pandas as pd
import pytest

import misata
from misata.schema import Column, Relationship, SchemaConfig, Table


def _gen(schema):
    return misata.generate_from_schema(schema)


class TestDegenerateSchemas:
    def test_zero_row_table(self):
        t = _gen(SchemaConfig(name="z", seed=1, tables=[Table(name="t", row_count=0)],
                 columns={"t": [Column(name="id", type="int", unique=True,
                                       distribution_params={"min": 1, "max": 99})]}))
        assert len(t["t"]) == 0

    def test_single_row_table(self):
        t = _gen(SchemaConfig(name="o", seed=1, tables=[Table(name="t", row_count=1)],
                 columns={"t": [
                     Column(name="id", type="int", unique=True,
                            distribution_params={"min": 1, "max": 99}),
                     Column(name="amount", type="float",
                            distribution_params={"min": 1, "max": 10}),
                     Column(name="created_at", type="datetime",
                            distribution_params={"start": "2025-01-01",
                                                 "end": "2025-12-31"})]}))
        assert len(t["t"]) == 1

    def test_single_day_datetime_range(self):
        """start == end means 'within that day', not a crash."""
        t = _gen(SchemaConfig(name="od", seed=1, tables=[Table(name="t", row_count=50)],
                 columns={"t": [
                     Column(name="id", type="int", unique=True,
                            distribution_params={"min": 1, "max": 999}),
                     Column(name="order_date", type="datetime",
                            distribution_params={"start": "2025-06-15",
                                                 "end": "2025-06-15"})]}))
        d = pd.to_datetime(t["t"]["order_date"])
        assert (d.dt.date == pd.Timestamp("2025-06-15").date()).all()

    def test_reversed_datetime_range_swaps_with_warning(self):
        with pytest.warns(UserWarning, match="swapping"):
            t = _gen(SchemaConfig(name="rv", seed=1,
                     tables=[Table(name="t", row_count=20)],
                     columns={"t": [
                         Column(name="id", type="int", unique=True,
                                distribution_params={"min": 1, "max": 999}),
                         Column(name="event_at", type="datetime",
                                distribution_params={"start": "2025-12-31",
                                                     "end": "2025-01-01"})]}))
        assert len(t["t"]) == 20

    def test_min_equals_max(self):
        t = _gen(SchemaConfig(name="mm", seed=1, tables=[Table(name="t", row_count=50)],
                 columns={"t": [
                     Column(name="id", type="int", unique=True,
                            distribution_params={"min": 1, "max": 999}),
                     Column(name="price", type="float",
                            distribution_params={"min": 10, "max": 10})]}))
        assert (t["t"]["price"] == 10).all()

    def test_child_of_empty_parent(self):
        t = _gen(SchemaConfig(name="ep", seed=1,
                 tables=[Table(name="p", row_count=0), Table(name="c", row_count=50)],
                 columns={"p": [Column(name="p_id", type="int", unique=True,
                                       distribution_params={"min": 1, "max": 99})],
                          "c": [Column(name="c_id", type="int", unique=True,
                                       distribution_params={"min": 1, "max": 999}),
                                Column(name="p_id", type="foreign_key")]},
                 relationships=[Relationship(parent_table="p", child_table="c",
                                             parent_key="p_id", child_key="p_id")]))
        assert len(t["c"]) == 50

    def test_wide_table_120_columns(self):
        cols = [Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 9999})]
        cols += [Column(name=f"metric_{i}", type="float",
                        distribution_params={"min": 0, "max": 100})
                 for i in range(119)]
        t = _gen(SchemaConfig(name="w", seed=1, tables=[Table(name="t", row_count=20)],
                              columns={"t": cols}))
        assert t["t"].shape == (20, 120)


class TestSelfAuditProperty:
    """Generation must pass its own audit across structurally varied schemas.

    Not hypothesis-random (schema construction is too structured for cheap
    strategies to stay valid), but a parametrized sweep over the shapes that
    exercise every coherence layer at once.
    """

    @pytest.mark.parametrize("seed", [1, 7, 42, 1234, 99999])
    def test_full_story_audits_clean_across_seeds(self, seed):
        schema = SchemaConfig(
            name="prop", seed=seed,
            tables=[Table(name="customers", row_count=80),
                    Table(name="products", row_count=30),
                    Table(name="orders", row_count=250),
                    Table(name="order_items", row_count=600)],
            columns={
                "customers": [
                    Column(name="customer_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 99999}),
                    Column(name="email", type="text"),
                    Column(name="country", type="text"),
                    Column(name="city", type="text"),
                    Column(name="signup_date", type="datetime",
                           distribution_params={"start": "2022-01-01",
                                                "end": "2024-12-31"})],
                "products": [
                    Column(name="product_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 9999}),
                    Column(name="unit_price", type="float",
                           distribution_params={"min": 5, "max": 500,
                                                "decimals": 2})],
                "orders": [
                    Column(name="order_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 999999}),
                    Column(name="customer_id", type="foreign_key"),
                    Column(name="status", type="categorical",
                           distribution_params={"choices": ["pending", "shipped",
                                                            "delivered",
                                                            "cancelled"]}),
                    Column(name="order_date", type="datetime",
                           distribution_params={"start": "2022-01-01",
                                                "end": "2025-06-30"}),
                    Column(name="order_total", type="float",
                           distribution_params={"min": 5, "max": 5000,
                                                "decimals": 2})],
                "order_items": [
                    Column(name="item_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 9999999}),
                    Column(name="order_id", type="foreign_key"),
                    Column(name="product_id", type="foreign_key"),
                    Column(name="quantity", type="int",
                           distribution_params={"min": 1, "max": 5}),
                    Column(name="unit_price", type="float",
                           distribution_params={"min": 5, "max": 500,
                                                "decimals": 2}),
                    Column(name="line_total", type="float",
                           distribution_params={"min": 5, "max": 2500,
                                                "decimals": 2})],
            },
            relationships=[
                Relationship(parent_table="customers", child_table="orders",
                             parent_key="customer_id", child_key="customer_id"),
                Relationship(parent_table="orders", child_table="order_items",
                             parent_key="order_id", child_key="order_id"),
                Relationship(parent_table="products", child_table="order_items",
                             parent_key="product_id", child_key="product_id")],
        )
        tables = misata.generate_from_schema(schema)
        report = misata.story_audit(tables, schema)
        assert report.clean, f"seed {seed}: {report.summary()}"
