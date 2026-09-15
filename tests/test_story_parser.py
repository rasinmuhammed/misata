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

    def test_delivered_at_has_valid_date_params(self):
        """delivered_at must not reference a non-date column — was 'drivers.status'."""
        parser = StoryParser()
        schema = parser.parse("A logistics company with drivers and shipments.", default_rows=100)
        shipment_cols = {c.name: c for c in schema.columns["shipments"]}
        params = shipment_cols["delivered_at"].distribution_params
        assert "start" in params, "delivered_at must have 'start' date param, not 'relative_to'"
        assert "end" in params, "delivered_at must have 'end' date param"
        assert "relative_to" not in params, "delivered_at must not reference 'relative_to'"

    def test_logistics_schema_generates_without_error(self):
        """End-to-end: logistics schema must generate data without crashing."""
        import pandas as pd
        from misata.simulator import DataSimulator

        parser = StoryParser()
        schema = parser.parse("A logistics company with drivers and shipments.", default_rows=100)
        sim = DataSimulator(schema)
        tables = {}
        for name, batch in sim.generate_all():
            tables[name] = pd.concat([tables.get(name, pd.DataFrame()), batch], ignore_index=True)
        assert "shipments" in tables
        assert len(tables["shipments"]) == 100


class TestGenericFallback:
    def test_unknown_domain_emits_warning(self):
        import warnings
        parser = StoryParser()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            schema = parser.parse("Generate some completely random data with no domain hints.", default_rows=50)
        assert any("could not detect a domain" in str(w.message).lower() for w in caught)

    def test_unknown_domain_still_returns_schema(self):
        import warnings
        parser = StoryParser()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = parser.parse("A totally ambiguous dataset.", default_rows=50)
        assert result is not None
        assert len(result.tables) >= 1


class TestValidateSchemaOutcomeCurveTypes:
    def test_non_date_time_column_raises(self):
        from misata.schema import OutcomeCurve
        from misata.validation import SchemaValidationError, validate_schema

        # users.user_id is an int column — not a valid time_column
        from misata.schema import Column, SchemaConfig, Table
        schema = SchemaConfig(
            name="test",
            tables=[Table(name="users", row_count=10)],
            columns={
                "users": [
                    Column(name="user_id", type="int", unique=True, distribution_params={"min": 1, "max": 10}),
                    Column(name="amount", type="float", distribution_params={"min": 0.0}),
                ]
            },
            outcome_curves=[
                OutcomeCurve(table="users", column="amount", time_column="user_id")
            ],
        )
        with pytest.raises(SchemaValidationError, match="must be 'date' or 'datetime'"):
            validate_schema(schema)

    def test_date_time_column_passes(self):
        from misata.schema import Column, OutcomeCurve, SchemaConfig, Table
        from misata.validation import validate_schema

        schema = SchemaConfig(
            name="test",
            tables=[Table(name="sales", row_count=10)],
            columns={
                "sales": [
                    Column(name="sale_id", type="int", unique=True, distribution_params={"min": 1, "max": 10}),
                    Column(name="amount", type="float", distribution_params={"min": 0.0}),
                    Column(name="sale_date", type="date", distribution_params={"start": "2023-01-01", "end": "2024-12-31"}),
                ]
            },
            outcome_curves=[
                OutcomeCurve(table="sales", column="amount", time_column="sale_date")
            ],
        )
        validate_schema(schema)  # must not raise


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


class TestDomainDetectionMatchesWordsNotSubstrings:
    """The HR domain has the keyword "hr", and detection was a raw substring
    scan. The word **through** contains "hr", so this prompt:

        "An e-commerce store, revenue rising through 2025"

    was detected as HR and generated departments, employees and payroll. So did
    "three", "throughout", "shrinking" and "chrome".

    Column-name inference was made token-aware after the same class of bug. The
    domain detector was still scanning substrings, and a two-letter keyword
    makes that catastrophic rather than merely sloppy.
    """

    def _domain(self, story):
        from misata.story_parser import StoryParser
        p = StoryParser()
        p.parse(story, default_rows=10)
        return p.detected_domain

    @pytest.mark.parametrize("story", [
        "An e-commerce store, revenue rising through 2025",
        "An online shop, revenue growing throughout 2025",
        "A shrinking retail chain with customers and orders",
    ])
    def test_a_word_that_merely_contains_hr_is_not_an_hr_system(self, story):
        assert self._domain(story) != "hr", (
            "an ordinary English word containing 'hr' selected the HR domain")

    @pytest.mark.parametrize("story", [
        "An HR system with employees and payroll",
        "hr analytics with headcount and hiring",
        "A human resources platform tracking onboarding",
    ])
    def test_a_real_hr_story_still_finds_hr(self, story):
        assert self._domain(story) == "hr"

    def test_the_ecommerce_prompt_that_started_it_produces_a_storefront(self):
        from misata.story_parser import StoryParser
        p = StoryParser()
        schema = p.parse(
            "An e-commerce store: customers, products, orders and order items, "
            "GMV rising through 2025 with a Black Friday spike", default_rows=500)
        names = {t.name for t in schema.tables}
        assert p.detected_domain == "ecommerce"
        assert "payroll" not in names and "employees" not in names
        assert "customers" in names and "orders" in names

    def test_a_multi_word_keyword_still_matches_as_a_phrase(self):
        assert self._domain("A human resources platform") == "hr"

    def test_a_longer_keyword_still_matches_as_a_stem(self):
        """Anchoring both edges was too strict: the keyword is "pharma" and the
        story says "pharmaceutical", which broke the flagship one-sentence CRO
        test. Only the left edge is anchored for keywords over three
        characters."""
        assert self._domain(
            "A pharmaceutical CRO with 60 employees and clinical projects") == "pharma"

    def test_a_short_keyword_is_not_a_prefix_match(self):
        """Three characters or fewer need both edges, or "cro" starts claiming
        every story about crowdfunding."""
        from misata.story_parser import _mentions
        assert _mentions("a cro running trials", "cro")
        assert not _mentions("a crowdfunding platform", "cro")
        assert not _mentions("revenue rising through 2025", "hr")


# ---------------------------------------------------------------------------
# STORY_PARSER_AUDIT.md — bugs found by generating data and checking the
# numbers, not by reading code and assuming it works. Every test below
# checks what the simulator DID with an extracted declaration, not just
# what the extractor returned — that gap in how this file tested itself
# was the actual root cause behind all three bugs.
# ---------------------------------------------------------------------------

class TestBareYearNextToAPeriodIsNotAValue:
    """Bug 1: "January 2026" / "Q1 2026" must never read the bare "2026" as
    a target value — a real symptom was every month between two such
    mentions interpolating to ~2026 dollars, not a formatting glitch."""

    def test_quarter_anchors_ignore_the_bare_year(self):
        parser = StoryParser()
        story = ("revenue grows from $50,000 in January 2026 to $500,000 in "
                  "December 2026, and churn rate rises from 2% in Q1 2026 to "
                  "15% by Q4 2026")
        anchors = parser._extract_quarter_anchors(story)
        assert 2026 not in anchors.values()
        assert not anchors, f"a bare year next to Q1/Q4 produced anchors: {anchors}"

    def test_month_points_still_correct_with_year_present(self):
        parser = StoryParser()
        story = ("revenue grows from $50,000 in January 2026 to $500,000 in "
                  "December 2026")
        anchors = parser._extract_target_month_points(story, 12)
        assert anchors[1] == pytest.approx(50000.0)
        assert anchors[12] == pytest.approx(500000.0)

    def test_the_full_monthly_curve_is_a_smooth_interpolation_not_a_repeated_year(self):
        """The originally reported symptom: every month between Jan and Dec
        came back as literally 2026, not a smooth ramp."""
        parser = StoryParser()
        schema = parser.parse(
            "An ecommerce company with 500 customers where revenue grows from "
            "$50,000 in January 2026 to $500,000 in December 2026",
            default_rows=500,
        )
        assert len(schema.outcome_curves) == 1
        points = {p["month"]: p["target_value"] for p in schema.outcome_curves[0].curve_points}
        assert len(points) == 12
        values = [points[m] for m in range(1, 13)]
        # Monotonically non-decreasing, and no value anywhere near a bare year.
        assert all(v2 >= v1 - 1e-6 for v1, v2 in zip(values, values[1:]))
        assert all(v > 3000 for v in values), f"a value collapsed to a bare-year figure: {values}"

    def test_a_single_quarter_year_mention_is_not_polluted_either(self):
        """A single "Q_ YYYY" mention is just as real a bug as two -- the
        original repro needed two mentions to make the interpolated middle
        visibly wrong, but one bad anchor is still one bad anchor."""
        parser = StoryParser()
        anchors = parser._extract_quarter_anchors("$100k in Q2 2026")
        assert anchors == {4: 100000.0, 5: 100000.0, 6: 100000.0}

    def test_reverse_order_year_then_quarter_does_not_pollute_either(self):
        parser = StoryParser()
        anchors = parser._extract_quarter_anchors("2026 Q1: $100k")
        assert 2026 not in anchors.values()


class TestRateCurvePeriodsCarryTheRightYear:
    """Bug 2: a bare month/quarter anchor with no year named in the story
    must repeat as an annual seasonal pattern across every year the data
    actually spans, not pin to a running index that only happens to land
    inside the data's first year. A year the story DOES name gets pinned
    to that one specific year instead."""

    def test_rising_churn_curve_hits_the_declared_rate_every_year_present(self):
        import warnings
        import misata

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tables = misata.generate(
                "Churn rate rises from 2% in Q1 to 15% by Q4", rows=4000, seed=42,
            )
        users = tables["users"]
        dates = pd.to_datetime(users["signup_date"])
        years = dates.dt.year.unique()
        assert len(years) > 1, "widen the sample so the multi-year bug has somewhere to hide"

        for year in years:
            in_year = users[dates.dt.year == year]
            jan = in_year[dates[dates.dt.year == year].dt.month == 1]
            dec = in_year[dates[dates.dt.year == year].dt.month == 12]
            if len(jan) < 10 or len(dec) < 10:
                continue
            jan_rate = jan["churned"].mean()
            dec_rate = dec["churned"].mean()
            # The declared range is 2%-15%; every year present should show
            # January low and December high, not just the first one.
            assert jan_rate < 0.08, f"{year}: January churn {jan_rate:.3f} is not near the declared 2% floor"
            assert dec_rate > 0.10, f"{year}: December churn {dec_rate:.3f} is not near the declared 15% ceiling"

    def test_explicit_year_pins_to_that_year_specifically(self):
        parser = StoryParser()
        schema = parser.parse(
            "A fintech company with 2000 transactions. Fraud rate rises from "
            "1% in Q1 2024 to 6% by Q4 2024.",
            default_rows=2000,
        )
        fraud_curves = [rc for rc in (schema.rate_curves or []) if "fraud" in rc.column]
        assert fraud_curves, "expected a fraud RateCurve"
        periods = [p["period"] for p in fraud_curves[0].rate_points]
        assert all("2024" in str(p) for p in periods), f"year was not attached: {periods}"

    def test_flat_rate_with_no_period_is_unaffected(self):
        parser = StoryParser()
        schema = parser.parse(
            "A fintech payments platform with 5000 transactions and a 2% fraud "
            "rate across all periods.",
            default_rows=5000,
        )
        assert schema.rate_curves
        assert schema.rate_curves[0].rate_points[0]["period"] == "all"

    def test_single_period_anchored_rate_still_works(self):
        parser = StoryParser()
        schema = parser.parse(
            "A fintech company with 2000 transactions and a 5% fraud rate in Q2.",
            default_rows=2000,
        )
        fraud_curves = [rc for rc in (schema.rate_curves or []) if "fraud" in rc.column]
        assert fraud_curves
        assert len(fraud_curves[0].rate_points) == 1
        assert abs(fraud_curves[0].rate_points[0]["rate"] - 0.05) < 1e-6


class TestRateNounMorphologicalForms:
    """Bug 3: a rate noun must match its realistic word family (noun, verb,
    adjective, gerund), not only the one exact string form the map happens
    to be keyed on. "Cancellation" produced zero rate curves against a map
    keyed only on "cancelled" -- the systematic version of that gap, not
    just the one word that got caught, is what this class checks."""

    @pytest.mark.parametrize("story,concept", [
        ("A fintech company with 2000 transactions where fraudulent activity "
         "rises from 1% in Q1 to 6% by Q4.", "fraud"),
        ("A SaaS startup with 3000 subscribers where subscribers keep churning "
         "-- churn rises from 2% in Q1 to 10% by Q4.", "churn"),
        ("A SaaS company with 2000 subscriptions where the cancellation rate "
         "for subscriptions rises from 5% in Q1 to 30% in Q4.", "cancellation"),
        ("An ecommerce store with 3000 orders where the return rate rises "
         "from 3% in Q1 to 12% by Q4.", "returned"),
        ("A logistics company with 3000 shipments where the return rate "
         "rises from 2% in Q1 to 9% by Q4.", "returned (logistics)"),
    ])
    def test_every_documented_morphological_variant_extracts_a_curve(self, story, concept):
        parser = StoryParser()
        schema = parser.parse(story, default_rows=2000)
        assert schema.rate_curves, f"{concept!r} form produced zero rate curves: {story!r}"

    @pytest.mark.parametrize("form", ["defect", "defects", "defective"])
    def test_defect_concept_has_no_domain_home_yet_but_does_not_crash(self, form):
        """None of the 18 built-in domains has a manufacturing table with a
        defect column, so this concept can never resolve today -- that's a
        template-coverage gap, not a regex bug, and the parser's documented
        behavior for "noun present but column not in schema" is to skip
        silently, not raise. Pinned here so this stays a known, deliberate
        gap rather than a silent crash if it regresses."""
        parser = StoryParser()
        story = f"A manufacturing plant with 5000 units where the {form} rate rises from 1% in Q1 to 8% by Q4."
        schema = parser.parse(story, default_rows=2000)
        assert schema.rate_curves == []

    def test_cancellation_status_column_keeps_its_real_categories(self):
        """A "status" fallback column is categorical (active/cancelled/
        paused/trialing), not boolean -- enforcement used to overwrite every
        real category with a bare True/False the moment "status" was picked
        as the target column."""
        import warnings
        import misata

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tables = misata.generate(
                "A SaaS company where the cancellation rate for subscriptions "
                "rises from 5% in Q1 to 30% in Q4",
                rows=2000, seed=3,
            )
        status = tables["subscriptions"]["status"]
        assert set(status.unique()) - {True, False}, (
            f"status column was overwritten with plain booleans: {sorted(status.unique())}"
        )
        assert "cancelled" in set(status.unique())


class TestGroupShareLanguageFailsLoudly:
    """Bug 4: plain-English plan-tier/group splits ("20% from Starter, 50%
    from Pro, 30% from Enterprise") have no extractor at all. Until that's
    built, the failure must be loud (a UserWarning naming what was dropped),
    never silent-and-wrong, which is worse."""

    def test_a_percentage_split_with_no_extractor_warns_by_name(self):
        import warnings

        parser = StoryParser()
        story = ("A SaaS company with 5000 users. Of that revenue, exactly 20% "
                  "comes from Starter plans, 50% from Pro plans, and 30% from "
                  "Enterprise plans")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            parser.parse(story, default_rows=5000)
        messages = [str(w.message) for w in caught]
        assert any("20%" in m or "Starter" in m for m in messages), (
            f"the dropped plan-tier split produced no warning naming it: {messages}"
        )
