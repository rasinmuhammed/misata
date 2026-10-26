"""Rotated evalpacks: several databases that share every declared answer.

The contract under test: a question ships only when its answer holds on every
rotation, and a candidate query counts as correct only when it matches on
every rotation, so a query that fits one database by coincidence fails.
"""

import json
import shutil
import subprocess
import sys

import pytest

duckdb = pytest.importorskip("duckdb")

from click.testing import CliRunner

from misata import OutcomeCurveBuilder
from misata.cli import main
from misata.evalpack import build_evalpack, near_misses
from misata.evalpack_verify import check, load_candidates
from misata.schema import Column, Relationship, SchemaConfig, Table

SEED = 11
ROTATIONS = 3


def _schema(seed: int = SEED) -> SchemaConfig:
    schema = SchemaConfig(
        name="rotation_test",
        seed=seed,
        tables=[Table(name="customers", row_count=100), Table(name="orders", row_count=2000)],
        columns={
            "customers": [
                Column(name="customer_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 10_000}),
            ],
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 1_000_000}),
                Column(name="customer_id", type="foreign_key"),
                Column(name="amount", type="float", distribution_params={"min": 5, "max": 50_000}),
                Column(name="order_date", type="date",
                       distribution_params={"start": "2024-01-01", "end": "2024-12-31"}),
            ],
        },
        relationships=[
            Relationship(parent_table="customers", child_table="orders",
                         parent_key="customer_id", child_key="customer_id"),
        ],
    )
    curve = (
        OutcomeCurveBuilder("orders", column="amount", time_column="order_date")
        .anchor("2024-01", 20_000)
        .anchor("2024-12", 80_000)
        .avg_value(120.0)
        .row_bounds(1, 10_000)
        .build()
    )
    return OutcomeCurveBuilder.attach(schema, curve)


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    return build_evalpack(_schema(), tmp_path_factory.mktemp("rotated"), rotations=ROTATIONS)


def _rotation_dirs(pack):
    return sorted((pack.output_dir / "rotations").iterdir())


def _verify(pack_dir, *args):
    return subprocess.run([sys.executable, str(pack_dir / "verify.py"), *args],
                          capture_output=True, text=True)


class TestLayout:
    def test_one_folder_per_seed(self, pack):
        names = [d.name for d in _rotation_dirs(pack)]
        assert names == [f"seed-{SEED + i}" for i in range(ROTATIONS)]
        assert pack.seeds == [SEED + i for i in range(ROTATIONS)]

    def test_each_rotation_carries_its_own_proof(self, pack):
        for rotation in _rotation_dirs(pack):
            assert (rotation / "tables" / "orders.csv").is_file()
            certificate = json.loads((rotation / "certificate.json").read_text())
            assert certificate["seed"] == int(rotation.name.removeprefix("seed-"))
            assert certificate["all_match"] is True
            assert (rotation / "attestation.intoto.json").is_file()
            assert (rotation / "verify_attestation.py").is_file()

    def test_root_holds_one_question_set(self, pack):
        assert not (pack.output_dir / "tables").exists()
        lines = (pack.output_dir / "questions.jsonl").read_text().splitlines()
        assert len(lines) == len(pack.questions) > 0
        certificate = json.loads((pack.output_dir / "certificate.json").read_text())
        assert certificate["seeds"] == pack.seeds
        assert [r["seed"] for r in certificate["rotations"]] == pack.seeds
        assert "every rotation" in certificate["pass_rule"]

    def test_rotations_differ_in_rows(self, pack):
        orders = [(d / "tables" / "orders.csv").read_bytes() for d in _rotation_dirs(pack)]
        assert len(set(orders)) == ROTATIONS

    def test_manifest_records_rotations(self, pack):
        manifest = json.loads((pack.output_dir / "manifest.json").read_text())
        assert manifest["seeds"] == pack.seeds
        assert [r["directory"] for r in manifest["rotations"]] == [
            f"rotations/seed-{s}" for s in pack.seeds
        ]

    def test_summary_names_the_pass_rule(self, pack):
        assert f"databases: {ROTATIONS}" in pack.summary()


class TestNearMissStudy:
    def test_study_is_recorded(self, pack):
        study = json.loads((pack.output_dir / "manifest.json").read_text())["near_miss_study"]
        expected = sum(len(near_misses(q)) for q in pack.questions)
        assert study["queries"] == expected > 0
        assert study["databases"] == ROTATIONS
        assert set(study["by_mistake"]) <= {"inclusive_end", "exclusive_start",
                                            "inner_join", "whole_units"}

    def test_window_boundary_mistakes_are_caught(self, pack):
        # Whole-day timestamps put rows on every period boundary, so a window
        # opened at the wrong end returns a different total.
        study = json.loads((pack.output_dir / "manifest.json").read_text())["near_miss_study"]
        assert study["by_mistake"]["exclusive_start"]["false_positive_rate_one_database"] == 0
        assert study["by_mistake"]["inclusive_end"]["false_positive_rate_one_database"] < 0.25

    def test_matching_all_is_never_easier_than_matching_one(self, pack):
        study = json.loads((pack.output_dir / "manifest.json").read_text())["near_miss_study"]
        assert (study["false_positive_rate_all_databases"]
                <= study["false_positive_rate_one_database"])
        for stats in study["by_mistake"].values():
            assert (stats["false_positive_rate_all_databases"]
                    <= stats["false_positive_rate_one_database"])


class TestCandidates:
    def _period_question(self, pack):
        return next(q for q in pack.questions if q.source["kind"] == "outcome_curve_period")

    def _coincidental_sql(self, pack, question):
        """Right on the first rotation only: the gold answer shifted by a row-level fact."""
        first = _rotation_dirs(pack)[0] / "tables" / "orders.csv"
        anchor = duckdb.sql(f"SELECT MAX(order_id) FROM read_csv_auto('{first}')").fetchone()[0]
        return f"SELECT ({question.gold_sql}) + (SELECT MAX(order_id) FROM orders) - {anchor}"

    def test_gold_sql_passes_on_every_rotation(self, pack):
        result = _verify(pack.output_dir)
        assert result.returncode == 0, result.stdout + result.stderr
        assert f"match on all {ROTATIONS} database(s)" in result.stdout

    def test_candidates_file_scores_gold(self, pack, tmp_path):
        answers = tmp_path / "answers.jsonl"
        answers.write_text("".join(json.dumps({"id": q.id, "sql": q.gold_sql}) + "\n"
                                   for q in pack.questions))
        result = _verify(pack.output_dir, "--candidates", str(answers))
        assert result.returncode == 0, result.stdout + result.stderr

    def test_query_right_on_one_rotation_fails(self, pack):
        question = self._period_question(pack)
        wrong = self._coincidental_sql(pack, question)
        failures, lines = check(pack.output_dir, {question.id: wrong})
        assert failures == 1
        report = "\n".join(lines)
        assert f"FAIL {question.id}" in report
        assert f"seed-{SEED}:" not in report
        for seed in pack.seeds[1:]:
            assert f"seed-{seed}:" in report

    def test_unknown_question_id_fails(self, pack):
        failures, lines = check(pack.output_dir, {"no_such_question": "SELECT 1"})
        assert failures == 1 and "no such question" in lines[0]

    def test_sql_error_is_a_wrong_answer(self, pack):
        question = self._period_question(pack)
        failures, _ = check(pack.output_dir, {question.id: "SELECT * FROM missing_table"})
        assert failures == 1

    def test_tampered_rotation_fails_gold(self, pack, tmp_path):
        copy = tmp_path / "pack"
        shutil.copytree(pack.output_dir, copy)
        last = sorted((copy / "rotations").iterdir())[-1] / "tables" / "orders.csv"
        lines = last.read_text().splitlines()
        amount = lines[0].split(",").index("amount")
        row = lines[1].split(",")
        row[amount] = str(float(row[amount]) + 100.0)
        lines[1] = ",".join(row)
        last.write_text("\n".join(lines) + "\n")
        assert _verify(copy).returncode == 1


class TestCandidateFormats:
    @pytest.mark.parametrize("payload", [
        '{"id": "q1", "sql": "SELECT 1"}\n{"id": "q2", "sql": "SELECT 2"}\n',
        '[{"id": "q1", "sql": "SELECT 1"}, {"id": "q2", "sql": "SELECT 2"}]',
        '{"q1": "SELECT 1", "q2": "SELECT 2"}',
    ], ids=["jsonl", "list", "mapping"])
    def test_accepted_shapes(self, tmp_path, payload):
        path = tmp_path / "answers"
        path.write_text(payload)
        assert load_candidates(path) == {"q1": "SELECT 1", "q2": "SELECT 2"}

    def test_single_object_is_one_candidate(self, tmp_path):
        path = tmp_path / "answers.json"
        path.write_text('{"id": "q1", "sql": "SELECT 1"}')
        assert load_candidates(path) == {"q1": "SELECT 1"}


class TestGuards:
    def test_rotations_must_be_positive(self, tmp_path):
        with pytest.raises(ValueError, match="at least 1"):
            build_evalpack(_schema(), tmp_path, rotations=0)

    def test_pregenerated_tables_fit_one_seed(self, tmp_path):
        with pytest.raises(ValueError, match="one seed"):
            build_evalpack(_schema(), tmp_path, tables={}, rotations=2)


class TestCli:
    def test_rotations_flag(self, tmp_path):
        config = tmp_path / "schema.json"
        config.write_text(_schema().model_dump_json())
        out = tmp_path / "pack"
        result = CliRunner().invoke(main, ["evalpack", "-c", str(config), "-o", str(out),
                                           "--seed", "5", "--rotations", "2"])
        assert result.exit_code == 0, result.output
        assert sorted(d.name for d in (out / "rotations").iterdir()) == ["seed-5", "seed-6"]

    def test_rotations_flag_rejects_zero(self, tmp_path):
        config = tmp_path / "schema.json"
        config.write_text(_schema().model_dump_json())
        result = CliRunner().invoke(main, ["evalpack", "-c", str(config), "--rotations", "0"])
        assert result.exit_code == 2
