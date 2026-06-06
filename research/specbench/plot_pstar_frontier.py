"""
Money figure for E11: the P-star frontier. Plots, against the target marginal's CV, the
normalized 1-Wasserstein distance of (a) the engine's exact-sum sample, (b) an unconstrained
same-family Gamma draw, and (c) the finite-sample floor. The (a)-(b) gap (the cost of
enforcing the exact aggregate) is shaded; it stays near zero while the distance to the target
grows with tail-heaviness. Reads from results_pstar_frontier.csv.

Run:  PYTHONPATH=. python3 research/specbench/plot_pstar_frontier.py
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.read_csv("research/specbench/results_pstar_frontier.csv")
df = df[np.isfinite(df["cv_F"])]

fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.4), sharey=True)
panels = [("lognormal", "lognormal target  (σ ↑ ⇒ tail-heaviness ↑)"),
          ("pareto", "Pareto target  (tail index ↓ ⇒ tail-heaviness ↑)")]

for ax, (fam, title) in zip(axes, panels):
    d = df[df["family"] == fam].sort_values("cv_F")
    cv = d["cv_F"].to_numpy()
    ax.plot(cv, d["MD_constrained"], "o-", color="#b2182b", lw=2.2, ms=6,
            label="exact-sum engine")
    ax.plot(cv, d["MD_unconstrained"], "s--", color="#2166ac", lw=1.8, ms=5,
            label="unconstrained same-family draw")
    ax.plot(cv, d["MD_floor"], "^:", color="#4d4d4d", lw=1.5, ms=5,
            label="finite-sample floor")
    ax.fill_between(cv, d["MD_floor"], d["MD_unconstrained"], color="#fdae61", alpha=0.35,
                    label="shape-family gap")
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("CV of target marginal")
    ax.grid(True, alpha=0.3)

axes[0].set_ylabel("normalized 1-Wasserstein distance to target")
axes[0].legend(frameon=False, fontsize=8.5, loc="upper left")
fig.suptitle("P★ frontier: the exact-aggregate constraint is nearly free (red ≈ blue, gap ≤ 0.006).\n"
             "The distance to an external target marginal is shape-family mismatch (shaded).",
             fontsize=10.5)
fig.tight_layout(rect=[0, 0, 1, 0.93])
fig.savefig("research/specbench/pstar_frontier.png", dpi=150)
fig.savefig("research/specbench/pstar_frontier.pdf")
print("wrote research/specbench/pstar_frontier.png and .pdf")
