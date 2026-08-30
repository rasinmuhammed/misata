import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))

from contact_center_queueing import (
    QUEUES,
    _erlang_b,
    _erlang_c,
    _required_agents,
    build,
    verify,
)


def test_full_verify_suite_passes():
    tables = build(n_business_days=10, seed=41)
    assert verify(tables) is True


def test_erlang_b_recursion_matches_the_direct_factorial_formula():
    # The Sundt-Jewell recursion is only used because the direct formula
    # overflows for large N -- for a small N it must agree with it exactly.
    import math

    def erlang_b_factorial(n, a):
        num = a ** n / math.factorial(n)
        den = sum(a ** k / math.factorial(k) for k in range(n + 1))
        return num / den

    for a, n in [(10, 13), (5, 8), (20, 25)]:
        assert abs(_erlang_b(n, a) - erlang_b_factorial(n, a)) < 1e-9


def test_erlang_c_is_a_valid_probability():
    for a, n in [(5, 8), (10, 13), (20, 25)]:
        c = _erlang_c(n, a)
        assert 0.0 <= c <= 1.0


def test_required_agents_actually_clears_the_target():
    a, aht, target_pct, target_sec = 10.0, 300, 0.80, 20
    n = _required_agents(a, aht, target_pct, target_sec)
    c = _erlang_c(n, a)
    import math
    sl = 1 - c * math.exp(-(n - a) * target_sec / aht)
    assert sl >= target_pct
    # one fewer agent should NOT clear it (n is the minimum before shrinkage)
    c_minus = _erlang_c(n - 1, a)
    sl_minus = 1 - c_minus * math.exp(-((n - 1) - a) * target_sec / aht)
    assert sl_minus < target_pct


def test_staffing_always_exceeds_traffic_intensity():
    tables = build(n_business_days=10, seed=42)
    iv = tables["intervals"]
    assert (iv["agents_staffed"] > iv["traffic_intensity_erlangs"]).all()


def test_calls_answered_and_abandoned_reconcile_to_offered():
    tables = build(n_business_days=10, seed=43)
    iv = tables["intervals"]
    assert (iv["calls_answered"] + iv["calls_abandoned"] == iv["offered_calls"]).all()


def test_every_queue_clears_its_own_declared_sla_almost_always():
    tables = build(n_business_days=12, seed=44)
    iv = tables["intervals"].merge(tables["queues"][["queue_id", "queue_name", "sla_pct"]], on="queue_id")
    for name, g in iv.groupby("queue_name"):
        target = g["sla_pct"].iloc[0] * 100
        met = (g["service_level_pct"] >= target - 0.05).mean()
        assert met > 0.95


def test_aggregate_abandonment_stays_industry_plausible():
    tables = build(n_business_days=20, seed=45)
    iv = tables["intervals"].merge(tables["queues"][["queue_id", "queue_name"]], on="queue_id")
    agg = iv.groupby("queue_name").apply(
        lambda g: g["calls_abandoned"].sum() / g["offered_calls"].sum(), include_groups=False)
    assert (agg < 0.10).all()


def test_intraday_volume_curve_peaks_midday():
    tables = build(n_business_days=15, seed=46)
    iv = tables["intervals"].merge(tables["queues"][["queue_id", "queue_name"]], on="queue_id")
    for name, g in iv.groupby("queue_name"):
        by_time = g.groupby(g["interval_start"].dt.time)["offered_calls"].mean()
        assert by_time.iloc[len(by_time) // 2] > by_time.iloc[0]


def test_interval_start_falls_exactly_on_half_hour_marks():
    tables = build(n_business_days=8, seed=47)
    iv = tables["intervals"]
    assert iv["interval_start"].dt.minute.isin([0, 30]).all()
    assert (iv["interval_start"].dt.second == 0).all()


def test_no_orphan_foreign_keys():
    tables = build(n_business_days=8, seed=48)
    queues, intervals = tables["queues"], tables["intervals"]
    assert intervals["queue_id"].isin(queues["queue_id"]).all()


def test_all_four_queues_present_exactly_once():
    tables = build(n_business_days=5, seed=49)
    names = set(tables["queues"]["queue_name"])
    assert names == set(QUEUES.keys())
    assert tables["queues"]["queue_id"].is_unique
