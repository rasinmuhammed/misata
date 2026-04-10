"""
Benchmark suite for Misata data generation.

Run with pytest-benchmark:
    pytest benchmarks/ --benchmark-only -v

Or as a standalone script for a quick text report:
    python benchmarks/bench_generation.py

Reports rows/second for:
  - Each supported distribution type (uniform, normal, lognormal, exponential, beta, power_law, zipf)
  - Scaling behaviour across table sizes (1k, 10k, 100k, 1M rows)
  - Multi-table relational generation (star schema with 5 tables)
"""

from __future__ import annotations

import time
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from misata.schema import Column, Relationship, SchemaConfig, Table
from misata.simulator import DataSimulator


# ---------------------------------------------------------------------------
# Schema builders
# ---------------------------------------------------------------------------

def _single_table_schema(n_rows: int, distribution: str, extra_params: dict | None = None) -> SchemaConfig:
    """Minimal single-table schema targeting a specific distribution."""
    params: dict = {"min": 0.01, "decimals": 2}
    params.update(extra_params or {})

    if distribution in ("normal", "lognormal", "exponential", "beta", "power_law"):
        params["distribution"] = distribution

    col_type = "float" if distribution not in ("categorical", "zipf") else "categorical"
    if distribution == "zipf":
        col_type = "categorical"
        params = {
            "choices": [f"cat_{i}" for i in range(20)],
            "sampling": "zipf",
        }
    elif distribution == "categorical":
        col_type = "categorical"
        probs = [1 / 10] * 10
        params = {"choices": [f"val_{i}" for i in range(10)], "probabilities": probs}

    dist_params: dict = {}
    if distribution == "normal":
        dist_params = {"distribution": "normal", "mean": 50.0, "std": 15.0, "min": 0.0, "decimals": 2}
    elif distribution == "lognormal":
        dist_params = {"distribution": "lognormal", "mu": 4.0, "sigma": 0.8, "min": 0.01, "decimals": 2}
    elif distribution == "exponential":
        dist_params = {"distribution": "exponential", "scale": 50.0, "min": 0.01, "decimals": 2}
    elif distribution == "beta":
        dist_params = {"distribution": "beta", "a": 2.0, "b": 5.0, "min": 0.0, "max": 1.0, "decimals": 4}
    elif distribution == "power_law":
        dist_params = {"distribution": "power_law", "exponent": 2.5, "min": 1.0, "max": 1000.0, "decimals": 2}
    elif distribution == "uniform":
        dist_params = {"min": 0.0, "max": 1000.0, "decimals": 2}
    elif distribution in ("categorical", "zipf"):
        dist_params = params

    return SchemaConfig(
        name=f"bench_{distribution}",
        tables=[Table(name="t", row_count=n_rows)],
        columns={
            "t": [
                Column(name="id", type="int", unique=True, distribution_params={"min": 1, "max": n_rows + 1}),
                Column(name="value", type=col_type, distribution_params=dist_params),
            ]
        },
        seed=42,
    )


def _star_schema(n_fact_rows: int, n_dims: int = 4, n_dim_rows: int = 50) -> SchemaConfig:
    """Star schema: one fact table referencing N dimension tables."""
    tables: List[Table] = []
    columns: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    for i in range(n_dims):
        dim_name = f"dim_{i}"
        tables.append(Table(name=dim_name, row_count=n_dim_rows))
        columns[dim_name] = [
            Column(name=f"{dim_name}_id", type="int", unique=True, distribution_params={"min": 1, "max": n_dim_rows + 1}),
            Column(name="label", type="categorical", distribution_params={
                "choices": [f"label_{j}" for j in range(5)],
                "probabilities": [0.4, 0.25, 0.15, 0.12, 0.08],
            }),
        ]

    tables.append(Table(name="fact", row_count=n_fact_rows))
    fact_cols: List[Column] = [
        Column(name="fact_id", type="int", unique=True, distribution_params={"min": 1, "max": n_fact_rows + 1}),
        Column(name="amount", type="float", distribution_params={"distribution": "lognormal", "mu": 4.0, "sigma": 0.8, "min": 0.01, "decimals": 2}),
        Column(name="created_at", type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
    ]
    for i in range(n_dims):
        dim_name = f"dim_{i}"
        fk_col = f"{dim_name}_id"
        fact_cols.append(Column(name=fk_col, type="foreign_key", distribution_params={}))
        relationships.append(Relationship(
            parent_table=dim_name, child_table="fact",
            parent_key=f"{dim_name}_id", child_key=fk_col,
        ))
    columns["fact"] = fact_cols

    return SchemaConfig(
        name="bench_star",
        tables=tables,
        columns=columns,
        relationships=relationships,
        seed=42,
    )


# ---------------------------------------------------------------------------
# Core timing helper
# ---------------------------------------------------------------------------

def _generate_and_count(schema: SchemaConfig) -> Tuple[int, float]:
    """Run generation, return (total_rows_generated, elapsed_seconds)."""
    sim = DataSimulator(schema)
    total_rows = 0
    t0 = time.perf_counter()
    for _, batch in sim.generate_all():
        total_rows += len(batch)
    elapsed = time.perf_counter() - t0
    return total_rows, elapsed


# ---------------------------------------------------------------------------
# pytest-benchmark tests (auto-discovered when `pytest benchmarks/` is run)
# ---------------------------------------------------------------------------

def test_bench_uniform_10k(benchmark):
    schema = _single_table_schema(10_000, "uniform")
    result = benchmark(_generate_and_count, schema)
    rows, _ = result
    assert rows == 10_000


def test_bench_normal_10k(benchmark):
    schema = _single_table_schema(10_000, "normal")
    result = benchmark(_generate_and_count, schema)
    rows, _ = result
    assert rows == 10_000


def test_bench_lognormal_10k(benchmark):
    schema = _single_table_schema(10_000, "lognormal")
    result = benchmark(_generate_and_count, schema)
    rows, _ = result
    assert rows == 10_000


def test_bench_exponential_10k(benchmark):
    schema = _single_table_schema(10_000, "exponential")
    result = benchmark(_generate_and_count, schema)
    rows, _ = result
    assert rows == 10_000


def test_bench_beta_10k(benchmark):
    schema = _single_table_schema(10_000, "beta")
    result = benchmark(_generate_and_count, schema)
    rows, _ = result
    assert rows == 10_000


def test_bench_power_law_10k(benchmark):
    schema = _single_table_schema(10_000, "power_law")
    result = benchmark(_generate_and_count, schema)
    rows, _ = result
    assert rows == 10_000


def test_bench_zipf_categorical_10k(benchmark):
    schema = _single_table_schema(10_000, "zipf")
    result = benchmark(_generate_and_count, schema)
    rows, _ = result
    assert rows == 10_000


def test_bench_scale_100k(benchmark):
    schema = _single_table_schema(100_000, "lognormal")
    result = benchmark(_generate_and_count, schema)
    rows, _ = result
    assert rows == 100_000


def test_bench_star_schema_50k_fact(benchmark):
    schema = _star_schema(n_fact_rows=50_000, n_dims=4, n_dim_rows=50)
    result = benchmark(_generate_and_count, schema)
    rows, _ = result
    assert rows > 50_000  # includes dimension rows


# ---------------------------------------------------------------------------
# Standalone runner — no pytest needed
# ---------------------------------------------------------------------------

STANDALONE_CASES: List[Tuple[str, int, str]] = [
    ("uniform",    10_000,  "single table"),
    ("normal",     10_000,  "single table"),
    ("lognormal",  10_000,  "single table"),
    ("exponential",10_000,  "single table"),
    ("beta",       10_000,  "single table"),
    ("power_law",  10_000,  "single table"),
    ("zipf",       10_000,  "single table"),
    ("lognormal",  100_000, "single table"),
    ("lognormal",  1_000_000, "single table"),
]


def _run_standalone():
    print(f"\n{'=' * 68}")
    print(f"{'Misata Generation Benchmark':^68}")
    print(f"{'=' * 68}")
    print(f"{'Case':<40} {'Rows':>10} {'Time (s)':>10} {'Rows/s':>10}")
    print(f"{'-' * 68}")

    for dist, n_rows, label in STANDALONE_CASES:
        schema = _single_table_schema(n_rows, dist)
        # Warm-up run (excludes import/JIT overhead from timing)
        _generate_and_count(_single_table_schema(100, dist))
        rows, elapsed = _generate_and_count(schema)
        rps = rows / elapsed if elapsed > 0 else float("inf")
        case_label = f"{dist} ({label})"
        print(f"{case_label:<40} {rows:>10,} {elapsed:>10.3f} {rps:>10,.0f}")

    # Star schema
    print(f"\n{'Star schema (4 dims × 50 rows, fact=50k)':<40}", end="")
    schema = _star_schema(50_000, n_dims=4, n_dim_rows=50)
    _generate_and_count(_star_schema(500, n_dims=2, n_dim_rows=5))
    rows, elapsed = _generate_and_count(schema)
    rps = rows / elapsed if elapsed > 0 else float("inf")
    print(f" {rows:>10,} {elapsed:>10.3f} {rps:>10,.0f}")

    print(f"{'=' * 68}\n")


if __name__ == "__main__":
    _run_standalone()
