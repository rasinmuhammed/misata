"""An entity's state implies exactly which events its log contains.

`lifecycles` (0.8.9.4) made a status column trustworthy: a row in state S carries
the timestamp of every state on the path to S and nulls elsewhere. In an
event-sourced system that history lives in a child table instead, and nothing
tied the two together, so the two could disagree freely.

The Warren conformance suite measured the disagreement on its first run: 602
done tasks with no completion event, 261 cancelled tasks with no cancellation
event, 332 open tasks that had somehow been completed, and 667 completion events
that happened before work had started. Every one of those is a query an analyst
writes on day one.

This module projects the lifecycle guarantee onto the log. The lifecycle already
computes the ordered path a state implies; this rewrites the child table so the
log says the same thing, exactly.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def _lifecycle_for(config: Any, table: str) -> Optional[Any]:
    for lc in (getattr(config, "lifecycles", None) or []):
        if lc.table == table:
            return lc
    return None


def apply_event_log(
    tables: Dict[str, pd.DataFrame],
    spec: Any,
    config: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Rewrite an event table so it agrees with its entities' lifecycle states.

    Only the event type and its timestamp are touched. Everything else the event
    carries, including which entity it belongs to and its own tenant, is left
    exactly as generated, so partition isolation and referential integrity
    survive untouched.
    """
    events = tables.get(spec.table)
    entities = tables.get(spec.entity_table)
    if events is None or entities is None or events.empty or entities.empty:
        return tables

    lc = _lifecycle_for(config, spec.entity_table)
    if lc is None:
        warnings.warn(
            f"EventLog '{spec.name}': no lifecycle declared on "
            f"'{spec.entity_table}', so there is no path to project onto the "
            f"log. Declare one, or drop this event_log."
        )
        return tables

    for name, df, col in ((spec.table, events, spec.entity_key),
                          (spec.table, events, spec.event_type_column),
                          (spec.table, events, spec.event_time_column),
                          (spec.entity_table, entities, lc.state_column)):
        if col not in df.columns:
            warnings.warn(
                f"EventLog '{spec.name}': column '{col}' missing from "
                f"'{name}'. Skipping.")
            return tables

    entity_pk = None
    partition_cols: list = []
    for rel in (getattr(config, "relationships", None) or []):
        if (rel.child_table == spec.table and rel.child_key == spec.entity_key
                and rel.parent_table == spec.entity_table):
            entity_pk = rel.parent_key
            partition_cols = [c for c in (rel.partition_by or [])
                              if c in events.columns and c in entities.columns]
            break
    if entity_pk is None or entity_pk not in entities.columns:
        warnings.warn(
            f"EventLog '{spec.name}': no declared relationship links "
            f"{spec.table}.{spec.entity_key} to {spec.entity_table}. Skipping.")
        return tables

    # For each state, the ordered (event_type, timestamp_column) its path
    # implies. Computed once per state, not once per row.
    ts_of = {st.name: getattr(st, "timestamp", None) for st in lc.states}
    plan: Dict[Any, list] = {}
    reached_of: Dict[Any, list] = {}
    for st in lc.states:
        path = lc.path_to(st.name) or [st.name]
        reached_of[st.name] = path
        plan[st.name] = [(spec.state_events[s], ts_of.get(s))
                         for s in path if s in spec.state_events]

    ent = entities.set_index(entity_pk)
    ent = ent[~ent.index.duplicated(keep="first")]
    states = ent[lc.state_column]

    # Allocate rows by what each entity's state REQUIRES, rather than hoping the
    # foreign key happened to give it enough. min_children can only promise one
    # row per entity, and a done task needs three; the first version of this
    # pass left 523 done tasks with no completion event for exactly that reason.
    keys = list(ent.index)
    need = [len(plan.get(states.get(k), [])) for k in keys]
    total_need = int(sum(need))
    n = len(events)
    if total_need > n:
        warnings.warn(
            f"EventLog '{spec.name}': the declared states need {total_need} "
            f"events but '{spec.table}' has only {n} rows. Raise "
            f"{spec.table}.row_count to at least {total_need}; the log cannot "
            f"be complete as declared."
        )
        return tables

    owner = np.empty(n, dtype=object)
    slot = np.zeros(n, dtype="int64")     # which step of the plan this row is
    at = 0
    for k, cnt in zip(keys, need):
        for i in range(cnt):
            owner[at] = k
            slot[at] = i
            at += 1
    # Surplus rows become filler, spread over the entities that can hold it.
    if at < n:
        extra_keys = [k for k, c in zip(keys, need) if c > 0]
        if not extra_keys:
            extra_keys = keys
        idx = rng.integers(0, len(extra_keys), size=n - at)
        for j, i in enumerate(idx):
            owner[at + j] = extra_keys[int(i)]
            slot[at + j] = -1            # -1 marks filler
    order = rng.permutation(n)
    owner, slot = owner[order], slot[order]

    types = np.empty(n, dtype=object)
    stamps = np.zeros(n, dtype="int64")
    start_col = getattr(lc, "start_column", None)
    hour = 3_600_000_000_000

    # Per entity: resolve the timestamps its own lifecycle already wrote, fill
    # the gaps monotonically, then place its rows.
    times_cache: Dict[Any, list] = {}
    filler_cache: Dict[Any, list] = {}
    for k in keys:
        st = states.get(k)
        steps = plan.get(st) or []
        if not steps:
            continue
        row = ent.loc[k]
        base = None
        if start_col and start_col in ent.columns and pd.notna(row[start_col]):
            base = pd.Timestamp(row[start_col]).value
        anchors = []
        for _, tcol in steps:
            v = row[tcol] if (tcol and tcol in ent.columns) else None
            anchors.append(pd.Timestamp(v).value if v is not None and pd.notna(v)
                           else None)
        filled = []
        prev = base if base is not None else (
            next((a for a in anchors if a is not None), 0))
        for i, a in enumerate(anchors):
            if a is not None:
                prev = max(a, prev)
            else:
                nxt = next((x for x in anchors[i + 1:] if x is not None), None)
                prev = (min(prev + hour, nxt) if nxt is not None and nxt > prev
                        else prev + hour)
            filled.append(prev)
        times_cache[k] = filled
        # Filler may ONLY use declared filler events. Letting it reuse the
        # state events meant a 'completed' filler could land before the task
        # started, which is the same defect wearing a different hat.
        filler_cache[k] = list(spec.filler_events or [])

    for i in range(n):
        k = owner[i]
        filled = times_cache.get(k)
        if not filled:
            types[i] = events[spec.event_type_column].iloc[i]
            stamps[i] = pd.Timestamp(
                events[spec.event_time_column].iloc[i]).value
            continue
        j = int(slot[i])
        if j >= 0:
            types[i] = plan[states.get(k)][j][0]
            stamps[i] = filled[j]
        else:
            pool = filler_cache.get(k) or []
            if not pool:
                # Nothing legal to add: repeat the first event of the path,
                # which is always true of the entity and never terminal.
                types[i] = plan[states.get(k)][0][0]
                stamps[i] = filled[0]
            else:
                types[i] = pool[int(rng.integers(0, len(pool)))]
                lo_t, hi_t = filled[0], filled[-1]
                stamps[i] = lo_t + int(rng.integers(0, max(hi_t - lo_t, 1)))

    out = events.copy()
    out[spec.entity_key] = owner
    out[spec.event_type_column] = types
    out[spec.event_time_column] = stamps.astype("datetime64[ns]")
    # Reassigning ownership moves the row into the entity's partition, so the
    # partition columns move with it. Otherwise this pass would re-open exactly
    # the tenant leak `partition_by` closes.
    for c in partition_cols:
        out[c] = pd.Series(owner).map(ent[c]).to_numpy()

    # Moving a row into another partition invalidates every OTHER partitioned
    # reference it carries: an event reassigned to a task in tenant 3 was still
    # pointing at an actor in tenant 5, which is the leak `partition_by` exists
    # to prevent, re-opened by the pass that fixed the log. Any pass that can
    # change a row's partition owes the row's other keys a redraw.
    if partition_cols:
        _redraw_sibling_keys(out, tables, config, spec, partition_cols, rng)

    tables[spec.table] = out
    return tables


def _redraw_sibling_keys(
    out: pd.DataFrame,
    tables: Dict[str, pd.DataFrame],
    config: Any,
    spec: Any,
    partition_cols: list,
    rng: np.random.Generator,
) -> None:
    """Re-resolve the table's other partitioned keys inside their new partition."""
    for rel in (getattr(config, "relationships", None) or []):
        if rel.child_table != spec.table or rel.child_key == spec.entity_key:
            continue
        cols = [c for c in (rel.partition_by or []) if c in out.columns]
        if not cols or cols != partition_cols:
            continue
        parent = tables.get(rel.parent_table)
        if parent is None or parent.empty or rel.parent_key not in parent.columns:
            continue
        if any(c not in parent.columns for c in cols):
            continue
        if rel.child_key not in out.columns:
            continue

        p_key = (pd.Index(parent[cols[0]]) if len(cols) == 1
                 else pd.MultiIndex.from_frame(parent[cols]))
        c_key = (pd.Index(out[cols[0]]) if len(cols) == 1
                 else pd.MultiIndex.from_frame(out[cols]))
        codes, _ = pd.factorize(p_key.append(c_key))
        p_codes, c_codes = codes[: len(p_key)], codes[len(p_key):]
        p_ids = parent[rel.parent_key].to_numpy()

        # If the relationship also declares temporal eligibility, honour it
        # here too. The redraw rewrote which parent a row points at, and doing
        # that without asking when the parent was born put 1,407 events before
        # their actor had signed up: fixing a partition leak by opening a
        # causality hole is not a fix.
        births = None
        child_ns = None
        ptime = getattr(rel, "parent_time", None)
        ctime = getattr(rel, "child_time", None)
        if ptime and ctime and ptime in parent.columns and ctime in out.columns:
            births = pd.to_datetime(parent[ptime], errors="coerce").to_numpy(
                dtype="datetime64[ns]").astype("int64")
            child_ns = pd.to_datetime(out[ctime], errors="coerce").to_numpy(
                dtype="datetime64[ns]").astype("int64")

        values = out[rel.child_key].to_numpy().copy()
        stranded = 0
        for code in np.unique(c_codes):
            rows = np.flatnonzero(c_codes == code)
            in_part = np.flatnonzero(p_codes == code)
            if in_part.size == 0:
                continue
            pool = p_ids[in_part]
            if births is not None:
                b = births[in_part]
                order = np.argsort(b, kind="stable")
                pool, b = pool[order], b[order]
                alive = np.searchsorted(b, child_ns[rows], side="right")
                stranded += int((alive == 0).sum())
                alive = np.maximum(alive, 1)
                draw = (rng.random(rows.size) * alive).astype("int64")
                draw = np.minimum(draw, alive - 1)
            else:
                draw = (rng.random(rows.size) * pool.size).astype("int64")
                draw = np.minimum(draw, pool.size - 1)
            values[rows] = pool[draw]
        if stranded:
            warnings.warn(
                f"EventLog '{spec.name}': {stranded} event(s) happen before any "
                f"{rel.parent_table} row in their partition existed, so "
                f"{rel.child_key} cannot both stay in the partition and "
                f"postdate its parent. Start {rel.parent_table}.{ptime} earlier."
            )
        out[rel.child_key] = values


def apply_event_logs(
    tables: Dict[str, pd.DataFrame],
    config: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    for spec in (getattr(config, "event_logs", None) or []):
        try:
            apply_event_log(tables, spec, config, rng)
        except Exception as e:
            warnings.warn(f"EventLog '{spec.name}' failed ({e}); "
                          f"table left as generated.")
    return tables


def event_log_tables(config: Any) -> set:
    """Tables an event-log pass needs materialised.

    Not only the two it rewrites. Reassigning ownership forces a redraw of the
    event table's other partitioned keys, and that reads their parent tables, so
    those buffer too. Leaving them out is silent rather than loud: the redraw
    simply finds nothing and 7,509 events keep an actor from the wrong tenant.
    """
    out: set = set()
    for spec in (getattr(config, "event_logs", None) or []):
        out.add(spec.table)
        out.add(spec.entity_table)
        for rel in (getattr(config, "relationships", None) or []):
            if (rel.child_table == spec.table
                    and rel.child_key != spec.entity_key
                    and rel.partition_by):
                out.add(rel.parent_table)
    return out
