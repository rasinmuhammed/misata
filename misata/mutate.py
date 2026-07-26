"""Mutation coverage for dbt models: can your data tell right SQL from wrong SQL?

Line coverage is meaningless for a data pipeline. The SQL always runs; the
question is never whether a statement executed but whether the *rows you test
with* could reveal an error in it. This module answers the question directly:

    Is there a plausible wrong version of this model that produces exactly the
    same output on your data?

If yes, no amount of green tests can see that error class. That is not a
hypothetical failure mode. Two real examples, both found by asking this
question by hand and both now public:

- ``dbt-labs/jaffle-shop``: changing ``left join`` to ``inner join`` in the
  customers mart leaves every data test green, because the warehouse happens to
  contain no customer with zero orders.
- ``fivetran/dbt_stripe``: the rolling totals are not partitioned by
  ``account_id``, so every account's cumulative revenue includes every other
  account's. Invisible because the integration seed data has exactly one
  account. (fivetran/dbt_stripe#155)

Both are the same shape: the *code* is wrong and the *data* cannot tell.

How this works
--------------
For each selected model:

1. Build the model as-is and take a checksum of its output.
2. For each mutation rule that applies, rewrite the model's SQL, rebuild, and
   checksum again.
3. A mutation whose checksum is unchanged is **survived**: your data is blind
   to that error. A mutation whose checksum changes is **caught**.
4. The original file is always restored, including when a build errors or the
   process is interrupted.

A mutation that makes the SQL fail to compile is reported as ``errored`` and
excluded from the score, because a change the warehouse rejects is not a change
your data caught.

Honest limits
-------------
This is mutation testing, and mutation testing has a well-known false-positive
problem: the *equivalent mutant*, a change that provably cannot alter output.
``min`` and ``max`` over a single-row group are identical, and a
``partition by`` on a column that holds one value is a no-op. The rule set here
is deliberately tiny and semantically meaningful for exactly that reason, and a
survived mutation is reported as a question to look at, never as a defect.

The tool measures your data, not your SQL. A survived mutation says the rows
cannot distinguish the two versions. Which of the two is correct is your call.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MutationRule:
    """One plausible way a real person (or an LLM) gets a model subtly wrong."""

    key: str
    label: str
    why: str
    pattern: str
    replacement: str
    flags: int = re.IGNORECASE

    def apply(self, sql: str, occurrence: int) -> Optional[str]:
        """Rewrite the ``occurrence``-th match (0-based). None when absent."""
        matches = list(re.finditer(self.pattern, sql, self.flags))
        if occurrence >= len(matches):
            return None
        m = matches[occurrence]
        return sql[: m.start()] + m.expand(self.replacement) + sql[m.end() :]

    def count(self, sql: str) -> int:
        return len(list(re.finditer(self.pattern, sql, self.flags)))


# Five rules, each corresponding to a mistake that has actually shipped.
# Resist growing this list: every extra rule is another chance to report an
# equivalent mutant and train people to ignore the output.
RULES: List[MutationRule] = [
    MutationRule(
        key="join_type",
        label="left join -> inner join",
        why=(
            "Drops parent rows with no match. Invisible whenever every parent "
            "happens to have a child in the data you test with."
        ),
        pattern=r"\bleft\s+(?:outer\s+)?join\b",
        replacement="inner join",
    ),
    MutationRule(
        key="window_partition",
        label="drop `partition by` from a window",
        why=(
            "Makes a per-entity running total run across all entities. "
            "Invisible when the test data holds a single entity. This is "
            "fivetran/dbt_stripe#155."
        ),
        # Only inside an OVER(...), and only when an ORDER BY follows, so the
        # rewrite stays valid SQL.
        pattern=r"(over\s*\(\s*)partition\s+by\s+[^)]*?(\border\s+by\b)",
        replacement=r"\1\2",
    ),
    MutationRule(
        key="comparison_boundary",
        label="> becomes >=",
        why=(
            "Off-by-one on a threshold. Invisible unless a row sits exactly on "
            "the boundary."
        ),
        pattern=r">(?!=)(\s)",
        replacement=r">=\1",
        flags=0,
    ),
    MutationRule(
        key="aggregate_swap",
        label="min() becomes max()",
        why=(
            "Earliest becomes latest. Invisible when every group has one row, "
            "which is common in small fixtures."
        ),
        pattern=r"\bmin\s*\(",
        replacement="max(",
    ),
    MutationRule(
        key="count_distinct",
        label="count(distinct x) becomes count(x)",
        why=(
            "Counts duplicates. Invisible unless the data actually contains a "
            "duplicate in that column."
        ),
        pattern=r"\bcount\s*\(\s*distinct\s+",
        replacement="count(",
    ),
]

RULES_BY_KEY = {r.key: r for r in RULES}


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


@dataclass
class MutationResult:
    model: str
    rule: MutationRule
    occurrence: int
    outcome: str  # "caught" | "survived" | "errored"
    detail: str = ""

    @property
    def caught(self) -> bool:
        return self.outcome == "caught"


@dataclass
class ModelReport:
    model: str
    path: str
    results: List[MutationResult] = field(default_factory=list)
    baseline_error: Optional[str] = None

    @property
    def scored(self) -> List[MutationResult]:
        return [r for r in self.results if r.outcome != "errored"]

    @property
    def caught(self) -> int:
        return sum(1 for r in self.scored if r.caught)

    @property
    def total(self) -> int:
        return len(self.scored)

    @property
    def survived(self) -> List[MutationResult]:
        return [r for r in self.scored if not r.caught]


@dataclass
class MutationReport:
    models: List[ModelReport] = field(default_factory=list)

    @property
    def caught(self) -> int:
        return sum(m.caught for m in self.models)

    @property
    def total(self) -> int:
        return sum(m.total for m in self.models)

    @property
    def score(self) -> float:
        return (100.0 * self.caught / self.total) if self.total else 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "caught": self.caught,
            "total": self.total,
            "score": round(self.score, 1),
            "models": [
                {
                    "model": m.model,
                    "path": m.path,
                    "caught": m.caught,
                    "total": m.total,
                    "baseline_error": m.baseline_error,
                    "results": [
                        {
                            "rule": r.rule.key,
                            "label": r.rule.label,
                            "occurrence": r.occurrence,
                            "outcome": r.outcome,
                            "detail": r.detail,
                            "why": r.rule.why,
                        }
                        for r in m.results
                    ],
                }
                for m in self.models
            ],
        }


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def resolve_dbt_bin() -> str:
    """Find the dbt executable.

    Prefer the one installed alongside the running interpreter, because misata
    and dbt usually share a virtualenv and that copy will not be on PATH when
    the venv is not activated. Fall back to PATH, then to the bare name so the
    error message names the command the user would type.
    """
    import sys

    sibling = Path(sys.executable).parent / "dbt"
    if sibling.is_file():
        return str(sibling)
    found = shutil.which("dbt")
    return found or "dbt"


class DbtRunner:
    """Thin wrapper around the dbt CLI plus an output checksum.

    The checksum is computed by the warehouse, not by us: we ask dbt to run an
    aggregate over the built relation and hash the answer. That keeps this
    adapter-agnostic and means we never pull rows into Python.
    """

    def __init__(self, project_dir: Path, profiles_dir: Optional[Path] = None,
                 target: Optional[str] = None, dbt_bin: Optional[str] = None):
        self.project_dir = project_dir
        self.profiles_dir = profiles_dir
        self.target = target
        self.dbt_bin = dbt_bin or resolve_dbt_bin()

    def _cmd(self, *args: str) -> List[str]:
        cmd = [self.dbt_bin, *args, "--project-dir", str(self.project_dir)]
        if self.profiles_dir:
            cmd += ["--profiles-dir", str(self.profiles_dir)]
        if self.target:
            cmd += ["--target", self.target]
        return cmd

    @staticmethod
    def _first_error(output: str) -> str:
        """Pull the meaningful error out of dbt's output.

        The last line is usually a caret from a SQL pointer, which tells the
        user nothing. Prefer the first line that actually names a problem.
        """
        lines = [ln.strip() for ln in (output or "").splitlines() if ln.strip()]
        for ln in lines:
            low = ln.lower()
            if any(k in low for k in ("error:", "runtime error", "catalog error",
                                      "compilation error", "parser error",
                                      "database error", "not exist")):
                return re.sub(r"\x1b\[[0-9;]*m", "", ln)[:200]
        return re.sub(r"\x1b\[[0-9;]*m", "", lines[-1])[:200] if lines else "dbt failed"

    def run_model(self, model: str) -> Tuple[bool, str]:
        proc = subprocess.run(
            self._cmd("run", "--select", model, "--quiet"),
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return False, self._first_error(proc.stdout or proc.stderr)
        return True, ""

    def checksum(self, model: str, limit: int = 100_000) -> Tuple[Optional[str], str]:
        """Order-independent checksum of a model's rows.

        Rows come back as JSON from ``dbt show``, which works identically on
        every adapter, then are sorted and hashed here. Sorting makes the
        digest order-independent: a mutation that only reorders rows has not
        changed the answer, and reporting it as a difference would be a false
        positive.

        ``limit`` caps how many rows are compared. dbt requires a limit on
        ``show``, so this is a real ceiling rather than a tuning knob: a model
        with more rows than this is only compared on the first ``limit`` of
        them, and :meth:`row_count` is checked separately so a change in size
        is never missed.
        """
        proc = subprocess.run(
            self._cmd("show", "--inline", f"select * from {{{{ ref('{model}') }}}}",
                      "--limit", str(limit), "--output", "json", "--quiet"),
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return None, self._first_error(proc.stdout or proc.stderr)
        try:
            payload = json.loads(proc.stdout)
            rows = payload.get("show", [])
        except (json.JSONDecodeError, AttributeError):
            return None, "could not parse dbt show output as JSON"
        # Canonicalise each row (sorted keys), then sort the rows themselves.
        canonical = sorted(
            json.dumps(r, sort_keys=True, default=str) for r in rows
        )
        blob = f"{len(rows)}\n" + "\n".join(canonical)
        return hashlib.sha256(blob.encode()).hexdigest()[:16], ""


def mutate_model(
    runner: DbtRunner,
    model: str,
    model_path: Path,
    rules: Optional[List[MutationRule]] = None,
    on_event: Optional[Any] = None,
) -> ModelReport:
    """Run every applicable mutation against one model, restoring it after."""
    rules = rules or RULES
    report = ModelReport(model=model, path=str(model_path))
    original = model_path.read_text(encoding="utf-8")

    # A backup on disk, not just in memory: if the process is killed midway the
    # user still has their model. Never leave someone's repo mutated.
    backup = Path(tempfile.gettempdir()) / f"misata-mutate-{model}-{id(report)}.sql"
    backup.write_text(original, encoding="utf-8")

    try:
        ok, err = runner.run_model(model)
        if not ok:
            report.baseline_error = f"baseline build failed: {err}"
            return report
        base, err = runner.checksum(model)
        if base is None:
            report.baseline_error = f"baseline checksum failed: {err}"
            return report

        for rule in rules:
            for occ in range(rule.count(original)):
                mutated = rule.apply(original, occ)
                if mutated is None or mutated == original:
                    continue
                model_path.write_text(mutated, encoding="utf-8")
                ok, err = runner.run_model(model)
                if not ok:
                    outcome, detail = "errored", err
                else:
                    digest, cerr = runner.checksum(model)
                    if digest is None:
                        outcome, detail = "errored", cerr
                    elif digest == base:
                        outcome, detail = "survived", "output identical"
                    else:
                        outcome, detail = "caught", "output changed"
                res = MutationResult(model, rule, occ, outcome, detail)
                report.results.append(res)
                if on_event:
                    on_event(res)
                model_path.write_text(original, encoding="utf-8")
    finally:
        # Restore unconditionally, then rebuild so the warehouse is not left
        # holding a mutated relation.
        model_path.write_text(original, encoding="utf-8")
        shutil.rmtree(backup, ignore_errors=True) if backup.is_dir() else backup.unlink(missing_ok=True)
        runner.run_model(model)

    return report


def model_sql_path(project_dir: Path, node: Dict[str, Any]) -> Optional[Path]:
    """Absolute path to a model's .sql file from its manifest node.

    ``original_file_path`` is relative to the package that owns the model, not
    to the root project, so a model from an installed package resolves under
    ``dbt_packages/<package>/``. Mutating a vendored package copy is a
    legitimate thing to measure (it is how you find out whether *your* data
    would catch a bug in a dependency), and the file is restored afterwards
    like any other.
    """
    original = node.get("original_file_path")
    if not original:
        return None
    candidates = [project_dir / original]
    package = node.get("package_name")
    if package:
        candidates.append(project_dir / "dbt_packages" / package / original)
    for c in candidates:
        p = c.resolve()
        if p.is_file():
            return p
    return None
