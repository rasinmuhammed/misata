"""Evalpack: answer-key-first eval databases with independent DuckDB verification.

The contract under test: every question shipped in a pack has an expected
answer that (a) derives only from the declared spec and (b) matches exact
execution of its gold SQL against the written CSVs in an engine that shares
no code with the generator. Candidates that fail are dropped, never shipped.
"""

import json
import subprocess
import sys

import pytest

duckdb = pytest.importorskip("duckdb")

import misata
from misata import OutcomeCurveBuilder, RateCurveBuilder
from misata.evalpack import build_evalpack, _quote_ident
from misata.schema import Column, Relationship, SchemaConfig, Table


def _pack_schema(seed: int = 7) -> SchemaConfig:
    schema = SchemaConfig(
        name="evalpack_test",
        seed=seed,
        tables=[
            Table(name="customers", row_count=200),
            Table(name="orders", row_count=5000),
        ],
        columns={
            "customers": [
                Column(name="customer_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 10_000}),
                Column(name="name", type="text"),
            ],
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 1_000_000}),
                Column(name="customer_id", type="foreign_key"),
                Column(name="amount", type="float",
                       distribution_params={"min": 5, "max": 100_000}),
                Column(name="is_refunded", type="boolean"),
                Column(name="order_date", type="datetime",
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-12-31"}),
            ],
        },
        relationships=[
            Relationship(parent_table="customers", child_table="orders",
                         parent_key="customer_id", child_key="customer_id"),
        ],
    )
    curve = (
        OutcomeCurveBuilder("orders", column="amount", time_column="order_date")
        .anchor("2024-01", 50_000)
        .anchor("2024-06", 120_000)
        .anchor("2024-12", 200_000)
        .avg_value(150.0)
        .build()
    )
    schema = OutcomeCurveBuilder.attach(schema, curve)
    rate = (
        RateCurveBuilder("orders", column="is_refunded", time_column="order_date")
        .anchor("2024-01", 0.03)
        .anchor("2024-12", 0.05)
        .build()
    )
    schema.rate_curves.append(rate)
    return schema


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    out = tmp_path_factory.mktemp("pack")
    result = build_evalpack(_pack_schema(), out)
    return result


class TestPackContents:
    def test_all_shipped_questions_verified(self, pack):
        assert pack.all_verified
        assert pack.certificate["all_match"] is True
        assert len(pack.questions) == len(pack.certificate["questions"])

    def test_expected_files_exist(self, pack):
        for name in ("questions.jsonl", "certificate.json", "manifest.json",
                     "verify.py", "README.md"):
            assert (pack.output_dir / name).exists(), name
        assert (pack.output_dir / "tables" / "orders.csv").exists()
        assert (pack.output_dir / "tables" / "customers.csv").exists()

    def test_period_totals_and_grand_total_shipped(self, pack):
        kinds = [q.source["kind"] for q in pack.questions]
        assert kinds.count("outcome_curve_period") == 12
        assert kinds.count("outcome_curve_total") == 1
        assert kinds.count("plan_row_count") == 12

    def test_fk_integrity_question_expects_zero(self, pack):
        fk = [q for q in pack.questions if q.source["kind"] == "fk_integrity"]
        assert len(fk) == 1
        assert fk[0].expected_answer == 0

    def test_argmax_question_answers_december(self, pack):
        argmax = [q for q in pack.questions
                  if q.source["kind"] == "outcome_curve_argmax"]
        assert len(argmax) == 1
        assert argmax[0].expected_answer == "2024-12"

    def test_rate_candidates_gated_not_silently_dropped(self, pack):
        # Interpolated rate anchors are usually infeasible under count
        # rounding; whatever fails exactness must land in dropped with the
        # observed value recorded, and nothing inexact may ship.
        shipped = [q for q in pack.questions
                   if q.source["kind"] == "rate_curve_anchor"]
        dropped = [d for d in pack.dropped
                   if d["source"]["kind"] == "rate_curve_anchor"]
        assert len(shipped) + len(dropped) == 12
        for d in dropped:
            assert d["drop_reason"] == "verification_mismatch"
            assert "observed" in d

    def test_manifest_records_seed_and_spec_hash(self, pack):
        manifest = json.loads((pack.output_dir / "manifest.json").read_text())
        assert manifest["seed"] == 7
        assert len(manifest["spec_sha256"]) == 64
        assert manifest["questions_shipped"] == len(pack.questions)
        assert manifest["misata_version"] == misata.__version__


class TestIndependentVerification:
    def test_questions_verify_against_csvs_in_fresh_duckdb(self, pack):
        """Re-execute every shipped gold SQL in a connection this test owns."""
        con = duckdb.connect()
        for csv in (pack.output_dir / "tables").glob("*.csv"):
            con.execute(
                f'CREATE VIEW "{csv.stem}" AS '
                f"SELECT * FROM read_csv_auto('{csv.resolve()}')"
            )
        for q in pack.questions:
            observed = con.execute(q.gold_sql).fetchone()[0]
            if q.answer_type == "string":
                assert str(observed) == str(q.expected_answer), q.id
            else:
                nd = q.round_decimals or 0
                assert observed == pytest.approx(
                    round(float(q.expected_answer), nd), abs=1e-9
                ), q.id

    def test_verify_script_passes_then_fails_after_tamper(self, pack, tmp_path):
        import shutil

        copy = tmp_path / "tampered"
        shutil.copytree(pack.output_dir, copy)

        ok = subprocess.run([sys.executable, str(copy / "verify.py")],
                            capture_output=True, text=True)
        assert ok.returncode == 0, ok.stdout + ok.stderr

        csv = copy / "tables" / "orders.csv"
        lines = csv.read_text().splitlines()
        header = lines[0].split(",")
        idx = header.index("amount")
        row = lines[1].split(",")
        row[idx] = str(float(row[idx]) + 100.0)
        lines[1] = ",".join(row)
        csv.write_text("\n".join(lines) + "\n")

        bad = subprocess.run([sys.executable, str(copy / "verify.py")],
                             capture_output=True, text=True)
        assert bad.returncode == 1


class TestReproducibility:
    def test_same_seed_same_expected_answers(self, tmp_path):
        r1 = build_evalpack(_pack_schema(seed=99), tmp_path / "a")
        r2 = build_evalpack(_pack_schema(seed=99), tmp_path / "b")
        a1 = {q.id: q.expected_answer for q in r1.questions}
        a2 = {q.id: q.expected_answer for q in r2.questions}
        assert a1 == a2

    def test_fresh_seed_keeps_declared_answers(self, tmp_path):
        """The contamination-resistance property: a regenerated database under
        a new seed still satisfies the same declared aggregate answers."""
        r1 = build_evalpack(_pack_schema(seed=1), tmp_path / "a")
        r2 = build_evalpack(_pack_schema(seed=2), tmp_path / "b")
        curve_answers = lambda r: {  # noqa: E731
            q.source["period"]: q.expected_answer
            for q in r.questions
            if q.source["kind"] == "outcome_curve_period"
        }
        assert curve_answers(r1) == curve_answers(r2)
        assert r1.all_verified and r2.all_verified


class TestGuards:
    def test_unsafe_identifier_rejected(self):
        with pytest.raises(ValueError, match="plain SQL identifier"):
            _quote_ident('orders"; DROP TABLE x; --')

    def test_schema_without_declarations_ships_nothing(self, tmp_path):
        schema = SchemaConfig(
            name="bare",
            seed=1,
            tables=[Table(name="items", row_count=50)],
            columns={"items": [
                Column(name="item_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 1000}),
            ]},
        )
        result = build_evalpack(schema, tmp_path / "bare")
        assert result.questions == []
        assert result.all_verified is False
