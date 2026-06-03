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


def _resolve_alias(columns, candidates):
    """Return the first candidate present in columns (case-insensitive), else None."""
    lower = {str(c).lower(): c for c in columns}
    for cand in candidates:
        if cand is not None and str(cand).lower() in lower:
            return lower[str(cand).lower()]
    return None


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
    if table not in tables:
        return MetricResult("AME", float("inf"), f"missing table {table}")

    cols = tables[table].columns
    # Resolve metric & time columns tolerantly: generators name things differently
    # (ordered_at vs order_date vs date). Comparison stays fair — we look for the
    # same semantic column in each generator's own output.
    m_col = metric_col if metric_col in cols else _resolve_alias(
        cols, [metric_col, "amount", "value", "revenue", "total", "mrr"])
    t_col = time_col if time_col in cols else _resolve_alias(
        cols, [time_col, "ordered_at", "order_date", "date", "start_date",
               "created_at", "timestamp"])
    if m_col is None or t_col is None:
        return MetricResult("AME", float("inf"),
                            f"no metric/time column in {table} (have {list(cols)})")

    df = tables[table][[t_col, m_col]].copy().rename(
        columns={t_col: time_col, m_col: metric_col})
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col])

    # Period labels may be full ('2024-01', freq='M') or month-of-year ('01') for
    # year-agnostic specs. Detect from the target keys and bucket to match.
    month_only = all(len(str(k)) == 2 for k in period_targets)
    if month_only:
        df["__period__"] = df[time_col].dt.strftime("%m")
    else:
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
# RCE — Rate-Conformance Error: |declared rate - realized rate| for a fraction target
#       (e.g. churn %, fraud %). Generalizes outcome conformance from sums to rates.
# --------------------------------------------------------------------------- #

def rate_conformance_error(
    tables: Dict[str, pd.DataFrame],
    table: str,
    column: str,
    positive_value,
    target_rate: float,
) -> MetricResult:
    """|realized_rate - target_rate|, where realized_rate = mean(column == positive_value).
    0.0 = exact. Demonstrates that outcome conformance is not limited to temporal sums."""
    if table not in tables or column not in tables[table].columns:
        return MetricResult("RCE", float("inf"), f"missing {table}.{column}")
    s = tables[table][column]
    realized = float((s == positive_value).mean())
    return MetricResult("RCE", abs(realized - target_rate),
                        f"realized={realized:.3f} vs target={target_rate:.3f}")


# --------------------------------------------------------------------------- #
# GDC — Group-Distribution Conformance: total-variation distance between the
#       declared category shares and the realized shares. 0.0 = exact match.
# --------------------------------------------------------------------------- #

def group_distribution_conformance(
    tables: Dict[str, pd.DataFrame],
    table: str,
    column: str,
    target_shares: Dict[str, float],
) -> MetricResult:
    """TVD = 0.5 * sum_k |realized_k - declared_k| over declared categories. 0 = exact."""
    if table not in tables or column not in tables[table].columns:
        return MetricResult("GDC", float("inf"), f"missing {table}.{column}")
    vc = tables[table][column].value_counts(normalize=True)
    tvd = 0.5 * sum(abs(float(vc.get(k, 0.0)) - p) for k, p in target_shares.items())
    return MetricResult("GDC", tvd,
                        f"realized={ {k: round(float(vc.get(k,0)),3) for k in target_shares} }")


# --------------------------------------------------------------------------- #
# MP — Marginal Plausibility (review B5): drift of the generated metric marginal
#       from the spec-implied domain-calibrated reference.
# --------------------------------------------------------------------------- #

def marginal_plausibility(
    tables: Dict[str, pd.DataFrame],
    table: str,
    metric_col: str,
    implied_mean: float,
    sigma: float = 0.6,
    n_ref: int = 200_000,
    seed: int = 0,
) -> MetricResult:
    """DEPRECATED / INVALID — kept for the scientific record (review B5 finding).

    This metric was an attempt to show blind rescaling distorts the marginal. It is
    **invalid** and must NOT be used as a headline: it compares the generated marginal to
    a lognormal at `implied_mean = total_targets / total_rows`, which wrongly assumes
    every row carries metric value. Models that legitimately differ on the *fraction* of
    value-bearing rows (e.g. a SaaS model with free-tier $0 subscriptions has a higher
    mean over paying rows) are penalized for being MORE realistic. Empirically it ranked
    Faker best and Misata worst — an artifact of the ill-defined reference, not a real
    plausibility ordering. We report distributional stats (CV/skew) and the categorical
    input-type axis instead; see `08_adversarial_review_round3.md` B5 resolution.
    """
    if table not in tables:
        return MetricResult("MP", float("inf"), f"missing table {table}")
    cols = tables[table].columns
    m_col = metric_col if metric_col in cols else _resolve_alias(
        cols, [metric_col, "amount", "value", "mrr", "revenue", "total"])
    if m_col is None:
        return MetricResult("MP", float("inf"), f"no metric column in {table}")

    realized = pd.to_numeric(tables[table][m_col], errors="coerce").dropna().to_numpy()
    realized = realized[realized > 0]                # lognormal reference is positive
    if realized.size == 0:
        return MetricResult("MP", float("inf"), "no positive metric values")

    rng = np.random.default_rng(seed)
    mu = np.log(max(implied_mean, 1e-9)) - 0.5 * sigma * sigma
    reference = rng.lognormal(mean=mu, sigma=sigma, size=n_ref)

    md = marginal_distortion(realized, reference)
    return MetricResult("MP", md.value,
                        f"gen_mean={realized.mean():.1f} vs implied={implied_mean:.1f}; "
                        f"gen_max={realized.max():.0f}")


# --------------------------------------------------------------------------- #
# CSAT — hard-constraint satisfaction
# --------------------------------------------------------------------------- #

def constraint_satisfaction(
    tables: Dict[str, pd.DataFrame],
    constraints: List[Dict[str, Any]],
) -> MetricResult:
    """Fraction of declared hard constraints satisfied (1.0 = all satisfied).

    Each constraint dict: {table, column, op, value} with op in
    {">=","<=",">","<"}, or {table, column, op:"between", low, high}.
    A constraint is 'satisfied' iff EVERY row obeys it. Blind aggregate-rescaling
    (NaiveRescale) typically violates range constraints because multiplying to hit a
    sum pushes values out of their declared bounds.
    """
    if not constraints:
        return MetricResult("CSAT", 1.0, "no hard constraints")

    satisfied = 0
    detail = []
    for c in constraints:
        t, col = c["table"], c["column"]
        if t not in tables or col not in tables[t].columns:
            detail.append(f"{t}.{col}:MISSING"); continue
        s = pd.to_numeric(tables[t][col], errors="coerce").dropna()
        op = c["op"]
        if op == "between":
            ok = bool((s >= c["low"]).all() and (s <= c["high"]).all())
        elif op == ">=":
            ok = bool((s >= c["value"]).all())
        elif op == "<=":
            ok = bool((s <= c["value"]).all())
        elif op == ">":
            ok = bool((s > c["value"]).all())
        elif op == "<":
            ok = bool((s < c["value"]).all())
        else:
            ok = False
        satisfied += int(ok)
        frac_bad = float((~_obey(s, c)).mean()) if not ok else 0.0
        detail.append(f"{t}.{col}{op}:{'ok' if ok else f'{frac_bad:.0%}bad'}")

    return MetricResult("CSAT", satisfied / len(constraints), "; ".join(detail))


def _obey(s: pd.Series, c: Dict[str, Any]) -> pd.Series:
    op = c["op"]
    if op == "between":
        return (s >= c["low"]) & (s <= c["high"])
    if op == ">=":
        return s >= c["value"]
    if op == "<=":
        return s <= c["value"]
    if op == ">":
        return s > c["value"]
    if op == "<":
        return s < c["value"]
    return pd.Series(False, index=s.index)


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
