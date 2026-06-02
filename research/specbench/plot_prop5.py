"""
Render the Prop-5 condensation-frontier figure from prop5_curve.csv.

Produces a publication-quality figure: marginal distortion (MD) vs target
tail-heaviness (lognormal log-sigma), with the fluid and condensation regimes shaded
and the exactness-preserved annotation. This is the paper's central figure.

Run (after prop5_curve.py): .venv_specbench/bin/python3 -m research.specbench.plot_prop5
Writes research/specbench/prop5_frontier.png (+ .pdf for the paper).
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

CSV = "research/specbench/prop5_curve.csv"
OUT_PNG = "research/specbench/prop5_frontier.png"
OUT_PDF = "research/specbench/prop5_frontier.pdf"


def main() -> None:
    if not os.path.exists(CSV):
        raise SystemExit(f"missing {CSV}; run prop5_curve.py first")
    df = pd.read_csv(CSV)

    fig, ax = plt.subplots(figsize=(7, 4.4))

    # regime shading (fluid vs condensation), boundary near the empirical knee sigma~1.4
    knee = 1.4
    ax.axvspan(df.sigma.min(), knee, alpha=0.07, color="tab:blue")
    ax.axvspan(knee, df.sigma.max(), alpha=0.07, color="tab:red")

    ax.plot(df.sigma, df.MD, "o-", color="black", lw=1.8, ms=5, zorder=3,
            label="measured marginal distortion (MD)")
    ax.axvline(knee, color="gray", ls="--", lw=1, zorder=2)

    ax.text(0.55, ax.get_ylim()[1] * 0.86, "fluid regime\n(constraint ~ free)",
            ha="center", va="top", fontsize=9, color="tab:blue")
    ax.text(1.78, ax.get_ylim()[1] * 0.86, "condensation regime\n(single big jump)",
            ha="center", va="top", fontsize=9, color="tab:red")

    ax.set_xlabel(r"target tail-heaviness  (lognormal  $\sigma$)")
    ax.set_ylabel("marginal distortion  MD  (norm. 1-Wasserstein)")
    ax.set_title("Conformance/fidelity frontier under exact aggregate (Prop. 5)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.9)

    # annotate that the aggregate stayed exact throughout
    max_err = df.sum_err.max()
    ax.text(0.99, 0.02, f"aggregate exact throughout  (max sum-error = {max_err:.0e})",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
            style="italic", color="dimgray")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=200)
    fig.savefig(OUT_PDF)
    light = df[df.sigma <= 0.4].MD.mean()
    heavy = df[df.sigma >= 1.6].MD.mean()
    print(f"wrote {OUT_PNG} and {OUT_PDF}")
    print(f"  fluid MD={light:.3f}  condensation MD={heavy:.3f}  "
          f"ratio={heavy/max(light,1e-9):.1f}x  max sum-error={max_err:.0e}")


if __name__ == "__main__":
    main()
