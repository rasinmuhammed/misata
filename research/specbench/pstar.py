"""
P-star (E10): exact monthly sum AND a specified external heavy-tailed marginal.

The engine hits the sum exactly (Prop. 1) but, by Prop. 4, fixes a Gamma-family shape
and so cannot reproduce an arbitrary external marginal F. This script measures both axes
on a Pareto target and writes results_pstar.csv. This is the task SpecBench reports as a
Misata FAILURE on the marginal-match axis, on purpose.

Run:  PYTHONPATH=. python3 research/specbench/pstar.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from misata.engines.fact_engine import FactEngine
from research.specbench.metrics import marginal_distortion


def _dummy_ts(n: int) -> pd.Series:
    return pd.Series(pd.date_range("2024-01-01", periods=max(n, 1), freq="h")[:n])


def pareto_reference(n: int, mu: float, b: float, rng: np.random.Generator) -> np.ndarray:
    """Pareto(b) sample whose mean equals mu (so it shares scale with the target).
    Mean of a Pareto with shape b>1 and minimum xm is b*xm/(b-1); solve xm for mean=mu."""
    xm = mu * (b - 1.0) / b
    u = rng.random(n)
    return xm / np.power(u, 1.0 / b)          # inverse-CDF draw of Pareto(b, xm)


def run(seeds=(42, 43, 44, 45, 46, 47, 48, 49, 50, 51),
        n=1000, mu=150.0, b=1.5, decimals=2) -> pd.DataFrame:
    target = n * mu
    rows = []
    for sd in seeds:
        eng = FactEngine(np.random.default_rng(sd))
        vals = np.asarray(eng._generate_exact_values(
            target=target, row_count=n, timestamps=_dummy_ts(n),
            decimals=decimals, concentration=2.0, intra_period_pattern="uniform",
        ), dtype=float)
        ref = pareto_reference(n, mu, b, np.random.default_rng(sd + 10_000))
        sum_err = abs(float(vals.sum()) - target)
        md = marginal_distortion(vals, ref).value      # normalized 1-Wasserstein
        rows.append({"seed": sd, "n": n, "target": target,
                     "sum_err": sum_err, "MD_pareto": md})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = run()
    out = "research/specbench/results_pstar.csv"
    df.to_csv(out, index=False)
    print(df.to_string(index=False))
    print(f"\nmean sum_err = {df.sum_err.mean():.3e}   "
          f"mean MD(Pareto) = {df.MD_pareto.mean():.3f} ± {df.MD_pareto.std():.3f}")
    print(f"wrote {out}")
