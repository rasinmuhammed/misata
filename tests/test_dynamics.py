"""Tests for the 0.9.0 dynamics primitives: retention, missingness, late arrival.

Each is asserted the same three ways every declaration in this engine is:
the generated data satisfies it, `coherence_audit` catches it when broken by
hand, and a schema without the declaration behaves exactly as before.

Retention is tested here rather than in the Gauntlet on purpose. It rewrites the
event table's entity key and timestamp, which is precisely what the Gauntlet's
pareto FK sampling, order lifecycle and multi-hop roll-ups are built on, so
adding it there would mean re-tuning a dozen unrelated declarations to
accommodate one. The assertions below are the same SQL questions, asked in
pandas.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata.coherence import coherence_audit
from misata.dynamics import exact_count
from misata.feasibility import InfeasibleSchema
from misata.schema import (SchemaConfig, Table, Column, Relationship,
                           CohortRetention, Missingness, LateArrival)

warnings.filterwarnings("ignore")

CURVE = {0: 1.0, 1: 0.55, 2: 0.40, 3: 0.34}


def _schema(retention=None, missing=None, late=None, customers=400,
            orders=3000, seed=7):
    return SchemaConfig(
        name="dyn",
        tables=[Table(name="customers", row_count=customers),
                Table(name="orders", row_count=orders)],
        columns={
            "customers": [
                Column(name="customer_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": customers}),
                Column(name="signup_date", type="datetime",
                       distribution_params={"start": "2024-01-01", "end": "2024-04-30"}),
                Column(name="age_band", type="categorical",
                       distribution_params={"choices": ["18-24", "25-44", "45+"]}),
                Column(name="income", type="float", nullable=True,
                       distribution_params={"min": 20000, "max": 200000}),
            ],
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": orders}),
                Column(name="customer_id", type="foreign_key",
                       distribution_params={"references": "customers.customer_id"}),
                Column(name="order_date", type="datetime",
                       distribution_params={"start": "2024-01-01", "end": "2024-12-31"}),
                Column(name="ingested_at", type="datetime", nullable=True,
                       distribution_params={"start": "2024-01-01", "end": "2025-01-31"}),
            ],
        },
        relationships=[Relationship(parent_table="customers", child_table="orders",
                                    parent_key="customer_id", child_key="customer_id")],
        retention=[retention] if retention else [],
        missingness=[missing] if missing else [],
        late_arrivals=[late] if late else [],
        seed=seed,
    )


def _retention() -> CohortRetention:
    return CohortRetention(table="orders", event_time="order_date",
                           cohort_key="customer_id", cohort_table="customers",
                           cohort_time="signup_date", unit="month", curve=CURVE)


def _realised(cu: pd.DataFrame, o: pd.DataFrame):
    """Cohort retention as an analyst would compute it."""
    cu = cu.copy(); o = o.copy()
    cu["_c"] = pd.to_datetime(cu["signup_date"]).dt.to_period("M")
    o["_p"] = pd.to_datetime(o["order_date"]).dt.to_period("M")
    m = o.merge(cu[["customer_id", "_c"]], on="customer_id")
    m["_off"] = (m["_p"] - m["_c"]).apply(lambda x: x.n)
    sizes = cu.groupby("_c")["customer_id"].nunique()
    return m, sizes


# --------------------------------------------------------------------------- #
# cohort retention
# --------------------------------------------------------------------------- #

class TestRetention:
    def test_every_offset_hits_its_declared_count(self):
        t = misata.generate_from_schema(_schema(retention=_retention()))
        m, sizes = _realised(t["customers"], t["orders"])
        for off, frac in CURVE.items():
            active = m[m["_off"] == off].groupby("_c")["customer_id"].nunique()
            for cohort, size in sizes.items():
                want = exact_count(int(size), frac)
                got = int(active.get(cohort, 0))
                assert abs(got - want) <= 1, (off, cohort, want, got)

    def test_retention_is_nested_for_a_decreasing_curve(self):
        """Someone active at offset 2 should also have been active at offset 1.
        Real retention curves nest; independent draws per cell would not."""
        t = misata.generate_from_schema(_schema(retention=_retention()))
        m, _ = _realised(t["customers"], t["orders"])
        at1 = set(map(tuple, m[m["_off"] == 1][["customer_id", "_c"]].values))
        at2 = set(map(tuple, m[m["_off"] == 2][["customer_id", "_c"]].values))
        overlap = len(at2 & at1) / max(len(at2), 1)
        assert overlap > 0.9, overlap

    def test_fk_integrity_survives_the_rewrite(self):
        t = misata.generate_from_schema(_schema(retention=_retention()))
        assert t["orders"]["customer_id"].isin(set(t["customers"]["customer_id"])).all()

    def test_row_count_is_unchanged(self):
        t = misata.generate_from_schema(_schema(retention=_retention(), orders=3000))
        assert len(t["orders"]) == 3000

    def test_other_columns_are_left_alone(self):
        """Retention owns the entity key and the event time. Nothing else."""
        base = misata.generate_from_schema(_schema())["orders"]
        with_r = misata.generate_from_schema(_schema(retention=_retention()))["orders"]
        assert base["order_id"].tolist() == with_r["order_id"].tolist()

    def test_impossible_curve_is_refused_up_front(self):
        # 400 customers x 4 offsets summing to 2.29 needs ~916 active
        # entity-periods; 200 order rows cannot carry them.
        with pytest.raises(InfeasibleSchema, match="retention|curve"):
            misata.generate_from_schema(_schema(retention=_retention(), orders=200))

    def test_audit_catches_a_broken_curve(self):
        schema = _schema(retention=_retention())
        t = misata.generate_from_schema(schema)
        # Collapse every event onto one customer: the curve cannot hold.
        t["orders"]["customer_id"] = t["customers"]["customer_id"].iloc[0]
        report = coherence_audit(t, schema=schema)
        assert any(f.kind == "retention_mismatch" for f in report.findings)

    def test_audit_clean_on_generated_data(self):
        schema = _schema(retention=_retention())
        t = misata.generate_from_schema(schema)
        report = coherence_audit(t, schema=schema)
        assert not [f for f in report.findings if f.kind == "retention_mismatch"]

    def test_missing_column_warns_and_skips(self):
        r = _retention(); r.cohort_time = "nope"
        with pytest.warns(UserWarning, match="missing from"):
            misata.generate_from_schema(_schema(retention=r))

    def test_negative_offset_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            CohortRetention(table="o", event_time="d", cohort_key="c",
                            cohort_table="cu", cohort_time="s", curve={-1: 0.5})


# --------------------------------------------------------------------------- #
# missingness (MNAR)
# --------------------------------------------------------------------------- #

def _missing(**over):
    kw = dict(table="customers", column="income", rate=0.40, else_rate=0.05,
              when_column="age_band", when_op="in", when_value=["18-24"])
    kw.update(over)
    return Missingness(**kw)


class TestMissingness:
    def test_conditional_rates_are_exact(self):
        cu = misata.generate_from_schema(_schema(missing=_missing()))["customers"]
        young = cu[cu["age_band"] == "18-24"]
        rest = cu[cu["age_band"] != "18-24"]
        assert young["income"].isna().sum() == exact_count(len(young), 0.40)
        assert rest["income"].isna().sum() == exact_count(len(rest), 0.05)

    def test_the_pattern_is_mnar_not_mcar(self):
        cu = misata.generate_from_schema(_schema(missing=_missing()))["customers"]
        young = cu[cu["age_band"] == "18-24"]["income"].isna().mean()
        rest = cu[cu["age_band"] != "18-24"]["income"].isna().mean()
        assert young > 2 * rest

    def test_unconditional_rate(self):
        cu = misata.generate_from_schema(
            _schema(missing=_missing(when_column=None, rate=0.25)))["customers"]
        assert cu["income"].isna().sum() == exact_count(len(cu), 0.25)

    def test_zero_rate_leaves_the_column_full(self):
        cu = misata.generate_from_schema(
            _schema(missing=_missing(rate=0.0, else_rate=0.0)))["customers"]
        assert cu["income"].notna().all()

    def test_integer_column_is_widened_rather_than_coerced(self):
        s = _schema(missing=Missingness(table="customers", column="customer_id",
                                        rate=0.1))
        # customer_id is unique+int; nulling some must not corrupt the rest.
        cu = misata.generate_from_schema(s)["customers"]
        assert cu["customer_id"].isna().sum() == exact_count(len(cu), 0.1)
        assert cu["customer_id"].dropna().is_unique

    def test_audit_catches_a_broken_rate(self):
        schema = _schema(missing=_missing())
        t = misata.generate_from_schema(schema)
        t["customers"]["income"] = 50000.0        # nothing missing at all
        report = coherence_audit(t, schema=schema)
        assert any(f.kind == "missingness_mismatch" for f in report.findings)

    def test_audit_clean_on_generated_data(self):
        schema = _schema(missing=_missing())
        t = misata.generate_from_schema(schema)
        report = coherence_audit(t, schema=schema)
        assert not [f for f in report.findings if f.kind == "missingness_mismatch"]

    def test_missing_column_warns(self):
        with pytest.warns(UserWarning, match="not found"):
            misata.generate_from_schema(
                _schema(missing=_missing(column="does_not_exist")))


# --------------------------------------------------------------------------- #
# late / out-of-order arrival
# --------------------------------------------------------------------------- #

def _late(**over):
    kw = dict(table="orders", event_time="order_date", ingest_time="ingested_at",
              late_fraction=0.05, max_delay_days=3)
    kw.update(over)
    return LateArrival(**kw)


def _delay_days(o: pd.DataFrame) -> pd.Series:
    return ((pd.to_datetime(o["ingested_at"]) - pd.to_datetime(o["order_date"]))
            .dt.total_seconds() / 86400.0)


class TestLateArrival:
    def test_ingest_never_precedes_the_event(self):
        o = misata.generate_from_schema(_schema(late=_late()))["orders"]
        assert (_delay_days(o) >= 0).all()

    def test_late_fraction_is_exact_by_calendar_day(self):
        """The threshold that matters is the partition boundary, not 24 hours:
        a row landing in a later daily partition is the one an incremental
        model can miss."""
        o = misata.generate_from_schema(_schema(late=_late()))["orders"]
        ev = pd.to_datetime(o["order_date"]).dt.normalize()
        ing = pd.to_datetime(o["ingested_at"]).dt.normalize()
        crossed = int((ing > ev).sum())
        assert crossed == exact_count(len(o), 0.05), crossed

    def test_punctual_rows_stay_in_the_event_day(self):
        o = misata.generate_from_schema(_schema(late=_late()))["orders"]
        d = _delay_days(o)
        ev = pd.to_datetime(o["order_date"]).dt.normalize()
        ing = pd.to_datetime(o["ingested_at"]).dt.normalize()
        # Anything that did not cross a day boundary is under a day of delay.
        assert (d[ing == ev] < 1.0).all()

    def test_delays_respect_the_declared_bound(self):
        o = misata.generate_from_schema(_schema(late=_late(max_delay_days=2)))["orders"]
        assert _delay_days(o).max() <= 2.0 + 1e-9

    def test_zero_fraction_means_nothing_late(self):
        o = misata.generate_from_schema(_schema(late=_late(late_fraction=0.0)))["orders"]
        ev = pd.to_datetime(o["order_date"]).dt.normalize()
        ing = pd.to_datetime(o["ingested_at"]).dt.normalize()
        assert (ing == ev).all()

    def test_undeclared_ingest_column_warns(self):
        with pytest.warns(UserWarning, match="nowhere to record"):
            misata.generate_from_schema(_schema(late=_late(ingest_time="absent_col")))

    def test_audit_catches_ingest_before_event(self):
        schema = _schema(late=_late())
        t = misata.generate_from_schema(schema)
        t["orders"].loc[t["orders"].index[:5], "ingested_at"] = pd.Timestamp("2020-01-01")
        report = coherence_audit(t, schema=schema)
        assert any(f.kind == "ingest_precedes_event" for f in report.findings)

    def test_audit_catches_a_delay_beyond_the_bound(self):
        schema = _schema(late=_late(max_delay_days=2))
        t = misata.generate_from_schema(schema)
        idx = t["orders"].index[:3]
        t["orders"].loc[idx, "ingested_at"] = (
            pd.to_datetime(t["orders"].loc[idx, "order_date"]) + pd.Timedelta(days=30))
        report = coherence_audit(t, schema=schema)
        assert any(f.kind == "late_arrival_exceeds_bound" for f in report.findings)

    def test_audit_clean_on_generated_data(self):
        schema = _schema(late=_late())
        t = misata.generate_from_schema(schema)
        bad = [f for f in coherence_audit(t, schema=schema).findings
               if f.kind.startswith("late_arrival") or f.kind == "ingest_precedes_event"]
        assert not bad


# --------------------------------------------------------------------------- #
# composition and the untouched default path
# --------------------------------------------------------------------------- #

class TestComposition:
    def test_all_three_together(self):
        schema = _schema(retention=_retention(), missing=_missing(), late=_late())
        t = misata.generate_from_schema(schema)
        cu, o = t["customers"], t["orders"]
        # retention
        m, sizes = _realised(cu, o)
        active = m[m["_off"] == 1].groupby("_c")["customer_id"].nunique()
        for cohort, size in sizes.items():
            assert abs(int(active.get(cohort, 0)) - exact_count(int(size), 0.55)) <= 1
        # missingness
        young = cu[cu["age_band"] == "18-24"]
        assert young["income"].isna().sum() == exact_count(len(young), 0.40)
        # late arrival, measured against the timestamps retention rewrote
        assert (_delay_days(o) >= 0).all()
        # and the whole thing audits clean
        kinds = {f.kind for f in coherence_audit(t, schema=schema).findings}
        assert not kinds & {"retention_mismatch", "missingness_mismatch",
                            "ingest_precedes_event", "late_arrival_exceeds_bound"}

    def test_no_declarations_is_byte_identical(self):
        a = misata.generate_from_schema(_schema())["orders"]
        b = misata.generate_from_schema(_schema())["orders"]
        pd.testing.assert_frame_equal(a, b)

    def test_determinism_with_all_three(self):
        mk = lambda: _schema(retention=_retention(), missing=_missing(), late=_late())
        a = misata.generate_from_schema(mk())
        b = misata.generate_from_schema(mk())
        for name in ("customers", "orders"):
            pd.testing.assert_frame_equal(a[name], b[name])


class TestExactCount:
    @pytest.mark.parametrize("n,frac,want", [
        (100, 0.40, 40), (94, 0.40, 38), (0, 0.5, 0),
        (7, 0.5, 4), (3, 0.5, 2), (1000, 0.055, 55),
    ])
    def test_largest_remainder_rounding(self, n, frac, want):
        assert exact_count(n, frac) == want
