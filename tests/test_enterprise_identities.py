"""Epoch 2 items 10-12: multi-tenant waterfalls, SCD2 histories, stock-flow
ledgers, and their round-trips.

Each identity is tested two-sided: honest generation satisfies it exactly and
audits clean; planted sabotage is caught by the matching detector, and for
segmented identities only the sabotaged segment is flagged.
"""

import numpy as np
import pandas as pd
import pytest

import misata
from misata.schema import (Column, SCD2Config, SchemaConfig,
                           StockFlowIdentity, Table, WaterfallIdentity)
from misata.yaml_schema import load_yaml_schema, save_yaml_schema

PERIODS = [f"2025-{m:02d}" for m in range(1, 7)]
INFLOWS = {"new", "expansion"}


def _movement_cols(with_tenant=False):
    cols = [
        Column(name="movement_id", type="int", unique=True,
               distribution_params={"min": 1, "max": 999999}),
        Column(name="period", type="text"),
        Column(name="movement_type", type="text"),
        Column(name="amount", type="float"),
    ]
    if with_tenant:
        cols.insert(1, Column(name="tenant", type="text"))
    return cols


TENANTS = {"acme": (50000.0, 3000.0), "globex": (120000.0, -1500.0),
           "initech": (20000.0, 800.0)}


def _tenant_schema(seed=42):
    def spec(name, start, step):
        return WaterfallIdentity(
            table="mrr_movements", starting_value=start,
            segment_column="tenant", segment_value=name,
            points=[{"period": p, "ending_value": start + (i + 1) * step}
                    for i, p in enumerate(PERIODS)])
    return SchemaConfig(
        name="tenants", seed=seed,
        tables=[Table(name="mrr_movements", row_count=4000)],
        columns={"mrr_movements": _movement_cols(with_tenant=True)},
        relationships=[],
        waterfalls=[spec(k, s, d) for k, (s, d) in TENANTS.items()],
    )


def _running(sub, start):
    signed = sub["amount"].where(sub["movement_type"].isin(INFLOWS),
                                 -sub["amount"])
    run = start
    out = []
    for p in PERIODS:
        run = round(run + round(float(signed[sub["period"] == p].sum()), 2), 2)
        out.append(run)
    return out


class TestMultiTenantWaterfalls:
    @pytest.fixture(scope="class")
    def generated(self):
        schema = _tenant_schema()
        return schema, misata.generate_from_schema(schema)

    def test_every_tenant_reconciles_independently(self, generated):
        _, tables = generated
        df = tables["mrr_movements"]
        assert set(df["tenant"]) == set(TENANTS)
        for name, (start, step) in TENANTS.items():
            balances = _running(df[df["tenant"] == name], start)
            for i, got in enumerate(balances):
                assert abs(got - (start + (i + 1) * step)) < 0.005, (name, i)

    def test_audit_isolates_the_sabotaged_tenant(self, generated):
        schema, tables = generated
        assert misata.story_audit(tables, schema).clean
        sab = {k: v.copy() for k, v in tables.items()}
        d = sab["mrr_movements"]
        i = d[(d["tenant"] == "acme") & (d["movement_type"] == "new")].index[0]
        d.loc[i, "amount"] = float(d.loc[i, "amount"]) + 7000.0
        findings = [f for f in misata.story_audit(sab, schema).findings
                    if f.kind == "waterfall_mismatch"]
        assert len(findings) == 1

    def test_ambiguous_segments_skip_with_warning(self):
        schema = _tenant_schema()
        # Two specs share a segment value: ambiguous, must skip all.
        schema.waterfalls[1].segment_value = "acme"
        with pytest.warns(UserWarning, match="ambiguous"):
            misata.generate_from_schema(schema)

    def test_lint_catches_duplicate_segment_values(self):
        from misata.lint import lint_schema
        schema = _tenant_schema()
        schema.waterfalls[1].segment_value = "acme"
        f = [x for x in lint_schema(schema) if "distinct" in x.message]
        assert f and f[0].severity == "error"

    def test_evalpack_questions_are_segment_scoped(self):
        from misata.evalpack import _waterfall_questions
        schema = _tenant_schema()
        counter = iter(range(10000))
        qs = _waterfall_questions(schema, lambda: f"q{next(counter)}")
        assert qs
        assert all("tenant" in q.gold_sql for q in qs)


def _scd2_schema(seed=42, avg_versions=3.0):
    cols = [
        Column(name="customer_id", type="int", unique=True,
               distribution_params={"min": 1, "max": 99999}),
        Column(name="plan", type="categorical",
               distribution_params={"choices": ["free", "pro", "ent"]}),
        Column(name="valid_from", type="datetime",
               distribution_params={"start": "2022-01-01",
                                    "end": "2025-06-30"}),
        Column(name="valid_to", type="datetime",
               distribution_params={"start": "2022-01-01",
                                    "end": "2025-06-30"}),
        Column(name="is_current", type="boolean"),
    ]
    return SchemaConfig(
        name="scd2", seed=seed,
        tables=[Table(name="dim_customer", row_count=1500,
                      scd2=SCD2Config(entity_column="customer_id",
                                      current_flag="is_current",
                                      avg_versions=avg_versions))],
        columns={"dim_customer": cols}, relationships=[],
    )


class TestSCD2:
    @pytest.fixture(scope="class")
    def generated(self):
        schema = _scd2_schema()
        return schema, misata.generate_from_schema(schema)

    def test_versions_tile_without_gaps_or_overlaps(self, generated):
        _, tables = generated
        df = tables["dim_customer"].copy()
        df["valid_from"] = pd.to_datetime(df["valid_from"])
        df["valid_to"] = pd.to_datetime(df["valid_to"])
        for _e, g in df.sort_values(["customer_id", "valid_from"]).groupby(
                "customer_id"):
            vf, vt = g["valid_from"].values, g["valid_to"].values
            for i in range(len(g) - 1):
                assert not pd.isna(vt[i])
                assert abs((pd.Timestamp(vt[i]) - pd.Timestamp(vf[i + 1]))
                           .total_seconds()) <= 1

    def test_exactly_one_current_open_ended_version(self, generated):
        _, tables = generated
        df = tables["dim_customer"]
        per = df.groupby("customer_id")["is_current"].sum()
        assert (per == 1).all()
        assert pd.to_datetime(df[df["is_current"]]["valid_to"]).isna().all()

    def test_attributes_vary_across_versions(self, generated):
        _, tables = generated
        df = tables["dim_customer"]
        multi = df.groupby("customer_id").filter(lambda g: len(g) > 2)
        vary = multi.groupby("customer_id")["plan"].nunique().gt(1).mean()
        assert vary > 0.5

    def test_audit_two_sided(self, generated):
        schema, tables = generated
        assert not [f for f in misata.story_audit(tables, schema).findings
                    if f.kind.startswith("scd2")]
        sab = {k: v.copy() for k, v in tables.items()}
        d = sab["dim_customer"]
        victim = d.groupby("customer_id").filter(
            lambda g: len(g) >= 3)["customer_id"].iloc[0]
        rows = d[d["customer_id"] == victim].sort_values("valid_from")
        d.loc[rows.index[0], "valid_to"] = pd.Timestamp("2099-01-01")
        d.loc[rows.index[1], "is_current"] = True
        kinds = {f.kind for f in misata.story_audit(sab, schema).findings}
        assert "scd2_tiling" in kinds and "scd2_current_flag" in kinds

    def test_yaml_round_trip(self, tmp_path):
        schema = _scd2_schema()
        path = tmp_path / "s.yaml"
        save_yaml_schema(schema, path)
        loaded = load_yaml_schema(path)
        t = loaded.get_table("dim_customer")
        assert t.scd2 is not None and t.scd2.entity_column == "customer_id"
        a = misata.generate_from_schema(schema)
        b = misata.generate_from_schema(loaded)
        pd.testing.assert_frame_equal(a["dim_customer"], b["dim_customer"])


def _stock_schema(rows=1200, seed=42):
    cols = [
        Column(name="row_id", type="int", unique=True,
               distribution_params={"min": 1, "max": 999999}),
        Column(name="sku", type="text",
               distribution_params={"text_type": "uuid"}),
        Column(name="period", type="text"),
        Column(name="opening_stock", type="int"),
        Column(name="received", type="int"),
        Column(name="shipped", type="int"),
        Column(name="closing_stock", type="int"),
    ]
    return SchemaConfig(
        name="stock", seed=seed,
        tables=[Table(name="stock_levels", row_count=rows)],
        columns={"stock_levels": cols}, relationships=[],
        stock_flows=[StockFlowIdentity(table="stock_levels",
                                       periods=PERIODS)],
    )


class TestStockFlow:
    @pytest.fixture(scope="class")
    def generated(self):
        schema = _stock_schema()
        return schema, misata.generate_from_schema(schema)

    def test_row_identity_holds_everywhere(self, generated):
        _, tables = generated
        df = tables["stock_levels"]
        assert (df["closing_stock"]
                == df["opening_stock"] + df["received"] - df["shipped"]).all()

    def test_chain_and_non_negativity(self, generated):
        _, tables = generated
        df = tables["stock_levels"]
        order = {p: i for i, p in enumerate(PERIODS)}
        w = df.copy()
        w["o"] = w["period"].map(order)
        w = w.sort_values(["sku", "o"])
        same = w["sku"].eq(w["sku"].shift(-1))
        assert ((w["closing_stock"] - w["opening_stock"].shift(-1))
                .abs()[same] < 0.001).all()
        assert (df[["opening_stock", "received", "shipped",
                    "closing_stock"]] >= 0).all().all()

    def test_partial_history_keeps_the_chain(self):
        # 1203 rows over 6 periods: 200 full SKUs + one 3-period SKU.
        schema = _stock_schema(rows=1203)
        df = misata.generate_from_schema(schema)["stock_levels"]
        counts = df.groupby("sku").size()
        assert sorted(counts.unique()) == [3, 6]
        assert (df["closing_stock"]
                == df["opening_stock"] + df["received"] - df["shipped"]).all()

    def test_audit_two_sided(self, generated):
        schema, tables = generated
        assert not [f for f in misata.story_audit(tables, schema).findings
                    if f.kind.startswith("stock_flow")]
        sab = {k: v.copy() for k, v in tables.items()}
        sab["stock_levels"].loc[sab["stock_levels"].index[3],
                                "closing_stock"] += 40
        kinds = {f.kind for f in misata.story_audit(sab, schema).findings}
        assert "stock_flow_arithmetic" in kinds

    def test_dict_envelope_parses(self):
        schema = misata.from_dict_schema({
            "name": "env", "tables": {
                "stock_levels": {"columns": {
                    "row_id": {"type": "integer", "primary_key": True},
                    "sku": {"type": "uuid"},
                    "period": {"type": "string"},
                    "opening_stock": {"type": "integer"},
                    "received": {"type": "integer"},
                    "shipped": {"type": "integer"},
                    "closing_stock": {"type": "integer"},
                }}},
            "stock_flows": [{"table": "stock_levels", "periods": PERIODS}],
        }, row_count=600, seed=3)
        assert len(schema.stock_flows) == 1


class TestProvenanceCLI:
    def test_provenance_prints_statement_and_manifest(self, tmp_path):
        import subprocess, sys
        (tmp_path / "t.csv").write_text("a,b\n1,2\n3,4\n")
        r = subprocess.run(
            [sys.executable, "-m", "misata.cli", "provenance", str(tmp_path)],
            capture_output=True, text=True)
        assert r.returncode == 0
        flat = " ".join(r.stdout.split())
        assert "No real data" in flat and "t.csv" in flat and "2" in flat
