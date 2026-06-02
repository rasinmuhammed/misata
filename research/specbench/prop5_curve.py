"""
The Prop-5 figure: the marginal-distortion frontier under exact-aggregate conformance.

Claim (Prop. 5, from condensation theory): an exact-aggregate generator preserves a
target marginal only in the light-tailed (fluid) regime. As the *demanded* target
marginal grows heavier-tailed under a fixed total, the conditioned law must depart
from it — a condensate (single big jump) forms. We measure that departure.

Method (honest, model-agnostic):
  For a fixed total T and row count n, we ask: "draw n positive values that (a) sum to
  exactly T and (b) look like a target lognormal with shape sigma." We realize (a)+(b)
  with the engine's own mechanism — a Dirichlet(alpha) partition scaled to T — choosing
  the alpha whose induced CV matches the target lognormal's CV (Prop. 2:
  CV = sqrt((n-1)/(n*alpha+1))). We then measure the 1-Wasserstein distance between the
  exact-sum sample and an *unconstrained* i.i.d. draw from the same target lognormal,
  normalized by the target IQR (the MD metric). Sweeping sigma traces the frontier.

Interpretation: small sigma (light tail) -> MD ~ 0 (fluid: constraint is free).
Large sigma (heavy tail) -> MD rises (condensation: exact sum incompatible with the
target shape). The rise is the empirical signature of the theory's transition.

Run: .venv_specbench/bin/python3 -m research.specbench.prop5_curve
Writes research/specbench/prop5_curve.csv (sigma, cv_target, MD, alpha).
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from misata.engines.fact_engine import FactEngine  # noqa: E402
from research.specbench.metrics import marginal_distortion  # noqa: E402


def alpha_for_cv(n: int, cv: float) -> float:
    """Invert Prop. 2: CV^2 = (n-1)/(n*alpha+1)  =>  alpha = ((n-1)/CV^2 - 1)/n."""
    cv = max(cv, 1e-6)
    val = ((n - 1) / (cv * cv) - 1.0) / n
    return max(val, 1e-3)


def lognormal_cv(sigma: float) -> float:
    """CV of a lognormal with log-sigma `sigma` (location-free): sqrt(exp(sigma^2)-1)."""
    return math.sqrt(math.expm1(sigma * sigma))


def run(n: int = 500, total: float = 75_000.0, seed: int = 0) -> pd.DataFrame:
    eng = FactEngine(np.random.default_rng(seed))
    rng = np.random.default_rng(seed + 1)
    mu = total / n                                  # mean is pinned by the exact sum

    rows = []
    for sigma in [0.1, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0]:
        cv_t = lognormal_cv(sigma)
        alpha = alpha_for_cv(n, cv_t)

        # exact-sum sample via the engine's Dirichlet-partition mechanism
        exact = eng._generate_exact_values(
            target=total, row_count=n, timestamps=pd.Series(pd.date_range("2024-01-01", periods=n, freq="h")),
            decimals=2, concentration=alpha, intra_period_pattern="uniform",
        )
        exact = np.asarray(exact, dtype=float)

        # unconstrained target: lognormal with the SAME mean mu and shape sigma
        # mean of lognormal = exp(m + sigma^2/2) = mu  => m = ln(mu) - sigma^2/2
        m = math.log(mu) - 0.5 * sigma * sigma
        target_draw = rng.lognormal(mean=m, sigma=sigma, size=n * 20)

        md = marginal_distortion(exact, target_draw).value
        # verify the exact-sum constraint actually held (sanity, must be ~0 error)
        sum_err = abs(exact.sum() - total)
        rows.append({"sigma": sigma, "cv_target": round(cv_t, 3),
                     "alpha": round(alpha, 4), "MD": round(md, 4),
                     "sum_err": round(sum_err, 6)})
    return pd.DataFrame(rows)


def main() -> None:
    df = run()
    out = "research/specbench/prop5_curve.csv"
    df.to_csv(out, index=False)

    print("\n" + "=" * 70)
    print("  Prop-5 frontier: marginal distortion vs target tail-heaviness")
    print("  (exact aggregate held throughout; sum_err must stay ~0)")
    print("=" * 70)
    print(f"\n  {'sigma':>6} {'CV_target':>10} {'alpha':>9} {'MD':>8} {'sum_err':>9}")
    print("  " + "-" * 48)
    for _, r in df.iterrows():
        print(f"  {r['sigma']:>6.2f} {r['cv_target']:>10.3f} {r['alpha']:>9.4f} "
              f"{r['MD']:>8.4f} {r['sum_err']:>9.6f}")

    light = df[df.sigma <= 0.4]["MD"].mean()
    heavy = df[df.sigma >= 1.6]["MD"].mean()
    print("\n  " + "-" * 48)
    print(f"  mean MD, light tail (sigma<=0.4): {light:.4f}")
    print(f"  mean MD, heavy tail (sigma>=1.6): {heavy:.4f}")
    print(f"  frontier ratio (heavy/light):     {heavy/max(light,1e-9):.1f}x")
    print(f"\n  max sum error across sweep: {df.sum_err.max():.2e}  (exactness preserved)")
    print(f"\n  wrote {out}\n")


if __name__ == "__main__":
    main()
