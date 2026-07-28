"""Which declarations own which column, and who writes last.

Every declaration in Misata is verified individually. Nothing checked that N of
them on the same table compose, and the record says that is where the bugs are:

* 0.8.8.5 — an inferred roll-up overwrote a declared curve, 23% off.
* 0.9.2 — `null_rate` ran after `apply_constraints` and silently undid a
  declared `when_then ... not_null` on 77 rows.
* 0.9.2 — `TimeGrid` moved a timestamp backwards after causality had placed it,
  so 86 tickets predated their own customer.
* 0.9.2 — `EventLog` reassigned a row's owner and left its other foreign key
  pointing into the previous tenant.

Four ordering defects, all found by accident. This module looks on purpose.

It is deliberately **static**: it reads the schema and reports which declarations
claim the same column, ranked by whether the later writer can actually destroy
the earlier one's guarantee. That is a different question from `feasibility`,
which asks whether declarations are arithmetically compatible. Two declarations
can be perfectly compatible and still fight over who writes last.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# The order passes actually run in, latest last. Read off `simulator.py` rather
# than remembered: the first version of this list put `lifecycle` before
# `null_rate` and the tool immediately reported four confident false positives
# on a suite that was 110/110. A composition checker that is wrong about the
# order is worse than not having one.
#
#   per batch      (simulator.py ~3035-3129)
#   identity phase (simulator.py ~5343-5613)
PASS_ORDER = [
    # per batch, in pipeline order
    "columns", "formula", "causality", "constraints", "null_rate",
    # identity phase, in pipeline order
    "lifecycle", "group_shares", "waterfall", "stock_flow", "scd2", "rollup",
    "curve", "graphs", "bitemporal", "event_log",
    # dynamics, last, in apply_dynamics order
    "retention", "late_arrival", "time_grid", "missingness", "outliers",
    "typos", "duplicates",
]
_RANK = {name: i for i, name in enumerate(PASS_ORDER)}


@dataclass
class Claim:
    """One declaration's claim on one column."""

    table: str
    column: str
    declaration: str          # human name, e.g. "time_grids"
    pass_name: str            # entry in PASS_ORDER
    writes: bool = True       # False when it only reads the column

    @property
    def rank(self) -> int:
        return _RANK.get(self.pass_name, len(PASS_ORDER))


@dataclass
class Overlap:
    """Two writers on one column, in the order they actually run."""

    table: str
    column: str
    earlier: str
    later: str
    note: str

    def __str__(self) -> str:
        return (f"[{self.table}.{self.column}] {self.later} runs after "
                f"{self.earlier}\n      {self.note}")


def _claims(config: Any) -> List[Claim]:
    out: List[Claim] = []

    def add(table, column, decl, pass_name, writes=True):
        if table and column:
            out.append(Claim(table, column, decl, pass_name, writes))

    for t, cols in (getattr(config, "columns", None) or {}).items():
        for c in cols or []:
            p = c.distribution_params or {}
            if "formula" in p:
                add(t, c.name, "formula", "formula")
            if "rollup" in p:
                add(t, c.name, "rollup", "rollup")
            if p.get("null_rate"):
                add(t, c.name, "null_rate", "null_rate")

    for table in (getattr(config, "tables", None) or []):
        for con in (getattr(table, "constraints", None) or []):
            for attr in ("column", "then_column", "column_a", "column_b"):
                col = getattr(con, attr, None)
                if col:
                    add(table.name, col, f"constraint '{con.name}'",
                        "constraints", writes=attr != "column_b")
        if getattr(table, "scd2", None):
            s = table.scd2
            for key in ("valid_from", "valid_to", "current_flag"):
                add(table.name, s.get(key) if isinstance(s, dict)
                    else getattr(s, key, None), "scd2", "scd2")

    for lc in (getattr(config, "lifecycles", None) or []):
        add(lc.table, lc.state_column, f"lifecycle '{lc.name}'", "lifecycle")
        for st in lc.states:
            add(lc.table, getattr(st, "timestamp", None),
                f"lifecycle '{lc.name}'", "lifecycle")

    for spec in (getattr(config, "outcome_curves", None) or []):
        add(spec.table, getattr(spec, "measure", None), "outcome_curve", "curve")
    for spec in (getattr(config, "group_shares", None) or []):
        add(spec.table, getattr(spec, "measure", None), "group_shares",
            "group_shares")
    for spec in (getattr(config, "bitemporal", None) or []):
        for key in ("valid_from", "valid_to", "recorded_at", "superseded_at"):
            add(spec.table, getattr(spec, key), f"bitemporal '{spec.name}'",
                "bitemporal")
    for spec in (getattr(config, "dag_edges", None) or []):
        add(spec.table, spec.from_column, f"dag_edges '{spec.name}'", "graphs")
        add(spec.table, spec.to_column, f"dag_edges '{spec.name}'", "graphs")
    for spec in (getattr(config, "closures", None) or []):
        for key in ("ancestor_column", "descendant_column", "depth_column"):
            add(spec.table, getattr(spec, key, None), f"closure '{spec.name}'",
                "graphs")
    for spec in (getattr(config, "event_logs", None) or []):
        for key in ("event_type_column", "event_time_column", "entity_key"):
            add(spec.table, getattr(spec, key), f"event_log '{spec.name}'",
                "event_log")
    for spec in (getattr(config, "retention", None) or []):
        add(spec.table, spec.cohort_key, "retention", "retention")
        add(spec.table, spec.event_time, "retention", "retention")
    for spec in (getattr(config, "late_arrivals", None) or []):
        add(spec.table, spec.ingest_time, "late_arrivals", "late_arrival")
    for spec in (getattr(config, "time_grids", None) or []):
        add(spec.table, spec.column, "time_grids", "time_grid")
    for spec in (getattr(config, "missingness", None) or []):
        add(spec.table, spec.column, "missingness", "missingness")
    for spec in (getattr(config, "outliers", None) or []):
        add(spec.table, spec.column, "outliers", "outliers")
    for spec in (getattr(config, "typos", None) or []):
        add(spec.table, spec.column, "typos", "typos")
    for spec in (getattr(config, "duplicates", None) or []):
        for c in (spec.subset or []):
            add(spec.table, c, "duplicates", "duplicates")
    return out


# Pairs worth a second look, with the sentence explaining what to check.
#
# These are stated as facts about ORDER, never as claims of breakage. A static
# reader cannot know whether the later pass happens to produce the same result:
# the first version of this file announced that three declared null rates "will
# not hold" on a schema where all three held exactly, because the rates had been
# chosen to agree with the lifecycle's weights. Report what is true (who writes
# last) and let the audit report what actually came out.
_DESTRUCTIVE: Dict[Tuple[str, str], str] = {
    ("null_rate", "lifecycle"):
        "the lifecycle writes this timestamp last, so the emitted null rate is "
        "whatever its state weights imply; the declared null_rate only holds if "
        "the two agree",
    ("constraints", "null_rate"):
        "null_rate runs after constraints and could undo a "
        "`when_then ... not_null`; 0.9.2 made the pass skip protected rows, so "
        "this is a guard against that protection being lost",
    ("causality", "time_grid"):
        "a grid that moved a timestamp backwards would undo causality; "
        "TimeGrid is forward-only for exactly this reason",
    ("formula", "missingness"):
        "if this column is an input to a formula, nulling it afterwards leaves "
        "the derived column computed from a value no longer present",
    ("rollup", "duplicates"):
        "duplicated rows are real rows, so any roll-up over this table counts "
        "them; check the parent total is still the one you declared",
    ("curve", "duplicates"):
        "duplicated rows are counted in the curve's period totals",
    ("rollup", "outliers"):
        "outliers are placed after the roll-up, so the parent total will not "
        "match unless the roll-up is recomputed",
    ("curve", "outliers"):
        "outliers are placed after the curve, so a period total will move",
    ("event_log", "retention"):
        "retention reassigns event ownership after the event log matched it to "
        "each entity's state; one of the two will not survive",
}


def find_overlaps(config: Any) -> List[Overlap]:
    """Columns two or more declarations write, in the order they run."""
    by_col: Dict[Tuple[str, str], List[Claim]] = {}
    for c in _claims(config):
        if c.writes:
            by_col.setdefault((c.table, c.column), []).append(c)

    out: List[Overlap] = []
    for (table, column), claims in sorted(by_col.items()):
        names = {c.declaration for c in claims}
        if len(names) < 2:
            continue
        claims.sort(key=lambda c: c.rank)
        for i in range(len(claims) - 1):
            a, b = claims[i], claims[i + 1]
            if a.declaration == b.declaration:
                continue
            note = _DESTRUCTIVE.get((a.pass_name, b.pass_name))
            out.append(Overlap(
                table=table, column=column,
                earlier=a.declaration, later=b.declaration,
                note=note or ("both write this column; the later one wins, "
                              "which may or may not be what was intended"),
            ))
    return out


def composition_report(config: Any) -> str:
    """A readable summary, for `misata lint` and for humans."""
    overlaps = find_overlaps(config)
    if not overlaps:
        return "No column is written by more than one declaration."
    risky = [o for o in overlaps
             if "may or may not be what was intended" not in o.note]
    lines = [f"{len(overlaps)} column(s) are written by more than one "
             f"declaration ({len(risky)} worth checking, because the later pass "
             f"decides the outcome):"]
    for i, o in enumerate(sorted(overlaps,
                                 key=lambda x: ("may or may not" in x.note,
                                                x.table, x.column)), 1):
        lines.append(f"  {i}. {o}")
    return "\n".join(lines)
