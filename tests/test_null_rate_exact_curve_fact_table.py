"""A declared null_rate must hold on a table that also carries an exact
outcome curve.

Two different code paths generate a table's rows: the normal row-wise batch
loop (``_generate_table_batches``), and the exact-curve fact-table path
(``_generate_fact_table``) used whenever a table carries an outcome curve
with ``value_mode: absolute``. The row-wise path's last step is
``_apply_null_rates``. The fact-table path never called it at all --
any column with a declared ``null_rate`` on a table that also had an exact
curve came back 100% populated, silently, no matter what rate was declared.

Found building Backlot's expanded Snowplow schema: ``events.user_id`` had
``null_rate: 0.65`` (a realistic mix of logged-in and anonymous sessions),
and ``events`` also carries an exact curve on ``page_view_unit`` (an
outcome-curve-controlled row COUNT). ``user_id`` came back fully non-null.

The curve-controlled column itself must NOT be null-eligible even when
declared nullable -- nulling it would silently break the exact aggregate
this code path exists to guarantee. Both are covered below.
"""

from __future__ import annotations

import pytest

import misata


def _schema(null_rate: float = 0.65, event_count: int = 3000):
    return {
        "events": {
            "__rows__": event_count,
            "event_id": {"type": "integer", "primary_key": True},
            "occurred_at": {"type": "datetime", "min_date": "2025-01-01", "max_date": "2025-03-31"},
            "page_view_unit": {"type": "integer", "enum": [1]},
            "user_id": {
                "type": "string",
                "enum": ["u-1", "u-2", "u-3", "u-4", "u-5"],
                "nullable": True,
                "null_rate": null_rate,
            },
        },
        "__outcome_curves__": [{
            "table": "events", "column": "page_view_unit", "time_column": "occurred_at",
            "time_unit": "month", "pattern_type": "custom", "value_mode": "absolute",
            "start_date": "2025-01-01",
            "curve_points": [
                {"date": "2025-01-01", "value": 150.0},
                {"date": "2025-02-01", "value": 210.0},
                {"date": "2025-03-01", "value": 300.0},
            ],
        }],
    }


def test_null_rate_holds_on_a_table_with_an_exact_outcome_curve():
    schema_dict = misata.from_dict_schema(_schema(null_rate=0.65), seed=7)
    events = misata.generate_from_schema(schema_dict)["events"]

    null_frac = events["user_id"].isna().mean()
    assert null_frac == pytest.approx(0.65, abs=0.05), (
        f"declared null_rate=0.65 on user_id produced {null_frac:.3f} nulls -- "
        "the exact-curve fact-table path is silently skipping null application"
    )


def test_the_curve_controlled_column_itself_stays_fully_populated():
    # page_view_unit is not declared nullable, but this guards the more
    # important invariant directly: whatever null handling runs, the
    # curve's own exact total must survive it untouched.
    schema_dict = misata.from_dict_schema(_schema(null_rate=0.65), seed=7)
    events = misata.generate_from_schema(schema_dict)["events"]

    assert events["page_view_unit"].isna().sum() == 0
    jan = events[events["occurred_at"].astype(str).str.startswith("2025-01")]
    assert jan["page_view_unit"].sum() == pytest.approx(150.0, abs=0.5)


def test_null_rate_zero_still_produces_no_nulls():
    schema_dict = misata.from_dict_schema(_schema(null_rate=0.0), seed=3)
    events = misata.generate_from_schema(schema_dict)["events"]
    assert events["user_id"].isna().sum() == 0
