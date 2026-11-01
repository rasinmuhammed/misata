"""Bounds that keep declared aggregates, declared precision, and declared openings.

- ``sum_lte_parent`` and ``lte_parent`` clamp a child column. When the column
  also carries an exact curve or group shares, the clamped amount moves to
  rows with room in the same period and group, so every declared number holds.
- ``group_shares`` honours the measure's declared decimals.
- ``stock_flows.opening`` fixes each SKU's first opening level.
- The count-column audit reads whole words and ignores timestamps.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata.coherence import _detect_bounds, coherence_audit
from misata.crosstable import _UNBOUNDED, enforce_cap
from misata.feasibility import find_conflicts
from misata.schema import (Column, Constraint, GroupShares, OutcomeCurve, Relationship,
                           SchemaConfig, StockFlowIdentity, Table)

warnings.filterwarnings("ignore")

SHARES = {"cafe": 0.5, "grocer": 0.3, "books": 0.2}


def _spending_schema(*, cap="sum", decimals=0, target=400_000, seed=3, cap_hi=6000):
    """Card spending capped by each account's spendable balance, with a declared
    daily total split exactly across merchants.

    At the default ``cap_hi`` the accounts can absorb the declared total while
    many of them, drawn near zero, still overshoot and must be clamped."""
    if cap == "sum":
        rule = Constraint(name="within_means", type="sum_lte_parent", column="amount",
                          parent_table="accounts", parent_column="spendable")
    else:
        rule = Constraint(name="per_payment", type="lte_parent", column="amount",
                          parent_table="accounts", parent_column="spendable")
    params = {"min": 1, "max": 2000, "decimals": decimals}
    return SchemaConfig(
        name="spending",
        tables=[Table(name="accounts", row_count=300),
                Table(name="payments", row_count=1500, constraints=[rule])],
        columns={
            "accounts": [
                Column(name="account_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 300}),
                Column(name="spendable", type="int",
                       distribution_params={"min": 0, "max": cap_hi}),
            ],
            "payments": [
                Column(name="payment_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 1500}),
                Column(name="account_id", type="foreign_key"),
                Column(name="merchant", type="categorical",
                       distribution_params={"choices": list(SHARES)}),
                Column(name="amount", type="float", distribution_params=params),
                Column(name="paid_on", type="date",
                       distribution_params={"start": "2026-11-01", "end": "2026-11-03"}),
            ],
        },
        relationships=[Relationship(parent_table="accounts", child_table="payments",
                                    parent_key="account_id", child_key="account_id")],
        outcome_curves=[OutcomeCurve(
            table="payments", column="amount", time_column="paid_on", time_unit="day",
            value_mode="absolute", curve_points=[
                {"date": "2026-11-01", "target_value": target * 0.3},
                {"date": "2026-11-02", "target_value": target * 0.3},
                {"date": "2026-11-03", "target_value": target * 0.4}])],
        group_shares=[GroupShares(table="payments", measure="amount",
                                  group_column="merchant", shares=SHARES)],
        seed=seed,
    )


def _day_merchant_totals(t):
    p = t["payments"]
    return p.groupby([pd.to_datetime(p["paid_on"]).dt.date, "merchant"])["amount"].sum()


class TestSumCapKeepsDeclaredAggregates:
    def test_every_account_stays_within_its_means(self):
        t = misata.generate_from_schema(_spending_schema())
        sums = t["payments"].groupby("account_id")["amount"].sum()
        cap = t["accounts"].set_index("account_id")["spendable"]
        assert (sums <= cap.reindex(sums.index)).all()

    def test_day_totals_and_merchant_shares_stay_exact(self):
        t = misata.generate_from_schema(_spending_schema())
        days = t["payments"].groupby(pd.to_datetime(t["payments"]["paid_on"]).dt.date)["amount"].sum()
        assert list(days.round(6)) == [120_000, 120_000, 160_000]
        cells = _day_merchant_totals(t)
        for (day, merchant), got in cells.items():
            day_total = days[day]
            assert got == pytest.approx(day_total * SHARES[merchant], abs=1)

    def test_declared_precision_survives(self):
        t = misata.generate_from_schema(_spending_schema(decimals=0))
        assert (t["payments"]["amount"] % 1 == 0).all()
        cents = misata.generate_from_schema(_spending_schema(decimals=2))["payments"]["amount"]
        assert ((cents * 100).round(6) % 1 == 0).all()

    def test_the_audit_is_clean(self):
        schema = _spending_schema()
        report = coherence_audit(misata.generate_from_schema(schema), schema=schema)
        kinds = {f.kind for f in report.findings}
        assert not kinds & {"cross_table_bound", "outcome_curve_mismatch", "group_share_mismatch"}

    def test_attestation_checks_the_bound(self, tmp_path):
        schema = _spending_schema()
        misata.to_parquet(misata.generate_from_schema(schema), str(tmp_path))
        a = misata.attest(tmp_path, schema, write=False)
        bound = [i for i in a.invariants if i["kind"] == "sum_lte_parent"]
        assert bound and all(i["passed"] for i in bound)
        assert a.passed

    def test_with_no_room_anywhere_the_aggregate_wins_and_warns(self):
        schema = _spending_schema(cap_hi=10)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            t = misata.generate_from_schema(schema)
        assert any("declared aggregate takes precedence" in str(w.message) for w in caught)
        assert t["payments"]["amount"].sum() == pytest.approx(400_000, abs=0.5)


class TestRowCapKeepsDeclaredAggregates:
    def test_rows_capped_and_totals_exact(self):
        # Accounts below the typical payment force clamping on many rows.
        t = misata.generate_from_schema(_spending_schema(cap="row"))
        m = t["payments"].merge(t["accounts"], on="account_id")
        assert (m["amount"] <= m["spendable"]).all()
        assert t["payments"]["amount"].sum() == pytest.approx(400_000, abs=0.5)


class TestEnforceCap:
    def test_without_cells_removed_units_are_dropped(self):
        values = np.array([60, 40, 10], dtype=np.int64)
        groups = np.array([0, 0, 1])
        out, yielded = enforce_cap(values, groups, np.array([50, _UNBOUNDED]), None,
                                   np.full(3, _UNBOUNDED, dtype=np.int64))
        assert out.tolist() == [30, 20, 10] and yielded == 0

    def test_with_cells_removed_units_move_within_the_cell(self):
        values = np.array([60, 40, 10, 10], dtype=np.int64)
        groups = np.array([0, 0, 1, 2])
        cells = np.array([0, 0, 0, 1])
        out, yielded = enforce_cap(values, groups, np.array([50, 100, 100]), cells,
                                   np.full(4, _UNBOUNDED, dtype=np.int64))
        assert out[:3].sum() == 110 and out[3] == 10
        assert out[:2].sum() == 50 and yielded == 0

    def test_a_null_parent_is_bounded_by_nothing(self):
        values = np.array([80, 5], dtype=np.int64)
        out, _ = enforce_cap(values, np.array([0, -1]), np.array([30]), np.array([0, 0]),
                             np.full(2, _UNBOUNDED, dtype=np.int64))
        assert out.tolist() == [30, 55]


class TestShareDecimals:
    def test_integer_measure_gets_integer_rows(self):
        t = misata.generate_from_schema(_spending_schema(cap_hi=10**7, decimals=0))
        assert (t["payments"]["amount"] % 1 == 0).all()


def _inventory_schema(opening, rows=None, periods=("2026-11-01", "2026-11-02")):
    return SchemaConfig(
        name="inventory",
        tables=[Table(name="stock", row_count=rows or len(opening) * len(periods))],
        columns={"stock": [
            Column(name="sku", type="categorical", distribution_params={"choices": ["x"]}),
            Column(name="period", type="categorical", distribution_params={"choices": list(periods)}),
            Column(name="opening_stock", type="int", distribution_params={"min": 0, "max": 9}),
            Column(name="received", type="int", distribution_params={"min": 0, "max": 9}),
            Column(name="shipped", type="int", distribution_params={"min": 0, "max": 9}),
            Column(name="closing_stock", type="int", distribution_params={"min": 0, "max": 9}),
        ]},
        stock_flows=[StockFlowIdentity(table="stock", periods=list(periods), opening=opening)],
        seed=4,
    )


class TestStockFlowOpening:
    OPENING = {"flour": 120, "eggs": 0, "milk": 45}

    def test_each_sku_opens_at_its_declared_level_in_order(self):
        t = misata.generate_from_schema(_inventory_schema(self.OPENING))["stock"]
        first = t[t["period"] == "2026-11-01"]
        assert first["sku"].tolist() == list(self.OPENING)
        assert first["opening_stock"].tolist() == list(self.OPENING.values())

    def test_the_chain_continues_from_the_declared_opening(self):
        t = misata.generate_from_schema(_inventory_schema(self.OPENING))["stock"]
        for _, g in t.groupby("sku"):
            assert g["opening_stock"].iloc[1] == g["closing_stock"].iloc[0]
            assert (g[["opening_stock", "closing_stock"]] >= 0).all().all()

    def test_a_row_count_that_does_not_fit_is_refused(self):
        conflicts = find_conflicts(_inventory_schema(self.OPENING, rows=7))
        assert any(c.kind == "stock_flow_opening_rows" for c in conflicts)

    def test_audit_and_attestation_check_the_opening(self, tmp_path):
        schema = _inventory_schema(self.OPENING)
        t = misata.generate_from_schema(schema)
        misata.to_parquet(t, str(tmp_path))
        assert misata.attest(tmp_path, schema, write=False).passed
        t["stock"].loc[0, ["opening_stock", "closing_stock"]] += 5
        report = coherence_audit(t, schema=schema)
        assert any(f.kind == "stock_flow_opening" for f in report.findings)

    def test_negative_opening_is_rejected(self):
        with pytest.raises(ValueError):
            StockFlowIdentity(table="stock", periods=["p"], opening={"flour": -1})


class TestCountColumns:
    def test_whole_words_only(self):
        df = pd.DataFrame({"triaged_at_offset": [-3], "account_balance": [-50],
                           "discount": [-2], "patient_age": [-1], "item_count": [-4],
                           "num_orders": [-1]})
        flagged = {f.column for f in _detect_bounds("t", df)}
        assert flagged == {"patient_age", "item_count", "num_orders"}

    def test_timestamps_are_not_counts(self):
        df = pd.DataFrame({"triaged_at": pd.to_datetime(["2026-11-02 10:00", None]),
                           "visit_age": pd.to_datetime(["2026-11-02", None])})
        assert _detect_bounds("t", df) == []
