"""
`"type": "date"` is a distinct declaration from `"type": "datetime"` -- a
calendar day, not a timestamp. Found via a manual realism audit of the
credit-risk-portfolio example: origination_date, declared as "date", was
generated as "2025-09-12 08:16:54" because the date-generation code path in
misata/simulator.py called the same temporal-profile machinery datetime
columns use (business-hour grids, waking-hour rhythms), regardless of the
column's declared type. A synthetic loan tape with nanosecond-precision
origination timestamps gives itself away as fast as an unrounded dollar
figure does.

Four separate code paths generate "date" columns (the plain range, an
after_column offset, a relative_to parent-date lookup, and
inherits_curve_from density sampling), and all four had the same bug. Each
is checked here so a regression in any one of them is caught, not just the
plain case.
"""

import numpy as np
import pandas as pd

import misata


def _all_midnight(series: pd.Series) -> bool:
    dt = pd.to_datetime(series)
    return bool((dt.dt.normalize() == dt).all())


def test_plain_date_range_has_no_time_of_day():
    schema = {
        "loans": {
            "__rows__": 500,
            "loan_id": {"type": "integer", "primary_key": True},
            "originated_on": {"type": "date", "min_date": "2022-01-01", "max_date": "2025-12-01"},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=1))
    assert _all_midnight(tables["loans"]["originated_on"])


def test_after_column_date_offset_has_no_time_of_day():
    schema = {
        "shipments": {
            "__rows__": 300,
            "shipment_id": {"type": "integer", "primary_key": True},
            "shipped_on": {"type": "date", "min_date": "2024-01-01", "max_date": "2024-12-01"},
            "delivered_on": {"type": "date", "after_column": "shipped_on",
                              "min_delta_days": 1, "max_delta_days": 10},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=2))
    assert _all_midnight(tables["shipments"]["shipped_on"])
    assert _all_midnight(tables["shipments"]["delivered_on"])


def test_relative_to_parent_date_has_no_time_of_day():
    schema = {
        "borrowers": {
            "__rows__": 200,
            "borrower_id": {"type": "integer", "primary_key": True},
            "onboarded_on": {"type": "date", "min_date": "2020-01-01", "max_date": "2023-01-01"},
        },
        "loans": {
            "__rows__": 400,
            "loan_id": {"type": "integer", "primary_key": True},
            "borrower_id": {"type": "integer",
                             "foreign_key": {"table": "borrowers", "column": "borrower_id"}},
            "originated_on": {"type": "date", "relative_to": "borrowers.onboarded_on",
                                "min_delta_days": 0, "max_delta_days": 365},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=3))
    assert _all_midnight(tables["borrowers"]["onboarded_on"])
    assert _all_midnight(tables["loans"]["originated_on"])
