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


class TestRideShareFieldReportV3:
    """0.8.1.22: fuzzy head matching for reference pools + vehicle coherence
    (ride-share field report v3: surge_pricing_event_types got Team/Advanced,
    vehicles.model and license_plate got marketing sentences)."""

    def _gen(self, schema_dict, seed=11):
        return misata.generate_from_schema(misata.from_dict_schema(schema_dict, seed=seed))

    def test_surge_pricing_event_types_use_surge_pool(self):
        t = self._gen({
            "surge_pricing_event_types": {"__rows__": 6,
                "id": {"type": "integer", "primary_key": True},
                "event_type": {"type": "string"}},
        })["surge_pricing_event_types"]
        vals = set(t["event_type"])
        assert vals <= {"High Demand", "Concert", "Sporting Event", "Bad Weather",
                        "Rush Hour", "Airport Peak", "Holiday", "Festival"}, vals

    def test_driver_statuses_use_driver_pool(self):
        t = self._gen({
            "driver_statuses": {"__rows__": 5,
                "id": {"type": "integer", "primary_key": True},
                "status": {"type": "string"}},
        })["driver_statuses"]
        vals = set(t["status"])
        assert vals <= {"Online", "Offline", "On Trip", "Available", "On Break",
                        "Pending Approval", "Suspended", "Deactivated"}, vals

    def test_vehicle_model_coheres_with_make_and_plate_is_code(self):
        import re as _re
        t = self._gen({
            "vehicles": {"__rows__": 200,
                "id": {"type": "integer", "primary_key": True},
                "make": {"type": "categorical",
                         "choices": ["Toyota", "Honda", "Tesla"]},
                "model": {"type": "string"},
                "license_plate": {"type": "string"}},
        })["vehicles"]
        from misata.vocab_seeds import VEHICLE_MODELS_BY_MAKE
        ok = sum(
            str(m) in VEHICLE_MODELS_BY_MAKE.get(str(mk).lower(), [])
            for mk, m in zip(t["make"], t["model"])
        )
        assert ok / len(t) > 0.9, f"only {ok}/{len(t)} models match their make"
        assert all(_re.fullmatch(r"[A-Z]{3}[- ]?\d{4}|\d[A-Z]{3}-\d{3}|\d{3}-[A-Z]{4}", str(p))
                   for p in t["license_plate"]), list(t["license_plate"][:5])

    def test_tier_fees_monotonic_with_rank(self):
        t = self._gen({
            "rider_membership_tiers": {"__rows__": 4,
                "id": {"type": "integer", "primary_key": True},
                "tier": {"type": "string"},
                "monthly_fee": {"type": "float", "min": 0, "max": 200}},
        })["rider_membership_tiers"]
        order = ["Free", "Basic", "Bronze", "Silver", "Gold", "Platinum", "Diamond", "Elite"]
        ranked = sorted(zip(t["tier"], t["monthly_fee"]), key=lambda p: order.index(p[0]))
        fees = [f for _, f in ranked]
        assert fees == sorted(fees), ranked

    def test_plan_price_and_limit_monotonic(self):
        t = self._gen({
            "subscription_plans": {"__rows__": 5,
                "id": {"type": "integer", "primary_key": True},
                "name": {"type": "categorical",
                         "choices": ["Free", "Basic", "Pro", "Business", "Enterprise"]},
                "price": {"type": "float", "min": 0, "max": 100},
                "api_limit": {"type": "integer", "min": 100, "max": 100000}},
        })["subscription_plans"]
        order = ["Free", "Basic", "Pro", "Business", "Enterprise"]
        ranked = sorted(zip(t["name"], t["price"], t["api_limit"]),
                        key=lambda p: order.index(p[0]))
        assert [p for _, p, _ in ranked] == sorted(p for _, p, _ in ranked), ranked
        assert [l for _, _, l in ranked] == sorted(l for _, _, l in ranked), ranked

    def test_temporal_gaps_compressed_and_duration_reconciled(self):
        import pandas as pd
        t = self._gen({
            "trips": {"__rows__": 800,
                "id": {"type": "integer", "primary_key": True},
                "request_time": {"type": "datetime", "min": "2025-01-01", "max": "2025-12-31"},
                "pickup_time": {"type": "datetime", "min": "2025-01-01", "max": "2025-12-31"},
                "dropoff_time": {"type": "datetime", "min": "2025-01-01", "max": "2025-12-31"},
                "trip_duration_minutes": {"type": "integer", "min": 5, "max": 55}},
        })["trips"]
        req = pd.to_datetime(t["request_time"])
        pu = pd.to_datetime(t["pickup_time"])
        do = pd.to_datetime(t["dropoff_time"])
        assert ((req <= pu) & (pu <= do)).all()
        wait_min = (pu - req).dt.total_seconds() / 60
        assert wait_min.max() <= 181, wait_min.max()
        ride_min = (do - pu).dt.total_seconds() / 60
        assert (abs(ride_min - t["trip_duration_minutes"]) < 0.02).all()

    def test_date_scale_spans_not_compressed(self):
        import pandas as pd
        t = self._gen({
            "leases": {"__rows__": 400,
                "id": {"type": "integer", "primary_key": True},
                "start_date": {"type": "date", "min": "2023-01-01", "max": "2024-12-31"},
                "end_date": {"type": "date", "min": "2023-06-01", "max": "2026-12-31"}},
        })["leases"]
        days = (pd.to_datetime(t["end_date"]) - pd.to_datetime(t["start_date"])).dt.days
        assert days.median() > 90, "lease spans must not be event-compressed"

    def test_fare_amount_derived_from_base_and_multiplier(self):
        import numpy as np
        t = self._gen({
            "trips": {"__rows__": 500,
                "id": {"type": "integer", "primary_key": True},
                "base_fare": {"type": "float", "min": 2.5, "max": 25},
                "surge_multiplier": {"type": "categorical",
                                     "choices": [1.0, 1.2, 1.5, 2.0, 3.0]},
                "fare_amount": {"type": "float", "min": 2, "max": 80},
                "tip_amount": {"type": "float", "min": 0, "max": 15}},
        })["trips"]
        calc = np.round(t["base_fare"].astype(float) * t["surge_multiplier"].astype(float), 2)
        assert (abs(t["fare_amount"] - calc) < 0.011).all()
        assert t["tip_amount"].std() > 1, "unrelated money columns must not be rewritten"


class TestSchemaContractPhase2:
    """0.8.1.22: the LLM value contract — schema-embedded vocabulary block,
    nested-columns hoist, state-machine FK label→id + inline_data extension,
    depends_on FK-id key coercion, lifetime_* rollup inference."""

    def _parse(self, sd):
        import warnings as w
        from misata.llm_parser import LLMSchemaGenerator
        gen = LLMSchemaGenerator.__new__(LLMSchemaGenerator)
        with w.catch_warnings():
            w.simplefilter("ignore")
            return gen._parse_schema(sd)

    def test_schema_vocabulary_block_feeds_text_columns(self):
        cfg = self._parse({
            "name": "Falconry",
            "vocabulary": {"species": ["Peregrine Falcon", "Harris Hawk",
                                       "Gyrfalcon", "Saker Falcon", "Goshawk"]},
            "tables": [{"name": "birds", "row_count": 200}],
            "columns": {"birds": [
                {"name": "id", "type": "int", "unique": True},
                {"name": "species", "type": "text"}]},
        })
        assert cfg.vocabularies and "species" in cfg.vocabularies
        t = misata.generate_from_schema(cfg)["birds"]
        assert set(t["species"].unique()) <= set(cfg.vocabularies["species"])

    def test_nested_table_columns_are_hoisted(self):
        cfg = self._parse({
            "name": "x",
            "tables": [{"name": "widgets", "row_count": 50, "columns": [
                {"name": "id", "type": "int", "unique": True},
                {"name": "size_cm", "type": "float", "distribution_params": {"min": 1, "max": 9}}]}],
        })
        assert len(cfg.columns.get("widgets", [])) == 2

    def test_state_machine_fk_label_resolves_and_extends_lookup(self):
        cfg = self._parse({
            "name": "rides",
            "tables": [
                {"name": "trip_statuses", "is_reference": True,
                 "inline_data": [{"id": 1, "status": "Requested"},
                                 {"id": 2, "status": "Completed"}]},
                {"name": "trips", "row_count": 2000,
                 "state_machine": {"state_column": "status_id",
                    "initial_state": "Requested",
                    "transitions": {"Requested": {"Completed": 0.9, "Cancelled": 0.1}}}},
            ],
            "columns": {"trips": [{"name": "id", "type": "int", "unique": True},
                                  {"name": "status_id", "type": "foreign_key"}]},
            "relationships": [{"parent_table": "trip_statuses", "child_table": "trips",
                               "parent_key": "id", "child_key": "status_id"}],
        })
        t = misata.generate_from_schema(cfg)
        trips, statuses = t["trips"], t["trip_statuses"]
        assert "Cancelled" in set(statuses["status"]), "missing state must be added"
        assert (~trips["status_id"].isin(statuses["id"])).sum() == 0, "no orphan FKs"
        labels = trips["status_id"].map(dict(zip(statuses["id"], statuses["status"])))
        assert {"Completed", "Cancelled"} <= set(labels.unique())

    def test_depends_on_with_fk_id_keys_coerces(self):
        cfg = self._parse({
            "name": "x",
            "tables": [
                {"name": "techniques", "is_reference": True,
                 "inline_data": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]},
                {"name": "sessions", "row_count": 4000},
            ],
            "columns": {"sessions": [
                {"name": "id", "type": "int", "unique": True},
                {"name": "technique_id", "type": "foreign_key"},
                {"name": "success", "type": "boolean",
                 "distribution_params": {"depends_on": "technique_id",
                                         "mapping": {"1": 0.9, "2": 0.3}}}]},
            "relationships": [{"parent_table": "techniques", "child_table": "sessions",
                               "parent_key": "id", "child_key": "technique_id"}],
        })
        s = misata.generate_from_schema(cfg)["sessions"]
        by = s.groupby("technique_id")["success"].mean()
        assert by.loc[1] > 0.75 and by.loc[2] < 0.45, by.to_dict()

    def test_lifetime_count_rollup_inferred(self):
        cfg = self._parse({
            "name": "x",
            "tables": [
                {"name": "riders", "row_count": 300},
                {"name": "trips", "row_count": 3000},
            ],
            "columns": {
                "riders": [{"name": "id", "type": "int", "unique": True},
                           {"name": "lifetime_trips", "type": "int"}],
                "trips": [{"name": "id", "type": "int", "unique": True},
                          {"name": "rider_id", "type": "foreign_key"}]},
            "relationships": [{"parent_table": "riders", "child_table": "trips",
                               "parent_key": "id", "child_key": "rider_id"}],
        })
        t = misata.generate_from_schema(cfg)
        real = t["trips"].groupby("rider_id").size()
        merged = t["riders"].set_index("id")
        err = (merged["lifetime_trips"] - real.reindex(merged.index).fillna(0)).abs().max()
        assert err == 0, f"lifetime_trips must equal real trip count (max err {err})"

    def test_label_column_without_choices_warns(self):
        import warnings as w
        from misata.llm_parser import LLMSchemaGenerator
        gen = LLMSchemaGenerator.__new__(LLMSchemaGenerator)
        with w.catch_warnings(record=True) as ws:
            w.simplefilter("always")
            gen._parse_schema({
                "name": "x",
                "tables": [{"name": "repairs", "row_count": 100}],
                "columns": {"repairs": [
                    {"name": "id", "type": "int", "unique": True},
                    {"name": "repair_type", "type": "text"}]},
            })
        assert any("label column" in str(x.message) for x in ws)


class TestReleaseGate0_8_1_22:
    """0.8.1.22: engine hardening surfaced by the 5-domain release-gate audit —
    lognormal log-space mean disambiguation, malformed-choice sanitizer,
    dispatch temporal ordering."""

    def _parse(self, sd):
        import warnings as w
        from misata.llm_parser import LLMSchemaGenerator
        gen = LLMSchemaGenerator.__new__(LLMSchemaGenerator)
        with w.catch_warnings():
            w.simplefilter("ignore")
            return gen._parse_schema(sd)

    def test_lognormal_mu_sigma_helper(self):
        from misata.simulator import _lognormal_mu_sigma
        import math
        mu, sigma = _lognormal_mu_sigma(12.5, 0.6, 80000)
        assert mu == 12.5 and sigma == 0.6
        assert math.exp(mu) > 80000
        mu2, sigma2 = _lognormal_mu_sigma(100.0, 40.0, None)
        assert abs(math.exp(mu2) - 100.0) < 20

    def test_lognormal_small_mean_large_min_is_log_space(self):
        # The canonical real-estate example: mean 12.5, min 80000 used to clip
        # every row onto 80000. mean must be read as log-space mu.
        t = misata.generate_from_schema(misata.from_dict_schema({
            "listings": {"__rows__": 5000,
                "id": {"type": "integer", "primary_key": True},
                "price": {"type": "float", "distribution": "lognormal",
                          "mean": 12.5, "std": 0.6, "min": 80000, "decimals": 0}},
        }, seed=3))["listings"]
        p = t["price"]
        assert p.nunique() > 1000, "prices must vary, not clip to min"
        assert 150_000 < p.median() < 500_000, f"median {p.median()}"

    def test_arithmetic_lognormal_still_works(self):
        # A normal arithmetic-mean lognormal (mean 100, no huge min) is untouched.
        t = misata.generate_from_schema(misata.from_dict_schema({
            "x": {"__rows__": 5000, "id": {"type": "integer", "primary_key": True},
                  "v": {"type": "float", "distribution": "lognormal",
                        "mean": 100, "std": 40}},
        }, seed=4))["x"]
        assert 70 < t["v"].median() < 130, t["v"].median()

    def test_malformed_concatenated_choices_do_not_crash(self):
        # LLMs sometimes emit choices/probabilities collapsed into one token.
        cfg = self._parse({
            "name": "x",
            "tables": [{"name": "listings", "row_count": 500}],
            "columns": {"listings": [
                {"name": "id", "type": "int", "unique": True},
                {"name": "bedrooms", "type": "int", "distribution_params": {
                    "distribution": "categorical", "choices": [123456],
                    "probabilities": ["0.050.200.350.250.100.05"]}},
                {"name": "bathrooms", "type": "float", "distribution_params": {
                    "distribution": "categorical", "choices": ["1.01.52.02.53.0"],
                    "probabilities": ["0.150.250.350.200.05"]}}]},
        })
        t = misata.generate_from_schema(cfg)["listings"]  # must not raise
        assert t["bedrooms"].between(1, 6).all()
        assert t["bathrooms"].between(1.0, 3.5).all()

    def test_dispatch_arrival_chain_ordered(self):
        import pandas as pd
        t = misata.generate_from_schema(misata.from_dict_schema({
            "missions": {"__rows__": 600,
                "id": {"type": "integer", "primary_key": True},
                "dispatch_date": {"type": "datetime", "min": "2024-01-01", "max": "2025-12-31"},
                "arrival_date": {"type": "datetime", "min": "2024-01-01", "max": "2025-12-31"}},
        }, seed=5))["missions"]
        assert (pd.to_datetime(t["arrival_date"]) >= pd.to_datetime(t["dispatch_date"])).all()


class TestFraudFieldReportEngine:
    """0.8.1.26: engine-side fixes from the credit-card fraud field report —
    unsupported regex patterns fall back to semantics, denormalized parent
    attributes agree, merchant/transaction pools, real MCC codes."""

    def _gen(self, sd, seed=9):
        return misata.generate_from_schema(misata.from_dict_schema(sd, seed=seed))

    def test_unsupported_pattern_falls_back_to_semantic(self):
        t = self._gen({
            "merchants": {"__rows__": 100,
                "id": {"type": "integer", "primary_key": True},
                "merchant_name": {"type": "text",
                                  "pattern": "Et+( Sj+){1,2}"}},
        })["merchants"]
        import re as _re
        leaked = t["merchant_name"].astype(str).apply(
            lambda v: bool(_re.search(r"[+{}()\\]", v))).sum()
        assert leaked == 0, list(t["merchant_name"][:3])

    def test_supported_pattern_still_expands(self):
        import re as _re
        t = self._gen({
            "orders": {"__rows__": 50,
                "id": {"type": "integer", "primary_key": True},
                "ref": {"type": "text", "pattern": "ORD-\\d{5}"}},
        })["orders"]
        assert all(_re.fullmatch(r"ORD-\d{5}", str(v)) for v in t["ref"])

    def test_denormalized_parent_column_agrees(self):
        tables = self._gen({
            "merchants": {"__rows__": 40,
                "id": {"type": "integer", "primary_key": True},
                "merchant_city": {"type": "text", "text_type": "city"}},
            "transactions": {"__rows__": 2000,
                "id": {"type": "integer", "primary_key": True},
                "merchant_id": {"type": "integer",
                                "foreign_key": {"table": "merchants", "column": "id"}},
                "merchant_city": {"type": "text", "text_type": "city"}},
        })
        tx, m = tables["transactions"], tables["merchants"]
        j = tx.merge(m, left_on="merchant_id", right_on="id", suffixes=("", "_p"))
        agree = (j["merchant_city"] == j["merchant_city_p"]).mean()
        assert agree > 0.99, f"only {agree:.1%} agree"

    def test_merchant_categories_and_transaction_lookups(self):
        tables = self._gen({
            "merchant_categories": {"__rows__": 8,
                "id": {"type": "integer", "primary_key": True},
                "name": {"type": "string"}},
            "transaction_channels": {"__rows__": 5,
                "id": {"type": "integer", "primary_key": True},
                "name": {"type": "string"}},
            "transaction_statuses": {"__rows__": 5,
                "id": {"type": "integer", "primary_key": True},
                "status": {"type": "string"}},
        })
        assert set(tables["merchant_categories"]["name"]) <= {
            "Grocery", "Restaurants & Dining", "Fuel & Convenience",
            "Travel & Airlines", "Electronics", "Pharmacy & Health",
            "Entertainment", "Apparel & Accessories", "Utilities & Telecom",
            "Digital Goods"}
        assert set(tables["transaction_channels"]["name"]) <= {
            "Online", "In-store", "Contactless", "Phone Order",
            "Recurring", "ATM", "Mobile Wallet"}
        assert set(tables["transaction_statuses"]["status"]) <= {
            "Approved", "Declined", "Pending", "Settled",
            "Reversed", "Refunded", "Flagged for Review"}

    def test_mcc_codes_are_real(self):
        t = self._gen({
            "merchants": {"__rows__": 200,
                "id": {"type": "integer", "primary_key": True},
                "mcc_code": {"type": "string"}},
        })["merchants"]
        real = {"5411", "5812", "5814", "5541", "4111", "5912", "5999",
                "5311", "7011", "5732", "4899", "5942", "5651", "5945",
                "4121", "5813", "5921", "7832", "8011", "8062", "4816",
                "5967", "6011", "4814", "5122"}
        assert set(t["mcc_code"].astype(str)) <= real
