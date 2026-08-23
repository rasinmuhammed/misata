"""The story parser says what it could not use.

It is a recogniser over a fixed set of phrasings, and it used to return
nothing at all for everything else without comment. A story asking for 6,000
invoices, a plan split, an average contract value and an unpaid rate came back
as two tables and looked exactly like a success.

A declaration is honoured or refused, never ignored. These pin both halves:
real gaps are reported, and work the parser genuinely did is not.
"""

import warnings

import pytest

import misata

HARD_SAAS = (
    "A B2B SaaS company in 2026 with 1,500 customers, 1,800 subscriptions and "
    "6,000 invoices. Revenue curve: Jan 180000, Feb 195000, Mar 210000, "
    "Apr 228000, May 245000, Jun 262000, Jul 280000, Aug 298000, Sep 315000, "
    "Oct 340000, Nov 365000, Dec 400000. 14% churn. "
    "Plans split 55% Starter, 33% Growth, 12% Enterprise. "
    "Average contract value 2400. 8% of invoices unpaid."
)


def _refused(story, rows=1500):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        schema = misata.parse(story, rows=rows)
    claims = [str(w.message).split("could not turn ")[1].split(" into")[0].strip("'")
              for w in caught if "could not turn" in str(w.message)]
    return schema, claims


@pytest.mark.parametrize("fragment", [
    "6,000 invoices",          # no invoices table is built
    "Average contract value",  # no mechanism for it
    "8% of invoices unpaid",   # arbitrary rates are not supported
])
def test_dropped_declarations_are_reported(fragment):
    _, claims = _refused(HARD_SAAS)
    assert any(fragment.lower() in c.lower() for c in claims), \
        f"{fragment!r} was dropped without saying so. Reported: {claims}"


def test_the_plan_split_is_reported():
    """`Growth` is a plan name. Matching the word 'growth' as if it were a
    revenue statement waved this straight through."""
    _, claims = _refused(HARD_SAAS)
    assert any("starter" in c.lower() for c in claims), \
        f"the plan split was dropped silently. Reported: {claims}"


def test_what_the_parser_did_honour_is_not_reported():
    """Row counts it delivered, and the curve and churn it built, must not be
    listed as failures. A confession layer that cries wolf gets ignored."""
    schema, claims = _refused(HARD_SAAS)
    joined = " ".join(claims).lower()

    assert {t.name for t in schema.tables} >= {"users", "subscriptions"}
    assert len(schema.outcome_curves[0].curve_points) == 12
    assert "1,500 customers" not in joined, "the users table was built with 1,500 rows"
    assert "jan" not in joined and "revenue curve" not in joined
    assert "14% churn" not in joined, "a rate curve was created for churn"
    assert "2026" not in joined, "a calendar year is not a quantity"


def test_a_fully_handled_story_reports_nothing():
    _, claims = _refused(
        "A SaaS company with 800 customers and 1000 subscriptions in 2026. "
        "Revenue curve: Jan 100000, Feb 120000, Mar 140000. 15% churn.", rows=800)
    assert claims == [], f"clean story reported: {claims}"


def test_report_carries_the_claims_too():
    """detection_report() is what the Studio renders, so it must carry them."""
    parser_report = misata.preview(HARD_SAAS, rows=1500)
    assert any("not understood" in w for w in parser_report.warnings)
