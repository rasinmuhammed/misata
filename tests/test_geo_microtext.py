"""Tests for geographic coherence and grammar-based microtext.

Geo: distances between named cities are facts (haversine × road circuity),
not distributions — and travel times must follow from distances.
Microtext: review sentiment is generated FROM the rating (conformance),
and the lorem ipsum fallback is gone.
"""

import numpy as np
import pandas as pd

import misata
from misata.geo import (
    CITY_COORDS,
    EFFECTIVE_SPEED_KMH,
    HANDLING_OVERHEAD_H,
    haversine_km,
    road_distance_km,
    travel_hours,
)
from misata.microtext import (
    Grammar,
    MicrotextGenerator,
    detect_sentiment,
)
from misata.realism import apply_realism_rules


# ─── Geo facts ───────────────────────────────────────────────────────────────


class TestGeoFacts:
    def test_haversine_known_pair(self):
        # NYC ↔ LA great-circle ≈ 3,936 km
        d = haversine_km(
            np.array(40.7128), np.array(-74.0060),
            np.array(34.0522), np.array(-118.2437),
        )
        assert 3900 < float(d) < 3980

    def test_road_distance_applies_circuity(self):
        gc = haversine_km(
            np.array(CITY_COORDS["Chicago"][0]), np.array(CITY_COORDS["Chicago"][1]),
            np.array(CITY_COORDS["Denver"][0]), np.array(CITY_COORDS["Denver"][1]),
        )
        assert road_distance_km("Chicago", "Denver") == round(float(gc) * 1.25, 1)

    def test_unknown_city_returns_none(self):
        assert road_distance_km("Chicago", "Atlantis") is None

    def test_travel_time_follows_distance(self):
        assert travel_hours(650.0) == round(650.0 / EFFECTIVE_SPEED_KMH + HANDLING_OVERHEAD_H, 1)

    def test_locale_pack_cities_have_coordinates(self):
        # every city any locale pack can emit must be resolvable
        import inspect
        import re

        import misata.generators_legacy as legacy
        import misata.locales.packs as packs

        src = inspect.getsource(packs)
        cities = set(legacy.CITIES)
        for match in re.findall(r"top_cities=\[(.*?)\]", src, re.S):
            cities.update(re.findall(r'"([^"]+)"', match))
        missing = sorted(c for c in cities if c not in CITY_COORDS)
        assert not missing, f"cities without coordinates: {missing}"


class TestRouteGeoRule:
    def _df(self):
        return pd.DataFrame(
            {
                "origin_city": ["Chicago", "Seattle", "Chicago", "Mythville"],
                "destination_city": ["San Diego", "Boston", "Chicago", "Boston"],
                "distance_km": [145.6, 10.0, 50.0, 777.0],
                "estimated_hours": [8.3, 1.0, 2.0, 9.9],
            }
        )

    def test_known_pairs_get_factual_distance_and_hours(self):
        fixed = apply_realism_rules(self._df(), rng=np.random.default_rng(0))
        expected = road_distance_km("Chicago", "San Diego")
        assert fixed["distance_km"][0] == expected
        assert expected > 2500  # not 145.6 km!
        assert fixed["estimated_hours"][0] == travel_hours(expected)

    def test_self_routes_are_rerouted(self):
        fixed = apply_realism_rules(self._df(), rng=np.random.default_rng(0))
        assert (fixed["origin_city"] != fixed["destination_city"]).all()

    def test_unknown_cities_left_untouched(self):
        fixed = apply_realism_rules(self._df(), rng=np.random.default_rng(0))
        assert fixed["distance_km"][3] == 777.0
        assert fixed["estimated_hours"][3] == 9.9

    def test_end_to_end_logistics_routes_are_factual(self):
        tables = misata.generate(
            "A logistics company with 50 drivers, routes and shipments", seed=7
        )
        routes = tables["routes"]
        checked = 0
        for _, row in routes.iterrows():
            fact = road_distance_km(row["origin_city"], row["destination_city"])
            if fact is not None:
                assert row["distance_km"] == fact
                checked += 1
        assert checked > len(routes) * 0.8  # coordinate coverage is broad


# ─── Microtext ───────────────────────────────────────────────────────────────


class TestGrammar:
    def test_expansion_is_deterministic(self):
        rules = {"s": ["{a} {b}"], "a": ["x", "y"], "b": ["1", "2", "3"]}
        g1 = Grammar(rules, np.random.default_rng(5))
        g2 = Grammar(rules, np.random.default_rng(5))
        assert [g1.expand("s") for _ in range(20)] == [g2.expand("s") for _ in range(20)]

    def test_unknown_symbol_fails_loudly(self):
        g = Grammar({"s": ["{typo}"]}, np.random.default_rng(0))
        try:
            g.expand("s")
            assert False, "expected KeyError"
        except KeyError:
            pass

    def test_weights_bias_selection(self):
        g = Grammar({"s": [(9, "heavy"), (1, "light")]}, np.random.default_rng(0))
        out = [g.expand("s") for _ in range(500)]
        assert out.count("heavy") > 400


class TestSentimentConformance:
    def test_reviews_match_their_ratings(self):
        gen = MicrotextGenerator(np.random.default_rng(0))
        ratings = np.array([1] * 200 + [5] * 200)
        reviews = gen.reviews(400, ratings=ratings)
        for text, rating in zip(reviews, ratings):
            polarity = detect_sentiment(text)
            if polarity is None:
                continue  # not every sentence carries a marker
            assert polarity == ("negative" if rating == 1 else "positive"), text
        # markers must actually fire on a healthy share of rows
        detected = sum(detect_sentiment(t) is not None for t in reviews)
        assert detected > 200

    def test_ten_point_scales_are_normalised(self):
        gen = MicrotextGenerator(np.random.default_rng(0))
        levels = gen.normalize_ratings(np.array([10.0, 2.0, 6.0]), 3, gen.rng)
        assert list(levels) == [5, 1, 3]

    def test_review_diversity(self):
        gen = MicrotextGenerator(np.random.default_rng(0))
        reviews = gen.reviews(500, ratings=np.full(500, 5))
        # combinatorial grammar ⇒ far more distinct strings than a flat pool
        assert len(set(reviews)) > 200

    def test_rule_repairs_sentiment_post_generation(self):
        df = pd.DataFrame(
            {
                "rating": [1.0, 5.0],
                "review_text": ["Absolutely loved it! 10/10.", "Terrible experience. Never again."],
            }
        )
        fixed = apply_realism_rules(df, rng=np.random.default_rng(0))
        assert detect_sentiment(fixed["review_text"][0]) != "positive"
        assert detect_sentiment(fixed["review_text"][1]) != "negative"

    def test_end_to_end_travel_reviews_conform(self):
        tables = misata.generate(
            "A travel booking platform with hotels, bookings and reviews", seed=3
        )
        rev = tables["reviews"]
        rating_col = next(c for c in rev.columns if "rating" in c)
        text_cols = [c for c in rev.columns if c in ("review_text", "review", "title", "review_title")]
        assert text_cols
        col = text_cols[0]
        low = rev[rev[rating_col] <= 2][col]
        high = rev[rev[rating_col] >= 5][col]
        assert not any(detect_sentiment(t) == "positive" for t in low)
        assert not any(detect_sentiment(t) == "negative" for t in high)


class TestLoremIsDead:
    def test_sentence_text_type_is_human(self):
        from misata.schema import Column, SchemaConfig, Table
        from misata.simulator import DataSimulator

        cfg = SchemaConfig(
            name="T",
            seed=1,
            tables=[Table(name="t", row_count=50)],
            columns={
                "t": [
                    Column(name="id", type="int"),
                    Column(name="notes", type="text", distribution_params={"text_type": "sentence"}),
                ]
            },
        )
        data = {}
        for tn, batch in DataSimulator(cfg).generate_all():
            data[tn] = batch
        joined = " ".join(data["t"]["notes"].astype(str)).lower()
        for lorem_word in ("lorem", "ipsum", "dolor", "amet", "consectetur"):
            assert lorem_word not in joined
