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

import numpy as np
import pandas as pd

from misata.exceptions import ConformanceWarning, warn


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
    via: Optional[List[str]] = None   # intermediate tables between from_table and the
    #                                   parent, nearest first. customers.lifetime_value =
    #                                   sum(payments.amount) reached through orders is
    #                                   via=["orders"]: payments join orders on their
    #                                   relationship, and `fk` names the column on the
    #                                   LAST via table that references the parent
    #                                   (orders.customer_id). Multi-hop facts are how
    #                                   real schemas reconcile; a single fk cannot
    #                                   express them.


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
            via = decl.get("via")
            if via is not None and not (
                isinstance(via, list) and all(isinstance(v, str) for v in via)
            ):
                via = None   # malformed via: fall back to single-hop semantics
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
                via=via,
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
    (re.compile(r"^lifetime_(.+)$"),      "count", 1),   # lifetime_rides -> count of rides
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
            # An int-typed total_<child> ("total_missions") counts child rows;
            # only float totals sum a child measure.
            if agg == "sum" and getattr(col, "type", "") == "int":
                agg = "count"
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
    specs.extend(_infer_line_item_totals(config, existing=specs))
    return specs


# A parent monetary total that equals the sum of its line items. Distinct from
# the name-rule roll-ups above: the column is named for the parent entity
# (order_total, invoice_total, cart.total), not for the child, and the child is
# recognised by being an unambiguous line-item table. Kept strict so it never
# fires on an order that also has a payments child (which would double count).
_TOTAL_COL_RE = re.compile(r"^(grand_total|sub_?total|total|.+_total|.+_amount|amount)$")
_LINE_MEASURE_NAMES = ("line_total", "line_amount", "line_subtotal",
                       "extended_price", "extended_amount")
_LINE_TABLE_TOKENS = ("item", "items", "line", "lines", "detail", "details",
                      "lineitem", "orderline")


def _looks_like_line_item_child(config: Any, child_table: str):
    """Return the child's summable line-measure column when the child is
    unambiguously a line-item table, else None."""
    cols = config.columns.get(child_table, [])
    names = {c.name.lower(): c for c in cols}
    measure = next((n for n in _LINE_MEASURE_NAMES if n in names), None)
    ct = child_table.lower()
    table_is_line = any(tok in ct.split("_") or ct.endswith(tok)
                        for tok in _LINE_TABLE_TOKENS)
    if measure is None and not table_is_line:
        return None
    if measure is None:
        # A line table with no explicit line measure: sum a single obvious
        # money column if there is exactly one.
        money = [c.name for c in cols
                 if c.type == "float" and not c.unique and not c.name.endswith("_id")
                 and any(k in c.name.lower()
                         for k in ("total", "amount", "price", "subtotal"))]
        if len(money) != 1:
            return None
        measure = money[0]
    return measure


def _infer_line_item_totals(config: Any, existing: List[RollupSpec]) -> List[RollupSpec]:
    specs: List[RollupSpec] = []
    children = _children_by_parent(config)
    declared = {(s.parent_table, s.target_column) for s in existing}
    declared |= {(s.parent_table, s.target_column) for s in collect_declared_rollups(config)}
    for parent_table, cols in config.columns.items():
        kids = children.get(parent_table, [])
        if not kids:
            continue
        parent_key = _primary_key_of(config, parent_table)
        # Every line-item child of this parent (must be exactly one to fire).
        line_children = [
            (ct, fk, meas)
            for (ct, fk, _pk) in kids
            if (meas := _looks_like_line_item_child(config, ct)) is not None
        ]
        if len(line_children) != 1:
            continue
        child_table, fk_col, measure = line_children[0]
        for col in cols:
            if (parent_table, col.name) in declared:
                continue
            if (col.distribution_params or {}).get("rollup"):
                continue
            if col.type != "float":
                continue
            if not _TOTAL_COL_RE.match(col.name.lower()):
                continue
            specs.append(RollupSpec(
                parent_table=parent_table, target_column=col.name,
                from_table=child_table, fk=fk_col, parent_key=parent_key,
                agg="sum", column=measure,
            ))
            declared.add((parent_table, col.name))
    return specs


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #

def resolve_via_frame(
    spec: RollupSpec,
    tables: Dict[str, pd.DataFrame],
    relationships: List[Any],
) -> Optional[pd.DataFrame]:
    """Annotate the leaf table's rows with the parent-referencing fk found at the
    end of the ``via`` chain, so a multi-hop roll-up reduces to a plain groupby.

    For customers.lifetime_value = sum(payments.amount) via ["orders"]:
    payments rows are joined to orders on their declared relationship, which
    puts ``customer_id`` on every payment row. Returns None (caller skips, with
    a warning) when a hop's relationship is missing or a table is absent —
    a declared multi-hop must never silently aggregate the wrong path.
    """
    # Resolve the relationship for every hop first, so a broken chain is
    # detected before any merging happens.
    chain: List[Any] = []
    current = spec.from_table
    for hop in spec.via or []:
        rel = next((r for r in relationships
                    if r.parent_table == hop and r.child_table == current), None)
        if rel is None or hop not in tables:
            return None
        chain.append(rel)
        current = hop

    df = tables[spec.from_table]
    for i, rel in enumerate(chain):
        hop_df = tables[rel.parent_table]
        last = i == len(chain) - 1
        carry = spec.fk if last else chain[i + 1].child_key
        if rel.parent_key not in hop_df.columns or carry not in hop_df.columns:
            return None
        if rel.child_key not in df.columns:
            return None
        link = hop_df[[rel.parent_key] + ([carry] if carry != rel.parent_key else [])]
        link = link.drop_duplicates(subset=[rel.parent_key])
        df = df.merge(link, left_on=rel.child_key, right_on=rel.parent_key,
                      how="left", suffixes=("", "__misata_hop"))
        if carry + "__misata_hop" in df.columns:
            df[carry] = df[carry + "__misata_hop"]
            df = df.drop(columns=[carry + "__misata_hop"])
    return df


def apply_rollups(
    tables: Dict[str, pd.DataFrame],
    specs: List[RollupSpec],
    relationships: Optional[List[Any]] = None,
) -> Dict[str, pd.DataFrame]:
    """Write each roll-up's aggregate into the parent column. Mutates and returns ``tables``."""
    for spec in specs:
        parent = tables.get(spec.parent_table)
        child = tables.get(spec.from_table)
        if parent is None or child is None:
            continue
        if spec.via:
            resolved = (resolve_via_frame(spec, tables, relationships)
                        if relationships else None)
            if resolved is None or spec.fk not in resolved.columns:
                warn(
                    f"Roll-up '{spec.parent_table}.{spec.target_column}': the via chain "
                    f"{spec.via} could not be resolved from the declared relationships; "
                    f"the column keeps its generated values and will NOT reconcile.",
                    ConformanceWarning,
                )
                continue
            child = resolved
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
    # Compound child tables still name the noun as their head token:
    # lifetime_sessions -> training_sessions.
    for child_table, fk, pk in kids:
        ct = child_table.lower()
        if any(ct.endswith("_" + f) for f in forms if f):
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


# --------------------------------------------------------------------------- #
# Streaming: roll-ups accumulated while the child table streams past
# --------------------------------------------------------------------------- #

STREAMABLE_AGGS = ("count", "sum", "min", "max", "mean")


def is_streamable(spec: RollupSpec) -> bool:
    """A roll-up that can be built from per-batch partials: one foreign-key
    hop and an aggregate that merges (count, sum, min, max, and mean as
    sum / count)."""
    return not spec.via and spec.agg in STREAMABLE_AGGS


class _Partials:
    """One roll-up's per-parent row count and running aggregate.

    Each parent owns one slot in dense arrays, assigned when it first appears,
    so a batch costs time in its own size and never in the number of parents
    seen so far. The aggregate keeps the child column's dtype: integer sums
    stay exact and datetimes compare as datetimes. A mean divides by the
    non-null values, as ``groupby().mean()`` does over the whole table.
    """

    def __init__(self, agg: str) -> None:
        self.agg = agg
        self.slots: Dict[Any, int] = {}
        self.keys: List[Any] = []
        self.count = np.zeros(0, dtype=np.int64)
        self.nonnull = np.zeros(0, dtype=np.int64)
        self.value: Optional[np.ndarray] = None
        self.seen = np.zeros(0, dtype=bool)
        self.dtype: Any = None

    def add(self, groups: Any, column: Optional[str]) -> None:
        sizes = groups.size()
        slots = self._slots_for(sizes.index)
        self.count[slots] += sizes.to_numpy(dtype=np.int64)
        if self.agg == "count" or column is None:
            return
        target = "sum" if self.agg in ("sum", "mean") else self.agg
        partial = getattr(groups[column], target)()
        values, valid = self._values(partial)
        acc = self._accumulator(values.dtype)
        if target == "sum":
            acc[slots] += values
            self.seen[slots] = True
            if self.agg == "mean":
                self.nonnull[slots] += groups[column].count().to_numpy(dtype=np.int64)
            return
        had = self.seen[slots]
        both = valid & had
        better = np.zeros(len(slots), dtype=bool)
        if both.any():
            current = acc[slots[both]]
            better[both] = values[both] < current if target == "min" else values[both] > current
        take = valid & (~had | better)
        acc[slots[take]] = values[take]
        self.seen[slots[take]] = True

    def series(self) -> pd.Series:
        """The finished aggregate per parent, omitting parents it never reached."""
        n = len(self.keys)
        index = pd.Index(self.keys)
        if self.agg == "count":
            return pd.Series(self.count[:n], index=index)
        if self.value is None:
            return pd.Series(dtype=float)
        if self.agg == "mean":
            with np.errstate(divide="ignore", invalid="ignore"):
                mean = np.where(self.nonnull[:n] > 0, self.value[:n] / self.nonnull[:n], np.nan)
            return pd.Series(mean, index=index)[self.seen[:n]]
        values = self.value[:n]
        if self.dtype is not None:
            values = values.view(self.dtype)
        return pd.Series(values, index=index)[self.seen[:n]]

    def _values(self, partial: pd.Series) -> Any:
        dtype = partial.dtype
        if isinstance(dtype, np.dtype) and dtype.kind == "M":
            if self.dtype is None:
                self.dtype = dtype
            values = partial.to_numpy(dtype=self.dtype).view(np.int64)
            return values, ~partial.isna().to_numpy()
        if isinstance(dtype, np.dtype) and dtype.kind in "iub":
            return partial.to_numpy(dtype=np.int64), np.ones(len(partial), dtype=bool)
        if pd.api.types.is_numeric_dtype(dtype):
            values = partial.to_numpy(dtype=float, na_value=np.nan)
            return values, ~np.isnan(values)
        return partial.to_numpy(dtype=object), partial.notna().to_numpy()

    def _accumulator(self, dtype: np.dtype) -> np.ndarray:
        size = len(self.count)
        if self.value is None:
            self.value = np.zeros(size, dtype=dtype)
        elif self.value.dtype != dtype:
            either_object = np.dtype(object) in (self.value.dtype, dtype)
            wider = np.dtype(object) if either_object else np.result_type(self.value.dtype, dtype)
            self.value = self.value.astype(wider)
        return self.value

    def _slots_for(self, keys: Any) -> np.ndarray:
        slots = np.empty(len(keys), dtype=np.int64)
        for i, key in enumerate(keys):
            slot = self.slots.get(key)
            if slot is None:
                slot = self.slots[key] = len(self.keys)
                self.keys.append(key)
            slots[i] = slot
        if len(self.keys) > len(self.count):
            grow = max(len(self.keys), 2 * len(self.count), 1024) - len(self.count)
            self.count = np.concatenate([self.count, np.zeros(grow, dtype=np.int64)])
            self.nonnull = np.concatenate([self.nonnull, np.zeros(grow, dtype=np.int64)])
            self.seen = np.concatenate([self.seen, np.zeros(grow, dtype=bool)])
            if self.value is not None:
                self.value = np.concatenate([self.value, np.zeros(grow, dtype=self.value.dtype)])
        return slots


class RollupAccumulator:
    """Per-parent partial aggregates for streamable roll-ups.

    Memory is proportional to the number of parents, never to the number of
    child rows, so a parent summary column can reconcile with a child table
    too large to hold."""

    def __init__(self, specs: List[RollupSpec]):
        self.specs = list(specs)
        self.parts: List[_Partials] = [_Partials(s.agg) for s in self.specs]

    def tables(self) -> set:
        return {s.from_table for s in self.specs}

    def update(self, table_name: str, batch: pd.DataFrame) -> None:
        for spec, part in zip(self.specs, self.parts, strict=True):
            if spec.from_table != table_name or spec.fk not in batch.columns:
                continue
            child = batch
            if spec.where:
                mask = pd.Series(True, index=child.index)
                for fcol, fval in spec.where.items():
                    if fcol not in child.columns:
                        continue
                    mask &= (child[fcol].isin(list(fval)) if isinstance(fval, (list, tuple, set))
                             else child[fcol] == fval)
                child = child[mask]
            if spec.agg != "count" and (spec.column is None or spec.column not in child.columns):
                continue
            part.add(child.groupby(spec.fk), spec.column)

    def apply(self, tables: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """Write each accumulated aggregate into its (buffered) parent."""
        for spec, part in zip(self.specs, self.parts, strict=True):
            parent = tables.get(spec.parent_table)
            if parent is None or spec.parent_key not in parent.columns:
                continue
            mapped = parent[spec.parent_key].map(part.series())
            mapped = mapped.fillna(0 if spec.agg == "count" else spec.fillna)
            if spec.agg == "count" or (spec.target_column in parent.columns
                                       and pd.api.types.is_integer_dtype(parent[spec.target_column])):
                mapped = mapped.round().astype("int64")
            tables[spec.parent_table][spec.target_column] = mapped.values
        return tables
