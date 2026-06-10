"""
Cross-table aggregate roll-ups: make parent summary columns reconcile with child rows.

The realism gap this closes: a ``customers.total_spent`` column generated independently of
that customer's actual ``orders.amount`` rows will not survive a single ``GROUP BY ... JOIN``
query. Real relational data reconciles. This module computes parent summary columns from the
true child-level facts after both tables are generated, so the numbers add up.

Declaration lives inside a column's ``distribution_params`` under the ``rollup`` key, matching
the existing idiom (``formula``, ``depends_on``, ``inherits_curve_from``)::

    Column(name="total_spent", type="float", distribution_params={
        "rollup": {
            "from_table": "orders",   # child table to aggregate
            "fk": "customer_id",      # child column that references this table's PK
            "agg": "sum",             # sum | count | mean | max | min
            "column": "amount",       # child column to aggregate (omit for count)
        }
    })

If the explicit declaration is absent, :func:`infer_rollups` can detect common conventions
from column names (``total_*``, ``*_count``, ``num_*``) against the relationship graph, so the
zero-config path produces reconciling data too.

Roll-ups run in a post-generation pass once parent and child tables are both materialized;
see ``DataSimulator`` for the buffering that makes both available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd


_VALID_AGGS = {"sum", "count", "mean", "max", "min"}


@dataclass
class RollupSpec:
    """A resolved roll-up: write ``target_column`` on ``parent_table`` from child facts."""
    parent_table: str
    target_column: str
    from_table: str
    fk: str            # child column referencing the parent PK
    parent_key: str    # the parent PK the fk points at
    agg: str
    column: Optional[str] = None   # child column to aggregate; None for count
    fillna: float = 0.0            # parents with no children get this
    where: Optional[Dict[str, Any]] = None   # equality filter on child rows, e.g.
    #                                          {"status": "completed"} or {"status": ["a","b"]}


# --------------------------------------------------------------------------- #
# Explicit declarations
# --------------------------------------------------------------------------- #

def collect_declared_rollups(config: Any) -> List[RollupSpec]:
    """Pull explicit ``rollup`` declarations out of the schema's columns."""
    specs: List[RollupSpec] = []
    for table_name, cols in config.columns.items():
        parent_key = _primary_key_of(config, table_name)
        for col in cols:
            decl = (col.distribution_params or {}).get("rollup")
            if not isinstance(decl, dict):
                continue
            agg = str(decl.get("agg", "sum")).lower()
            if agg not in _VALID_AGGS:
                continue
            fk = decl.get("fk")
            from_table = decl.get("from_table")
            if not fk or not from_table:
                continue
            where = decl.get("where")
            specs.append(RollupSpec(
                parent_table=table_name,
                target_column=col.name,
                from_table=from_table,
                fk=fk,
                parent_key=decl.get("parent_key", parent_key),
                agg=agg,
                column=decl.get("column"),
                fillna=float(decl.get("fillna", 0.0)),
                where=where if isinstance(where, dict) else None,
            ))
    return specs


# --------------------------------------------------------------------------- #
# Convention-based inference (zero-config)
# --------------------------------------------------------------------------- #

# (regex on the parent column name, agg, group index naming the noun)
# Deliberately conservative. Every rule REQUIRES a noun that must name an actual child table
# (enforced in _pick_child_for), because aggregate-shaped names are ambiguous: "stock_count"
# is inventory, not a count of child rows; "rating" is not a roll-up. We would rather infer
# nothing than write a wrong number — the explicit `rollup` declaration covers the rest.
_NAME_RULES = [
    (re.compile(r"^(total|sum)_(.+)$"),   "sum",   2),   # total_orders -> sum over orders
    (re.compile(r"^num_(.+)$"),           "count", 1),   # num_orders   -> count of orders
    (re.compile(r"^(.+)_count$"),         "count", 1),   # order_count  -> count of orders
    (re.compile(r"^avg_(.+)$"),           "mean",  1),   # avg_order... -> mean over orders
]


def infer_rollups(config: Any, tables_present: Optional[set] = None) -> List[RollupSpec]:
    """Infer roll-ups from column-name conventions against the relationship graph.

    Only fires when (a) the parent column name matches a known aggregate convention, (b) the
    parent has a child via a declared relationship, and (c) a plausible child column to
    aggregate exists (for sum/mean/max/min). Count needs no child column. Conservative by
    design: when in doubt it produces nothing rather than a wrong number.
    """
    specs: List[RollupSpec] = []
    # parent_table -> list of (child_table, fk_col, parent_key)
    children = _children_by_parent(config)

    for table_name, cols in config.columns.items():
        kids = children.get(table_name, [])
        if not kids:
            continue
        parent_key = _primary_key_of(config, table_name)
        existing_targets = {
            s.target_column for s in collect_declared_rollups(config)
            if s.parent_table == table_name
        }
        for col in cols:
            if col.name in existing_targets:
                continue   # explicit declaration wins
            if (col.distribution_params or {}).get("rollup"):
                continue
            match = _match_name_rule(col.name)
            if match is None:
                continue
            agg, noun = match
            child = _pick_child_for(noun, kids, config, agg)
            if child is None:
                continue
            child_table, fk_col, _pk = child
            child_col = None
            if agg in ("sum", "mean", "max", "min"):
                child_col = _pick_numeric_child_column(config, child_table, noun)
                if child_col is None:
                    continue
            specs.append(RollupSpec(
                parent_table=table_name,
                target_column=col.name,
                from_table=child_table,
                fk=fk_col,
                parent_key=parent_key,
                agg=agg,
                column=child_col,
            ))
    return specs


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #

def apply_rollups(tables: Dict[str, pd.DataFrame], specs: List[RollupSpec]) -> Dict[str, pd.DataFrame]:
    """Write each roll-up's aggregate into the parent column. Mutates and returns ``tables``."""
    for spec in specs:
        parent = tables.get(spec.parent_table)
        child = tables.get(spec.from_table)
        if parent is None or child is None:
            continue
        if spec.parent_key not in parent.columns or spec.fk not in child.columns:
            continue
        if spec.agg != "count" and (spec.column is None or spec.column not in child.columns):
            continue

        # Optional equality filter: aggregate only child rows matching `where`
        # (e.g. total_completed = sum(amount where status == "completed")). Scalar matches
        # one value; a list matches any. Unknown filter columns are ignored (no silent
        # wrong number — the filter simply does not narrow on a column that is not there).
        if spec.where:
            mask = pd.Series(True, index=child.index)
            for fcol, fval in spec.where.items():
                if fcol not in child.columns:
                    continue
                if isinstance(fval, (list, tuple, set)):
                    mask &= child[fcol].isin(list(fval))
                else:
                    mask &= (child[fcol] == fval)
            child = child[mask]

        if spec.agg == "count":
            grouped = child.groupby(spec.fk).size()
        else:
            grouped = child.groupby(spec.fk)[spec.column].agg(spec.agg)

        mapped = parent[spec.parent_key].map(grouped)
        if spec.agg == "count":
            mapped = mapped.fillna(0)
        else:
            mapped = mapped.fillna(spec.fillna)

        # Preserve integer-ness for counts and originally-int columns.
        if spec.agg == "count" or pd.api.types.is_integer_dtype(parent[spec.target_column]):
            mapped = mapped.round().astype("int64")
        tables[spec.parent_table][spec.target_column] = mapped.values
    return tables


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _primary_key_of(config: Any, table_name: str) -> str:
    """Best-effort primary key: a unique int column, else <table_singular>_id, else 'id'."""
    for col in config.columns.get(table_name, []):
        if col.unique and col.type in ("int",):
            return col.name
    singular = table_name[:-1] if table_name.endswith("s") else table_name
    names = {c.name for c in config.columns.get(table_name, [])}
    for cand in (f"{singular}_id", f"{table_name}_id", "id"):
        if cand in names:
            return cand
    return f"{singular}_id"


def _children_by_parent(config: Any) -> Dict[str, List[tuple]]:
    out: Dict[str, List[tuple]] = {}
    for rel in getattr(config, "relationships", []) or []:
        out.setdefault(rel.parent_table, []).append(
            (rel.child_table, rel.child_key, rel.parent_key))
    return out


def _match_name_rule(name: str):
    low = name.lower()
    for rx, agg, group in _NAME_RULES:
        m = rx.match(low)
        if m:
            noun = m.group(group) if group else None
            return agg, noun
    return None


def _pick_child_for(noun: Optional[str], kids: List[tuple], config: Any, agg: str):
    """Choose which child table the roll-up aggregates over — only when the noun *names* a
    child table. ``total_orders``/``order_count`` -> the ``orders`` child. We do NOT guess
    from a lone child, because aggregate-shaped names (``total_sales``, ``stock_count``) often
    refer to something other than 'all rows of the one child table'. Naming the table is the
    signal that the user means a row-level roll-up."""
    if not noun:
        return None
    forms = {noun, noun + "s", noun.rstrip("s")}
    for child_table, fk, pk in kids:
        ct = child_table.lower()
        if ct in forms or ct.rstrip("s") in forms:
            return (child_table, fk, pk)
    return None


def _pick_numeric_child_column(config: Any, child_table: str, noun: Optional[str]) -> Optional[str]:
    """Pick the child column to aggregate: a noun-name match first, else the obvious money/qty
    column, else the single numeric non-key column."""
    cols = config.columns.get(child_table, [])
    numeric = [c for c in cols
               if c.type in ("int", "float") and not c.unique
               and c.type != "foreign_key" and not c.name.endswith("_id")]
    if not numeric:
        return None
    if noun:
        for c in numeric:
            if c.name.lower() == noun or noun in c.name.lower():
                return c.name
    for pref in ("amount", "total", "price", "value", "revenue", "cost", "quantity", "qty"):
        for c in numeric:
            if pref in c.name.lower():
                return c.name
    if len(numeric) == 1:
        return numeric[0].name
    return None
