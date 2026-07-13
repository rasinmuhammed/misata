"""Exact group shares: split a measure's total across a categorical column.

The declaration is :class:`misata.schema.GroupShares` ("Electronics is 40% of
revenue"). Paired with an :class:`OutcomeCurve` on the same table and measure,
the shares hold exactly inside every declared period, so the per-group totals
are fully declared rather than measured. Without a curve, the shares hold
exactly over the table's total.

The arithmetic lives in one helper, :func:`split_total_by_shares`, used by
the generator, the evalpack question derivation, and the story audit, so the
three can never disagree about what a share is worth.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def split_total_by_shares(
    shares: Dict[str, float], total: float, decimals: int = 2
) -> Dict[str, float]:
    """Split ``total`` by ``shares`` so the parts sum back exactly.

    Each group's target is ``round(fraction * total, decimals)``; the rounding
    residual is absorbed by the largest-share group, so
    ``sum(targets) == round(total, decimals)`` holds to the cent.
    """
    if not shares:
        return {}
    labels = list(shares.keys())
    fracs = np.array([float(shares[l]) for l in labels], dtype=float)
    targets = {l: round(float(f) * float(total), decimals)
               for l, f in zip(labels, fracs)}
    residual = round(round(float(total), decimals) - sum(targets.values()), decimals)
    if residual:
        biggest = labels[int(np.argmax(fracs))]
        targets[biggest] = round(targets[biggest] + residual, decimals)
    return targets


def normalized_shares(spec: Any) -> Dict[str, float]:
    """Return the spec's shares normalised to sum to 1, warning on drift."""
    shares = {str(k): float(v) for k, v in (spec.shares or {}).items() if float(v) > 0}
    s = sum(shares.values())
    if not shares or s <= 0:
        return {}
    if abs(s - 1.0) > 0.005:
        warnings.warn(
            f"group_shares on {spec.table}.{spec.measure}: shares sum to "
            f"{s:.3f}, normalising to 1"
        )
    return {k: v / s for k, v in shares.items()}


def _curve_for(spec: Any, schema: Any):
    """The exact-target OutcomeCurve matching this spec's table+measure, if any."""
    try:
        from misata.engines import FactEngine
        engine = FactEngine()
    except Exception:
        return None, None
    for curve in getattr(schema, "outcome_curves", []) or []:
        if (curve.table == spec.table and curve.column == spec.measure
                and engine.curve_has_exact_targets(curve)):
            columns = schema.get_columns(spec.table)
            if columns:
                return curve, engine._resolve_curve(curve, columns)
    return None, None


def declared_group_targets(
    spec: Any, schema: Any
) -> Optional[List[Tuple[Any, Any, Dict[str, float]]]]:
    """Per-bucket declared group targets: [(start, end, {label: target}), ...].

    Only available when an exact-target curve pairs with the spec, because
    that is the only case where the totals being split are themselves
    declared. Returns None otherwise.
    """
    curve, resolved = _curve_for(spec, schema)
    if resolved is None:
        return None
    shares = normalized_shares(spec)
    if not shares:
        return None
    out = []
    for bucket, target in zip(resolved.buckets, resolved.targets):
        out.append((bucket.start, bucket.end,
                    split_total_by_shares(shares, float(target))))
    return out


def apply_group_shares(
    df: pd.DataFrame, spec: Any, schema: Any, rng: np.random.Generator
) -> pd.DataFrame:
    """Overwrite ``group_column`` and rescale ``measure`` so the declared
    shares hold exactly per bucket (curve periods, or one global bucket).

    Row counts per group follow largest-remainder on fraction * bucket rows,
    with at least one row per positive-share group; a bucket with fewer rows
    than positive-share groups is skipped with a warning (infeasible). Within
    each group the measure is rescaled to its target, rounded to cents, and
    the rounding residual lands on the group's largest row, so the bucket
    total still equals the declared period target exactly.
    """
    shares = normalized_shares(spec)
    if not shares or spec.measure not in df.columns or spec.group_column not in df.columns:
        return df

    labels = list(shares.keys())
    fracs = np.array([shares[l] for l in labels])

    curve, resolved = _curve_for(spec, schema)
    if resolved is not None:
        time_col = curve.time_column
        if time_col not in df.columns:
            return df
        times = pd.to_datetime(df[time_col], errors="coerce")
        buckets = [
            (np.where((times >= b.start) & (times < b.end))[0], float(t))
            for b, t in zip(resolved.buckets, resolved.targets)
        ]
    else:
        buckets = [(np.arange(len(df)), float(pd.to_numeric(
            df[spec.measure], errors="coerce").fillna(0).sum()))]

    measure = pd.to_numeric(df[spec.measure], errors="coerce").fillna(0).to_numpy(dtype=float)
    groups = df[spec.group_column].astype(object).to_numpy(copy=True)

    for idx, total in buckets:
        n = idx.size
        if n == 0:
            continue
        if n < len(labels):
            warnings.warn(
                f"group_shares on {spec.table}: bucket with {n} rows cannot "
                f"host {len(labels)} groups; skipping (infeasible)"
            )
            continue
        # Largest-remainder row allocation, minimum one row per group.
        raw = fracs * n
        counts = np.floor(raw).astype(int)
        counts = np.maximum(counts, 1)
        while counts.sum() > n:
            counts[int(np.argmax(counts))] -= 1
        order = np.argsort(-(raw - np.floor(raw)))
        i = 0
        while counts.sum() < n:
            counts[order[i % len(labels)]] += 1
            i += 1

        # Assign labels over a seeded shuffle of the bucket's rows.
        shuffled = idx.copy()
        rng.shuffle(shuffled)
        targets = split_total_by_shares(shares, total)
        pos = 0
        for g_i, label in enumerate(labels):
            rows = shuffled[pos: pos + counts[g_i]]
            pos += counts[g_i]
            groups[rows] = label
            t = targets[label]
            cur = measure[rows].sum()
            if cur > 0:
                measure[rows] = np.round(measure[rows] * (t / cur), 2)
            elif rows.size:
                measure[rows] = np.round(t / rows.size, 2)
            # Residual to the largest row so the group hits t exactly.
            resid = round(t - measure[rows].sum(), 2)
            if resid and rows.size:
                big = rows[int(np.argmax(measure[rows]))]
                measure[big] = round(measure[big] + resid, 2)

    df[spec.group_column] = groups
    df[spec.measure] = np.round(measure, 2)
    return df
