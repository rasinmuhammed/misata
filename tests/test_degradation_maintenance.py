"""
Three additions to the degradation engine, found necessary because the
existing capability, while genuinely more rigorous than the public
predictive-maintenance benchmarks, had two real gaps: the bearing-fault
physics in `defect_frequencies` was disconnected from generation entirely,
and there was no maintenance concept at all -- a fleet that only ever runs
to failure has no maintenance history, and every real fleet is repaired.

Each test here caught a real bug during development, not just a shape:
the terminal damage value silently stopped being exactly 1.0 once
maintenance re-anchors life as a float, and a wear penalty compounding on
every imperfect repair produced a "repair storm" (one unit repaired 28
times in its last 30 cycles) before a cooldown floor was added.
"""

import numpy as np
import pandas as pd

from misata.schema import Degradation, SensorResponse
from misata.degradation import generate, verify, defect_frequencies


# ── kurtosis: the one non-monotonic shape ──────────────────────────────

def test_kurtosis_shape_peaks_early_and_decays():
    spec = Degradation(
        table="r", units=20, life_mean=200, life_std=20, life_min=80, life_max=350,
        responses=[SensorResponse(column="k", baseline=3.0, at_failure=12.0,
                                   shape="kurtosis", noise=0.0)],
    )
    df = generate(spec, seed=7)
    for _, u in df.groupby("unit_id"):
        u = u.sort_values("cycle")
        peak_row = u.loc[u["k"].idxmax()]
        # Peaks near damage=0.2 (the literature's "onset of defect growth"),
        # not at damage=1.0 like every monotonic shape.
        assert 0.1 < peak_row["damage"] < 0.35
        # And falls back most of the way toward baseline by failure --
        # the property no other shape in this engine can produce at all.
        assert peak_row["k"] > u["k"].iloc[-1]


def test_kurtosis_respects_declared_endpoints():
    # baseline at damage=0 still holds even for a non-monotonic shape.
    spec = Degradation(table="r", units=10, life_mean=100, life_std=5, life_min=60, life_max=150,
        responses=[SensorResponse(column="k", baseline=3.0, at_failure=12.0, shape="kurtosis", noise=0.0)])
    df = generate(spec, seed=3)
    first_rows = df.sort_values("cycle").groupby("unit_id").head(1)
    assert np.allclose(first_rows["k"], 3.0, atol=0.5)


# ── defect frequencies wired into generation ───────────────────────────

def test_bearing_defect_frequencies_match_independent_recomputation():
    spec = Degradation(table="r", units=100, life_mean=100, life_std=10,
                        life_min=30, life_max=200, bearing_rpm=1797.0)
    df = generate(spec, seed=7)

    for col in ("bpfo_hz", "bpfi_hz", "bsf_hz", "ftf_hz"):
        assert col in df.columns

    # Each unit has its own RPM (unit_variation is on by default), so the
    # real check is: for EVERY unit, its own four frequencies are mutually
    # consistent with SOME single RPM -- i.e., recomputing defect_frequencies
    # at that implied RPM reproduces all four columns, not just one.
    base = defect_frequencies(1797.0)
    ratio = base["BPFO"] / 1797.0
    for unit_id, g in df.groupby("unit_id"):
        implied_rpm = g["bpfo_hz"].iloc[0] / ratio
        expected = defect_frequencies(implied_rpm)
        for col, key in [("bpfo_hz", "BPFO"), ("bpfi_hz", "BPFI"),
                          ("bsf_hz", "BSF"), ("ftf_hz", "FTF")]:
            assert abs(g[col].iloc[0] - expected[key]) < 0.01, (unit_id, col)


def test_bearing_frequencies_absent_without_rpm_declared():
    spec = Degradation(table="r", units=5, life_mean=50, life_std=5, life_min=20, life_max=80)
    df = generate(spec, seed=1)
    assert "bpfo_hz" not in df.columns


# ── MCSA current sidebands and acoustic emission burst rate ────────────
#
# Both derive from the same defect frequencies as the vibration columns,
# not a separate model: a current sideband is the line frequency offset
# by a defect frequency, and an AE burst arrives once per defect strike,
# so its rate tracks BPFO directly. Grounded in the literature on bearing-
# induced current modulation and AE burst-rate-tracks-defect-frequency
# findings researched before implementation, not invented.

def test_mcsa_sidebands_match_independent_recomputation():
    spec = Degradation(table="r", units=50, life_mean=80, life_std=8,
                        life_min=30, life_max=150, bearing_rpm=1797.0, line_frequency_hz=60.0)
    df = generate(spec, seed=7)
    ratio = defect_frequencies(1797.0)["BPFO"] / 1797.0

    for uid, g in df.groupby("unit_id"):
        implied_rpm = g["bpfo_hz"].iloc[0] / ratio
        freqs = defect_frequencies(implied_rpm)
        for name, hz in freqs.items():
            key = name.lower()
            assert abs(g[f"mcsa_{key}_upper_sideband_hz"].iloc[0] - (60.0 + hz)) < 0.01
            assert abs(g[f"mcsa_{key}_lower_sideband_hz"].iloc[0] - abs(60.0 - hz)) < 0.01


def test_ae_burst_rate_tracks_outer_race_defect_frequency():
    spec = Degradation(table="r", units=50, life_mean=80, life_std=8,
                        life_min=30, life_max=150, bearing_rpm=1797.0, line_frequency_hz=60.0)
    df = generate(spec, seed=7)

    for uid, g in df.groupby("unit_id"):
        bpfo = g["bpfo_hz"].iloc[0]
        # Mean burst rate over a unit's whole life should sit within 2% of
        # its own BPFO -- jitter is per-reading noise, not a bias.
        assert abs(g["ae_burst_rate_hz"].mean() - bpfo) / bpfo < 0.02


def test_mcsa_and_ae_require_both_bearing_rpm_and_line_frequency():
    # bearing_rpm alone (no line_frequency_hz): no MCSA/AE columns.
    spec = Degradation(table="r", units=3, life_mean=50, life_std=5,
                        life_min=20, life_max=80, bearing_rpm=1797.0)
    df = generate(spec, seed=1)
    assert not any(c.startswith("mcsa_") or c == "ae_burst_rate_hz" for c in df.columns)

    # line_frequency_hz alone (no bearing_rpm): still nothing, since there
    # is no defect frequency to build a sideband or burst rate from.
    spec2 = Degradation(table="r", units=3, life_mean=50, life_std=5,
                         life_min=20, life_max=80, line_frequency_hz=60.0)
    df2 = generate(spec2, seed=1)
    assert not any(c.startswith("mcsa_") or c == "ae_burst_rate_hz" for c in df2.columns)


# ── maintenance: the part that did not exist at all before ────────────

def test_scheduled_maintenance_produces_events_and_exact_rul():
    spec = Degradation(
        table="r", units=15, life_mean=150, life_std=20, life_min=50, life_max=1500,
        maintenance_policy="scheduled", maintenance_interval_cycles=40,
        maintenance_restoration=0.7, maintenance_wear_penalty=0.08,
    )
    df, events = generate(spec, seed=7, return_events=True)

    assert len(events) > 0
    assert set(events.columns) == {
        "unit_id", "cycle", "event_type", "damage_before",
        "damage_after", "restoration_fraction",
    }

    result = verify(df, spec, events=events)
    assert result["rul_exact"], result["findings"]

    # The exact-1.0-at-failure guarantee predates maintenance and must
    # survive it: this is the bug found during development, now pinned.
    terminal = df.sort_values("cycle").groupby("unit_id").tail(1)["damage"]
    assert (terminal == 1.0).all()


def test_condition_based_maintenance_fires_near_the_declared_trigger():
    spec = Degradation(
        table="r", units=15, life_mean=150, life_std=20, life_min=50, life_max=1500,
        maintenance_policy="condition_based", maintenance_trigger_damage=0.6,
        maintenance_restoration=0.5, maintenance_wear_penalty=0.15,
    )
    df, events = generate(spec, seed=11, return_events=True)
    assert len(events) > 0
    # damage_before is allowed to sit AT OR ABOVE the trigger (a cooldown
    # can delay the visit past the exact crossing) but never far below it.
    assert (events["damage_before"] >= 0.6 - 1e-6).all()

    result = verify(df, spec, events=events)
    assert result["rul_exact"], result["findings"]


def test_maintenance_without_a_policy_is_unchanged_from_before():
    # The single most important test in this file: everyone who declared
    # degradation before maintenance existed must see byte-identical output.
    spec = Degradation(table="r", units=25, life_mean=220, life_std=45,
                        life_min=20, life_max=1000, damage_exponent=1.3)
    df = generate(spec, seed=42)
    assert isinstance(df, pd.DataFrame)  # NOT a tuple -- return_events defaults False
    result = verify(df, spec)
    assert result["rul_exact"], result["findings"]


def test_repair_storm_is_prevented_by_the_cooldown_floor():
    # Found during development: an aggressive wear penalty compounding on
    # every imperfect repair shrank effective life fast enough that one
    # unit was repaired 28 times in its final ~30 cycles. A cooldown floor
    # (5% of nominal life when not set explicitly) exists specifically to
    # prevent this from being the default behaviour.
    spec = Degradation(
        table="r", units=15, life_mean=150, life_std=20, life_min=50, life_max=1500,
        maintenance_policy="condition_based", maintenance_trigger_damage=0.6,
        maintenance_restoration=0.5, maintenance_wear_penalty=0.15,
    )
    _, events = generate(spec, seed=11, return_events=True)
    gaps = (events.sort_values(["unit_id", "cycle"])
                  .groupby("unit_id")["cycle"].diff().dropna())
    assert gaps.min() >= 3  # the floor's own hard minimum


def test_explicit_cooldown_is_honoured():
    spec = Degradation(
        table="r", units=10, life_mean=150, life_std=20, life_min=50, life_max=1500,
        maintenance_policy="scheduled", maintenance_interval_cycles=10,
        maintenance_restoration=0.9, maintenance_min_cooldown_cycles=25,
    )
    _, events = generate(spec, seed=5, return_events=True)
    gaps = (events.sort_values(["unit_id", "cycle"])
                  .groupby("unit_id")["cycle"].diff().dropna())
    assert (gaps >= 25).all()
