"""
P-star frontier (E11): map the boundary the engine does NOT cross, correctly controlled.

The engine produces a Gamma-family shape under an exact sum (Prop. 0, Prop. 4). For a target
external marginal F, it therefore cannot match F in general. The question this experiment
answers is *what* the obstacle is: the exact-sum constraint, or the shape-family choice.

For each target family F (lognormal over sigma, Pareto over tail index b) we match the
engine's marginal CV to F's CV, then compare three normalized 1-Wasserstein distances to a
large F reference:
  - MD_constrained:   engine's exact-sum sample vs F
  - MD_unconstrained: an i.i.d. Gamma draw of the SAME (shape, mean), no sum constraint, vs F
  - MD_floor:         a second i.i.d. F sample vs F   (finite-sample estimator floor)

If MD_constrained ≈ MD_unconstrained, the exact-sum constraint contributes ~0 to the miss,
and the residual above MD_floor is pure shape-family mismatch. That locates P-star as a
family problem, not a constraint problem, which is the honest and useful statement. This is
the correctly-controlled successor to the retracted "condensation frontier."

Run:  PYTHONPATH=. python3 research/specbench/pstar_frontier.py
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from misata.engines.fact_engine import FactEngine
from research.specbench.metrics import marginal_distortion


def _ts(n):
    return pd.Series(pd.date_range("2024-01-01", periods=max(n, 1), freq="h")[:n])


def lognormal_sample(n, mu, sigma, rng):
    mlog = np.log(mu) - 0.5 * sigma**2          # so E[X] = mu
    return rng.lognormal(mean=mlog, sigma=sigma, size=n)


def pareto_sample(n, mu, b, rng):
    xm = mu * (b - 1.0) / b                       # so E[X] = mu (b > 1)
    return xm / np.power(rng.random(n), 1.0 / b)


def cv_of(family, p):
    if family == "lognormal":
        return float(np.sqrt(np.exp(p**2) - 1.0))
    # Pareto: CV finite only for b > 2
    b = p
    return float(np.sqrt(1.0 / (b * (b - 2.0)))) if b > 2.0 else float("inf")


def run(n=4000, n_ref=40000, mu=100.0, decimals=4,
        seeds=(42, 43, 44, 45, 46, 47, 48, 49, 50, 51)):
    grid = ([("lognormal", s) for s in (0.3, 0.5, 0.7, 0.9, 1.1, 1.3)]
            + [("pareto", b) for b in (10.0, 6.0, 4.0, 3.0, 2.5)])
    rows = []
    for family, p in grid:
        cv = cv_of(family, p)
        # match engine concentration to F's CV (engine CV -> 1/sqrt(alpha)); if CV is
        # infinite (heavy Pareto), the engine cannot even match the 2nd moment: use a
        # heavy but finite alpha and flag it.
        alpha = (1.0 / cv**2) if np.isfinite(cv) and cv > 0 else 0.3
        cv_matchable = bool(np.isfinite(cv))
        mc, mu_, mf, sumerr = [], [], [], []
        for sd in seeds:
            rng = np.random.default_rng(sd)
            eng = FactEngine(np.random.default_rng(sd))
            T = n * mu
            v = np.asarray(eng._generate_exact_values(
                target=T, row_count=n, timestamps=_ts(n),
                decimals=decimals, concentration=alpha,
                intra_period_pattern="uniform"), dtype=float)
            g = rng.gamma(shape=alpha, scale=mu / alpha, size=n)   # same family, no sum constraint
            ref = (lognormal_sample(n_ref, mu, p, rng) if family == "lognormal"
                   else pareto_sample(n_ref, mu, p, rng))
            ref2 = (lognormal_sample(n, mu, p, rng) if family == "lognormal"
                    else pareto_sample(n, mu, p, rng))
            mc.append(marginal_distortion(v, ref).value)
            mu_.append(marginal_distortion(g, ref).value)
            mf.append(marginal_distortion(ref2, ref).value)
            sumerr.append(abs(float(v.sum()) - T))
        rows.append({
            "family": family, "param": p, "cv_F": round(cv, 3) if np.isfinite(cv) else np.inf,
            "cv_matchable": cv_matchable, "alpha": round(alpha, 4),
            "MD_constrained": np.mean(mc), "MD_unconstrained": np.mean(mu_),
            "MD_floor": np.mean(mf),
            "constraint_cost": np.mean(mc) - np.mean(mu_),   # exact-sum cost in MD
            "family_gap": np.mean(mu_) - np.mean(mf),        # shape mismatch above floor
            "max_sum_err": max(sumerr),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = run()
    out = "research/specbench/results_pstar_frontier.csv"
    df.to_csv(out, index=False)
    pd.set_option("display.width", 200, "display.max_columns", 20)
    print(df.to_string(index=False))
    print(f"\nmax |constraint_cost| over grid = {df.constraint_cost.abs().max():.4f}")
    print(f"max sum error over grid         = {df.max_sum_err.max():.2e}")
    print(f"wrote {out}")
