"""Epoch 2 item 8: anchored RNG streams (edit-stable regeneration).

The contract of ``generation_mode: "anchored"``: every generation site draws
from a stream derived from its own stable name, so a schema edit changes
only what it touches. Adding a column leaves every other column
byte-identical; adding a table leaves every other table byte-identical;
editing one column re-rolls only that column plus its true dependents.
Edits flow DOWN the dependency graph (a parent's key pool feeds its
children), never sideways.
"""

import warnings

import pandas as pd
import pytest

import misata
from misata.schema import (Column, GroupShares, OutcomeCurve, Relationship,
                           SchemaConfig, Table, WaterfallIdentity)


def _base(extra_col=False, extra_table=False, tweak_age=False,
          mode="anchored", seed=42):
    cols_u = [
        Column(name="user_id", type="int", unique=True,
               distribution_params={"min": 1, "max": 99999}),
        Column(name="email", type="text",
               distribution_params={"text_type": "email"}),
        Column(name="age", type="int",
               distribution_params=({"min": 21, "max": 70} if tweak_age
                                    else {"min": 18, "max": 80})),
        Column(name="signup_date", type="datetime",
               distribution_params={"start": "2024-01-01",
                                    "end": "2025-05-31"}),
    ]
    if extra_col:
        cols_u.insert(2, Column(name="nickname", type="text",
                                distribution_params={"text_type": "username"}))
    cols_o = [
        Column(name="order_id", type="int", unique=True,
               distribution_params={"min": 1, "max": 999999}),
        Column(name="user_id", type="foreign_key"),
        Column(name="amount", type="float",
               distribution_params={"min": 5, "max": 500, "decimals": 2}),
        Column(name="order_date", type="datetime",
               distribution_params={"start": "2025-01-01",
                                    "end": "2025-06-30"}),
    ]
    tables = [Table(name="users", row_count=500),
              Table(name="orders", row_count=3000)]
    columns = {"users": cols_u, "orders": cols_o}
    if extra_table:
        tables.append(Table(name="tickets", row_count=400))
        columns["tickets"] = [
            Column(name="ticket_id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 99999}),
            Column(name="subject", type="text"),
        ]
    return SchemaConfig(
        name="anchored", seed=seed, generation_mode=mode,
        tables=tables, columns=columns,
        relationships=[Relationship(parent_table="users",
                                    child_table="orders",
                                    parent_key="user_id",
                                    child_key="user_id")],
    )


class TestEditStability:
    @pytest.fixture(scope="class")
    def base(self):
        return misata.generate_from_schema(_base())

    def test_adding_a_column_leaves_every_other_column_identical(self, base):
        plus = misata.generate_from_schema(_base(extra_col=True))
        for t in ("users", "orders"):
            for c in base[t].columns:
                pd.testing.assert_series_equal(base[t][c], plus[t][c])

    def test_adding_a_table_leaves_existing_tables_identical(self, base):
        plus = misata.generate_from_schema(_base(extra_table=True))
        for t in ("users", "orders"):
            pd.testing.assert_frame_equal(base[t], plus[t])

    def test_editing_one_column_changes_only_that_column(self, base):
        tweaked = misata.generate_from_schema(_base(tweak_age=True))
        assert not base["users"]["age"].equals(tweaked["users"]["age"])
        for c in ("user_id", "email", "signup_date"):
            pd.testing.assert_series_equal(base["users"][c],
                                           tweaked["users"][c])
        pd.testing.assert_frame_equal(base["orders"], tweaked["orders"])

    def test_anchored_is_reproducible(self, base):
        again = misata.generate_from_schema(_base())
        for t in base:
            pd.testing.assert_frame_equal(base[t], again[t])

    def test_seed_changes_everything(self, base):
        other = misata.generate_from_schema(_base(seed=7))
        assert not base["users"]["email"].equals(other["users"]["email"])

    def test_legacy_stays_default_and_deterministic(self):
        assert SchemaConfig.model_fields["generation_mode"].default == "legacy"
        a = misata.generate_from_schema(_base(mode="legacy"))
        b = misata.generate_from_schema(_base(mode="legacy"))
        for t in a:
            pd.testing.assert_frame_equal(a[t], b[t])

    def test_modes_produce_different_bytes(self):
        a = misata.generate_from_schema(_base(mode="legacy"))
        b = misata.generate_from_schema(_base(mode="anchored"))
        assert not a["users"]["email"].equals(b["users"]["email"])


class TestAnchoredKeepsExactness:
    """Anchored mode must not cost a single declared guarantee."""

    @pytest.fixture(scope="class")
    def declared(self):
        cols_o = [
            Column(name="order_id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 999999}),
            Column(name="order_date", type="datetime",
                   distribution_params={"start": "2025-01-01",
                                        "end": "2025-06-30"}),
            Column(name="category", type="categorical",
                   distribution_params={"choices": ["A", "B", "C"]}),
            Column(name="revenue", type="float",
                   distribution_params={"min": 5, "max": 500, "decimals": 2}),
        ]
        cols_m = [
            Column(name="movement_id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 999999}),
            Column(name="period", type="text"),
            Column(name="movement_type", type="text"),
            Column(name="amount", type="float"),
        ]
        schema = SchemaConfig(
            name="exact", seed=42, generation_mode="anchored",
            tables=[Table(name="orders", row_count=2000),
                    Table(name="mrr_movements", row_count=900)],
            columns={"orders": cols_o, "mrr_movements": cols_m},
            relationships=[],
            outcome_curves=[OutcomeCurve(
                table="orders", column="revenue", time_column="order_date",
                time_unit="month", value_mode="absolute",
                curve_points=[{"date": f"2025-{m:02d}-01",
                               "target_value": 40000.0 + m * 1000}
                              for m in range(1, 7)])],
            group_shares=[GroupShares(table="orders", measure="revenue",
                                      group_column="category",
                                      shares={"A": 0.5, "B": 0.3, "C": 0.2})],
            waterfalls=[WaterfallIdentity(
                table="mrr_movements", starting_value=80000.0,
                points=[{"period": f"2025-{m:02d}",
                         "ending_value": 80000.0 + m * 4000}
                        for m in range(1, 7)])],
        )
        return schema, misata.generate_from_schema(schema)

    def test_curves_and_shares_exact(self, declared):
        from misata.shares import split_total_by_shares
        _, tables = declared
        df = tables["orders"].copy()
        df["order_date"] = pd.to_datetime(df["order_date"])
        for m in range(1, 7):
            target = 40000.0 + m * 1000
            month = df[df["order_date"].dt.month == m]
            assert abs(round(float(month["revenue"].sum()), 2) - target) < 0.005
            exp = split_total_by_shares({"A": 0.5, "B": 0.3, "C": 0.2}, target)
            got = month.groupby("category")["revenue"].sum().round(2)
            for k, v in exp.items():
                assert abs(float(got.get(k, 0)) - v) < 0.005

    def test_waterfall_reconciles(self, declared):
        _, tables = declared
        mv = tables["mrr_movements"]
        signed = mv["amount"].where(
            mv["movement_type"].isin({"new", "expansion"}), -mv["amount"])
        run = 80000.0
        for m in range(1, 7):
            run = round(run + round(float(
                signed[mv["period"] == f"2025-{m:02d}"].sum()), 2), 2)
            assert abs(run - (80000.0 + m * 4000)) < 0.005

    def test_audit_clean(self, declared):
        schema, tables = declared
        assert misata.story_audit(tables, schema).clean


class TestFactTableCausality:
    """Fact tables (exact curves) now get the cross-table causality fix, and
    the declared aggregate outranks it when the two conflict."""

    def test_fact_children_postdate_parents_and_sums_hold(self):
        cols_c = [
            Column(name="customer_id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 99999}),
            Column(name="signup_date", type="datetime",
                   distribution_params={"start": "2024-01-01",
                                        "end": "2024-12-31"})]
        cols_o = [
            Column(name="order_id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 999999}),
            Column(name="customer_id", type="foreign_key"),
            Column(name="order_date", type="datetime",
                   distribution_params={"start": "2025-01-01",
                                        "end": "2025-06-30"}),
            Column(name="revenue", type="float",
                   distribution_params={"min": 5, "max": 500, "decimals": 2}),
        ]
        schema = SchemaConfig(
            name="factcause", seed=42,
            tables=[Table(name="customers", row_count=200),
                    Table(name="orders", row_count=2000)],
            columns={"customers": cols_c, "orders": cols_o},
            relationships=[Relationship(parent_table="customers",
                                        child_table="orders",
                                        parent_key="customer_id",
                                        child_key="customer_id")],
            outcome_curves=[OutcomeCurve(
                table="orders", column="revenue", time_column="order_date",
                time_unit="month", value_mode="absolute",
                curve_points=[{"date": f"2025-{m:02d}-01",
                               "target_value": 30000.0}
                              for m in range(1, 7)])],
        )
        tables = misata.generate_from_schema(schema)
        m = tables["orders"].merge(tables["customers"], on="customer_id")
        assert (pd.to_datetime(m["order_date"])
                > pd.to_datetime(m["signup_date"])).all()
        df = tables["orders"].copy()
        df["order_date"] = pd.to_datetime(df["order_date"])
        for mo in range(1, 7):
            got = round(float(
                df[df["order_date"].dt.month == mo]["revenue"].sum()), 2)
            assert abs(got - 30000.0) < 0.005


class TestModeRoundTrip:
    def test_yaml_round_trip_preserves_mode(self, tmp_path):
        from misata.yaml_schema import load_yaml_schema, save_yaml_schema
        schema = _base()
        path = tmp_path / "s.yaml"
        save_yaml_schema(schema, path)
        assert load_yaml_schema(path).generation_mode == "anchored"

    def test_dict_forms_accept_mode(self):
        flat = misata.from_dict_schema(
            {"t": {"id": {"type": "integer", "primary_key": True}},
             "generation_mode": "anchored"}, row_count=10)
        assert flat.generation_mode == "anchored"
        env = misata.from_dict_schema(
            {"name": "x", "generation_mode": "anchored",
             "tables": {"t": {"columns": {"id": {"type": "integer"}}}}},
            row_count=10)
        assert env.generation_mode == "anchored"
