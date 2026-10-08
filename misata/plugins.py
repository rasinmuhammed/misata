"""Custom column generators: the escape hatch for what the language cannot say.

Declarations cover the common shapes. When a column needs logic of your own (a
loyalty tier computed from a parent's lifetime spend, a code format from an
internal spec), write a function and register it, rather than post-processing
the DataFrame afterwards, which is the hand-written script Misata replaces::

    import misata

    @misata.generator("loyalty_tier")
    def loyalty_tier(ctx):
        spend = ctx.parent("customers")["lifetime_value"]
        tier = np.where(spend > 1000, "gold", np.where(spend > 200, "silver", "bronze"))
        upgrade = ctx.rng.random(ctx.size) < 0.05      # seeded: same seed, same rows
        return np.where(upgrade, "gold", tier)

The schema then names it, from Python, YAML or a dict alike::

    orders:
      columns:
        tier: {type: text, generator: loyalty_tier}

and the CLI loads the module that registers it with ``--plugin`` (or the
``MISATA_PLUGINS`` environment variable)::

    misata --plugin my_generators generate --config misata.yaml

A schema only ever refers to a registered name. It never imports code itself,
so a schema handed over by someone else (or by an agent through the MCP
server) cannot run anything you did not register.

What a generator receives (:class:`GenContext`):

- ``ctx.size``: rows to produce for this batch;
- ``ctx.rows``: the batch's columns generated so far (declare the custom
  column after the columns it reads);
- ``ctx.parent(table_or_fk)``: the referenced parent rows, aligned to the
  batch, with all the parent's columns;
- ``ctx.rng``: a numpy Generator seeded from the schema seed, the table, the
  column and the batch, so output is reproducible;
- ``ctx.table``, ``ctx.column``, ``ctx.params`` and ``ctx.tables`` (every
  parent table generated so far).

It returns an array, list or Series of length ``ctx.size``; anything else
raises with the column named.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

import numpy as np
import pandas as pd

_GENERATORS: Dict[str, Callable[["GenContext"], Any]] = {}


def generator(name: str, fn: Optional[Callable] = None):
    """Register a column generator under ``name``. Usable as a decorator
    (``@misata.generator("tier")``) or a call (``misata.generator("tier", fn)``)."""
    def _register(f: Callable) -> Callable:
        if not callable(f):
            raise TypeError(f"generator {name!r} must be callable")
        _GENERATORS[name] = f
        return f
    return _register(fn) if fn is not None else _register


register_generator = generator


def get_generator(name: str) -> Callable:
    try:
        return _GENERATORS[name]
    except KeyError:
        known = ", ".join(sorted(_GENERATORS)) or "none"
        raise KeyError(
            f"No generator named {name!r} is registered (registered: {known}). "
            f"Register it with @misata.generator({name!r}) in Python, or load "
            f"the module that does with --plugin on the CLI.") from None


def registered_generators() -> Dict[str, Callable]:
    return dict(_GENERATORS)


def load_plugins(modules) -> None:
    """Import modules that register generators (the CLI's ``--plugin``)."""
    import os
    import sys
    # A console script does not put the working directory on sys.path, and
    # the plugin module usually lives right there next to misata.yaml.
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    for mod in modules or ():
        importlib.import_module(mod)


@dataclass
class GenContext:
    table: str
    column: str
    size: int
    rows: pd.DataFrame
    rng: np.random.Generator
    params: Dict[str, Any]
    tables: Dict[str, pd.DataFrame]
    _relationships: list = field(default_factory=list, repr=False)

    def parent(self, which: str) -> pd.DataFrame:
        """The parent rows referenced by this batch, one per row, in order.

        ``which`` is the parent table's name or the foreign-key column. Rows
        whose key is missing from the parent come back as NaN.
        """
        rel = next((r for r in self._relationships
                    if r.child_table == self.table
                    and which in (r.parent_table, r.child_key)), None)
        if rel is None:
            raise KeyError(
                f"{self.table}.{self.column}: no relationship from {self.table} "
                f"to {which!r}")
        if rel.child_key not in self.rows.columns:
            raise KeyError(
                f"{self.table}.{self.column} reads {rel.child_key}, which is not "
                f"generated yet: declare {self.column} after {rel.child_key}")
        parent = self.tables.get(rel.parent_table)
        if parent is None:
            raise KeyError(f"{rel.parent_table} has not been generated yet")
        lookup = parent.drop_duplicates(rel.parent_key).set_index(rel.parent_key)
        return lookup.reindex(self.rows[rel.child_key].to_numpy()).reset_index(drop=True)
