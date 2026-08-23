"""A number in a story is read correctly or refused, never mis-scaled.

The value pattern was `\\d[\\d,]*(?:\\.\\d+)?\\s*[kmb]?` in six places. It
swallowed the comma that ended a number and then read the following month's
initial as a magnitude suffix, so "Revenue curve: Jan 120000, Feb 140000,
Mar 160000" produced a February of 140,000,000,000. The run completed, the
foreign keys were intact, and the total was off by a factor of a million.
"""

import pytest

import misata
from misata.story_parser import StoryParser


@pytest.fixture(scope="module")
def parser():
    return StoryParser.__new__(StoryParser)


@pytest.mark.parametrize("raw,expected", [
    ("140000", 140_000), ("140,000", 140_000), ("2,000,000", 2_000_000),
    ("1.5M", 1_500_000), ("1.5 m", 1_500_000), ("$50k", 50_000),
    ("120000, ", 120_000),
])
def test_values_read_at_the_right_magnitude(parser, raw, expected):
    assert parser._parse_numeric_value(raw) == expected


@pytest.mark.parametrize("raw", ["140000, M", "200000, May", "abc", ""])
def test_ambiguous_values_are_refused_not_guessed(parser, raw):
    """A magnitude suffix must be attached to the digits. Anything else is a
    misread waiting to happen, and refusing lets the caller skip the point."""
    with pytest.raises(ValueError):
        parser._parse_numeric_value(raw)


def test_a_twelve_month_revenue_curve_survives_the_story():
    story = ("An ecommerce store with 1200 customers, 300 products and 4000 orders "
             "in 2026. Revenue curve: Jan 120000, Feb 140000, Mar 160000, "
             "Apr 180000, May 200000, Jun 220000, Jul 210000, Aug 230000, "
             "Sep 250000, Oct 280000, Nov 400000, Dec 320000.")
    schema = misata.parse(story, rows=1200)
    curves = schema.outcome_curves or []
    assert curves, "the declared revenue curve was dropped entirely"

    declared = [120_000, 140_000, 160_000, 180_000, 200_000, 220_000,
                210_000, 230_000, 250_000, 280_000, 400_000, 320_000]
    got = [p.get("value") or p.get("target_value") or p.get("relative_value")
           for p in curves[0].curve_points]
    assert got == pytest.approx(declared), \
        f"months were mis-scaled: {got}"


def test_the_named_months_land_on_the_declared_figure():
    """Naming three months of a twelve month year carries the last value
    forward, so the year total is not the sum of what was typed. What must
    hold is that each month actually named lands on its figure."""
    story = ("An ecommerce store with 800 customers and 2000 orders in 2026. "
             "Revenue curve: Jan 100000, Feb 120000, Mar 140000.")
    data = misata.generate_from_schema(misata.parse(story, rows=800))
    orders = data["orders"]
    amount = next(c for c in ("amount", "total", "order_total") if c in orders.columns)
    stamp = next(c for c in ("order_date", "created_at", "date") if c in orders.columns)

    monthly = orders.set_index(stamp)[amount].resample("MS").sum()
    for month, declared in ((1, 100_000), (2, 120_000), (3, 140_000)):
        got = float(monthly[monthly.index.month == month].iloc[0])
        assert got == pytest.approx(declared, abs=1.0), \
            f"month {month}: got {got:,.2f}, story said {declared:,}"
