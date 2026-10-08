"""Exact group shares must not break the column's declared min/max.

`apply_group_shares` rescaled each group with one multiplier, which hits the
total and moves every row by the same factor. Next to an exact outcome curve
that pushed 12-15% of rows below the declared minimum with no warning, and
on shares alone it let a column declared max 900 reach 902.44. The shares
were right and the bounds were quietly wrong.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata.shares import fit_total_within_bounds

MONTHLY = [40000, 46000, 52000, 61000, 70000, 80000, 90000, 104000,
           118000, 135000, 152000, 170000]
SHARES = {"Starter": 0.2, "Pro": 0.5, "Enterprise": 0.3}


def _schema(curve, lo=20, hi=900, rows=30000):
    s = {"t": {"__rows__": rows,
               "id": {"type": "integer", "primary_key": True},
               "d": {"type": "date", "start": "2025-01-01", "end": "2025-12-31"},
               "plan": {"type": "string", "enum": list(SHARES)},
               "amount": {"type": "float", "min": lo, "max": hi}},
         "__group_shares__": [{"table": "t", "group_column": "plan",
                               "measure": "amount", "shares": SHARES}]}
    if curve:
        s["__outcome_curves__"] = [{
            "table": "t", "column": "amount", "time_column": "d",
            "time_unit": "month", "value_mode": "absolute",
            "curve_points": [{"month": i + 1, "value": v}
                             for i, v in enumerate(MONTHLY)]}]
    return s


def _gen(schema, seed=1):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))["t"]


@pytest.mark.parametrize("curve", [False, True])
def test_shares_hold_and_no_row_leaves_the_declared_bounds(curve):
    df = _gen(_schema(curve))
    assert df.amount.min() >= 20 and df.amount.max() <= 900
    got = df.groupby("plan").amount.sum() / df.amount.sum()
    for k, v in SHARES.items():
        assert got[k] == pytest.approx(v, abs=1e-4)


def test_the_curve_stays_exact_with_shares_and_bounds_together():
    df = _gen(_schema(True))
    df["m"] = pd.to_datetime(df.d).dt.month
    for i, v in enumerate(MONTHLY):
        assert df[df.m == i + 1].amount.sum() == pytest.approx(v, abs=0.01)


def test_same_seed_is_identical():
    a, b = _gen(_schema(True), 5), _gen(_schema(True), 5)
    assert a.equals(b)


class TestFitTotalWithinBounds:
    def test_hits_the_total_to_the_cent_inside_the_bounds(self):
        rng = np.random.default_rng(0)
        v = rng.lognormal(3, 1.2, 500)
        out = fit_total_within_bounds(v, 12345.67, 5.0, 400.0)
        assert out.sum() == pytest.approx(12345.67, abs=1e-6)
        assert out.min() >= 5.0 and out.max() <= 400.0

    def test_returns_none_when_no_assignment_can_satisfy_both(self):
        v = np.ones(10)
        assert fit_total_within_bounds(v, 5.0, 1.0, 100.0) is None   # below lo*n
        assert fit_total_within_bounds(v, 5000.0, 1.0, 100.0) is None  # above hi*n

    def test_a_total_exactly_at_the_floor_puts_every_row_on_it(self):
        out = fit_total_within_bounds(np.arange(1, 6, dtype=float), 50.0, 10.0, 90.0)
        assert out.tolist() == [10.0] * 5

    def test_all_zero_input_is_spread_evenly(self):
        out = fit_total_within_bounds(np.zeros(4), 100.0, 0.0, 60.0)
        assert out.sum() == pytest.approx(100.0) and out.max() <= 60.0

    def test_one_sided_bound(self):
        out = fit_total_within_bounds(np.array([1.0, 1.0, 100.0]), 90.0, 10.0, None)
        assert out.sum() == pytest.approx(90.0) and out.min() >= 10.0

    def test_empty(self):
        assert fit_total_within_bounds(np.array([]), 0.0, 0.0, 1.0).size == 0


def test_an_unholdable_share_warns_instead_of_silently_leaving_the_bounds():
    """A 0.1% group of 200 rows still needs one row, and one row at 0.1% of
    the total is far under the declared minimum. The exact share wins, and it
    says so."""
    s = _schema(False, lo=250, hi=350, rows=200)
    s["__group_shares__"][0]["shares"] = {"Starter": 0.001, "Pro": 0.5, "Enterprise": 0.499}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        misata.generate_from_schema(misata.from_dict_schema(s, seed=1))
    assert any("cannot hold inside the column's declared bounds" in str(x.message) for x in w)


def test_a_column_with_no_bounds_behaves_as_before():
    s = _schema(False)
    s["t"]["amount"] = {"type": "float"}
    df = _gen(s)
    got = df.groupby("plan").amount.sum() / df.amount.sum()
    for k, v in SHARES.items():
        assert got[k] == pytest.approx(v, abs=1e-4)
