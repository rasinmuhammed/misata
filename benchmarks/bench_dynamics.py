"""How the dynamics passes scale.

`retention`, `missingness`, `late_arrivals`, `time_grids` and `duplicates` all
run *after* generation and rewrite whole tables. That is the right design for
exactness, and it also means nobody had measured what it costs. This measures
it, at sizes people actually use, and prints the per-row cost so a regression
shows up as a number rather than a feeling.

    python -m benchmarks.bench_dynamics            # 100k, 1M
    python -m benchmarks.bench_dynamics --big      # adds 10M

Every figure is measured on the run that prints it. Nothing here is a target.
"""

from __future__ import annotations

import argparse
import time
import warnings

import numpy as np
import pandas as pd

from misata.dynamics import (apply_duplicates, apply_late_arrival,
                             apply_missingness, apply_retention,
                             apply_time_grid)
from misata.schema import (CohortRetention, Duplicates, LateArrival,
                           Missingness, TimeGrid)

warnings.filterwarnings("ignore")

NS_PER_DAY = 86_400_000_000_000


def _events(n: int, entities: int, seed: int = 7) -> dict:
    """An event table and its cohort table, built directly rather than generated.

    The point is to isolate the cost of the pass, not of generation.
    """
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2024-01-01").value
    span = 540 * NS_PER_DAY
    events = pd.DataFrame({
        "event_id": np.arange(n, dtype="int64"),
        "entity_id": rng.integers(0, entities, size=n),
        "event_time": pd.to_datetime(
            (start + rng.integers(0, span, size=n)).astype("datetime64[ns]")),
        "amount": rng.lognormal(4.0, 0.7, size=n).round(2),
        "channel": rng.choice(["web", "ios", "android"], size=n),
        "status": rng.choice(["ok", "failed"], size=n, p=[0.93, 0.07]),
    })
    events["ingested_at"] = pd.NaT
    cohorts = pd.DataFrame({
        "entity_id": np.arange(entities, dtype="int64"),
        "signup_date": pd.to_datetime(
            (start + rng.integers(0, span // 2, size=entities)
             ).astype("datetime64[ns]")),
    })
    return {"events": events, "entities": cohorts}


def _time(fn, *a, **kw) -> float:
    t0 = time.perf_counter()
    fn(*a, **kw)
    return time.perf_counter() - t0


def measure(n: int) -> list:
    entities = max(n // 200, 50)
    rng = np.random.default_rng(1)
    rows = []

    def case(name, spec, fn, tables=None):
        t = tables if tables is not None else _events(n, entities)
        secs = _time(fn, t, spec, np.random.default_rng(1))
        rows.append((name, n, secs, n / secs if secs else float("inf")))

    case("time_grids",
         TimeGrid(table="events", column="event_time",
                  minute_grid=15, hours=(9, 17)),
         apply_time_grid)
    case("missingness",
         Missingness(table="events", column="amount",
                     when_column="status", when_operator="==",
                     when_value="failed", rate=0.8, else_rate=0.02),
         apply_missingness)
    case("late_arrivals",
         LateArrival(table="events", event_time="event_time",
                     ingest_time="ingested_at",
                     late_fraction=0.04, max_delay_days=3),
         apply_late_arrival)
    case("duplicates",
         Duplicates(table="events", fraction=0.02, keys=["event_id"]),
         apply_duplicates)
    case("retention",
         CohortRetention(table="events", cohort_table="entities",
                         cohort_key="entity_id", cohort_time="signup_date",
                         event_time="event_time", unit="month",
                         curve={0: 1.0, 1: 0.6, 2: 0.45, 3: 0.35}),
         apply_retention)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--big", action="store_true",
                    help="also measure 10M rows (needs ~6 GB)")
    args = ap.parse_args()

    sizes = [100_000, 1_000_000] + ([10_000_000] if args.big else [])
    all_rows = []
    for n in sizes:
        all_rows.extend(measure(n))

    print(f"\nDYNAMICS SCALING  --  pandas {pd.__version__}, "
          f"numpy {np.__version__}\n")
    print(f"  {'pass':<16} {'rows':>12} {'seconds':>9} {'rows/sec':>14}")
    print(f"  {'-'*16} {'-'*12} {'-'*9} {'-'*14}")
    for name, n, secs, rate in all_rows:
        print(f"  {name:<16} {n:>12,} {secs:>9.2f} {rate:>14,.0f}")

    # Linear is the claim worth checking: these are hashes, sorts and
    # vectorised arithmetic, so cost should track row count.
    #
    # Measured across the two LARGEST sizes only. Including the smallest makes
    # the number lie: at 100k rows fixed costs dominate, so a pass can look
    # "superlinear" purely because its per-row rate improved on the way up. The
    # first version of this script reported 3.22x for time_grids on exactly
    # that artefact, while its actual throughput was flat.
    by_pass = {}
    for name, n, secs, _ in all_rows:
        by_pass.setdefault(name, []).append((n, secs))
    if len(sizes) < 2:
        return 0

    print(f"\n  cost growth from {sizes[-2]:,} to {sizes[-1]:,} rows "
          f"(1.0 = linear):")
    worst, worst_name = 0.0, ""
    for name, pts in by_pass.items():
        pts.sort()
        (n0, s0), (n1, s1) = pts[-2], pts[-1]
        if s0 <= 0:
            continue
        f = (s1 / s0) / (n1 / n0)
        if f > worst:
            worst, worst_name = f, name
        print(f"    {name:<16} {f:>6.2f}x")
    # Threshold reasoning, so the verdict means something: every pass here is
    # O(n) hashes, sorts and vectorised arithmetic. A genuinely quadratic pass
    # would show ~10x cost growth for 10x rows, not 2x. Growth in the 1.2-2.0x
    # band past a million rows is memory bandwidth, not complexity: the working
    # set stops fitting in cache. So 3.0x is the line that would actually catch
    # a complexity regression, and anything under it is reported as a number
    # without a verdict attached to it.
    verdict = ("no complexity regression" if worst < 3.0
               else "SUPERLINEAR, investigate")
    print(f"\n  worst: {worst_name} at {worst:.2f}x  ({verdict})")

    slowest = min(all_rows, key=lambda r: r[3] if r[1] == sizes[-1] else 1e18)
    print(f"  slowest at {sizes[-1]:,} rows: {slowest[0]} "
          f"({slowest[2]:.1f}s, {slowest[3]:,.0f} rows/sec)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
