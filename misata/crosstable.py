"""Cross-table constraint enforcement: a child's numbers bounded by its parent's.

Two constraints that cannot run inside a single-table pass because they need
the FK parent materialised:

- ``lte_parent``:     child.column <= parent.parent_column, row by row.
  A refund larger than its order's total is impossible in real data; clamping
  it against the mapped parent value makes it impossible here too.

- ``sum_lte_parent``: per parent row, sum(child.column) <= parent.parent_column.
  Payments against one order must never total more than the order. Groups that
  overshoot are rescaled proportionally, which preserves each payment's share
  of the total rather than truncating whichever row came last.

Both run in the post-generation pass (``DataSimulator.generate_all``), after
the roll-ups that produce the parent columns they clamp against and before the
roll-ups that aggregate the clamped values upward — see the ordering there.

The fk linking child to parent is resolved from the declared relationship, so
a constraint on an undeclared pair is a warning, never a guess.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Tuple

import pandas as pd

CROSS_TABLE_TYPES = ("lte_parent", "sum_lte_parent")


def collect_cross_table_constraints(config: Any) -> List[Tuple[str, Any]]:
    """Return [(child_table_name, constraint), ...] for every declared
    cross-table constraint in the schema."""
    out: List[Tuple[str, Any]] = []
    for table in getattr(config, "tables", []) or []:
        for c in getattr(table, "constraints", []) or []:
            if getattr(c, "type", None) in CROSS_TABLE_TYPES:
                out.append((table.name, c))
    return out


def _find_fk(config: Any, child_table: str, parent_table: str):
    """The (child_key, parent_key) linking child to parent, from the declared
    relationships. None when the pair is not declared."""
    for rel in getattr(config, "relationships", []) or []:
        if rel.child_table == child_table and rel.parent_table == parent_table:
            return rel.child_key, rel.parent_key
    return None


def apply_cross_table_constraints(
    tables: Dict[str, pd.DataFrame],
    constraints: List[Tuple[str, Any]],
    config: Any,
) -> Dict[str, pd.DataFrame]:
    """Enforce every collected cross-table constraint. Mutates and returns ``tables``."""
    for child_name, c in constraints:
        child = tables.get(child_name)
        parent = tables.get(getattr(c, "parent_table", None))
        col = getattr(c, "column", None)
        pcol = getattr(c, "parent_column", None)
        if child is None or parent is None:
            warnings.warn(
                f"Constraint '{c.name}': table '{child_name}' or its parent "
                f"'{c.parent_table}' is not materialised. Skipping.")
            continue
        if not col or col not in child.columns or not pcol or pcol not in parent.columns:
            warnings.warn(
                f"Constraint '{c.name}': column '{col}' or parent column "
                f"'{pcol}' not found. Skipping.")
            continue
        link = _find_fk(config, child_name, c.parent_table)
        if link is None:
            warnings.warn(
                f"Constraint '{c.name}': no declared relationship between "
                f"'{child_name}' and '{c.parent_table}'. Declare one; the fk "
                "is never guessed. Skipping.")
            continue
        child_key, parent_key = link
        if child_key not in child.columns or parent_key not in parent.columns:
            continue

        parent_vals = (parent.drop_duplicates(subset=[parent_key])
                       .set_index(parent_key)[pcol])
        mapped = child[child_key].map(parent_vals)

        if c.type == "lte_parent":
            over = child[col] > mapped
            over &= mapped.notna()
            if over.any():
                child.loc[over, col] = mapped[over].astype(child[col].dtype, errors="ignore")
        else:  # sum_lte_parent
            sums = child.groupby(child_key)[col].transform("sum")
            cap = mapped
            over = (sums > cap) & cap.notna() & (sums > 0)
            if over.any():
                scale = (cap / sums).clip(upper=1.0)
                child.loc[over, col] = child.loc[over, col] * scale[over]
        tables[child_name] = child
    return tables
