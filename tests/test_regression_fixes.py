"""Regression tests for the 12 deep-audit fixes applied in v0.8.1.x.

Each test is named after the issue code it guards (C2, C4, H1, ...) so
regressions are immediately traceable back to the original fix.
"""

from __future__ import annotations

import datetime
import os
import tempfile
import threading

import numpy as np
import pandas as pd
import pytest

import misata
from misata import from_dict_schema
from misata.schema import Column, SchemaConfig, Table, Relationship
from misata.simulator import DataSimulator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parent_child_schema(parent_rows: int = 200, child_rows: int = 50) -> SchemaConfig:
    return SchemaConfig(
        name="pc",
        seed=7,
        tables=[
            Table(name="parents", row_count=parent_rows),
            Table(name="children", row_count=child_rows),
        ],
        columns={
            "parents": [
                Column(name="id", type="int",
                       distribution_params={"distribution": "sequence", "start": 1},
                       unique=True),
            ],
            "children": [
                Column(name="id", type="int",
                       distribution_params={"distribution": "sequence", "start": 1},
                       unique=True),
                Column(name="parent_id", type="foreign_key", distribution_params={}),
            ],
        },
        relationships=[
            Relationship(
                parent_table="parents", parent_key="id",
                child_table="children", child_key="parent_id",
            )
        ],
    )


# ---------------------------------------------------------------------------
# C2 — PK store is populated and used for FK sampling
# ---------------------------------------------------------------------------

def test_c2_pk_store_populated():
    """_pk_store accumulates all parent PKs regardless of the context row cap."""
    schema = _parent_child_schema(parent_rows=200)
    sim = DataSimulator(schema)
    tables = {n: df for n, df in sim.generate_all()}

    assert "parents" in sim._pk_store
    assert len(sim._pk_store["parents"]) == 200

    parent_pks = set(tables["parents"]["id"].tolist())
    child_fks = set(tables["children"]["parent_id"].tolist())
    assert child_fks.issubset(parent_pks), "Orphaned FK values found"


def test_c2_fk_sampling_spans_full_range():
    """Child FK values must span the full parent PK range."""
    schema = _parent_child_schema(parent_rows=300, child_rows=300)
    sim = DataSimulator(schema)
    tables = {n: df for n, df in sim.generate_all()}

    parent_range = tables["parents"]["id"].max() - tables["parents"]["id"].min()
    fk_range = tables["children"]["parent_id"].max() - tables["children"]["parent_id"].min()

    assert fk_range >= parent_range * 0.5, (
        f"FK range {fk_range} suspiciously narrow vs parent range {parent_range}"
    )


# ---------------------------------------------------------------------------
# C4 — DataSimulator does not mutate global numpy RNG
# ---------------------------------------------------------------------------

def test_c4_no_global_rng_mutation():
    """Creating a DataSimulator must not alter np.random global state."""
    np.random.seed(42)
    expected = np.random.random()

    np.random.seed(42)
    DataSimulator(SchemaConfig(
        name="x", seed=99,
        tables=[Table(name="t", row_count=5)],
        columns={"t": [Column(name="id", type="int",
                               distribution_params={"distribution": "sequence", "start": 1})]},
    ))
    actual = np.random.random()

    assert actual == expected, "DataSimulator.__init__ mutated global np.random state"


def test_c4_generator_factory_thread_safe():
    """Each GeneratorFactory call must return its own independent RNG."""
    from misata.generators.base import GeneratorFactory

    results = []
    errors = []

    def _generate():
        try:
            gen = GeneratorFactory.get_generator("float")
            vals = gen.generate(500, {"distribution": "uniform", "min": 0, "max": 1})
            results.append(vals)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_generate) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"
    assert len(results) == 8
    # Concurrent threads each own independent generators — draws must not be identical
    unique_first = {r[0] for r in results}
    assert len(unique_first) > 1, "All threads produced identical draws — shared RNG"


# ---------------------------------------------------------------------------
# H1 — exact_incidence uses round(), not floor()
# ---------------------------------------------------------------------------

def test_h1_exact_incidence_round_not_floor():
    """rate=0.336 on 100 rows: round gives 34, floor gives 33."""
    schema = SchemaConfig(
        name="ei", seed=1,
        tables=[Table(name="t", row_count=100)],
        columns={"t": [
            Column(name="id", type="int",
                   distribution_params={"distribution": "sequence", "start": 1},
                   unique=True),
            Column(name="flag", type="boolean", distribution_params={
                "exact_incidence": {"mode": "exact", "rate": 0.336}
            }),
        ]},
    )
    tables = misata.generate_from_schema(schema)
    assert int(tables["t"]["flag"].sum()) == 34, (
        f"Expected 34 (round(33.6)), got {tables['t']['flag'].sum()}"
    )


def test_h1_grouped_exact_incidence_correct_count():
    """Grouped exact_incidence must also use round() per group."""
    schema = SchemaConfig(
        name="gei", seed=2,
        tables=[Table(name="t", row_count=100)],
        columns={"t": [
            Column(name="id", type="int",
                   distribution_params={"distribution": "sequence", "start": 1},
                   unique=True),
            Column(name="tier", type="categorical",
                   distribution_params={"choices": ["A", "B"],
                                        "probabilities": [0.5, 0.5]}),
            Column(name="flag", type="boolean", distribution_params={
                "exact_incidence": {
                    "mode": "exact",
                    "group_by": "tier",
                    "rates": {"A": 0.336, "B": 0.5},
                }
            }),
        ]},
    )
    tables = misata.generate_from_schema(schema)
    df = tables["t"]
    for tier, rate in [("A", 0.336), ("B", 0.5)]:
        grp = df[df["tier"] == tier]
        expected = int(round(len(grp) * rate))
        actual = int(grp["flag"].sum())
        assert actual == expected, f"Tier {tier}: expected {expected}, got {actual}"


# ---------------------------------------------------------------------------
# H3 — seasonal curve cycles instead of flat-clamping
# ---------------------------------------------------------------------------

def test_h3_seasonal_curve_cyclic_not_clamped():
    """Months outside the declared curve range must interpolate cyclically."""
    schema = SchemaConfig(
        name="seas", seed=3,
        tables=[Table(name="t", row_count=1200)],
        columns={"t": [
            Column(name="id", type="int",
                   distribution_params={"distribution": "sequence", "start": 1},
                   unique=True),
            Column(name="dt", type="date",
                   distribution_params={"distribution": "uniform",
                                        "start": "2024-01-01", "end": "2024-12-31"}),
            Column(name="amount", type="float",
                   distribution_params={"distribution": "uniform", "min": 100, "max": 200}),
        ]},
    )
    from misata.schema import OutcomeCurve
    schema.outcome_curves = [
        OutcomeCurve(
            table="t", column="amount", time_column="dt",
            pattern_type="seasonal",
            curve_points=[
                {"month": 6,  "relative_value": 0.5},
                {"month": 9,  "relative_value": 1.0},
                {"month": 12, "relative_value": 2.0},
            ],
        )
    ]
    df = misata.generate_from_schema(schema)["t"]
    df["month"] = pd.to_datetime(df["dt"]).dt.month

    mean_jan = df[df["month"] == 1]["amount"].mean()
    mean_jun = df[df["month"] == 6]["amount"].mean()
    mean_dec = df[df["month"] == 12]["amount"].mean()

    # Cyclic: Jan must differ from Jun (not clamped to it)
    assert abs(mean_jan - mean_jun) > 1.0, (
        f"Jan mean {mean_jan:.1f} ≈ Jun mean {mean_jun:.1f} — curve is flat-clamping"
    )
    assert mean_dec > mean_jun, "Dec (r=2.0) should scale higher than Jun (r=0.5)"


# ---------------------------------------------------------------------------
# H4 — generate_diff offsets FK columns correctly
# ---------------------------------------------------------------------------

def test_h4_generate_diff_fk_offset():
    """New child rows must reference new (offset) parent PKs only."""
    schema = _parent_child_schema(parent_rows=10, child_rows=20)

    with tempfile.TemporaryDirectory() as tmpdir:
        initial = misata.generate_from_schema(schema)
        for name, df in initial.items():
            df.to_csv(os.path.join(tmpdir, f"{name}.csv"), index=False)

        new_rows = misata.generate_diff(
            schema, tmpdir, new_rows={"parents": 5, "children": 10}
        )

    new_parent_pks = set(new_rows["parents"]["id"].tolist())
    new_child_fks = set(new_rows["children"]["parent_id"].tolist())

    assert new_child_fks.issubset(new_parent_pks), (
        f"Child FKs {new_child_fks - new_parent_pks} not in new parent PKs {new_parent_pks}"
    )


# ---------------------------------------------------------------------------
# M1 — correlations applied in fact tables
# ---------------------------------------------------------------------------

def test_m1_correlations_applied_in_fact_table():
    """__correlations__ must take effect even on fact tables."""
    from misata.schema import OutcomeCurve

    schema = SchemaConfig(
        name="fact_corr", seed=42,
        tables=[Table(name="sales", row_count=2000,
                      correlations=[{"col_a": "price", "col_b": "quantity", "r": 0.7}])],
        columns={"sales": [
            Column(name="id", type="int",
                   distribution_params={"distribution": "sequence", "start": 1}, unique=True),
            Column(name="dt", type="date",
                   distribution_params={"distribution": "uniform",
                                        "start": "2024-01-01", "end": "2024-12-31"}),
            Column(name="price", type="float",
                   distribution_params={"distribution": "uniform", "min": 1, "max": 100}),
            Column(name="quantity", type="int",
                   distribution_params={"distribution": "uniform", "min": 1, "max": 50}),
        ]},
        outcome_curves=[OutcomeCurve(
            table="sales", column="price", time_column="dt",
            pattern_type="growth",
            curve_points=[{"month": 1, "relative_value": 0.8},
                          {"month": 12, "relative_value": 1.2}],
        )],
    )
    df = misata.generate_from_schema(schema)["sales"]
    r = float(np.corrcoef(df["price"].astype(float), df["quantity"].astype(float))[0, 1])
    assert r > 0.35, f"Expected positive correlation ~0.7 in fact table, got {r:.3f}"


# ---------------------------------------------------------------------------
# M4 — NaN predictor rows receive base_rate missingness
# ---------------------------------------------------------------------------

def test_m4_nan_predictor_applies_base_rate():
    """Rows with NaN predictor must be nulled at base_rate, not silently skipped."""
    schema = SchemaConfig(
        name="m4", seed=5,
        tables=[Table(name="t", row_count=500)],
        columns={"t": [
            Column(name="id", type="int",
                   distribution_params={"distribution": "sequence", "start": 1}, unique=True),
            Column(name="income", type="float",
                   distribution_params={"distribution": "uniform",
                                        "min": 20000, "max": 100000,
                                        "null_rate": 0.5}),
            Column(name="target", type="float",
                   distribution_params={
                       "distribution": "uniform", "min": 0, "max": 1,
                       "missing_if": {
                           "predictor": "income",
                           "relationship": "higher_increases_probability",
                           "base_rate": 0.2,
                           "max_rate": 0.8,
                       }
                   }),
        ]},
    )
    df = misata.generate_from_schema(schema)["t"]
    nan_pred_rows = df[df["income"].isna()]
    if len(nan_pred_rows) < 10:
        pytest.skip("Too few NaN-predictor rows to test reliably")

    null_rate = nan_pred_rows["target"].isna().mean()
    assert null_rate > 0.02, (
        f"NaN-predictor rows had null rate {null_rate:.3f}; "
        "expected ~0.2 (base_rate) — rows may be silently skipped"
    )


# ---------------------------------------------------------------------------
# M5 — cluster effects preserve integer dtype
# ---------------------------------------------------------------------------

def test_m5_cluster_effects_preserve_int_dtype():
    """Adding a float intercept to an int column must not widen it to float."""
    schema = from_dict_schema({
        "sites": {
            "__rows__": 10,
            "__cluster_effect__": {
                "affects_table": "patients",
                "affects_columns": {"score": {"icc": 0.3, "sd_total": 10}},
            },
            "id": {"type": "integer", "primary_key": True},
        },
        "patients": {
            "__rows__": 100,
            "id":       {"type": "integer", "primary_key": True},
            "site_id":  {"type": "integer",
                         "foreign_key": {"table": "sites", "column": "id"}},
            "score":    {"type": "integer", "distribution": "normal",
                         "mean": 50, "std": 10},
        },
    })
    tables = misata.generate_from_schema(schema)
    dtype = tables["patients"]["score"].dtype
    assert pd.api.types.is_integer_dtype(dtype), (
        f"score dtype widened to {dtype} after cluster effects"
    )


# ---------------------------------------------------------------------------
# M6 — growth curve normalisation handles multi-year indices
# ---------------------------------------------------------------------------

def test_m6_growth_curve_multi_year():
    """Month indices 1-24 must produce higher scaling in year 2 than year 1."""
    from misata.schema import OutcomeCurve

    schema = SchemaConfig(
        name="m6", seed=8,
        tables=[Table(name="t", row_count=2400)],
        columns={"t": [
            Column(name="id", type="int",
                   distribution_params={"distribution": "sequence", "start": 1}, unique=True),
            Column(name="dt", type="date",
                   distribution_params={"distribution": "uniform",
                                        "start": "2023-01-01", "end": "2024-12-31"}),
            Column(name="revenue", type="float",
                   distribution_params={"distribution": "uniform", "min": 100, "max": 200}),
        ]},
        outcome_curves=[OutcomeCurve(
            table="t", column="revenue", time_column="dt",
            pattern_type="growth",
            curve_points=[
                {"month": 1,  "relative_value": 0.5},
                {"month": 12, "relative_value": 1.0},
                {"month": 24, "relative_value": 2.0},
            ],
        )],
    )
    df = misata.generate_from_schema(schema)["t"]
    df["yr"] = pd.to_datetime(df["dt"]).dt.year
    mean_2023 = df[df["yr"] == 2023]["revenue"].mean()
    mean_2024 = df[df["yr"] == 2024]["revenue"].mean()

    assert mean_2024 > mean_2023 * 1.2, (
        f"Year-2 mean ({mean_2024:.1f}) should notably exceed year-1 ({mean_2023:.1f})"
    )


# ---------------------------------------------------------------------------
# M9 — same-table formula resolves sibling columns
# ---------------------------------------------------------------------------

def test_m9_same_table_formula():
    """A formula referencing sibling columns must evaluate against the live row."""
    schema = from_dict_schema({
        "sales": {
            "__rows__": 50,
            "id":       {"type": "integer", "primary_key": True},
            "price":    {"type": "float", "distribution": "uniform", "min": 10, "max": 100},
            "quantity": {"type": "integer", "distribution": "uniform", "min": 1, "max": 10},
            "revenue":  {"type": "float", "formula": "price * quantity"},
        }
    })
    df = misata.generate_from_schema(schema)["sales"]

    assert "revenue" in df.columns
    mask = df["revenue"].notna() & df["price"].notna() & df["quantity"].notna()
    expected = df.loc[mask, "price"] * df.loc[mask, "quantity"]
    actual = df.loc[mask, "revenue"]
    assert np.allclose(actual.values, expected.values, rtol=1e-4), (
        "revenue != price * quantity — same-table formula not resolving sibling columns"
    )


# ---------------------------------------------------------------------------
# L4 — to_arrow writes date columns as date32, not TimestampType
# ---------------------------------------------------------------------------

def test_l4_to_arrow_date_columns_are_date32():
    """Columns holding python date objects must map to pa.date32() in Arrow."""
    pa = pytest.importorskip("pyarrow")
    import pyarrow.ipc as ipc
    from misata.export import to_arrow

    df = pd.DataFrame({
        "date_col": [datetime.date(2024, 1, 1), datetime.date(2024, 6, 15)],
        "ts_col":   pd.to_datetime(["2024-01-01", "2024-06-15"]),
        "val":      [1.0, 2.0],
    })

    with tempfile.TemporaryDirectory() as tmp:
        to_arrow({"t": df}, tmp)
        with pa.OSFile(os.path.join(tmp, "t.arrow")) as f:
            table = ipc.open_file(f).read_all()

    assert pa.types.is_date32(table.schema.field("date_col").type), (
        f"Expected date32, got {table.schema.field('date_col').type}"
    )
    assert pa.types.is_timestamp(table.schema.field("ts_col").type), (
        "datetime column should stay as TimestampType"
    )


# ---------------------------------------------------------------------------
# L6 — FloatGenerator.beta scales output to [min, max]
# ---------------------------------------------------------------------------

def test_l6_beta_scales_to_min_max():
    """Beta distribution must be scaled to [min, max], not left as raw [0, 1]."""
    from misata.generators.base import FloatGenerator

    gen = FloatGenerator()
    values = gen.generate(2000, {"distribution": "beta", "a": 2.0, "b": 5.0,
                                 "min": 10.0, "max": 50.0})
    assert values.min() >= 10.0 - 0.01, f"min {values.min():.4f} below declared min 10"
    assert values.max() <= 50.0 + 0.01, f"max {values.max():.4f} above declared max 50"
    # Beta(2,5) mean ≈ 0.286 → scaled ≈ 10 + 0.286*40 ≈ 21.4
    assert 15 < values.mean() < 30, f"Unexpected scaled mean {values.mean():.2f}"


def test_l6_beta_default_range_unchanged():
    """Beta with no min/max must remain in [0, 1] (backwards compatible)."""
    from misata.generators.base import FloatGenerator

    values = FloatGenerator().generate(1000, {"distribution": "beta", "a": 2.0, "b": 5.0})
    assert values.min() >= 0.0
    assert values.max() <= 1.0


# ---------------------------------------------------------------------------
# UC spark helpers — no PySpark required
# ---------------------------------------------------------------------------

def test_uc_table_exists_returns_false_on_error():
    """_table_exists_uc must return False (not raise) on any SQL error."""
    from misata.spark import _table_exists_uc

    class _BadSpark:
        def sql(self, _q):
            raise RuntimeError("table not found")

    assert _table_exists_uc(_BadSpark(), "nonexistent.table") is False


def test_uc_foreign_keys_returns_empty_without_info_schema():
    """_uc_foreign_keys must return {} when INFORMATION_SCHEMA is absent."""
    from misata.spark import _uc_foreign_keys

    class _BadSpark:
        def sql(self, _q):
            raise RuntimeError("no such table: INFORMATION_SCHEMA")

    assert _uc_foreign_keys(_BadSpark(), "catalog", "bronze") == {}
