"""Iman-Conover rank-correlation enforcement tests.

Misata's correlation engine preserves each column's *marginal distribution*
exactly while imposing pairwise rank correlations.  These tests guard the
contract that:
  • A declared ``r=0.7`` produces empirical Pearson correlation close to 0.7
  • Marginals are preserved (every value is a permutation of the original)
  • Negative correlations work
  • Three-column correlation matrices stay positive-definite
  • Non-positive-definite specs are dropped silently (no crash)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import misata
from misata.schema import Column, SchemaConfig, Table


def _build_table(correlations, n_rows: int = 1000, seed: int = 42) -> SchemaConfig:
    """Build a simple two-or-three-column numeric SchemaConfig for testing."""
    return SchemaConfig(
        name="corr_test",
        seed=seed,
        tables=[
            Table(name="data", row_count=n_rows, correlations=correlations),
        ],
        columns={
            "data": [
                Column(name="age", type="int", distribution_params={
                    "distribution": "normal", "mean": 40, "std": 12, "min": 18, "max": 90,
                }),
                Column(name="salary", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 11.0, "sigma": 0.4, "min": 25_000, "decimals": 0,
                }),
                Column(name="years_experience", type="int", distribution_params={
                    "distribution": "normal", "mean": 12, "std": 6, "min": 0, "max": 40,
                }),
            ],
        },
    )


def _pearson(df: pd.DataFrame, a: str, b: str) -> float:
    return float(np.corrcoef(df[a].astype(float), df[b].astype(float))[0, 1])


# ---------------------------------------------------------------------------
# Single positive correlation
# ---------------------------------------------------------------------------


def test_positive_correlation_is_imposed():
    schema = _build_table(
        [{"col_a": "age", "col_b": "salary", "r": 0.7}],
        n_rows=2000,
    )
    tables = misata.generate_from_schema(schema)
    df = tables["data"]
    r = _pearson(df, "age", "salary")
    assert 0.55 <= r <= 0.85, (
        f"Expected r ≈ 0.7 (±0.15) for age vs salary, got {r:.3f}"
    )


def test_negative_correlation_is_imposed():
    schema = _build_table(
        [{"col_a": "age", "col_b": "salary", "r": -0.6}],
        n_rows=2000,
    )
    tables = misata.generate_from_schema(schema)
    df = tables["data"]
    r = _pearson(df, "age", "salary")
    assert -0.75 <= r <= -0.45, (
        f"Expected r ≈ -0.6 (±0.15) for age vs salary, got {r:.3f}"
    )


# ---------------------------------------------------------------------------
# Marginal preservation — Iman-Conover guarantees this exactly
# ---------------------------------------------------------------------------


def test_marginals_are_preserved_exactly():
    """The set of values in each column must be unchanged after correlation."""
    base = _build_table([], n_rows=500)
    schema_corr = _build_table(
        [{"col_a": "age", "col_b": "salary", "r": 0.5}],
        n_rows=500,
    )
    a = misata.generate_from_schema(base)["data"]
    b = misata.generate_from_schema(schema_corr)["data"]

    # The multisets of values in each correlated column must match between
    # the no-correlation and with-correlation runs (same seed, same dist).
    for col in ("age", "salary"):
        assert sorted(a[col].tolist()) == sorted(b[col].tolist()), (
            f"Marginal of '{col}' changed after correlation enforcement — "
            "Iman-Conover should only reorder, never resample"
        )


# ---------------------------------------------------------------------------
# Multi-pair correlation
# ---------------------------------------------------------------------------


def test_three_column_correlation_matrix():
    schema = _build_table(
        [
            {"col_a": "age", "col_b": "salary", "r": 0.6},
            {"col_a": "age", "col_b": "years_experience", "r": 0.7},
            {"col_a": "salary", "col_b": "years_experience", "r": 0.5},
        ],
        n_rows=2000,
    )
    df = misata.generate_from_schema(schema)["data"]

    r_age_sal = _pearson(df, "age", "salary")
    r_age_yrs = _pearson(df, "age", "years_experience")
    r_sal_yrs = _pearson(df, "salary", "years_experience")

    # Each pair within ±0.15 of declared
    assert 0.45 <= r_age_sal <= 0.75
    assert 0.55 <= r_age_yrs <= 0.85
    assert 0.35 <= r_sal_yrs <= 0.65


# ---------------------------------------------------------------------------
# Robustness — non-PD matrices, single-row tables, non-numeric columns
# ---------------------------------------------------------------------------


def test_non_positive_definite_does_not_crash():
    """A correlation spec that produces a non-PD matrix must be dropped silently
    rather than crashing. r=0.99 across three columns can fail Cholesky."""
    schema = _build_table(
        [
            {"col_a": "age", "col_b": "salary", "r": 0.99},
            {"col_a": "age", "col_b": "years_experience", "r": -0.99},
            {"col_a": "salary", "col_b": "years_experience", "r": 0.99},
        ],
        n_rows=200,
    )
    # Should not raise — the simulator catches LinAlgError and returns df unchanged
    df = misata.generate_from_schema(schema)["data"]
    assert len(df) == 200


def test_correlation_with_one_row():
    """rows=1 must not crash the correlation engine (degenerate but valid)."""
    schema = _build_table(
        [{"col_a": "age", "col_b": "salary", "r": 0.5}],
        n_rows=1,
    )
    df = misata.generate_from_schema(schema)["data"]
    assert len(df) == 1
