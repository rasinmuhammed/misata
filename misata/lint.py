"""Pre-generation schema lint: catch infeasible declarations before any rows.

Generation already refuses impossible declarations loudly (see the
failure-modes documentation), but a warning during a long run is easy to
miss and expensive to reach. ``misata lint`` runs the same feasibility
arithmetic against the schema alone, in milliseconds, with the message you
would otherwise meet mid-generation:

- aggregate targets versus declared per-row bounds (lo * n <= T <= hi * n)
- Prop. 3 row-count clamps that would inflate or deflate per-row values
- reversed or degenerate date ranges
- unique columns whose declared range cannot host the row count
- relationships pointing at tables or keys that do not exist
- group shares that cannot fit their buckets, or do not sum to 1
- waterfalls with more period-type cells than rows, or unsorted period labels
- rates outside 0..1

Severity: an ``error`` means generation will refuse or knowingly violate a
declaration; a ``warning`` means generation will proceed with a documented
sacrifice; ``info`` is advisory. Exit codes mirror ``misata audit``: 1 on
errors (or any finding with ``--strict``), 2 when the schema cannot be
parsed at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List

import pandas as pd

if TYPE_CHECKING:
    from misata.schema import SchemaConfig


@dataclass
class LintFinding:
    severity: str          # "error" | "warning" | "info"
    where: str             # "orders.revenue", "relationships[0]", ...
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"severity": self.severity, "where": self.where,
                "message": self.message}


def _columns_of(schema: "SchemaConfig", table: str) -> Dict[str, Any]:
    return {c.name: c for c in (schema.columns.get(table) or [])}


def _check_relationships(schema: "SchemaConfig") -> List[LintFinding]:
    out = []
    table_names = {t.name for t in schema.tables}
    for i, rel in enumerate(schema.relationships or []):
        where = f"relationships[{i}]"
        if rel.parent_table not in table_names:
            out.append(LintFinding("error", where,
                       f"parent table '{rel.parent_table}' does not exist"))
        elif rel.parent_key not in _columns_of(schema, rel.parent_table):
            out.append(LintFinding("error", where,
                       f"parent key '{rel.parent_table}.{rel.parent_key}' does not exist"))
        if rel.child_table not in table_names:
            out.append(LintFinding("error", where,
                       f"child table '{rel.child_table}' does not exist"))
        elif rel.child_key not in _columns_of(schema, rel.child_table):
            out.append(LintFinding("error", where,
                       f"child key '{rel.child_table}.{rel.child_key}' does not exist"))
    return out


def _check_date_ranges(schema: "SchemaConfig") -> List[LintFinding]:
    out = []
    for table in schema.tables:
        for col in schema.columns.get(table.name) or []:
            if col.type not in ("date", "datetime", "time"):
                continue
            params = col.distribution_params or {}
            start, end = params.get("start"), params.get("end")
            if not start or not end:
                continue
            try:
                s, e = pd.Timestamp(start), pd.Timestamp(end)
            except (TypeError, ValueError):
                out.append(LintFinding("error", f"{table.name}.{col.name}",
                           f"unparseable date range ({start!r} .. {end!r})"))
                continue
            if s > e:
                out.append(LintFinding(
                    "warning", f"{table.name}.{col.name}",
                    f"date range start {s.date()} is after end {e.date()}; "
                    f"generation will swap them with a warning"))
    return out


def _check_unique_ranges(schema: "SchemaConfig") -> List[LintFinding]:
    out = []
    for table in schema.tables:
        for col in schema.columns.get(table.name) or []:
            if not col.unique or col.type != "int":
                continue
            params = col.distribution_params or {}
            lo, hi = params.get("min"), params.get("max")
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
                capacity = int(hi) - int(lo) + 1
                if capacity < table.row_count:
                    out.append(LintFinding(
                        "warning", f"{table.name}.{col.name}",
                        f"unique range holds {capacity:,} values but the table "
                        f"declares {table.row_count:,} rows; generation will "
                        f"extend the max with a warning"))
    return out


def _check_rates(schema: "SchemaConfig") -> List[LintFinding]:
    out = []
    for i, rc in enumerate(schema.rate_curves or []):
        for point in rc.rate_points or []:
            rate = point.get("rate")
            if isinstance(rate, (int, float)) and not (0.0 <= float(rate) <= 1.0):
                out.append(LintFinding(
                    "error", f"rate_curves[{i}] ({rc.table}.{rc.column})",
                    f"rate {rate} in period {point.get('period')!r} is outside 0..1"))
    return out


def _check_curves(schema: "SchemaConfig") -> List[LintFinding]:
    """Bound feasibility and Prop. 3 clamps via the conformance preview."""
    out = []
    try:
        from misata.conformance import conformance_preview
        preview = conformance_preview(schema)
    except Exception as exc:
        return [LintFinding("warning", "outcome_curves",
                            f"conformance preview unavailable: {exc}")]
    for w in preview.global_warnings or []:
        out.append(LintFinding("warning", "schema", str(w)))
    for curve in preview.curves:
        where = f"{curve.table}.{curve.column}"
        sev = "warning" if curve.ame_achievable else "error"
        for w in curve.warnings or []:
            out.append(LintFinding(sev, where, str(w)))
        if not getattr(curve, "bounds_respected", True):
            out.append(LintFinding(
                "error", where,
                "a period target is infeasible under the column's declared "
                "min/max (lo*n <= target <= hi*n fails); the curve will take "
                "precedence and violate the bound"))
    return out


def _check_group_shares(schema: "SchemaConfig") -> List[LintFinding]:
    out = []
    for i, spec in enumerate(schema.group_shares or []):
        where = f"group_shares[{i}] ({spec.table}.{spec.measure})"
        cols = _columns_of(schema, spec.table)
        if not cols:
            out.append(LintFinding("error", where,
                       f"table '{spec.table}' does not exist"))
            continue
        for role, cname in (("measure", spec.measure),
                            ("group_column", spec.group_column)):
            if cname not in cols:
                out.append(LintFinding("error", where,
                           f"{role} column '{spec.table}.{cname}' does not exist"))
        positive = {k: v for k, v in (spec.shares or {}).items() if float(v) > 0}
        if not positive:
            out.append(LintFinding("error", where, "no positive shares declared"))
            continue
        s = sum(float(v) for v in positive.values())
        if abs(s - 1.0) > 0.005:
            out.append(LintFinding(
                "warning", where,
                f"shares sum to {s:.3f}; generation will normalise to 1 "
                f"with a warning"))
        table_cfg = next((t for t in schema.tables if t.name == spec.table), None)
        paired = any(c.table == spec.table and c.column == spec.measure
                     for c in (schema.outcome_curves or []))
        if table_cfg is not None:
            n_periods = max(
                (len(c.curve_points or []) for c in (schema.outcome_curves or [])
                 if c.table == spec.table and c.column == spec.measure),
                default=1,
            )
            # Every period bucket needs at least one row per positive-share
            # group; rows split across periods roughly evenly.
            per_bucket = table_cfg.row_count // max(n_periods, 1)
            if per_bucket < len(positive):
                out.append(LintFinding(
                    "error", where,
                    f"~{per_bucket} rows per period cannot host "
                    f"{len(positive)} positive-share groups; the bucket will "
                    f"be skipped as infeasible"))
        if not paired:
            out.append(LintFinding(
                "info", where,
                "no exact-target curve pairs with this measure: shares hold "
                "over the table total, and evalpacks will ship no group "
                "questions (totals would be measured, not declared)"))
    return out


def _check_waterfalls(schema: "SchemaConfig") -> List[LintFinding]:
    out = []
    for i, spec in enumerate(schema.waterfalls or []):
        where = f"waterfalls[{i}] ({spec.table})"
        cols = _columns_of(schema, spec.table)
        if not cols:
            out.append(LintFinding("error", where,
                       f"table '{spec.table}' does not exist"))
            continue
        for role, cname in (("period_column", spec.period_column),
                            ("type_column", spec.type_column),
                            ("amount_column", spec.amount_column)):
            if cname not in cols:
                out.append(LintFinding("error", where,
                           f"{role} '{spec.table}.{cname}' does not exist"))
        try:
            from misata.waterfall import declared_movements
            plan = declared_movements(spec)
        except Exception as exc:
            out.append(LintFinding("error", where, f"invalid declaration: {exc}"))
            continue
        cells = sum(len(ins) + len(outs) for _, _, ins, outs in plan)
        table_cfg = next((t for t in schema.tables if t.name == spec.table), None)
        if table_cfg is not None and table_cfg.row_count < cells:
            out.append(LintFinding(
                "error", where,
                f"{table_cfg.row_count} rows cannot host {cells} period-type "
                f"movements; the identity will be skipped as infeasible"))
        labels = [p for p, _, _, _ in plan]
        if labels != sorted(labels):
            out.append(LintFinding(
                "info", where,
                "period labels do not sort lexicographically in declaration "
                "order; evalpacks will ship no running-balance questions "
                "(their gold SQL filters with period <= label)"))
    return out


def lint_schema(schema: "SchemaConfig") -> List[LintFinding]:
    """Run every pre-generation check against a parsed schema."""
    findings: List[LintFinding] = []
    findings.extend(_check_relationships(schema))
    findings.extend(_check_date_ranges(schema))
    findings.extend(_check_unique_ranges(schema))
    findings.extend(_check_rates(schema))
    findings.extend(_check_curves(schema))
    findings.extend(_check_group_shares(schema))
    findings.extend(_check_waterfalls(schema))
    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: order.get(f.severity, 3))
    return findings
