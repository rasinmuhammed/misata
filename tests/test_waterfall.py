"""Waterfall identities: MRR-style movements reconciling to declared balances.

Declare a starting value and per-period ending values; the generated
new/expansion/contraction/churn rows must satisfy the identity exactly per
period, the audit must be silent on honest data and loud on sabotage, and the
evalpack questions (all derived from the declaration) must verify via DuckDB.
"""

import json

import numpy as np
import pandas as pd
import pytest

import misata
from misata.schema import Column, SchemaConfig, Table, WaterfallIdentity
from misata.waterfall import apply_waterfall, declared_movements

POINTS = [{"period": f"2025-{m:02d}", "ending_value": 100000.0 + m * 6000}
          for m in range(1, 7)]
POINTS[3]["ending_value"] = POINTS[2]["ending_value"] - 3500.0  # decline month
INFLOWS = {"new", "expansion"}


def _schema(rows=2000, points=POINTS, **spec_kwargs):
    cols = [
        Column(name="movement_id", type="int", unique=True,
               distribution_params={"min": 1, "max": 9_999_999}),
        Column(name="period", type="text"),
        Column(name="movement_type", type="text"),
        Column(name="amount", type="float"),
    ]
    return SchemaConfig(
        name="waterfall_test", seed=7,
        tables=[Table(name="mrr_movements", row_count=rows,
                      columns=[c.name for c in cols])],
        columns={"mrr_movements": cols}, relationships=[],
        waterfalls=[WaterfallIdentity(
            table="mrr_movements", starting_value=100000.0,
            points=points, **spec_kwargs)],
    )


def _running(df, points, starting=100000.0):
    signed = df["amount"].where(df["movement_type"].isin(INFLOWS), -df["amount"])
    balances = []
    run = starting
    for pt in points:
        run = round(run + round(float(
            signed[df["period"] == pt["period"]].sum()), 2), 2)
        balances.append(run)
    return balances


class TestDeclaredPlan:
    def test_net_of_plan_equals_declared_delta(self):
        spec = _schema().waterfalls[0]
        prev = 100000.0
        for (period, end, ins, outs) in declared_movements(spec):
            net = round(sum(ins.values()) - sum(outs.values()), 2)
            assert abs(net - round(end - prev, 2)) < 0.005
            prev = end

    def test_decline_month_keeps_gross_sides_positive(self):
        spec = _schema().waterfalls[0]
        plan = declared_movements(spec)
        period, end, ins, outs = plan[3]
        assert end < plan[2][1]
        assert all(v >= 0 for v in ins.values())
        assert sum(outs.values()) > 0

    def test_shares_not_summing_normalise_with_warning(self):
        spec = _schema(inflow_shares={"new": 0.5, "expansion": 0.45}).waterfalls[0]
        with pytest.warns(UserWarning, match="normalising"):
            declared_movements(spec)


class TestGeneration:
    @pytest.fixture(scope="class")
    def generated(self):
        schema = _schema()
        return schema, misata.generate_from_schema(schema)

    def test_running_balance_hits_every_declared_ending(self, generated):
        _, tables = generated
        balances = _running(tables["mrr_movements"], POINTS)
        for got, pt in zip(balances, POINTS):
            assert abs(got - pt["ending_value"]) < 0.005, (
                f"{pt['period']}: {got} != {pt['ending_value']}")

    def test_all_types_present_and_positive(self, generated):
        _, tables = generated
        df = tables["mrr_movements"]
        assert set(df["movement_type"]) == {"new", "expansion",
                                             "churn", "contraction"}
        assert (pd.to_numeric(df["amount"]) > 0).all()

    def test_reproducible(self):
        a = misata.generate_from_schema(_schema())["mrr_movements"]
        b = misata.generate_from_schema(_schema())["mrr_movements"]
        pd.testing.assert_frame_equal(a, b)

    def test_infeasible_row_count_warns_and_skips(self):
        df = pd.DataFrame({
            "period": ["x"] * 3, "movement_type": ["y"] * 3,
            "amount": [1.0, 2.0, 3.0],
        })
        spec = _schema().waterfalls[0]  # 6 periods x 4 types = 24 cells > 3 rows
        with pytest.warns(UserWarning, match="infeasible"):
            out = apply_waterfall(df.copy(), spec, np.random.default_rng(1))
        assert out["amount"].tolist() == [1.0, 2.0, 3.0]


class TestAudit:
    def test_clean_on_honest_data(self):
        schema = _schema()
        tables = misata.generate_from_schema(schema)
        rep = misata.story_audit(tables, schema)
        assert not [f for f in rep.findings if f.kind == "waterfall_mismatch"]

    def test_catches_inflated_movement(self):
        schema = _schema()
        tables = misata.generate_from_schema(schema)
        sab = {k: v.copy() for k, v in tables.items()}
        df = sab["mrr_movements"]
        i = df[df["movement_type"] == "new"].index[0]
        df.loc[i, "amount"] = float(df.loc[i, "amount"]) + 9000.0
        rep = misata.story_audit(sab, schema)
        findings = [f for f in rep.findings if f.kind == "waterfall_mismatch"]
        assert findings and findings[0].severity == "high"


class TestEvalpack:
    def test_questions_ship_and_verify(self, tmp_path):
        duckdb = pytest.importorskip("duckdb")
        schema = _schema()
        out = tmp_path / "pack"
        from misata.evalpack import build_evalpack
        build_evalpack(schema, output_dir=str(out))
        qs = [json.loads(l)
              for l in (out / "questions.jsonl").read_text().splitlines()
              if l.strip()]
        wfq = [q for q in qs
               if q.get("source", {}).get("kind", "").startswith("waterfall")]
        # 6 nets + 6 running balances + 6x4 components, none may be dropped.
        assert len(wfq) == 6 + 6 + 24
        con = duckdb.connect()
        con.execute(
            f"CREATE VIEW mrr_movements AS SELECT * FROM "
            f"read_csv_auto('{out}/tables/mrr_movements.csv')")
        for q in wfq:
            v = con.execute(q["gold_sql"]).fetchone()[0]
            assert abs(float(v) - float(q["expected_answer"])) < 0.005, q["id"]

    def test_no_running_balance_questions_for_unsorted_labels(self):
        points = [{"period": "march", "ending_value": 110000.0},
                  {"period": "april", "ending_value": 120000.0}]
        schema = _schema(points=points)
        from misata.evalpack import _waterfall_questions
        counter = iter(range(10000))
        qs = _waterfall_questions(schema, lambda: f"q{next(counter)}")
        kinds = {q.source["kind"] for q in qs}
        assert "waterfall_balance" not in kinds
        assert "waterfall_net" in kinds


class TestDictEnvelope:
    def test_waterfalls_envelope_parses_and_applies(self):
        schema = misata.from_dict_schema({
            "mrr_movements": {
                "movement_id": {"type": "integer", "primary_key": True},
                "period": {"type": "string"},
                "movement_type": {"type": "string"},
                "amount": {"type": "float"},
            },
            "__waterfalls__": [{
                "table": "mrr_movements", "starting_value": 50000.0,
                "points": [{"period": "2025-01", "ending_value": 56000.0},
                           {"period": "2025-02", "ending_value": 61000.0}],
            }],
        }, row_count=600, seed=3)
        assert len(schema.waterfalls) == 1
        tables = misata.generate_from_schema(schema)
        balances = _running(tables["mrr_movements"],
                            [{"period": "2025-01", "ending_value": 56000.0},
                             {"period": "2025-02", "ending_value": 61000.0}],
                            starting=50000.0)
        assert balances == [56000.0, 61000.0]
