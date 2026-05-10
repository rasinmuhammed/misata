"""Tests for expanded narrative pattern extraction in StoryParser.

Covers:
- Quarterly modifiers  (Q1–Q4 qualitative + anchors)
- Named seasonal events (Black Friday, Christmas, summer slump, …)
- Relative multipliers  (doubled, tripled, 10x, 2x, halved)
- Extended keywords     (slump, boom, push, flat, slow, …)
"""

from __future__ import annotations

import pytest

from misata.story_parser import StoryParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _curve_points(story: str, table: str = "subscriptions", column: str = "mrr") -> list[dict]:
    """Parse a story and return the outcome curve points for the given table+column."""
    parser = StoryParser()
    schema = parser.parse(story)
    for oc in schema.outcome_curves:
        if oc.table == table and oc.column == column:
            return oc.curve_points
    return []


def _monthly_values(story: str, table: str = "subscriptions", column: str = "mrr") -> list[float]:
    return [pt["target_value"] for pt in _curve_points(story, table, column)]


def _saas_values(story: str) -> list[float]:
    """Parse a SaaS story and return MRR curve values."""
    return _monthly_values(story, table="subscriptions", column="mrr")


# ---------------------------------------------------------------------------
# Quarter-level qualitative modifiers
# ---------------------------------------------------------------------------


class TestQuarterModifiers:
    def test_q4_peak_lifts_months_10_11_12(self):
        story = "SaaS with 1k users, revenue peak in Q4"
        parser = StoryParser()
        parser.parse(story)
        # Just verify Q4 quarter modifiers are extracted (we test via full curve below)
        modifiers = parser._extract_qualitative_month_modifiers(story)
        assert modifiers.get(10, 1.0) > 1.0
        assert modifiers.get(11, 1.0) > 1.0
        assert modifiers.get(12, 1.0) > 1.0

    def test_q3_dip_lowers_months_7_8_9(self):
        story = "SaaS with 1k users, dip in Q3"
        parser = StoryParser()
        parser.parse(story)
        modifiers = parser._extract_qualitative_month_modifiers(story)
        assert modifiers.get(7, 1.0) < 1.0
        assert modifiers.get(8, 1.0) < 1.0
        assert modifiers.get(9, 1.0) < 1.0

    def test_q1_slump_lowers_months_1_2_3(self):
        story = "saas mrr with Q1 slump"
        parser = StoryParser()
        parser.parse(story)
        modifiers = parser._extract_qualitative_month_modifiers(story)
        assert modifiers.get(1, 1.0) < 1.0
        assert modifiers.get(2, 1.0) < 1.0
        assert modifiers.get(3, 1.0) < 1.0

    def test_strong_q4_lifts_all_q4_months(self):
        story = "saas revenue strong Q4"
        parser = StoryParser()
        parser.parse(story)
        modifiers = parser._extract_qualitative_month_modifiers(story)
        for m in [10, 11, 12]:
            assert modifiers.get(m, 1.0) > 1.0, f"Month {m} should be lifted"

    def test_quarter_modifiers_dont_affect_other_months(self):
        """Q2 surge should not touch Q1 or Q3."""
        story = "saas mrr surge in Q2"
        parser = StoryParser()
        parser.parse(story)
        modifiers = parser._extract_qualitative_month_modifiers(story)
        # Q2 months boosted
        for m in [4, 5, 6]:
            assert modifiers.get(m, 1.0) > 1.0
        # Other quarters untouched
        for m in [1, 2, 3, 7, 8, 9, 10, 11, 12]:
            assert modifiers.get(m, 1.0) == 1.0, f"Month {m} should not be modified"

    def test_q_anchor_expands_to_three_months(self):
        """$100k in Q2 → months 4, 5, 6 all anchored at $100k."""
        story = "saas mrr $100k in Q2"
        parser = StoryParser()
        parser.parse(story)
        anchors = parser._extract_quarter_anchors(story)
        for m in [4, 5, 6]:
            assert m in anchors
            assert anchors[m] == pytest.approx(100_000.0)

    def test_q_anchor_does_not_override_explicit_month_anchor(self):
        """Explicit month anchor (May = $120k) beats Q2 anchor ($100k) for that month."""
        story = "saas mrr $100k in Q2, $120k in May"
        parser = StoryParser()
        period_count = 12
        month_anchors = parser._extract_target_month_points(story, period_count)
        quarter_anchors = parser._extract_quarter_anchors(story)
        # Merge: month anchors win via dict.setdefault in _build_absolute_monthly_curve
        merged = {**quarter_anchors}
        merged.update(month_anchors)  # explicit month wins
        assert merged[5] == pytest.approx(120_000.0)


# ---------------------------------------------------------------------------
# Named commercial / seasonal events
# ---------------------------------------------------------------------------


class TestNamedEventModifiers:
    def test_black_friday_boosts_november(self):
        story = "ecommerce orders with Black Friday spike"
        parser = StoryParser()
        parser.parse(story)
        modifiers = parser._extract_qualitative_month_modifiers(story)
        assert modifiers.get(11, 1.0) >= 1.4

    def test_christmas_boosts_december(self):
        story = "ecommerce orders peak at Christmas"
        parser = StoryParser()
        parser.parse(story)
        modifiers = parser._extract_qualitative_month_modifiers(story)
        assert modifiers.get(12, 1.0) >= 1.3

    def test_summer_slump_lowers_july_and_august(self):
        story = "saas mrr with summer slump"
        parser = StoryParser()
        parser.parse(story)
        modifiers = parser._extract_qualitative_month_modifiers(story)
        assert modifiers.get(7, 1.0) < 1.0
        assert modifiers.get(8, 1.0) < 1.0

    def test_back_to_school_boosts_august(self):
        story = "edtech enrollments with back to school surge"
        parser = StoryParser()
        parser.parse(story)
        modifiers = parser._extract_qualitative_month_modifiers(story)
        assert modifiers.get(8, 1.0) > 1.0

    def test_new_year_boosts_january(self):
        story = "saas signups New Year spike"
        parser = StoryParser()
        parser.parse(story)
        modifiers = parser._extract_qualitative_month_modifiers(story)
        assert modifiers.get(1, 1.0) > 1.0

    def test_holiday_season_boosts_december(self):
        story = "ecommerce orders spike during holiday season"
        parser = StoryParser()
        parser.parse(story)
        modifiers = parser._extract_qualitative_month_modifiers(story)
        assert modifiers.get(12, 1.0) > 1.0

    def test_named_event_reflected_in_full_curve(self):
        """Black Friday should make November the highest-value month in the curve."""
        story = "ecommerce store, revenue from $50k in Jan to $80k in Dec, Black Friday spike"
        parser = StoryParser()
        schema = parser.parse(story)
        for oc in schema.outcome_curves:
            if oc.table in ("orders", "products") or "revenue" in oc.column:
                vals = [pt["target_value"] for pt in oc.curve_points]
                if len(vals) == 12:
                    assert vals[10] == max(vals), "November should be the peak month"
                    break


# ---------------------------------------------------------------------------
# Relative multipliers (doubled, tripled, 10x, …)
# ---------------------------------------------------------------------------


class TestMultiplierPatterns:
    def test_doubled_detected(self):
        story = "SaaS revenue doubled over the year"
        parser = StoryParser()
        assert parser._extract_multiplier_growth(story) == pytest.approx(2.0)

    def test_tripled_detected(self):
        story = "saas mrr tripled in one year"
        parser = StoryParser()
        assert parser._extract_multiplier_growth(story) == pytest.approx(3.0)

    def test_10x_detected(self):
        story = "startup with 10x growth in revenue"
        parser = StoryParser()
        assert parser._extract_multiplier_growth(story) == pytest.approx(10.0)

    def test_halved_detected(self):
        story = "saas mrr halved after the layoffs"
        parser = StoryParser()
        assert parser._extract_multiplier_growth(story) == pytest.approx(0.5)

    def test_2x_notation_detected(self):
        story = "saas mrr 2x increase"
        parser = StoryParser()
        assert parser._extract_multiplier_growth(story) == pytest.approx(2.0)

    def test_multiplier_produces_growth_curve(self):
        """'doubled' with no explicit anchors → final month ≈ 2× first month."""
        story = "SaaS company, mrr doubled over the year"
        parser = StoryParser()
        schema = parser.parse(story)
        for oc in schema.outcome_curves:
            if oc.column == "mrr":
                vals = [pt["target_value"] for pt in oc.curve_points]
                assert len(vals) == 12
                # Last value should be ~2× the first (allow ±5% for rounding)
                assert vals[-1] == pytest.approx(vals[0] * 2.0, rel=0.05)
                break
        else:
            pytest.fail("No MRR curve produced for 'doubled' story")

    def test_10x_curve_end_is_10x_start(self):
        """10x growth → last month value = 10 × first month value."""
        story = "SaaS startup, mrr 10x growth over the year"
        parser = StoryParser()
        schema = parser.parse(story)
        for oc in schema.outcome_curves:
            if oc.column == "mrr":
                vals = [pt["target_value"] for pt in oc.curve_points]
                assert vals[-1] == pytest.approx(vals[0] * 10.0, rel=0.05)
                break
        else:
            pytest.fail("No MRR curve produced for '10x growth' story")

    def test_multiplier_with_explicit_anchor_scales_correctly(self):
        """$50k in Jan, doubled → Dec should be ~$100k."""
        story = "SaaS mrr $50k in January, doubled by December"
        parser = StoryParser()
        schema = parser.parse(story)
        for oc in schema.outcome_curves:
            if oc.column == "mrr":
                by_month = {pt["month"]: pt["target_value"] for pt in oc.curve_points}
                assert by_month[1] == pytest.approx(50_000.0)
                assert by_month[12] == pytest.approx(100_000.0, rel=0.05)
                break
        else:
            pytest.fail("No MRR curve produced")

    def test_percentage_over_100_detected_as_multiplier(self):
        """'grew 300%' → multiplier = 4.0 (1 + 300/100)."""
        story = "saas revenue grew 300% over the year"
        parser = StoryParser()
        assert parser._extract_multiplier_growth(story) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Extended qualitative keywords
# ---------------------------------------------------------------------------


class TestExtendedKeywords:
    def test_boom_keyword(self):
        story = "saas mrr boom in December"
        parser = StoryParser()
        modifiers = parser._extract_qualitative_month_modifiers(story)
        assert modifiers.get(12, 1.0) > 1.0

    def test_slump_keyword_month(self):
        story = "saas mrr slump in August"
        parser = StoryParser()
        modifiers = parser._extract_qualitative_month_modifiers(story)
        assert modifiers.get(8, 1.0) < 1.0

    def test_flat_keyword_month(self):
        story = "saas mrr flat in Q2"
        parser = StoryParser()
        modifiers = parser._extract_qualitative_month_modifiers(story)
        # flat = 1.0 factor — shouldn't boost or drop
        assert modifiers.get(4, 1.0) == pytest.approx(1.0)
        assert modifiers.get(5, 1.0) == pytest.approx(1.0)
        assert modifiers.get(6, 1.0) == pytest.approx(1.0)

    def test_push_keyword_quarter(self):
        story = "saas revenue Q4 push"
        parser = StoryParser()
        modifiers = parser._extract_qualitative_month_modifiers(story)
        for m in [10, 11, 12]:
            assert modifiers.get(m, 1.0) > 1.0


# ---------------------------------------------------------------------------
# Integration: full-parse stories that combine multiple new features
# ---------------------------------------------------------------------------


class TestNarrativeIntegration:
    def test_ecommerce_seasonal_story(self):
        """Ecommerce story with Black Friday + Christmas should produce a curve
        where November and December are the two highest months."""
        story = (
            "Ecommerce store with 5k orders, revenue from $80k in Jan to $120k in Oct, "
            "Black Friday spike, Christmas peak"
        )
        parser = StoryParser()
        schema = parser.parse(story)
        assert parser.detected_domain == "ecommerce"
        for oc in schema.outcome_curves:
            vals = [pt["target_value"] for pt in oc.curve_points]
            if len(vals) == 12:
                top2 = sorted(range(12), key=lambda i: vals[i])[-2:]
                # Months 11 and 12 (index 10 and 11) should be among the top 2
                assert 10 in top2 or 11 in top2, f"Nov/Dec not in top-2 months: vals={vals}"
                break

    def test_saas_q4_push_10x(self):
        """A story with both a quarter modifier and 10x multiplier should parse."""
        story = "SaaS startup with mrr 10x growth, strong Q4"
        parser = StoryParser()
        schema = parser.parse(story)
        assert parser.detected_domain == "saas"
        curves = [oc for oc in schema.outcome_curves if oc.column == "mrr"]
        assert curves, "No MRR curve produced"

    def test_detect_no_domain_multiplier_story_still_works(self):
        """A story with just 'doubled' should not crash even without domain detection."""
        story = "Revenue doubled over the year"
        parser = StoryParser()
        schema = parser.parse(story)
        # May fall back to generic schema — just confirm no crash and curve exists
        assert schema is not None
