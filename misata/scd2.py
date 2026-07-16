"""SCD2 history generation: versions that tile time correctly.

A slowly-changing-dimension (type 2) table stores every version of every
entity with a validity interval. The shape has three invariants that naive
generation always breaks:

  1. within an entity, ``valid_to`` of one version equals ``valid_from`` of
     the next (no gaps, no overlaps),
  2. exactly one version per entity is current,
  3. only the current version is open-ended.

``apply_scd2`` rewrites the declared columns so all three hold, leaving every
other column untouched (attributes genuinely vary across versions). The
audit recomputes the invariants from the rows, so generator and audit cannot
drift.
"""

from __future__ import annotations

import warnings
from typing import Any, Optional

import numpy as np
import pandas as pd

from misata.schema import SCD2Config


def _window(spec: SCD2Config, col_params: dict) -> tuple:
    start = spec.start or col_params.get("start") or "2020-01-01"
    end = spec.end or col_params.get("end") or "2024-12-31"
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    if s > e:
        s, e = e, s
    if s == e:
        e = s + pd.Timedelta(days=1)
    return s, e


def apply_scd2(
    df: pd.DataFrame,
    spec: SCD2Config,
    rng: np.random.Generator,
    col_params: Optional[dict] = None,
    table_name: str = "",
) -> pd.DataFrame:
    """Rewrite entity/validity columns so the SCD2 invariants hold exactly.

    Rows are distributed over ``n / avg_versions`` entities (at least one
    version each, extras spread by a seeded multinomial). Per entity, the
    version boundaries are distinct whole-second draws inside the window,
    sorted, and tiled: consecutive versions share a boundary to the second.
    Entity identifiers reuse the column's generated values, so their type
    and format survive.
    """
    needed = {spec.entity_column, spec.valid_from, spec.valid_to}
    if spec.current_flag:
        needed.add(spec.current_flag)
    missing = needed - set(df.columns)
    if missing:
        warnings.warn(
            f"scd2 on {table_name or 'table'}: missing column(s) "
            f"{sorted(missing)}; skipping")
        return df
    n = len(df)
    if n == 0:
        return df

    avg = max(float(spec.avg_versions), 1.0)
    n_entities = max(1, int(round(n / avg)))
    # Version counts: one guaranteed per entity, the rest multinomial.
    counts = np.ones(n_entities, dtype=int)
    if n > n_entities:
        counts += rng.multinomial(n - n_entities,
                                  np.full(n_entities, 1.0 / n_entities))

    # Entity identifiers keep the generated column's type and format.
    pool = pd.unique(df[spec.entity_column])
    if len(pool) < n_entities:
        # Not enough distinct values (tiny declared range): reuse with a
        # warning rather than inventing values of an unknown format.
        warnings.warn(
            f"scd2 on {table_name or 'table'}: only {len(pool)} distinct "
            f"{spec.entity_column} values for {n_entities} entities; "
            f"entity count reduced")
        n_entities = max(1, len(pool))
        counts = np.ones(n_entities, dtype=int)
        if n > n_entities:
            counts += rng.multinomial(n - n_entities,
                                      np.full(n_entities, 1.0 / n_entities))
    entity_ids = pool[:n_entities]

    start, end = _window(spec, col_params or {})
    total_secs = max(int((end - start).total_seconds()), n * 2)

    entities = np.empty(n, dtype=object)
    v_from = np.empty(n, dtype="datetime64[ns]")
    v_to = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    current = np.zeros(n, dtype=bool)

    pos = 0
    for ent, k in zip(entity_ids, counts):
        k = int(k)
        # k distinct whole-second boundaries; the first is the entity's birth.
        secs = np.sort(rng.choice(total_secs, size=k, replace=False))
        stamps = start + pd.to_timedelta(secs, unit="s")
        rows = slice(pos, pos + k)
        pos += k
        entities[rows] = ent
        v_from[rows] = stamps.values
        if k > 1:
            v_to[pos - k: pos - 1] = stamps.values[1:]
        if not spec.open_ended:
            v_to[pos - 1] = np.datetime64(end)
        current[pos - 1] = True

    df[spec.entity_column] = entities
    df[spec.valid_from] = pd.Series(v_from, index=df.index)
    df[spec.valid_to] = pd.Series(v_to, index=df.index)
    if spec.current_flag:
        df[spec.current_flag] = current
    return df
