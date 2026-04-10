"""Tests for story-driven exact outcome curve extraction."""

import pandas as pd
import pytest

from misata.simulator import DataSimulator
from misata.story_parser import StoryParser
from misata.validation import validate_data


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
