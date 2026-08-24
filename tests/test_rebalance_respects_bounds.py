"""A rebalanced bucket must still honour the column's declared bounds.

The engine fits values inside [min, max] when it first generates a curve, but
`rebalance()` regenerates any bucket whose sum drifted after realism and events
ran. That second path was calling the same generator without passing the bounds
along, so it hit the aggregate again and quietly undid the fitting: a salary
column declared 45,000 to 350,000 came back holding 1,808 and 815,895 while
every monthly total was exact to the unit.

Integer columns (decimals=0) are where it showed, because their sums drift by a
whole unit and so almost always trip the rebalance, but nothing about the defect
was specific to them.
"""

import misata


def _schema(lo, hi, decimals, per_month):
    points = [
        {"date": f"2024-{m:02d}-01" if m <= 12 else f"2025-{m - 12:02d}-01",
         "value": per_month}
        for m in range(1, 25)
    ]
    return {
        "f": {
            "__rows__": 2000,
            "k": {"type": "integer", "primary_key": True},
            "t": {"type": "datetime", "min_date": "2024-01-01", "max_date": "2025-12-31"},
            "v": {"type": "float", "min": lo, "max": hi, "decimals": decimals},
        },
        "__outcome_curves__": [{
            "table": "f", "column": "v", "time_column": "t", "time_unit": "month",
            "pattern_type": "custom", "value_mode": "absolute",
            "start_date": "2024-01-01", "curve_points": points,
        }],
    }


def _run(lo, hi, decimals, per_month, seed):
    schema = _schema(lo, hi, decimals, per_month)
    return misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))["f"]["v"]


def test_integer_column_stays_inside_declared_bounds():
    # 14,583,333 across ~83 rows a month wants a mean of ~175,000, which sits
    # squarely inside the declared range. There is no excuse for leaving it.
    values = _run(45_000, 350_000, 0, 14_583_333, seed=7)
    assert values.min() >= 45_000
    assert values.max() <= 350_000


def test_the_totals_are_still_exact_after_fitting():
    per_month = 14_583_333
    values = _run(45_000, 350_000, 0, per_month, seed=7)
    assert values.sum() == per_month * 24


def test_holds_across_seeds():
    for seed in (3, 7, 11, 29, 101):
        values = _run(45_000, 350_000, 0, 14_583_333, seed=seed)
        assert values.min() >= 45_000, seed
        assert values.max() <= 350_000, seed


def test_decimal_column_was_never_broken_and_still_is_not():
    values = _run(10, 24_000, 2, 1_000_000, seed=7)
    assert values.min() >= 10
    assert values.max() <= 24_000
    assert abs(values.sum() - 24_000_000) < 0.5
