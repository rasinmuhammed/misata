"""Simulate a declared :class:`~misata.schema.Process` into an event log.

A semi-Markov chain advanced for every case at once: each step draws the next
state for all active cases from the declared transition row, then the time
spent in the state from the dwell distribution of that transition, with numpy
operations over the whole population. A million cases with a dozen steps take
seconds; there is no event queue and no per-case Python object, which is why
this is not built on SimPy.

The audit (:func:`process_audit`) re-derives every structural guarantee from
the rows alone, so it can check a log produced by anything.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_UNIT_NS = {"seconds": 1_000_000_000, "minutes": 60_000_000_000,
            "hours": 3_600_000_000_000, "days": 86_400_000_000_000}


def _states(spec) -> List[str]:
    seen: List[str] = [spec.initial]
    for s, nxt in spec.transitions.items():
        for x in [s, *nxt]:
            if x not in seen:
                seen.append(x)
    return seen


def _draw_dwell(cfg: Dict[str, Any], n: int, rng: np.random.Generator) -> np.ndarray:
    """Dwell times in nanoseconds."""
    dist = str(cfg.get("distribution", "lognormal")).lower()
    unit = _UNIT_NS.get(str(cfg.get("unit", "hours")).lower())
    if unit is None:
        raise ValueError(f"dwell unit must be one of {sorted(_UNIT_NS)}, got {cfg.get('unit')!r}")
    if dist == "lognormal":
        x = rng.lognormal(float(cfg.get("mu", 0.0)), float(cfg.get("sigma", 1.0)), n)
    elif dist == "exponential":
        x = rng.exponential(float(cfg.get("scale", 1.0)), n)
    elif dist == "gamma":
        x = rng.gamma(float(cfg.get("shape", 2.0)), float(cfg.get("scale", 1.0)), n)
    elif dist == "uniform":
        x = rng.uniform(float(cfg.get("min", 0.0)), float(cfg.get("max", 1.0)), n)
    elif dist == "fixed":
        x = np.full(n, float(cfg.get("value", 1.0)))
    else:
        raise ValueError(f"unknown dwell distribution {dist!r} "
                         f"(lognormal, exponential, gamma, uniform, fixed)")
    return np.maximum(x, 0.0) * unit


def simulate_process(cases: pd.DataFrame, spec, rng: np.random.Generator
                     ) -> Tuple[pd.DataFrame, np.ndarray]:
    """Return ``(events, final_state)`` for every row of ``cases``.

    ``events`` has the case key, the step number, the activity (state entered)
    and its timestamp; ``final_state`` is aligned with ``cases``.
    """
    states = _states(spec)
    idx = {s: i for i, s in enumerate(states)}
    k = len(states)
    terminal = np.array([s not in spec.transitions for s in states])
    P = np.zeros((k, k))
    for s, nxt in spec.transitions.items():
        for t, p in nxt.items():
            P[idx[s], idx[t]] = float(p)
    cum = np.cumsum(P, axis=1)

    n = len(cases)
    if spec.start_column and spec.start_column in cases.columns:
        start = pd.to_datetime(cases[spec.start_column], errors="coerce")
        if getattr(start.dt, "tz", None) is not None:
            start = start.dt.tz_localize(None)
        t = start.to_numpy(dtype="datetime64[ns]").astype("int64")
        missing = start.isna().to_numpy()
    else:
        lo = pd.Timestamp(spec.start).value
        hi = pd.Timestamp(spec.end).value
        t = rng.integers(lo, max(hi, lo + 1), n)
        missing = np.zeros(n, dtype=bool)

    dwell_by_pair: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for key, cfg in spec.dwell.items():
        if "->" in key:
            a, b = (x.strip() for x in key.split("->", 1))
            dwell_by_pair[(idx[a], idx[b])] = cfg
    dwell_by_state = {idx[k_]: cfg for k_, cfg in spec.dwell.items() if "->" not in k_}
    default = {"distribution": "lognormal", "mu": 0.0, "sigma": 1.0, "unit": "hours"}

    state = np.full(n, idx[spec.initial])
    active = ~missing
    rows_case, rows_step, rows_state, rows_t = [], [], [], []
    case_pos = np.arange(n)

    def emit(mask: np.ndarray, step: int) -> None:
        rows_case.append(case_pos[mask])
        rows_step.append(np.full(int(mask.sum()), step))
        rows_state.append(state[mask].copy())
        rows_t.append(t[mask].copy())

    emit(active, 1)
    step = 1
    active = active & ~terminal[state]
    while active.any() and step < spec.max_steps:
        a = np.flatnonzero(active)
        u = rng.random(len(a))
        nxt = (u[:, None] > cum[state[a]]).sum(axis=1)
        nxt = np.minimum(nxt, k - 1)
        # dwell in the current state before leaving it for `nxt`
        dt = np.empty(len(a))
        cur = state[a]
        for (s_, n_) in set(zip(cur.tolist(), nxt.tolist())):
            m = (cur == s_) & (nxt == n_)
            cfg = dwell_by_pair.get((s_, n_)) or dwell_by_state.get(s_) or default
            dt[m] = _draw_dwell(cfg, int(m.sum()), rng)
        # Whole seconds, at least one: nanosecond-precision event times are
        # a tell no real system emits.
        t[a] = t[a] + (np.maximum(np.round(dt / 1e9), 1) * 1_000_000_000).astype("int64")
        state[a] = nxt
        step += 1
        emit(np.isin(case_pos, a), step)
        active[a] = ~terminal[nxt]

    case_rows = np.concatenate(rows_case) if rows_case else np.array([], dtype=int)
    events = pd.DataFrame({
        spec.case_key: cases[spec.case_key].to_numpy()[case_rows],
        spec.step_column: np.concatenate(rows_step) if rows_step else [],
        spec.activity_column: np.array(states, dtype=object)[np.concatenate(rows_state)]
        if rows_state else [],
        spec.time_column: pd.to_datetime(np.concatenate(rows_t)) if rows_t else [],
    })
    events = events.sort_values([spec.case_key, spec.step_column], kind="stable",
                                ignore_index=True)
    events.insert(0, "event_id", np.arange(1, len(events) + 1))
    final = np.array(states, dtype=object)[state]
    final[missing] = None
    return events, final


def apply_processes(buffered: Dict[str, pd.DataFrame], config, rng: np.random.Generator
                    ) -> List[str]:
    """Simulate every declared process into ``buffered``; returns the names of
    the event tables added."""
    added = []
    for spec in getattr(config, "processes", None) or []:
        cases = buffered.get(spec.cases_table)
        if cases is None or spec.case_key not in cases.columns:
            raise ValueError(f"process {spec.name!r}: cases table {spec.cases_table!r} "
                             f"with key {spec.case_key!r} was not generated")
        events, final = simulate_process(cases, spec, rng)
        buffered[spec.event_table] = events
        if spec.final_state_column:
            cases[spec.final_state_column] = final
        added.append(spec.event_table)
    return added


def process_audit(events: pd.DataFrame, spec, cases: Optional[pd.DataFrame] = None
                  ) -> List[str]:
    """Check an event log against a process declaration, from the rows alone.

    Returns human-readable violations; an empty list means every structural
    guarantee holds.
    """
    out: List[str] = []
    ck, sc, ac, tc = spec.case_key, spec.step_column, spec.activity_column, spec.time_column
    ev = events.sort_values([ck, sc], kind="stable")
    allowed = {(s, t) for s, nxt in spec.transitions.items() for t in nxt}
    terminal = {s for s in _states(spec) if s not in spec.transitions}
    g = ev.groupby(ck, sort=False)
    first = g.head(1)
    if (first[ac] != spec.initial).any():
        out.append(f"{int((first[ac] != spec.initial).sum())} cases do not start in "
                   f"{spec.initial!r}")
    expected = g.cumcount() + 1
    if (ev[sc].to_numpy() != expected.to_numpy()).any():
        out.append("step numbers are not 1..n within every case")
    prev_a = g[ac].shift()
    pairs = list(zip(prev_a[prev_a.notna()], ev[ac][prev_a.notna()]))
    bad = sum(1 for p in pairs if p not in allowed)
    if bad:
        out.append(f"{bad} transitions are not declared")
    tt = pd.to_datetime(ev[tc])
    back = (tt.groupby(ev[ck]).diff() < pd.Timedelta(0)).sum()
    if back:
        out.append(f"{int(back)} events are earlier than the event before them")
    last = g.tail(1)
    unfinished = last[~last[ac].isin(terminal) & (last[sc] < spec.max_steps)]
    if len(unfinished):
        out.append(f"{len(unfinished)} cases stop in a non-terminal state before max_steps")
    if cases is not None and spec.start_column and spec.start_column in cases.columns:
        st = pd.to_datetime(cases.set_index(ck)[spec.start_column])
        early = (pd.to_datetime(first.set_index(ck)[tc]) < st.reindex(first[ck]).values).sum()
        if early:
            out.append(f"{int(early)} cases begin before their {spec.start_column}")
    return out


def to_xes(events: pd.DataFrame, path, *, case_column: str, activity_column: str = "activity",
           time_column: str = "timestamp") -> str:
    """Write an event log as IEEE 1849 XES (the format ProM, PM4Py, Disco and
    Celonis import). Columns other than case, activity and time are written
    as string attributes on each event."""
    from xml.sax.saxutils import quoteattr
    extra = [c for c in events.columns if c not in (case_column, activity_column, time_column)]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<log xes.version="1849-2016" xmlns="http://www.xes-standard.org/">',
             '  <extension name="Concept" prefix="concept" uri="http://www.xes-standard.org/concept.xesext"/>',
             '  <extension name="Time" prefix="time" uri="http://www.xes-standard.org/time.xesext"/>']
    ev = events.sort_values([case_column, time_column], kind="stable")
    times = pd.to_datetime(ev[time_column])
    ev = ev.assign(**{"__xes_time__": times})
    for case, grp in ev.groupby(case_column, sort=False):
        lines.append("  <trace>")
        lines.append(f'    <string key="concept:name" value={quoteattr(str(case))}/>')
        for r in grp.to_dict("records"):
            lines.append("    <event>")
            lines.append(f'      <string key="concept:name" value={quoteattr(str(r[activity_column]))}/>')
            lines.append(f'      <date key="time:timestamp" value="{r["__xes_time__"].isoformat()}"/>')
            for c in extra:
                v = r.get(c)
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    lines.append(f'      <string key={quoteattr(str(c))} value={quoteattr(str(v))}/>')
            lines.append("    </event>")
        lines.append("  </trace>")
    lines.append("</log>")
    text = "\n".join(lines) + "\n"
    if path is not None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text
