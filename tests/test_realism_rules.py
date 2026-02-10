import pandas as pd

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
