"""
The Prop-5 figure: the marginal-distortion frontier under exact-aggregate conformance,
WITH the unconstrained control that isolates the condensation effect (review fix B1).

The claim (Prop. 5, condensation theory): conditioning a positive i.i.d. population on
a fixed sum preserves the marginal in the light-tailed (fluid) regime, but distorts it
in the heavy-tailed regime where a condensate (single big jump) forms.

CONFOUND WE MUST AVOID (review B1): if we compare a Dirichlet/Beta exact-sum sample to a
*lognormal* target, the rising distance could be Beta-vs-lognormal family mismatch, not
condensation. To isolate the effect we hold the FAMILY fixed and compare:

    constrained:    X_i drawn i.i.d. Gamma(shape k), THEN conditioned on sum = T
                    (this is exactly the engine's Dirichlet mechanism; Prop. 0)
    unconstrained:  X_i drawn i.i.d. Gamma(shape k), NOT conditioned (sum free)

Both have the SAME marginal family and the SAME target shape g = Gamma(k). We measure,
for each, the 1-Wasserstein distance to that common target g. The CONDENSATION COST is
the GAP:  MD_constrained - MD_unconstrained.  Family mismatch cancels in the gap.

We sweep tail-heaviness by lowering the Gamma shape k (smaller k = heavier tail;
CV = 1/sqrt(k)). Gamma is subexponential-enough at small k to exhibit the transition,
and crucially the engine's law is *exactly* the Gamma-conditional (Prop. 0), so this is
the honest, on-mechanism test — no cross-family confound.

Run: .venv_specbench/bin/python3 -m research.specbench.prop5_curve
Writes research/specbench/prop5_curve.csv.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from misata.engines.fact_engine import FactEngine  # noqa: E402
from research.specbench.metrics import marginal_distortion  # noqa: E402


def cv_from_shape(k: float) -> float:
    """Gamma(shape=k) coefficient of variation = 1/sqrt(k)."""
    return 1.0 / math.sqrt(k)


def run(n: int = 500, total: float = 75_000.0, n_seeds: int = 10) -> pd.DataFrame:
    """Sweep Gamma shape k; for each, measure constrained vs unconstrained MD to the
    common Gamma(k) target, over n_seeds. Returns per-(k,seed) rows."""
    mu = total / n                       # exact-sum pins the mean
    theta = mu                           # Gamma scale so that mean = k*theta when... see below
    # We want the TARGET marginal to be Gamma(shape=k, mean=mu): scale = mu/k.
    shapes = [8.0, 5.0, 3.0, 2.0, 1.5, 1.0, 0.7, 0.5, 0.35, 0.25, 0.18, 0.12]

    rows = []
    for k in shapes:
        cv = cv_from_shape(k)
        # The engine's Dirichlet(alpha) with alpha=k reproduces Gamma(k)-conditional-on-sum
        # EXACTLY (Prop. 0): normalized i.i.d. Gamma(k) ~ Dirichlet(k,...,k).
        alpha = k
        scale = mu / k                   # Gamma(shape=k, scale=mu/k) has mean mu
        for s in range(n_seeds):
            eng = FactEngine(np.random.default_rng(1000 + s))
            rng = np.random.default_rng(7000 + s)

            # --- constrained: engine's exact-sum Gamma-conditional sample ---
            constrained = np.asarray(eng._generate_exact_values(
                target=total, row_count=n,
                timestamps=pd.Series(pd.date_range("2024-01-01", periods=n, freq="h")),
                decimals=2, concentration=alpha, intra_period_pattern="uniform",
            ), dtype=float)

            # --- unconstrained: i.i.d. Gamma(k, mu/k), sum NOT fixed ---
            unconstrained = rng.gamma(shape=k, scale=scale, size=n)

            # --- common target: a large i.i.d. Gamma(k, mu/k) reference ---
            target = rng.gamma(shape=k, scale=scale, size=n * 40)

            md_c = marginal_distortion(constrained, target).value
            md_u = marginal_distortion(unconstrained, target).value
            sum_err = abs(constrained.sum() - total)

            rows.append({
                "shape_k": k, "cv": round(cv, 3),
                "MD_constrained": md_c, "MD_unconstrained": md_u,
                "gap": md_c - md_u, "sum_err": sum_err, "seed": s,
            })
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("shape_k")
    out = g.agg(
        cv=("cv", "first"),
        MD_constrained=("MD_constrained", "mean"),
        MD_constrained_sd=("MD_constrained", "std"),
        MD_unconstrained=("MD_unconstrained", "mean"),
        MD_unconstrained_sd=("MD_unconstrained", "std"),
        gap=("gap", "mean"),
        gap_sd=("gap", "std"),
        max_sum_err=("sum_err", "max"),
    ).reset_index().sort_values("shape_k", ascending=False)
    return out


def main() -> None:
    df = run()
    summ = summarize(df)
    df.to_csv("research/specbench/prop5_curve.csv", index=False)
    summ.to_csv("research/specbench/prop5_summary.csv", index=False)

    print("\n" + "=" * 86)
    print("  Prop-5 frontier WITH unconstrained control (review fix B1) — 10 seeds")
    print("  condensation cost = GAP = MD_constrained - MD_unconstrained (same family;")
    print("  family-mismatch cancels). exact sum held throughout (max_sum_err ~ 0).")
    print("=" * 86)
    print(f"\n  {'k':>5} {'CV':>6} {'MD_constr':>11} {'MD_uncon':>10} {'GAP':>9} {'gap_sd':>8} {'sumerr':>8}")
    print("  " + "-" * 70)
    for _, r in summ.iterrows():
        print(f"  {r['shape_k']:>5.2f} {r['cv']:>6.2f} "
              f"{r['MD_constrained']:>11.4f} {r['MD_unconstrained']:>10.4f} "
              f"{r['gap']:>9.4f} {r['gap_sd']:>8.4f} {r['max_sum_err']:>8.1e}")

    light = summ[summ.shape_k >= 5.0]["gap"].mean()
    heavy = summ[summ.shape_k <= 0.25]["gap"].mean()
    print("\n  " + "-" * 70)
    print(f"  mean GAP, light tail (k>=5,  CV<=0.45): {light:+.4f}")
    print(f"  mean GAP, heavy tail (k<=0.25, CV>=2.0): {heavy:+.4f}")
    if abs(light) > 1e-9:
        print(f"  heavy/light gap ratio:                  {heavy/light:.1f}x")
    print(f"\n  VERDICT: condensation gap {'SURVIVES' if heavy > 3*max(light,1e-6) else 'DOES NOT clearly survive'} "
          f"the control.")
    print("\n  wrote prop5_curve.csv (per-seed) + prop5_summary.csv\n")


if __name__ == "__main__":
    main()
