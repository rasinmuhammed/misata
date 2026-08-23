"""An outcome curve must hit its target without breaking the column's bounds.

Both were declared, and the engine used to satisfy the aggregate and quietly
push rows outside the declared min/max: a target of 150,000 across 400 rows
produced invoices of 6.71 against a declared min of 49. It warned, but a
warning is not the same as the declaration holding.

Both hold whenever `lo*n <= T <= hi*n`. When they genuinely cannot, the
aggregate is kept and the conflict is reported with the arithmetic, which is
the behaviour that was always documented for the impossible case.

Two code paths reach this: exact/absolute targets go through the FactEngine,
relative multipliers go through the simulator. Both are covered.
"""

import warnings

import pytest

import misata

CURVE = [{"period": p, "value": v} for p, v in [
    ("2026-01", 150_000), ("2026-02", 165_000), ("2026-03", 180_000),
    ("2026-04", 195_000), ("2026-05", 205_000), ("2026-06", 225_000)]]


def _exact(lo, hi, rows=2400, seed=11):
    return misata.generate_from_schema({
        "name": "t", "seed": seed,
        "tables": {"invoices": {"rows": rows, "columns": {
            "invoice_id": {"type": "int", "unique": True, "min": 1, "max": rows * 20},
            "amount": {"type": "float", "min": lo, "max": hi},
            "issued_at": {"type": "datetime", "start": "2026-01-01", "end": "2026-06-30"}}}},
        "outcome_curves": [{
            "table": "invoices", "column": "amount", "time_column": "issued_at",
            "time_unit": "month", "pattern_type": "custom",
            "value_mode": "absolute", "curve_points": CURVE}]})["invoices"]


@pytest.mark.parametrize("lo,hi", [(49, 9000), (100, 1200), (200, 800)])
def test_exact_curve_keeps_every_row_inside_declared_bounds(lo, hi):
    df = _exact(lo, hi)
    a = df["amount"]
    assert int((a < lo).sum()) == 0, f"{int((a < lo).sum())} row(s) below declared min={lo}"
    assert int((a > hi).sum()) == 0, f"{int((a > hi).sum())} row(s) above declared max={hi}"


@pytest.mark.parametrize("lo,hi", [(49, 9000), (100, 1200), (200, 800)])
def test_bounds_do_not_cost_the_aggregate(lo, hi):
    """Fitting into the bounds must not move a single period total."""
    df = _exact(lo, hi)
    monthly = df.set_index("issued_at")["amount"].resample("MS").sum()
    assert len(monthly) == len(CURVE)
    for got, point in zip(monthly, CURVE):
        assert abs(got - point["value"]) < 0.005, \
            f"period {point['period']}: got {got:,.2f}, declared {point['value']:,.2f}"


def test_relative_curve_path_also_respects_bounds():
    """Seasonal multipliers go through the simulator, not the FactEngine."""
    pts = [{"month": m, "relative_value": v} for m, v in
           [(1, .8), (2, .9), (3, 1.0), (4, 1.1), (5, 1.2), (6, 1.3),
            (7, 1.2), (8, 1.1), (9, 1.0), (10, 1.2), (11, 1.6), (12, 2.0)]]
    a = misata.generate_from_schema({
        "name": "t", "seed": 5,
        "tables": {"sales": {"rows": 300, "columns": {
            "id": {"type": "int", "unique": True, "min": 1, "max": 3000},
            "amount": {"type": "float", "min": 10, "max": 500},
            "at": {"type": "datetime", "start": "2026-01-01", "end": "2026-12-31"}}}},
        "outcome_curves": [{
            "table": "sales", "column": "amount", "time_column": "at",
            "time_unit": "month", "pattern_type": "seasonal",
            "value_mode": "relative", "curve_points": pts}]})["sales"]["amount"]
    assert int(((a < 10) | (a > 500)).sum()) == 0


def test_an_impossible_target_keeps_the_aggregate_and_says_so():
    """1,000 across 100 rows cannot hold a declared min of 50: the floor alone
    is 5,000. The aggregate wins, and the sacrifice is reported."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        df = misata.generate_from_schema({
            "name": "t", "seed": 3,
            "tables": {"t": {"rows": 100, "columns": {
                "id": {"type": "int", "unique": True, "min": 1, "max": 1000},
                "amt": {"type": "float", "min": 50, "max": 900},
                "at": {"type": "datetime", "start": "2026-01-01", "end": "2026-01-31"}}}},
            "outcome_curves": [{
                "table": "t", "column": "amt", "time_column": "at",
                "time_unit": "month", "pattern_type": "custom",
                "value_mode": "absolute",
                "curve_points": [{"period": "2026-01", "value": 1000}]}]})["t"]

    assert abs(df["amt"].sum() - 1000) < 0.005, "the aggregate must still be exact"
    assert any("infeasible" in str(w.message).lower() for w in caught), \
        "an impossible bound must be reported, not hidden"
