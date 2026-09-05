"""Two ways a story lost an entity without saying so.

Both were found writing the prompts documentation, by running the examples
instead of describing them.

1. A coverage signal excused a whole sentence. "800 customers and 5000 invoices
   where revenue grows from ..." is one fragment, and the word "revenue" told
   the confession layer the fragment was accounted for, so the 5,000 invoices
   that produced no table were never mentioned. Silence is the failure mode the
   confession layer exists to prevent.

2. A copula became part of a table name. "12% of admissions are readmissions"
   composed a table called `are_readmissions`, because the modifier check
   excluded stopwords and -s verbs but not "are".
"""

import warnings

import pytest

import misata
from misata.composer import extract_entities
from misata.story_parser import StoryParser


def _claims(story, rows=1000):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        schema = StoryParser().parse(story, default_rows=rows)
    return schema, [str(w.message) for w in caught if "could not turn" in str(w.message)]


class TestACurveDoesNotExcuseTheWholeSentence:
    STORY = ("A SaaS company with 800 customers and 5000 invoices where revenue "
             "grows from 50000 in January 2026 to 200000 in December 2026")

    def test_the_dropped_table_is_reported(self):
        schema, claims = _claims(self.STORY)
        assert "invoices" not in {t.name for t in schema.tables}, \
            "premise changed: if invoices is built now, this test should assert that instead"
        assert any("5000 invoices" in c for c in claims), \
            f"the dropped table was not reported. Claims: {claims}"

    def test_the_curve_itself_is_still_not_reported(self):
        """A confession layer that cries wolf gets ignored, so the declaration
        the parser DID honour must stay quiet."""
        _, claims = _claims(self.STORY)
        joined = " ".join(claims).lower()
        assert "january" not in joined and "revenue" not in joined
        assert "800 customers" not in joined

    def test_a_magnitude_is_not_a_dropped_table(self):
        """"grows to 200000 dollars" is the size of the curve, not a request
        for two hundred thousand rows of something."""
        _, claims = _claims(
            "An ecommerce store with 1200 customers in 2026 where revenue "
            "grows to 200000 dollars by December.")
        assert not any("dollars" in c for c in claims), f"reported: {claims}"


class TestACopulaIsNotPartOfAnEntity:
    STORY = ("A hospital with 1500 patients, 4000 admissions and 9000 lab results "
             "in 2026, where 12% of admissions are readmissions within 30 days.")

    def test_no_table_is_named_after_a_verb(self):
        schema, _ = _claims(self.STORY)
        names = {t.name for t in schema.tables}
        assert not any(n.startswith(("are_", "is_", "was_", "were_", "has_", "have_"))
                       for n in names), f"a copula reached a table name: {names}"

    def test_a_predicate_nominative_builds_no_table(self):
        """"X are Y" says something about X. It does not introduce Y."""
        schema, _ = _claims(self.STORY)
        names = {t.name for t in schema.tables}
        assert "readmissions" not in names, \
            f"a classification of admissions became its own table: {names}"
        assert {"patients", "admissions", "lab_results"} <= names, \
            f"the real entities must survive the fix: {names}"

    @pytest.mark.parametrize("story,forbidden", [
        ("30% of orders are refunds", "refunds"),
        ("half of the accounts are duplicates", "duplicates"),
        ("most shipments were returns", "returns"),
    ])
    def test_the_pattern_generally(self, story, forbidden):
        entities = {e.table_name for e in extract_entities(story)}
        assert forbidden not in entities, f"{story!r} composed {entities}"

    def test_entities_introduced_normally_still_compose(self):
        """The fix must not cost the composer its actual job."""
        entities = {e.table_name for e in extract_entities(
            "A depot with 40 drones, 900 deliveries and 120 battery swaps")}
        assert {"drones", "deliveries"} <= entities, entities
