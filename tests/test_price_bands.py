"""Conditional vocabulary coherence: category-tied product pools and price
bands.

A capsule can declare that a row's price lives inside the band of its
category ("Honey": 4-25, "Laptops": 400-3500). Generation draws inside the
band (log-uniform, retail endings), the audit flags any row outside it, and
the precedence ladder holds: explicit user shapes beat the band, declared
bounds intersect it, semantic fallback bounds lose to it.
"""

import json

import numpy as np
import pandas as pd
import pytest

import misata
from misata.schema import Column, RealismConfig, SchemaConfig, Table

BANDS = {"Honey": [4, 25], "Laptops": [400, 3500], "Coffee": [6, 40]}
CATS = list(BANDS)


@pytest.fixture()
def capsule_file(tmp_path):
    capsule = {
        "misata_capsule": 1,
        "domain": "grocery-electronics",
        "vocabularies": {"category": CATS},
        "conditional_vocabularies": {
            "product_name": {
                "parent": "category",
                "map": {
                    "Honey": ["Wildflower Honey 500g", "Manuka Honey 250g"],
                    "Laptops": ["ThinkPad X1 Carbon", "MacBook Air M3"],
                    "Coffee": ["Ethiopian Yirgacheffe 250g"],
                },
            }
        },
        "price_bands": {
            "price": {"parent": "category", "bands": BANDS},
        },
    }
    path = tmp_path / "capsule.json"
    path.write_text(json.dumps(capsule))
    return str(path)


def _schema(capsule_file, price_params=None, cats=CATS, rows=3000,
            with_product=True):
    cols = [
        Column(name="id", type="int", unique=True,
               distribution_params={"min": 1, "max": 999999}),
        Column(name="category", type="categorical",
               distribution_params={"choices": cats}),
    ]
    if with_product:
        cols.append(Column(name="product_name", type="text"))
    cols.append(Column(name="price", type="float",
                       distribution_params=price_params or {}))
    return SchemaConfig(
        name="bands", seed=5,
        tables=[Table(name="products", row_count=rows,
                      columns=[c.name for c in cols])],
        columns={"products": cols}, relationships=[],
        realism=RealismConfig(capsule_file=capsule_file),
    )


class TestBandGeneration:
    def test_every_price_inside_its_category_band(self, capsule_file):
        df = misata.generate_from_schema(_schema(capsule_file))["products"]
        for cat, (lo, hi) in BANDS.items():
            sub = df[df["category"] == cat]["price"]
            assert len(sub) > 0
            assert sub.min() >= lo and sub.max() <= hi, (
                f"{cat}: [{sub.min()}, {sub.max()}] outside [{lo}, {hi}]")

    def test_band_uses_its_full_range_not_a_fallback_cap(self, capsule_file):
        # Regression: semantic fallback bounds (a bare "price" gets 0-1000)
        # must not clip the laptop band to 400-1000.
        df = misata.generate_from_schema(_schema(capsule_file))["products"]
        lp = df[df["category"] == "Laptops"]["price"]
        assert lp.max() > 1500, f"laptop max {lp.max()}: band clipped by fallback"

    def test_products_match_their_category_pool(self, capsule_file):
        df = misata.generate_from_schema(_schema(capsule_file))["products"]
        honey = set(df[df["category"] == "Honey"]["product_name"])
        assert honey and all("honey" in p.lower() for p in honey)

    def test_prices_lean_cheap_within_band(self, capsule_file):
        # Log-uniform stacks the cheap end: the median sits below the
        # arithmetic midpoint of the band.
        df = misata.generate_from_schema(_schema(capsule_file))["products"]
        lp = df[df["category"] == "Laptops"]["price"]
        assert lp.median() < (400 + 3500) / 2


class TestPrecedence:
    def test_declared_bounds_intersect_the_band(self, capsule_file):
        df = misata.generate_from_schema(
            _schema(capsule_file, {"min": 5, "max": 500}, cats=["Honey"])
        )["products"]
        p = df["price"]
        assert p.min() >= 5 and p.max() <= 25

    def test_contradictory_declaration_wins_over_band(self, capsule_file):
        df = misata.generate_from_schema(
            _schema(capsule_file, {"min": 1, "max": 300}, cats=["Laptops"])
        )["products"]
        assert df["price"].max() <= 300

    def test_explicit_shape_ignores_the_band(self, capsule_file):
        df = misata.generate_from_schema(
            _schema(capsule_file,
                    {"distribution": "normal", "mean": 100, "std": 5},
                    cats=["Laptops"])
        )["products"]
        assert 90 < df["price"].mean() < 110


class TestAudit:
    def test_clean_on_honest_data(self, capsule_file):
        schema = _schema(capsule_file)
        tables = misata.generate_from_schema(schema)
        rep = misata.story_audit(tables, schema)
        assert not [f for f in rep.findings if f.kind == "price_band_violation"]

    def test_catches_500_dollar_honey(self, capsule_file):
        schema = _schema(capsule_file)
        tables = misata.generate_from_schema(schema)
        sab = {k: v.copy() for k, v in tables.items()}
        idx = sab["products"][sab["products"]["category"] == "Honey"].index[0]
        sab["products"].loc[idx, "price"] = 500.0
        rep = misata.story_audit(sab, schema)
        findings = [f for f in rep.findings if f.kind == "price_band_violation"]
        assert findings and findings[0].severity == "high"
        assert findings[0].rows_affected == 1

    def test_no_detector_without_bands(self):
        # No capsule attached: the detector must stay silent, whatever the
        # prices look like.
        cols = [
            Column(name="id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 999999}),
            Column(name="category", type="categorical",
                   distribution_params={"choices": ["A"]}),
            Column(name="price", type="float",
                   distribution_params={"min": 1, "max": 9999}),
        ]
        schema = SchemaConfig(
            name="nobands", seed=5,
            tables=[Table(name="t", row_count=200,
                          columns=[c.name for c in cols])],
            columns={"t": cols}, relationships=[],
        )
        tables = misata.generate_from_schema(schema)
        rep = misata.story_audit(tables, schema)
        assert not [f for f in rep.findings if f.kind == "price_band_violation"]


class TestCapsuleRoundtrip:
    def test_price_bands_survive_save_and_load(self, capsule_file, tmp_path):
        from misata.capsules import load_capsule, save_capsule
        capsule = load_capsule(capsule_file)
        assert capsule.price_bands["price"]["bands"]["Honey"] == [4.0, 25.0]
        out = tmp_path / "resaved.json"
        save_capsule(capsule, out)
        again = load_capsule(out)
        assert again.price_bands == capsule.price_bands

    def test_malformed_bands_are_dropped(self, tmp_path):
        from misata.capsules import load_capsule
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({
            "misata_capsule": 1, "domain": "x",
            "price_bands": {
                "price": {"parent": "category",
                          "bands": {"Good": [1, 5], "Reversed": [9, 2],
                                    "NotNumbers": ["a", "b"]}},
            },
        }))
        capsule = load_capsule(path)
        assert list(capsule.price_bands["price"]["bands"]) == ["Good"]
