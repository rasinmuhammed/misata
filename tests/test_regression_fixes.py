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


# ---------------------------------------------------------------------------
# DQ1 — from_dict_schema exposes __noise__ for declared data-quality defects
# ---------------------------------------------------------------------------

def _noise_spec(noise: dict) -> dict:
    return {
        "__noise__": noise,
        "customers": {
            "__rows__": 1000,
            "id":    {"type": "integer", "primary_key": True},
            "name":  {"type": "string", "text_type": "name"},
            "spend": {"type": "float", "distribution": "normal", "mean": 100, "std": 20},
        },
    }


def test_noise_directive_parsed_into_config():
    """__noise__ must build a NoiseConfig on the SchemaConfig."""
    schema = from_dict_schema(_noise_spec({"mode": "custom", "duplicate_rate": 0.05}))
    assert schema.noise_config is not None
    assert schema.noise_config.duplicate_rate == 0.05


def test_noise_custom_mode_injects_duplicates_and_nulls():
    """custom mode injects duplicate rows and null cells at the declared rate."""
    schema = from_dict_schema(
        _noise_spec({"mode": "custom", "duplicate_rate": 0.05, "null_rate": 0.03}),
        seed=7,
    )
    df = misata.generate_from_schema(schema)["customers"]
    # 1000 base rows + ~5% duplicates
    assert len(df) > 1000, "duplicate_rate did not add rows"
    assert int(df["id"].duplicated().sum()) > 0, "no duplicate PKs injected"
    assert int(df["spend"].isna().sum()) > 0, "null_rate injected no nulls"


def test_noise_analytics_safe_protects_keys():
    """analytics_safe must never duplicate rows or null out the primary key."""
    schema = from_dict_schema(
        _noise_spec({"mode": "analytics_safe", "duplicate_rate": 0.05, "null_rate": 0.05}),
        seed=7,
    )
    df = misata.generate_from_schema(schema)["customers"]
    assert len(df) == 1000, "analytics_safe must not duplicate rows"
    assert int(df["id"].duplicated().sum()) == 0, "analytics_safe duplicated PKs"
    assert int(df["id"].isna().sum()) == 0, "analytics_safe nulled the PK"


def test_noise_invalid_raises():
    """A malformed __noise__ must fail loudly at schema-compile time."""
    with pytest.raises(ValueError, match="__noise__"):
        from_dict_schema(_noise_spec({"duplicate_rate": 5.0}))  # > 1.0 is invalid


# ---------------------------------------------------------------------------
# Text-type inference: token-aware matching (replaces greedy substring scan)
# ---------------------------------------------------------------------------

def test_entity_name_columns_are_not_person_names():
    """`*_name` entity columns must not borrow the person-name generator.

    Greedy substring matching turned product_name / file_name / category_name
    (and ip_address / mac_address) into human names and street addresses.
    """
    from misata.compat import _infer_text_type as infer

    # Entity / technical names: never a person name.
    for col in (
        "product_name", "file_name", "filename", "hostname", "category_name",
        "table_name", "column_name", "event_name", "app_name", "role_name",
        "tag_name",
    ):
        assert infer(col) != "name", f"{col} wrongly resolved to person name"

    # Network / crypto addresses: never a street address.
    for col in ("ip_address", "mac_address", "wallet_address"):
        assert infer(col) != "address", f"{col} wrongly resolved to street address"


def test_person_and_contact_columns_still_resolve():
    """The fix must not regress the columns that should resolve."""
    from misata.compat import _infer_text_type as infer

    expected = {
        "name": "name", "full_name": "name", "customer_name": "name",
        "user_name": "name", "first_name": "first_name", "last_name": "last_name",
        "company_name": "company", "brand_name": "company",
        "email": "email", "user_email": "email", "email_address": "email",
        "phone_number": "phone", "mobile_number": "phone",
        "billing_address": "address", "shipping_address": "address",
        "shipping_city": "city", "home_country": "country",
        "zip_code": "postcode", "profile_url": "url", "job_title": "job",
        "domain_name": "domain",
    }
    for col, want in expected.items():
        assert infer(col) == want, f"{col}: expected {want!r}, got {infer(col)!r}"


def test_identifier_suffix_columns_are_uuids():
    """Token/id-suffixed text columns generate identifiers, not free text."""
    from misata.compat import _infer_text_type as infer

    for col in (
        "anonymous_id", "request_id", "device_token", "correlation_id",
        "user_id", "order_uuid", "session_token",
    ):
        assert infer(col) == "uuid", f"{col} should infer uuid, got {infer(col)!r}"


def test_unknown_columns_stay_free_text():
    """Ambiguous names resolve to None (free text) rather than a wrong guess."""
    from misata.compat import _infer_text_type as infer

    for col in ("user_agent", "region", "description", "timezone"):
        assert infer(col) is None, f"{col} should be free text, got {infer(col)!r}"


def test_entity_catalog_columns_route_to_realistic_generators():
    """Unambiguous entity columns infer realistic catalog semantic types."""
    from misata.compat import _infer_text_type as infer

    expected = {
        "product_name": "product_name", "item_name": "product_name",
        "product_description": "product_description",
        "menu_item": "menu_item", "restaurant_name": "restaurant_name",
        "review_text": "review", "bio": "bio", "caption": "caption",
    }
    for col, want in expected.items():
        assert infer(col) == want, f"{col}: expected {want!r}, got {infer(col)!r}"


def test_entity_name_values_are_not_sentences_or_people():
    """product_name generates product-like values; customer_name stays a person."""
    schema = from_dict_schema(
        {
            "catalog": {
                "__rows__": 30,
                "id": {"type": "integer", "primary_key": True},
                "product_name": {"type": "text"},
                "customer_name": {"type": "text"},
            }
        },
        seed=3,
    )
    df = misata.generate_from_schema(schema)["catalog"]
    products = df["product_name"].astype(str)
    # Product names are short labels, not multi-clause business sentences.
    assert products.str.len().mean() < 40, "product_name looks like sentences"
    assert not products.str.endswith(".").any(), "product_name should not be sentences"
    # customer_name should still look like a person (two words, no trailing period).
    people = df["customer_name"].astype(str)
    assert (people.str.split().str.len() == 2).mean() > 0.7, "customer_name not person-like"


def test_integer_max_is_inclusive():
    """A declared integer max must be reachable (rating 1..5 must hit 5)."""
    for lo, hi in [(1, 2), (1, 5), (0, 1), (5, 10)]:
        schema = from_dict_schema(
            {"t": {"__rows__": 3000, "v": {"type": "integer", "min": lo, "max": hi}}},
            seed=1,
        )
        v = misata.generate_from_schema(schema)["t"]["v"]
        assert int(v.min()) == lo, f"min {lo}..{hi}: got {v.min()}"
        assert int(v.max()) == hi, f"max {lo}..{hi} unreachable: got {v.max()}"


def test_unique_integer_range_is_inclusive():
    """A unique integer column over [1,5] must be able to fill 5 rows exactly."""
    schema = from_dict_schema(
        {"u": {"__rows__": 5,
               "v": {"type": "integer", "min": 1, "max": 5, "unique": True}}},
        seed=2,
    )
    v = sorted(misata.generate_from_schema(schema)["u"]["v"].tolist())
    assert v == [1, 2, 3, 4, 5], f"unique inclusive range wrong: {v}"


# ---------------------------------------------------------------------------
# Resilience Phase 1: measured values, attribute extraction, cardinality realism
# (compositional path for unseen domains) — guards docs/resilience.md C2/C3/C4.
# ---------------------------------------------------------------------------

def test_extract_measures_finds_named_quantities():
    from misata.composer import extract_measures
    names = {m[0] for m in extract_measures(
        "machines emitting temperature and vibration readings every hour")}
    assert "temperature" in names and "vibration" in names


def test_measured_event_gets_named_value_columns():
    """C2 + C3: a reading table carries the quantities the story named."""
    from misata.composer import compose_schema
    schema = compose_schema(
        "A factory with 50 machines emitting temperature and vibration sensor readings.",
        default_rows=1000,
    )
    cols = {c.name for c in schema.columns["sensor_readings"]}
    assert "temperature_celsius" in cols and "vibration_mm_s" in cols, cols


def test_measured_event_without_named_quantity_gets_generic_value():
    from misata.composer import compose_schema
    schema = compose_schema("A network of 20 buoys recording ocean readings.", default_rows=500)
    reading_tbl = next(t for t in schema.columns if "reading" in t)
    cols = {c.name for c in schema.columns[reading_tbl]}
    assert "value" in cols and "unit" in cols, cols


def test_cardinality_does_not_explode_unstated_entities():
    """C4: a 200-case firm must not spawn thousands of attorneys."""
    from misata.composer import compose_schema
    schema = compose_schema(
        "A law firm managing 200 legal cases, clients, attorneys, and court hearings.",
        default_rows=10_000,
    )
    rc = {t.name: t.row_count for t in schema.tables}
    assert rc["legal_cases"] == 200
    assert rc["attorneys"] <= 400 and rc["clients"] <= 400, rc


def test_event_counts_are_proportional_to_parents():
    """C4: child events scale off parent volume, not a flat 30k default."""
    from misata.composer import compose_schema
    schema = compose_schema(
        "A factory with 50 machines emitting sensor readings.", default_rows=10_000)
    rc = {t.name: t.row_count for t in schema.tables}
    assert rc["machines"] == 50
    assert rc["sensor_readings"] <= 50 * 20, rc["sensor_readings"]


def test_composed_stated_counts_still_honoured():
    from misata.composer import compose_schema
    schema = compose_schema("A fleet of 40 trucks and 5000 deliveries.", default_rows=1000)
    rc = {t.name: t.row_count for t in schema.tables}
    assert rc["trucks"] == 40 and rc["deliveries"] == 5000


def test_composed_measured_values_generate_in_range():
    import warnings as _w
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        tables = misata.generate(
            "A factory with 50 machines emitting temperature and vibration sensor readings.",
            seed=1,
        )
    readings = tables["sensor_readings"]
    assert "temperature_celsius" in readings.columns
    assert readings["temperature_celsius"].between(-10, 120).all()


# ---------------------------------------------------------------------------
# AWS Bedrock provider (Converse API) — server-funded LLM path
# ---------------------------------------------------------------------------

def test_bedrock_provider_builds_converse_payload(monkeypatch):
    """The bedrock provider formats messages for the Converse API correctly."""
    pytest.importorskip("boto3")
    from unittest.mock import MagicMock
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    from misata.llm_parser import LLMSchemaGenerator

    gen = LLMSchemaGenerator(provider="bedrock", model="anthropic.claude-3-5-haiku-20241022-v1:0")
    assert gen.provider == "bedrock" and gen._protocol == "bedrock"

    captured = {}
    def fake_converse(**kw):
        captured.update(kw)
        return {"output": {"message": {"content": [{"text": '{"ok": true}'}]}}}
    gen.client = MagicMock()
    gen.client.converse = fake_converse

    out = gen._call_bedrock(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        max_tokens=6000, temperature=0.3,
    )
    assert out == '{"ok": true}'
    assert captured["modelId"] == "anthropic.claude-3-5-haiku-20241022-v1:0"
    assert captured["system"] == [{"text": "sys"}]
    assert captured["inferenceConfig"]["maxTokens"] == 4096  # capped for Bedrock
    # Converse content-block message shape, with a JSON nudge on the last turn.
    last = captured["messages"][-1]["content"][0]["text"]
    assert last.startswith("hi")
    assert last.strip().endswith("JSON only.")


def test_bedrock_model_id_env_override(monkeypatch):
    pytest.importorskip("boto3")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "custom.model.id")
    from misata.llm_parser import LLMSchemaGenerator
    assert LLMSchemaGenerator(provider="bedrock").model == "custom.model.id"


# ---------------------------------------------------------------------------
# Realism value-generation: lookup tables / domain (LLM path, no inline_data)
# ---------------------------------------------------------------------------

def test_realism_lookup_name_is_not_a_person():
    """A free-text `name` in a lookup/dimension table must not become a person."""
    import numpy as np
    from misata.realism import RealisticTextGenerator
    g = RealisticTextGenerator(np.random.default_rng(1))
    # lookup/dimension tables -> a neutral label, never a person
    assert g._infer_semantic("name", "plans") == "category_label"
    assert g._infer_semantic("name", "subscription_status") == "category_label"
    assert g._infer_semantic("status", "subscription_status") == "category_label"
    assert g._infer_semantic("type", "usage_event_type") == "category_label"
    # real person tables still resolve to a person name
    assert g._infer_semantic("name", "customers") == "person_name"
    assert g._infer_semantic("name", "users") == "person_name"


def test_realism_domain_is_a_url_not_a_sentence():
    import numpy as np
    from misata.realism import RealisticTextGenerator
    g = RealisticTextGenerator(np.random.default_rng(1))
    assert g._infer_semantic("domain", "customers") == "url"
    vals = list(g.generate("domain", "customers", 3, None))
    assert all(str(v).startswith("http") for v in vals), vals


def test_realism_category_label_values_are_short():
    import numpy as np
    from misata.realism import RealisticTextGenerator
    g = RealisticTextGenerator(np.random.default_rng(3))
    vals = [str(v) for v in g.generate("name", "plans", 5, None)]
    # short labels, not person names or sentences
    assert all(len(v) < 30 and "." not in v for v in vals), vals


# ---------------------------------------------------------------------------
# LLM-output robustness: imperfect-but-close schemas must not crash generation
# ---------------------------------------------------------------------------

def _new_gen():
    from misata.llm_parser import LLMSchemaGenerator
    return LLMSchemaGenerator.__new__(LLMSchemaGenerator)


def test_llm_probabilities_coerced_and_renormalized():
    g = _new_gen()
    # mixed int/str (used to crash validation's sum()) -> clean floats summing to 1
    out = g._normalize_distribution_params("categorical",
        {"choices": ["a", "b", "c"], "probabilities": [1, "2", 1]})
    assert out["probabilities"] == [0.25, 0.5, 0.25]
    # length mismatch / garbage -> dropped (engine falls back to uniform)
    assert "probabilities" not in g._normalize_distribution_params("categorical",
        {"choices": ["a", "b"], "probabilities": [0.5, 0.3, 0.2]})
    assert "probabilities" not in g._normalize_distribution_params("categorical",
        {"choices": ["a", "b"], "probabilities": "high"})


def test_llm_time_unit_normalized_to_allowed_enum():
    g = _new_gen()
    assert g._normalize_time_unit("quarter") == "month"
    assert g._normalize_time_unit("yearly") == "month"
    assert g._normalize_time_unit("daily") == "day"
    assert g._normalize_time_unit("bogus") == "month"
    assert g._normalize_time_unit(None) == "month"


def test_llm_foreign_key_without_relationship_is_repaired():
    g = _new_gen()
    schema_dict = {
        "name": "t", "seed": 1,
        "tables": [
            {"name": "tiers", "is_reference": True,
             "inline_data": [{"id": 1, "name": "Gold"}, {"id": 2, "name": "Silver"}]},
            {"name": "sellers", "row_count": 40},
            {"name": "orphans", "row_count": 10},
        ],
        "columns": {
            "sellers": [{"name": "id", "type": "int", "unique": True},
                        {"name": "tier_id", "type": "foreign_key"}],
            "orphans": [{"name": "id", "type": "int", "unique": True},
                        {"name": "nonexistent_id", "type": "foreign_key"}],
        },
        "relationships": [],
    }
    cfg = g._parse_schema(schema_dict)
    # inferred the missing relationship to `tiers`
    assert ("tiers", "sellers", "tier_id") in [
        (r.parent_table, r.child_table, r.child_key) for r in cfg.relationships]
    # orphan FK (no parent table) demoted to int, not left to crash validation
    assert {c.name: c.type for c in cfg.get_columns("orphans")}["nonexistent_id"] == "int"
    # and it actually generates with valid FK integrity
    tables = misata.generate_from_schema(cfg)
    assert set(tables["sellers"]["tier_id"]).issubset(set(tables["tiers"]["id"]))


# ---------------------------------------------------------------------------
# 0.8.1.8 value-quality: explicit text_type passthrough from dict schema
# ---------------------------------------------------------------------------

def test_realism_name_semantic_type_in_lookup_table_gives_label():
    """When from_dict_schema passthrough sets text_type='name' on a lookup column,
    the generator must produce a short label, not a person name or lorem sentence."""
    import numpy as np
    from misata.realism import RealisticTextGenerator
    g = RealisticTextGenerator(np.random.default_rng(7))
    # explicit semantic_type="name" in a non-person table → category label
    vals = [str(v) for v in g.generate("name", "plans", 6, "name")]
    assert all(len(v) < 30 for v in vals), f"too long: {vals}"
    assert not any(v.count(" ") >= 2 for v in vals), f"looks like a person name: {vals}"


def test_realism_name_semantic_type_in_person_table_gives_full_name():
    """When text_type='name' is on a column in a person table, a human name is correct."""
    import numpy as np
    from misata.realism import RealisticTextGenerator
    g = RealisticTextGenerator(np.random.default_rng(8))
    vals = [str(v) for v in g.generate("name", "customers", 5, "name")]
    # full names have at least one space
    assert all(" " in v for v in vals), f"expected full name with space: {vals}"


def test_realism_domain_semantic_type_gives_url():
    """When engine_public.py enrichment sets text_type='domain', the result is a URL."""
    import numpy as np
    from misata.realism import RealisticTextGenerator
    g = RealisticTextGenerator(np.random.default_rng(9))
    vals = [str(v) for v in g.generate("domain", "companies", 4, "domain")]
    assert all(v.startswith("https://") for v in vals), f"expected URL: {vals}"


def test_realism_industry_column_is_industry_type():
    """industry/sector/vertical columns must not fall through to lorem sentences."""
    import numpy as np
    from misata.realism import RealisticTextGenerator, _INDUSTRY_LABELS
    g = RealisticTextGenerator(np.random.default_rng(10))
    assert g._infer_semantic("industry", "companies") == "industry"
    assert g._infer_semantic("sector", "leads") == "industry"
    assert g._infer_semantic("vertical", "accounts") == "industry"
    vals = [str(v) for v in g.generate("industry", "companies", 5, None)]
    # Must be short, no sentences, and drawn from the industry vocabulary
    assert all(len(v) < 40 and "." not in v for v in vals), f"looks like a sentence: {vals}"
    assert any(v in _INDUSTRY_LABELS for v in vals), f"not industry labels: {vals}"


# ---------------------------------------------------------------------------
# 0.8.1.8 pass-2: person_name guard, product tables, action_name, column qualifier
# ---------------------------------------------------------------------------

def test_realism_explicit_person_name_in_lookup_table_is_guarded():
    """If the LLM hardcodes text_type='person_name' on plans.name, the guard
    must intercept and return a tier label, not a human name."""
    import numpy as np
    from misata.realism import RealisticTextGenerator
    g = RealisticTextGenerator(np.random.default_rng(42))
    vals = [str(v) for v in g.generate("name", "plans", 5, "person_name")]
    assert all(len(v) < 30 and " " not in v or " " not in v for v in vals), (
        f"person_name guard failed — still generating person names in plans: {vals}"
    )
    # person tables must still produce human names even with explicit person_name
    person_vals = [str(v) for v in g.generate("name", "users", 5, "person_name")]
    assert all(" " in v for v in person_vals), f"users.name should be person: {person_vals}"


def test_realism_products_table_name_column_generates_product_names():
    """products.name must route to product_name, not category_label or person names."""
    import numpy as np
    from misata.realism import RealisticTextGenerator
    g = RealisticTextGenerator(np.random.default_rng(3))
    got = g._infer_semantic("name", "products")
    assert got == "product_name", f"expected product_name, got {got!r}"
    got2 = g._infer_semantic("name", "items")
    assert got2 == "product_name", f"expected product_name for items table, got {got2!r}"


def test_realism_action_name_in_logs_gives_event_type():
    """action_name in logs/events must produce event-type slugs, not category labels."""
    import numpy as np
    from misata.realism import RealisticTextGenerator, _EVENT_TYPE_LABELS
    g = RealisticTextGenerator(np.random.default_rng(5))
    vals = [str(v) for v in g.generate("action_name", "logs", 6, None)]
    assert all(len(v) < 40 and "." not in v for v in vals), f"looks like sentence: {vals}"
    # At least some should come from the event vocabulary
    assert any(v in _EVENT_TYPE_LABELS for v in vals), f"not event labels: {vals}"


def test_realism_customer_name_infer_semantic_returns_person():
    """_infer_semantic must return 'person_name' for customer_name in any table."""
    import numpy as np
    from misata.realism import RealisticTextGenerator
    g = RealisticTextGenerator(np.random.default_rng(1))
    assert g._infer_semantic("customer_name", "invoices") == "person_name"
    assert g._infer_semantic("recipient_name", "emails") == "person_name"
    assert g._infer_semantic("company_name", "orders") == "company_name"


# ---------------------------------------------------------------------------
# 0.8.1.9: curve extraction toolbox — rate_curves, id-column guard, correlations
# ---------------------------------------------------------------------------

def _parse(schema_dict):
    from misata.llm_parser import LLMSchemaGenerator
    return LLMSchemaGenerator.__new__(LLMSchemaGenerator)._parse_schema(schema_dict)


def test_rate_curve_is_parsed_from_llm_output():
    """A `rate_curves` key from the LLM must become RateCurve objects (was dropped)."""
    cfg = _parse({
        "name": "t", "seed": 1,
        "tables": [{"name": "subs", "row_count": 1000}],
        "columns": {"subs": [
            {"name": "id", "type": "int", "unique": True},
            {"name": "churn_date", "type": "date"},
            {"name": "churned", "type": "boolean"},
        ]},
        "relationships": [],
        "rate_curves": [{
            "table": "subs", "column": "churned", "time_column": "churn_date",
            "time_unit": "quarter", "true_value": True,
            "rate_points": [{"period": 1, "rate": 0.02}, {"period": 12, "rate": 0.09}],
        }],
    })
    assert len(cfg.rate_curves) == 1
    rc = cfg.rate_curves[0]
    assert rc.table == "subs" and rc.column == "churned"
    assert rc.time_unit == "quarter"          # RateCurve allows quarter
    assert len(rc.rate_points) == 2


def test_outcome_curve_on_id_column_is_dropped():
    """A curve attached to an id/pk/fk column is meaningless and must be dropped."""
    cfg = _parse({
        "name": "t", "seed": 1,
        "tables": [{"name": "views", "row_count": 1000}],
        "columns": {"views": [
            {"name": "id", "type": "int", "unique": True},
            {"name": "viewed_at", "type": "date"},
            {"name": "watch_seconds", "type": "int"},
        ]},
        "relationships": [],
        "outcome_curves": [
            {"table": "views", "column": "id", "time_column": "viewed_at",
             "pattern_type": "growth", "curve_points": [{"month": 1, "target_value": 5}]},
            {"table": "views", "column": "watch_seconds", "time_column": "viewed_at",
             "pattern_type": "growth", "curve_points": [{"month": 1, "target_value": 5}]},
        ],
    })
    cols = [c.column for c in cfg.outcome_curves]
    assert "id" not in cols, "curve on id column should have been dropped"
    assert "watch_seconds" in cols, "valid measure curve should be kept"


def test_table_correlations_parsed_from_llm_output():
    """Pairwise numeric correlations on a table must round-trip (was never read)."""
    cfg = _parse({
        "name": "t", "seed": 1,
        "tables": [{"name": "loans", "row_count": 8000,
                    "correlations": [{"col_a": "credit_score", "col_b": "default_prob", "r": -0.6}]}],
        "columns": {"loans": [
            {"name": "id", "type": "int", "unique": True},
            {"name": "credit_score", "type": "int"},
            {"name": "default_prob", "type": "float"},
        ]},
        "relationships": [],
    })
    corr = cfg.tables[0].correlations
    assert corr and corr[0]["col_a"] == "credit_score" and corr[0]["r"] == -0.6


def test_time_unit_quarter_only_for_rate_curves():
    """OutcomeCurve normalizes quarter→month; RateCurve keeps quarter."""
    from misata.llm_parser import LLMSchemaGenerator
    g = LLMSchemaGenerator.__new__(LLMSchemaGenerator)
    assert g._normalize_time_unit("quarter") == "month"
    assert g._normalize_time_unit("quarter", allow_quarter=True) == "quarter"


def test_dict_schema_forwards_lambda_and_null_rate():
    """0.8.1.10: from_dict_schema dropped poisson `lambda` and column `null_rate`
    (and binomial n/p), so declared distributions silently degraded. They must now
    reach the generator."""
    schema = from_dict_schema({
        "t": {
            "__rows__": 20000,
            "k":   {"type": "integer", "distribution": "poisson", "lambda": 4, "min": 0},
            "opt": {"type": "float", "distribution": "normal", "mean": 5, "std": 1, "null_rate": 0.15},
        }
    }, seed=1)
    params = {c.name: c.distribution_params for c in schema.get_columns("t")}
    assert params["k"].get("lambda") == 4, "poisson lambda dropped by from_dict_schema"
    assert params["opt"].get("null_rate") == 0.15, "null_rate dropped by from_dict_schema"
    df = misata.generate_from_schema(schema)["t"]
    assert abs(df["k"].mean() - 4) < 0.3, f"poisson mean {df['k'].mean():.2f} ≠ 4 (lambda ignored)"
    assert abs(df["opt"].isna().mean() - 0.15) < 0.03, "null_rate not applied"


def test_binomial_and_zipf_distributions_in_simulator():
    """0.8.1.10: the simulator's integer path lacked `binomial` and `zipf`, so both
    fell through to uniform[0,1000]. zipf in particular is what the LLM is told to
    emit for heavy-tailed columns."""
    bn = misata.generate_from_schema(from_dict_schema(
        {"t": {"__rows__": 20000, "k": {"type": "integer", "distribution": "binomial", "n": 10, "p": 0.3}}},
        seed=1))["t"]
    assert bn["k"].max() <= 10, f"binomial exceeded n=10 (max {bn['k'].max()}) — fell back to uniform"
    assert abs(bn["k"].mean() - 3.0) < 0.3, f"binomial mean {bn['k'].mean():.2f} ≠ n*p=3"

    zf = misata.generate_from_schema(from_dict_schema(
        {"t": {"__rows__": 20000, "views": {"type": "integer", "distribution": "zipf", "a": 2.0, "min": 1}}},
        seed=1))["t"]
    median, mx = float(np.median(zf["views"])), int(zf["views"].max())
    assert median <= 5 and mx > median * 20, (
        f"zipf not heavy-tailed (median={median}, max={mx}) — likely fell back to uniform"
    )


def test_rate_curve_on_fk_id_column_is_dropped():
    """A rate curve attached to a foreign-key id column (e.g. status_id) is dropped."""
    cfg = _parse({
        "name": "t", "seed": 1,
        "tables": [{"name": "tickets", "row_count": 100}],
        "columns": {"tickets": [
            {"name": "id", "type": "int", "unique": True},
            {"name": "status_id", "type": "foreign_key"},
            {"name": "resolved", "type": "boolean"},
            {"name": "created_at", "type": "date"},
        ]},
        "relationships": [],
        "rate_curves": [
            {"table": "tickets", "column": "status_id", "time_column": "created_at",
             "rate_points": [{"period": 1, "rate": 0.1}]},
            {"table": "tickets", "column": "resolved", "time_column": "created_at",
             "rate_points": [{"period": 1, "rate": 0.7}]},
        ],
    })
    cols = [c.column for c in cfg.rate_curves]
    assert "status_id" not in cols, "rate curve on fk id column should be dropped"
    assert "resolved" in cols, "rate curve on a boolean column should be kept"


def test_semantic_type_in_type_field_does_not_crash():
    """`type: "email"` (a semantic type in the type field) coerces to text+text_type,
    and a wholly-unknown type falls back to text instead of raising."""
    cfg = _parse({
        "name": "t", "seed": 1,
        "tables": [{"name": "people", "row_count": 50}],
        "columns": {"people": [
            {"name": "id", "type": "int", "unique": True},
            {"name": "contact", "type": "email"},
            {"name": "blob", "type": "geojson"},
        ]},
        "relationships": [],
    })
    by = {c.name: c for c in cfg.columns["people"]}
    assert by["contact"].type == "text"
    assert by["contact"].distribution_params.get("text_type") == "email"
    assert by["blob"].type == "text"   # unknown type → text, no crash


def test_listing_title_category_are_coherent_and_diverse():
    """C8: a marketplace `listings` table's title must match its category, while
    the category distribution stays diverse (not collapsed to one pool)."""
    from misata.realism import _NAME_TO_POOL
    schema = from_dict_schema({
        "listings": {
            "__rows__": 60,
            "listing_id": {"type": "integer", "primary_key": True},
            "title": {"type": "text", "text_type": "product_name"},
            "category": {"type": "string",
                         "enum": ["electronics", "home", "books", "clothing", "sports", "beauty"]},
        }
    }, seed=7)
    df = misata.generate_from_schema(schema)["listings"]
    mismatch = 0
    cats = set()
    for title, cat in zip(df["title"].astype(str), df["category"].astype(str)):
        cats.add(cat)
        pool = _NAME_TO_POOL.get(title)
        if pool and pool.lower() not in cat.lower() and cat.lower() not in pool.lower():
            mismatch += 1
    assert mismatch == 0, f"{mismatch} title/category mismatches"
    assert len(cats) >= 3, f"category collapsed to {cats} — lost diversity"
