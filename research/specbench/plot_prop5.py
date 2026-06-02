"""
Render the corrected Prop-4 figure: scale-invariance / no-condensation result.

Shows, across tail-heaviness (Gamma CV), the marginal distortion of the engine's
exact-sum sample vs an unconstrained i.i.d. draw from the SAME family, with error bars
over seeds. The two curves coincide -> the exact-aggregate constraint costs ~nothing in
shape; the gap is ~0 (the condensation cost vanishes because the engine is scale-free,
Prop. 4). This replaces the earlier, confounded "frontier" figure (review fix B1).

Run: .venv_specbench/bin/python3 -m research.specbench.plot_prop5
Writes research/specbench/prop4_scale_invariance.png (+ .pdf).
"""

from __future__ import annotations

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

SUMM = "research/specbench/prop5_summary.csv"
OUT_PNG = "research/specbench/prop4_scale_invariance.png"
OUT_PDF = "research/specbench/prop4_scale_invariance.pdf"


def main() -> None:
    if not os.path.exists(SUMM):
        raise SystemExit(f"missing {SUMM}; run prop5_curve.py first")
    df = pd.read_csv(SUMM).sort_values("cv")

    fig, ax = plt.subplots(figsize=(7, 4.4))
    ax.errorbar(df.cv, df.MD_constrained, yerr=df.MD_constrained_sd,
                fmt="o-", color="tab:blue", lw=1.8, ms=5, capsize=3, zorder=3,
                label="exact-aggregate sample (engine)")
    ax.errorbar(df.cv, df.MD_unconstrained, yerr=df.MD_unconstrained_sd,
                fmt="s--", color="tab:gray", lw=1.5, ms=4, capsize=3, zorder=2,
                label="unconstrained i.i.d. (control, sum free)")

    ax.set_xlabel(r"target tail-heaviness  (Gamma coefficient of variation, $1/\sqrt{k}$)")
    ax.set_ylabel("marginal distortion  MD  (norm. 1-Wasserstein)")
    ax.set_title("Exact aggregate costs ~no shape distortion (Prop. 4; control included)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.9)
    ax.text(0.99, 0.02,
            "two curves coincide -> condensation avoided by construction\n"
            "(engine fixes shape, lets scale absorb the constraint)",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
            style="italic", color="dimgray")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=200)
    fig.savefig(OUT_PDF)
    gap_light = df[df.cv <= 0.45].gap.mean()
    gap_heavy = df[df.cv >= 2.0].gap.mean()
    print(f"wrote {OUT_PNG} and {OUT_PDF}")
    print(f"  mean gap light={gap_light:+.4f}  heavy={gap_heavy:+.4f}  (≈0 ⇒ no shape cost)")


if __name__ == "__main__":
    main()
