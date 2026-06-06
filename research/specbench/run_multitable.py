"""
Multi-table reference-mode runs (review M13) for E5: 2-table (customers->orders) and
3-table (regions->stores->sales) hierarchies, each with an outcome target on the child
metric. Compares Misata (declarative) against SDV HMA (relational synthesizer). Writes
results_multitable.csv. HMA is copula-based, so this needs no torch/ctgan.

Run:  PYTHONPATH=. python3 research/specbench/run_multitable.py
"""
from __future__ import annotations

import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from research.specbench.baselines import MisataBaseline, SDVBaseline
from research.specbench.metrics import aggregate_match_error, fk_integrity_violation_rate
from research.specbench.tasks import (
    _multitable_reference_task, _three_table_reference_task,
)


def metrics_for(task, res):
    ame = aggregate_match_error(
        res.tables, task.metric_table, task.metric_col,
        task.time_col, task.period_targets, task.period_freq,
    ).value
    fivr = fk_integrity_violation_rate(res.tables, task.fks).value
    return ame, fivr


def main(seeds=(42, 43, 44)):
    tasks = [("2-table", _multitable_reference_task()),
             ("3-table", _three_table_reference_task())]
    baselines = [MisataBaseline(), SDVBaseline(synthesizer="hma")]
    rows = []
    for label, task in tasks:
        for bl in baselines:
            ames, fivrs, secs = [], [], []
            for sd in seeds:
                res = bl.generate(task, seed=sd)
                if not res.ran:
                    rows.append({"task": label, "baseline": bl.name, "ran": False,
                                 "reason": res.reason})
                    break
                a, f = metrics_for(task, res)
                ames.append(a); fivrs.append(f); secs.append(res.wall_seconds)
            else:
                rows.append({
                    "task": label, "baseline": bl.name, "ran": True,
                    "input": bl.capabilities.input_type,
                    "AME_mean": float(np.mean(ames)), "AME_std": float(np.std(ames)),
                    "FIVR_mean": float(np.mean(fivrs)), "secs_mean": float(np.mean(secs)),
                    "seeds": len(seeds),
                })
    df = pd.DataFrame(rows)
    out = "research/specbench/results_multitable.csv"
    df.to_csv(out, index=False)
    print(df.to_string(index=False))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
