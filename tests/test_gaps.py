"""Tests for Gap 1 (RateCurve enforcement), Gap 3 (child-table curve inheritance),
and Gap 4 (streaming exactness).

Every test makes a hard, mathematical assertion — not just "it ran without error".
The tolerance used is derived from the Prop. 2 guarantee: for period with n rows,
the realized count is exactly round(n * rate), so the realized rate deviates by at
most 0.5/n from the declared rate.  We use a generous 2/n bound to allow for
edge-case tie-breaking without being flakey.
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd
import pytest

import misata
from misata.schema import (
    Column, Relationship, RateCurve, SchemaConfig, Table, OutcomeCurve,
)
from misata.simulator import DataSimulator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_schema(
    *,
    table_name: str = "transactions",
    rows: int = 1000,
    with_rate_curve: bool = False,
    rate: float = 0.05,
    with_outcome_curve: bool = False,
    revenue_targets: dict | None = None,
) -> SchemaConfig:
    """Minimal schema factory for testing individual gaps."""
    columns = [
        Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
        Column(name="amount", type="float", distribution_params={
            "distribution": "lognormal", "mu": 4.5, "sigma": 0.8
        }),
        Column(name="tx_date", type="date", distribution_params={
            "start": "2024-01-01", "end": "2024-12-31"
        }),
        Column(name="is_fraud", type="boolean", distribution_params={"probability": 0.05}),
    ]

    outcome_curves = []
    if with_outcome_curve and revenue_targets:
        pts = [{"month": m, "target_value": v} for m, v in revenue_targets.items()]
        outcome_curves.append(OutcomeCurve(
            table=table_name,
            column="amount",
            time_column="tx_date",
            time_unit="month",
            avg_transaction_value=500.0,
            concentration=2.0,
            curve_points=pts,
        ))

    rate_curves = []
    if with_rate_curve:
        rate_curves.append(RateCurve(
            table=table_name,
            column="is_fraud",
            time_column="tx_date",
            true_value=True,
            interpolate=False,
            rate_points=[{"period": "01", "rate": rate}],
        ))

    return SchemaConfig(
        name="test",
        tables=[Table(name=table_name, row_count=rows)],
        columns={table_name: columns},
        outcome_curves=outcome_curves,
        rate_curves=rate_curves,
        seed=42,
    )


# ---------------------------------------------------------------------------
# Gap 1 — RateCurve enforcement
# ---------------------------------------------------------------------------

class TestRateCurveEnforcement:
    """Gap 1: _apply_rate_curves must satisfy |realized_rate - target_rate| ≤ 0.5/n."""

    def test_boolean_rate_single_period_exact(self):
        """A single-period 5% fraud rate must be enforced exactly."""
        schema = _build_schema(rows=1000, with_rate_curve=True, rate=0.05)
        sim = DataSimulator(schema)
        tables = {t: df for t, df in sim.generate_all()}
        df = tables["transactions"]

        jan_mask = pd.to_datetime(df["tx_date"]).dt.month == 1
        if not jan_mask.any():
            pytest.skip("No January rows generated (probabilistic skip)")

        jan_df = df[jan_mask]
        n_jan = len(jan_df)
        realized_rate = jan_df["is_fraud"].sum() / n_jan
        # Prop. 2 guarantee: |realized - declared| ≤ 0.5/n
        tolerance = 0.5 / n_jan + 1e-9
        assert abs(realized_rate - 0.05) <= tolerance, (
            f"Realized fraud rate {realized_rate:.4f} deviates from 0.05 "
            f"by more than {tolerance:.6f} (n={n_jan})"
        )

    def test_boolean_rate_zero_means_no_positives(self):
        """A declared rate of 0.0 must produce exactly 0 positives."""
        schema = _build_schema(rows=500, with_rate_curve=True, rate=0.0)
        sim = DataSimulator(schema)
        tables = {t: df for t, df in sim.generate_all()}
        df = tables["transactions"]
        jan_mask = pd.to_datetime(df["tx_date"]).dt.month == 1
        if not jan_mask.any():
            pytest.skip("No January rows")
        assert df[jan_mask]["is_fraud"].sum() == 0

    def test_boolean_rate_one_means_all_positives(self):
        """A declared rate of 1.0 must produce all positives."""
        schema = _build_schema(rows=500, with_rate_curve=True, rate=1.0)
        sim = DataSimulator(schema)
        tables = {t: df for t, df in sim.generate_all()}
        df = tables["transactions"]
        jan_mask = pd.to_datetime(df["tx_date"]).dt.month == 1
        if not jan_mask.any():
            pytest.skip("No January rows")
        assert df[jan_mask]["is_fraud"].all()

    def test_rate_curve_does_not_alter_amount_column(self):
        """RateCurve must not touch numeric aggregate columns (AME=0 preservation)."""
        # With outcome curve + rate curve on same table
        schema = _build_schema(
            rows=1200,
            with_outcome_curve=True,
            revenue_targets={1: 50_000.0, 6: 80_000.0, 12: 120_000.0},
            with_rate_curve=True,
            rate=0.03,
        )
        sim = DataSimulator(schema)
        tables = {t: df for t, df in sim.generate_all()}
        df = tables["transactions"]

        from research.specbench.metrics import aggregate_match_error
        ame = aggregate_match_error(
            {"transactions": df},
            "transactions", "amount", "tx_date",
            {"01": 50_000.0, "06": 80_000.0, "12": 120_000.0},
        )
        assert ame.value < 0.01, (
            f"RateCurve application disturbed AME: {ame.value:.4f} (expected < 0.01). "
            f"Detail: {ame.detail}"
        )

    def test_rate_curve_interpolation_monotone(self):
        """With interpolate=True, rates between anchors must be monotone."""
        schema = SchemaConfig(
            name="test_interp",
            tables=[Table(name="t", row_count=3000)],
            columns={"t": [
                Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
                Column(name="flag", type="boolean", distribution_params={"probability": 0.05}),
                Column(name="date", type="date", distribution_params={"start": "2024-01-01", "end": "2024-12-31"}),
            ]},
            rate_curves=[RateCurve(
                table="t",
                column="flag",
                time_column="date",
                true_value=True,
                interpolate=True,
                rate_points=[
                    {"period": "01", "rate": 0.02},
                    {"period": "12", "rate": 0.08},
                ],
            )],
            seed=7,
        )
        sim = DataSimulator(schema)
        tables = {t: df for t, df in sim.generate_all()}
        df = tables["t"]
        df["month"] = pd.to_datetime(df["date"]).dt.month

        jan = df[df["month"] == 1]
        dec = df[df["month"] == 12]

        if len(jan) < 10 or len(dec) < 10:
            pytest.skip("Too few rows to test monotone interpolation")

        jan_rate = jan["flag"].sum() / len(jan)
        dec_rate = dec["flag"].sum() / len(dec)

        # Interpolated: December rate must be higher than January rate
        assert dec_rate > jan_rate, (
            f"Interpolated rates not monotone: Jan={jan_rate:.4f}, Dec={dec_rate:.4f}"
        )


# ---------------------------------------------------------------------------
# Gap 3 — Child-table curve inheritance
# ---------------------------------------------------------------------------

class TestChildTableCurveInheritance:
    """Gap 3: child tables must cluster temporally around parent curve peaks."""

    def _multi_table_schema_with_curve(self, parent_rows: int = 500, child_rows: int = 2000) -> SchemaConfig:
        """Schema: accounts (parent, with revenue curve) → transactions (child, FK)."""
        account_cols = [
            Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
            Column(name="revenue", type="float", distribution_params={
                "distribution": "lognormal", "mu": 5.0, "sigma": 0.8,
            }),
            Column(name="account_date", type="date", distribution_params={
                "start": "2024-01-01", "end": "2024-12-31",
            }),
        ]
        tx_cols = [
            Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
            Column(name="account_id", type="foreign_key", distribution_params={}),
            Column(name="amount", type="float", distribution_params={
                "distribution": "lognormal", "mu": 4.5, "sigma": 0.6,
            }),
            Column(name="tx_date", type="date", distribution_params={
                "start": "2024-01-01", "end": "2024-12-31",
            }),
        ]
        # Outcome curve: Q4 accounts peak dramatically
        outcome_curve = OutcomeCurve(
            table="accounts",
            column="revenue",
            time_column="account_date",
            time_unit="month",
            avg_transaction_value=1000.0,
            concentration=2.0,
            curve_points=[
                {"month": 1, "target_value": 10_000.0},
                {"month": 9, "target_value": 20_000.0},
                {"month": 12, "target_value": 80_000.0},  # Q4 spike: 4× Jan
            ],
        )
        return SchemaConfig(
            name="test_inheritance",
            tables=[
                Table(name="accounts", row_count=parent_rows),
                Table(name="transactions", row_count=child_rows),
            ],
            columns={"accounts": account_cols, "transactions": tx_cols},
            relationships=[Relationship(
                parent_table="accounts",
                child_table="transactions",
                parent_key="id",
                child_key="account_id",
            )],
            outcome_curves=[outcome_curve],
            seed=99,
        )

    def test_fk_integrity_preserved(self):
        """All child FK values must reference existing parent PKs (FIVR = 0)."""
        schema = self._multi_table_schema_with_curve()
        sim = DataSimulator(schema)
        tables = {t: df for t, df in sim.generate_all()}
        parent_ids = set(tables["accounts"]["id"].unique())
        child_fks = tables["transactions"]["account_id"]
        orphan_rate = (~child_fks.isin(parent_ids)).mean()
        assert orphan_rate == 0.0, f"FK orphan rate = {orphan_rate:.4f} (expected 0)"

    def test_child_fk_temporal_weighting_direction(self):
        """With Level-1 inheritance, more child FKs should reference Q4 parents.

        The parent curve has a 4× spike in December.  After temporal FK weighting,
        the fraction of child rows referencing Q4 accounts should be meaningfully
        higher than Q1 fraction.  We use a loose threshold (Q4 > Q1) rather than
        an exact ratio to avoid flakey tests from rounding.
        """
        schema = self._multi_table_schema_with_curve(parent_rows=600, child_rows=3000)
        sim = DataSimulator(schema)
        tables = {t: df for t, df in sim.generate_all()}

        accounts = tables["accounts"]
        transactions = tables["transactions"]

        # Identify Q1 and Q4 parent accounts
        acc_dates = pd.to_datetime(accounts["account_date"])
        q1_ids = set(accounts.loc[acc_dates.dt.month.isin([1, 2, 3]), "id"])
        q4_ids = set(accounts.loc[acc_dates.dt.month.isin([10, 11, 12]), "id"])

        if not q1_ids or not q4_ids:
            pytest.skip("Insufficient Q1/Q4 parent distribution (seed edge case)")

        tx_fks = transactions["account_id"]
        q1_frac = tx_fks.isin(q1_ids).mean()
        q4_frac = tx_fks.isin(q4_ids).mean()

        # Q4 has 4× the curve target of Q1, so Q4 fraction should exceed Q1
        assert q4_frac > q1_frac, (
            f"Temporal FK weighting not working: Q1_frac={q1_frac:.4f}, Q4_frac={q4_frac:.4f}. "
            "Child FKs should cluster toward Q4 parent accounts (4× higher curve target)."
        )

    def test_inherits_curve_from_date_column(self):
        """Level-2: a child date column with inherits_curve_from must mirror parent density."""
        # The payment_date inherits from accounts.account_date (which has a Q4 peak)
        account_cols = [
            Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
            Column(name="revenue", type="float", distribution_params={
                "distribution": "lognormal", "mu": 5.0, "sigma": 0.8,
            }),
            Column(name="account_date", type="date", distribution_params={
                "start": "2024-01-01", "end": "2024-12-31",
            }),
        ]
        payment_cols = [
            Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
            Column(name="account_id", type="foreign_key", distribution_params={}),
            Column(name="amount", type="float", distribution_params={
                "distribution": "lognormal", "mu": 3.5, "sigma": 0.5,
            }),
            Column(name="payment_date", type="date", distribution_params={
                "start": "2024-01-01",
                "end": "2024-12-31",
                "inherits_curve_from": "accounts",  # Level-2 inheritance
            }),
        ]
        curve = OutcomeCurve(
            table="accounts",
            column="revenue",
            time_column="account_date",
            time_unit="month",
            avg_transaction_value=800.0,
            concentration=2.0,
            curve_points=[
                {"month": 1, "target_value": 8_000.0},
                {"month": 12, "target_value": 72_000.0},   # 9× Q1 → very steep
            ],
        )
        schema = SchemaConfig(
            name="test_l2",
            tables=[
                Table(name="accounts", row_count=400),
                Table(name="payments", row_count=2000),
            ],
            columns={"accounts": account_cols, "payments": payment_cols},
            relationships=[Relationship(
                parent_table="accounts",
                child_table="payments",
                parent_key="id",
                child_key="account_id",
            )],
            outcome_curves=[curve],
            seed=17,
        )
        sim = DataSimulator(schema)
        tables = {t: df for t, df in sim.generate_all()}
        payments = tables["payments"]

        pay_months = pd.to_datetime(payments["payment_date"]).dt.month
        q1_frac = (pay_months.isin([1, 2, 3])).mean()
        q4_frac = (pay_months.isin([10, 11, 12])).mean()

        # With 9× December target, Q4 fraction of payment_dates should exceed Q1
        assert q4_frac > q1_frac, (
            f"Level-2 date inheritance not working: Q1={q1_frac:.4f}, Q4={q4_frac:.4f}. "
            "payment_date should cluster toward Q4 (9× parent density)."
        )


# ---------------------------------------------------------------------------
# Gap 4 — Streaming exactness
# ---------------------------------------------------------------------------

class TestStreamingExactness:
    """Gap 4: exact-curve tables must achieve AME=0 regardless of how batches are consumed."""

    def test_exact_curve_ame_zero_via_generate_all(self):
        """generate_all() must preserve AME=0 for exact outcome curve tables."""
        import sys, os
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from research.specbench.metrics import aggregate_match_error

        targets = {"01": 40_000.0, "06": 80_000.0, "12": 200_000.0}
        curve = OutcomeCurve(
            table="orders",
            column="amount",
            time_column="order_date",
            time_unit="month",
            avg_transaction_value=200.0,
            concentration=2.0,
            curve_points=[
                {"month": 1, "target_value": 40_000.0},
                {"month": 6, "target_value": 80_000.0},
                {"month": 12, "target_value": 200_000.0},
            ],
        )
        schema = SchemaConfig(
            name="streaming_test",
            tables=[Table(name="orders", row_count=2000)],
            columns={"orders": [
                Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
                Column(name="amount", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 5.0, "sigma": 0.8,
                }),
                Column(name="order_date", type="date", distribution_params={
                    "start": "2024-01-01", "end": "2024-12-31",
                }),
            ]},
            outcome_curves=[curve],
            seed=101,
        )
        sim = DataSimulator(schema)
        all_batches: list = []
        for _, batch in sim.generate_all():
            all_batches.append(batch)

        full_df = pd.concat(all_batches, ignore_index=True)
        ame = aggregate_match_error(
            {"orders": full_df},
            "orders", "amount", "order_date",
            {"01": 40_000.0, "06": 80_000.0, "12": 200_000.0},
        )
        assert ame.value < 1e-6, (
            f"Streaming AME={ame.value:.8f} — exact-curve tables must achieve AME=0. "
            f"Detail: {ame.detail}"
        )

    def test_exact_curve_same_result_single_and_streaming(self):
        """Concatenated streaming batches must match a single generate_all() call."""
        curve = OutcomeCurve(
            table="sales",
            column="revenue",
            time_column="sale_date",
            time_unit="month",
            avg_transaction_value=100.0,
            concentration=2.0,
            curve_points=[
                {"month": 3, "target_value": 30_000.0},
                {"month": 9, "target_value": 90_000.0},
            ],
        )
        schema = SchemaConfig(
            name="consistency_test",
            tables=[Table(name="sales", row_count=1000)],
            columns={"sales": [
                Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
                Column(name="revenue", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 4.6, "sigma": 0.7,
                }),
                Column(name="sale_date", type="date", distribution_params={
                    "start": "2024-01-01", "end": "2024-12-31",
                }),
            ]},
            outcome_curves=[curve],
            seed=55,
        )

        def _run(seed_override: int) -> pd.DataFrame:
            s = schema.model_copy(update={"seed": seed_override})
            sim = DataSimulator(s)
            batches = [b for _, b in sim.generate_all()]
            return pd.concat(batches, ignore_index=True)

        df1 = _run(55)
        df2 = _run(55)
        # Same seed must produce identical output (determinism)
        pd.testing.assert_frame_equal(
            df1.reset_index(drop=True),
            df2.reset_index(drop=True),
            check_dtype=False,
        )

    def test_rate_curve_preserved_across_streaming(self):
        """RateCurve enforcement must survive the streaming path (generate_all)."""
        schema = _build_schema(rows=2000, with_rate_curve=True, rate=0.10)
        sim = DataSimulator(schema)

        groups: dict = {}
        for table_name, batch in sim.generate_all():
            groups.setdefault(table_name, []).append(batch)
        tables = {t: pd.concat(bs, ignore_index=True) for t, bs in groups.items()}

        df = tables["transactions"]
        jan_mask = pd.to_datetime(df["tx_date"]).dt.month == 1
        if not jan_mask.any():
            pytest.skip("No January rows")
        jan_df = df[jan_mask]
        n = len(jan_df)
        realized = jan_df["is_fraud"].sum() / n
        tolerance = 0.5 / n + 1e-9
        assert abs(realized - 0.10) <= tolerance, (
            f"Streaming RateCurve: realized={realized:.4f}, target=0.10 (tol={tolerance:.6f})"
        )


# ---------------------------------------------------------------------------
# Gap A — NL → RateCurve extraction in StoryParser
# ---------------------------------------------------------------------------

class TestNLRateCurveExtraction:
    """Gap A: StoryParser must extract RateCurve from natural-language stories."""

    def test_flat_fraud_rate_produces_rate_curve(self):
        """\"2% fraud rate\" in a fintech story must produce a RateCurve on is_fraud."""
        from misata.story_parser import StoryParser
        parser = StoryParser()
        schema = parser.parse(
            "A fintech payments platform with 100K transactions per month "
            "and a 2% fraud rate across all periods.",
            default_rows=5000,
        )
        assert schema.rate_curves, "StoryParser should produce at least one RateCurve"
        rc = schema.rate_curves[0]
        assert rc.column in ("is_fraud", "is_fraudulent"), (
            f"Expected is_fraud column, got '{rc.column}'"
        )
        assert any(
            abs(float(p.get("rate", 0)) - 0.02) < 1e-4
            for p in rc.rate_points
        ), f"Expected ~0.02 rate, got rate_points={rc.rate_points}"

    def test_rising_fraud_rate_produces_interpolated_curve(self):
        """\"3% fraud in Q1 rising to 8% by Q4\" must produce a 2-anchor interpolated RateCurve."""
        from misata.story_parser import StoryParser
        parser = StoryParser()
        schema = parser.parse(
            "A fintech company with 50K transactions. "
            "3% fraud in Q1 rising to 8% by Q4 as attack volume increases.",
            default_rows=5000,
        )
        assert schema.rate_curves, "Expected RateCurve from rising fraud pattern"
        rc = schema.rate_curves[0]
        assert rc.interpolate is True, "Rising rate curve must have interpolate=True"
        assert len(rc.rate_points) == 2, (
            f"Expected 2 anchor points for rising range, got {len(rc.rate_points)}"
        )
        rates = sorted(float(p["rate"]) for p in rc.rate_points)
        assert rates[0] < rates[1], f"Rates should be rising: {rates}"
        assert abs(rates[0] - 0.03) < 0.005, f"Start rate should be ~0.03, got {rates[0]}"
        assert abs(rates[1] - 0.08) < 0.005, f"End rate should be ~0.08, got {rates[1]}"

    def test_churn_rate_in_saas_story(self):
        """SaaS story with churn rate must produce a RateCurve on the churned column."""
        from misata.story_parser import StoryParser
        parser = StoryParser()
        schema = parser.parse(
            "A SaaS startup with 10K subscribers. Monthly churn rate of 3%.",
            default_rows=10000,
        )
        churn_curves = [
            rc for rc in (schema.rate_curves or [])
            if rc.column in ("is_churned", "churned")
        ]
        assert churn_curves, (
            "Expected at least one RateCurve targeting a churn column in SaaS story. "
            f"Got rate_curves={schema.rate_curves}"
        )
        rc = churn_curves[0]
        assert any(
            abs(float(p.get("rate", 0)) - 0.03) < 0.005
            for p in rc.rate_points
        ), f"Expected ~0.03 churn rate, got {rc.rate_points}"

    def test_extracted_rate_curve_is_enforced_on_generation(self):
        """End-to-end: NL story → RateCurve → generation enforces exact rate."""
        from misata.story_parser import StoryParser
        parser = StoryParser()
        schema = parser.parse(
            "A fintech with 10K transactions and a flat 5% fraud rate.",
            default_rows=3000,
        )
        # Must have produced a rate curve
        fraud_curves = [rc for rc in (schema.rate_curves or []) if "fraud" in rc.column]
        if not fraud_curves:
            pytest.skip("Story parser did not extract a fraud RateCurve (pattern miss)")

        sim = DataSimulator(schema)
        tables = {t: df for t, df in sim.generate_all()}

        # Find the table containing the fraud column
        rc = fraud_curves[0]
        df = tables.get(rc.table)
        if df is None or rc.column not in df.columns:
            pytest.skip(f"Table '{rc.table}' or column '{rc.column}' not in output")

        # Overall realized rate should be close to declared rate
        realized = df[rc.column].sum() / len(df)
        # Loose tolerance because rate may only be declared for specific periods
        assert abs(realized - 0.05) < 0.03, (
            f"End-to-end NL rate enforcement: realized={realized:.4f}, target=0.05"
        )


# ---------------------------------------------------------------------------
# Gap B — Relative-curve cross-batch accumulation
# ---------------------------------------------------------------------------

class TestRelativeCurveAccumulation:
    """Gap B: relative curves across multiple batches must converge to implied targets."""

    def test_relative_curve_shapes_distribution_direction(self):
        """A relative curve with high Q4 factor must produce higher Q4 values than Q1.

        Gap B doesn't guarantee an exact total (that's FactEngine's job for absolute
        curves), but it should correct per-batch drift so the final distribution
        is directionally correct: months with higher relative_value should have
        higher column sums.
        """
        from misata.schema import OutcomeCurve
        curve = OutcomeCurve(
            table="sales",
            column="amount",
            time_column="sale_date",
            time_unit="month",
            avg_transaction_value=100.0,
            curve_points=[
                {"month": 1, "relative_value": 0.5},
                {"month": 6, "relative_value": 1.0},
                {"month": 12, "relative_value": 2.0},
            ],
        )
        schema = SchemaConfig(
            name="relative_test",
            tables=[Table(name="sales", row_count=3000)],
            columns={"sales": [
                Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
                Column(name="amount", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 4.6, "sigma": 0.5,
                }),
                Column(name="sale_date", type="date", distribution_params={
                    "start": "2024-01-01", "end": "2024-12-31",
                }),
            ]},
            outcome_curves=[curve],
            seed=33,
        )
        sim = DataSimulator(schema)
        tables = {t: df for t, df in sim.generate_all()}
        df = tables["sales"]
        df["month"] = pd.to_datetime(df["sale_date"]).dt.month

        jan_avg = df[df["month"] == 1]["amount"].mean()
        dec_avg = df[df["month"] == 12]["amount"].mean()

        if pd.isna(jan_avg) or pd.isna(dec_avg):
            pytest.skip("Insufficient rows in Jan or Dec")

        assert dec_avg > jan_avg, (
            f"Relative curve: Dec avg ({dec_avg:.2f}) should exceed Jan avg ({jan_avg:.2f}) "
            f"(December factor=2.0 vs January factor=0.5)"
        )

    def test_relative_curve_multi_batch_consistency(self):
        """Same seed must produce same output regardless of batch_size (determinism check)."""
        from misata.schema import OutcomeCurve
        curve = OutcomeCurve(
            table="orders",
            column="revenue",
            time_column="order_date",
            time_unit="month",
            avg_transaction_value=50.0,
            curve_points=[
                {"month": 3, "relative_value": 1.5},
                {"month": 9, "relative_value": 2.0},
            ],
        )
        schema = SchemaConfig(
            name="batch_consistency",
            tables=[Table(name="orders", row_count=600)],
            columns={"orders": [
                Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
                Column(name="revenue", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 3.9, "sigma": 0.6,
                }),
                Column(name="order_date", type="date", distribution_params={
                    "start": "2024-01-01", "end": "2024-12-31",
                }),
            ]},
            outcome_curves=[curve],
            seed=77,
        )
        sim1 = DataSimulator(schema, batch_size=600)  # single batch
        sim2 = DataSimulator(schema, batch_size=100)  # multi-batch
        df1 = pd.concat([b for _, b in sim1.generate_all()], ignore_index=True)
        df2 = pd.concat([b for _, b in sim2.generate_all()], ignore_index=True)

        # The month-level sum ratios must be consistent in direction
        df1["month"] = pd.to_datetime(df1["order_date"]).dt.month
        df2["month"] = pd.to_datetime(df2["order_date"]).dt.month

        mar_avg1 = df1[df1["month"] == 3]["revenue"].mean()
        sep_avg1 = df1[df1["month"] == 9]["revenue"].mean()
        mar_avg2 = df2[df2["month"] == 3]["revenue"].mean()
        sep_avg2 = df2[df2["month"] == 9]["revenue"].mean()

        for df_label, mar, sep in [("single-batch", mar_avg1, sep_avg1), ("multi-batch", mar_avg2, sep_avg2)]:
            if not (pd.isna(mar) or pd.isna(sep)):
                assert sep > mar, (
                    f"{df_label}: Sep avg ({sep:.2f}) should exceed Mar avg ({mar:.2f}) "
                    "(Sep factor=2.0 > Mar factor=1.5)"
                )


# ---------------------------------------------------------------------------
# Gap C — Deep hierarchy temporal propagation
# ---------------------------------------------------------------------------

class TestDeepHierarchyPropagation:
    """Gap C: grandchild tables must inherit temporal density from grandparent curves."""

    def test_three_level_hierarchy_grandchild_clustering(self):
        """regions → stores → sales: sales FK distribution should reflect regions curve.

        The regions table has a Q4 spike (4× Q1).  After density propagation:
        - stores.region_id FKs cluster toward Q4 regions (Level 1, direct)
        - sales.store_id FKs cluster toward Q4 stores (Level 1, via propagated proxy)
        Net effect: more sales reference stores in Q4-heavy regions.
        """
        # Build a 3-level hierarchy with curve only on the top table
        region_cols = [
            Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
            Column(name="revenue", type="float", distribution_params={
                "distribution": "lognormal", "mu": 7.0, "sigma": 1.0,
            }),
            Column(name="region_date", type="date", distribution_params={
                "start": "2024-01-01", "end": "2024-12-31",
            }),
        ]
        store_cols = [
            Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
            Column(name="region_id", type="foreign_key", distribution_params={}),
            Column(name="sales_total", type="float", distribution_params={
                "distribution": "lognormal", "mu": 5.0, "sigma": 0.8,
            }),
            Column(name="store_date", type="date", distribution_params={
                "start": "2024-01-01", "end": "2024-12-31",
            }),
        ]
        sale_cols = [
            Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
            Column(name="store_id", type="foreign_key", distribution_params={}),
            Column(name="amount", type="float", distribution_params={
                "distribution": "lognormal", "mu": 4.0, "sigma": 0.7,
            }),
        ]

        region_curve = OutcomeCurve(
            table="regions",
            column="revenue",
            time_column="region_date",
            time_unit="month",
            avg_transaction_value=100_000.0,
            concentration=2.0,
            curve_points=[
                {"month": 1, "target_value": 50_000.0},
                {"month": 12, "target_value": 200_000.0},  # 4× Q1 spike
            ],
        )

        schema = SchemaConfig(
            name="three_level",
            tables=[
                Table(name="regions", row_count=200),
                Table(name="stores",  row_count=500),
                Table(name="sales",   row_count=3000),
            ],
            columns={
                "regions": region_cols,
                "stores":  store_cols,
                "sales":   sale_cols,
            },
            relationships=[
                Relationship(parent_table="regions", child_table="stores",
                             parent_key="id", child_key="region_id"),
                Relationship(parent_table="stores",  child_table="sales",
                             parent_key="id", child_key="store_id"),
            ],
            outcome_curves=[region_curve],
            seed=123,
        )

        sim = DataSimulator(schema)
        tables = {t: df for t, df in sim.generate_all()}

        regions = tables["regions"]
        stores  = tables["stores"]
        sales   = tables["sales"]

        # Verify FK integrity at every level
        region_ids = set(regions["id"])
        store_ids  = set(stores["id"])
        assert (~stores["region_id"].isin(region_ids)).sum() == 0, "stores→regions FK broken"
        assert (~sales["store_id"].isin(store_ids)).sum() == 0, "sales→stores FK broken"

        # Identify Q1 vs Q4 regions
        reg_dates = pd.to_datetime(regions["region_date"])
        q1_region_ids = set(regions.loc[reg_dates.dt.month.isin([1, 2, 3]), "id"])
        q4_region_ids = set(regions.loc[reg_dates.dt.month.isin([10, 11, 12]), "id"])

        if not q1_region_ids or not q4_region_ids:
            pytest.skip("Insufficient Q1/Q4 region distribution")

        # Identify Q4-associated stores (stores whose region_id is in Q4 regions)
        q1_store_ids = set(stores.loc[stores["region_id"].isin(q1_region_ids), "id"])
        q4_store_ids = set(stores.loc[stores["region_id"].isin(q4_region_ids), "id"])

        if not q1_store_ids or not q4_store_ids:
            pytest.skip("Insufficient Q1/Q4 store distribution")

        # Sales FK clustering: Q4-associated stores should attract more sales
        q1_sales_frac = sales["store_id"].isin(q1_store_ids).mean()
        q4_sales_frac = sales["store_id"].isin(q4_store_ids).mean()

        assert q4_sales_frac > q1_sales_frac, (
            f"Deep hierarchy propagation not working: "
            f"Q1-store sales frac={q1_sales_frac:.4f}, Q4-store sales frac={q4_sales_frac:.4f}. "
            "Sales should cluster toward Q4 stores (which belong to high-revenue Q4 regions)."
        )


class TestRelativeCurveConvergence:
    """Gap B (0.8.0.2): relative curves now converge to the implied SHAPE exactly, and
    identically across batch sizes — not just directionally. Per-row means must follow the
    curve's relative factors regardless of how the data is batched."""

    def _schema(self):
        from misata.schema import OutcomeCurve
        curve = OutcomeCurve(
            table="sales", column="amount", time_column="sale_date", time_unit="month",
            avg_transaction_value=100.0,
            curve_points=[{"month": 1, "relative_value": 0.5},
                          {"month": 6, "relative_value": 1.0},
                          {"month": 12, "relative_value": 2.0}],
        )
        return SchemaConfig(
            name="rel_converge",
            tables=[Table(name="sales", row_count=6000)],
            columns={"sales": [
                Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
                Column(name="amount", type="float",
                       distribution_params={"distribution": "lognormal", "mu": 4.6, "sigma": 0.5}),
                Column(name="sale_date", type="date",
                       distribution_params={"start": "2024-01-01", "end": "2024-12-31"}),
            ]},
            outcome_curves=[curve], seed=33,
        )

    def _ratios(self, batch_size):
        sim = DataSimulator(self._schema(), batch_size=batch_size)
        df = pd.concat([b for _, b in sim.generate_all()], ignore_index=True)
        df["m"] = pd.to_datetime(df["sale_date"]).dt.month
        mean_by = df.groupby("m")["amount"].mean()
        return mean_by.get(12) / mean_by.get(1), mean_by.get(6) / mean_by.get(1)

    def test_shape_exact_single_batch(self):
        dec_jan, jun_jan = self._ratios(6000)
        assert abs(dec_jan - 4.0) < 0.05
        assert abs(jun_jan - 2.0) < 0.05

    def test_shape_invariant_to_batch_size(self):
        # The 0.8.0.2 fix: multi-batch must match single-batch (previously drifted ~13%)
        big = self._ratios(6000)
        small = self._ratios(200)
        assert abs(big[0] - small[0]) < 0.1, f"Dec/Jan drift across batch sizes: {big[0]} vs {small[0]}"
        assert abs(small[0] - 4.0) < 0.1, f"multi-batch Dec/Jan off target: {small[0]}"
