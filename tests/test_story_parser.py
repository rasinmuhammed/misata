"""Tests for story-driven exact outcome curve extraction."""

import pandas as pd
import pytest

from misata.simulator import DataSimulator
from misata.story_parser import StoryParser
from misata.validation import validate_data


class TestFintechDomain:
    def test_produces_three_tables(self):
        parser = StoryParser()
        schema = parser.parse("A fintech startup with 100 users and 500 transactions.", default_rows=100)
        names = {t.name for t in schema.tables}
        assert names == {"customers", "accounts", "transactions"}

    def test_domain_is_fintech(self):
        parser = StoryParser()
        schema = parser.parse("A payments company with 200 customers.", default_rows=200)
        assert schema.domain == "fintech"

    def test_fraud_rate_column_present(self):
        parser = StoryParser()
        schema = parser.parse("A banking fraud detection dataset.", default_rows=100)
        tx_cols = {c.name for c in schema.columns["transactions"]}
        assert "is_fraud" in tx_cols

    def test_relationships_customers_to_accounts_to_transactions(self):
        parser = StoryParser()
        schema = parser.parse("A fintech company with loans and credit.", default_rows=100)
        rels = {(r.parent_table, r.child_table) for r in schema.relationships}
        assert ("customers", "accounts") in rels
        assert ("accounts", "transactions") in rels

    def test_credit_score_column_bounded(self):
        parser = StoryParser()
        schema = parser.parse("A credit scoring fintech with 100 customers.", default_rows=100)
        customer_cols = {c.name: c for c in schema.columns["customers"]}
        assert "credit_score" in customer_cols
        params = customer_cols["credit_score"].distribution_params
        assert params.get("min", 0) >= 300
        assert params.get("max", 999) <= 850


class TestHealthcareDomain:
    def test_produces_three_tables(self):
        parser = StoryParser()
        schema = parser.parse("A hospital with 500 patients and doctors.", default_rows=500)
        names = {t.name for t in schema.tables}
        assert names == {"doctors", "patients", "appointments"}

    def test_domain_is_healthcare(self):
        parser = StoryParser()
        schema = parser.parse("A clinic managing patient appointments.", default_rows=100)
        assert schema.domain == "healthcare"

    def test_blood_type_probabilities_sum_to_one(self):
        parser = StoryParser()
        schema = parser.parse("A healthcare system with 200 patients.", default_rows=200)
        patient_cols = {c.name: c for c in schema.columns["patients"]}
        probs = patient_cols["blood_type"].distribution_params["probabilities"]
        assert abs(sum(probs) - 1.0) < 1e-6

    def test_appointments_has_two_foreign_keys(self):
        parser = StoryParser()
        schema = parser.parse("A medical appointment booking system.", default_rows=100)
        appt_fks = [c for c in schema.columns["appointments"] if c.type == "foreign_key"]
        assert len(appt_fks) == 2

    def test_doctor_count_scales_with_patient_count(self):
        parser = StoryParser()
        schema = parser.parse("A hospital with 1000 patients.", default_rows=1000)
        doctor_table = next(t for t in schema.tables if t.name == "doctors")
        patient_table = next(t for t in schema.tables if t.name == "patients")
        assert doctor_table.row_count < patient_table.row_count


class TestMarketplaceDomain:
    def test_produces_four_tables(self):
        parser = StoryParser()
        schema = parser.parse("A marketplace platform with sellers, buyers, and listings.", default_rows=200)
        names = {t.name for t in schema.tables}
        assert names == {"sellers", "buyers", "listings", "orders"}

    def test_domain_is_marketplace(self):
        parser = StoryParser()
        schema = parser.parse("A gig economy freelance platform.", default_rows=100)
        assert schema.domain == "marketplace"

    def test_seller_rating_uses_beta_distribution(self):
        parser = StoryParser()
        schema = parser.parse("A marketplace with 100 sellers.", default_rows=100)
        seller_cols = {c.name: c for c in schema.columns["sellers"]}
        assert seller_cols["rating"].distribution_params.get("distribution") == "beta"

    def test_three_relationships_present(self):
        parser = StoryParser()
        schema = parser.parse("A marketplace platform with 50 users.", default_rows=50)
        assert len(schema.relationships) == 3

    def test_listing_category_uses_zipf(self):
        parser = StoryParser()
        schema = parser.parse("An online marketplace with product listings.", default_rows=100)
        listing_cols = {c.name: c for c in schema.columns["listings"]}
        assert listing_cols["category"].distribution_params.get("sampling") == "zipf"


class TestLogisticsDomain:
    def test_produces_four_tables(self):
        parser = StoryParser()
        schema = parser.parse("A logistics company with drivers and shipments.", default_rows=200)
        names = {t.name for t in schema.tables}
        assert names == {"drivers", "vehicles", "routes", "shipments"}

    def test_domain_is_logistics(self):
        parser = StoryParser()
        schema = parser.parse("A shipping and delivery fleet management system.", default_rows=100)
        assert schema.domain == "logistics"

    def test_distance_is_lognormal(self):
        parser = StoryParser()
        schema = parser.parse("A logistics dataset with routes and delivery.", default_rows=100)
        route_cols = {c.name: c for c in schema.columns["routes"]}
        assert route_cols["distance_km"].distribution_params.get("distribution") == "lognormal"

    def test_three_relationships_present(self):
        parser = StoryParser()
        schema = parser.parse("A warehouse supply chain with drivers.", default_rows=50)
        assert len(schema.relationships) == 3

    def test_vehicle_type_uses_zipf(self):
        parser = StoryParser()
        schema = parser.parse("A fleet management system for logistics.", default_rows=100)
        vehicle_cols = {c.name: c for c in schema.columns["vehicles"]}
        assert vehicle_cols["vehicle_type"].distribution_params.get("sampling") == "zipf"


class TestStoryParserOutcomeCurves:
    """Tests for rule-based story parsing into exact target curves."""

    def test_extracts_absolute_monthly_revenue_curve(self):
        """Revenue stories with anchors should become exact monthly targets."""
        parser = StoryParser()

        schema = parser.parse(
            "An ecommerce company with 50 customers where revenue rises from 5k in Jan to 20k in Dec with a dip in September",
            default_rows=100,
        )

        assert len(schema.outcome_curves) == 1
        curve = schema.outcome_curves[0]

        assert curve.table == "orders"
        assert curve.column == "amount"
        assert curve.value_mode == "absolute"
        assert len(curve.curve_points) == 12
        assert curve.curve_points[0]["target_value"] == pytest.approx(5000.0)
        assert curve.curve_points[11]["target_value"] == pytest.approx(20000.0)
        assert curve.curve_points[8]["target_value"] < curve.curve_points[7]["target_value"]

    def test_story_drives_exact_generated_monthly_totals(self):
        """Parsed story constraints should survive end-to-end generation."""
        parser = StoryParser()
        schema = parser.parse(
            "An ecommerce company with 50 customers where revenue rises from 5k in Jan to 20k in Dec with a dip in September",
            default_rows=100,
        )

        simulator = DataSimulator(schema)
        tables = {}
        for table_name, batch in simulator.generate_all():
            if table_name in tables:
                tables[table_name] = pd.concat([tables[table_name], batch], ignore_index=True)
            else:
                tables[table_name] = batch

        orders = tables["orders"]
        monthly = (
            orders.assign(month=pd.to_datetime(orders["order_date"]).dt.month)
            .groupby("month")["amount"]
            .sum()
        )
        targets = {point["month"]: point["target_value"] for point in schema.outcome_curves[0].curve_points}

        assert monthly.loc[1] == pytest.approx(targets[1], abs=0.01)
        assert monthly.loc[9] == pytest.approx(targets[9], abs=0.01)
        assert monthly.loc[12] == pytest.approx(targets[12], abs=0.01)

        report = validate_data(tables, schema)
        assert not report.has_errors


class TestQualitativeOnlyCurves:
    """Qualitative modifiers alone (no numeric anchors) must still produce curves."""

    def test_qualitative_only_produces_curve(self):
        parser = StoryParser()
        schema = parser.parse(
            "A SaaS company with 10K users. Sales peak in November and dip in March.",
            default_rows=1000,
        )
        assert len(schema.outcome_curves) == 1

    def test_peak_month_greater_than_dip_month(self):
        parser = StoryParser()
        schema = parser.parse(
            "An ecommerce company. Sales peak in November and dip in March.",
            default_rows=1000,
        )
        curve = schema.outcome_curves[0]
        pts = {pt["month"]: pt["target_value"] for pt in curve.curve_points}
        assert pts[11] > pts[3]

    def test_one_anchor_plus_qualitative_produces_curve(self):
        parser = StoryParser()
        schema = parser.parse(
            "Revenue at $100k in January, with a spike in November.",
            default_rows=1000,
        )
        assert len(schema.outcome_curves) == 1
        curve = schema.outcome_curves[0]
        pts = {pt["month"]: pt["target_value"] for pt in curve.curve_points}
        assert pts[1] == pytest.approx(100_000.0)
        assert pts[11] > pts[1]

    def test_numeric_anchors_are_pinned_exactly(self):
        """Explicit numeric anchors must not be overwritten by interpolation."""
        parser = StoryParser()
        schema = parser.parse(
            "Revenue from $50k in January to $200k in December with a dip in September.",
            default_rows=1000,
        )
        curve = schema.outcome_curves[0]
        pts = {pt["month"]: pt["target_value"] for pt in curve.curve_points}
        assert pts[1] == pytest.approx(50_000.0)
        assert pts[12] == pytest.approx(200_000.0)
        assert pts[9] < pts[8]
