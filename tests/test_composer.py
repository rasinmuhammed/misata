"""Tests for compositional schema synthesis (unknown-domain stories).

The composer derives STRUCTURE from the sentence (entities, archetypes,
counts, FK wiring) and never invents domain semantics. It must beat both
failure modes it replaces: wrong-template confabulation on weak keyword
matches, and the single-generic-table collapse.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata.composer import (
    archetype_of,
    compose_schema,
    extract_entities,
    singularize,
)
from misata.story_parser import StoryParser


class TestExtraction:
    def test_plural_nouns_become_entities(self):
        entities = extract_entities("A startup tracking flights, swaps, and zones")
        names = {e.table_name for e in entities}
        assert {"flights", "swaps", "zones"} <= names

    def test_compound_noun_phrases(self):
        entities = extract_entities("tracking battery swaps and delivery zones")
        names = {e.table_name for e in entities}
        assert "battery_swaps" in names
        assert "delivery_zones" in names

    def test_row_counts_bind_to_entities(self):
        entities = {e.singular: e for e in extract_entities("A farm with 40 tractors and 5k harvests")}
        assert entities["tractor"].row_count == 40
        assert entities["harvest"].row_count == 5000

    def test_irregular_plurals(self):
        assert singularize("people") == "person"
        assert singularize("companies") == "company"
        assert singularize("boxes") == "box"
        assert singularize("flights") == "flight"

    def test_metric_words_are_not_entities(self):
        # "Revenue at $100k in January" must yield nothing → generic fallback
        # (curve extraction depends on that path staying intact).
        assert extract_entities("Revenue at $100k in January, with a spike in November.") == []

    def test_org_words_are_not_entities(self):
        entities = extract_entities("A company with startups and platforms and 100 riders")
        names = {e.singular for e in entities}
        assert "rider" in names
        assert "startup" not in names and "platform" not in names


class TestArchetypes:
    def test_lexicon_classification(self):
        assert archetype_of("rider") == "person"
        assert archetype_of("drone") == "asset"
        assert archetype_of("warehouse") == "place"
        assert archetype_of("swap") == "event"
        assert archetype_of("prescription") == "document"

    def test_morphology_fallback_marks_events(self):
        assert archetype_of("calibration") == "event"
        assert archetype_of("enrollment") == "event"

    def test_unknown_words_get_honest_record_archetype(self):
        assert archetype_of("phlebotomy") == "record"
        assert archetype_of("widget") == "record"


class TestComposedSchema:
    def test_events_reference_parent_entities(self):
        schema = compose_schema("A stable with 30 horses, 10 riders and daily rides")
        assert schema is not None
        rides_cols = {c.name for c in schema.columns["rides"]}
        assert "horse_id" in rides_cols and "rider_id" in rides_cols
        rels = {(r.parent_table, r.child_table) for r in schema.relationships}
        assert ("horses", "rides") in rels and ("riders", "rides") in rels

    def test_documents_get_author_and_event(self):
        schema = compose_schema("A workshop with 5 mechanics, repairs and repair notes")
        note_cols = {c.name for c in schema.columns["repair_notes"]}
        assert "mechanic_id" in note_cols
        assert "content" in note_cols

    def test_monetary_events_get_amount(self):
        schema = compose_schema("A stand with 3 farmers selling produce via purchases and pickups")
        assert "amount" in {c.name for c in schema.columns["purchases"]}
        assert "amount" not in {c.name for c in schema.columns["pickups"]}

    def test_no_entities_returns_none(self):
        assert compose_schema("Growth of 20% every month this year") is None


class TestParserIntegration:
    def test_weak_keyword_match_loses_to_composition(self):
        # "delivery" alone keyword-matches logistics; the drone story must
        # NOT get truck drivers and routes.
        parser = StoryParser()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            schema = parser.parse(
                "A drone delivery startup tracking flights, battery swaps, and delivery zones"
            )
        names = {t.name for t in schema.tables}
        assert "drivers" not in names and "routes" not in names
        assert {"flights", "battery_swaps", "delivery_zones", "drones"} <= names

    def test_strong_domain_matches_still_win(self):
        parser = StoryParser()
        schema = parser.parse("A SaaS company with 500 users, subscriptions and 20% churn")
        assert "subscriptions" in {t.name for t in schema.tables}
        assert parser.detected_domain == "saas"

        parser2 = StoryParser()
        schema2 = parser2.parse("A hospital with 300 patients and doctors")
        assert parser2.detected_domain == "healthcare"

    def test_composition_is_announced_honestly(self):
        parser = StoryParser()
        with pytest.warns(UserWarning, match="composed a structural schema"):
            parser.parse("A vineyard tracking 200 vines, harvests and tastings")

    def test_curve_only_story_keeps_generic_fallback(self):
        parser = StoryParser()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            schema = parser.parse(
                "Revenue at $100k in January, with a spike in November.", default_rows=1000
            )
        assert len(schema.outcome_curves) == 1  # the provable wedge stays intact


class TestEndToEnd:
    def test_drone_story_generates_with_fk_integrity(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tables = misata.generate(
                "A drone delivery startup with 40 drones tracking flights, "
                "battery swaps, and delivery zones",
                seed=7,
                rows=200,
            )
        assert len(tables["drones"]) == 40
        for child in ("flights", "battery_swaps"):
            df = tables[child]
            assert set(df["drone_id"]).issubset(set(tables["drones"]["drone_id"]))
            assert set(df["delivery_zone_id"]).issubset(
                set(tables["delivery_zones"]["delivery_zone_id"])
            )
            # composed events inherit the realism core: profiled timestamps,
            # Zipfian statuses
            dates = pd.to_datetime(df[[c for c in df.columns if c.endswith("_date")][0]])
            assert (dates.dt.nanosecond == 0).all()
            freqs = df["status"].value_counts(normalize=True)
            assert freqs.iloc[0] > 1.2 * freqs.iloc[-1]

    def test_unknown_domain_record_tables_are_honest(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tables = misata.generate(
                "A lab cataloguing 100 widgets and 50 doohickeys", seed=1
            )
        widgets = tables["widgets"]
        # no invented semantics: structural columns only
        assert {"widget_id", "reference_code", "status", "created_at", "value"} <= set(widgets.columns)
        assert widgets["reference_code"].str.match(r"WID-\d{5}").all()
