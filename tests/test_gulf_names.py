"""Gulf locales return Gulf Arabic names, not Faker's English fallback.

Faker has an Arabic person provider for ar_SA only. ar_AE, ar_BH, ar_JO and
ar_EG fall back to English silently, so a Qatari customer table came back
with "Gerald Holden" beside correctly localised cities.
"""

import re
import warnings

import pytest

import misata
from misata.locales.gulf_names import GULF_NAME_LOCALES, _FAMILY

ARABIC = re.compile(r"^[؀-ۿ ]+$")


def _names(locale, n=300, seed=4):
    schema = {"p": {"__rows__": n, "name": {"type": "text", "semantic": "person_name"}},
              "locale": locale}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return misata.generate_from_schema(
            misata.from_dict_schema(schema, seed=seed))["p"]["name"].astype(str).tolist()


@pytest.mark.parametrize("locale", GULF_NAME_LOCALES)
def test_every_gulf_name_is_arabic_script(locale):
    bad = [n for n in _names(locale) if not ARABIC.match(n)]
    assert not bad, f"{locale} returned non-Arabic names: {bad[:5]}"


@pytest.mark.parametrize("locale", GULF_NAME_LOCALES)
def test_family_names_belong_to_the_country(locale):
    families = {n.split(" ", 1)[1] for n in _names(locale)}
    assert families <= set(_FAMILY[locale])


def test_oman_does_not_get_qatari_tribal_names():
    assert not ({"الكواري", "المهندي"} & {n.split(" ", 1)[1] for n in _names("ar_OM")})


def test_names_are_not_one_repeated_value():
    assert len(set(_names("ar_QA"))) > 100


def test_seeded_run_is_reproducible_and_seed_matters():
    assert _names("ar_QA", seed=9) == _names("ar_QA", seed=9)
    assert _names("ar_QA", seed=9) != _names("ar_QA", seed=10)


def test_both_genders_appear():
    from misata.locales.gulf_names import _FEMALE, _MALE
    firsts = {n.split(" ")[0] for n in _names("ar_AE")}
    assert firsts & set(_MALE) and firsts & set(_FEMALE)


def test_ruling_family_surnames_are_not_used():
    banned = {"آل ثاني", "الثاني", "آل نهيان", "النهيان", "آل مكتوم", "المكتوم",
              "الصباح", "آل خليفة", "آل سعيد"}
    for loc in GULF_NAME_LOCALES:
        assert not (banned & set(_FAMILY[loc]))


def test_an_english_story_set_in_doha_gets_arabic_names():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = misata.generate(
            "An online store in Doha, Qatar selling to customers in Lusail and West Bay.",
            rows=100, seed=2)
    assert all(ARABIC.match(str(n)) for n in out["customers"]["name"])


def test_saudi_keeps_its_native_faker_names():
    names = _names("ar_SA", n=50)
    assert all(ARABIC.match(n) for n in names)
