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
      attestation.intoto.json   in-toto Statement pinning every table by
                                SHA-256 with the declared invariants
      attestation.dsse.json     the Statement in an unsigned DSSE envelope
      verify_attestation.py     re-checks the digests and the invariants
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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from misata.sqlutil import quote_ident, quote_literal

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
    return quote_ident(name)


def _sql_literal(value: Any) -> str:
    """Render a Python value as a self-contained SQL literal."""
    return quote_literal(value)


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
    seeds: List[int] = field(default_factory=list)

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
        if len(self.seeds) > 1:
            lines.append(f"  databases: {len(self.seeds)} (seeds {self.seeds[0]} to "
                         f"{self.seeds[-1]}); a query must match on all of them")
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
        label: str = start.strftime("%Y-%m")
        return label
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
        for bucket, target in zip(resolved.buckets, resolved.targets, strict=True):
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
            for bucket, rows in zip(plan.buckets, plan.row_counts, strict=True):
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


@dataclass(frozen=True)
class RateAnchor:
    """One declared rate over one time window, resolved to concrete bounds."""

    rate_curve: Any
    period: str
    rate: float
    start: Any
    end: Any


def rate_anchors(schema: "SchemaConfig") -> List[RateAnchor]:
    """Every rate-curve anchor whose window can be resolved from the schema.

    An anchor names its period as ``YYYY-MM``, or as a month number resolved
    through the same table's outcome-curve calendar. Other forms are skipped.
    """
    import pandas as pd

    anchors: List[RateAnchor] = []
    for rate_curve in getattr(schema, "rate_curves", []) or []:
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
                continue
            anchors.append(RateAnchor(rate_curve, period, float(rate), start, end))
    return anchors


def _rate_questions(schema: "SchemaConfig", next_id: Any) -> List[EvalQuestion]:
    """Rate anchors as candidates. Count rounding can make a declared rate
    unattainable exactly, so these rely on the verification gate: any anchor
    whose achieved rate differs at 4 decimals is dropped, never shipped."""
    questions: List[EvalQuestion] = []
    for anchor in rate_anchors(schema):
        rate_curve, period, rate = anchor.rate_curve, anchor.period, anchor.rate
        start, end = anchor.start, anchor.end
        table_sql = _quote_ident(rate_curve.table)
        col_sql = _quote_ident(rate_curve.column)
        time_sql = _quote_ident(rate_curve.time_column)
        true_literal = _sql_literal(rate_curve.true_value)
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


def _waterfall_questions(schema: "SchemaConfig", next_id: Any) -> List[EvalQuestion]:
    """Running-balance questions from ``waterfalls`` declarations.

    Fully answer-key-first: the per-period net movements and ending balances
    come from the declaration (via the same ``declared_movements`` helper the
    generator uses), never from measuring the data. Running-balance questions
    are emitted only when the period labels sort lexicographically in
    declaration order (true for ISO labels like 2025-01), because their gold
    SQL filters with ``period <= label``."""
    from misata.waterfall import declared_movements

    questions: List[EvalQuestion] = []
    for spec in getattr(schema, "waterfalls", []) or []:
        plan = declared_movements(spec)
        if not plan:
            continue
        tbl = _quote_ident(spec.table)
        p_sql = _quote_ident(spec.period_column)
        t_sql = _quote_ident(spec.type_column)
        a_sql = _quote_ident(spec.amount_column)
        seg_where = ""
        seg_phrase = ""
        if spec.segment_column and spec.segment_value is not None:
            seg_sql = _quote_ident(spec.segment_column)
            seg_lit = "'" + str(spec.segment_value).replace("'", "''") + "'"
            seg_where = f" AND {seg_sql} = {seg_lit}"
            seg_phrase = (f" for rows where {spec.segment_column} is "
                          f"'{spec.segment_value}'")
        inflow_labels = sorted({label for _, _, ins, _ in plan for label in ins})
        in_list = ", ".join(quote_literal(label) for label in inflow_labels)
        signed = (f"SUM(CASE WHEN {t_sql} IN ({in_list}) "
                  f"THEN {a_sql} ELSE -{a_sql} END)")
        labels = [period for period, _, _, _ in plan]
        labels_sorted = labels == sorted(labels)

        prev = round(float(spec.starting_value), 2)
        for period, end, inflows, outflows in plan:
            lab = quote_literal(period)
            delta = round(end - prev, 2)
            questions.append(
                EvalQuestion(
                    id=next_id(),
                    question=(
                        f"In the {spec.table} table, treating "
                        f"{', '.join(inflow_labels)} as inflows and every "
                        f"other {spec.type_column} as an outflow, what is the "
                        f"net movement of {spec.amount_column}{seg_phrase} "
                        f"in period '{period}'? Give a number rounded to 2 decimal "
                        f"places (negative for a net decline)."
                    ),
                    gold_sql=(
                        f"SELECT ROUND({signed}, 2) FROM {tbl} "
                        f"WHERE {p_sql} = {lab}{seg_where}"
                    ),
                    expected_answer=delta,
                    answer_type="number",
                    round_decimals=2,
                    tags=["identity", "filtered_aggregation", "single_table"],
                    source={"kind": "waterfall_net", "table": spec.table,
                            "period": period},
                )
            )
            for label, total in list(inflows.items()) + list(outflows.items()):
                t_lab = quote_literal(label)
                questions.append(
                    EvalQuestion(
                        id=next_id(),
                        question=(
                            f"In the {spec.table} table, what is the total "
                            f"{spec.amount_column} of {spec.type_column} "
                            f"'{label}'{seg_phrase} in period '{period}'? Give a number "
                            f"rounded to 2 decimal places."
                        ),
                        gold_sql=(
                            f"SELECT ROUND(SUM({a_sql}), 2) FROM {tbl} "
                            f"WHERE {p_sql} = {lab} AND {t_sql} = {t_lab}{seg_where}"
                        ),
                        expected_answer=total,
                        answer_type="number",
                        round_decimals=2,
                        tags=["group_by", "filtered_aggregation", "single_table"],
                        source={"kind": "waterfall_component",
                                "table": spec.table, "period": period,
                                "type": label},
                    )
                )
            if labels_sorted:
                questions.append(
                    EvalQuestion(
                        id=next_id(),
                        question=(
                            f"The balance before the first period in the "
                            f"{spec.table} table was "
                            f"{round(float(spec.starting_value), 2)}. Treating "
                            f"{', '.join(inflow_labels)} as inflows and every "
                            f"other {spec.type_column} as an outflow, what is "
                            f"the balance{seg_phrase} at the end of period "
                            f"'{period}'? "
                            f"Give a number rounded to 2 decimal places."
                        ),
                        gold_sql=(
                            f"SELECT ROUND({round(float(spec.starting_value), 2)} "
                            f"+ {signed}, 2) FROM {tbl} "
                            f"WHERE {p_sql} <= {lab}{seg_where}"
                        ),
                        expected_answer=end,
                        answer_type="number",
                        round_decimals=2,
                        tags=["identity", "running_total", "single_table"],
                        source={"kind": "waterfall_balance",
                                "table": spec.table, "period": period},
                    )
                )
            prev = end
    return questions


def _group_share_questions(schema: "SchemaConfig", next_id: Any) -> List[EvalQuestion]:
    """Filtered-aggregation questions from ``group_shares`` declarations.

    Emitted only when the spec pairs with an exact-target curve on the same
    table and measure: that is the only case where the totals being split are
    themselves declared, so the expected answers come from the specification
    rather than from measuring the generated data (answer-key-first). The
    targets are computed by the same helper the generator uses, so the
    questions cannot drift from the data."""
    from misata.shares import declared_group_targets

    questions: List[EvalQuestion] = []
    for spec in getattr(schema, "group_shares", []) or []:
        per_bucket = declared_group_targets(spec, schema)
        if not per_bucket:
            continue
        curve = next(
            (c for c in schema.outcome_curves
             if c.table == spec.table and c.column == spec.measure), None)
        if curve is None:
            continue
        tbl = _quote_ident(spec.table)
        m_sql = _quote_ident(spec.measure)
        g_sql = _quote_ident(spec.group_column)
        time_sql = _quote_ident(curve.time_column)

        grand: Dict[str, float] = {}
        for start, end, targets in per_bucket:
            for label, t in targets.items():
                grand[label] = round(grand.get(label, 0.0) + t, 2)
                lab_sql = quote_literal(str(label))
                questions.append(
                    EvalQuestion(
                        id=next_id(),
                        question=(
                            f"In the {spec.table} table, what is the total of "
                            f"{spec.measure} for rows where {spec.group_column} "
                            f"is '{label}' {_window_phrase(start, end)}? "
                            f"Give a number rounded to 2 decimal places."
                        ),
                        gold_sql=(
                            f"SELECT ROUND(SUM({m_sql}), 2) FROM {tbl} "
                            f"WHERE {g_sql} = {lab_sql} "
                            f"AND {time_sql} >= {_ts_literal(start)} "
                            f"AND {time_sql} < {_ts_literal(end)}"
                        ),
                        expected_answer=t,
                        answer_type="number",
                        round_decimals=2,
                        tags=["group_by", "filtered_aggregation", "single_table"],
                        source={
                            "kind": "group_share_period",
                            "table": spec.table,
                            "measure": spec.measure,
                            "group": str(label),
                            "period": _month_label(start, end) or f"{start}..{end}",
                        },
                    )
                )

        first_start = per_bucket[0][0]
        last_end = per_bucket[-1][1]
        for label, total in grand.items():
            lab_sql = quote_literal(str(label))
            questions.append(
                EvalQuestion(
                    id=next_id(),
                    question=(
                        f"In the {spec.table} table, what is the total of "
                        f"{spec.measure} for rows where {spec.group_column} is "
                        f"'{label}' across all rows whose {curve.time_column} "
                        f"is on or after {first_start.date()} and strictly "
                        f"before {last_end.date()}? Give a number rounded to "
                        f"2 decimal places."
                    ),
                    gold_sql=(
                        f"SELECT ROUND(SUM({m_sql}), 2) FROM {tbl} "
                        f"WHERE {g_sql} = {lab_sql} "
                        f"AND {time_sql} >= {_ts_literal(first_start)} "
                        f"AND {time_sql} < {_ts_literal(last_end)}"
                    ),
                    expected_answer=round(total, 2),
                    answer_type="number",
                    round_decimals=2,
                    tags=["group_by", "filtered_aggregation", "single_table"],
                    source={
                        "kind": "group_share_total",
                        "table": spec.table,
                        "measure": spec.measure,
                        "group": str(label),
                    },
                )
            )
    return questions


# ---------------------------------------------------------------------------
# Independent verification (DuckDB over the written files)
# ---------------------------------------------------------------------------

_DERIVERS = (
    _curve_questions,
    _rate_questions,
    _fk_questions,
    _ledger_questions,
    _group_share_questions,
    _waterfall_questions,
)


def derive_questions(schema: "SchemaConfig") -> List[EvalQuestion]:
    """Every question the schema's declarations answer, before any data exists.

    Each expected answer comes from the declared spec alone: curve targets
    and their allocation plan, rate anchors, relationships, ledger identities,
    group shares and waterfalls. Ids run ``q001``, ``q002`` in that order.
    """
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"q{counter:03d}"

    questions: List[EvalQuestion] = []
    for derive in _DERIVERS:
        questions.extend(derive(schema, next_id))
    return questions


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
# Near misses: plausible wrong queries, to measure what rotation buys
# ---------------------------------------------------------------------------

#: Mistakes a text-to-SQL system makes that can still return the right number
#: on one database: a window closed at the wrong end, a join that cannot see
#: orphans, money rounded to whole units.
NEAR_MISSES: Tuple[Tuple[str, "re.Pattern[str]", str], ...] = (
    ("inclusive_end", re.compile(r" < TIMESTAMP "), " <= TIMESTAMP "),
    ("exclusive_start", re.compile(r" >= TIMESTAMP "), " > TIMESTAMP "),
    ("inner_join", re.compile(r" LEFT JOIN "), " JOIN "),
    ("whole_units", re.compile(r"ROUND\((SUM\([^()]*\)), 2\)"), r"ROUND(\1, 0)"),
)


def near_misses(question: EvalQuestion) -> List[Tuple[str, str]]:
    """``(mistake, sql)`` for each near miss that changes the gold SQL."""
    out = []
    for name, pattern, replacement in NEAR_MISSES:
        sql = pattern.sub(replacement, question.gold_sql)
        if sql != question.gold_sql:
            out.append((name, sql))
    return out


# ---------------------------------------------------------------------------
# Pack assembly
# ---------------------------------------------------------------------------

@dataclass
class _Database:
    """One generated database of a pack: its seed, folder and open views."""

    seed: int
    schema: "SchemaConfig"
    directory: Path
    tables: Dict[str, "pd.DataFrame"]
    con: Any
    questions: Dict[str, EvalQuestion]


def _observe(con: Any, question: EvalQuestion) -> Tuple[Any, Optional[str]]:
    try:
        row = con.execute(question.gold_sql).fetchone()
    except Exception as exc:  # noqa: BLE001 - any SQL failure drops the question
        return None, str(exc)
    return (row[0] if row else None), None


def _open_database(duckdb: Any, schema: "SchemaConfig", seed: int, directory: Path,
                   tables: Dict[str, "pd.DataFrame"]) -> _Database:
    """Write the tables as CSV and open them in DuckDB exactly as a consumer would."""
    tables_dir = directory / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        _quote_ident(name)  # fail early on unsafe names
        df.to_csv(tables_dir / f"{name}.csv", index=False)
    con = duckdb.connect()
    for name in tables:
        csv_path = quote_literal(str((tables_dir / f"{name}.csv").resolve()))
        # Parsed once, as a consumer's read_csv_auto would; every question then
        # runs against the table instead of re-reading the file.
        con.execute(f"CREATE TABLE {_quote_ident(name)} AS SELECT * FROM read_csv_auto({csv_path})")
    questions = {q.id: q for q in derive_questions(schema)}
    return _Database(seed, schema, directory, tables, con, questions)


def _story_audit_block(db: _Database) -> Dict[str, Any]:
    """Whether the data telling the story is coherent: advisory, never blocking."""
    try:
        from misata.coherence import story_audit

        audit = story_audit(db.tables, db.schema)
        return {"clean": bool(audit.clean), "score": float(audit.score),
                "findings": [f.to_dict() for f in audit.findings]}
    except Exception as exc:  # noqa: BLE001 - advisory, never blocks a build
        return {"clean": None, "error": str(exc)[:200]}


def _attest(db: _Database) -> Dict[str, Any]:
    """The portable form of the proof: tables pinned by SHA-256 in an in-toto Statement."""
    from misata.attestation import AttestationError, attest

    try:
        attestation = attest(db.directory, db.schema, script_name="verify_attestation.py")
    except AttestationError as exc:
        return {"statement": None, "reason": str(exc)}
    return {"statement": "attestation.intoto.json",
            "result": attestation.statement["predicate"]["result"]}


def _near_miss_study(shipped: List[EvalQuestion], dbs: List[_Database]) -> Dict[str, Any]:
    """How often a plausible wrong query passes on one database, and on all of them."""
    per_mistake: Dict[str, Dict[str, int]] = {}
    single_matches, total, all_matches = 0, 0, 0
    for question in shipped:
        for mistake, sql in near_misses(question):
            wrong = EvalQuestion(id=question.id, question=question.question, gold_sql=sql,
                                 expected_answer=question.expected_answer,
                                 answer_type=question.answer_type,
                                 round_decimals=question.round_decimals)
            hits = [_answers_match(wrong, _observe(db.con, wrong)[0]) for db in dbs]
            stats = per_mistake.setdefault(mistake, {"queries": 0, "match_one": 0, "match_all": 0})
            stats["queries"] += 1
            stats["match_one"] += sum(hits)
            stats["match_all"] += int(all(hits))
            single_matches += sum(hits)
            all_matches += int(all(hits))
            total += 1
    if total == 0:
        return {"queries": 0}
    return {
        "queries": total,
        "databases": len(dbs),
        "false_positive_rate_one_database": round(single_matches / (total * len(dbs)), 4),
        "false_positive_rate_all_databases": round(all_matches / total, 4),
        "by_mistake": {
            name: {
                "queries": st["queries"],
                "false_positive_rate_one_database":
                    round(st["match_one"] / (st["queries"] * len(dbs)), 4),
                "false_positive_rate_all_databases": round(st["match_all"] / st["queries"], 4),
            }
            for name, st in sorted(per_mistake.items())
        },
        "note": ("A near miss is the gold SQL with one plausible mistake. Matching one "
                 "database is what single-database execution accuracy accepts; matching "
                 "all of them is what this pack accepts. A mistake that matches every "
                 "database is equivalent on this data, and no execution check can catch it."),
    }


def _select_questions(
    dbs: List[_Database],
) -> Tuple[List[EvalQuestion], List[Dict[str, Any]], Dict[str, List[Any]]]:
    """Split the derived questions into shipped and dropped.

    A question ships only when every database agrees on its SQL and its
    declared answer, and every database's files return that answer. Returns
    the shipped questions, the dropped ones with their reason, and each
    shipped question's observed answer per database.
    """
    shipped: List[EvalQuestion] = []
    dropped: List[Dict[str, Any]] = []
    observed: Dict[str, List[Any]] = {}
    cons = [db.con for db in dbs]
    for question in dbs[0].questions.values():
        twins = [db.questions.get(question.id) for db in dbs]
        if any(t is None or t.gold_sql != question.gold_sql
               or t.expected_answer != question.expected_answer for t in twins):
            dropped.append({**question.to_dict(), "drop_reason": "answer_depends_on_seed"})
            continue
        values, drop = _check_question(question, cons)
        if drop is None:
            shipped.append(question)
            observed[question.id] = values
        else:
            dropped.append(drop)
    return shipped, dropped, observed


def _check_question(question: EvalQuestion,
                    cons: List[Any]) -> Tuple[List[Any], Optional[Dict[str, Any]]]:
    """Each connection's answer, and the drop record when any of them misses."""
    results = [_observe(con, question) for con in cons]
    errors = [err for _, err in results if err]
    if errors:
        return [], {**question.to_dict(), "drop_reason": f"sql_error: {errors[0]}"}
    values = [_jsonable(value) for value, _ in results]
    if all(_answers_match(question, value) for value, _ in results):
        return values, None
    return values, {**question.to_dict(), "drop_reason": "verification_mismatch",
                    "observed": values[0] if len(cons) == 1 else values}


def verify_questions(
    con: Any,
    questions: List[EvalQuestion],
) -> Tuple[List[EvalQuestion], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Keep the questions whose gold SQL returns the expected answer on ``con``.

    For packs whose questions come from somewhere other than the schema's
    declarations, such as a generated answer key. Uses the same comparison
    as :func:`build_evalpack`.

    Returns:
        The shipped questions, the dropped ones with their ``drop_reason``,
        and one certificate entry per shipped question.
    """
    shipped: List[EvalQuestion] = []
    dropped: List[Dict[str, Any]] = []
    entries: List[Dict[str, Any]] = []
    for question in questions:
        values, drop = _check_question(question, [con])
        if drop is not None:
            dropped.append(drop)
            continue
        shipped.append(question)
        entries.append({"id": question.id, "gold_sql": question.gold_sql,
                        "expected": question.expected_answer, "observed": values[0],
                        "match": True})
    return shipped, dropped, entries


def build_evalpack(
    schema: "SchemaConfig",
    output_dir: Any,
    *,
    tables: Optional[Dict[str, "pd.DataFrame"]] = None,
    rotations: int = 1,
) -> EvalPackResult:
    """Generate a database from ``schema`` and emit a verified evalpack.

    Every candidate question's expected answer derives from the *declared*
    spec (outcome-curve targets, allocation plan, rate anchors, FK
    relationships). The written CSVs are then loaded with DuckDB and every
    gold SQL is executed against them; only questions whose observed answer
    exactly matches the declared answer are shipped. Failures are recorded
    in ``manifest.json`` under ``dropped_questions``.

    With ``rotations=N`` the pack holds N databases generated from seeds
    ``seed, seed + 1, ...`` under ``rotations/seed-<n>/``. They share every
    declared answer and differ in every row, so a question ships only when
    its answer holds on all of them, and a candidate query is scored correct
    only when it matches on all of them. The manifest records how often
    plausible wrong queries pass on one database against all of them.

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
                    schema+seed); when omitted, tables are generated. Only
                    valid with one rotation.
        rotations:  Number of databases in the pack.

    Returns:
        :class:`EvalPackResult`; check ``.all_verified``.
    """
    duckdb = _require_duckdb()
    import misata

    if rotations < 1:
        raise ValueError("rotations must be at least 1")
    if tables is not None and rotations > 1:
        raise ValueError("pre-generated tables fit one seed; omit them to build rotations")
    if schema.seed is None:
        import random

        schema.seed = random.randint(1, 2**31 - 1)
    seed = int(schema.seed)
    seeds = [seed + i for i in range(rotations)]

    # Per-row costs of a declaration (Prop-3 clamping, bound conflicts) ride
    # with the pack: all_match certifies the declared aggregates, not the rows.
    conformance_warnings: List[str] = []
    if getattr(schema, "outcome_curves", None):
        from misata.conformance import conformance_preview

        conformance_warnings = list(conformance_preview(schema).warnings)
        for w in conformance_warnings:
            print(f"⚠ evalpack conformance: {w}")

    out = Path(output_dir)
    dbs: List[_Database] = []
    for s in seeds:
        rotation_schema = schema.model_copy(deep=True)
        rotation_schema.seed = s
        rotation_tables = tables if tables is not None else misata.generate_from_schema(rotation_schema)
        directory = out if rotations == 1 else out / "rotations" / f"seed-{s}"
        dbs.append(_open_database(duckdb, rotation_schema, s, directory, rotation_tables))

    shipped, dropped, observed = _select_questions(dbs)
    spec_json = schema.model_dump_json()
    spec_hash = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()
    fk_integrity = [{"relationship": q.source["relationship"], "orphans": 0, "verified": True}
                    for q in shipped if q.source.get("kind") == "fk_integrity"]

    certificates = []
    for i, db in enumerate(dbs):
        entries = [{"id": q.id, "gold_sql": q.gold_sql, "expected": q.expected_answer,
                    "observed": observed[q.id][i], "match": True} for q in shipped]
        certificate = {
            "pack": schema.name,
            "misata_version": misata.__version__,
            "seed": db.seed,
            "spec_sha256": spec_hash,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "verifier": {"engine": "duckdb", "version": duckdb.__version__},
            "sql_dialect": "duckdb",
            "answer_comparison": ("numeric at round_decimals (never string equality); "
                                  "strings compared exactly"),
            "fk_integrity": fk_integrity,
            "conformance_warnings": conformance_warnings,
            "questions": entries,
            "all_match": bool(entries),
            "attestation": _attest(db),
        }
        certificates.append(certificate)
        if rotations > 1:
            _write_json(db.directory / "certificate.json", certificate)

    manifest: Dict[str, Any] = {
        "pack": schema.name,
        "misata_version": misata.__version__,
        "seed": seed,
        "seeds": seeds,
        "spec_sha256": spec_hash,
        "tables": {name: int(len(df)) for name, df in dbs[0].tables.items()},
        "questions_shipped": len(shipped),
        "questions_dropped": len(dropped),
        "dropped_questions": dropped,
        "conformance_warnings": conformance_warnings,
        "story_audit": _story_audit_block(dbs[0]),
        "schema": json.loads(spec_json),
    }
    if rotations == 1:
        root_certificate = certificates[0]
    else:
        manifest["rotations"] = [
            {"seed": db.seed, "directory": db.directory.relative_to(out).as_posix(),
             "tables": {name: int(len(df)) for name, df in db.tables.items()},
             "story_audit": _story_audit_block(db)}
            for db in dbs
        ]
        manifest["near_miss_study"] = _near_miss_study(shipped, dbs)
        root_certificate = {
            "pack": schema.name,
            "misata_version": misata.__version__,
            "seeds": seeds,
            "spec_sha256": spec_hash,
            "pass_rule": "a query is correct only when it matches on every rotation",
            "rotations": [{"seed": c["seed"], "all_match": c["all_match"],
                           "attestation": c["attestation"]} for c in certificates],
            "all_match": bool(shipped),
            "attestation": certificates[0]["attestation"],
        }
    for db in dbs:
        db.con.close()

    with open(out / "questions.jsonl", "w", encoding="utf-8") as fh:
        for q in shipped:
            fh.write(json.dumps(q.to_dict()) + "\n")
    _write_json(out / "certificate.json", root_certificate)
    _write_json(out / "manifest.json", manifest)
    from misata import evalpack_verify

    (out / "verify.py").write_text(Path(evalpack_verify.__file__).read_text(encoding="utf-8"),
                                   encoding="utf-8")
    (out / "README.md").write_text(_readme(schema.name, len(shipped), seeds), encoding="utf-8")

    return EvalPackResult(
        output_dir=out,
        questions=shipped,
        dropped=dropped,
        certificate=root_certificate,
        seed=seed,
        conformance_warnings=conformance_warnings,
        seeds=seeds,
    )


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def _readme(name: str, n_questions: int, seeds: List[int]) -> str:
    if len(seeds) == 1:
        where = "the CSV tables in `tables/`"
        databases = ""
        proof = "`attestation.intoto.json` pins every table"
    else:
        where = f"{len(seeds)} databases in `rotations/` (seeds {seeds[0]} to {seeds[-1]})"
        databases = f"""
The databases share every declared answer and differ in every row. A query
is correct only when it returns the expected answer on all {len(seeds)}, so a query
that depends on particular rows rather than on the question (a hard-coded
key, a `LIMIT` without `ORDER BY`) fails even when it fits one database.
`manifest.json` → `near_miss_study` records how often plausible wrong queries
pass on one database and on all of them.
"""
        proof = "each rotation's `attestation.intoto.json` pins its tables"
    return f"""# Evalpack: {name}

{n_questions} question/answer pairs over {where}.
Every expected answer was **declared before the data was generated** and then
verified by executing the gold SQL with DuckDB against these exact files.
{databases}
Re-verify yourself (30 seconds):

```bash
pip install duckdb
python verify.py
```

Score your own SQL, one `{{"id": "q001", "sql": "..."}}` per line:

```bash
python verify.py --candidates my_answers.jsonl
```

`certificate.json` records the verification run (DuckDB version, per-question
observed values, FK orphan counts). `manifest.json` records the generation
seed, the misata version, the spec hash, and every candidate question that
was dropped by the verification gate. {proof} by SHA-256 in an in-toto
Statement, and the `verify_attestation.py` beside it rechecks it.

Gold SQL is written in DuckDB dialect and verified with DuckDB. Numeric
answers must be compared numerically at each question's `round_decimals`
(JSON numbers cannot carry trailing zeros); never compare answers as strings.

Regenerate the identical pack from `manifest.json`'s schema + seed with
[misata](https://github.com/rasinmuhammed/misata), or change the seed to get
a fresh database with the same declared answers where applicable.
"""
