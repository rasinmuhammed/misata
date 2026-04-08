import numpy as np
import pandas as pd
import pytest

from misata.realism import apply_realism_rules


def test_realism_rules_basic():
    df = pd.DataFrame(
        {
            "created_at": ["2024-01-10", "2024-01-05"],
            "updated_at": ["2024-01-01", "2024-01-07"],
            "start_date": ["2024-01-10", "2024-01-01"],
            "end_date": ["2024-01-05", None],
            "quantity": [2, 3],
            "unit_price": [10.0, 20.0],
            "total": [0.0, 0.0],
            "plan": ["Pro", "Free"],
            "price": [0.0, 0.0],
            "status": ["active", "cancelled"],
        }
    )

    out = apply_realism_rules(df, "orders")

    created = pd.to_datetime(out["created_at"], errors="coerce")
    updated = pd.to_datetime(out["updated_at"], errors="coerce")
    assert (updated >= created).all()

    start = pd.to_datetime(out["start_date"], errors="coerce")
    end = pd.to_datetime(out["end_date"], errors="coerce")
    valid_mask = end.notna()
    assert (end[valid_mask] >= start[valid_mask]).all()

    assert out.loc[0, "price"] == 19.99
    assert out.loc[1, "price"] == 0.0

    assert out.loc[0, "end_date"] is pd.NaT or pd.isna(out.loc[0, "end_date"])
    assert pd.notna(out.loc[1, "end_date"])

    expected_total_0 = round(2 * 10.0, 2)
    expected_total_1 = round(3 * 20.0, 2)
    assert abs(out.loc[0, "total"] - expected_total_0) < 1.0
    assert abs(out.loc[1, "total"] - expected_total_1) < 1.0


# ── cost fix: only violations are touched ────────────────────────────────────

def test_cost_valid_rows_are_not_overwritten():
    """Rows where cost < price must be left untouched."""
    df = pd.DataFrame({"price": [100.0, 200.0], "cost": [40.0, 80.0]})
    out = apply_realism_rules(df.copy(), "products")
    assert out.loc[0, "cost"] == pytest.approx(40.0)
    assert out.loc[1, "cost"] == pytest.approx(80.0)


def test_cost_violation_is_corrected():
    """Rows where cost >= price must be fixed to cost < price."""
    df = pd.DataFrame({"price": [100.0, 50.0], "cost": [150.0, 50.0]})
    out = apply_realism_rules(df.copy(), "products")
    assert out.loc[0, "cost"] < 100.0
    assert out.loc[1, "cost"] < 50.0


def test_cost_null_is_filled():
    """Null cost values must be generated as a valid margin of price."""
    df = pd.DataFrame({"price": [100.0], "cost": [np.nan]})
    out = apply_realism_rules(df.copy(), "products")
    assert pd.notna(out.loc[0, "cost"])
    assert out.loc[0, "cost"] < 100.0


# ── delivered_at: only violated rows are corrected ───────────────────────────

def test_delivered_at_valid_rows_are_not_overwritten():
    """Rows where delivered_at > created_at must not be changed."""
    df = pd.DataFrame({
        "created_at": ["2024-01-01"],
        "delivered_at": ["2024-01-10"],
    })
    out = apply_realism_rules(df.copy(), "orders")
    assert str(out.loc[0, "delivered_at"])[:10] == "2024-01-10"


def test_delivered_at_violation_is_corrected():
    """Rows where delivered_at <= created_at must be pushed forward."""
    df = pd.DataFrame({
        "created_at": ["2024-03-01"],
        "delivered_at": ["2024-02-01"],
    })
    out = apply_realism_rules(df.copy(), "orders")
    created = pd.to_datetime(out.loc[0, "created_at"])
    delivered = pd.to_datetime(out.loc[0, "delivered_at"])
    assert delivered > created


# ── reproducibility: seeded rng produces identical output ────────────────────

def test_apply_realism_rules_is_reproducible_with_seed():
    df = pd.DataFrame({
        "created_at": ["2024-01-10", "2024-01-05"],
        "updated_at": ["2024-01-01", "2024-01-07"],
        "price": [100.0, 200.0],
        "cost": [200.0, 300.0],
    })
    out1 = apply_realism_rules(df.copy(), "t", rng=np.random.default_rng(0))
    out2 = apply_realism_rules(df.copy(), "t", rng=np.random.default_rng(0))
    pd.testing.assert_frame_equal(out1, out2)


# ── schema date defaults are fixed (not datetime.now()) ──────────────────────

def test_date_column_default_range_is_fixed():
    from misata.schema import Column
    col = Column(name="created_at", type="date")
    assert col.distribution_params["start"] == "2020-01-01"
    assert col.distribution_params["end"] == "2024-12-31"
