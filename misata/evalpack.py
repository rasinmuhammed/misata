"""
Answer-key-first evaluation packs for data agents.

An *evalpack* inverts the usual benchmark-construction order. Instead of
taking a database and annotating question/answer pairs afterwards (the step
where published text-to-SQL benchmarks pick up pervasive answer-key errors),
the ground truth is the *specification*: the outcome curves, rate curves, and
FK relationships declared in a :class:`~misata.schema.SchemaConfig`. Misata
generates a database that satisfies the spec, and every question shipped in
the pack is then verified by executing its gold SQL against the **written
files** with DuckDB — an engine that shares no code with the generator.

Questions whose observed answer does not exactly match the declared answer
are never shipped; they are dropped and recorded in the manifest. The result
is a benchmark where a wrong answer key is impossible by construction *and*
double-checked by independent execution.

Pack layout::

    pack_dir/
      tables/*.csv        the database
      questions.jsonl     one verified question per line
      certificate.json    per-question DuckDB verification + FK proof
      manifest.json       spec hash, seed, versions, dropped questions
      verify.py           standalone re-verification script (duckdb only)
      README.md           how to regenerate and re-verify

Usage::

    from misata.evalpack import build_evalpack
    result = build_evalpack(schema, "my_pack")
    assert result.all_verified

Requires the optional dependency ``duckdb`` (``pip install misata[evalpack]``).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd
    from misata.schema import SchemaConfig


_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _require_duckdb() -> Any:
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise ImportError(
            "Evalpacks verify answers with DuckDB, which is not installed. "
            "Install it with: pip install 'misata[evalpack]'"
        ) from exc
    return duckdb


def _quote_ident(name: str) -> str:
    """Quote an SQL identifier; reject names that can't be safely embedded."""
    if not _IDENT_RE.match(name):
        raise ValueError(
            f"Identifier {name!r} is not a plain SQL identifier; evalpack "
            "requires alphanumeric/underscore table and column names."
        )
    return f'"{name}"'


def _sql_literal(value: Any) -> str:
    """Render a Python value as a self-contained SQL literal."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _ts_literal(ts: Any) -> str:
    return f"TIMESTAMP '{ts.strftime('%Y-%m-%d %H:%M:%S')}'"


@dataclass
class EvalQuestion:
    """A single question whose answer derives from the declared spec."""

    id: str
    question: str
    gold_sql: str
    expected_answer: Any
    answer_type: str  # "number" | "integer" | "string"
    round_decimals: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    source: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "id": self.id,
            "question": self.question,
            "gold_sql": self.gold_sql,
            "expected_answer": self.expected_answer,
            "answer_type": self.answer_type,
            "tags": self.tags,
            "source": self.source,
        }
        if self.round_decimals is not None:
            payload["round_decimals"] = self.round_decimals
        return payload


@dataclass
class EvalPackResult:
    """Outcome of :func:`build_evalpack`."""

    output_dir: Path
    questions: List[EvalQuestion]
    dropped: List[Dict[str, Any]]
    certificate: Dict[str, Any]
    seed: int
    conformance_warnings: List[str] = field(default_factory=list)

    @property
    def all_verified(self) -> bool:
        return bool(self.certificate.get("all_match")) and bool(self.questions)

    def summary(self) -> str:
        lines = [
            f"Evalpack: {self.output_dir}",
            f"  questions shipped: {len(self.questions)} (all independently "
            f"verified with DuckDB)" if self.questions else "  questions shipped: 0",
            f"  candidates dropped: {len(self.dropped)}",
            f"  seed: {self.seed}",
        ]
        fk = self.certificate.get("fk_integrity", [])
        if fk:
            orphans = sum(entry["orphans"] for entry in fk)
            lines.append(f"  fk relationships: {len(fk)} ({orphans} orphans)")
        for w in self.conformance_warnings:
            lines.append(f"  ⚠ {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Question derivation (spec -> candidates; nothing here looks at the data)
# ---------------------------------------------------------------------------

def _month_label(start: Any, end: Any) -> Optional[str]:
    """Return 'YYYY-MM' when [start, end) is exactly one calendar month."""
    import pandas as pd

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if start.day == 1 and start.normalize() == start and end == start + pd.DateOffset(months=1):
        return start.strftime("%Y-%m")
    return None


def _window_phrase(start: Any, end: Any) -> str:
    label = _month_label(start, end)
    if label:
        return (
            f"during {start.strftime('%B %Y')} (rows whose timestamp is on or "
            f"after {start.date()} and strictly before {end.date()})"
        )
    return (
        f"in the window from {start} (inclusive) to {end} (exclusive)"
    )


def _curve_questions(schema: "SchemaConfig", next_id: Any) -> List[EvalQuestion]:
    from misata.engines import FactEngine

    engine = FactEngine()
    questions: List[EvalQuestion] = []

    for curve in getattr(schema, "outcome_curves", []) or []:
        if not engine.curve_has_exact_targets(curve):
            continue
        columns = schema.get_columns(curve.table)
        if not columns:
            continue
        resolved = engine._resolve_curve(curve, columns)
        table_sql = _quote_ident(curve.table)
        col_sql = _quote_ident(curve.column)
        time_sql = _quote_ident(curve.time_column)

        table_cfg = schema.get_table(curve.table)
        plan = engine.build_plan(table_cfg, columns, [curve]) if table_cfg else None

        month_labels: List[Optional[str]] = []
        for bucket, target in zip(resolved.buckets, resolved.targets):
            expected = round(float(target), 2)
            where = (
                f"{time_sql} >= {_ts_literal(bucket.start)} "
                f"AND {time_sql} < {_ts_literal(bucket.end)}"
            )
            questions.append(
                EvalQuestion(
                    id=next_id(),
                    question=(
                        f"In the {curve.table} table, what is the total of "
                        f"{curve.column} {_window_phrase(bucket.start, bucket.end)}? "
                        f"Give a number rounded to 2 decimal places."
                    ),
                    gold_sql=(
                        f"SELECT ROUND(SUM({col_sql}), 2) FROM {table_sql} "
                        f"WHERE {where}"
                    ),
                    expected_answer=expected,
                    answer_type="number",
                    round_decimals=2,
                    tags=["aggregation", "temporal_window", "single_table"],
                    source={
                        "kind": "outcome_curve_period",
                        "table": curve.table,
                        "column": curve.column,
                        "period": bucket.label,
                    },
                )
            )
            month_labels.append(_month_label(bucket.start, bucket.end))

        # Grand total across all declared periods.
        first = resolved.buckets[0]
        last = resolved.buckets[-1]
        total = round(float(sum(float(t) for t in resolved.targets)), 2)
        questions.append(
            EvalQuestion(
                id=next_id(),
                question=(
                    f"In the {curve.table} table, what is the total of "
                    f"{curve.column} across all rows whose {curve.time_column} "
                    f"is on or after {first.start.date()} and strictly before "
                    f"{last.end.date()}? Give a number rounded to 2 decimal places."
                ),
                gold_sql=(
                    f"SELECT ROUND(SUM({col_sql}), 2) FROM {table_sql} "
                    f"WHERE {time_sql} >= {_ts_literal(first.start)} "
                    f"AND {time_sql} < {_ts_literal(last.end)}"
                ),
                expected_answer=total,
                answer_type="number",
                round_decimals=2,
                tags=["aggregation", "single_table"],
                source={
                    "kind": "outcome_curve_total",
                    "table": curve.table,
                    "column": curve.column,
                },
            )
        )

        # Per-period row counts come from the engine's exact allocation plan.
        if plan is not None:
            for bucket, rows in zip(plan.buckets, plan.row_counts):
                questions.append(
                    EvalQuestion(
                        id=next_id(),
                        question=(
                            f"How many rows does the {curve.table} table contain "
                            f"{_window_phrase(bucket.start, bucket.end)}? "
                            f"Give an integer."
                        ),
                        gold_sql=(
                            f"SELECT COUNT(*) FROM {table_sql} "
                            f"WHERE {time_sql} >= {_ts_literal(bucket.start)} "
                            f"AND {time_sql} < {_ts_literal(bucket.end)}"
                        ),
                        expected_answer=int(rows),
                        answer_type="integer",
                        tags=["count", "temporal_window", "single_table"],
                        source={
                            "kind": "plan_row_count",
                            "table": curve.table,
                            "period": bucket.label,
                        },
                    )
                )

        # Argmax period — only when every bucket is a calendar month and the
        # maximum target is unique, so the answer has exactly one defensible
        # value. Tie-break is stated anyway to keep the question unambiguous.
        targets = [float(t) for t in resolved.targets]
        if all(month_labels) and targets.count(max(targets)) == 1:
            best = month_labels[targets.index(max(targets))]
            questions.append(
                EvalQuestion(
                    id=next_id(),
                    question=(
                        f"Which calendar month (format YYYY-MM) has the highest "
                        f"total of {curve.column} in the {curve.table} table? "
                        f"If several months tie, answer the earliest one."
                    ),
                    gold_sql=(
                        f"SELECT strftime(date_trunc('month', {time_sql}), '%Y-%m') "
                        f"AS period FROM {table_sql} GROUP BY 1 "
                        f"ORDER BY SUM({col_sql}) DESC, 1 ASC LIMIT 1"
                    ),
                    expected_answer=best,
                    answer_type="string",
                    tags=["aggregation", "argmax", "group_by", "single_table"],
                    source={
                        "kind": "outcome_curve_argmax",
                        "table": curve.table,
                        "column": curve.column,
                    },
                )
            )

    return questions


def _month_windows(schema: "SchemaConfig", table: str) -> Dict[int, tuple]:
    """Map month number -> (start, end) from the table's outcome-curve buckets.

    Rate-curve anchors store bare month numbers; the calendar year is defined
    by the outcome curve driving the same fact table. Months covered by more
    than one bucket (multi-year curves) are ambiguous and excluded."""
    from misata.engines import FactEngine

    engine = FactEngine()
    windows: Dict[int, Any] = {}
    ambiguous: set = set()
    for curve in getattr(schema, "outcome_curves", []) or []:
        if curve.table != table or not engine.curve_has_exact_targets(curve):
            continue
        columns = schema.get_columns(table)
        if not columns:
            continue
        resolved = engine._resolve_curve(curve, columns)
        for bucket in resolved.buckets:
            if _month_label(bucket.start, bucket.end) is None:
                continue
            month = bucket.start.month
            if month in windows:
                ambiguous.add(month)
            windows[month] = (bucket.start, bucket.end)
    return {m: w for m, w in windows.items() if m not in ambiguous}


def _rate_questions(schema: "SchemaConfig", next_id: Any) -> List[EvalQuestion]:
    """Rate anchors as candidates. Count rounding can make a declared rate
    unattainable exactly, so these rely on the verification gate: any anchor
    whose achieved rate differs at 4 decimals is dropped, never shipped."""
    import pandas as pd

    questions: List[EvalQuestion] = []
    for rate_curve in getattr(schema, "rate_curves", []) or []:
        table_sql = _quote_ident(rate_curve.table)
        col_sql = _quote_ident(rate_curve.column)
        time_sql = _quote_ident(rate_curve.time_column)
        true_literal = _sql_literal(rate_curve.true_value)
        month_windows = _month_windows(schema, rate_curve.table)

        for point in rate_curve.rate_points or []:
            period = str(point.get("period", ""))
            rate = point.get("rate")
            if rate is None:
                continue
            if re.match(r"^\d{4}-\d{2}$", period):
                start = pd.Timestamp(f"{period}-01")
                end = start + pd.DateOffset(months=1)
            elif re.match(r"^\d{1,2}$", period) and int(period) in month_windows:
                start, end = month_windows[int(period)]
                period = start.strftime("%Y-%m")
            else:
                continue  # v1: YYYY-MM anchors, or month numbers resolvable
                          # through the table's outcome-curve calendar
            questions.append(
                EvalQuestion(
                    id=next_id(),
                    question=(
                        f"In the {rate_curve.table} table, what fraction of rows "
                        f"{_window_phrase(start, end)} have {rate_curve.column} "
                        f"equal to {rate_curve.true_value}? Give a number rounded "
                        f"to 4 decimal places."
                    ),
                    gold_sql=(
                        f"SELECT ROUND(AVG(CASE WHEN {col_sql} = {true_literal} "
                        f"THEN 1.0 ELSE 0.0 END), 4) FROM {table_sql} "
                        f"WHERE {time_sql} >= {_ts_literal(start)} "
                        f"AND {time_sql} < {_ts_literal(end)}"
                    ),
                    expected_answer=round(float(rate), 4),
                    answer_type="number",
                    round_decimals=4,
                    tags=["rate", "temporal_window", "single_table"],
                    source={
                        "kind": "rate_curve_anchor",
                        "table": rate_curve.table,
                        "column": rate_curve.column,
                        "period": period,
                    },
                )
            )
    return questions


def _fk_questions(schema: "SchemaConfig", next_id: Any) -> List[EvalQuestion]:
    questions: List[EvalQuestion] = []
    for rel in getattr(schema, "relationships", []) or []:
        child_sql = _quote_ident(rel.child_table)
        parent_sql = _quote_ident(rel.parent_table)
        ck = _quote_ident(rel.child_key)
        pk = _quote_ident(rel.parent_key)
        questions.append(
            EvalQuestion(
                id=next_id(),
                question=(
                    f"How many rows in the {rel.child_table} table have a "
                    f"{rel.child_key} value that does not appear in the "
                    f"{rel.parent_key} column of the {rel.parent_table} table? "
                    f"Count NULL {rel.child_key} values as matching. Give an integer."
                ),
                gold_sql=(
                    f"SELECT COUNT(*) FROM {child_sql} c "
                    f"LEFT JOIN {parent_sql} p ON c.{ck} = p.{pk} "
                    f"WHERE p.{pk} IS NULL AND c.{ck} IS NOT NULL"
                ),
                expected_answer=0,
                answer_type="integer",
                tags=["join", "integrity", "multi_table"],
                source={
                    "kind": "fk_integrity",
                    "relationship": f"{rel.child_table}.{rel.child_key} -> "
                                    f"{rel.parent_table}.{rel.parent_key}",
                },
            )
        )
    return questions


def _ledger_questions(schema: "SchemaConfig", next_id: Any) -> List[EvalQuestion]:
    """Identity questions from ``balanced_ledger`` constraints.

    Double-entry data satisfies a cross-row identity: within every journal
    entry, total debits equal total credits. Two questions follow, both
    requiring a group-by (the composed-declaration families): the count of
    entries that fail to balance (declared zero, like FK orphans), and the
    global trial-balance difference (declared zero)."""
    questions: List[EvalQuestion] = []
    for table in getattr(schema, "tables", []) or []:
        for con in getattr(table, "constraints", []) or []:
            if getattr(con, "type", None) != "balanced_ledger":
                continue
            debit = getattr(con, "debit_column", None)
            credit = getattr(con, "credit_column", None)
            group_by = getattr(con, "group_by", None) or []
            if not (debit and credit and group_by):
                continue
            tbl = _quote_ident(table.name)
            dcol, ccol = _quote_ident(debit), _quote_ident(credit)
            gcols = ", ".join(_quote_ident(g) for g in group_by)
            dec = int(getattr(con, "decimals", 2) or 2)
            key_phrase = " and ".join(group_by)

            questions.append(
                EvalQuestion(
                    id=next_id(),
                    question=(
                        f"In the {table.name} table, grouping rows by "
                        f"{key_phrase}, how many groups have a total {debit} "
                        f"that does not equal their total {credit} (rounded to "
                        f"{dec} decimal places)? Give an integer."
                    ),
                    gold_sql=(
                        f"SELECT COUNT(*) FROM (SELECT {gcols}, "
                        f"ROUND(SUM({dcol}) - SUM({ccol}), {dec}) AS net "
                        f"FROM {tbl} GROUP BY {gcols}) WHERE net <> 0"
                    ),
                    expected_answer=0,
                    answer_type="integer",
                    tags=["group_by", "identity", "accounting", "single_table"],
                    source={"kind": "ledger_entry_balance", "table": table.name},
                )
            )
            questions.append(
                EvalQuestion(
                    id=next_id(),
                    question=(
                        f"In the {table.name} table, what is the total {debit} "
                        f"across all rows minus the total {credit} across all "
                        f"rows, rounded to {dec} decimal places? Give a number."
                    ),
                    gold_sql=(
                        f"SELECT ROUND(SUM({dcol}) - SUM({ccol}), {dec}) "
                        f"FROM {tbl}"
                    ),
                    expected_answer=0.0,
                    answer_type="number",
                    round_decimals=dec,
                    tags=["aggregation", "identity", "accounting", "single_table"],
                    source={"kind": "ledger_trial_balance", "table": table.name},
                )
            )
    return questions


# ---------------------------------------------------------------------------
# Independent verification (DuckDB over the written files)
# ---------------------------------------------------------------------------

def _verify_questions(
    con: Any,
    candidates: List[EvalQuestion],
) -> tuple[List[EvalQuestion], List[Dict[str, Any]], List[Dict[str, Any]]]:
    shipped: List[EvalQuestion] = []
    dropped: List[Dict[str, Any]] = []
    entries: List[Dict[str, Any]] = []

    for q in candidates:
        try:
            row = con.execute(q.gold_sql).fetchone()
            observed = row[0] if row else None
        except Exception as exc:  # noqa: BLE001 - any SQL failure drops the question
            dropped.append({**q.to_dict(), "drop_reason": f"sql_error: {exc}"})
            continue

        match = _answers_match(q, observed)
        if match:
            shipped.append(q)
            entries.append(
                {
                    "id": q.id,
                    "gold_sql": q.gold_sql,
                    "expected": q.expected_answer,
                    "observed": _jsonable(observed),
                    "match": True,
                }
            )
        else:
            dropped.append(
                {
                    **q.to_dict(),
                    "drop_reason": "verification_mismatch",
                    "observed": _jsonable(observed),
                }
            )
    return shipped, dropped, entries


def _answers_match(q: EvalQuestion, observed: Any) -> bool:
    if observed is None:
        return False
    if q.answer_type == "string":
        return str(observed) == str(q.expected_answer)
    try:
        observed_num = float(observed)
        expected_num = float(q.expected_answer)
    except (TypeError, ValueError):
        return False
    nd = q.round_decimals if q.round_decimals is not None else 0
    return abs(round(observed_num, nd) - round(expected_num, nd)) < 1e-9


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Pack assembly
# ---------------------------------------------------------------------------

def build_evalpack(
    schema: "SchemaConfig",
    output_dir: Any,
    *,
    tables: Optional[Dict[str, "pd.DataFrame"]] = None,
) -> EvalPackResult:
    """Generate a database from ``schema`` and emit a verified evalpack.

    Every candidate question's expected answer derives from the *declared*
    spec (outcome-curve targets, allocation plan, rate anchors, FK
    relationships). The written CSVs are then loaded with DuckDB and every
    gold SQL is executed against them; only questions whose observed answer
    exactly matches the declared answer are shipped. Failures are recorded
    in ``manifest.json`` under ``dropped_questions``.

    Before generation, :func:`~misata.conformance.conformance_preview` runs
    against the schema's outcome curves; its warnings (Prop-3 clamping,
    bound conflicts) are printed and recorded under ``conformance_warnings``
    in both ``manifest.json`` and ``certificate.json``.

    Args:
        schema:     A :class:`~misata.schema.SchemaConfig`. If ``schema.seed``
                    is ``None`` a seed is chosen and recorded so the pack is
                    reproducible.
        output_dir: Directory to create the pack in (created if missing).
        tables:     Optional pre-generated tables (must come from this exact
                    schema+seed); when omitted, tables are generated.

    Returns:
        :class:`EvalPackResult`; check ``.all_verified``.
    """
    duckdb = _require_duckdb()
    import misata

    if schema.seed is None:
        import random

        schema.seed = random.randint(1, 2**31 - 1)
    seed = int(schema.seed)

    # Pre-generation conformance check: Prop-3 clamping silently distorts
    # per-row values (a period whose ideal row count exceeds
    # max_transactions_per_period ships inflated amounts), so the pack must
    # carry those warnings, not hide them.
    conformance_warnings: List[str] = []
    if getattr(schema, "outcome_curves", None):
        from misata.conformance import conformance_preview

        conformance_warnings = list(conformance_preview(schema).warnings)
        for w in conformance_warnings:
            print(f"⚠ evalpack conformance: {w}")

    if tables is None:
        tables = misata.generate_from_schema(schema)

    out = Path(output_dir)
    tables_dir = out / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        _quote_ident(name)  # fail early on unsafe names
        df.to_csv(tables_dir / f"{name}.csv", index=False)

    counter = {"n": 0}

    def next_id() -> str:
        counter["n"] += 1
        return f"q{counter['n']:03d}"

    candidates: List[EvalQuestion] = []
    candidates.extend(_curve_questions(schema, next_id))
    candidates.extend(_rate_questions(schema, next_id))
    candidates.extend(_fk_questions(schema, next_id))
    candidates.extend(_ledger_questions(schema, next_id))

    # Verify what we ship: DuckDB reads the CSVs from disk, exactly as a
    # downstream consumer would. The generator and the verifier share
    # nothing but the files.
    con = duckdb.connect()
    for name in tables:
        csv_path = str((tables_dir / f"{name}.csv").resolve()).replace("'", "''")
        con.execute(
            f"CREATE VIEW {_quote_ident(name)} AS "
            f"SELECT * FROM read_csv_auto('{csv_path}')"
        )
    shipped, dropped, entries = _verify_questions(con, candidates)

    fk_integrity = [
        {
            "relationship": e_q.source["relationship"],
            "orphans": 0,
            "verified": True,
        }
        for e_q in shipped
        if e_q.source.get("kind") == "fk_integrity"
    ]

    spec_json = schema.model_dump_json()
    spec_hash = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()

    certificate = {
        "pack": schema.name,
        "misata_version": misata.__version__,
        "seed": seed,
        "spec_sha256": spec_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verifier": {"engine": "duckdb", "version": duckdb.__version__},
        "sql_dialect": "duckdb",
        "answer_comparison": (
            "numeric at round_decimals (never string equality); "
            "strings compared exactly"
        ),
        "fk_integrity": fk_integrity,
        # all_match certifies the declared aggregates only; clamping
        # distortion of per-row values is disclosed here, not hidden in
        # the manifest alone.
        "conformance_warnings": conformance_warnings,
        "questions": entries,
        "all_match": all(e["match"] for e in entries) if entries else False,
    }

    # The story-audit verdict rides in the manifest: an evalpack asserts its
    # answers are right, and this asserts the DATA telling that story is
    # internally coherent (FK, causality, roll-ups, bounds). Same honesty
    # ledger, second axis.
    try:
        from misata.coherence import story_audit as _story_audit
        _audit = _story_audit(tables, schema)
        story_audit_block = {
            "clean": bool(_audit.clean),
            "score": float(_audit.score),
            "findings": [f.to_dict() for f in _audit.findings],
        }
    except Exception as exc:  # noqa: BLE001 - advisory, never blocks a build
        story_audit_block = {"clean": None, "error": str(exc)[:200]}

    manifest = {
        "pack": schema.name,
        "misata_version": misata.__version__,
        "seed": seed,
        "spec_sha256": spec_hash,
        "tables": {name: int(len(df)) for name, df in tables.items()},
        "questions_shipped": len(shipped),
        "questions_dropped": len(dropped),
        "dropped_questions": dropped,
        "conformance_warnings": conformance_warnings,
        "story_audit": story_audit_block,
        "schema": json.loads(spec_json),
    }

    with open(out / "questions.jsonl", "w", encoding="utf-8") as fh:
        for q in shipped:
            fh.write(json.dumps(q.to_dict()) + "\n")
    with open(out / "certificate.json", "w", encoding="utf-8") as fh:
        json.dump(certificate, fh, indent=2)
    with open(out / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    (out / "verify.py").write_text(_VERIFY_SCRIPT, encoding="utf-8")
    (out / "README.md").write_text(_readme(schema.name, len(shipped)), encoding="utf-8")

    return EvalPackResult(
        output_dir=out,
        questions=shipped,
        dropped=dropped,
        certificate=certificate,
        seed=seed,
        conformance_warnings=conformance_warnings,
    )


def _readme(name: str, n_questions: int) -> str:
    return f"""# Evalpack: {name}

{n_questions} question/answer pairs over the CSV tables in `tables/`.
Every expected answer was **declared before the data was generated** and then
verified by executing the gold SQL with DuckDB against these exact files.

Re-verify yourself (30 seconds):

```bash
pip install duckdb
python verify.py
```

`certificate.json` records the verification run (DuckDB version, per-question
observed values, FK orphan counts). `manifest.json` records the generation
seed, the misata version, the spec hash, and every candidate question that
was dropped by the verification gate.

Gold SQL is written in DuckDB dialect and verified with DuckDB. Numeric
answers must be compared numerically at each question's `round_decimals`
(JSON numbers cannot carry trailing zeros); never compare answers as strings.

Regenerate the identical pack from `manifest.json`'s schema + seed with
[misata](https://github.com/rasinmuhammed/misata), or change the seed to get
a fresh database with the same declared answers where applicable.
"""


_VERIFY_SCRIPT = '''#!/usr/bin/env python3
"""Independently re-verify this evalpack: run every gold SQL with DuckDB
against the CSVs in tables/ and compare to the expected answers.

Usage: python verify.py     (exits 1 on any mismatch)
"""
import json
import sys
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
con = duckdb.connect()
for csv in sorted((HERE / "tables").glob("*.csv")):
    path = str(csv.resolve()).replace("'", "''")
    con.execute(
        'CREATE VIEW "%s" AS SELECT * FROM read_csv_auto(\\'%s\\')'
        % (csv.stem, path)
    )

failures = 0
total = 0
for line in (HERE / "questions.jsonl").read_text().splitlines():
    if not line.strip():
        continue
    q = json.loads(line)
    total += 1
    row = con.execute(q["gold_sql"]).fetchone()
    observed = row[0] if row else None
    expected = q["expected_answer"]
    if q["answer_type"] == "string":
        ok = str(observed) == str(expected)
    else:
        nd = q.get("round_decimals", 0)
        try:
            ok = (
                observed is not None
                and abs(round(float(observed), nd) - round(float(expected), nd))
                < 1e-9
            )
        except (TypeError, ValueError):
            ok = False
    status = "OK  " if ok else "FAIL"
    if not ok:
        failures += 1
        print(f"{status} {q['id']}: expected={expected} observed={observed}")
        print(f"     {q['gold_sql']}")
    else:
        print(f"{status} {q['id']}: {expected}")

print(f"\\n{total - failures}/{total} verified exactly")
sys.exit(1 if failures else 0)
'''
