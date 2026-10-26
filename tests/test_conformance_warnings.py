"""Conformance warnings: a declaration that holds at a cost says what it cost.

Every such warning is a ``ConformanceWarning``, a ``MisataWarning`` and a
``UserWarning``, so a CI run can turn exactly Misata's warnings into errors
without touching anyone else's.
"""

from __future__ import annotations

import warnings

import pytest

import misata
from misata.exceptions import ConformanceWarning, MisataWarning


def _curve_schema(*, max_per_period: int, avg: float = 50.0):
    return misata.from_dict_schema({
        "__outcome_curves__": [{
            "table": "orders", "column": "amount",
            "time_column": "order_date", "time_unit": "month",
            "value_mode": "absolute", "start_date": "2025-01-01",
            "avg_transaction_value": avg,
            "min_transactions_per_period": 1,
            "max_transactions_per_period": max_per_period,
            "curve_points": [{"month": 1, "target_value": 50_000.0},
                             {"month": 3, "target_value": 50_000.0}],
        }],
        "orders": {"order_id": {"type": "integer", "primary_key": True},
                   "amount": {"type": "float", "min": 0, "max": 1_000_000},
                   "order_date": {"type": "date"}},
    }, seed=7)


def test_hierarchy():
    assert issubclass(ConformanceWarning, MisataWarning)
    assert issubclass(MisataWarning, UserWarning)
    assert misata.ConformanceWarning is ConformanceWarning
    assert misata.MisataWarning is MisataWarning


def test_row_cap_warns_and_totals_still_hold():
    schema = _curve_schema(max_per_period=20)
    with pytest.warns(ConformanceWarning) as caught:
        tables = misata.generate_from_schema(schema)

    message = str(caught[0].message)
    assert "amount: 3 of 3 periods" in message
    assert "[1, 20]" in message
    assert "avg_transaction_value=50" in message
    assert "2025-01" in message

    orders = tables["orders"]
    monthly = orders.groupby(orders["order_date"].astype("datetime64[ns]").dt.month)["amount"].sum()
    assert monthly.round(2).tolist() == [50_000.0, 50_000.0, 50_000.0]
    assert orders.groupby(orders["order_date"].astype("datetime64[ns]").dt.month).size().max() <= 20


def test_row_cap_warning_points_at_the_caller():
    with pytest.warns(ConformanceWarning) as caught:
        misata.generate_from_schema(_curve_schema(max_per_period=20))
    assert not caught[0].filename.endswith("fact_engine.py")


def test_feasible_bounds_stay_quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("error", MisataWarning)
        misata.generate_from_schema(_curve_schema(max_per_period=10_000))


def test_ci_filter_turns_conformance_into_an_error():
    with warnings.catch_warnings():
        warnings.simplefilter("error", MisataWarning)
        with pytest.raises(ConformanceWarning, match="min/max_transactions_per_period"):
            misata.generate_from_schema(_curve_schema(max_per_period=20))


def test_a_skipped_declaration_is_a_conformance_warning():
    with pytest.warns(ConformanceWarning, match="Skipping invalid __outcome_curves__"):
        misata.from_dict_schema({
            "__outcome_curves__": [{"table": "orders"}],
            "orders": {"order_id": {"type": "integer", "primary_key": True}},
        })


def test_every_warning_goes_through_the_package_helper():
    """A direct ``warnings.warn`` would bypass the category and the attribution."""
    import ast
    from pathlib import Path

    package = Path(misata.__file__).parent
    direct = []
    for path in package.rglob("*.py"):
        if path.name == "exceptions.py" and path.parent == package:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "warn" and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in {"warnings", "_warnings"}):
                direct.append(f"{path.relative_to(package)}:{node.lineno}")
    assert direct == []
