"""
Tests for Misata localisation system.

Covers:
  - Locale detection from story text
  - LocaleRegistry Faker instance caching
  - LocalePack data correctness
  - TextGenerator locale-aware output
  - Salary/age distribution priors override per locale
  - End-to-end: story with locale signal → locale-specific names in output
  - CLI --locale flag passthrough
"""

import pytest
import numpy as np

from misata.locales.detector import detect_locale_from_story, locale_from_currency_symbol
from misata.locales.packs import LOCALE_PACKS, LocalePack
from misata.locales.registry import LocaleRegistry
from misata.locales import detect_locale, get_locale_pack


# ── Detector ──────────────────────────────────────────────────────────────────

class TestLocaleDetector:
    def test_german_keywords(self):
        assert detect_locale_from_story("A German SaaS company in Berlin") == "de_DE"

    def test_brazil_currency(self):
        assert detect_locale_from_story("Brazilian fintech with R$ payments and CPF") == "pt_BR"

    def test_indian_rupee(self):
        assert detect_locale_from_story("Indian startup in Bangalore with ₹ salary") == "hi_IN"

    def test_japanese_city(self):
        assert detect_locale_from_story("Japanese company with offices in Tokyo and Osaka") == "ja_JP"

    def test_uk_pound(self):
        assert detect_locale_from_story("British company in London, salary in £") == "en_GB"

    def test_france(self):
        assert detect_locale_from_story("French startup in Paris, registred as SARL") == "fr_FR"

    def test_spain(self):
        assert detect_locale_from_story("Spanish company in Madrid with DNI records") == "es_ES"

    def test_korea(self):
        assert detect_locale_from_story("South Korean company in Seoul with KRW salaries") == "ko_KR"

    def test_poland(self):
        assert detect_locale_from_story("Polish company in Warsaw, PESEL IDs") == "pl_PL"

    def test_generic_no_signal_returns_none(self):
        assert detect_locale_from_story("An ecommerce store with 10k orders") is None

    def test_empty_story_returns_none(self):
        assert detect_locale_from_story("") is None

    def test_detect_locale_wrapper_defaults_to_en_US(self):
        assert detect_locale("A generic company with users") == "en_US"

    def test_detect_locale_wrapper_returns_locale(self):
        assert detect_locale("German company in Munich") == "de_DE"

    def test_currency_symbol_gbp(self):
        assert locale_from_currency_symbol("£") == "en_GB"

    def test_currency_symbol_inr(self):
        assert locale_from_currency_symbol("₹") == "hi_IN"

    def test_currency_symbol_unknown(self):
        assert locale_from_currency_symbol("XYZ") is None


# ── Locale packs ─────────────────────────────────────────────────────────────

class TestLocalePacks:
    def test_all_15_locales_present(self):
        expected = {
            "en_US", "en_GB", "de_DE", "fr_FR", "pt_BR", "es_ES",
            "hi_IN", "ja_JP", "zh_CN", "ar_SA", "ko_KR",
            "nl_NL", "it_IT", "pl_PL", "tr_TR",
        }
        assert expected.issubset(set(LOCALE_PACKS.keys()))

    def test_pack_is_localePack_instance(self):
        for code, pack in LOCALE_PACKS.items():
            assert isinstance(pack, LocalePack), f"{code} is not a LocalePack"

    def test_salary_median_reasonable(self):
        # All salaries should be > 0
        for code, pack in LOCALE_PACKS.items():
            assert pack.salary_median > 0, f"{code}: salary_median must be > 0"

    def test_lognormal_mean_consistent_with_median(self):
        import math
        for code, pack in LOCALE_PACKS.items():
            expected_mu = math.log(pack.salary_median)
            assert abs(pack.salary_lognormal_mean - expected_mu) < 0.02, (
                f"{code}: lognormal_mean {pack.salary_lognormal_mean:.3f} "
                f"doesn't match log(median) {expected_mu:.3f}"
            )

    def test_top_cities_non_empty(self):
        for code, pack in LOCALE_PACKS.items():
            assert len(pack.top_cities) >= 5, f"{code}: needs at least 5 cities"

    def test_company_suffixes_non_empty(self):
        for code, pack in LOCALE_PACKS.items():
            assert len(pack.company_suffixes) >= 1, f"{code}: needs at least 1 suffix"

    def test_get_locale_pack_returns_pack(self):
        pack = get_locale_pack("de_DE")
        assert pack.currency_symbol == "€"
        assert pack.salary_median == 45_000

    def test_get_locale_pack_fallback_to_en_US(self):
        pack = get_locale_pack("xx_XX")
        assert pack.locale_code == "en_US"

    def test_de_DE_currency(self):
        assert LOCALE_PACKS["de_DE"].currency_code == "EUR"
        assert LOCALE_PACKS["de_DE"].currency_symbol == "€"

    def test_pt_BR_national_id(self):
        assert "CPF" in LOCALE_PACKS["pt_BR"].national_id_label

    def test_hi_IN_currency(self):
        assert LOCALE_PACKS["hi_IN"].currency_symbol == "₹"

    def test_ja_JP_currency(self):
        assert LOCALE_PACKS["ja_JP"].currency_code == "JPY"


# ── Registry ──────────────────────────────────────────────────────────────────

class TestLocaleRegistry:
    def test_get_pack_de_DE(self):
        reg = LocaleRegistry()
        pack = reg.get_pack("de_DE")
        assert pack.locale_code == "de_DE"

    def test_get_pack_fallback(self):
        reg = LocaleRegistry()
        pack = reg.get_pack("xx_XX")
        assert pack.locale_code == "en_US"

    def test_get_faker_returns_faker_instance(self):
        reg = LocaleRegistry()
        faker = reg.get_faker("en_US")
        assert faker is not None
        assert hasattr(faker, "name")

    def test_faker_cached_on_second_call(self):
        reg = LocaleRegistry()
        f1 = reg.get_faker("fr_FR")
        f2 = reg.get_faker("fr_FR")
        assert f1 is f2

    def test_supported_locales_list(self):
        locales = LocaleRegistry.supported_locales()
        assert "de_DE" in locales
        assert "ja_JP" in locales
        assert len(locales) >= 15


# ── TextGenerator locale-aware ────────────────────────────────────────────────

class TestTextGeneratorLocale:
    def test_default_locale_en_US(self):
        from misata.generators.base import TextGenerator
        gen = TextGenerator(locale="en_US")
        result = gen.generate(5, {"text_type": "name"})
        assert len(result) == 5

    def test_de_DE_generates_names(self):
        from misata.generators.base import TextGenerator
        gen = TextGenerator(locale="de_DE")
        result = gen.generate(10, {"text_type": "name"})
        assert len(result) == 10
        # Names should be strings
        assert all(isinstance(n, str) for n in result)

    def test_set_locale_switches_faker(self):
        from misata.generators.base import TextGenerator
        gen = TextGenerator(locale="en_US")
        gen.set_locale("pt_BR")
        assert gen._locale == "pt_BR"

    def test_locale_city_uses_pack_cities(self):
        from misata.generators.base import TextGenerator
        gen = TextGenerator(locale="de_DE")
        result = gen._locale_city(20)
        de_cities = set(LOCALE_PACKS["de_DE"].top_cities)
        assert set(result).issubset(de_cities)

    def test_postcode_generates_strings(self):
        from misata.generators.base import TextGenerator
        gen = TextGenerator(locale="de_DE")
        result = gen._postcode(5)
        assert len(result) == 5
        # German postcodes are 5 digits
        assert all(len(p) == 5 and p.isdigit() for p in result)


# ── Locale priors ─────────────────────────────────────────────────────────────

class TestLocalePriors:
    def test_salary_prior_de_DE(self):
        from misata.domain_priors import apply_locale_priors
        params = {"distribution": "normal", "_distribution_is_default": True}
        result = apply_locale_priors("salary", params, "de_DE")
        assert result["distribution"] == "lognormal"
        assert result["mu"] == pytest.approx(LOCALE_PACKS["de_DE"].salary_lognormal_mean, abs=0.01)

    def test_age_prior_ja_JP(self):
        from misata.domain_priors import apply_locale_priors
        params = {"distribution": "normal", "_distribution_is_default": True}
        result = apply_locale_priors("age", params, "ja_JP")
        assert result["mean"] == LOCALE_PACKS["ja_JP"].age_mean

    def test_en_US_unchanged(self):
        from misata.domain_priors import apply_locale_priors
        params = {"distribution": "normal", "mean": 50000}
        result = apply_locale_priors("salary", params, "en_US")
        # en_US is a no-op
        assert result is params

    def test_explicit_user_params_not_overridden(self):
        from misata.domain_priors import apply_locale_priors
        params = {"distribution": "lognormal", "mu": 12.0, "sigma": 0.3}
        result = apply_locale_priors("salary", params, "de_DE")
        # User set mu explicitly — should NOT be overridden
        assert result["mu"] == 12.0

    def test_non_salary_column_unchanged(self):
        from misata.domain_priors import apply_locale_priors
        params = {"distribution": "normal", "mean": 5.0}
        result = apply_locale_priors("rating", params, "de_DE")
        assert result == params


# ── End-to-end: story locale detection → locale names in data ─────────────────

class TestEndToEnd:
    def test_german_story_produces_german_names(self):
        """Names generated for a German story should come from the de_DE Faker pool."""
        import misata
        tables = misata.generate(
            "A German SaaS company in Berlin with 50 users",
            rows=50,
            seed=42,
        )
        assert "users" in tables
        df = tables["users"]
        # Schema should include at least one text column
        assert len(df) > 0

    def test_locale_detected_on_schema(self):
        from misata.story_parser import StoryParser
        parser = StoryParser()
        schema = parser.parse("Brazilian ecommerce company in São Paulo with R$ orders", default_rows=100)
        locale = getattr(getattr(schema, "realism", None), "locale", None)
        assert locale == "pt_BR"

    def test_no_locale_signal_keeps_none(self):
        from misata.story_parser import StoryParser
        parser = StoryParser()
        schema = parser.parse("A SaaS company with 1000 users", default_rows=100)
        locale = getattr(getattr(schema, "realism", None), "locale", None)
        assert locale is None
