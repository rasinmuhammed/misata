"""
The full predictive-maintenance capability, all in one fleet: exact
run-to-failure trajectories, real bearing-fault physics, a maintenance
history, and multi-modal sensors grounded in published degradation
literature rather than invented shapes.

What each piece is grounded in, briefly (full citations in
docs/domains/predictive-maintenance.md):

  * Vibration RMS: rises late, which is the textbook "exponential" shape
    already in this engine.
  * Vibration kurtosis: rises fast at the ONSET of defect growth, then
    falls back most of the way to baseline -- the one non-monotonic
    signature in the bearing literature, and the reason the "kurtosis"
    shape exists.
  * Bearing fault frequencies (BPFO/BPFI/BSF/FTF): textbook geometry, not
    fitted to anything -- checkable against published values.
  * MCSA current sidebands: bearing damage modulates the stator field,
    producing sidebands offset from the line frequency by each defect
    frequency.
  * Acoustic emission burst rate: a struck defect produces one burst per
    rolling-element pass, so burst rate tracks BPFO directly.
  * Maintenance: scheduled and condition-based repair policies, each
    logged, each provably reconciling against the readings it produced.

Run it directly. Every guarantee below is checked against the data this
script just generated, not asserted.
"""

import numpy as np
import pandas as pd

from misata.schema import Degradation, SensorResponse
from misata.degradation import generate, verify, defect_frequencies


def build(units: int = 100, seed: int = 42):
    spec = Degradation(
        table="readings",
        units=units,
        life_mean=220, life_std=45, life_min=40, life_max=1200,
        damage_exponent=1.3,
        unit_variation=0.10,

        # Real SKF 6205-2RS bearing geometry (the Case Western Reserve test
        # rig bearing), a 60 Hz supply -- the standard case in published
        # motor-current and acoustic-emission bearing studies.
        bearing_rpm=1797.0,
        line_frequency_hz=60.0,

        # Condition-based maintenance: repair the first time damage would
        # cross 55%, restoring 65% of accumulated damage. Imperfect on
        # purpose -- a perfect repair every time is not what real fleets do,
        # and the documented finding that repeated imperfect repairs raise
        # susceptibility to future deterioration only shows up if some
        # repairs are imperfect.
        maintenance_policy="condition_based",
        maintenance_trigger_damage=0.55,
        maintenance_restoration=0.65,
        maintenance_wear_penalty=0.10,

        responses=[
            SensorResponse(column="vibration_rms_mms", baseline=0.8, at_failure=7.5,
                            shape="exponential", noise=0.05, decimals=3),
            SensorResponse(column="vibration_kurtosis", baseline=3.0, at_failure=11.0,
                            shape="kurtosis", noise=0.15, decimals=2),
            SensorResponse(column="mcsa_sideband_amplitude_db", baseline=-45.0, at_failure=-18.0,
                            shape="exponential", noise=0.4, decimals=1),
            SensorResponse(column="ae_energy_mv2s", baseline=0.02, at_failure=1.8,
                            shape="exponential", noise=0.02, decimals=3),
            SensorResponse(column="bearing_temperature_c", baseline=42.0, at_failure=71.0,
                            shape="sqrt", noise=0.5, decimals=1),
        ],
    )
    df, events = generate(spec, seed=seed, return_events=True)
    return spec, df, events


def verify_all(spec, df, events) -> bool:
    checks = []

    core = verify(df, spec, events=events)
    checks.append(("run-to-failure RUL exact, damage=1.0 at every failure row",
                    core["rul_exact"]))

    freqs = defect_frequencies(1797.0)
    ratio = freqs["BPFO"] / 1797.0
    freq_ok, sideband_ok, ae_ok = True, True, True
    for uid, g in df.groupby("unit_id"):
        implied_rpm = g["bpfo_hz"].iloc[0] / ratio
        expected = defect_frequencies(implied_rpm)
        for name, hz in expected.items():
            key = name.lower()
            freq_ok &= abs(g[f"{key}_hz"].iloc[0] - hz) < 0.01
            sideband_ok &= abs(g[f"mcsa_{key}_upper_sideband_hz"].iloc[0] - (60.0 + hz)) < 0.01
        ae_ok &= abs(g["ae_burst_rate_hz"].mean() - expected["BPFO"]) / expected["BPFO"] < 0.03
    checks.append(("bearing fault frequencies match independent recomputation", freq_ok))
    checks.append(("MCSA sidebands match independent recomputation", sideband_ok))
    checks.append(("AE burst rate tracks each unit's own BPFO", ae_ok))

    kurt_ok = True
    for uid, g in df.groupby("unit_id"):
        g = g.sort_values("cycle")
        peak = g.loc[g["vibration_kurtosis"].idxmax()]
        kurt_ok &= 0.05 < peak["damage"] < 0.4 and peak["vibration_kurtosis"] > g["vibration_kurtosis"].iloc[-1]
    checks.append(("vibration_kurtosis peaks early and falls back, not monotonic", kurt_ok))

    checks.append(("maintenance events were logged", len(events) > 0))
    gaps = (events.sort_values(["unit_id", "cycle"])
                  .groupby("unit_id")["cycle"].diff().dropna())
    checks.append(("no repair-storm: minimum gap between repairs on one unit >= 3 cycles",
                    len(gaps) == 0 or gaps.min() >= 3))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)
    return all_ok


if __name__ == "__main__":
    spec, df, events = build()
    print(f"units: {df['unit_id'].nunique()}  readings: {len(df)}  maintenance events: {len(events)}")
    print(f"columns: {list(df.columns)}")
    print()
    ok = verify_all(spec, df, events)
    print()
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    raise SystemExit(0 if ok else 1)
