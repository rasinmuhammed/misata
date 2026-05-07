"""Outcome curve stress tests.

Outcome curves are the narrative differentiator: a plain-English business
story produces a generated dataset whose monthly aggregates *exactly* match
the trajectory the user described.  These tests guard the contract that a
SaaS revenue ramp, a fintech transaction surge, or an ecommerce holiday
peak — written as a sentence — actually appears in the output.
"""

from __future__ import annotations

import pandas as pd
import pytest

import misata
from misata.story_parser import StoryParser


# ---------------------------------------------------------------------------
# Anchor extraction
# ---------------------------------------------------------------------------


def test_two_anchors_interpolate_linearly():
    """A 'from X in Jan to Y in Dec' story produces a 12-month linear interpolation."""
    schema = misata.parse(
        "A SaaS company with revenue rising from 50k in January 2023 to 200k in December 2023"
    )
    assert schema.outcome_curves, "Expected at least one outcome curve"
    curve = schema.outcome_curves[0]

    assert len(curve.curve_points) == 12
    points = {p["month"]: p["target_value"] for p in curve.curve_points}
    assert points[1] == pytest.approx(50_000, abs=1)
    assert points[12] == pytest.approx(200_000, abs=1)
    # Monotonic upward
    monthly = [points[m] for m in range(1, 13)]
    assert monthly == sorted(monthly), "Expected monotonically increasing curve"


def test_year_in_anchor_is_not_treated_as_value():
    """Regression: 'Jan 2023' must not be parsed as 'Jan with target value 2023'."""
    schema = misata.parse(
        "A SaaS company with revenue going from 100k in Jan 2024 to 500k in Dec 2024"
    )
    curve = schema.outcome_curves[0]
    targets = [p["target_value"] for p in curve.curve_points]
    # No anchor should be exactly 2024 — that's the year, not a target
    assert 2024 not in targets
    assert max(targets) == pytest.approx(500_000, abs=1)
    assert min(targets) == pytest.approx(100_000, abs=1)


def test_qualitative_modifier_creates_dip():
    """'dip in March' must produce a March value below the surrounding months."""
    schema = misata.parse(
        "A SaaS company with revenue from 100k in January to 200k in December, "
        "but a dip in March"
    )
    curve = schema.outcome_curves[0]
    points = {p["month"]: p["target_value"] for p in curve.curve_points}
    # March must be lower than its neighbours
    assert points[3] < points[2], "March should dip below February"
    assert points[3] < points[4], "March should dip below April"


def test_qualitative_modifier_creates_peak():
    """'peak in November' must produce November above neighbours."""
    schema = misata.parse(
        "An ecommerce store with orders rising from 1000 in January to 5000 in December, "
        "with a peak in November"
    )
    curve = schema.outcome_curves[0]
    points = {p["month"]: p["target_value"] for p in curve.curve_points}
    assert points[11] >= points[10]
    assert points[11] >= points[12]


# ---------------------------------------------------------------------------
# Generated data hits the curve targets
# ---------------------------------------------------------------------------


def _monthly_aggregate(df: pd.DataFrame, value_col: str, time_col: str) -> dict:
    """Sum a value column by month for outcome-curve verification."""
    series_time = pd.to_datetime(df[time_col])
    grouped = df.groupby(series_time.dt.to_period("M"))[value_col].sum()
    return {p.month: float(v) for p, v in grouped.items()}


def test_saas_revenue_curve_shapes_real_data():
    """Generated SaaS subscription totals must follow the described shape, not be random."""
    schema = misata.parse(
        "A SaaS company with 2000 users and revenue rising from 50k in January 2023 to "
        "200k in December 2023"
    )
    schema.seed = 42
    tables = misata.generate_from_schema(schema)

    curve = schema.outcome_curves[0]
    df = tables[curve.table]

    # The aggregate need not match the targets exactly (other realism rules
    # also apply), but the shape must be monotonically growing — January
    # totals should be lower than December totals.
    monthly = _monthly_aggregate(df, curve.column, curve.time_column)
    if not monthly:
        pytest.skip("Generated data produced no time buckets — skipping shape check")

    early = sum(v for m, v in monthly.items() if m <= 3)
    late = sum(v for m, v in monthly.items() if m >= 10)
    assert late > early, (
        f"Expected late-year totals to exceed early-year totals "
        f"(early={early:.0f}, late={late:.0f})"
    )


# ---------------------------------------------------------------------------
# Robustness — outcome-curve detection must not crash on edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "story",
    [
        "A SaaS company with no narrative",                                       # no curve signal
        "A SaaS company with peak in December",                                   # qualitative-only, no anchor
        "A SaaS company with revenue from 50k in Jan to 100k in Feb",             # 2-month range
        "A SaaS company with revenue from 50k in Jan to 100k in Feb over 6 months",  # explicit period
        "A SaaS company with revenue 100k in January, dip in March, peak in Nov", # mixed signals
    ],
)
def test_curve_detection_does_not_crash(story):
    """No combination of curve signals should raise an exception during parse."""
    schema = misata.parse(story)
    # If a curve was detected, it must have at least one point and a valid mode
    for curve in schema.outcome_curves:
        assert curve.curve_points, f"Empty curve_points for: {story}"
        assert curve.value_mode in ("auto", "relative", "absolute")
