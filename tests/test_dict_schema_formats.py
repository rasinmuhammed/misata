"""Regression tests for from_dict_schema input formats and Oracle curve-awareness.

Covers the three 0.8.1.15 fixes:
  1. YAML-style envelope ({"name", "seed", "tables", "relationships"}) unwrap —
     previously parsed "tables" as a table named tables and generated garbage.
  2. references: "parent.key" string on foreign_key columns — previously never
     created a Relationship, so validation rejected the README's own example.
  3. Oracle row-count check is curve-aware — previously oracle["passed"] was
     False on perfectly curve-conformant datasets.
"""
import pandas as pd
import pytest

import misata


ENVELOPE_SCHEMA = {
    "name": "shop",
    "seed": 7,
    "tables": {
        "customers": {"rows": 300, "columns": {
            "customer_id": {"type": "int", "unique": True},
            "total_spent": {"type": "float", "rollup": {
                "from_table": "orders", "fk": "customer_id",
                "agg": "sum", "column": "amount"}},
        }},
        "orders": {"rows": 2000, "columns": {
            "order_id": {"type": "int", "unique": True},
            "customer_id": {"type": "foreign_key",
                            "references": "customers.customer_id"},
            "amount": {"type": "float", "min": 1, "max": 500},
        }},
    },
}


class TestEnvelopeFormat:
    def test_envelope_unwraps_to_real_tables(self):
        schema = misata.from_dict_schema(ENVELOPE_SCHEMA)
        assert sorted(t.name for t in schema.tables) == ["customers", "orders"]
        assert schema.name == "shop"
        assert schema.seed == 7

    def test_references_string_builds_relationship(self):
        schema = misata.from_dict_schema(ENVELOPE_SCHEMA)
        rels = [(r.parent_table, r.child_table, r.parent_key, r.child_key)
                for r in schema.relationships]
        assert ("customers", "orders", "customer_id", "customer_id") in rels

    def test_envelope_generates_with_fk_integrity_and_rollup(self):
        schema = misata.from_dict_schema(ENVELOPE_SCHEMA)
        tables = misata.generate_from_schema(schema)
        assert set(tables) == {"customers", "orders"}
        orders, cust = tables["orders"], tables["customers"]
        assert (~orders["customer_id"].isin(cust["customer_id"])).sum() == 0
        real = orders.groupby("customer_id")["amount"].sum()
        merged = cust.set_index("customer_id").join(real.rename("real"))
        merged["real"] = merged["real"].fillna(0)
        assert ((merged["total_spent"] - merged["real"]).abs() > 0.01).sum() == 0

    def test_envelope_relationships_arrow_string(self):
        schema = misata.from_dict_schema({
            "tables": {
                "users": {"rows": 50, "columns": {
                    "user_id": {"type": "int", "unique": True}}},
                "orders": {"rows": 200, "columns": {
                    "order_id": {"type": "int", "unique": True},
                    "user_id": {"type": "foreign_key"},
                    "amount": {"type": "float", "min": 5, "max": 50}}},
            },
            "relationships": ["users.user_id → orders.user_id"],
        })
        assert len(schema.relationships) == 1
        tables = misata.generate_from_schema(schema)
        orphans = (~tables["orders"]["user_id"]
                   .isin(tables["users"]["user_id"])).sum()
        assert orphans == 0

    def test_flat_format_unchanged(self):
        schema = misata.from_dict_schema({
            "users": {"id": {"type": "integer", "primary_key": True},
                      "email": {"type": "email"}},
            "posts": {"id": {"type": "integer", "primary_key": True},
                      "user_id": {"type": "integer",
                                  "foreign_key": {"table": "users", "column": "id"}}},
        }, row_count=100)
        tables = misata.generate_from_schema(schema)
        assert set(tables) == {"users", "posts"}

    def test_table_literally_named_tables_of_columns_stays_flat(self):
        # A real table named "tables" whose values are column defs must NOT
        # be mistaken for the envelope.
        schema = misata.from_dict_schema({
            "tables": {"id": {"type": "integer", "primary_key": True},
                       "label": {"type": "string"}},
        }, row_count=20)
        assert [t.name for t in schema.tables] == ["tables"]


class TestOracleCurveAwareRowCount:
    def test_oracle_passes_on_conformant_curve_dataset(self):
        schema = misata.from_dict_schema({
            "__outcome_curves__": [{
                "table": "orders", "column": "amount",
                "time_column": "order_date", "time_unit": "month",
                "value_mode": "absolute", "start_date": "2024-01-01",
                "avg_transaction_value": 120.0,
                "curve_points": [{"month": 1, "target_value": 50000.0},
                                 {"month": 12, "target_value": 200000.0}],
            }],
            "orders": {"__rows__": 5000,
                       "order_id": {"type": "integer", "primary_key": True},
                       "amount": {"type": "float", "min": 5, "max": 500},
                       "order_date": {"type": "date"}},
        }, seed=42)
        tables = misata.generate_from_schema(schema)
        oracle = misata.build_oracle_report(tables, schema, seed=42)
        assert oracle["passed"] is True
        check = oracle["guarantees"]["row_count_fulfillment"]["tables"]["orders"]
        assert check["row_count_derived_from_outcome_curve"] is True
        assert check["passed"] is True

    def test_non_curve_table_row_count_still_strict(self):
        schema = misata.from_dict_schema({
            "users": {"__rows__": 100,
                      "id": {"type": "integer", "primary_key": True}},
        }, seed=1)
        tables = misata.generate_from_schema(schema)
        # Drop rows to force a row-count failure.
        tables["users"] = tables["users"].head(50)
        oracle = misata.build_oracle_report(tables, schema, seed=1)
        check = oracle["guarantees"]["row_count_fulfillment"]["tables"]["users"]
        assert check["passed"] is False
        assert "row_count_derived_from_outcome_curve" not in check


class TestAnalyzeGenerationBundle:
    def test_default_runs_all_reports_with_attribute_access(self):
        schema = misata.from_dict_schema({
            "users": {"__rows__": 60,
                      "id": {"type": "integer", "primary_key": True},
                      "age": {"type": "integer", "min": 18, "max": 90}},
        }, seed=2)
        tables = misata.generate_from_schema(schema)
        bundle = misata.analyze_generation(tables, schema)
        assert set(bundle) == {"privacy", "fidelity", "data_card"}
        assert bundle.fidelity.overall_score >= 0
        assert bundle.privacy is bundle.privacy_report
        assert bundle.fidelity is bundle.fidelity_report
        with pytest.raises(AttributeError):
            _ = bundle.nonexistent_report

    def test_explicit_empty_list_runs_nothing(self):
        schema = misata.from_dict_schema({
            "users": {"__rows__": 10,
                      "id": {"type": "integer", "primary_key": True}},
        }, seed=2)
        tables = misata.generate_from_schema(schema)
        assert dict(misata.analyze_generation(tables, schema, reports=[])) == {}


class TestReferenceTableRealism:
    """0.8.1.16: lookup tables get distinct, head-noun-appropriate labels
    (misata.studio field report: property_types.name was Premium/Essential,
    listing_statuses had duplicate labels)."""

    def _gen(self, schema_dict, seed=9):
        return misata.generate_from_schema(misata.from_dict_schema(schema_dict, seed=seed))

    def test_property_types_get_property_labels(self):
        t = self._gen({
            "property_types": {"__rows__": 7,
                "id": {"type": "integer", "primary_key": True},
                "name": {"type": "string"}},
        })["property_types"]
        vals = set(t["name"])
        assert len(vals) == 7, "reference labels must be distinct"
        assert vals & {"House", "Apartment", "Condo", "Townhouse", "Villa",
                       "Studio", "Duplex", "Penthouse", "Cottage", "Land"}, vals

    def test_statuses_tables_distinct_domain_labels(self):
        tables = self._gen({
            "listing_statuses": {"__rows__": 5,
                "id": {"type": "integer", "primary_key": True},
                "status": {"type": "string"}},
            "order_statuses": {"__rows__": 6,
                "id": {"type": "integer", "primary_key": True},
                "status": {"type": "string"}},
        })
        for name in ("listing_statuses", "order_statuses"):
            vals = list(tables[name]["status"])
            assert len(set(vals)) == len(vals), f"{name} labels must be distinct: {vals}"
        assert set(tables["listing_statuses"]["status"]) <= {
            "Active", "Pending", "Sold", "Under Offer", "Withdrawn",
            "Expired", "Coming Soon", "Off Market"}

    def test_lookup_choices_distinct_even_with_probabilities(self):
        t = self._gen({
            "payment_methods": {"__rows__": 4,
                "id": {"type": "integer", "primary_key": True},
                "name": {"type": "categorical",
                         "choices": ["Card", "Cash", "Wire", "PayPal"],
                         "probabilities": [0.7, 0.1, 0.1, 0.1]}},
        })["payment_methods"]
        vals = list(t["name"])
        assert len(set(vals)) == 4, vals


class TestRelativeDefaultStd:
    """0.8.1.16: a mean without std must get a mean-scaled default, not a fixed
    20 (price mean=80000 rendered visually constant and correlation-dead)."""

    def test_float_mean_only_gets_scaled_spread(self):
        t = misata.generate_from_schema(misata.from_dict_schema({
            "listings": {"__rows__": 4000,
                "id": {"type": "integer", "primary_key": True},
                "price": {"type": "float", "mean": 80000}},
        }, seed=3))["listings"]
        rel_spread = t["price"].std() / t["price"].mean()
        assert rel_spread > 0.10, f"relative spread {rel_spread:.4f} too tight"

    def test_correlations_deliver_on_mean_only_column(self):
        t = misata.generate_from_schema(misata.from_dict_schema({
            "listings": {"__rows__": 6000,
                "__correlations__": [
                    {"col_a": "price", "col_b": "sqft", "r": 0.65},
                    {"col_a": "price", "col_b": "distance", "r": -0.45}],
                "id": {"type": "integer", "primary_key": True},
                "price": {"type": "float", "mean": 450000},
                "sqft": {"type": "integer", "min": 400, "max": 5000},
                "distance": {"type": "float", "min": 0.1, "max": 30}},
        }, seed=3))["listings"]
        c = t[["price", "sqft", "distance"]].corr()
        assert abs(c.loc["price", "sqft"] - 0.65) < 0.08
        assert abs(c.loc["price", "distance"] + 0.45) < 0.08

    def test_explicit_std_still_wins(self):
        t = misata.generate_from_schema(misata.from_dict_schema({
            "x": {"__rows__": 3000,
                "id": {"type": "integer", "primary_key": True},
                "v": {"type": "float", "mean": 1000, "std": 10}},
        }, seed=4))["x"]
        assert 8 < t["v"].std() < 12


class TestB2BMarketplaceFieldReport:
    """0.8.1.17: fixes from the B2B-marketplace studio field report —
    buyer_segments got person names, supplier_sizes got company names,
    annual_gmv was constant 50000, and hq_city sat in the wrong hq_country."""

    def test_segments_and_sizes_get_labels_not_names(self):
        tables = misata.generate_from_schema(misata.from_dict_schema({
            "buyer_segments": {"__rows__": 5,
                "id": {"type": "integer", "primary_key": True},
                "name": {"type": "string"}},
            "supplier_sizes": {"__rows__": 3,
                "id": {"type": "integer", "primary_key": True},
                "name": {"type": "string"}},
            "plan_tiers": {"__rows__": 4,
                "id": {"type": "integer", "primary_key": True},
                "name": {"type": "string"}},
        }, seed=11))
        segs = set(tables["buyer_segments"]["name"])
        assert segs <= {"Enterprise", "Mid-Market", "SMB", "Startup",
                        "Individual", "Government", "Non-Profit", "Education"}, segs
        sizes = set(tables["supplier_sizes"]["name"])
        assert sizes <= {"Micro", "Small", "Medium", "Large", "Enterprise"}, sizes
        tiers = set(tables["plan_tiers"]["name"])
        assert tiers <= {"Free", "Basic", "Pro", "Business", "Enterprise"}, tiers
        for tname in ("buyer_segments", "supplier_sizes", "plan_tiers"):
            vals = list(tables[tname].iloc[:, 1])
            assert len(set(vals)) == len(vals), f"{tname} labels must be distinct"

    def test_llm_spread_sanitizer(self):
        from misata.llm_parser import _sanitize_numeric_spread
        # min == max money column widens
        p = _sanitize_numeric_spread("annual_gmv", "float", {"min": 50000, "max": 50000})
        assert p["min"] < 50000 < p["max"]
        # degenerate std gets rescaled
        p = _sanitize_numeric_spread("annual_gmv", "float", {"mean": 50000, "std": 5})
        assert p["std"] == 12500.0
        # missing std gets mean-scaled default
        p = _sanitize_numeric_spread("order_value", "float", {"mean": 1200})
        assert p["std"] == 300.0
        # non-money and legit specs untouched
        assert _sanitize_numeric_spread("year_built", "int", {"mean": 1985, "std": 20}) \
            == {"mean": 1985, "std": 20}
        assert _sanitize_numeric_spread("price", "float", {"mean": 100, "std": 30}) \
            == {"mean": 100, "std": 30}

    def test_city_belongs_to_row_country(self):
        from misata.realism import COUNTRY_CITIES
        t = misata.generate_from_schema(misata.from_dict_schema({
            "suppliers": {"__rows__": 200,
                "id": {"type": "integer", "primary_key": True},
                "hq_city": {"type": "string"},
                "hq_country": {"type": "string"}},
        }, seed=12))["suppliers"]
        bad = sum(
            1 for _, r in t.iterrows()
            if str(r["hq_country"]) in COUNTRY_CITIES
            and str(r["hq_city"]) not in COUNTRY_CITIES[str(r["hq_country"])]
        )
        assert bad == 0, f"{bad} rows have a city outside their country"


class TestHospitalFieldReport:
    """0.8.1.18: clinical columns must never hold business filler, and a
    hospital's departments are clinical (studio field report)."""

    def test_clinical_columns_get_medical_values(self):
        from misata.vocab_seeds import (
            BLOOD_TYPES, COMMON_DIAGNOSES, LAB_TESTS, MEDICATIONS,
            MEDICAL_DEPARTMENTS, MEDICAL_SPECIALTIES,
        )
        t = misata.generate_from_schema(misata.from_dict_schema({
            "__domain__": "healthcare",
            "departments": {"__rows__": 6,
                "id": {"type": "integer", "primary_key": True},
                "name": {"type": "string"}},
            "doctors": {"__rows__": 5,
                "id": {"type": "integer", "primary_key": True},
                "specialty": {"type": "string"}},
            "patients": {"__rows__": 5,
                "id": {"type": "integer", "primary_key": True},
                "blood_type": {"type": "string"}},
            "admissions": {"__rows__": 5,
                "id": {"type": "integer", "primary_key": True},
                "diagnosis": {"type": "string"}},
            "lab_results": {"__rows__": 5,
                "id": {"type": "integer", "primary_key": True},
                "test_name": {"type": "string"}},
            "prescriptions": {"__rows__": 5,
                "id": {"type": "integer", "primary_key": True},
                "medication_name": {"type": "string"},
                "dosage": {"type": "string"}},
        }, seed=5))
        assert set(t["departments"]["name"]) <= set(MEDICAL_DEPARTMENTS)
        assert set(t["doctors"]["specialty"]) <= set(MEDICAL_SPECIALTIES)
        assert set(t["patients"]["blood_type"]) <= set(BLOOD_TYPES)
        assert set(t["admissions"]["diagnosis"]) <= set(COMMON_DIAGNOSES)
        assert set(t["lab_results"]["test_name"]) <= set(LAB_TESTS)
        assert set(t["prescriptions"]["medication_name"]) <= set(MEDICATIONS)
        assert all(" mg" in d for d in t["prescriptions"]["dosage"])


class TestMultiplierCurveDropped:
    """0.8.1.19: an LLM emitting surge multipliers (0.92–1.15) as absolute
    fare totals must have the curve dropped, not fail generation with 12
    infeasibility errors (ride-share field report)."""

    def test_multiplier_shaped_curve_is_dropped(self):
        import warnings as w
        from misata.llm_parser import LLMSchemaGenerator
        gen = LLMSchemaGenerator.__new__(LLMSchemaGenerator)  # skip API init
        schema_dict = {
            "name": "rides",
            "tables": [{"name": "trips", "row_count": 100}],
            "columns": {"trips": [
                {"name": "id", "type": "int", "unique": True},
                {"name": "fare_amount", "type": "float",
                 "distribution_params": {"min": 3.5, "max": 80}},
                {"name": "trip_date", "type": "date"},
            ]},
            "outcome_curves": [{
                "table": "trips", "column": "fare_amount",
                "time_column": "trip_date", "time_unit": "month",
                "value_mode": "absolute",
                "curve_points": [{"month": i + 1, "target_value": v}
                                 for i, v in enumerate(
                                     [0.92, 0.88, 0.95, 0.98, 1.02, 1.06])],
            }],
        }
        with w.catch_warnings(record=True) as caught:
            w.simplefilter("always")
            config = gen._parse_schema(schema_dict)
        assert config.outcome_curves == []
        assert any("multiplier" in str(x.message) for x in caught)
        # And generation now succeeds instead of raising 12 issues.
        tables = misata.generate_from_schema(config)
        assert len(tables["trips"]) > 0


class TestCardinalityRealism:
    """0.8.1.21: fact tables (2+ FKs) must not share their parents' row count
    (10k drivers / 10k riders / 10k trips field report)."""

    def test_uniform_rows_scale_fact_table(self):
        import warnings as w
        from misata.llm_parser import LLMSchemaGenerator
        gen = LLMSchemaGenerator.__new__(LLMSchemaGenerator)
        sd = {
            "name": "rides",
            "tables": [{"name": "drivers", "row_count": 1000},
                       {"name": "riders", "row_count": 1000},
                       {"name": "trips", "row_count": 1000}],
            "columns": {
                "drivers": [{"name": "id", "type": "int", "unique": True}],
                "riders": [{"name": "id", "type": "int", "unique": True}],
                "trips": [
                    {"name": "id", "type": "int", "unique": True},
                    {"name": "driver_id", "type": "foreign_key"},
                    {"name": "rider_id", "type": "foreign_key"},
                ],
            },
            "relationships": [
                {"parent_table": "drivers", "child_table": "trips",
                 "parent_key": "id", "child_key": "driver_id"},
                {"parent_table": "riders", "child_table": "trips",
                 "parent_key": "id", "child_key": "rider_id"},
            ],
        }
        with w.catch_warnings():
            w.simplefilter("ignore")
            config = gen._parse_schema(sd)
        rows = {t.name: t.row_count for t in config.tables}
        assert rows["trips"] == 10000, rows
        assert rows["drivers"] == 1000 and rows["riders"] == 1000
