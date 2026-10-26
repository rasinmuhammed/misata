"""Solve declared inputs until a pipeline's outputs hit declared targets.

A schema's outcome curves fix what Misata generates: the total of
``orders.amount`` in each month. A pipeline someone else wrote (a dbt
project, a SQL model, a Python function) turns those tables into the numbers
people look at: net revenue after refunds, tax owed, retained users. Those
are not declarations Misata owns, so they cannot be generated directly.

:func:`solve` closes the loop. It generates, runs the pipeline, compares each
metric with its target period by period, and moves only the outcome-curve
values it was given as levers, until every period is within tolerance or the
run stops and says why. Every iteration generates from a complete, feasible
schema with the same seed, so each point on the trajectory is a dataset the
solved spec reproduces exactly.

Each lever steps by the first of these that applies:

* **Coupled least squares.** Pipelines often move a row across a period
  boundary, so feeding more into March also raises April. Once a lever has
  ``n + 1`` distinct observations for its ``n`` periods, the solver fits
  ``measured = A @ fed + b`` over a sliding window and steps toward
  ``A^-1 (target - b)``. The fit is used only when it is well conditioned,
  keeps every value's sign and reaches no further past the observed values
  than their own spread.
* **Secant.** A period whose last two observations slope the way its
  direction says steps to where that line meets the target. Pipelines that
  add or subtract the lever (net = gross - refunds) are lines, and a ratio
  step crawls on them.
* **Damped ratio.** The period's value is multiplied by
  ``(target / measured) ** damping``, or by the reciprocal for an
  ``inverse`` lever, whose larger magnitudes lower the metric. When the
  ratio is undefined (nothing measured, or measured and target on opposite
  sides of zero) the step is a fixed factor of 1.5 in the direction the
  metric must move.

Coupled and secant steps move ``damping`` of the way to their answer.

Every step is bounded: no value grows more than twentyfold in one step, none
crosses zero, and none exceeds 1e12 in magnitude. A run whose largest gap
widens three iterations in a row to end further off than it started stops as
``diverging`` with its trajectory rather than guessing further.

Generation is random within each period, so a pipeline that reads rows
across period boundaries sees a little noise from one iteration to the next.
A tolerance below that noise cannot be reached reliably, and the run reports
``max_iterations`` with its closest iteration.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Union,
    runtime_checkable,
)

import numpy as np
import pandas as pd

from misata.attestation_verify import format_value, within_tolerance

if TYPE_CHECKING:
    from misata.attestation import Attestation, Invariant
    from misata.feasibility import Conflict
    from misata.schema import OutcomeCurve, SchemaConfig

__all__ = [
    "DbtDuckDBRunner",
    "PipelineError",
    "PythonRunner",
    "Runner",
    "SQLRunner",
    "SolveError",
    "SolveResult",
    "SolveStep",
    "Target",
    "solve",
]

REASONS = ("converged", "max_iterations", "max_seconds", "diverging", "unresponsive",
           "infeasible", "pipeline_error")

DIRECTIONS = ("direct", "inverse")

#: Largest factor a lever value may change by in one step.
MAX_STEP = 20.0
#: Largest magnitude a lever value may take.
MAX_MAGNITUDE = 1e12
#: Step used when the measured-to-target ratio says nothing about magnitude.
NUDGE = 1.5
#: How far past the values it was fitted on a coupled solution may reach, as a
#: multiple of their spread. Further out, the fit is extrapolating noise.
MAX_EXTRAPOLATION = 1.0
#: Condition number above which a coupled fit is treated as singular.
MAX_CONDITION = 1e8
#: File the solved schema is written to, beside the data.
SOLVED_SPEC = "schema.solved.json"
#: Consecutive widening iterations that, ending further off than the first
#: iteration, stop a run as diverging.
DIVERGING_RUN = 3

_SANDBOX = {"enable_external_access": False, "lock_configuration": True}


class SolveError(ValueError):
    """The solve request cannot run as written: a lever, target or setting is wrong."""


class PipelineError(RuntimeError):
    """The pipeline failed, or returned output that cannot be read as a metric."""


# --------------------------------------------------------------------------- #
# Targets and runners
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Target:
    """A metric the pipeline must produce, and the outcome curve that moves it.

    Attributes:
        metric: Name of a metric the runner returns.
        lever: ``table.column`` of an outcome curve with exact targets. Only
            this curve's values change while solving for the metric.
        values: Target value per period. A period is any date inside the
            curve period it names: ``"2025-03"``, ``"2025-03-01"`` or a
            ``date`` all name March 2025 on a monthly curve.
        direction: ``"direct"`` when a larger lever magnitude raises the
            metric, ``"inverse"`` when it lowers it (a discount, a refund, a
            deductible loss).
    """

    metric: str
    lever: str
    values: Mapping[Any, float]
    direction: str = "direct"

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Target":
        unknown = set(raw) - {"metric", "lever", "values", "direction"}
        if unknown:
            raise SolveError(f"unknown target field(s): {', '.join(sorted(unknown))}")
        missing = [k for k in ("metric", "lever", "values") if k not in raw]
        if missing:
            raise SolveError(f"a target needs {', '.join(missing)}")
        if not isinstance(raw["values"], Mapping):
            raise SolveError(f"target {raw['metric']!r}: values must map period to value")
        return cls(metric=str(raw["metric"]), lever=str(raw["lever"]),
                   values=dict(raw["values"]), direction=str(raw.get("direction", "direct")))


@runtime_checkable
class Runner(Protocol):
    """Runs a pipeline over generated tables and returns its metrics."""

    def run(self, tables: Mapping[str, pd.DataFrame]) -> Mapping[str, Any]:
        """Each metric's values by period.

        A metric's value may be a mapping of period to number, a Series
        indexed by period, or a two-column DataFrame of period and number.
        """
        ...

    def identity(self) -> Dict[str, str]:
        """What ran, as ``kind``, ``name`` and a ``digest`` of its definition."""
        ...


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class PythonRunner:
    """A Python callable as the pipeline: ``fn(tables) -> {metric: values}``."""

    def __init__(self, fn: Callable[[Mapping[str, pd.DataFrame]], Mapping[str, Any]],
                 name: Optional[str] = None) -> None:
        self.fn = fn
        self.name: str = name or str(getattr(fn, "__qualname__", type(fn).__name__))

    def run(self, tables: Mapping[str, pd.DataFrame]) -> Mapping[str, Any]:
        return self.fn(tables)

    def identity(self) -> Dict[str, str]:
        try:
            source = inspect.getsource(self.fn).encode("utf-8")
        except (OSError, TypeError):
            source = self.name.encode("utf-8")
        return {"kind": "python", "name": self.name, "digest": _digest(source)}


def _metric_sql(sql: str) -> str:
    """``sql`` as a subquery yielding ``(period DATE, value DOUBLE)``.

    Being a subquery, it can hold exactly one SELECT: a second statement is
    a syntax error rather than something that runs.
    """
    body = sql.strip().rstrip(";").strip()
    if not body:
        raise SolveError("a metric query is empty")
    return f"SELECT CAST(p AS DATE), CAST(v AS DOUBLE) FROM ({body}) AS q(p, v)"


class _Interrupt:
    """Interrupts a DuckDB query that outlives its time limit."""

    def __init__(self, con: Any, seconds: Optional[float]) -> None:
        self._con = con
        self._timer = threading.Timer(seconds, self._fire) if seconds else None
        self.fired = False

    def _fire(self) -> None:
        self.fired = True
        self._con.interrupt()

    def __enter__(self) -> "_Interrupt":
        if self._timer is not None:
            self._timer.daemon = True
            self._timer.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._timer is not None:
            self._timer.cancel()


def _run_metric_queries(con: Any, queries: Mapping[str, str],
                        timeout: Optional[float]) -> Dict[str, List[Tuple[Any, float]]]:
    out: Dict[str, List[Tuple[Any, float]]] = {}
    for metric, sql in queries.items():
        with _Interrupt(con, timeout) as guard:
            try:
                out[metric] = [tuple(row) for row in con.execute(_metric_sql(sql)).fetchall()]
            except Exception as exc:  # noqa: BLE001 - every engine error is the pipeline's
                text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
                if guard.fired:
                    text = f"stopped after {timeout:g}s"
                raise PipelineError(f"metric {metric!r}: {text}") from exc
    return out


class SQLRunner:
    """DuckDB queries over the generated tables, one per metric.

    Each query returns two columns, the period and the value, one row per
    period. Queries run in a sandbox: the generated tables are readable, and
    files, extensions, ``ATTACH`` and configuration changes are refused.

    Because the queries read only the generated tables, a solved target can
    be re-checked against the written files, so :meth:`SolveResult.write`
    adds each one to the attestation as a ``within_tolerance`` invariant.
    """

    def __init__(self, queries: Mapping[str, str], *, timeout: Optional[float] = 60.0,
                 memory_limit: Optional[str] = None) -> None:
        if not queries:
            raise SolveError("SQLRunner needs at least one metric query")
        for metric, sql in queries.items():
            _metric_sql(sql)
            if not isinstance(metric, str) or not metric:
                raise SolveError("metric names must be non-empty strings")
        self.queries = dict(queries)
        self.timeout = timeout
        self.memory_limit = memory_limit

    def _connect(self) -> Any:
        import duckdb

        config: Dict[str, Any] = {}
        if self.memory_limit:
            config["memory_limit"] = self.memory_limit
        config.update(_SANDBOX)
        return duckdb.connect(config=config)

    def run(self, tables: Mapping[str, pd.DataFrame]) -> Mapping[str, Any]:
        con = self._connect()
        try:
            for name, frame in tables.items():
                con.register(name, frame)
            return _run_metric_queries(con, self.queries, self.timeout)
        finally:
            con.close()

    def identity(self) -> Dict[str, str]:
        return {"kind": "sql", "name": ", ".join(sorted(self.queries)),
                "digest": _digest(_canonical(self.queries))}

    def invariant_sql(self, metric: str, start: pd.Timestamp, end: pd.Timestamp) -> str:
        """The metric's value for the one period starting at ``start``."""
        return (f"SELECT v FROM ({_metric_sql(self.queries[metric])}) AS m(p, v) "
                f"WHERE p >= DATE '{start.date().isoformat()}' "
                f"AND p < DATE '{end.date().isoformat()}'")


_ANSI = re.compile(r"\x1b\[[0-9;]*m")

#: Folders inside a dbt project that hold build output, not definitions.
_DBT_BUILD_DIRS = {"target", "logs", ".git", "__pycache__", ".venv", "venv"}


class DbtDuckDBRunner:
    """A dbt project run on a temporary DuckDB warehouse.

    The generated tables are loaded into ``source_schema`` of a fresh
    database, ``dbt run`` builds the selected models with a generated
    ``profiles.yml`` (the project's own profile name, adapter ``duckdb``),
    and each metric query then reads the built models. The project folder
    is never written to: build output goes to the temporary directory.

    Needs ``dbt-duckdb`` and, when the project uses packages, a prior
    ``dbt deps``.
    """

    def __init__(self, project_dir: Union[str, Path], metrics: Mapping[str, str], *,
                 select: Optional[str] = None, source_schema: str = "main",
                 dbt: str = "dbt", timeout: float = 900.0,
                 query_timeout: Optional[float] = 60.0) -> None:
        self.project_dir = Path(project_dir).expanduser().resolve()
        project_file = self.project_dir / "dbt_project.yml"
        if not project_file.is_file():
            raise SolveError(f"no dbt_project.yml in {self.project_dir}")
        if not metrics:
            raise SolveError("DbtDuckDBRunner needs at least one metric query")
        for sql in metrics.values():
            _metric_sql(sql)
        import yaml

        project = yaml.safe_load(project_file.read_text(encoding="utf-8")) or {}
        self.profile = str(project.get("profile") or project.get("name") or "misata")
        self.metrics = dict(metrics)
        self.select = select
        self.source_schema = source_schema
        self.dbt = dbt
        self.timeout = timeout
        self.query_timeout = query_timeout

    def _executable(self) -> str:
        """``dbt`` on PATH, else beside the running interpreter, where pip puts it."""
        found = shutil.which(self.dbt) or shutil.which(self.dbt, path=str(Path(sys.executable).parent))
        if found is None:
            raise PipelineError(f"{self.dbt!r} is not on PATH; pip install dbt-duckdb")
        return found

    def run(self, tables: Mapping[str, pd.DataFrame]) -> Mapping[str, Any]:
        import duckdb
        import yaml

        from misata.sqlutil import quote_ident

        executable = self._executable()
        with tempfile.TemporaryDirectory(prefix="misata-dbt-") as tmp:
            root = Path(tmp)
            warehouse = root / "warehouse.duckdb"
            with duckdb.connect(str(warehouse)) as con:
                schema = quote_ident(self.source_schema)
                con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
                for name, frame in tables.items():
                    con.register("misata_source", frame)
                    con.execute(f"CREATE TABLE {schema}.{quote_ident(name)} AS "
                                f"SELECT * FROM misata_source")
                    con.unregister("misata_source")
            profile = {self.profile: {"target": "misata", "outputs": {"misata": {
                "type": "duckdb", "path": str(warehouse), "schema": self.source_schema,
                "threads": 1}}}}
            (root / "profiles.yml").write_text(yaml.safe_dump(profile), encoding="utf-8")
            command = [executable, "run", "--project-dir", str(self.project_dir),
                       "--profiles-dir", str(root), "--target-path", str(root / "target"),
                       "--log-path", str(root / "logs")]
            if self.select:
                command += ["--select", self.select]
            env = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
                   "DBT_USE_COLORS": "false"}
            try:
                done = subprocess.run(  # noqa: S603 - argument list, no shell; dbt resolved on PATH
                    command, capture_output=True, text=True, env=env, timeout=self.timeout,
                    check=False)
            except subprocess.TimeoutExpired as exc:
                raise PipelineError(f"dbt run did not finish in {self.timeout:g}s") from exc
            if done.returncode != 0:
                log = _ANSI.sub("", done.stdout + done.stderr).strip()
                tail = "\n".join(log.splitlines()[-12:])
                raise PipelineError(f"dbt run failed (exit {done.returncode}):\n{tail}")
            with duckdb.connect(str(warehouse), read_only=True) as con:
                return _run_metric_queries(con, self.metrics, self.query_timeout)

    def identity(self) -> Dict[str, str]:
        digest = hashlib.sha256()
        for path in sorted(self.project_dir.rglob("*")):
            relative = path.relative_to(self.project_dir)
            if not path.is_file() or _DBT_BUILD_DIRS & set(relative.parts):
                continue
            digest.update(relative.as_posix().encode("utf-8") + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(_canonical({"metrics": self.metrics, "select": self.select,
                                  "source_schema": self.source_schema}))
        return {"kind": "dbt-duckdb", "name": self.project_dir.name,
                "digest": "sha256:" + digest.hexdigest()}


# --------------------------------------------------------------------------- #
# Levers
# --------------------------------------------------------------------------- #


def _timestamp(period: Any) -> pd.Timestamp:
    if isinstance(period, (int, float, np.integer, np.floating)) and not isinstance(period, bool):
        raise SolveError(f"period {period!r} is a number; name periods by date, such as "
                         f"2025-03, because a month number means nothing without a year")
    if isinstance(period, pd.Period):
        return period.start_time
    try:
        stamp = pd.Timestamp(period)
    except (TypeError, ValueError) as exc:
        raise SolveError(f"{period!r} is not a date or period") from exc
    if pd.isna(stamp):
        raise SolveError(f"{period!r} is not a date or period")
    return stamp.tz_localize(None) if stamp.tzinfo is not None else stamp


@dataclass
class _Lever:
    """One outcome curve the solver may move, as explicit per-period points."""

    name: str
    curve: "OutcomeCurve"
    starts: List[pd.Timestamp]
    ends: List[pd.Timestamp]
    values: np.ndarray
    integral: bool
    decimals: int

    def bucket(self, period: Any) -> Optional[int]:
        stamp = _timestamp(period)
        for i, (start, end) in enumerate(zip(self.starts, self.ends, strict=True)):
            if start <= stamp < end:
                return i
        return None

    def label(self, index: int) -> str:
        start = self.starts[index]
        return str(start.strftime("%Y-%m" if self.curve.time_unit == "month" else "%Y-%m-%d"))

    def round(self, value: float) -> float:
        return float(round(value)) if self.integral else round(float(value), self.decimals)

    def write_points(self) -> None:
        """Make the curve declare one explicit point per period."""
        self.curve.curve_points = [
            {"date": start.strftime("%Y-%m-%d"),
             "target_value": int(v) if self.integral else float(v)}
            for start, v in zip(self.starts, self.values, strict=True)]


def _levers(schema: "SchemaConfig", targets: Sequence[Target]) -> Dict[str, _Lever]:
    from misata.engines import FactEngine

    engine = FactEngine()
    curves = list(getattr(schema, "outcome_curves", None) or [])
    out: Dict[str, _Lever] = {}
    for target in targets:
        if target.lever in out:
            raise SolveError(f"two targets move {target.lever}; give each lever one metric")
        table, _, column = target.lever.partition(".")
        matches = [c for c in curves if c.table == table and c.column == column]
        if not matches:
            raise SolveError(f"no outcome curve on {target.lever} to use as a lever; declare one "
                             f"with exact per-period values")
        if len(matches) > 1:
            raise SolveError(f"{target.lever} has {len(matches)} outcome curves; a lever must "
                             f"name exactly one")
        curve = matches[0]
        if not engine.curve_has_exact_targets(curve):
            raise SolveError(f"the curve on {target.lever} is relative; a lever needs exact "
                             f"per-period values (value_mode: absolute)")
        columns = schema.get_columns(curve.table) or []
        resolved = engine._resolve_curve(curve, columns)
        column_cfg = next((c for c in columns if c.name == curve.column), None)
        integral = curve.value_mode == "count" or getattr(column_cfg, "type", "") == "int"
        lever = _Lever(
            name=target.lever, curve=curve,
            starts=[b.start for b in resolved.buckets], ends=[b.end for b in resolved.buckets],
            values=np.asarray(resolved.targets, dtype=float), integral=integral,
            decimals=engine._column_decimals(column_cfg))
        lever.write_points()
        out[target.lever] = lever
    return out


@dataclass
class _Plan:
    """One target resolved against its lever: which periods, aimed where."""

    target: Target
    lever: _Lever
    periods: List[int]
    goals: np.ndarray
    expected: List[str]


def _plans(targets: Sequence[Target], levers: Mapping[str, _Lever]) -> List[_Plan]:
    plans = []
    for target in targets:
        if target.direction not in DIRECTIONS:
            raise SolveError(f"target {target.metric!r}: direction must be one of "
                             f"{', '.join(DIRECTIONS)}, not {target.direction!r}")
        if not target.values:
            raise SolveError(f"target {target.metric!r} names no periods")
        lever = levers[target.lever]
        chosen: Dict[int, float] = {}
        for period, value in target.values.items():
            index = lever.bucket(period)
            if index is None:
                raise SolveError(
                    f"target {target.metric!r}: {period} is outside the {target.lever} curve "
                    f"({lever.label(0)} to {lever.label(len(lever.starts) - 1)})")
            if index in chosen:
                raise SolveError(f"target {target.metric!r}: two values for period "
                                 f"{lever.label(index)}")
            number = float(value)
            if not math.isfinite(number) or number == 0:
                raise SolveError(
                    f"target {target.metric!r} for {lever.label(index)} is {value}; a target "
                    f"must be a finite non-zero number, because a relative tolerance of zero "
                    f"can only be met exactly")
            if format_value(Decimal(repr(number)), "decimal", "0.00") in ("0.00", "-0.00"):
                raise SolveError(f"target {target.metric!r} for {lever.label(index)} is {value}; "
                                 f"targets are compared at two decimal places")
            chosen[index] = number
        periods = sorted(chosen)
        goals = np.array([chosen[i] for i in periods])
        expected = [format_value(Decimal(repr(float(g))), "decimal", "0.00") for g in goals]
        plans.append(_Plan(target, lever, periods, goals, expected))
    return plans


# --------------------------------------------------------------------------- #
# Measuring
# --------------------------------------------------------------------------- #


def _pairs(metric: str, raw: Any) -> List[Tuple[Any, float]]:
    if isinstance(raw, pd.DataFrame):
        if raw.shape[1] != 2:
            raise PipelineError(f"metric {metric!r}: a DataFrame must have two columns, "
                                f"period and value; it has {raw.shape[1]}")
        return list(raw.itertuples(index=False, name=None))
    if isinstance(raw, pd.Series):
        return list(raw.items())
    if isinstance(raw, Mapping):
        return list(raw.items())
    if isinstance(raw, (list, tuple)):
        return [tuple(row) for row in raw]  # type: ignore[misc]
    raise PipelineError(f"metric {metric!r}: expected period values, got {type(raw).__name__}")


def _measure(plan: _Plan, output: Mapping[str, Any]) -> np.ndarray:
    """The metric's value in each targeted period; a period with no row is 0."""
    metric = plan.target.metric
    if metric not in output:
        raise PipelineError(f"the pipeline returned no metric {metric!r}; it returned "
                            f"{', '.join(map(repr, output)) or 'nothing'}")
    position = {index: k for k, index in enumerate(plan.periods)}
    measured = np.zeros(len(plan.periods))
    found = np.zeros(len(plan.periods), dtype=bool)
    returned = []
    for pair in _pairs(metric, output[metric]):
        if len(pair) != 2:
            raise PipelineError(f"metric {metric!r}: each row must be (period, value)")
        period, value = pair
        returned.append(str(period))
        try:
            index = plan.lever.bucket(period)
        except SolveError as exc:
            raise PipelineError(f"metric {metric!r}: {exc}") from exc
        k = position.get(index) if index is not None else None
        if index is None or k is None:
            continue
        if found[k]:
            raise PipelineError(f"metric {metric!r} returned more than one value for "
                                f"{plan.lever.label(index)}; aggregate it to one per period")
        number = float("nan") if value is None else float(value)
        if not math.isfinite(number):
            raise PipelineError(f"metric {metric!r} is {value} for {plan.lever.label(index)}")
        measured[k], found[k] = number, True
    if not found.any():
        shown = ", ".join(returned[:6]) + (" ..." if len(returned) > 6 else "")
        raise PipelineError(f"metric {metric!r} has no value in any targeted period; it "
                            f"returned periods {shown or 'none'}")
    return measured


def _relative_gaps(measured: np.ndarray, goals: np.ndarray) -> np.ndarray:
    gaps: np.ndarray = np.abs(measured - goals) / np.abs(goals)
    return gaps


def _within(measured: np.ndarray, plan: _Plan, tolerance: Decimal) -> np.ndarray:
    """Whether each period holds, decided exactly as the attestation verifier decides it."""
    return np.array([
        within_tolerance(format_value(Decimal(repr(float(m))), "decimal", e), e, _fixed(tolerance))
        for m, e in zip(measured, plan.expected, strict=True)])


# --------------------------------------------------------------------------- #
# Stepping
# --------------------------------------------------------------------------- #


def _ratio_step(value: float, measured: float, goal: float, direction: str,
                damping: float, seed: float) -> float:
    rise = goal > measured
    grow = rise if direction == "direct" else not rise
    ratio = goal / measured if abs(measured) > 1e-12 else 0.0
    if ratio > 0:
        scale = (ratio if direction == "direct" else 1.0 / ratio) ** damping
    else:
        scale = NUDGE if grow else 1.0 / NUDGE
    scale = min(max(scale, 1.0 / MAX_STEP), MAX_STEP)
    if value == 0:
        return seed if grow else 0.0
    return float(value * scale)


def _coupled_step(history: Sequence[Tuple[np.ndarray, np.ndarray]],
                  goals: np.ndarray, signs: np.ndarray) -> Optional[np.ndarray]:
    """The fed-in values a fitted ``measured = A @ fed + b`` says hit ``goals``."""
    n = len(goals)
    distinct: Dict[bytes, Tuple[np.ndarray, np.ndarray]] = {}
    for fed, measured in history:
        distinct[fed.tobytes()] = (fed, measured)
    samples = list(distinct.values())[-(2 * n + 2):]
    if n < 2 or len(samples) < n + 1:
        return None
    fed = np.array([s[0] for s in samples])
    measured = np.array([s[1] for s in samples])
    design = np.column_stack([fed, np.ones(len(samples))])
    coef, _, rank, _ = np.linalg.lstsq(design, measured, rcond=None)
    if rank < n + 1:
        return None
    transfer, offset = coef[:n].T, coef[n]
    with np.errstate(all="ignore"):
        if not np.isfinite(np.linalg.cond(transfer)) or np.linalg.cond(transfer) > MAX_CONDITION:
            return None
        try:
            solved = np.linalg.solve(transfer, goals - offset)
        except np.linalg.LinAlgError:
            return None
    if not np.all(np.isfinite(solved)):
        return None
    if np.any(solved * signs < 0):
        return None
    low, high = fed.min(axis=0), fed.max(axis=0)
    reach = MAX_EXTRAPOLATION * (high - low)
    if np.any(solved < low - reach) or np.any(solved > high + reach):
        return None
    return solved


def _secant_step(history: Sequence[Tuple[np.ndarray, np.ndarray]], k: int, goal: float,
                 slope_sign: float) -> Optional[float]:
    """The value a line through period ``k``'s last two observations says hits ``goal``.

    Used only when the line slopes the way the lever's direction says it
    must, so noise can never turn the step around.
    """
    latest_fed, latest_out = history[-1][0][k], history[-1][1][k]
    for fed, out in reversed(history[:-1]):
        if fed[k] != latest_fed:
            slope = (latest_out - out[k]) / (latest_fed - fed[k])
            if not math.isfinite(slope) or slope * slope_sign <= 0:
                return None
            return float(latest_fed + (goal - latest_out) / slope)
    return None


def _bounded(old: float, new: float, sign: float) -> float:
    if new * sign < 0:
        new = 0.0
    if old != 0 and abs(new) > MAX_STEP * abs(old):
        new = math.copysign(MAX_STEP * abs(old), new)
    return float(np.clip(new, -MAX_MAGNITUDE, MAX_MAGNITUDE))


def _signs(lever: _Lever) -> np.ndarray:
    nonzero = lever.values[lever.values != 0]
    default = 1.0 if nonzero.size == 0 else float(np.sign(np.median(nonzero)))
    return np.where(lever.values != 0, np.sign(lever.values), default)


def _seed(lever: _Lever) -> float:
    """Magnitude a zero-valued period restarts from: the curve's typical value."""
    nonzero = np.abs(lever.values[lever.values != 0])
    magnitude = lever.round(float(nonzero.mean())) if nonzero.size else 0.0
    return magnitude or (1.0 if lever.integral else 0.01)


def _advance(plan: _Plan, measured: np.ndarray, held: np.ndarray, damping: float,
             history: Sequence[Tuple[np.ndarray, np.ndarray]]) -> str:
    lever = plan.lever
    signs = _signs(lever)[plan.periods]
    fed = lever.values[plan.periods]
    solved = _coupled_step(history, plan.goals, signs)
    seed = _seed(lever)
    toward = 1.0 if plan.target.direction == "direct" else -1.0
    methods = set()
    for k, index in enumerate(plan.periods):
        if held[k]:
            continue
        old = fed[k]
        aim = solved[k] if solved is not None else _secant_step(
            history, k, plan.goals[k], toward * signs[k])
        if aim is not None:
            new = old + damping * (aim - old)
            methods.add("coupled" if solved is not None else "secant")
        else:
            new = _ratio_step(old, measured[k], plan.goals[k], plan.target.direction,
                              damping, seed * signs[k])
            methods.add("ratio")
        lever.values[index] = lever.round(_bounded(old, new, signs[k]))
    lever.write_points()
    return "+".join(sorted(methods))


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


@dataclass
class SolveStep:
    """One iteration: what was fed in, what came out, and how far off it was."""

    iteration: int
    max_gap: float
    fed: Dict[str, Dict[str, float]]
    measured: Dict[str, Dict[str, float]]
    gaps: Dict[str, Dict[str, float]]
    method: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"iteration": self.iteration, "max_gap": _json_number(self.max_gap),
                "fed": self.fed, "measured": self.measured,
                "gaps": {m: {p: _json_number(g) for p, g in v.items()}
                         for m, v in self.gaps.items()},
                "method": self.method}


def _json_number(value: float) -> Optional[float]:
    return float(value) if math.isfinite(value) else None


@dataclass
class SolveResult:
    """The outcome of :func:`solve`.

    ``schema`` and ``tables`` are those of the best iteration (the smallest
    largest gap), which is the last one when the run converged.
    """

    converged: bool
    reason: str
    message: str
    tolerance: Decimal
    targets: List[Target]
    steps: List[SolveStep]
    runner: Dict[str, str]
    schema: Optional["SchemaConfig"] = None
    tables: Optional[Dict[str, pd.DataFrame]] = None
    best_iteration: Optional[int] = None
    conflicts: List["Conflict"] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    pipeline: Optional[Runner] = field(default=None, repr=False, compare=False)

    @property
    def iterations(self) -> int:
        return len(self.steps)

    @property
    def best(self) -> Optional[SolveStep]:
        if self.best_iteration is None:
            return None
        return self.steps[self.best_iteration - 1]

    def levers(self) -> Dict[str, List[Dict[str, Any]]]:
        """The solved curve points of every lever."""
        if self.schema is None:
            return {}
        out = {}
        for target in self.targets:
            table, _, column = target.lever.partition(".")
            curve = next(c for c in self.schema.outcome_curves
                         if c.table == table and c.column == column)
            out[target.lever] = list(curve.curve_points)
        return out

    def summary(self) -> str:
        done = (f"after {self.iterations} iteration(s)" if self.steps
                 else "before any iteration completed")
        lines = [f"solve: {self.reason} {done} in {self.elapsed_seconds:.1f}s "
                 f"(tolerance {_percent(self.tolerance)})"]
        best = self.best
        if best is not None:
            for metric, gaps in best.gaps.items():
                worst = max(gaps.values()) if gaps else 0.0
                lines.append(f"  {metric}: worst period off by {worst:.4%} "
                             f"(iteration {best.iteration})")
        if not self.converged:
            lines.append(f"  {self.message}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        from misata import __version__

        return {
            "converged": self.converged,
            "reason": self.reason,
            "message": self.message,
            "iterations": self.iterations,
            "best_iteration": self.best_iteration,
            "tolerance": _fixed(self.tolerance),
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "runner": self.runner,
            "targets": [{"metric": t.metric, "lever": t.lever, "direction": t.direction,
                         "values": {str(k): v for k, v in t.values.items()}}
                        for t in self.targets],
            "levers": self.levers(),
            "steps": [s.to_dict() for s in self.steps],
            "conflicts": [{"kind": c.kind, "where": c.where, "declarations": c.declarations,
                           "arithmetic": c.arithmetic, "remedy": c.remedy}
                          for c in self.conflicts],
            "misata_version": __version__,
        }

    def invariants(self) -> List["Invariant"]:
        """Each solved period as a check the attestation verifier can rerun.

        Only queries that read the generated tables alone can be rerun
        against the written files, so only a :class:`SQLRunner` yields any.
        """
        from misata.attestation import Invariant

        runner = self.pipeline
        if not isinstance(runner, SQLRunner) or self.schema is None:
            return []
        levers = _levers(self.schema.model_copy(deep=True), self.targets)
        out = []
        for plan in _plans(self.targets, levers):
            for index, expected in zip(plan.periods, plan.expected, strict=True):
                out.append(Invariant(
                    id=f"{plan.target.metric}.{plan.lever.label(index)}.solved",
                    kind="solved_target",
                    sql=runner.invariant_sql(plan.target.metric, plan.lever.starts[index],
                                             plan.lever.ends[index]),
                    expected=expected, value_type="decimal", comparator="within_tolerance",
                    tolerance=_fixed(self.tolerance)))
        return out

    def write(self, directory: Union[str, Path], *, fmt: str = "csv",
              source_yaml: Optional[Union[str, Path]] = None) -> Path:
        """Write the closest dataset, the solved spec and the trajectory.

        Writes the tables in ``fmt``, ``schema.solved.json`` (loads with
        ``misata generate -c``), ``solve.json`` (this result), and, given the
        YAML the schema came from, ``<name>.solved.yaml``: that file with only
        the lever curves' points replaced.

        Returns:
            The path of ``schema.solved.json``.
        """
        if self.schema is None or self.tables is None:
            raise SolveError(f"nothing to write: the run stopped as {self.reason} before "
                             f"any dataset was generated")
        from misata.sinks import open_sink

        root = Path(directory)
        with open_sink(fmt, root, self.schema) as sink:
            for table in self.schema.tables:
                if table.name in self.tables:
                    sink.write(table.name, self.tables[table.name])
        spec = root / SOLVED_SPEC
        spec.write_text(json.dumps(self.schema.model_dump(mode="json"), indent=2,
                                   sort_keys=True) + "\n", encoding="utf-8")
        if source_yaml is not None:
            self._write_solved_yaml(Path(source_yaml), root)
        (root / "solve.json").write_text(json.dumps(self.to_dict(), indent=2) + "\n",
                                         encoding="utf-8")
        return spec

    def attest(self, directory: Union[str, Path]) -> "Attestation":
        """Attest a folder :meth:`write` filled, against the solved spec.

        Every declaration of the solved spec is checked, and a
        :class:`SQLRunner`'s solved periods are added as ``within_tolerance``
        invariants that ``verify.py`` reruns.
        """
        from misata.attestation import attest as attest_dataset

        if self.schema is None:
            raise SolveError(f"nothing to attest: the run stopped as {self.reason}")
        root = Path(directory)
        return attest_dataset(root, self.schema, spec_path=root / SOLVED_SPEC,
                              extra_invariants=self.invariants())

    def _write_solved_yaml(self, source: Path, root: Path) -> None:
        import yaml

        document = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        curves = document.get("outcome_curves") or []
        for lever, points in self.levers().items():
            table, _, column = lever.partition(".")
            for curve in curves:
                if curve.get("table") == table and curve.get("column") == column:
                    curve["curve_points"] = points
        out = root / f"{source.stem}.solved.yaml"
        out.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                       encoding="utf-8")


@dataclass
class SolveConfig:
    """A solve described in a file: what to generate, what runs it, what to hit."""

    schema: "SchemaConfig"
    runner: Runner
    targets: List[Target]
    tolerance: Decimal
    max_iterations: int = 25
    max_seconds: Optional[float] = None
    damping: float = 0.85
    schema_path: Optional[Path] = None

    def run(self) -> SolveResult:
        return solve(self.schema, self.runner, self.targets, tolerance=self.tolerance,
                     max_iterations=self.max_iterations, max_seconds=self.max_seconds,
                     damping=self.damping)


_CONFIG_KEYS = {"schema", "seed", "tolerance", "max_iterations", "max_seconds", "damping",
                "pipeline", "targets"}


def runner_from_dict(pipeline: Mapping[str, Any], base: Path = Path(".")) -> Runner:
    """A runner from ``{"sql": {metric: query}}`` or ``{"dbt": {...}}``.

    ``base`` resolves a relative dbt ``project_dir``.
    """
    if not isinstance(pipeline, Mapping) or len(pipeline) != 1:
        raise SolveError("pipeline must have exactly one of: sql, dbt")
    (kind, spec), = pipeline.items()
    if kind == "sql":
        if not isinstance(spec, Mapping):
            raise SolveError("pipeline.sql must map each metric to its query")
        return SQLRunner({str(k): str(v) for k, v in spec.items()})
    if kind == "dbt":
        if not isinstance(spec, Mapping) or "project_dir" not in spec or "metrics" not in spec:
            raise SolveError("pipeline.dbt needs project_dir and metrics")
        allowed = {"project_dir", "metrics", "select", "source_schema", "timeout"}
        unknown = set(spec) - allowed
        if unknown:
            raise SolveError(f"unknown pipeline.dbt field(s): {', '.join(sorted(unknown))}")
        options = {k: spec[k] for k in ("select", "source_schema", "timeout") if k in spec}
        return DbtDuckDBRunner(base / str(spec["project_dir"]),
                               {str(k): str(v) for k, v in spec["metrics"].items()}, **options)
    raise SolveError(f"unknown pipeline {kind!r}; use sql or dbt")


def load_config(path: Union[str, Path]) -> SolveConfig:
    """Read a ``solve.yaml``.

    Example::

        schema: misata.yaml          # relative to this file
        tolerance: 0.5%
        max_iterations: 25
        pipeline:
          sql:
            net_revenue: |
              SELECT date_trunc('month', ordered_at), SUM(amount) * 0.97
              FROM orders GROUP BY 1
        targets:
          - metric: net_revenue
            lever: orders.amount
            values: {2025-01: 70000, 2025-02: 65000}
    """
    import yaml

    from misata.yaml_schema import load_schema_file

    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise SolveError(f"{config_path} is not a solve config: expected a mapping")
    unknown = set(raw) - _CONFIG_KEYS
    if unknown:
        raise SolveError(f"unknown field(s) in {config_path.name}: {', '.join(sorted(unknown))}")
    for key in ("schema", "pipeline", "targets"):
        if key not in raw:
            raise SolveError(f"{config_path.name} needs {key}")
    base = config_path.parent
    schema_path = base / str(raw["schema"])
    if not schema_path.is_file():
        raise SolveError(f"schema file {schema_path} does not exist")
    seed = raw.get("seed")
    try:
        schema = load_schema_file(schema_path, seed=None if seed is None else int(seed))
    except (ValueError, TypeError) as exc:
        raise SolveError(f"schema {schema_path.name} could not be read: {exc}") from exc
    if not isinstance(raw["targets"], list):
        raise SolveError("targets must be a list")
    return SolveConfig(
        schema=schema,
        runner=runner_from_dict(raw["pipeline"], base),
        targets=[Target.from_dict(t) for t in raw["targets"]],
        tolerance=parse_tolerance(raw.get("tolerance", "1%")),
        max_iterations=int(raw.get("max_iterations", 25)),
        max_seconds=None if raw.get("max_seconds") is None else float(raw["max_seconds"]),
        damping=float(raw.get("damping", 0.85)),
        schema_path=schema_path,
    )


def _percent(tolerance: Decimal) -> str:
    return f"{(tolerance * 100).normalize():f}%"


def _fixed(value: Decimal) -> str:
    """``value`` in plain decimal notation, never ``1E-7``."""
    return format(value.normalize(), "f")


def parse_tolerance(value: Union[str, float, Decimal]) -> Decimal:
    """``"0.5%"``, ``0.005`` or ``Decimal("0.005")`` as a relative tolerance."""
    text = str(value).strip()
    try:
        tolerance = (Decimal(text[:-1].strip()) / 100 if text.endswith("%")
                     else Decimal(text))
    except InvalidOperation as exc:
        raise SolveError(f"tolerance {value!r} is not a number or a percentage") from exc
    if not 0 < tolerance < 1:
        raise SolveError(f"tolerance must be above 0 and below 100%, not {value!r}")
    return tolerance.normalize()


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #


def _unresponsive(plans: Sequence[_Plan], measured: Mapping[str, np.ndarray],
                  history: Mapping[str, Sequence[Tuple[np.ndarray, np.ndarray]]]) -> Optional[str]:
    """Why a metric is not worth solving for: its lever moved and it did not."""
    for plan in plans:
        past = history[plan.lever.name]
        if not past:
            continue
        before_fed, before_out = past[-1]
        now_fed, now_out = plan.lever.values[plan.periods], measured[plan.target.metric]
        moved = np.abs(now_fed - before_fed) / np.maximum(np.abs(before_fed), 1e-12)
        if moved.max() > 0.01 and np.array_equal(now_out, before_out):
            return (f"{plan.target.metric} did not change when {plan.lever.name} moved by up "
                    f"to {moved.max():.0%}; the metric may not read that column, or may group "
                    f"by a different date than the curve's {plan.lever.curve.time_column}")
    return None


def _snapshot(plans: Sequence[_Plan], measured: Mapping[str, np.ndarray],
              gaps: Mapping[str, np.ndarray]) -> Tuple[Dict, Dict, Dict]:
    fed, out, off = {}, {}, {}
    for plan in plans:
        labels = [plan.lever.label(i) for i in plan.periods]
        fed[plan.lever.name] = {lab: float(plan.lever.values[i])
                                for lab, i in zip(labels, plan.periods, strict=True)}
        out[plan.target.metric] = {lab: float(v) for lab, v in
                                   zip(labels, measured[plan.target.metric], strict=True)}
        off[plan.target.metric] = {lab: float(g) for lab, g in
                                   zip(labels, gaps[plan.target.metric], strict=True)}
    return fed, out, off


def solve(
    schema: Union["SchemaConfig", Mapping[str, Any]],
    runner: Union[Runner, Callable[[Mapping[str, pd.DataFrame]], Mapping[str, Any]]],
    targets: Sequence[Union[Target, Mapping[str, Any]]],
    *,
    tolerance: Union[str, float, Decimal] = "1%",
    max_iterations: int = 25,
    max_seconds: Optional[float] = None,
    damping: float = 0.85,
) -> SolveResult:
    """Move outcome-curve levers until the pipeline's metrics hit their targets.

    Args:
        schema: The schema to generate from. Each target's lever must be one
            of its outcome curves with exact per-period values. The schema's
            seed is used for every iteration.
        runner: The pipeline: a :class:`Runner` (:class:`SQLRunner`,
            :class:`DbtDuckDBRunner`, :class:`PythonRunner`) or a callable
            taking the generated tables.
        targets: What each metric must be, per period, and which lever moves
            it.
        tolerance: Relative tolerance per period, ``"0.5%"`` or ``0.005``.
        max_iterations: Pipeline runs allowed before stopping.
        max_seconds: Wall-clock budget; checked before each iteration.
        damping: Exponent on the ratio step and fraction of the coupled
            step, in (0, 1]. Lower is slower and steadier.

    Returns:
        A :class:`SolveResult`. Failing to converge is a result, not an
        exception: ``reason`` says why, ``steps`` holds the trajectory.

    Raises:
        SolveError: a lever, target or setting cannot work as written.
    """
    from misata.compat import from_dict_schema
    from misata.schema import SchemaConfig

    _check_settings(max_iterations, max_seconds, damping)
    goals = [t if isinstance(t, Target) else Target.from_dict(t) for t in targets]
    if not goals:
        raise SolveError("solve needs at least one target")
    working = (schema.model_copy(deep=True) if isinstance(schema, SchemaConfig)
               else from_dict_schema(dict(schema)))
    solver = _Solver(
        working=working, goals=goals, plans=_plans(goals, _levers(working, goals)),
        pipeline=runner if isinstance(runner, Runner) else PythonRunner(runner),
        tolerance=parse_tolerance(tolerance), damping=damping)

    for iteration in range(1, max_iterations + 1):
        if max_seconds is not None and solver.elapsed() > max_seconds:
            return solver.finish("max_seconds",
                                 f"stopped after {max_seconds:g}s without converging")
        stop = solver.iterate(iteration)
        if stop is not None:
            return stop
        if iteration < max_iterations:
            solver.advance()
    assert solver.best is not None
    return solver.finish("max_iterations", f"{max_iterations} iteration(s) without every "
                         f"period within {_percent(solver.tolerance)}; the closest was off "
                         f"by {solver.best[0]:.2%}")


def _check_settings(max_iterations: int, max_seconds: Optional[float], damping: float) -> None:
    if max_iterations < 1:
        raise SolveError(f"max_iterations must be at least 1, not {max_iterations}")
    if not 0 < damping <= 1:
        raise SolveError(f"damping must be in (0, 1], not {damping}")
    if max_seconds is not None and max_seconds <= 0:
        raise SolveError(f"max_seconds must be positive, not {max_seconds}")


def _diverging(steps: Sequence[SolveStep]) -> Optional[str]:
    """Why the run is moving away: it widened every recent step, past where it began."""
    recent = [s.max_gap for s in steps[-(DIVERGING_RUN + 1):]]
    if len(recent) <= DIVERGING_RUN or recent[-1] <= steps[0].max_gap:
        return None
    if not all(b > a for a, b in zip(recent, recent[1:], strict=False)):
        return None
    return (f"the largest gap widened {DIVERGING_RUN} iterations in a row, to "
            f"{recent[-1]:.2%}; the lever may move this metric the other way "
            f"(direction: inverse) or not at all")


@dataclass
class _Solver:
    """The state one :func:`solve` call carries from iteration to iteration."""

    working: "SchemaConfig"
    goals: List[Target]
    plans: List[_Plan]
    pipeline: Runner
    tolerance: Decimal
    damping: float
    started: float = field(default_factory=time.monotonic)
    steps: List[SolveStep] = field(default_factory=list)
    history: Dict[str, List[Tuple[np.ndarray, np.ndarray]]] = field(default_factory=dict)
    best: Optional[Tuple[float, int, "SchemaConfig", Dict[str, pd.DataFrame]]] = None
    measured: Dict[str, np.ndarray] = field(default_factory=dict)
    held: Dict[str, np.ndarray] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.identity = self.pipeline.identity()
        self.history = {p.lever.name: [] for p in self.plans}

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def finish(self, reason: str, message: str, conflicts: Sequence[Any] = ()) -> SolveResult:
        result = SolveResult(
            converged=reason == "converged", reason=reason, message=message,
            tolerance=self.tolerance, targets=self.goals, steps=self.steps,
            runner=self.identity, conflicts=list(conflicts), elapsed_seconds=self.elapsed(),
            pipeline=self.pipeline)
        if self.best is not None:
            result.best_iteration, result.schema, result.tables = self.best[1:]
        return result

    def iterate(self, iteration: int) -> Optional[SolveResult]:
        """Generate, run and measure once; a result when the run should stop."""
        import misata
        from misata.exceptions import SchemaError
        from misata.feasibility import InfeasibleSchema

        spec = self.working.model_copy(deep=True)
        try:
            tables = misata.generate_from_schema(self.working.model_copy(deep=True))
        except SchemaError as exc:
            where = ("the schema as declared" if iteration == 1
                     else f"the values iteration {iteration} chose")
            return self.finish("infeasible", f"{where} cannot generate: {exc}",
                               exc.conflicts if isinstance(exc, InfeasibleSchema) else ())
        try:
            output = self.pipeline.run(tables)
            self.measured = {p.target.metric: _measure(p, output) for p in self.plans}
        except PipelineError as exc:
            return self.finish("pipeline_error", str(exc))
        except Exception as exc:  # noqa: BLE001 - a pipeline may raise anything
            return self.finish("pipeline_error", f"{type(exc).__name__}: {exc}")

        gaps = {p.target.metric: _relative_gaps(self.measured[p.target.metric], p.goals)
                for p in self.plans}
        self.held = {p.target.metric: _within(self.measured[p.target.metric], p, self.tolerance)
                     for p in self.plans}
        worst = max(float(g.max()) for g in gaps.values())
        fed, out, off = _snapshot(self.plans, self.measured, gaps)
        self.steps.append(SolveStep(iteration=iteration, max_gap=worst, fed=fed, measured=out,
                                    gaps=off))
        converged = all(h.all() for h in self.held.values())
        if converged or self.best is None or worst < self.best[0]:
            self.best = (worst, iteration, spec, tables)
        if converged:
            return self.finish("converged", f"every period within {_percent(self.tolerance)}")
        away = _diverging(self.steps)
        if away is not None:
            return self.finish("diverging", away)
        idle = _unresponsive(self.plans, self.measured, self.history)
        if idle is not None:
            return self.finish("unresponsive", idle)
        return None

    def advance(self) -> None:
        """Move every lever toward its targets from the latest measurement."""
        step = self.steps[-1]
        for plan in self.plans:
            name, metric = plan.lever.name, plan.target.metric
            self.history[name].append((plan.lever.values[plan.periods].copy(),
                                       self.measured[metric].copy()))
            step.method[name] = _advance(plan, self.measured[metric], self.held[metric],
                                         self.damping, self.history[name])
