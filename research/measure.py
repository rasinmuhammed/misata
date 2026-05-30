"""
Measurement harness for outcome-driven relational synthesis.

Brick 2 of the research program. Turns Propositions 1-3 of
``research/01_formalization.md`` into reproducible numbers, and serves as the
benchmark scoreboard any *improved* algorithm must beat.

It exercises the real engine (``misata.engines.fact_engine.FactEngine``) directly,
isolating Stage 1 (``_allocate_row_counts``) and Stage 2 (``_generate_exact_values``)
so the math is tested without the rest of the pipeline.

Run:
    .venv/bin/python3 research/measure.py
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from misata.engines.fact_engine import FactEngine, ResolvedCurve  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _dummy_ts(n: int) -> pd.Series:
    """Timestamps are only consumed by non-uniform patterns; supply a valid Series."""
    return pd.Series(pd.date_range("2024-01-01", periods=max(n, 1), freq="h")[:n])


def _make_curve(targets, mu, r_min, r_max, alpha=2.0) -> ResolvedCurve:
    return ResolvedCurve(
        column="y",
        time_column="t",
        time_unit="month",
        buckets=[],                       # _allocate_row_counts only reads the fields below
        targets=np.asarray(targets, dtype=float),
        min_transactions_per_period=r_min,
        max_transactions_per_period=r_max,
        avg_transaction_value=mu,
        concentration=alpha,
    )


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


# --------------------------------------------------------------------------- #
# Proposition 1 — exactness (deterministic identity)
# --------------------------------------------------------------------------- #

def check_prop1_exactness(trials: int = 5000, seed: int = 0) -> Check:
    eng = FactEngine(np.random.default_rng(seed))
    rng = np.random.default_rng(seed + 1)
    max_unit_err = 0
    worst = None

    for _ in range(trials):
        decimals = int(rng.choice([0, 2]))
        m = 10 ** decimals
        n = int(rng.integers(1, 2000))
        # span tiny to large targets, including awkward fractional cents
        target = float(rng.uniform(0.01, 5_000_000)) if decimals else float(rng.integers(0, 5_000_000))
        alpha = float(rng.uniform(0.3, 50.0))

        vals = eng._generate_exact_values(
            target=target, row_count=n, timestamps=_dummy_ts(n),
            decimals=decimals, concentration=alpha, intra_period_pattern="uniform",
        )
        got_units = int(round(float(np.sum(vals)) * m))
        want_units = int(round(target * m))
        err = abs(got_units - want_units)
        if err > max_unit_err:
            max_unit_err, worst = err, (target, n, decimals, alpha)

    passed = max_unit_err == 0
    detail = (f"{trials} trials, max sum error = {max_unit_err} integer units "
              f"(expected 0). worst case: {worst}")
    return Check("Prop 1  exact aggregate (sum_p == round(T_p,d))", passed, detail)


# --------------------------------------------------------------------------- #
# Proposition 2 — marginal law: mean = T/n, CV = sqrt((n-1)/(nα+1))
# --------------------------------------------------------------------------- #

def check_prop2_marginals(seed: int = 0) -> Check:
    eng = FactEngine(np.random.default_rng(seed))
    mu = 150.0
    rows = []
    grid = [(50, 1.0), (200, 2.0), (500, 5.0), (1000, 25.0)]
    ok = True

    for n, alpha in grid:
        target = n * mu                       # unsaturated: E[v] should equal mu = T/n
        pool: List[np.ndarray] = []
        draws = max(1, 2_000_000 // n)        # ~2e6 pooled samples for a tight estimate
        for _ in range(draws):
            v = eng._generate_exact_values(
                target=target, row_count=n, timestamps=_dummy_ts(n),
                decimals=2, concentration=alpha, intra_period_pattern="uniform",
            )
            pool.append(np.asarray(v, dtype=float))
        x = np.concatenate(pool)

        emp_mean = float(x.mean())
        emp_cv = float(x.std() / x.mean())
        th_mean = target / n
        th_cv = math.sqrt((n - 1) / (n * alpha + 1))

        mean_rel = abs(emp_mean - th_mean) / th_mean
        cv_rel = abs(emp_cv - th_cv) / th_cv
        row_ok = mean_rel < 0.01 and cv_rel < 0.03   # 1% mean, 3% CV tolerance
        ok = ok and row_ok
        rows.append((n, alpha, th_mean, emp_mean, th_cv, emp_cv, cv_rel, row_ok))

    lines = ["  n     alpha mean(th->emp)       CV(th->emp)      CV_relerr ok"]
    for n, a, tm, em, tc, ec, cvr, rok in rows:
        lines.append(f"  {n:<5d} {a:<5.1f} {tm:8.2f}->{em:8.2f}  "
                     f"{tc:6.3f}->{ec:6.3f}  {cvr*100:6.2f}%   {'[ok]' if rok else '[XX]'}")
    return Check("Prop 2  marginal law (mean=T/n, CV=sqrt((n-1)/(n*alpha+1)))", ok, "\n".join(lines))


# --------------------------------------------------------------------------- #
# Proposition 3 — exact distortion bound under clamp saturation
# --------------------------------------------------------------------------- #

def check_prop3_distortion(seed: int = 0) -> Check:
    eng = FactEngine(np.random.default_rng(seed))
    mu = 150.0
    r_min, r_max = 10, 1000

    # targets chosen to land in each regime:
    #   upper-clamp saturated (T/μ < r_min):   T = 150*5  -> T/μ = 5  < 10
    #   unsaturated:                            T = 150*300-> T/μ = 300 in [10,1000]
    #   lower-clamp saturated (T/μ > r_max):    T = 150*5000->T/μ=5000 > 1000
    targets = np.array([mu * 5, mu * 300, mu * 5000], dtype=float)
    curve = _make_curve(targets, mu, r_min, r_max)
    n = eng._allocate_row_counts(fallback_row_count=1000, curve=curve)

    rows = []
    ok = True
    for p, (T, np_) in enumerate(zip(targets, n)):
        rho = T / (np_ * mu)
        ratio = T / mu
        if ratio < r_min:
            predicted = T / (r_min * mu)            # upper-clamp branch
            regime = "upper-clamp"
        elif ratio > r_max:
            predicted = T / (r_max * mu)            # lower-clamp branch
            regime = "lower-clamp"
        else:
            predicted = 1.0                         # unsaturated
            regime = "unsaturated"
        rel = abs(rho - predicted) / predicted
        row_ok = rel < 0.02
        ok = ok and row_ok
        rows.append((p, regime, ratio, int(np_), rho, predicted, rel, row_ok))

    lines = ["  period regime        T/mu     n_p     rho(emp->pred)    relerr  ok"]
    for p, reg, ratio, np_, rho, pred, rel, rok in rows:
        lines.append(f"  {p:<6d} {reg:<13s} {ratio:8.1f} {np_:<7d} "
                     f"{rho:7.3f}->{pred:7.3f}  {rel*100:6.2f}%  {'[ok]' if rok else '[XX]'}")
    lines.append("  -> marginals undistorted (rho~1) iff T/mu in [r_min, r_max]; "
                 "else rho = closed-form clamp ratio.")
    return Check("Prop 3  distortion rho_p = T_p/(n_p*mu) matches closed form", ok, "\n".join(lines))


# --------------------------------------------------------------------------- #
# end-to-end sanity: public API rolls up to the curve (no fabrication)
# --------------------------------------------------------------------------- #

def check_e2e_rollup(seed: int = 42) -> Check:
    import misata
    tables = misata.generate(
        "SaaS company with 5k users — MRR $50k in January, $100k in June, $200k in December",
        rows=5000, seed=seed,
    )
    subs = tables["subscriptions"]
    subs = subs.copy()
    subs["month"] = pd.to_datetime(subs["start_date"]).dt.to_period("M").astype(str)
    monthly = subs.groupby("month")["mrr"].sum()
    jan = monthly.iloc[0]
    dec = monthly.iloc[-1]
    ok = abs(jan - 50_000) < 1.0 and abs(dec - 200_000) < 1.0
    detail = f"Jan sum = {jan:,.2f} (target 50,000), Dec sum = {dec:,.2f} (target 200,000)"
    return Check("E2E   NL story → microdata rolls up to curve", ok, detail)


# --------------------------------------------------------------------------- #

def main() -> None:
    checks = [
        check_prop1_exactness(),
        check_prop2_marginals(),
        check_prop3_distortion(),
        check_e2e_rollup(),
    ]
    print("\n" + "=" * 74)
    print("  MISATA RESEARCH HARNESS — baseline (fact_engine.py) validation")
    print("=" * 74)
    for c in checks:
        status = "PASS" if c.passed else "FAIL"
        print(f"\n[{status}] {c.name}")
        for line in c.detail.splitlines():
            print(f"   {line}")
    n_pass = sum(c.passed for c in checks)
    print("\n" + "-" * 74)
    print(f"  {n_pass}/{len(checks)} checks passed")
    print("-" * 74 + "\n")
    raise SystemExit(0 if n_pass == len(checks) else 1)


if __name__ == "__main__":
    main()
