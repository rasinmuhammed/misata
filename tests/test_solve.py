"""misata.solve: move outcome curves until a pipeline's metrics hit targets."""

from __future__ import annotations

import json
import subprocess
import sys
import warnings
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

import misata
from misata.solve import (
    MAX_STEP,
    PipelineError,
    SolveError,
    SQLRunner,
    Target,
    _bounded,
    _coupled_step,
    _ratio_step,
    _secant_step,
    load_config,
    parse_tolerance,
    solve,
)

duckdb = pytest.importorskip("duckdb")

MONTHS = ["2025-01", "2025-02", "2025-03", "2025-04"]
GOALS = dict(zip(MONTHS, [70_000, 65_000, 72_000, 80_000], strict=True))


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


def _schema(order_max: float = 500, refunds: float = 4_000.0) -> misata.SchemaConfig:
    return misata.from_dict_schema({
        "orders": {"__rows__": 2_000,
                   "order_id": {"type": "int", "primary_key": True},
                   "amount": {"type": "float", "min": 5, "max": order_max},
                   "ordered_at": {"type": "datetime", "start": "2025-01-01",
                                  "end": "2025-04-30"}},
        "refunds": {"__rows__": 400,
                    "refund_id": {"type": "int", "primary_key": True},
                    "amount": {"type": "float", "min": 1, "max": 200},
                    "refunded_at": {"type": "datetime", "start": "2025-01-01",
                                    "end": "2025-04-30"}},
        "__outcome_curves__": [
            {"table": "orders", "column": "amount", "time_column": "ordered_at",
             "value_mode": "absolute",
             "curve_points": [{"month": i + 1, "target_value": v}
                              for i, v in enumerate([50_000, 52_000, 55_000, 60_000])]},
            {"table": "refunds", "column": "amount", "time_column": "refunded_at",
             "value_mode": "absolute",
             "curve_points": [{"month": i + 1, "target_value": refunds} for i in range(4)]},
        ],
    }, seed=11)


def _monthly(frame: pd.DataFrame, column: str, at: str) -> pd.Series:
    return frame.groupby(pd.to_datetime(frame[at]).dt.to_period("M"))[column].sum()


def _fee(tables):
    return {"net": _monthly(tables["orders"], "amount", "ordered_at") * 0.97}


def _net_of_refunds(tables):
    return {"net": _monthly(tables["orders"], "amount", "ordered_at")
            - _monthly(tables["refunds"], "amount", "refunded_at")}


def _blend(tables):
    month = _monthly(tables["orders"], "amount", "ordered_at")
    return {"net": 0.7 * month + 0.3 * month.shift(1).fillna(0)}


FEE_SQL = "SELECT date_trunc('month', ordered_at), SUM(amount) * 0.97 FROM orders GROUP BY 1"


class TestConverges:
    def test_a_direct_lever_converges_and_the_result_regenerates(self):
        result = solve(_schema(), _fee, [Target("net", "orders.amount", GOALS)],
                       tolerance="0.5%")
        assert result.converged and result.reason == "converged"
        assert result.iterations <= 6
        again = misata.generate_from_schema(result.schema)
        assert misata.fingerprint(again) == misata.fingerprint(result.tables)
        net = _fee(result.tables)["net"]
        for month, goal in GOALS.items():
            assert abs(net[pd.Period(month)] - goal) <= 0.005 * goal

    def test_an_inverse_lever_moves_the_other_way(self):
        goals = dict(zip(MONTHS, [45_000, 49_000, 50_000, 57_000], strict=True))
        result = solve(_schema(), _net_of_refunds,
                       [{"metric": "net", "lever": "refunds.amount", "values": goals,
                         "direction": "inverse"}], tolerance="0.5%")
        assert result.converged, result.message
        assert result.iterations <= 4

    def test_coupled_periods_converge_through_the_fitted_transfer(self):
        result = solve(_schema(), _blend, [Target("net", "orders.amount", GOALS)],
                       tolerance="0.1%", max_iterations=30)
        assert result.converged, result.message
        assert any("coupled" in m for s in result.steps for m in s.method.values())

    def test_the_trajectory_is_deterministic(self):
        first = solve(_schema(), _fee, [Target("net", "orders.amount", GOALS)])
        second = solve(_schema(), _fee, [Target("net", "orders.amount", GOALS)])
        assert [s.to_dict() for s in first.steps] == [s.to_dict() for s in second.steps]

    def test_periods_name_any_date_inside_them(self):
        goals = {pd.Timestamp("2025-01-15"): 70_000, pd.Period("2025-02", "M"): 65_000}
        result = solve(_schema(), _fee, [Target("net", "orders.amount", goals)],
                       tolerance="0.5%")
        assert result.converged
        assert set(result.best.gaps["net"]) == {"2025-01", "2025-02"}

    def test_an_untargeted_period_keeps_its_declared_value(self):
        result = solve(_schema(), _fee, [Target("net", "orders.amount",
                                                {"2025-02": 65_000})])
        points = result.levers()["orders.amount"]
        assert points[0]["target_value"] == 50_000 and points[2]["target_value"] == 55_000


class TestStops:
    def test_a_lever_declared_the_wrong_way_diverges(self):
        result = solve(_schema(), _fee, [Target("net", "orders.amount", GOALS, "inverse")])
        assert result.reason == "diverging"
        assert "direction: inverse" in result.message
        gaps = [s.max_gap for s in result.steps]
        assert gaps[-1] > gaps[0]

    def test_a_metric_that_ignores_its_lever_is_unresponsive(self):
        result = solve(_schema(), lambda t: {"net": {m: 1_000.0 for m in MONTHS}},
                       [Target("net", "orders.amount", GOALS)])
        assert result.reason == "unresponsive" and result.iterations == 2

    def test_the_budget_stops_with_the_closest_iteration(self):
        result = solve(_schema(), _blend, [Target("net", "orders.amount", GOALS)],
                       tolerance="0.01%", max_iterations=3)
        assert result.reason == "max_iterations" and not result.converged
        assert result.best.max_gap == min(s.max_gap for s in result.steps)
        assert result.tables is not None

    def test_a_schema_that_cannot_generate_is_infeasible_with_its_conflicts(self):
        schema = misata.from_dict_schema({
            "orders": {"__rows__": 10, "code": {"type": "int", "unique": True, "min": 1, "max": 3},
                       "amount": {"type": "float", "min": 1, "max": 9},
                       "ordered_at": {"type": "datetime", "start": "2025-01-01",
                                      "end": "2025-01-31"}},
            "__outcome_curves__": [{"table": "orders", "column": "amount",
                                    "time_column": "ordered_at", "value_mode": "absolute",
                                    "curve_points": [{"month": 1, "target_value": 50}]}],
        }, seed=1)
        result = solve(schema, _fee, [Target("net", "orders.amount", {"2025-01": 60})])
        assert result.reason == "infeasible" and result.conflicts
        assert result.iterations == 0 and result.tables is None

    def test_values_the_bounds_cannot_reach_stop_as_infeasible(self):
        result = solve(_schema(order_max=6), _fee,
                       [Target("net", "orders.amount", {m: 9e9 for m in MONTHS})],
                       max_iterations=12)
        assert result.reason == "infeasible"
        assert "iteration" in result.message

    def test_a_pipeline_exception_stops_with_its_message(self):
        def broken(_tables):
            raise RuntimeError("warehouse unreachable")
        result = solve(_schema(), broken, [Target("net", "orders.amount", GOALS)])
        assert result.reason == "pipeline_error"
        assert result.message == "RuntimeError: warehouse unreachable"

    @pytest.mark.parametrize("output,match", [
        ({"gross": {}}, "no metric 'net'"),
        ({"net": {"2030-01": 5.0}}, "no value in any targeted period"),
        ({"net": [("2025-01-01", 1.0), ("2025-01-20", 2.0)]}, "more than one value"),
        ({"net": {"2025-01": None}}, "is None"),
        ({"net": pd.DataFrame({"a": [1], "b": [2], "c": [3]})}, "two columns"),
    ])
    def test_unreadable_output_is_a_pipeline_error(self, output, match):
        result = solve(_schema(), lambda _t: output, [Target("net", "orders.amount", GOALS)])
        assert result.reason == "pipeline_error" and match in result.message


class TestRefusesBeforeRunning:
    @pytest.mark.parametrize("target,match", [
        (Target("net", "orders.total", GOALS), "no outcome curve on orders.total"),
        (Target("net", "orders.amount", {"2026-01": 5}), "outside the orders.amount curve"),
        (Target("net", "orders.amount", {"2025-01": 0}), "non-zero"),
        (Target("net", "orders.amount", {"2025-01": 0.001}), "two decimal places"),
        (Target("net", "orders.amount", {1: 5}), "is a number"),
        (Target("net", "orders.amount", {"2025-01-02": 5, "2025-01-09": 6}), "two values"),
        (Target("net", "orders.amount", GOALS, "sideways"), "direction"),
        (Target("net", "orders.amount", {}), "names no periods"),
    ])
    def test_bad_targets(self, target, match):
        with pytest.raises(SolveError, match=match):
            solve(_schema(), _fee, [target])

    def test_one_lever_per_metric(self):
        with pytest.raises(SolveError, match="two targets move"):
            solve(_schema(), _fee, [Target("a", "orders.amount", GOALS),
                                    Target("b", "orders.amount", GOALS)])

    def test_a_relative_curve_is_not_a_lever(self):
        schema = _schema()
        schema.outcome_curves[0].value_mode = "relative"
        with pytest.raises(SolveError, match="relative"):
            solve(schema, _fee, [Target("net", "orders.amount", GOALS)])

    @pytest.mark.parametrize("value", ["0", "100%", "-1", "abc", "1.5"])
    def test_bad_tolerances(self, value):
        with pytest.raises(SolveError):
            parse_tolerance(value)

    def test_tolerance_forms(self):
        assert parse_tolerance("0.5%") == parse_tolerance(0.005) == Decimal("0.005")
        assert parse_tolerance("0.00001%") == Decimal("0.0000001")

    def test_the_callers_schema_is_left_alone(self):
        schema = _schema()
        before = schema.model_dump()
        solve(schema, _fee, [Target("net", "orders.amount", GOALS)], max_iterations=2)
        assert schema.model_dump() == before


class TestSteps:
    def test_a_ratio_across_zero_nudges_instead_of_going_complex(self):
        assert _ratio_step(100.0, -50.0, 80.0, "direct", 0.85, 1.0) == pytest.approx(150.0)
        assert _ratio_step(100.0, -50.0, 80.0, "inverse", 0.85, 1.0) == pytest.approx(100 / 1.5)

    def test_a_zero_value_restarts_from_the_seed_only_when_it_must_grow(self):
        assert _ratio_step(0.0, 10.0, 20.0, "direct", 0.85, 7.0) == 7.0
        assert _ratio_step(0.0, 30.0, 20.0, "direct", 0.85, 7.0) == 0.0

    def test_a_step_never_crosses_zero_or_grows_past_the_cap(self):
        assert _bounded(10.0, -5.0, 1.0) == 0.0
        assert _bounded(-10.0, 5.0, -1.0) == 0.0
        assert _bounded(10.0, 10_000.0, 1.0) == 10.0 * MAX_STEP

    def test_a_secant_against_the_declared_direction_is_refused(self):
        history = [(np.array([10.0]), np.array([100.0])), (np.array([20.0]), np.array([50.0]))]
        assert _secant_step(history, 0, 80.0, slope_sign=1.0) is None
        assert _secant_step(history, 0, 80.0, slope_sign=-1.0) == pytest.approx(14.0)

    def test_a_coupled_fit_will_not_extrapolate_far_past_its_samples(self):
        rng = np.random.default_rng(0)
        transfer = np.array([[1.0, 0.2], [0.1, 1.0]])
        fed = [np.array([10.0, 10.0]) + rng.random(2) for _ in range(4)]
        history = [(f, transfer @ f) for f in fed]
        near = transfer @ np.array([10.5, 10.5])
        assert _coupled_step(history, near, np.ones(2)) == pytest.approx([10.5, 10.5])
        far = transfer @ np.array([1_000.0, 1_000.0])
        assert _coupled_step(history, far, np.ones(2)) is None


class TestSQL:
    def test_sql_and_python_pipelines_agree(self):
        target = [Target("net", "orders.amount", GOALS)]
        via_sql = solve(_schema(), SQLRunner({"net": FEE_SQL}), target)
        via_python = solve(_schema(), _fee, target)
        assert [s.max_gap for s in via_sql.steps] == pytest.approx(
            [s.max_gap for s in via_python.steps], rel=1e-9)

    @pytest.mark.parametrize("sql,match", [
        ("SELECT * FROM read_csv('/etc/passwd')", "net"),
        ("SELECT 1, 2; DROP TABLE orders", "net"),
        ("SELECT now(), x FROM range(1000000000000) AS t(x)", "stopped after"),
    ])
    def test_the_sandbox_refuses_files_second_statements_and_runaway_queries(self, sql, match):
        runner = SQLRunner({"net": sql}, timeout=0.5)
        result = solve(_schema(), runner, [Target("net", "orders.amount", GOALS)])
        assert result.reason == "pipeline_error" and match in result.message

    def test_a_solved_dataset_attests_and_verify_py_rechecks_every_period(self, tmp_path):
        pytest.importorskip("pyarrow")
        result = solve(_schema(), SQLRunner({"net": FEE_SQL}),
                       [Target("net", "orders.amount", GOALS)], tolerance="0.5%")
        result.write(tmp_path, fmt="parquet")
        attestation = result.attest(tmp_path)
        assert attestation.passed, attestation.failures
        solved = [i for i in attestation.statement["predicate"]["invariants"]
                  if i["kind"] == "solved_target"]
        assert len(solved) == len(GOALS)
        assert {i["comparator"] for i in solved} == {"within_tolerance"}
        assert {i["tolerance"] for i in solved} == {"0.005"}
        verify = [sys.executable, str(tmp_path / "verify.py")]
        assert subprocess.run(verify, capture_output=True).returncode == 0

        orders = tmp_path / "orders.parquet"
        frame = pd.read_parquet(orders)
        frame["amount"] *= 1.05
        frame.to_parquet(orders, index=False)
        report = subprocess.run(verify, capture_output=True, text=True)
        assert report.returncode == 1 and "solved" in report.stdout

    def test_a_python_pipeline_writes_no_solved_invariants(self, tmp_path):
        result = solve(_schema(), _fee, [Target("net", "orders.amount", GOALS)])
        assert result.invariants() == []
        result.write(tmp_path)
        assert result.attest(tmp_path).passed
        record = json.loads((tmp_path / "solve.json").read_text())
        assert record["runner"]["kind"] == "python" and record["converged"]


CONFIG = """\
schema: misata.yaml
tolerance: 0.5%
pipeline:
  sql:
    net: |
      SELECT date_trunc('month', ordered_at), SUM(amount) * 0.97
      FROM orders GROUP BY 1
targets:
  - metric: net
    lever: orders.amount
    values: {2025-01: 70000, 2025-02: 65000}
"""

YAML_SCHEMA = """\
name: shop
seed: 11
tables:
  orders:
    rows: 1500
    columns:
      order_id: {type: int, unique: true}
      amount: {type: float, min: 5, max: 500}
      ordered_at: {type: datetime, start: "2025-01-01", end: "2025-02-28"}
outcome_curves:
  - table: orders
    column: amount
    time_column: ordered_at
    value_mode: absolute
    curve_points:
      - {month: 1, target_value: 50000}
      - {month: 2, target_value: 52000}
"""


@pytest.fixture
def config(tmp_path):
    (tmp_path / "misata.yaml").write_text(YAML_SCHEMA)
    path = tmp_path / "solve.yaml"
    path.write_text(CONFIG)
    return path


class TestConfigAndCLI:
    def test_the_config_runs_and_writes_a_patched_yaml(self, config, tmp_path):
        loaded = load_config(config)
        result = loaded.run()
        assert result.converged
        result.write(tmp_path / "out", source_yaml=loaded.schema_path)
        solved = misata.load_yaml_schema(tmp_path / "out" / "misata.solved.yaml")
        assert misata.fingerprint(misata.generate_from_schema(solved)) == misata.fingerprint(
            result.tables)

    @pytest.mark.parametrize("edit,match", [
        (lambda c: c.replace("schema: misata.yaml", "schema: nope.yaml"), "does not exist"),
        (lambda c: c.replace("  sql:", "  spark:"), "unknown pipeline"),
        (lambda c: c + "extra: 1\n", "unknown field"),
        (lambda c: c.split("targets:")[0], "needs targets"),
    ])
    def test_config_mistakes_are_named(self, config, edit, match):
        config.write_text(edit(CONFIG))
        with pytest.raises(SolveError, match=match):
            load_config(config)

    def _run(self, *args):
        from click.testing import CliRunner

        from misata.cli import main

        result = CliRunner().invoke(main, ["solve", *args, "--json"])
        return result.exit_code, json.loads(result.stdout)

    def test_cli_converges_with_exit_0_and_writes_a_passing_certificate(self, config, tmp_path):
        code, envelope = self._run("-c", str(config), "-o", str(tmp_path / "o"))
        assert code == 0, envelope["message"]
        assert envelope["data"]["solve"]["converged"]
        assert envelope["data"]["solve"]["attestation"]["result"] == "PASSED"

    def test_cli_stops_short_with_exit_1_and_the_trajectory(self, config):
        config.write_text(CONFIG.replace("0.5%", "0.0001%"))
        code, envelope = self._run("-c", str(config), "--max-iterations", "2")
        assert code == 1 and envelope["code"] == "failed"
        assert len(envelope["data"]["solve"]["steps"]) == 2

    def test_cli_config_mistake_is_exit_2(self, config):
        config.write_text(CONFIG.replace("orders.amount", "orders.nope"))
        code, envelope = self._run("-c", str(config))
        assert code == 2 and "no outcome curve" in envelope["message"]

    def test_cli_infeasible_schema_is_exit_3(self, config, tmp_path):
        (tmp_path / "misata.yaml").write_text(YAML_SCHEMA.replace(
            "order_id: {type: int, unique: true}",
            "order_id: {type: int, unique: true, min: 1, max: 5}"))
        code, envelope = self._run("-c", str(config))
        assert code == 3 and envelope["conflicts"]


class TestPipelineErrorType:
    def test_pipeline_error_is_a_runtime_error(self):
        assert issubclass(PipelineError, RuntimeError)


def _dbt_available() -> bool:
    """dbt is installed and runs on this interpreter (dbt-core lags new Pythons)."""
    import shutil
    from pathlib import Path

    dbt = shutil.which("dbt") or shutil.which("dbt", path=str(Path(sys.executable).parent))
    if dbt is None:
        return False
    try:
        return subprocess.run([dbt, "--version"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _dbt_available(), reason="needs dbt-duckdb")
class TestDbt:
    PROJECT = {
        "dbt_project.yml": "name: shop\nversion: '1.0.0'\nprofile: shop\nmodel-paths: [models]\n"
                           "models:\n  shop:\n    +materialized: table\n",
        "models/sources.yml": "version: 2\nsources:\n  - name: raw\n    schema: main\n"
                              "    tables: [{name: orders}, {name: refunds}]\n",
        "models/fct_net.sql": (
            "with o as (select date_trunc('month', ordered_at) as m, sum(amount) * 0.97 as g "
            "from {{ source('raw', 'orders') }} group by 1), "
            "r as (select date_trunc('month', refunded_at) as m, sum(amount) as x "
            "from {{ source('raw', 'refunds') }} group by 1) "
            "select o.m, o.g - coalesce(r.x, 0) as net from o left join r using (m)"),
    }

    def _project(self, root):
        for name, text in self.PROJECT.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return root

    def test_a_dbt_project_solves_and_is_left_untouched(self, tmp_path):
        from misata.solve import DbtDuckDBRunner

        project = self._project(tmp_path / "shop")
        before = sorted(p.as_posix() for p in project.rglob("*"))
        runner = DbtDuckDBRunner(project, {"net": "SELECT m, net FROM fct_net"})
        goals = dict(zip(MONTHS, [46_000, 48_000, 51_000, 55_000], strict=True))
        result = solve(_schema(), runner, [Target("net", "refunds.amount", goals, "inverse")],
                       tolerance="0.5%", max_iterations=10)
        assert result.converged, result.message
        assert result.runner["kind"] == "dbt-duckdb"
        assert sorted(p.as_posix() for p in project.rglob("*")) == before

    def test_seeds_load_before_the_models_run(self, tmp_path):
        from misata.solve import DbtDuckDBRunner

        project = self._project(tmp_path / "shop")
        (project / "seeds").mkdir()
        (project / "seeds/fee_rates.csv").write_text("rate\n0.97\n")
        (project / "models/fct_net.sql").write_text(
            "select date_trunc('month', ordered_at) as m, "
            "sum(amount) * (select rate from {{ ref('fee_rates') }}) as net "
            "from {{ source('raw', 'orders') }} group by 1")
        metrics = {"net": "SELECT m, net FROM fct_net"}
        unseeded = solve(_schema(), DbtDuckDBRunner(project, metrics),
                         [Target("net", "orders.amount", GOALS)], max_iterations=1)
        assert unseeded.reason == "pipeline_error"

        seeded = DbtDuckDBRunner(project, metrics, seeds="fee_rates")
        result = solve(_schema(), seeded, [Target("net", "orders.amount", GOALS)],
                       tolerance="0.5%", max_iterations=10)
        assert result.converged, result.message

    def test_a_failing_model_reports_dbts_error(self, tmp_path):
        from misata.solve import DbtDuckDBRunner

        project = self._project(tmp_path / "shop")
        (project / "models/fct_net.sql").write_text("select broken from where")
        runner = DbtDuckDBRunner(project, {"net": "SELECT m, net FROM fct_net"})
        result = solve(_schema(), runner, [Target("net", "orders.amount", GOALS)])
        assert result.reason == "pipeline_error"
        assert "dbt run failed" in result.message and "\x1b[" not in result.message
