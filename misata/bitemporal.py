"""Two independent time axes on the same fact.

`scd2` tiles one axis: an entity's versions cover business time without gaps or
overlaps. Bitemporal data has two, and the second is not a decoration. System
time records *when the system was told*, and it moves independently of business
time: a correction recorded today can change what was true last March while
leaving intact the record of what we believed in between.

That independence is the whole point of the shape, and it is what makes the
defining query answerable: "as of last Tuesday, what did we think the position
was?" A table where the two axes are the same column, or where more than one row
is current, cannot answer it, and no row-level check notices.

The construction here keeps the axes genuinely independent. System time is tiled
strictly: each version's `superseded_at` is the next version's `recorded_at`,
exactly one version per entity is open. Business time is then written *inside*
each version, so a later correction can restate an earlier period.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List

import numpy as np
import pandas as pd

NS_PER_DAY = 86_400_000_000_000


def apply_bitemporal(
    tables: Dict[str, pd.DataFrame],
    spec: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Rewrite a table so its two time axes tile independently per entity."""
    df = tables.get(spec.table)
    if df is None or df.empty:
        return tables
    cols = [*spec.entity_columns, spec.valid_from, spec.valid_to,
            spec.recorded_at, spec.superseded_at]
    for c in cols:
        if c not in df.columns:
            warnings.warn(
                f"Bitemporal '{spec.name}': column '{c}' missing from "
                f"'{spec.table}'. Skipping.")
            return tables

    n = len(df)
    out = df.copy()

    # Group the rows into entities. Every row keeps the entity it was generated
    # with, so foreign keys and any partition declaration survive untouched;
    # only the four time columns are rewritten.
    keys = (out[spec.entity_columns[0]] if len(spec.entity_columns) == 1
            else pd.MultiIndex.from_frame(out[spec.entity_columns]))
    codes, _ = pd.factorize(pd.Index(keys))

    # The window each entity's history lives in, taken from the generated
    # recorded_at values so the declaration does not invent a range the schema
    # never asked for.
    rec = pd.to_datetime(out[spec.recorded_at], errors="coerce")
    lo = int(rec.min().value) if rec.notna().any() else 0
    hi = int(rec.max().value) if rec.notna().any() else lo + 365 * NS_PER_DAY
    if hi <= lo:
        hi = lo + 365 * NS_PER_DAY

    recorded = np.zeros(n, dtype="int64")
    superseded = np.full(n, np.iinfo("int64").min, dtype="int64")
    has_super = np.zeros(n, dtype=bool)
    v_from = np.zeros(n, dtype="int64")
    v_to = np.full(n, np.iinfo("int64").min, dtype="int64")
    has_vto = np.zeros(n, dtype=bool)

    for code in np.unique(codes):
        rows = np.flatnonzero(codes == code)
        k = len(rows)
        # System time: k ascending instants inside the window, each version
        # superseded by the next. The last one is current.
        picks = np.sort(lo + (rng.random(k) * (hi - lo)).astype("int64"))
        # Strictly increasing, so `superseded_at > recorded_at` always holds.
        picks = picks + np.arange(k, dtype="int64") * 1_000_000_000
        recorded[rows] = picks
        if k > 1:
            superseded[rows[:-1]] = picks[1:]
            has_super[rows[:-1]] = True

        # Business time, written inside each version. The current version leaves
        # valid time open; superseded ones close, and may restate a period that
        # an earlier version already covered. That overlap across versions is
        # correct: it is what a correction looks like.
        starts = np.sort(lo + (rng.random(k) * (hi - lo)).astype("int64"))
        v_from[rows] = starts
        if k > 1:
            span = np.maximum(
                (rng.random(k - 1) * 180 * NS_PER_DAY).astype("int64"),
                NS_PER_DAY)
            v_to[rows[:-1]] = starts[:-1] + span
            has_vto[rows[:-1]] = True

    out[spec.recorded_at] = recorded.astype("datetime64[ns]")
    sup = pd.Series(superseded.astype("datetime64[ns]"))
    sup[~has_super] = pd.NaT
    out[spec.superseded_at] = sup.values
    out[spec.valid_from] = v_from.astype("datetime64[ns]")
    vt = pd.Series(v_to.astype("datetime64[ns]"))
    vt[~has_vto] = pd.NaT
    out[spec.valid_to] = vt.values

    tables[spec.table] = out
    return tables


def apply_bitemporals(
    tables: Dict[str, pd.DataFrame],
    config: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    for spec in (getattr(config, "bitemporal", None) or []):
        try:
            apply_bitemporal(tables, spec, rng)
        except Exception as e:
            warnings.warn(f"Bitemporal '{spec.name}' failed ({e}); table left "
                          f"as generated.")
    return tables


def bitemporal_tables(config: Any) -> set:
    return {s.table for s in (getattr(config, "bitemporal", None) or [])}
