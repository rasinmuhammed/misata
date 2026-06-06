"""
Per-bin validity check for the California Housing reference task (review F2): show the
monthly targets are NOT near-uniform (so AME is a real per-bin miss, not a degenerate
target), and quantify one month's miss for a fitted GaussianCopula. Writes
results_california_bins.csv.

Run:  PYTHONPATH=. python3 research/specbench/verify_california_bins.py
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from sklearn.datasets import fetch_california_housing


def main():
    cal = fetch_california_housing(as_frame=True).frame
    real = pd.DataFrame({"value": cal["MedHouseVal"].to_numpy(),
                         "month": (1 + (cal["HouseAge"].astype(int) % 12)).astype(int)})
    targets = {m: float(real.loc[real.month == m, "value"].sum()) for m in range(1, 13)}
    tv = np.array(list(targets.values()))
    target_cv = float(tv.std() / tv.mean())
    max_over_median = float(tv.max() / np.median(tv))
    r = float(np.corrcoef(real["value"], real["month"])[0, 1])

    from sdv.single_table import GaussianCopulaSynthesizer as S
    from sdv.metadata import Metadata
    import random; random.seed(42); np.random.seed(42)
    md = Metadata.detect_from_dataframe(real)
    synth = S(md); synth.fit(real)
    samp = synth.sample(num_rows=len(real))
    gc_m05 = float(samp.loc[samp.month == 5, "value"].sum())

    rows = [{"quantity": "target_cv", "value": round(target_cv, 4)},
            {"quantity": "max_over_median_target", "value": round(max_over_median, 3)},
            {"quantity": "corr_value_monthbin", "value": round(r, 4)},
            {"quantity": "month05_target", "value": round(targets[5], 1)},
            {"quantity": "month05_gaussian_copula_sum_seed42", "value": round(gc_m05, 1)}]
    df = pd.DataFrame(rows)
    out = "research/specbench/results_california_bins.csv"
    df.to_csv(out, index=False)
    print(df.to_string(index=False))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
