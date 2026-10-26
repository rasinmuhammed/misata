"""Schemas as an agent writes them for the MCP tool, each a case that shipped wrong data with a clean report.

Found by running two everyday prompts (a SaaS MRR story, a store's 2025 orders) through generate_from_schema
exactly as a model wrote them, then reading the rows back with plain pandas."""
import numpy as np
import pandas as pd
import pytest

import misata
from misata.coherence import coherence_audit
from misata.feasibility import find_conflicts


def _build(schema, seed=7):
    cfg = misata.from_dict_schema(schema, row_count=500, seed=seed)
    return cfg, misata.generate_from_schema(cfg)


def test_date_min_max_bound_the_dates():
    # the tool documents min/max as "numeric or date bounds"; only min_date/start were read, so 2025 dates came back 2020-24
    _, t = _build({"events": {"__rows__": 400, "event_id": {"type": "integer", "primary_key": True},
                              "at": {"type": "date", "min": "2025-03-01", "max": "2025-08-31"}}})
    at = pd.to_datetime(t["events"]["at"])
    assert at.min() >= pd.Timestamp("2025-03-01") and at.max() <= pd.Timestamp("2025-08-31")


def test_inline_foreign_key_carries_min_children():
    schema = {"orders": {"__rows__": 300, "order_id": {"type": "integer", "primary_key": True},
                         "total": {"type": "float", "rollup": {"from_table": "lines", "fk": "order_id", "agg": "sum", "column": "amount"}}},
              "lines": {"__rows__": 450, "line_id": {"type": "integer", "primary_key": True},
                        "order_id": {"type": "integer", "foreign_key": {"table": "orders", "column": "order_id", "min_children": 1}},
                        "amount": {"type": "float", "distribution": "uniform", "min": 5, "max": 50, "decimals": 2}}}
    cfg, t = _build(schema)
    assert any(r.min_children == 1 for r in cfg.relationships)
    assert t["orders"]["order_id"].isin(t["lines"]["order_id"]).all()
    assert (t["orders"]["total"] > 0).all()


def test_empty_rollups_are_reported():
    schema = {"orders": {"__rows__": 300, "order_id": {"type": "integer", "primary_key": True},
                         "total": {"type": "float", "rollup": {"from_table": "lines", "fk": "order_id", "agg": "sum", "column": "amount"}}},
              "lines": {"__rows__": 300, "line_id": {"type": "integer", "primary_key": True},
                        "order_id": {"type": "integer", "foreign_key": {"table": "orders", "column": "order_id"}},
                        "amount": {"type": "float", "distribution": "uniform", "min": 5, "max": 50, "decimals": 2}}}
    cfg, t = _build(schema)
    if t["orders"]["order_id"].isin(t["lines"]["order_id"]).mean() > 0.95:
        pytest.skip("this seed gave every order a line")
    kinds = {f.kind for f in coherence_audit(t, schema=cfg).findings}
    assert "empty_rollup" in kinds


def _monthly(points, mode="absolute", rows=2000):
    return {"invoices": {"__rows__": rows, "invoice_id": {"type": "integer", "primary_key": True},
                         "period_start": {"type": "date", "min": "2024-11-01", "max": "2025-10-31"},
                         "amount": {"type": "float", "distribution": "lognormal", "mu": 5, "sigma": 0.6, "decimals": 2}},
            "__outcome_curves__": [{"table": "invoices", "column": "amount", "time_column": "period_start", "time_unit": "month",
                                    "value_mode": mode, "start_date": "2024-11-01", "curve_points": points}]}


def test_anchor_points_fill_the_months_between():
    # "$50k in month 1 ... $200k in month 12" are anchors: the months between were left with no rows at all
    cfg, t = _build(_monthly([{"month": 1, "target_value": 50000}, {"month": 7, "target_value": 110000}, {"month": 12, "target_value": 160000}]))
    inv = t["invoices"]
    by = inv.groupby(pd.to_datetime(inv.period_start).dt.to_period("M")).amount.sum()
    assert len(by) == 12
    assert by[pd.Period("2024-11")] == pytest.approx(50000, abs=0.01)
    assert by[pd.Period("2025-05")] == pytest.approx(110000, abs=0.01)
    assert by[pd.Period("2025-10")] == pytest.approx(160000, abs=0.01)
    assert by[pd.Period("2025-02")] == pytest.approx(80000, abs=0.01)  # on the line between month 1 and month 7
    assert not [f for f in coherence_audit(t, schema=cfg).findings if f.kind == "outcome_curve_mismatch"]


def test_count_curve_sets_rows_per_month():
    pts = [{"month": m, "target_value": v} for m, v in zip(range(1, 13), [100, 90, 110, 120, 130, 125, 120, 140, 150, 170, 260, 300])]
    cfg, t = _build(_monthly(pts, mode="count"))
    by = pd.to_datetime(t["invoices"].period_start).dt.to_period("M").value_counts().sort_index()
    assert by.tolist() == [100, 90, 110, 120, 130, 125, 120, 140, 150, 170, 260, 300]
    assert not [f for f in coherence_audit(t, schema=cfg).findings if f.kind == "outcome_curve_mismatch"]


def test_rate_curve_reads_curve_points():
    # outcome curves take "curve_points"; an agent wrote it on a rate curve too, and it was ignored: the rate held nothing
    schema = {"accounts": {"__rows__": 3000, "account_id": {"type": "integer", "primary_key": True},
                           "created_at": {"type": "date", "min": "2024-11-01", "max": "2025-10-31"},
                           "churned": {"type": "boolean"}},
              "__rate_curves__": [{"table": "accounts", "column": "churned", "time_column": "created_at", "time_unit": "month",
                                   "curve_points": [{"period": "2024-11", "rate": 0.6}, {"period": "2025-01", "rate": 0.1},
                                                    {"period": "2025-10", "rate": 0.1}]}]}
    cfg, t = _build(schema)
    a = t["accounts"]
    m = pd.to_datetime(a.created_at).dt.to_period("M")
    assert a[m == pd.Period("2024-11")].churned.mean() == pytest.approx(0.6, abs=0.03)
    assert a[m == pd.Period("2025-10")].churned.mean() == pytest.approx(0.1, abs=0.03)
    with pytest.warns(UserWarning, match="no rate_points"):
        misata.from_dict_schema({**schema, "__rate_curves__": [{"table": "accounts", "column": "churned"}]}, row_count=10, seed=1)


def test_curve_on_a_formula_column_is_refused():
    schema = {"orders": {"__rows__": 200, "order_id": {"type": "integer", "primary_key": True},
                         "ordered_at": {"type": "date", "min": "2025-01-01", "max": "2025-12-31"}},
              "lines": {"__rows__": 600, "line_id": {"type": "integer", "primary_key": True},
                        "order_id": {"type": "integer", "foreign_key": {"table": "orders", "column": "order_id"}},
                        "ordered_at": {"type": "date", "formula": "@orders.ordered_at"},
                        "quantity": {"type": "integer", "distribution": "uniform", "min": 1, "max": 3},
                        "unit_price": {"type": "float", "distribution": "uniform", "min": 5, "max": 50, "decimals": 2},
                        "line_total": {"type": "float", "formula": "quantity * unit_price"}},
              "__outcome_curves__": [{"table": "lines", "column": "line_total", "time_column": "ordered_at", "time_unit": "month",
                                      "value_mode": "absolute", "start_date": "2025-01-01",
                                      "curve_points": [{"month": 1, "target_value": 5000}, {"month": 12, "target_value": 9000}]}]}
    cfg = misata.from_dict_schema(schema, row_count=500, seed=7)
    found = [c for c in find_conflicts(cfg) if c.kind == "curve_on_worked_out_column"]
    assert {c.where for c in found} == {"lines.line_total", "lines.ordered_at"}
    assert any("orders" in c.remedy for c in found if c.where == "lines.ordered_at")


def test_dates_outside_their_window_are_reported():
    from misata.coherence import _detect_declared_window_violation
    cfg = misata.from_dict_schema({"e": {"__rows__": 10, "id": {"type": "integer", "primary_key": True},
                                         "at": {"type": "date", "min": "2025-01-01", "max": "2025-12-31"}}}, row_count=10, seed=1)
    rows = {"e": pd.DataFrame({"id": range(4), "at": ["2025-02-01", "2019-05-05", "2025-12-31", "2026-01-02"]})}
    (f,) = _detect_declared_window_violation(rows, cfg)
    assert f.rows_affected == 2 and f.column == "at"
