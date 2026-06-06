"""
Re-run the SDV-dependent, copula-based numbers (GaussianCopula, HMA, and the per-period
conditioned steelman) and compare to the committed CSVs, to confirm they reproduce in a
pinned environment. CTGAN is excluded: it requires torch, which is not installed here.

Run:  PYTHONPATH=. python3 research/specbench/verify_sdv.py
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import numpy as np

from research.specbench.tasks import _real_dataset_reference_task, _multitable_reference_task, _three_table_reference_task
from research.specbench.baselines import SDVBaseline, SDVConditionalBaseline
from research.specbench.metrics import aggregate_match_error


def ame(task, res):
    return aggregate_match_error(res.tables, task.metric_table, task.metric_col,
                                 task.time_col, task.period_targets, task.period_freq).value


def run_one(task, baseline, seeds):
    vals = []
    for sd in seeds:
        r = baseline.generate(task, seed=sd)
        if r.ran:
            vals.append(ame(task, r))
    return vals


def report(label, vals, committed):
    if not vals:
        print(f"  {label:42} (did not run)"); return
    m, s = float(np.mean(vals)), float(np.std(vals))
    delta = m - committed
    flag = "MATCH" if abs(delta) < 5e-4 else f"DELTA {delta:+.4f}"
    print(f"  {label:42} rerun={m:.4f}±{s:.4f}  committed={committed:.4f}  -> {flag}")


print("=== California Housing reference (3 seeds) ===")
cal = _real_dataset_reference_task()
report("SDV GaussianCopula", run_one(cal, SDVBaseline("gaussian_copula"), (42, 43, 44)), 0.7389)
report("SDV HMA", run_one(cal, SDVBaseline("hma"), (42, 43, 44)), 0.7389)
report("SDV GaussianCopula per-period (steelman)", run_one(cal, SDVConditionalBaseline(), (42, 43, 44)), 0.189)

print("\n=== Multi-table reference (3 seeds) ===")
t2 = _multitable_reference_task()
report("SDV HMA, 2-table", run_one(t2, SDVBaseline("hma"), (42, 43, 44)), 0.776)
t3 = _three_table_reference_task()
report("SDV HMA, 3-table", run_one(t3, SDVBaseline("hma"), (42, 43, 44)), 0.698)
