"""Composed declarations v1: exact group shares.

"Electronics is 40% of revenue, Home 25%" held exactly: per declared period
when an OutcomeCurve pairs with the spec, over the table total otherwise.
The suite covers the shared arithmetic helper, the generation pass, the
interaction with curve exactness, the audit detector (both sides), the
evalpack question family with independent DuckDB verification, and the
dict-schema envelope.
"""

import json
import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata.schema import Column, GroupShares, OutcomeCurve, SchemaConfig, Table
from misata.shares import (apply_group_shares, normalized_shares,
                           split_total_by_shares)

SHARES = {"Electronics": 0.4, "Home": 0.25, "Toys": 0.2, "Grocery": 0.15}


def _schema(months=12, row_count=6000, with_curve=True, seed=42):
    cols = [
        Column(name="order_id", type="int", unique=True,
               distribution_params={"min": 1, "max": 10_000_000}),
        Column(name="order_date", type="date",
               distribution_params={"start": "2025-01-01", "end": "2025-12-31"}),
        Column(name="category", type="categorical",
               distribution_params={"choices": list(SHARES)}),
        Column(name="revenue", type="float",
               distribution_params={"min": 5, "max": 500, "decimals": 2}),
    ]
    curves = []
    if with_curve:
        curves = [OutcomeCurve(
            table="orders", column="revenue", time_column="order_date",
            time_unit="month", value_mode="absolute",
            curve_points=[{"date": f"2025-{m:02d}-01",
                           "target_value": 100000.0 + m * 5000}
                          for m in range(1, months + 1)],
        )]
    return SchemaConfig(
        name="group_shares_test",
        tables=[Table(name="orders", row_count=row_count,
                      columns=[c.name for c in cols])],
        columns={"orders": cols},
        relationships=[],
        outcome_curves=curves,
        group_shares=[GroupShares(table="orders", measure="revenue",
                                  group_column="category", shares=SHARES)],
        seed=seed,
    )


def _generate(schema):
    return misata.generate_from_schema(schema)


class TestSplitHelper:
    def test_parts_sum_to_total_exactly(self):
        for total in (100000.0, 33333.33, 0.01, 7.0, 123456.789):
            parts = split_total_by_shares(SHARES, total)
            assert round(sum(parts.values()), 2) == round(total, 2)

    def test_residual_lands_on_largest_share(self):
        # 100.00 split 3 ways at 1/3 each: two get 33.33, first (largest by
        # tie order) absorbs the extra cent.
        parts = split_total_by_shares({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}, 100.0)
        assert sorted(parts.values()) == [33.33, 33.33, 33.34]

    def test_empty_shares(self):
        assert split_total_by_shares({}, 100.0) == {}


class TestCurvePairedGeneration:
    def test_per_period_group_sums_exact(self):
        schema = _schema()
        tables = _generate(schema)
        df = tables["orders"].copy()
        df["order_date"] = pd.to_datetime(df["order_date"])
        for m in range(1, 13):
            target = 100000.0 + m * 5000
            expected = split_total_by_shares(SHARES, target)
            got = (df[df["order_date"].dt.month == m]
                   .groupby("category")["revenue"].sum().round(2))
            for label, want in expected.items():
                assert abs(float(got.get(label, 0.0)) - want) < 0.005, (
                    f"month {m}, {label}: {got.get(label)} != {want}")

    def test_curve_period_totals_survive_the_pass(self):
        schema = _schema()
        tables = _generate(schema)
        df = tables["orders"].copy()
        df["order_date"] = pd.to_datetime(df["order_date"])
        for m in range(1, 13):
            target = 100000.0 + m * 5000
            month_sum = round(float(
                df[df["order_date"].dt.month == m]["revenue"].sum()), 2)
            assert abs(month_sum - target) < 0.005

    def test_every_group_present_every_period(self):
        schema = _schema()
        tables = _generate(schema)
        df = tables["orders"].copy()
        df["order_date"] = pd.to_datetime(df["order_date"])
        for m in range(1, 13):
            cats = set(df[df["order_date"].dt.month == m]["category"])
            assert cats == set(SHARES)

    def test_reproducible_across_runs(self):
        a = _generate(_schema())["orders"]
        b = _generate(_schema())["orders"]
        pd.testing.assert_frame_equal(a, b)


class TestGlobalGeneration:
    def test_shares_exact_over_table_total(self):
        schema = _schema(with_curve=False, row_count=2000)
        tables = _generate(schema)
        df = tables["orders"]
        total = round(float(df["revenue"].sum()), 2)
        expected = split_total_by_shares(SHARES, total)
        got = df.groupby("category")["revenue"].sum().round(2)
        for label, want in expected.items():
            assert abs(float(got.get(label, 0.0)) - want) < 0.005


class TestEdgeCases:
    def test_shares_not_summing_to_one_normalise_with_warning(self):
        spec = GroupShares(table="t", measure="m", group_column="g",
                           shares={"a": 0.5, "b": 0.47})
        with pytest.warns(UserWarning, match="normalising"):
            shares = normalized_shares(spec)
        assert abs(sum(shares.values()) - 1.0) < 1e-9

    def test_infeasible_bucket_warns_and_skips(self):
        # 2 rows cannot host 4 positive-share groups.
        df = pd.DataFrame({
            "g": ["x", "x"],
            "m": [10.0, 20.0],
        })
        spec = GroupShares(table="t", measure="m", group_column="g",
                           shares=SHARES)
        schema = SchemaConfig(name="x", tables=[], columns={},
                              relationships=[])
        with pytest.warns(UserWarning, match="infeasible"):
            out = apply_group_shares(df.copy(), spec, schema,
                                     np.random.default_rng(1))
        # Skipped: measure untouched.
        assert out["m"].tolist() == [10.0, 20.0]

    def test_missing_columns_leave_table_alone(self):
        df = pd.DataFrame({"other": [1, 2, 3]})
        spec = GroupShares(table="t", measure="m", group_column="g",
                           shares=SHARES)
        schema = SchemaConfig(name="x", tables=[], columns={},
                              relationships=[])
        out = apply_group_shares(df.copy(), spec, schema,
                                 np.random.default_rng(1))
        pd.testing.assert_frame_equal(out, df)


class TestStoryAudit:
    def test_clean_on_honest_data(self):
        schema = _schema(months=6, row_count=3000)
        tables = _generate(schema)
        report = misata.story_audit(tables, schema)
        kinds = [f.kind for f in report.findings]
        assert "group_share_mismatch" not in kinds

    def test_catches_sabotaged_group_total(self):
        schema = _schema(months=6, row_count=3000)
        tables = _generate(schema)
        sab = {k: v.copy() for k, v in tables.items()}
        mask = sab["orders"]["category"] == "Electronics"
        sab["orders"].loc[mask, "revenue"] *= 1.3
        report = misata.story_audit(sab, schema)
        findings = [f for f in report.findings
                    if f.kind == "group_share_mismatch"]
        assert findings and findings[0].severity == "high"

    def test_catches_global_case_sabotage(self):
        schema = _schema(with_curve=False, row_count=2000)
        tables = _generate(schema)
        sab = {k: v.copy() for k, v in tables.items()}
        # Relabel rows without touching the measure: shares now wrong.
        sab["orders"]["category"] = "Electronics"
        report = misata.story_audit(sab, schema)
        findings = [f for f in report.findings
                    if f.kind == "group_share_mismatch"]
        assert findings


class TestEvalpack:
    def test_group_questions_ship_and_verify(self, tmp_path):
        duckdb = pytest.importorskip("duckdb")
        schema = _schema(months=6, row_count=3000)
        out = tmp_path / "pack"
        from misata.evalpack import build_evalpack
        build_evalpack(schema, output_dir=str(out))
        qlist = [json.loads(l)
                 for l in (out / "questions.jsonl").read_text().splitlines()
                 if l.strip()]
        gsq = [q for q in qlist
               if q.get("source", {}).get("kind", "").startswith("group_share")]
        # 6 periods x 4 groups + 4 grand totals; the verifier gate may drop
        # none of them because generation is exact.
        assert len(gsq) == 6 * 4 + 4
        con = duckdb.connect()
        con.execute(
            f"CREATE VIEW orders AS SELECT * FROM "
            f"read_csv_auto('{out}/tables/orders.csv')")
        for q in gsq:
            val = con.execute(q["gold_sql"]).fetchone()[0]
            assert abs(float(val) - float(q["expected_answer"])) < 0.005, q["id"]

    def test_no_questions_without_curve(self, tmp_path):
        # Answer-key-first: without a curve the totals are measured, not
        # declared, so no group-share questions may ship.
        schema = _schema(with_curve=False, row_count=1000)
        from misata.evalpack import _group_share_questions
        counter = iter(range(10000))
        qs = _group_share_questions(schema, lambda: f"q{next(counter)}")
        assert qs == []


class TestDictEnvelope:
    def test_group_shares_envelope_parses_and_applies(self):
        schema_dict = {
            "orders": {
                "order_id": {"type": "integer", "primary_key": True},
                "order_date": {"type": "date", "min_date": "2025-01-01",
                               "max_date": "2025-03-31"},
                "category": {"type": "string", "enum": list(SHARES)},
                "revenue": {"type": "float", "min": 5, "max": 500,
                            "decimals": 2},
            },
            "__outcome_curves__": [{
                "table": "orders", "column": "revenue",
                "time_column": "order_date", "time_unit": "month",
                "value_mode": "absolute",
                "curve_points": [
                    {"date": f"2025-{m:02d}-01", "target_value": 50000.0}
                    for m in range(1, 4)],
            }],
            "__group_shares__": [{
                "table": "orders", "measure": "revenue",
                "group_column": "category", "shares": SHARES,
            }],
        }
        schema = misata.from_dict_schema(schema_dict, row_count=1500, seed=7)
        assert len(schema.group_shares) == 1
        tables = misata.generate_from_schema(schema)
        df = tables["orders"].copy()
        df["order_date"] = pd.to_datetime(df["order_date"])
        expected = split_total_by_shares(SHARES, 50000.0)
        for m in range(1, 4):
            got = (df[df["order_date"].dt.month == m]
                   .groupby("category")["revenue"].sum().round(2))
            for label, want in expected.items():
                assert abs(float(got.get(label, 0.0)) - want) < 0.005
