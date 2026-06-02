"""
SpecBench runner — produces the E5 cross-paradigm leaderboard.

For each (task, baseline): run the generator, then compute the conformance and
integrity metrics. Baselines that cannot run a task (e.g. SDV on a cold-start task)
are recorded as "n/a (reason)" — never a fabricated score. Determinism is checked by
running each baseline twice with the same seed.

Run:
    .venv_specbench/bin/python3 -m research.specbench.runner
(use the env that has SDV; falls back gracefully if SDV absent, recording n/a)
"""

from __future__ import annotations

import warnings
from typing import Dict, List

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from research.specbench.baselines import Baseline, all_baselines  # noqa: E402
from research.specbench.metrics import (  # noqa: E402
    aggregate_match_error,
    constraint_satisfaction,
    determinism,
    fk_integrity_violation_rate,
)
from research.specbench.tasks import Task, seed_suite  # noqa: E402


def _fmt(x: float) -> str:
    if x != x:                       # NaN
        return "  n/a"
    if x == 0:
        return "0.000"
    if x >= 100:
        return f"{x:7.1f}"
    return f"{x:.3f}"


def run_task(task: Task, baselines: List[Baseline], seed: int = 42) -> List[Dict]:
    rows: List[Dict] = []
    for bl in baselines:
        rec: Dict = {"task": task.task_id, "baseline": bl.name,
                     "CSC": int(bl.capabilities.cold_start)}
        if not bl.available():
            rec.update(ran=False, reason="package unavailable")
            rows.append(rec); continue

        res = bl.generate(task, seed=seed)
        if not res.ran:
            rec.update(ran=False, reason=res.reason)
            rows.append(rec); continue

        rec["ran"] = True
        rec["secs"] = round(res.wall_seconds, 3)

        # --- Family A: AME (only if the task declares period targets) ---
        if task.period_targets:
            ame = aggregate_match_error(
                res.tables, task.metric_table, task.metric_col,
                task.time_col, task.period_targets, task.period_freq,
            )
            rec["AME"] = ame.value
        else:
            rec["AME"] = float("nan")

        # --- Family B: FIVR ---
        fivr = fk_integrity_violation_rate(res.tables, task.fks)
        rec["FIVR"] = fivr.value

        # --- Family A: CSAT (hard-constraint satisfaction) ---
        if task.constraints:
            csat = constraint_satisfaction(res.tables, task.constraints)
            rec["CSAT"] = csat.value
        else:
            rec["CSAT"] = float("nan")

        # --- Family B: DET (same seed twice) ---
        res2 = bl.generate(task, seed=seed)
        det = determinism(res.tables, res2.tables) if res2.ran else None
        rec["DET"] = det.value if det else float("nan")

        rows.append(rec)
    return rows


def main() -> None:
    tasks = seed_suite()
    baselines = all_baselines()

    print("\n" + "=" * 78)
    print("  SpecBench E5 — cross-paradigm conformance leaderboard")
    print("  axis: CONFORMANCE (lower AME/FIVR better; DET=1 better; CSC=1 capable)")
    print("=" * 78)

    all_rows: List[Dict] = []
    for task in tasks:
        print(f"\n### Task: {task.task_id}  (mode={task.mode}, "
              f"targets={'curve' if task.period_targets else 'integrity-only'})")
        print(f"  {'baseline':<22} {'CSC':>3} {'AME':>8} {'CSAT':>6} {'FIVR':>7} {'DET':>5}  {'secs':>7}  note")
        print("  " + "-" * 82)
        for rec in run_task(task, baselines):
            if not rec.get("ran", False):
                print(f"  {rec['baseline']:<22} {rec['CSC']:>3} {'n/a':>8} {'n/a':>6} {'n/a':>7} "
                      f"{'n/a':>5}  {'-':>7}  {rec.get('reason','')}")
            else:
                print(f"  {rec['baseline']:<22} {rec['CSC']:>3} "
                      f"{_fmt(rec['AME']):>8} {_fmt(rec['CSAT']):>6} {_fmt(rec['FIVR']):>7} "
                      f"{_fmt(rec['DET']):>5}  {rec['secs']:>7}  ")
            all_rows.append(rec)

    # machine-readable leaderboard
    out = pd.DataFrame(all_rows)
    csv_path = "research/specbench/results_e5.csv"
    out.to_csv(csv_path, index=False)
    print("\n" + "-" * 78)
    print(f"  wrote {csv_path}")
    print("-" * 78 + "\n")


if __name__ == "__main__":
    main()
