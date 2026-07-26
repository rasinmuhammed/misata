"""Entity lifecycles: declare the state machine, and make the history legal.

A status column beside a scatter of per-state timestamps is the most common
shape in operational data and the most commonly wrong. An "active" subscription
with a cancellation date, a "cancelled" order with a delivery time, a "returned"
order missing the shipment it must have had: every one of those is the same
defect, a row whose columns describe a history that could not have happened.

The fix is not more rules. Enumerating ``when_then`` implications pair by pair
grows quadratically and still cannot express ordering along a path. Declaring
the machine once gives every implication for free:

    for a row in state S, let P = path(initial → S). Then
      * every state in P with a timestamp column has it populated,
      * those timestamps ascend in path order,
      * every state NOT in P has its timestamp NULL,
      * the whole chain postdates ``start_column``.

That is the entire contract, and it is what :func:`apply_lifecycles` enforces
and ``coherence_audit`` re-checks independently.

Why this runs during the owning table's generation rather than in the
post-generation pass: rewriting ``status`` changes which parents are eligible
for a filtered relationship (``shipments`` only attach to shipped orders). The
children must therefore see the final states, so the lifecycle is applied as
soon as the parent table is complete and its context is refreshed before any
child is generated.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

NS_PER_DAY = 86_400_000_000_000


def _allocate_states(
    n: int,
    states: List[str],
    weights: Optional[Dict[str, float]],
    rng: np.random.Generator,
) -> np.ndarray:
    """Assign a state to each of ``n`` rows.

    Counts come from largest-remainder allocation so the realised mix matches
    the declared weights as closely as integers allow, rather than only in
    expectation. Positions are then shuffled so state does not correlate with
    row order.
    """
    if not weights:
        counts = {s: n // len(states) for s in states}
        for s in states[: n - sum(counts.values())]:
            counts[s] += 1
    else:
        total = sum(float(w) for w in weights.values())
        if total <= 0:
            raise ValueError("lifecycle weights must sum to a positive number")
        if abs(total - 1.0) > 0.01:
            warnings.warn(
                f"Lifecycle weights sum to {total:.4f}, normalising to 1.0."
            )
        exact = {s: n * float(weights.get(s, 0.0)) / total for s in states}
        counts = {s: int(np.floor(v)) for s, v in exact.items()}
        remainder = n - sum(counts.values())
        # Largest fractional part wins the leftover rows.
        order = sorted(states, key=lambda s: exact[s] - np.floor(exact[s]), reverse=True)
        for s in order[:remainder]:
            counts[s] += 1

    out = np.empty(n, dtype=object)
    i = 0
    for s in states:
        c = counts.get(s, 0)
        if c:
            out[i : i + c] = s
            i += c
    if i < n:  # defensive: any shortfall goes to the first state
        out[i:] = states[0]
    rng.shuffle(out)
    return out


def apply_lifecycle(
    df: pd.DataFrame,
    spec: Any,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Enforce one lifecycle on a materialised table. Mutates and returns ``df``."""
    if df is None or df.empty:
        return df
    if spec.state_column not in df.columns:
        warnings.warn(
            f"Lifecycle '{spec.name}': state column '{spec.state_column}' not "
            f"in '{spec.table}'. Skipping."
        )
        return df

    all_states = spec.state_names()

    # Resolve every state's path up front so an unreachable state is reported
    # once, loudly, rather than producing a row with no legal history.
    paths: Dict[str, List[str]] = {}
    unreachable: List[str] = []
    for s in all_states:
        p = spec.path_to(s)
        if p is None:
            unreachable.append(s)
        else:
            paths[s] = p
    if unreachable:
        warnings.warn(
            f"Lifecycle '{spec.name}': state(s) {unreachable} are not reachable "
            f"from '{spec.initial or all_states[0]}' via the declared "
            f"transitions; no rows will be placed in them."
        )
    usable = [s for s in all_states if s in paths]
    if not usable:
        warnings.warn(
            f"Lifecycle '{spec.name}': no reachable states. Skipping."
        )
        return df

    weights = spec.weights
    if weights:
        dropped = {k: v for k, v in weights.items() if k not in paths and v}
        if dropped:
            warnings.warn(
                f"Lifecycle '{spec.name}': weights given for unreachable "
                f"state(s) {sorted(dropped)}; those shares are redistributed."
            )
        weights = {k: v for k, v in weights.items() if k in paths}

    n = len(df)
    df[spec.state_column] = _allocate_states(n, usable, weights, rng)

    ts_cols = spec.timestamp_columns()
    if not ts_cols:
        return df   # states declared without timestamps: the status mix is the contract

    missing = [c for c in ts_cols if c not in df.columns]
    if missing:
        warnings.warn(
            f"Lifecycle '{spec.name}': timestamp column(s) {missing} are not in "
            f"'{spec.table}'; declare them on the table to have them enforced."
        )
        ts_cols = [c for c in ts_cols if c in df.columns]
        if not ts_cols:
            return df

    # Base instant every chain starts from.
    if spec.start_column and spec.start_column in df.columns:
        base = pd.to_datetime(df[spec.start_column], errors="coerce")
        if base.isna().all():
            base = pd.Series(pd.Timestamp("2024-01-01"), index=df.index)
        else:
            base = base.fillna(base.min())
    else:
        pool = [pd.to_datetime(df[c], errors="coerce") for c in ts_cols]
        stacked = pd.concat(pool, axis=1).min(axis=1)
        base = stacked.fillna(pd.Timestamp("2024-01-01"))
    base_ns = base.astype("int64").to_numpy()

    # Every timestamp column starts empty, then only path states get a value.
    for c in ts_cols:
        df[c] = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")

    max_gap_ns = max(int(spec.max_days_per_step), 1) * NS_PER_DAY
    status = df[spec.state_column].to_numpy()

    for state, path in paths.items():
        mask = status == state
        cnt = int(mask.sum())
        if not cnt:
            continue
        # Gaps for this group's whole path in one draw, then a running sum so
        # the timestamps ascend strictly in path order.
        gaps = rng.integers(1, max_gap_ns, size=(cnt, len(path)))
        gaps[:, 0] = 0                      # entering the initial state is the base instant
        offsets = np.cumsum(gaps, axis=1)
        for i, pstate in enumerate(path):
            col = spec.timestamp_of(pstate)
            if not col or col not in df.columns:
                continue
            vals = base_ns[mask] + offsets[:, i]
            df.loc[mask, col] = pd.to_datetime(vals)

    return df


def apply_lifecycles(
    tables: Dict[str, pd.DataFrame],
    config: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Apply every declared lifecycle whose table is present."""
    for spec in (getattr(config, "lifecycles", None) or []):
        df = tables.get(spec.table)
        if df is None:
            continue
        try:
            tables[spec.table] = apply_lifecycle(df, spec, rng)
        except Exception as e:   # never let a lifecycle corrupt an otherwise-valid run
            warnings.warn(
                f"Lifecycle '{spec.name}' could not be applied ({e}); "
                f"'{spec.table}' is left as generated."
            )
    return tables


def lifecycles_for_table(config: Any, table_name: str) -> List[Any]:
    return [
        s for s in (getattr(config, "lifecycles", None) or [])
        if s.table == table_name
    ]
