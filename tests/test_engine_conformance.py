"""Standing engine-conformance suite — validates the deterministic generation
engine's OUTPUT statistically (not just that it runs). No LLM involved.

Born from an intensive 0.8.1.10 sweep that surfaced silently-wrong data:
dropped distribution params, unimplemented distributions, and a cross-table
formula that mis-joined when the parent PK name differed from the child FK.
These tests assert on measured values so that class of bug cannot regress.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata import from_dict_schema


def gen(schema, seed=42):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return misata.generate_from_schema(from_dict_schema(schema, seed=seed))


# ── Distribution fidelity ────────────────────────────────────────────────

def test_distribution_params_honored():
    d = gen({"t": {"__rows__": 20000,
        "norm": {"type": "float", "distribution": "normal", "mean": 100, "std": 15},
        "uni":  {"type": "float", "distribution": "uniform", "min": 10, "max": 20},
        "pois": {"type": "integer", "distribution": "poisson", "lambda": 4, "min": 0},
        "binom":{"type": "integer", "distribution": "binomial", "n": 10, "p": 0.3},
    }})["t"]
    assert abs(d["norm"].mean() - 100) < 1.5
    assert abs(d["norm"].std() - 15) < 1.0
    assert d["uni"].min() >= 10 and d["uni"].max() <= 20
    assert abs(d["pois"].mean() - 4) < 0.3          # lambda honored (was dropped)
    assert d["binom"].max() <= 10 and abs(d["binom"].mean() - 3) < 0.3  # binomial (was uniform)


def test_zipf_is_heavy_tailed():
    d = gen({"t": {"__rows__": 20000,
        "views": {"type": "integer", "distribution": "zipf", "a": 2.0, "min": 1}}})["t"]
    median, mx = float(np.median(d["views"])), int(d["views"].max())
    assert median <= 5 and mx > median * 20, f"not heavy-tailed: median={median} max={mx}"


def test_null_rate_honored():
    d = gen({"t": {"__rows__": 10000,
        "v": {"type": "float", "distribution": "normal", "mean": 5, "std": 1, "null_rate": 0.15}}})["t"]
    assert abs(d["v"].isna().mean() - 0.15) < 0.03


def test_categorical_probabilities_conform():
    d = gen({"t": {"__rows__": 20000,
        "s": {"type": "string", "enum": ["a", "b", "c"], "probabilities": [0.7, 0.2, 0.1]}}})["t"]
    vc = d["s"].value_counts(normalize=True)
    assert abs(vc["a"] - 0.7) < 0.02 and abs(vc["b"] - 0.2) < 0.02 and abs(vc["c"] - 0.1) < 0.02


# ── Curves & rates ───────────────────────────────────────────────────────

def test_absolute_outcome_curve_hits_targets():
    s = {"sales": {"__rows__": 6000, "id": {"type": "integer", "primary_key": True},
            "dt": {"type": "date", "start": "2024-01-01", "end": "2024-12-31"},
            "amount": {"type": "float", "min": 10, "max": 100}},
        "__outcome_curves__": [{"table": "sales", "column": "amount", "time_column": "dt",
            "time_unit": "month", "value_mode": "absolute",
            "curve_points": [{"month": 1, "target_value": 50000}, {"month": 12, "target_value": 200000}]}]}
    d = gen(s)["sales"]; d["m"] = pd.to_datetime(d["dt"]).dt.month
    assert abs(d[d.m == 1]["amount"].sum() - 50000) / 50000 < 0.05
    assert abs(d[d.m == 12]["amount"].sum() - 200000) / 200000 < 0.05


def test_rate_curve_conforms_per_period():
    s = {"subs": {"__rows__": 12000, "id": {"type": "integer", "primary_key": True},
            "churn_date": {"type": "date", "start": "2024-01-01", "end": "2024-12-31"},
            "churned": {"type": "boolean", "probability": 0.5}},
        "__rate_curves__": [{"table": "subs", "column": "churned", "time_column": "churn_date",
            "time_unit": "month", "true_value": True, "interpolate": True,
            "rate_points": [{"period": 1, "rate": 0.02}, {"period": 12, "rate": 0.20}]}]}
    d = gen(s)["subs"]; d["m"] = pd.to_datetime(d["churn_date"]).dt.month
    assert abs(d[d.m == 1]["churned"].mean() - 0.02) < 0.015
    assert abs(d[d.m == 12]["churned"].mean() - 0.20) < 0.02


@pytest.mark.parametrize("target_r", [0.7, -0.6])
def test_correlation_enforced(target_r):
    d = gen({"t": {"__rows__": 5000,
        "a": {"type": "float", "distribution": "normal", "mean": 50, "std": 10},
        "b": {"type": "float", "distribution": "normal", "mean": 100, "std": 20},
        "__correlations__": [{"col_a": "a", "col_b": "b", "r": target_r}]}})["t"]
    r = float(np.corrcoef(d["a"].astype(float), d["b"].astype(float))[0, 1])
    assert abs(r - target_r) < 0.15, f"measured r={r:.3f}"


# ── Cross-table logic ────────────────────────────────────────────────────

@pytest.mark.parametrize("parent_pk", ["id", "employee_id"])
def test_cross_table_formula_joins_on_real_fk(parent_pk):
    """The formula must join on the declared FK even when the parent PK name
    ('id') differs from the child FK name ('employee_id')."""
    s = {"employees": {"__rows__": 20, parent_pk: {"type": "integer", "primary_key": True},
            "hourly_rate": {"type": "float", "distribution": "uniform", "min": 20, "max": 50}},
        "timesheets": {"__rows__": 2000, "id": {"type": "integer", "primary_key": True},
            "employee_id": {"type": "integer", "foreign_key": {"table": "employees", "column": parent_pk}},
            "hours": {"type": "float", "distribution": "uniform", "min": 1, "max": 8},
            "billed": {"type": "float", "formula": "hours * @employees.hourly_rate"}}}
    t = gen(s)
    m = t["timesheets"].merge(t["employees"], left_on="employee_id", right_on=parent_pk)
    err = (m["billed"] - m["hours"] * m["hourly_rate"]).abs().max()
    assert err < 0.01, f"formula mis-joined (max_err={err:.2f}) with parent PK '{parent_pk}'"


def test_cross_fk_depends_on_maps_on_parent_value():
    s = {"plans": {"__rows__": 2, "id": {"type": "integer", "primary_key": True},
            "tier": {"type": "string", "enum": ["Free", "Enterprise"], "probabilities": [0.5, 0.5]}},
        "subs": {"__rows__": 3000, "id": {"type": "integer", "primary_key": True},
            "plan_id": {"type": "integer", "foreign_key": {"table": "plans", "column": "id"}},
            "mrr": {"type": "float", "depends_on": "plan_id.tier",
                "mapping": {"Free": {"mean": 0, "std": 1}, "Enterprise": {"mean": 1000, "std": 5}}}}}
    t = gen(s)
    sub = t["subs"].merge(t["plans"][["id", "tier"]], left_on="plan_id", right_on="id", suffixes=("", "_p"))
    assert abs(sub[sub.tier == "Free"]["mrr"].mean()) < 5
    assert abs(sub[sub.tier == "Enterprise"]["mrr"].mean() - 1000) < 30


def test_profiles_stratify_by_subgroup():
    d = gen({"patients": {"__rows__": 6000,
        "arm": {"type": "string", "enum": ["placebo", "low", "high"], "probabilities": [0.34, 0.33, 0.33]},
        "effect": {"type": "float", "distribution": "normal", "mean": 0, "std": 0.5, "profiles": [
            {"when": "arm == 'placebo'", "distribution": "normal", "mean": -0.3, "std": 0.4},
            {"when": "arm == 'low'", "distribution": "normal", "mean": -1.0, "std": 0.4},
            {"when": "arm == 'high'", "distribution": "normal", "mean": -1.5, "std": 0.4}]}}})["patients"]
    by = d.groupby("arm")["effect"].mean()
    assert by["placebo"] > by["low"] > by["high"]


# ── Integrity & scale ────────────────────────────────────────────────────

def test_fk_integrity_three_level():
    t = gen({
        "regions": {"__rows__": 5, "id": {"type": "integer", "primary_key": True}},
        "stores":  {"__rows__": 30, "id": {"type": "integer", "primary_key": True},
                    "region_id": {"type": "integer", "foreign_key": {"table": "regions", "column": "id"}}},
        "orders":  {"__rows__": 5000, "id": {"type": "integer", "primary_key": True},
                    "store_id": {"type": "integer", "foreign_key": {"table": "stores", "column": "id"}}}})
    assert set(t["orders"]["store_id"]).issubset(set(t["stores"]["id"]))
    assert set(t["stores"]["region_id"]).issubset(set(t["regions"]["id"]))


def test_determinism_same_seed():
    a = gen({"t": {"__rows__": 1000, "x": {"type": "float", "distribution": "normal", "mean": 0, "std": 1}}}, seed=123)["t"]
    b = gen({"t": {"__rows__": 1000, "x": {"type": "float", "distribution": "normal", "mean": 0, "std": 1}}}, seed=123)["t"]
    assert a["x"].equals(b["x"])
