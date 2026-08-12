"""
The published schema and the loader have to agree.

`schema/misata.schema.json` is shipped to SchemaStore, so it is what every
editor autocompletes people into. A key published there and ignored by
`from_dict_schema` is the worst failure this project can have: the user
declares something, no error is raised, and the data quietly ignores it.

That is exactly what happened to `locale` and `realism`. Both were published at
the top level, both were dropped by the envelope normaliser, and a schema
asking for Japanese names returned American ones without complaint.
"""

import json
from pathlib import Path

import pytest

import misata
from misata.compat import HANDLED_TOP_LEVEL_KEYS, UNHANDLED_TOP_LEVEL_KEYS

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "misata.schema.json"


def published_keys():
    return set(json.loads(SCHEMA_PATH.read_text())["properties"])


PEOPLE = {
    "name": "contract",
    "tables": {
        "people": {
            "rows": 6,
            "columns": {
                "person_id": {"type": "int", "unique": True},
                "name": {"type": "text", "text_type": "name"},
                "city": {"type": "text", "text_type": "city"},
            },
        }
    },
}


def build(**extra):
    spec = dict(PEOPLE)
    spec.update(extra)
    return misata.from_dict_schema(spec, seed=7)


# ── The contract itself ───────────────────────────────────────────────────────

def test_every_published_key_is_accounted_for():
    """
    Add a key to the JSON Schema and you must either handle it or record it as
    knowingly unhandled. Silence is not an option, because silence is what
    shipped a locale setting that did nothing.
    """
    unaccounted = published_keys() - HANDLED_TOP_LEVEL_KEYS - UNHANDLED_TOP_LEVEL_KEYS
    assert unaccounted == set(), (
        f"published in misata.schema.json but neither handled nor declared "
        f"unhandled: {sorted(unaccounted)}"
    )


def test_handled_and_unhandled_do_not_overlap():
    assert HANDLED_TOP_LEVEL_KEYS & UNHANDLED_TOP_LEVEL_KEYS == set()


def test_the_unhandled_list_stays_honest():
    """A key listed as unhandled that is now handled should leave the list."""
    for key in UNHANDLED_TOP_LEVEL_KEYS:
        assert key not in HANDLED_TOP_LEVEL_KEYS


# ── Locale ────────────────────────────────────────────────────────────────────

def test_top_level_locale_reaches_the_engine():
    """The spelling the published schema teaches has to be the one that works."""
    assert build(locale="ja_JP").realism.locale == "ja_JP"


def test_nested_realism_locale_reaches_the_engine():
    assert build(realism={"locale": "ja_JP"}).realism.locale == "ja_JP"


def test_an_explicit_realism_locale_is_not_overwritten():
    schema = build(locale="en_US", realism={"locale": "de_DE"})
    assert schema.realism.locale == "de_DE"


@pytest.mark.parametrize("locale", ["ja_JP", "de_DE"])
def test_a_declared_locale_changes_the_data(locale):
    default = misata.generate_from_schema(build())["people"]["name"].tolist()
    localised = misata.generate_from_schema(build(locale=locale))["people"]["name"].tolist()
    assert localised != default, f"{locale} produced identical names to the default"


def test_no_locale_leaves_realism_alone():
    assert build().realism is None


def test_an_invalid_realism_block_is_loud():
    """
    Silently dropping it is how this bug lasted. A malformed realism block must
    raise rather than hand back data that ignores it.
    """
    with pytest.raises(ValueError):
        build(realism={"coherence": "not a valid mode"})


# ── Row counts ────────────────────────────────────────────────────────────────

def rows_for(spec, **kwargs):
    schema = misata.from_dict_schema(spec, seed=1, **kwargs)
    return len(misata.generate_from_schema(schema)["t"])


BARE = {"name": "r", "tables": {"t": {"columns": {"id": {"type": "int", "unique": True}}}}}


def test_top_level_rows_is_honoured():
    spec = dict(BARE, rows=33)
    assert rows_for(spec) == 33


def test_an_explicit_row_count_argument_beats_the_document():
    spec = dict(BARE, rows=33)
    assert rows_for(spec, row_count=7) == 7


def test_a_table_row_count_beats_the_top_level_default():
    spec = {"name": "r", "rows": 33,
            "tables": {"t": {"rows": 5, "columns": {"id": {"type": "int", "unique": True}}}}}
    assert rows_for(spec) == 5


def test_the_default_still_applies_when_nothing_is_declared():
    assert rows_for(dict(BARE)) == 1000
