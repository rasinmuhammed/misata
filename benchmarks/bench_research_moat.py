"""Research-moat benchmark harness for Misata vs common alternatives.

This is intentionally small and offline-friendly. It compares what Misata can
prove out of the box against a hand-written Faker baseline:

- setup effort proxy
- referential integrity
- scenario/control support
- reproducibility
- Oracle report quality signals
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd
from faker import Faker

import misata


@dataclass
class BenchmarkResult:
    tool: str
    rows: int
    elapsed_seconds: float
    rows_per_second: float
    fk_orphans: int
    reproducible: bool
    scenario_control: bool
    oracle_available: bool
    setup_steps: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "rows": self.rows,
            "elapsed_seconds": round(self.elapsed_seconds, 4),
            "rows_per_second": round(self.rows_per_second, 1),
            "fk_orphans": self.fk_orphans,
            "reproducible": self.reproducible,
            "scenario_control": self.scenario_control,
            "oracle_available": self.oracle_available,
            "setup_steps": self.setup_steps,
        }


def _misata_run(rows: int = 500, seed: int = 42) -> tuple[Dict[str, pd.DataFrame], Dict[str, Any], float]:
    story = "A SaaS company with monthly subscriptions and 20% churn"
    t0 = time.perf_counter()
    schema = misata.parse(story, rows=rows)
    schema.seed = seed
    tables = misata.generate_from_schema(schema)
    oracle = misata.build_oracle_report(tables, schema, seed=seed)
    elapsed = time.perf_counter() - t0
    return tables, oracle, elapsed


def benchmark_misata(rows: int = 500, seed: int = 42) -> BenchmarkResult:
    tables, oracle, elapsed = _misata_run(rows=rows, seed=seed)
    tables_again, _, _ = _misata_run(rows=rows, seed=seed)

    fk_orphans = 0
    if {"users", "subscriptions"}.issubset(tables):
        parent_ids = set(tables["users"]["user_id"])
        fk_orphans = int((~tables["subscriptions"]["user_id"].isin(parent_ids)).sum())

    reproducible = all(tables[name].equals(tables_again[name]) for name in tables)
    total_rows = sum(len(df) for df in tables.values())
    return BenchmarkResult(
        tool="misata",
        rows=total_rows,
        elapsed_seconds=elapsed,
        rows_per_second=total_rows / elapsed if elapsed > 0 else float("inf"),
        fk_orphans=fk_orphans,
        reproducible=reproducible,
        scenario_control=True,
        oracle_available=bool(oracle.get("misata_report") == "oracle"),
        setup_steps=1,
    )


def _faker_tables(rows: int = 500, seed: int = 42) -> Dict[str, pd.DataFrame]:
    fake = Faker("en_US")
    Faker.seed(seed)
    users = pd.DataFrame(
        {
            "user_id": list(range(1, rows + 1)),
            "email": [fake.email() for _ in range(rows)],
            "name": [fake.name() for _ in range(rows)],
            "churned": [i % 5 == 0 for i in range(rows)],
        }
    )
    subscriptions = pd.DataFrame(
        {
            "subscription_id": list(range(1, rows + 1)),
            "user_id": [(i % rows) + 1 for i in range(rows)],
            "plan": [fake.random_element(["starter", "pro", "enterprise"]) for _ in range(rows)],
            "mrr": [fake.pyfloat(min_value=10, max_value=500, right_digits=2) for _ in range(rows)],
        }
    )
    return {"users": users, "subscriptions": subscriptions}


def benchmark_faker(rows: int = 500, seed: int = 42) -> BenchmarkResult:
    t0 = time.perf_counter()
    tables = _faker_tables(rows=rows, seed=seed)
    elapsed = time.perf_counter() - t0
    tables_again = _faker_tables(rows=rows, seed=seed)

    parent_ids = set(tables["users"]["user_id"])
    fk_orphans = int((~tables["subscriptions"]["user_id"].isin(parent_ids)).sum())
    reproducible = all(tables[name].equals(tables_again[name]) for name in tables)
    total_rows = sum(len(df) for df in tables.values())
    return BenchmarkResult(
        tool="faker_manual",
        rows=total_rows,
        elapsed_seconds=elapsed,
        rows_per_second=total_rows / elapsed if elapsed > 0 else float("inf"),
        fk_orphans=fk_orphans,
        reproducible=reproducible,
        scenario_control=False,
        oracle_available=False,
        setup_steps=6,
    )


def run_comparison(rows: int = 500, seed: int = 42) -> List[Dict[str, Any]]:
    """Return a compact, serializable benchmark comparison."""
    return [
        benchmark_misata(rows=rows, seed=seed).as_dict(),
        benchmark_faker(rows=rows, seed=seed).as_dict(),
    ]


def main() -> None:
    results = run_comparison()
    print("tool,rows,elapsed_seconds,rows_per_second,fk_orphans,reproducible,scenario_control,oracle_available,setup_steps")
    for result in results:
        print(",".join(str(result[key]) for key in result))


if __name__ == "__main__":
    main()
