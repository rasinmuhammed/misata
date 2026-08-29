---
title: Generate Predictive Maintenance Synthetic Data in Python | Misata
description: Generate synthetic run-to-failure sensor data with exact remaining useful life, real bearing-fault physics (BPFO/BPFI/BSF/FTF), motor current sidebands, acoustic emission, and a maintenance event history. No AI4I 2020 shortcuts, no invented columns.
---

# Generate Predictive Maintenance Synthetic Data in Python

Most public predictive-maintenance datasets have one of two problems. AI4I 2020, the most widely used, has no unit identity and no time index: tool wear is as likely to fall as to rise between consecutive readings for the same machine, and there is no remaining-life label at all — a dataset for *predicting* failure in which nothing progresses toward failure. NASA C-MAPSS has real trajectories and RUL labels, and remains the standard benchmark, but it is a fixed 2008 turbofan simulation: fleet size, failure mix, and noise level are not yours to change.

Misata declares the failure time. Each unit draws a life, damage accumulates toward it, and every sensor follows the damage — so remaining useful life is exact by construction, not annotated afterward. That part of this capability is not new. What follows is: real bearing-fault physics wired into actual generated columns, a maintenance history (a fleet that only ever runs to failure and is never repaired is not what any real fleet looks like), and sensor signatures grounded in published degradation literature rather than shapes chosen for convenience.

```python
from misata.schema import Degradation, SensorResponse
from misata.degradation import generate

spec = Degradation(
    table="readings", units=100,
    life_mean=220, life_std=45, life_min=40, life_max=1200,

    # SKF 6205-2RS bearing geometry, the Case Western Reserve test rig
    # bearing -- checkable against published fault frequencies.
    bearing_rpm=1797.0, line_frequency_hz=60.0,

    # Repair the first time damage crosses 55%, restoring 65% of it.
    maintenance_policy="condition_based",
    maintenance_trigger_damage=0.55, maintenance_restoration=0.65,

    responses=[
        SensorResponse(column="vibration_rms_mms", baseline=0.8, at_failure=7.5, shape="exponential"),
        SensorResponse(column="vibration_kurtosis", baseline=3.0, at_failure=11.0, shape="kurtosis"),
    ],
)
readings, maintenance_events = generate(spec, seed=42, return_events=True)
```

Run the complete, runnable version directly: [`examples/predictive_maintenance_full.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/predictive_maintenance_full.py). It produces 100 units, roughly 81,000 readings, and 22 columns, and prints every guarantee below checked against the data it just generated:

```
[OK] run-to-failure RUL exact, damage=1.0 at every failure row
[OK] bearing fault frequencies match independent recomputation
[OK] MCSA sidebands match independent recomputation
[OK] AE burst rate tracks each unit's own BPFO
[OK] vibration_kurtosis peaks early and falls back, not monotonic
[OK] maintenance events were logged
[OK] no repair-storm: minimum gap between repairs on one unit >= 3 cycles

ALL CHECKS PASSED
```

## What each column is grounded in

Nothing below is an invented shape. Each one traces to a specific, checkable claim.

**Exact remaining useful life.** The failure cycle is drawn before any row exists; damage accumulates toward it as `(cycle/life) ** damage_exponent`. `rul_cycles` is life minus cycle, exactly, on every row, whether the unit ran to natural failure or was repaired along the way.

**Vibration RMS.** Sits near its healthy value for most of the life and climbs late — the `"exponential"` shape, already established before this update.

**Vibration kurtosis.** Published bearing studies report kurtosis rising quickly at the *onset* of defect growth, then falling back toward baseline as the defect widens and smooths — the opposite pattern of every other shape in this engine, which is why kurtosis is the feature used for early-stage detection rather than end-of-life. The `"kurtosis"` shape peaks at damage≈0.2 and decays most of the way back by failure — a non-monotonic signature no other shape here can produce.

**Bearing fault frequencies (BPFO, BPFI, BSF, FTF).** Textbook formulas from bearing geometry and shaft speed — not fitted to anything. Set `bearing_rpm` and every unit gets its own `bpfo_hz`, `bpfi_hz`, `bsf_hz`, `ftf_hz`, checkable independently against `misata.degradation.defect_frequencies()`.

**Motor current sidebands (MCSA).** Bearing damage modulates load on the stator's magnetic field, producing current sidebands offset from the line frequency by each defect frequency. Set `line_frequency_hz` alongside `bearing_rpm` and every unit gets `mcsa_{defect}_upper_sideband_hz` (line frequency + defect frequency) and `mcsa_{defect}_lower_sideband_hz` (the absolute difference, the standard convention when a defect frequency exceeds the line frequency).

**Acoustic emission burst rate.** A struck defect produces one acoustic burst per rolling-element pass, so burst rate tracks the outer-race defect frequency (BPFO) directly, not a growth curve. `ae_burst_rate_hz` sits within a couple of percent of each unit's own BPFO across its life, with the kind of small per-reading jitter a real tachometer/AE sensor pairing would show.

**Sideband amplitude and AE energy.** Both grow with damage severity the same way vibration RMS does, so they are declared as ordinary sensor responses (`shape="exponential"`) rather than a second bespoke growth model — the example above does exactly this for `mcsa_sideband_amplitude_db` and `ae_energy_mv2s`.

**Bearing temperature.** Rises due to increased friction as damage accumulates, typically lagging vibration as an indicator — modelled with `shape="sqrt"`, which moves early relative to the exponential vibration climb and then flattens.

## Maintenance history

Absent entirely before this. A fleet that only ever runs to failure has no maintenance history, and every real fleet is repaired.

```python
maintenance_policy="condition_based",       # or "scheduled"
maintenance_trigger_damage=0.55,             # repair the first time damage crosses this
maintenance_restoration=0.65,                # fraction of damage the repair removes
maintenance_wear_penalty=0.10,               # see below
```

A restoration of `1.0` is a perfect, as-good-as-new repair. Below `1.0` is imperfect, and the condition-based maintenance literature documents that repeated imperfect repairs leave a system more susceptible to future deterioration — modelled here as `maintenance_wear_penalty` shortening the unit's effective life after each imperfect repair. A perfect repair carries no such penalty.

`generate(spec, seed=42, return_events=True)` returns a second DataFrame: one row per intervention, with the cycle, the type, and the damage immediately before and after. `misata.degradation.verify()` accepts this event log and cross-checks every logged repair against the readings it actually produced — not merely that damage is allowed to have dropped, but that it dropped to *exactly* the value the event log claims.

A cooldown floor (5% of a unit's own nominal life by default, or set `maintenance_min_cooldown_cycles` explicitly) prevents an aggressive wear penalty from producing a "repair storm" — one unit visited dozens of times in its final few dozen cycles, which is not a maintenance history any real fleet would produce. This was a real defect found while building this feature, not a hypothetical: an early version did exactly that before the floor existed.

## What this is not

The damage law is a simplified lumped model, not a validated simulation of a specific bearing, spindle, or pump. The bearing geometry defaults (SKF 6205-2RS) and the fault-frequency formulas are textbook and checkable; the rate at which damage accumulates and how far each sensor travels are declared, not measured from a real machine. Anything published from this should rest its claims on the labels being exact and the physics being checkable, not on having been validated against a specific real bearing's run-to-failure data.
