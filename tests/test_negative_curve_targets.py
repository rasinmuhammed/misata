"""A declared outcome-curve target can legitimately be negative.

A ledger's net change, a P&L delta, a cash flow: none of these are bounded
below zero the way revenue or a transaction count is. `_allocate_row_counts`
clamped every target to `max(target, 0)` before deciding how many rows a
period gets, so a period with a negative target was judged inactive and
received zero rows. `_generate_exact_values` had the matching defect one
layer down: `total_units <= 0` treated "negative" the same as "nothing to
generate" and returned an all-zero column. Together, a schema declaring six
positive months and six negative months came back with the six negative
months completely empty and the total silently wrong, no warning raised.

This is not a boundary case. Nobody generating a real ledger or a real P&L
avoids negative periods; they are the majority of what makes such data look
like a real business rather than a machine that only ever grows.
"""

import numpy as np
import misata


def _signed_schema(points, decimals=2, lo=-100_000, hi=100_000):
    return {
        "t": {
            "__rows__": 200,
            "k": {"type": "integer", "primary_key": True},
            "d": {"type": "datetime", "min_date": "2024-01-01", "max_date": "2024-12-31"},
            "v": {"type": "float", "min": lo, "max": hi, "decimals": decimals},
        },
        "__outcome_curves__": [{
            "table": "t", "column": "v", "time_column": "d", "time_unit": "month",
            "pattern_type": "custom", "value_mode": "absolute", "start_date": "2024-01-01",
            "curve_points": [{"date": d, "value": v} for d, v in points],
        }],
    }


def test_a_negative_month_gets_rows_and_the_right_sign():
    points = [("2024-01-01", 5000.0), ("2024-02-01", -3000.0)]
    tables = misata.generate_from_schema(misata.from_dict_schema(_signed_schema(points), seed=1))
    df = tables["t"]
    feb = df[df["d"].astype(str).str.startswith("2024-02")]
    assert len(feb) > 0, "a negative-target period must not come back empty"
    assert abs(feb["v"].sum() - (-3000.0)) < 0.01
    assert (feb["v"] < 0).all(), "every row in an all-negative-target period should be negative"


def test_twelve_months_alternating_sign_all_land_exact():
    net = {
        "2024-01": 41200.00, "2024-02": -12000.00, "2024-03": 52300.00,
        "2024-04": -80000.00, "2024-05": 61000.00, "2024-06": -45450.00,
        "2024-07": 33300.00, "2024-08": -8700.00, "2024-09": 47100.00,
        "2024-10": -39800.00, "2024-11": 62200.00, "2024-12": -95000.00,
    }
    points = [(f"{m}-01", v) for m, v in net.items()]
    tables = misata.generate_from_schema(
        misata.from_dict_schema(_signed_schema(points, lo=-25_000, hi=25_000), seed=11)
    )
    df = tables["t"]
    import pandas as pd
    month = pd.to_datetime(df["d"]).dt.strftime("%Y-%m")
    actual = df.groupby(month)["v"].sum()
    counts = df.groupby(month).size()
    for m, v in net.items():
        assert counts.get(m, 0) > 0, f"{m} came back empty"
        assert abs(actual.get(m, 0.0) - v) < 0.01, f"{m}: declared {v}, got {actual.get(m, 0.0)}"


def test_a_zero_target_period_still_correctly_gets_no_rows():
    # The fix must not turn "genuinely zero" into "negative" or vice versa.
    points = [("2024-01-01", 5000.0), ("2024-02-01", 0.0), ("2024-03-01", -2000.0)]
    tables = misata.generate_from_schema(misata.from_dict_schema(_signed_schema(points), seed=2))
    df = tables["t"]
    feb = df[df["d"].astype(str).str.startswith("2024-02")]
    assert len(feb) == 0 or abs(feb["v"].sum()) < 0.01


def test_declared_row_bounds_still_respected_when_the_target_is_negative():
    points = [("2024-01-01", -50_000.0)]
    schema = _signed_schema(points, lo=-2000, hi=2000)
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=3))
    v = tables["t"]["v"]
    assert v.min() >= -2000
    assert v.max() <= 2000
    assert abs(v.sum() - (-50_000.0)) < 0.5
