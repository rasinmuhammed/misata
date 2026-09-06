"""A declared locale reaches the data, and a declared semantic type survives it.

Two bugs, both silent, both in the capability this engine sells hardest:

  * A person-name column declared `semantic: person_name` came back "Business"
    and "Growth" under ja_JP and de_DE while cities localised correctly. A
    guard meant to catch an LLM mislabelling a lookup table's `name` column was
    being applied to an explicit declaration. Under en_US the lexicon answered
    first and hid it; every other locale steps the lexicon aside for the locale
    machinery, execution reached the guard, and the declaration lost.
  * The flat dict form dropped `locale` entirely. `_unwrap_envelope` folds it
    into the realism block and returns early when there is no `tables` key, so
    the form most people write accepted the documented spelling and did nothing
    with it.
"""

import warnings

import pytest

import misata

LOCALES = ["ja_JP", "de_DE", "fr_FR", "es_ES"]


def _generate(schema, seed=4):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))


def _flat(locale):
    return {"p": {"__rows__": 60,
                  "name": {"type": "text", "semantic": "person_name"},
                  "city": {"type": "text", "text_type": "city"}},
            "locale": locale}


def _envelope(locale):
    return {"tables": {"p": {"rows": 60, "columns": {
        "name": {"type": "text", "semantic": "person_name"},
        "city": {"type": "text", "text_type": "city"}}}},
        "locale": locale}


class TestADeclaredSemanticSurvivesTheLocale:
    @pytest.mark.parametrize("locale", LOCALES)
    def test_a_declared_person_name_is_not_a_category_label(self, locale):
        names = set(_generate(_envelope(locale))["p"]["name"].astype(str))
        # The filler this used to return, drawn from the category-label pool.
        assert not names & {"Business", "Growth", "Standard", "Professional"}, \
            f"{locale} returned category labels instead of names: {sorted(names)[:5]}"

    @pytest.mark.parametrize("locale", LOCALES)
    def test_names_are_not_all_the_english_default(self, locale):
        """Region-correctness is the point. Composition must never cost it."""
        localised = set(_generate(_envelope(locale))["p"]["name"].astype(str))
        english = set(_generate(_envelope("en_US"))["p"]["name"].astype(str))
        assert localised != english, f"{locale} produced the en_US name set"

    def test_japanese_names_use_japanese_characters(self):
        names = _generate(_envelope("ja_JP"))["p"]["name"].astype(str)
        assert any(any(ord(ch) > 0x3000 for ch in n) for n in names), \
            f"no Japanese characters in {list(names[:5])}"

    def test_the_guard_still_catches_a_real_lookup_table(self):
        """The exemption is for DECLARED semantics only. A bare `name` on a
        plans table, with nothing declared, is still a tier label and not a
        person, which is what the guard was written for."""
        schema = {"tables": {"plans": {"rows": 20, "columns": {
            "name": {"type": "text", "text_type": "name"}}}}, "locale": "ja_JP"}
        values = set(_generate(schema)["plans"]["name"].astype(str))
        assert not any(any(ord(ch) > 0x3000 for ch in v) for v in values), \
            f"a plans lookup table got person names: {sorted(values)[:5]}"


class TestEverySchemaFormHonoursLocale:
    """Three spellings reach the same engine, so they must reach the same data."""

    def test_flat_envelope_and_realism_block_agree(self):
        flat = _generate(_flat("ja_JP"))["p"]
        envelope = _generate(_envelope("ja_JP"))["p"]
        explicit = _generate({"p": {"__rows__": 60,
                                    "name": {"type": "text", "semantic": "person_name"},
                                    "city": {"type": "text", "text_type": "city"}},
                              "__realism__": {"locale": "ja_JP"}})["p"]
        assert list(flat["name"]) == list(envelope["name"]) == list(explicit["name"])
        assert list(flat["city"]) == list(envelope["city"]) == list(explicit["city"])

    def test_the_flat_form_actually_builds_a_realism_config(self):
        """It used to return early and leave realism unset, so the declaration
        was accepted and discarded."""
        schema = misata.from_dict_schema(_flat("de_DE"), seed=1)
        assert getattr(schema, "realism", None) is not None
        assert schema.realism.locale == "de_DE"

    @pytest.mark.parametrize("locale", LOCALES)
    def test_cities_localise_too(self, locale):
        cities = set(_generate(_flat(locale))["p"]["city"].astype(str))
        english = set(_generate(_flat("en_US"))["p"]["city"].astype(str))
        assert cities != english, f"{locale} produced US cities"
