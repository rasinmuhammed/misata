"""
SpecBench metrics.

Each metric is a pure function of generated tables + a task specification. No metric
reads from any generator's internals, so the same metric applies to every baseline
on equal footing. All metrics are deterministic given their inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class MetricResult:
    name: str
    value: float
    detail: str = ""


# --------------------------------------------------------------------------- #
# AME — Aggregate-Match Error
# --------------------------------------------------------------------------- #

def aggregate_match_error(
    tables: Dict[str, pd.DataFrame],
    table: str,
    metric_col: str,
    time_col: str,
    period_targets: Dict[str, float],
    freq: str = "M",
) -> MetricResult:
    """max_p |realized_p - target_p| / |target_p|, over specified periods.

    period_targets maps a period label (e.g. '2024-01') to the required SUM of
    metric_col over rows whose time_col falls in that period. Exact generators
    score 0.0.
    """
    if table not in tables or metric_col not in tables[table].columns:
        return MetricResult("AME", float("inf"), f"missing {table}.{metric_col}")

    df = tables[table][[time_col, metric_col]].copy()
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col])
    df["__period__"] = df[time_col].dt.to_period(freq).astype(str)
    realized = df.groupby("__period__")[metric_col].sum()

    worst = 0.0
    worst_p = None
    for period, target in period_targets.items():
        got = float(realized.get(period, 0.0))
        denom = abs(target) if abs(target) > 1e-9 else 1.0
        rel = abs(got - target) / denom
        if rel > worst:
            worst, worst_p = rel, (period, target, got)

    detail = "exact" if worst == 0.0 else f"worst period {worst_p}"
    return MetricResult("AME", worst, detail)


# --------------------------------------------------------------------------- #
# FIVR — FK-Integrity Violation Rate
# --------------------------------------------------------------------------- #

def fk_integrity_violation_rate(
    tables: Dict[str, pd.DataFrame],
    fks: List[Tuple[str, str, str, str]],
) -> MetricResult:
    """Fraction of child rows whose FK value has no matching parent key.

    fks: list of (parent_table, parent_key, child_table, child_key).
    Averaged over all FK edges, weighted by child row count. 0.0 = perfect.
    """
    if not fks:
        return MetricResult("FIVR", 0.0, "no FK edges")

    total_rows = 0
    total_violations = 0
    per_edge = []
    for parent_t, parent_k, child_t, child_k in fks:
        if parent_t not in tables or child_t not in tables:
            per_edge.append(f"{child_t}.{child_k}->MISSING")
            continue
        parent_df, child_df = tables[parent_t], tables[child_t]
        if parent_k not in parent_df.columns or child_k not in child_df.columns:
            per_edge.append(f"{child_t}.{child_k}->NOKEY")
            continue
        valid = set(parent_df[parent_k].dropna().unique())
        child_vals = child_df[child_k].dropna()
        violations = int((~child_vals.isin(valid)).sum())
        total_rows += len(child_vals)
        total_violations += violations
        per_edge.append(f"{child_t}.{child_k}:{violations}/{len(child_vals)}")

    rate = (total_violations / total_rows) if total_rows else 0.0
    return MetricResult("FIVR", rate, "; ".join(per_edge))


# --------------------------------------------------------------------------- #
# MD — Marginal Distortion (1-Wasserstein, scale-normalized)
# --------------------------------------------------------------------------- #

def marginal_distortion(
    realized_values: np.ndarray,
    reference_values: np.ndarray,
) -> MetricResult:
    """Normalized 1-Wasserstein distance between realized and reference marginals.

    Normalized by the reference IQR so the metric is scale-free and comparable
    across columns. Requires scipy; falls back to a quantile-L1 proxy if absent.
    """
    realized = np.asarray(realized_values, dtype=float)
    reference = np.asarray(reference_values, dtype=float)
    realized = realized[np.isfinite(realized)]
    reference = reference[np.isfinite(reference)]
    if realized.size == 0 or reference.size == 0:
        return MetricResult("MD", float("inf"), "empty input")

    q1, q3 = np.percentile(reference, [25, 75])
    scale = (q3 - q1) if (q3 - q1) > 1e-9 else (np.std(reference) or 1.0)

    try:
        from scipy.stats import wasserstein_distance
        w = float(wasserstein_distance(realized, reference))
    except Exception:
        grid = np.linspace(0.01, 0.99, 99)
        w = float(np.mean(np.abs(np.quantile(realized, grid) - np.quantile(reference, grid))))

    return MetricResult("MD", w / scale, f"W1={w:.4g}, scale(IQR)={scale:.4g}")


# --------------------------------------------------------------------------- #
# CR — Controllability Response error
# --------------------------------------------------------------------------- #

def controllability_response(
    ame_after_change: float,
) -> MetricResult:
    """Does the generator track a changed specification?

    Operationally: re-specify a target (e.g. double December), regenerate, and
    measure AME against the NEW targets. A controllable generator keeps AME ~ 0;
    a generator that ignores the spec shows large error. We pass through the
    post-change AME so the runner can compute it with the same AME function.
    """
    return MetricResult("CR", float(ame_after_change), "AME against changed spec")


# --------------------------------------------------------------------------- #
# DET — Determinism
# --------------------------------------------------------------------------- #

def determinism(
    tables_a: Dict[str, pd.DataFrame],
    tables_b: Dict[str, pd.DataFrame],
) -> MetricResult:
    """1.0 if two same-seed runs are bitwise-identical across all tables, else 0.0."""
    if set(tables_a) != set(tables_b):
        return MetricResult("DET", 0.0, "table sets differ")
    for name in tables_a:
        a, b = tables_a[name], tables_b[name]
        if a.shape != b.shape or list(a.columns) != list(b.columns):
            return MetricResult("DET", 0.0, f"{name} shape/cols differ")
        try:
            pd.testing.assert_frame_equal(
                a.reset_index(drop=True), b.reset_index(drop=True),
                check_dtype=False, check_exact=True,
            )
        except AssertionError:
            return MetricResult("DET", 0.0, f"{name} values differ")
    return MetricResult("DET", 1.0, "bitwise identical")
