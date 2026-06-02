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


def run_task(task: Task, baselines: List[Baseline], seed: int = 42,
             det_check: bool = True) -> List[Dict]:
    """Run each baseline once on `task` at `seed`, compute metrics.

    det_check: when True, run a second generation at the same seed to measure
    determinism (DET). This doubles cost; the multi-seed driver computes DET on the
    first seed only and passes det_check=False thereafter (DET is a property, not a
    per-seed quantity), keeping expensive baselines (CTGAN) affordable over many seeds.
    """
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

        # --- Family B: DET (same seed twice) — only when requested ---
        if det_check:
            res2 = bl.generate(task, seed=seed)
            det = determinism(res.tables, res2.tables) if res2.ran else None
            rec["DET"] = det.value if det else float("nan")
        else:
            rec["DET"] = float("nan")

        rows.append(rec)
    return rows


def _agg(vals: List[float]) -> str:
    """mean±std over seeds, formatted; NaN-safe."""
    arr = np.array([v for v in vals if v == v], dtype=float)
    if arr.size == 0:
        return "  n/a"
    m, s = arr.mean(), arr.std()
    if np.allclose(arr, arr[0]):            # deterministic across seeds
        return _fmt(float(arr[0]))
    return f"{_fmt(float(m))}±{s:.3f}"


def main(seeds: int = 10) -> None:
    tasks = seed_suite()
    baselines = all_baselines()

    print("\n" + "=" * 90)
    print(f"  SpecBench E5 — cross-paradigm conformance leaderboard ({seeds} seeds, mean±std)")
    print("  axis: CONFORMANCE (lower AME/FIVR better; CSAT/DET=1 better; CSC=1 capable)")
    print("=" * 90)

    all_rows: List[Dict] = []
    for task in tasks:
        print(f"\n### Task: {task.task_id}  (mode={task.mode}, "
              f"targets={'curve' if task.period_targets else 'integrity-only'}, "
              f"constraints={len(task.constraints)})")
        print(f"  {'baseline':<20} {'CSC':>3} {'AME':>11} {'CSAT':>8} {'FIVR':>8} {'DET':>6}  {'secs':>7}")
        print("  " + "-" * 84)

        # collect per-seed records, keyed by baseline
        by_bl: Dict[str, List[Dict]] = {}
        for sd in range(seeds):
            # DET is a property; measure it once (first seed) to avoid doubling the
            # cost of expensive baselines (CTGAN) across all seeds.
            for rec in run_task(task, baselines, seed=42 + sd, det_check=(sd == 0)):
                by_bl.setdefault(rec["baseline"], []).append(rec)
                rec["seed"] = 42 + sd
                all_rows.append(rec)

        for bl in baselines:
            recs = by_bl.get(bl.name, [])
            ran = [r for r in recs if r.get("ran")]
            if not ran:
                reason = recs[0].get("reason", "") if recs else ""
                print(f"  {bl.name:<20} {int(bl.capabilities.cold_start):>3} "
                      f"{'n/a':>11} {'n/a':>8} {'n/a':>8} {'n/a':>6}  {'-':>7}  {reason}")
                continue
            print(f"  {bl.name:<20} {ran[0]['CSC']:>3} "
                  f"{_agg([r['AME'] for r in ran]):>11} "
                  f"{_agg([r['CSAT'] for r in ran]):>8} "
                  f"{_agg([r['FIVR'] for r in ran]):>8} "
                  f"{_agg([r['DET'] for r in ran]):>6}  "
                  f"{np.mean([r['secs'] for r in ran]):>7.2f}")

    out = pd.DataFrame(all_rows)
    csv_path = "research/specbench/results_e5.csv"
    out.to_csv(csv_path, index=False)
    print("\n" + "-" * 90)
    print(f"  wrote {csv_path}  ({len(out)} rows = tasks x baselines x seeds)")
    print("-" * 90 + "\n")


if __name__ == "__main__":
    main()
