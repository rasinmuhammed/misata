"""Tests for temporal foreign-key eligibility (0.9.1).

The contract: a child row may only reference a parent that already existed at
the child's own moment. An order line cannot contain a product invented after
the order was placed, which every generator gets wrong by construction because
a foreign key is drawn from the whole parent table without asking when the
parent was born.

This was the Gauntlet's last known-red. The tests below are the small,
readable version of the assertion that closed it.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata.coherence import coherence_audit
from misata.feasibility import InfeasibleSchema, find_conflicts
from misata.schema import SchemaConfig, Table, Column, Relationship

warnings.filterwarnings("ignore")


def _direct_schema(**over):
    """products → orders, where the order carries its own date."""
    kwargs = dict(
        name="direct",
        seed=11,
        tables=[
            Table(name="products", row_count=40),
            Table(name="orders", row_count=600),
        ],
        columns={
            "products": [
                Column(name="product_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 40}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2023-01-01",
                                            "end": "2023-12-31"}),
            ],
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 600}),
                Column(name="order_date", type="datetime",
                       distribution_params={"start": "2023-06-01",
                                            "end": "2024-06-30"}),
                Column(name="product_id", type="foreign_key",
                       distribution_params={"references": "products.product_id"}),
            ],
        },
        relationships=[
            Relationship(parent_table="products", child_table="orders",
                         parent_key="product_id", child_key="product_id",
                         parent_time="created_at", child_time="order_date"),
        ],
    )
    kwargs.update(over)
    return SchemaConfig(**kwargs)


def _violations(tables, parent="products", child="orders",
                ptime="created_at", ctime="order_date", key="product_id"):
    births = tables[parent].set_index(key)[ptime]
    births = births[~births.index.duplicated(keep="first")]
    mapped = pd.to_datetime(tables[child][key].map(births))
    return int((pd.to_datetime(tables[child][ctime]) < mapped).sum())


class TestDirectEligibility:

    def test_no_row_references_an_unborn_parent(self):
        tables = misata.generate_from_schema(_direct_schema())
        assert _violations(tables) == 0

    def test_direct_case_was_already_covered_without_the_declaration(self):
        """Measured, not assumed: the one-hop case never needed this.

        When the child carries its own date, the cross-table causality pass
        already shifts that date to postdate the parent, so declaring
        eligibility here changes nothing. Recorded as a test because the
        interesting claim is the narrow one below it, and overstating what a
        feature added is how a benchmark stops meaning anything.
        """
        cfg = _direct_schema()
        cfg.relationships[0].parent_time = None
        cfg.relationships[0].child_time = None
        assert _violations(misata.generate_from_schema(cfg)) == 0

    def test_every_key_still_resolves(self):
        """Eligibility must not cost referential integrity."""
        tables = misata.generate_from_schema(_direct_schema())
        valid = set(tables["products"]["product_id"])
        assert set(tables["orders"]["product_id"]) <= valid
        assert tables["orders"]["product_id"].notna().all()

    def test_more_than_one_parent_is_used(self):
        """A trivial 'always pick the oldest parent' would also pass above."""
        tables = misata.generate_from_schema(_direct_schema())
        assert tables["orders"]["product_id"].nunique() > 5

    def test_deterministic_under_the_same_seed(self):
        a = misata.generate_from_schema(_direct_schema())
        b = misata.generate_from_schema(_direct_schema())
        pd.testing.assert_series_equal(a["orders"]["product_id"],
                                       b["orders"]["product_id"])


class TestEligibilityThroughAnotherTable:
    """The moment that matters is not always the child's own."""

    def _schema(self):
        return SchemaConfig(
            name="hop", seed=5,
            tables=[
                Table(name="products", row_count=30),
                Table(name="orders", row_count=200),
                Table(name="order_items", row_count=800),
            ],
            columns={
                "products": [
                    Column(name="product_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 30}),
                    Column(name="created_at", type="datetime",
                           distribution_params={"start": "2023-01-01",
                                                "end": "2023-12-31"}),
                ],
                "orders": [
                    Column(name="order_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 200}),
                    Column(name="order_date", type="datetime",
                           distribution_params={"start": "2023-07-01",
                                                "end": "2024-06-30"}),
                ],
                "order_items": [
                    Column(name="item_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 800}),
                    Column(name="order_id", type="foreign_key",
                           distribution_params={"references": "orders.order_id"}),
                    Column(name="product_id", type="foreign_key",
                           distribution_params={"references": "products.product_id"}),
                ],
            },
            relationships=[
                Relationship(parent_table="orders", child_table="order_items",
                             parent_key="order_id", child_key="order_id"),
                Relationship(parent_table="products", child_table="order_items",
                             parent_key="product_id", child_key="product_id",
                             parent_time="created_at", child_time="order_date",
                             child_time_table="orders"),
            ],
        )

    def test_line_never_predates_its_products_creation(self):
        tables = misata.generate_from_schema(self._schema())
        items, orders, products = (tables["order_items"], tables["orders"],
                                   tables["products"])
        when = items["order_id"].map(
            orders.set_index("order_id")["order_date"])
        born = items["product_id"].map(
            products.set_index("product_id")["created_at"])
        assert int((pd.to_datetime(when) < pd.to_datetime(born)).sum()) == 0

    def test_without_the_declaration_the_hop_is_violated(self):
        """The control that matters.

        A junction row has no date of its own, so there is nothing for the
        causality pass to shift and the product is drawn from the whole
        catalogue. This is the case the declaration exists for.
        """
        cfg = self._schema()
        cfg.relationships[1].parent_time = None
        cfg.relationships[1].child_time = None
        cfg.relationships[1].child_time_table = None
        tables = misata.generate_from_schema(cfg)
        items, orders, products = (tables["order_items"], tables["orders"],
                                   tables["products"])
        when = items["order_id"].map(
            orders.set_index("order_id")["order_date"])
        born = items["product_id"].map(
            products.set_index("product_id")["created_at"])
        assert int((pd.to_datetime(when) < pd.to_datetime(born)).sum()) > 0

    def test_min_children_does_not_reintroduce_violations(self):
        """Coverage must not manufacture the violation eligibility removed."""
        cfg = self._schema()
        cfg.relationships[0].min_children = 1
        tables = misata.generate_from_schema(cfg)
        items, orders, products = (tables["order_items"], tables["orders"],
                                   tables["products"])
        when = items["order_id"].map(
            orders.set_index("order_id")["order_date"])
        born = items["product_id"].map(
            products.set_index("product_id")["created_at"])
        assert int((pd.to_datetime(when) < pd.to_datetime(born)).sum()) == 0


class TestAudit:

    def test_audit_reports_an_injected_violation(self):
        """The verifier must catch it independently of the generator."""
        cfg = _direct_schema()
        tables = misata.generate_from_schema(cfg)
        assert not [f for f in coherence_audit(tables, schema=cfg).findings
                    if f.kind == "temporal_eligibility"]

        # Break it by hand: point every order at the youngest product.
        youngest = tables["products"].sort_values("created_at").iloc[-1]
        tables["orders"]["product_id"] = youngest["product_id"]
        findings = [f for f in coherence_audit(tables, schema=cfg).findings
                    if f.kind == "temporal_eligibility"]
        assert findings and findings[0].rows_affected > 0


class TestFeasibility:

    def test_disjoint_windows_are_refused_with_arithmetic(self):
        cfg = _direct_schema()
        cfg.columns["products"][1].distribution_params = {
            "start": "2025-01-01", "end": "2025-12-31"}
        cfg.columns["orders"][1].distribution_params = {
            "start": "2023-01-01", "end": "2023-12-31"}
        conflicts = [c for c in find_conflicts(cfg)
                     if c.kind == "temporal_eligibility_impossible"]
        assert len(conflicts) == 1
        assert "2025-01-01" in conflicts[0].arithmetic
        assert "2023-12-31" in conflicts[0].arithmetic

        with pytest.raises(InfeasibleSchema):
            misata.generate_from_schema(cfg)

    def test_overlapping_windows_are_not_refused(self):
        """False refusals are worse than the warnings they replace."""
        assert not [c for c in find_conflicts(_direct_schema())
                    if c.kind == "temporal_eligibility_impossible"]

    def test_partial_overlap_warns_rather_than_refusing(self):
        """Some rows orphaned in time is still a mostly-satisfiable schema."""
        cfg = _direct_schema()
        cfg.columns["products"][1].distribution_params = {
            "start": "2023-09-01", "end": "2023-12-31"}
        cfg.columns["orders"][1].distribution_params = {
            "start": "2023-01-01", "end": "2023-12-31"}
        assert not [c for c in find_conflicts(cfg)
                    if c.kind == "temporal_eligibility_impossible"]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            misata.generate_from_schema(cfg)
        assert any("Temporal eligibility" in str(w.message) for w in caught)
