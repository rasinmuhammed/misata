"""Tests for the numeric-quantization core: human-chosen quantities land on
the values humans actually choose.

These mechanisms exist to kill the next "synthetic data tells" after
nanosecond timestamps: 19-minute appointment slots, $43.27 shelf prices,
ages of 34.7 years, and float64-noise percentages — while leaving genuinely
measured quantities (gaming sessions, watch time, transaction sums) alone.
"""

import numpy as np
import pandas as pd
import pytest

import misata
from misata.quantization import (
    CHARM_DOMAINS,
    DURATION_GRID_MINUTES,
    apply_quantization,
    classify_quantization,
)
from misata.schema import Column, SchemaConfig, Table
from misata.simulator import DataSimulator


def _generate(config):
    data = {}
    for table_name, batch_df in DataSimulator(config).generate_all():
        if table_name in data:
            data[table_name] = pd.concat([data[table_name], batch_df], ignore_index=True)
        else:
            data[table_name] = batch_df
    return data


def _schema(table, columns, rows=2000, seed=11, domain=None):
    return SchemaConfig(
        name="Test",
        seed=seed,
        domain=domain,
        tables=[Table(name=table, row_count=rows)],
        columns={table: [Column(name="id", type="int")] + columns},
    )


def _cents(series):
    return set(np.round((series % 1) * 100).astype(int))


# ─── Classification ──────────────────────────────────────────────────────────


class TestClassification:
    def test_scheduled_durations_get_the_slot_grid(self):
        assert classify_quantization("duration_minutes", "appointments") == "duration_grid"
        assert classify_quantization("meeting_duration", "calendar") == "duration_grid"
        assert classify_quantization("duration_mins", "bookings") == "duration_grid"

    def test_measured_durations_are_left_alone(self):
        # Gaming sessions, match lengths and watch time are measured, not booked.
        assert classify_quantization("duration_minutes", "sessions") is None
        assert classify_quantization("duration_minutes", "matches") is None
        assert classify_quantization("watch_duration_minutes", "watch_history") is None
        assert classify_quantization("duration_minutes", "flights") is None

    def test_non_minute_durations_never_snap(self):
        assert classify_quantization("session_duration_seconds", "appointments") is None
        assert classify_quantization("trial_duration_days", "bookings") is None
        assert classify_quantization("duration_hours", "meetings") is None

    def test_prices_charm_only_in_retailish_domains(self):
        assert classify_quantization("price", "products", "ecommerce") == "charm_price"
        assert classify_quantization("unit_price", "items", "retail") == "charm_price"
        assert classify_quantization("order_amount", "orders", "marketplace") == "charm_price"
        assert classify_quantization("shipping_fee", "orders", "saas") == "charm_price"
        # Fintech transaction amounts and healthcare claims are sums, not shelf prices.
        assert classify_quantization("transaction_amount", "payments", "fintech") is None
        assert classify_quantization("claim_amount", "claims", "healthcare") is None
        assert classify_quantization("price", "products", None) is None

    def test_age_matches_whole_token_only(self):
        assert classify_quantization("age", "patients") == "age"
        assert classify_quantization("patient_age", "patients") == "age"
        # Substring "age" inside another word must not trigger.
        assert classify_quantization("usage", "metrics") is None
        assert classify_quantization("page_count", "documents") is None
        assert classify_quantization("average_score", "stats") is None

    def test_percentage_stems(self):
        assert classify_quantization("discount_percentage", "orders") == "percentage"
        assert classify_quantization("cpu_percent", "servers") == "percentage"
        assert classify_quantization("growth_pct", "metrics") == "percentage"
        assert classify_quantization("completion_rate", "tasks") is None


# ─── Profile application ─────────────────────────────────────────────────────


class TestApplyQuantization:
    def test_duration_snaps_to_slot_grid(self):
        raw = np.array([7, 19, 35, 52, 64, 90, 3])
        out = apply_quantization(raw, "duration_grid", np.random.default_rng(0))
        assert list(out) == [5, 15, 30, 45, 60, 90, 5]

    def test_long_durations_step_in_half_hours(self):
        out = apply_quantization(
            np.array([131.0, 224.0]), "duration_grid", np.random.default_rng(0)
        )
        assert list(out) == [120.0, 210.0]
        assert (out % 30 == 0).all()

    def test_charm_prices_end_in_99_95_or_00(self):
        raw = np.random.default_rng(1).uniform(1.0, 500.0, size=3000)
        out = apply_quantization(raw, "charm_price", np.random.default_rng(2))
        cents = np.round((out % 1) * 100).astype(int)
        assert set(cents) == {0, 95, 99}
        # .99 dominates, the way merchants actually price
        assert (cents == 99).mean() > 0.35
        # endings move a price by less than a dollar
        assert np.abs(out - raw).max() < 1.0

    def test_charm_preserves_structural_zeros(self):
        raw = np.array([0.0, 0.0, 12.34])
        out = apply_quantization(raw, "charm_price", np.random.default_rng(0))
        assert out[0] == 0.0 and out[1] == 0.0
        assert out[2] != 12.34

    def test_age_rounds_to_integers(self):
        out = apply_quantization(
            np.array([34.7, 18.2, 64.5001]), "age", np.random.default_rng(0)
        )
        assert (out == np.round(out)).all()

    def test_percentage_rounding_adapts_to_scale(self):
        scale_100 = apply_quantization(
            np.array([34.61234, 7.98765]), "percentage", np.random.default_rng(0)
        )
        assert list(scale_100) == [34.6, 8.0]
        fraction = apply_quantization(
            np.array([0.346123, 0.079876]), "percentage", np.random.default_rng(0)
        )
        assert list(fraction) == [0.346, 0.08]

    def test_deterministic_under_seed(self):
        raw = np.random.default_rng(3).uniform(1.0, 200.0, size=500)
        a = apply_quantization(raw, "charm_price", np.random.default_rng(9))
        b = apply_quantization(raw, "charm_price", np.random.default_rng(9))
        assert list(a) == list(b)


# ─── Simulator integration ───────────────────────────────────────────────────


class TestSimulatorQuantization:
    def _durations(self, **col_kwargs):
        config = _schema(
            "appointments",
            [
                Column(
                    name="duration_minutes",
                    type="int",
                    distribution_params={
                        "distribution": "normal", "mean": 25, "std": 10,
                        "min": 5, "max": 90, **col_kwargs.get("params", {}),
                    },
                )
            ],
            seed=col_kwargs.get("seed", 11),
        )
        return _generate(config)["appointments"]["duration_minutes"]

    def test_appointment_durations_land_on_the_grid(self):
        d = self._durations()
        assert set(d.unique()) <= set(DURATION_GRID_MINUTES.astype(int))
        # the classic 15/30/45 slots dominate for a ~25-minute mean
        top = set(d.value_counts().index[:3])
        assert top <= {15, 30, 45, 60}
        assert d.dtype.kind == "i"

    def test_quantize_false_opts_out(self):
        d = self._durations(params={"quantize": False})
        assert (d % 5 != 0).any()  # raw normal draws stay off-grid

    def test_explicit_choices_are_never_touched(self):
        config = _schema(
            "appointments",
            [
                Column(
                    name="duration_minutes",
                    type="int",
                    distribution_params={"choices": [7, 19, 35], "probabilities": [0.4, 0.4, 0.2]},
                )
            ],
        )
        d = _generate(config)["appointments"]["duration_minutes"]
        assert set(d.unique()) <= {7, 19, 35}

    def test_measured_session_durations_stay_continuous(self):
        config = _schema(
            "sessions",
            [
                Column(
                    name="duration_minutes",
                    type="int",
                    distribution_params={
                        "distribution": "lognormal", "mu": 4.2, "sigma": 1.0,
                        "min": 1, "max": 600, "decimals": 0,
                    },
                )
            ],
        )
        d = _generate(config)["sessions"]["duration_minutes"]
        assert (d % 5 != 0).mean() > 0.5

    def test_ecommerce_prices_are_charm_priced(self):
        config = _schema(
            "products",
            [Column(name="price", type="float")],
            domain="ecommerce",
        )
        price = _generate(config)["products"]["price"]
        assert _cents(price) <= {0, 95, 99}

    def test_prices_without_retail_domain_keep_raw_cents(self):
        config = _schema("payments", [Column(name="amount", type="float")], domain="fintech")
        amount = _generate(config)["payments"]["amount"]
        assert len(_cents(amount)) > 10

    def test_reproducible_under_seed(self):
        a = self._durations(seed=42)
        b = self._durations(seed=42)
        assert list(a) == list(b)
        config = _schema("products", [Column(name="price", type="float")], domain="ecommerce", seed=42)
        p1 = _generate(config)["products"]["price"]
        p2 = _generate(_schema("products", [Column(name="price", type="float")], domain="ecommerce", seed=42))["products"]["price"]
        assert list(p1) == list(p2)

    def test_quantize_false_survives_dict_schema(self):
        def build(quantize):
            col = {"type": "integer", "min": 5, "max": 90,
                   "distribution": "normal", "mean": 25, "std": 10}
            if quantize is not None:
                col["quantize"] = quantize
            return misata.from_dict_schema(
                {"appointments": {
                    "id": {"type": "integer", "primary_key": True},
                    "duration_minutes": col,
                }},
                row_count=2000,
                seed=11,
            )

        on = _generate(build(None))["appointments"]["duration_minutes"]
        off = _generate(build(False))["appointments"]["duration_minutes"]
        assert (on % 5 == 0).all()
        assert (off % 5 != 0).any()

    def test_end_to_end_hospital_durations_on_grid(self):
        tables = misata.generate("A hospital with 300 patients and doctors", seed=7)
        d = tables["appointments"]["duration_minutes"]
        assert (d % 5 == 0).all()
        assert set(d.unique()) <= set(DURATION_GRID_MINUTES.astype(int))

    def test_charm_domains_cover_the_retailish_set(self):
        assert {"ecommerce", "retail", "marketplace", "saas"} <= CHARM_DOMAINS
