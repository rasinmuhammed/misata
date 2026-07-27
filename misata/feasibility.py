"""Refuse contradictory declarations, with the arithmetic that proves it.

The behaviour that separates a declarative engine from a generator with a lot of
options is what it does when two declarations cannot both hold. A generator
picks one and carries on. A declarative engine refuses, names both declarations,
shows the arithmetic, and says what to change — the way a compiler does.

Misata previously warned and then proceeded. Empirically:

    declared:  smb .6 / mid .6 / ent .3   (sums to 1.5)
    realised:  smb .4 / mid .4 / ent .2   ← a specification nobody wrote

    declared:  200 rows, unique id capped at 50
    realised:  ids up to 301               ← the declared bound overridden

Both emitted a warning first, which is worse than it sounds rather than better:
a warning that the engine has substituted its own specification still leaves the
user holding data that violates what they asked for, and the file looks
authoritative afterwards. 0.8.8.5 was this class of defect (an inferred roll-up
overwrote a declared curve, 23% off) and it is why this module exists.

Scope discipline: a conflict is reported only when the declarations are
**arithmetically incompatible**, never when they are merely unusual or when the
engine can satisfy both. False refusals are worse than the warnings they
replace, because they block work that was actually valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from misata.exceptions import SchemaValidationError


@dataclass
class Conflict:
    """One arithmetically impossible combination of declarations."""

    kind: str
    where: str                     # "table.column" or "table"
    declarations: List[str]        # the named declarations that clash
    arithmetic: str                # the sum/count that proves it
    remedy: str                    # what to change

    def __str__(self) -> str:
        decls = " vs ".join(self.declarations) if len(self.declarations) > 1 \
            else self.declarations[0]
        return (f"[{self.where}] {decls}\n"
                f"      {self.arithmetic}\n"
                f"      → Suggestion: {self.remedy}")


class InfeasibleSchema(SchemaValidationError):
    """Raised when declarations cannot all hold at once.

    Subclasses :class:`SchemaValidationError`, so callers already catching
    schema problems keep working. ``.conflicts`` carries every conflict found,
    not only the first, because fixing them one run at a time is miserable.
    """

    def __init__(self, conflicts: List[Conflict]):
        self.conflicts = conflicts
        n = len(conflicts)
        body = "\n".join(f"  {i}. {c}" for i, c in enumerate(conflicts, 1))
        message = (
            f"{n} declaration{'s' if n != 1 else ''} cannot be satisfied "
            f"together:\n{body}"
        )
        super().__init__(message)

    def __str__(self) -> str:   # the base class prefixes with [field]; not wanted here
        return self.message


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _columns_of(config: Any, table: str) -> Dict[str, Any]:
    return {c.name: c for c in (config.columns.get(table, []) or [])}


def _numeric_range(col: Any) -> Optional[tuple]:
    p = col.distribution_params or {}
    lo, hi = p.get("min"), p.get("max")
    if lo is None or hi is None:
        return None
    try:
        return float(lo), float(hi)
    except (TypeError, ValueError):
        return None


def _row_count(config: Any, table: str) -> Optional[int]:
    for t in config.tables:
        if t.name == table:
            return t.row_count
    return None


def _choices(col: Any) -> Optional[Set[str]]:
    p = col.distribution_params or {}
    ch = p.get("choices")
    if isinstance(ch, (list, tuple, set)) and ch:
        return {str(x) for x in ch}
    return None


# --------------------------------------------------------------------------- #
# individual checks
# --------------------------------------------------------------------------- #

def _check_group_shares(config: Any) -> List[Conflict]:
    out: List[Conflict] = []
    for spec in (getattr(config, "group_shares", None) or []):
        cols = _columns_of(config, spec.table)
        total = sum(float(v) for v in spec.shares.values())
        if total > 1.005:
            out.append(Conflict(
                kind="shares_exceed_whole",
                where=f"{spec.table}.{spec.group_column}",
                declarations=[f"group_shares on {spec.measure}"],
                arithmetic=(f"declared shares sum to {total:.3f} "
                            f"({', '.join(f'{k}={v}' for k, v in spec.shares.items())}); "
                            f"a share of a whole cannot exceed 1.0"),
                remedy=("scale the shares so they sum to 1.0, or drop a group. "
                        "Misata will not renormalise them for you, because the "
                        "result would be a specification you did not write"),
            ))
        col = cols.get(spec.group_column)
        if col is not None:
            declared = _choices(col)
            if declared:
                unknown = sorted(set(spec.shares) - declared)
                if unknown:
                    out.append(Conflict(
                        kind="shares_name_absent_group",
                        where=f"{spec.table}.{spec.group_column}",
                        declarations=[f"group_shares on {spec.measure}",
                                      f"choices on {spec.group_column}"],
                        arithmetic=(f"shares name {unknown}, which are not among "
                                    f"the column's choices {sorted(declared)}"),
                        remedy=(f"add {unknown} to the column's choices, or use a "
                                f"group name that exists"),
                    ))
    return out


def _check_numeric_ranges(config: Any) -> List[Conflict]:
    out: List[Conflict] = []
    for table, cols in (config.columns or {}).items():
        rows = _row_count(config, table)
        for col in cols:
            rng = _numeric_range(col)
            if rng is None:
                continue
            lo, hi = rng
            if lo > hi:
                out.append(Conflict(
                    kind="inverted_range",
                    where=f"{table}.{col.name}",
                    declarations=[f"min/max on {col.name}"],
                    arithmetic=f"min={lo:g} is greater than max={hi:g}",
                    remedy="swap the bounds",
                ))
                continue
            # A unique integer column cannot hold more distinct values than its
            # range contains. Extending the range silently, which is what the
            # engine used to do, violates the declared max.
            if col.unique and col.type in ("int", "integer") and rows:
                capacity = int(hi) - int(lo) + 1
                if capacity < rows:
                    out.append(Conflict(
                        kind="unique_range_too_narrow",
                        where=f"{table}.{col.name}",
                        declarations=[f"unique + min/max on {col.name}",
                                      f"row_count on {table}"],
                        arithmetic=(f"{rows} unique values needed but the range "
                                    f"[{int(lo)}, {int(hi)}] holds only {capacity}"),
                        remedy=(f"raise max to at least {int(lo) + rows - 1}, "
                                f"lower row_count to {capacity}, or drop unique"),
                    ))
    return out


def _check_inequalities(config: Any) -> List[Conflict]:
    """An inequality between columns whose declared ranges cannot satisfy it."""
    out: List[Conflict] = []
    ops = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
           "<": lambda a, b: a < b, "<=": lambda a, b: a <= b}
    for table in (config.columns or {}):
        tbl = next((t for t in config.tables if t.name == table), None)
        if tbl is None:
            continue
        cols = _columns_of(config, table)
        for c in (getattr(tbl, "constraints", None) or []):
            if getattr(c, "type", None) != "inequality":
                continue
            a, b, op = c.column_a, c.column_b, c.operator
            if not (a in cols and b in cols and op in ops):
                continue
            ra, rb = _numeric_range(cols[a]), _numeric_range(cols[b])
            if ra is None or rb is None:
                continue
            # Best case for the inequality: a at its max, b at its min.
            if op in (">", ">="):
                satisfiable = ops[op](ra[1], rb[0])
                best = f"max({a})={ra[1]:g} vs min({b})={rb[0]:g}"
            else:
                satisfiable = ops[op](ra[0], rb[1])
                best = f"min({a})={ra[0]:g} vs max({b})={rb[1]:g}"
            if not satisfiable:
                out.append(Conflict(
                    kind="unsatisfiable_inequality",
                    where=f"{table}.{a}",
                    declarations=[f"constraint '{c.name}' ({a} {op} {b})",
                                  f"min/max on {a} and {b}"],
                    arithmetic=(f"no value can satisfy {a} {op} {b}: "
                                f"even in the best case, {best}"),
                    remedy=(f"widen the range of {a} or {b} so they overlap, "
                            f"or remove the constraint"),
                ))
    return out


def _check_column_governance(config: Any) -> List[Conflict]:
    """Two declarations that each claim exclusive authorship of one column.

    An outcome curve is an exact promise about a column's per-period totals. A
    roll-up recomputes that column from child rows. Whichever runs last wins,
    which is the 0.8.8.5 defect.
    """
    out: List[Conflict] = []
    curve_owned = {}
    for cur in (getattr(config, "outcome_curves", None) or []):
        curve_owned[(cur.table, cur.column)] = cur
    for table, cols in (config.columns or {}).items():
        for col in cols:
            decl = (col.distribution_params or {}).get("rollup")
            if not isinstance(decl, dict):
                continue
            if (table, col.name) in curve_owned:
                out.append(Conflict(
                    kind="two_owners_one_column",
                    where=f"{table}.{col.name}",
                    declarations=[f"outcome_curve on {table}.{col.name}",
                                  f"rollup on {table}.{col.name}"],
                    arithmetic=(f"the curve fixes {col.name}'s per-period totals "
                                f"while the rollup recomputes it as "
                                f"{decl.get('agg', 'sum')}({decl.get('from_table')}"
                                f".{decl.get('column', 'rows')}); both cannot hold "
                                f"unless the children happen to sum to the curve"),
                    remedy=(f"drop one. Keep the curve to control the total, or "
                            f"keep the rollup and put the curve on "
                            f"{decl.get('from_table')}.{decl.get('column')} instead"),
                ))
    return out


def _check_lifecycles(config: Any) -> List[Conflict]:
    out: List[Conflict] = []
    seen: Dict[tuple, str] = {}
    for spec in (getattr(config, "lifecycles", None) or []):
        key = (spec.table, spec.state_column)
        if key in seen:
            out.append(Conflict(
                kind="two_lifecycles_one_column",
                where=f"{spec.table}.{spec.state_column}",
                declarations=[f"lifecycle '{seen[key]}'", f"lifecycle '{spec.name}'"],
                arithmetic=(f"both machines govern {spec.state_column}; the second "
                            f"would overwrite the first's states entirely"),
                remedy="keep one lifecycle per state column",
            ))
        else:
            seen[key] = spec.name

        # Weights placed on states the transitions cannot reach.
        if spec.weights:
            bad = sorted(s for s, w in spec.weights.items()
                         if w and spec.path_to(s) is None)
            if bad:
                out.append(Conflict(
                    kind="weight_on_unreachable_state",
                    where=f"{spec.table}.{spec.state_column}",
                    declarations=[f"lifecycle '{spec.name}' weights",
                                  f"lifecycle '{spec.name}' transitions"],
                    arithmetic=(f"state(s) {bad} carry a non-zero share but no "
                                f"path reaches them from "
                                f"'{spec.initial or spec.states[0].name}'"),
                    remedy=(f"add transitions that reach {bad}, or set their "
                            f"weights to zero"),
                ))

        # A when_then rule that contradicts the machine's own implication.
        tbl = next((t for t in config.tables if t.name == spec.table), None)
        for c in (getattr(tbl, "constraints", None) or []) if tbl else []:
            if getattr(c, "type", None) != "when_then":
                continue
            if c.when_column != spec.state_column or c.when_op != "==":
                continue
            state = c.when_value
            path = spec.path_to(state) if isinstance(state, str) else None
            if path is None:
                continue
            owner = next((s for s in spec.states
                          if s.timestamp == c.then_column), None)
            if owner is None:
                continue
            on_path = owner.name in set(path)
            # Machine says populated; rule says null (or vice versa).
            if (on_path and c.then == "null") or (not on_path and c.then == "not_null"):
                out.append(Conflict(
                    kind="rule_contradicts_lifecycle",
                    where=f"{spec.table}.{c.then_column}",
                    declarations=[f"constraint '{c.name}'", f"lifecycle '{spec.name}'"],
                    arithmetic=(
                        f"the machine's path to '{state}' is {' → '.join(path)}, so "
                        f"'{owner.name}' is {'on' if on_path else 'not on'} it and "
                        f"{c.then_column} must be "
                        f"{'populated' if on_path else 'NULL'}; the constraint "
                        f"requires {c.then}"),
                    remedy=(f"remove constraint '{c.name}' — the lifecycle already "
                            f"implies the correct rule — or change the machine"),
                ))
    return out


def _check_min_children(config: Any) -> List[Conflict]:
    out: List[Conflict] = []
    for rel in (getattr(config, "relationships", None) or []):
        n = int(getattr(rel, "min_children", 0) or 0)
        if n <= 0:
            continue
        parents = _row_count(config, rel.parent_table)
        children = _row_count(config, rel.child_table)
        if not parents or not children:
            continue
        needed = n * parents
        if needed > children:
            out.append(Conflict(
                kind="min_children_exceeds_capacity",
                where=f"{rel.child_table}.{rel.child_key}",
                declarations=[f"min_children={n} on "
                              f"{rel.parent_table}→{rel.child_table}",
                              f"row_count on {rel.child_table}"],
                arithmetic=(f"{parents} parents × {n} children = {needed} rows "
                            f"needed, but {rel.child_table} has only {children}"),
                remedy=(f"raise {rel.child_table}.row_count to at least {needed}, "
                        f"lower min_children, or reduce "
                        f"{rel.parent_table}.row_count"),
            ))
    return out


def _check_retention_budget(config: Any) -> List[Conflict]:
    """A retention curve needs at least one event row per active entity-period."""
    out: List[Conflict] = []
    for spec in (getattr(config, "retention", None) or []):
        cohort_rows = _row_count(config, spec.cohort_table)
        event_rows = _row_count(config, spec.table)
        if not cohort_rows or not event_rows:
            continue
        # Upper bound: every cohort member active at every declared offset.
        needed = int(sum(cohort_rows * float(f) for f in spec.curve.values()))
        if needed > event_rows:
            out.append(Conflict(
                kind="retention_exceeds_event_rows",
                where=f"{spec.table}.{spec.event_time}",
                declarations=[f"retention curve on {spec.table}",
                              f"row_count on {spec.table}"],
                arithmetic=(f"the curve needs about {needed} active "
                            f"entity-periods across {cohort_rows} cohort members "
                            f"but {spec.table} has only {event_rows} rows"),
                remedy=(f"raise {spec.table}.row_count to at least {needed}, "
                        f"lower the retention fractions, or shorten the curve"),
            ))
    return out


def _check_curve_point_shape(config: Any) -> List[Conflict]:
    """An absolute curve whose points carry `relative_value` is a silent 65,000x
    error waiting to happen. Found the hard way: `value_mode="absolute"` with
    `relative_value` keys produced totals in the billions against a declared
    100,000, with no warning at all."""
    out: List[Conflict] = []
    for cur in (getattr(config, "outcome_curves", None) or []):
        pts = [p for p in (cur.curve_points or []) if isinstance(p, dict)]
        if not pts:
            continue
        has_target = any("target_value" in p for p in pts)
        has_relative = any("relative_value" in p for p in pts)
        mode = getattr(cur, "value_mode", "auto")
        if mode == "absolute" and has_relative and not has_target:
            out.append(Conflict(
                kind="curve_point_shape_mismatch",
                where=f"{cur.table}.{cur.column}",
                declarations=[f'outcome_curve value_mode="absolute"',
                              "curve_points using relative_value"],
                arithmetic=("absolute mode reads `target_value`; these points "
                            "only carry `relative_value`, so the numbers would "
                            "be treated as multipliers and the totals would "
                            "land orders of magnitude away from the intent"),
                remedy=('rename the keys to `target_value` (and use `date` '
                        'rather than `month` for the x axis), or switch to '
                        'value_mode="relative"'),
            ))
    return out


_CHECKS = (
    _check_retention_budget,
    _check_curve_point_shape,
    _check_group_shares,
    _check_numeric_ranges,
    _check_inequalities,
    _check_column_governance,
    _check_lifecycles,
    _check_min_children,
)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def find_conflicts(config: Any) -> List[Conflict]:
    """Every arithmetically impossible combination in the schema."""
    conflicts: List[Conflict] = []
    for check in _CHECKS:
        try:
            conflicts.extend(check(config))
        except Exception:
            # A broken check must never block a valid schema. Feasibility is a
            # guard, not a gate that can fail closed on its own bug.
            continue
    return conflicts


def check_feasibility(config: Any) -> None:
    """Raise :class:`InfeasibleSchema` when declarations cannot all hold.

    Reports every conflict at once, because fixing them one run at a time is
    miserable and the arithmetic for each is independent.
    """
    conflicts = find_conflicts(config)
    if conflicts:
        raise InfeasibleSchema(conflicts)
