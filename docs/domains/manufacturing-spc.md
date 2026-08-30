---
title: "Generate Synthetic Manufacturing SPC / Cpk Data in Python | Misata"
description: "Generate process-control measurements (processes, subgroups, individual readings) built to a declared Cp/Cpk process capability via a real Xbar-R control chart, with Western Electric Rule violations that actually fire where an engineered tool-wear drift happens, not asserted."
---

# Generate Synthetic Manufacturing SPC / Cpk Data in Python

A "measurement" column of independently random floats can't sit at a declared Cp/Cpk, can't split into the right within/between variance an Xbar-R chart actually estimates from, and can't trigger a Western Electric Rule violation at a believable rate. This example builds all three: process capability, control limits, and out-of-control detection, the way a real shop-floor SPC system does it.

```python
import misata

schema = {
    "processes": {
        "__rows__": 5,
        "process_id": {"type": "integer", "primary_key": True},
    },
    "subgroups": {
        "__rows__": 450,
        "subgroup_id": {"type": "integer", "primary_key": True},
        "process_id": {"type": "integer", "foreign_key": {"table": "processes", "column": "process_id"}},
    },
}
tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=19))
print(list(tables.keys()))   # ['processes', 'subgroups']
```

That's the structural shape. The full example — real spec limits, a declared target Cpk per process solved for the underlying sigma, an engineered tool-wear drift, and Western Electric rule detection — is a working, runnable script: [`examples/manufacturing_spc.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/manufacturing_spc.py). Run it directly:

```bash
python examples/manufacturing_spc.py
```

It prints every guarantee below, checked against the data it just generated:

```
processes: 5  subgroups: 450  measurements: 2250

  [OK] 'Shaft Diameter': measured Cpk 1.58 vs target 1.67
  [OK] 'Bore Diameter': measured Cpk 1.28 vs target 1.33
  [OK] 'Housing Bolt Torque': measured Cpk 1.41 vs target 1.33
  [OK] 'Valve Seal Thickness': measured Cpk 0.83 vs target 0.85
  [OK] 'Bearing Race Width': measured Cpk 1.30 vs target 1.33
  [OK] Cp >= Cpk on every process (the Cp/Cpk identity)
  [OK] 'Housing Bolt Torque' is off-center: Cp 1.94 > Cpk 1.41
  [OK] 'Valve Seal Thickness' measures Cpk 0.83, below the 1.33 capability minimum
  [OK] UCL_xbar reconciles to grand_mean + A2 x Rbar on every process
  [OK] every subgroup's xbar equals the mean of its own 5 measurements
  [OK] every subgroup's r equals the range of its own 5 measurements
  [OK] 'Shaft Diameter' (stable) trips a Western Electric rule on only 1.1% of subgroups
  [OK] 'Bore Diameter' (stable) trips a Western Electric rule on only 0.0% of subgroups
  [OK] 'Housing Bolt Torque' (stable) trips a Western Electric rule on only 3.3% of subgroups
  [OK] 'Valve Seal Thickness' (stable) trips a Western Electric rule on only 1.1% of subgroups
  [OK] 'Bearing Race Width' (tool-wear drift): 100% of its final subgroups trip a rule vs 0% before the drift started
  [OK] every subgroup has exactly 5 measurements
  [OK] subgroups.process_id has zero orphans against processes
  [OK] measurements.subgroup_id has zero orphans against subgroups
  [OK] every process has USL strictly greater than LSL

ALL CHECKS PASSED
```

## What each number is grounded in

**Process capability.** `Cp = (USL - LSL) / (6 x sigma)`, `Cpk = Cp x (1 - k)`, where k is how far off-center the process mean sits as a fraction of the tolerance band's half-width (Montgomery, *Introduction to Statistical Quality Control*). Cpk ≤ Cp always, with equality only when the process is perfectly centered — this example builds one process off-center on purpose, so that distinction (Cp 1.94 vs Cpk 1.41 for Housing Bolt Torque) is a measured fact about the rows, not a claim in a docstring.

**Sigma, estimated the real way.** `sigma_within = Rbar / d2`, from the average subgroup range — not the pooled standard deviation of every raw measurement, which is a different (and less standard) estimator. `d2 = 2.326` for a subgroup of size 5, the standard control-chart-constants table value (ASQ / Montgomery Table VI).

**Control limits.** The standard Xbar-R chart limits: `UCL/LCL = grand_mean ± A2 x Rbar`, `A2 = 0.577` for n = 5. Limits are set during a baseline (Phase I) period — the first 60% of subgroups — and then applied forward (Phase II) to flag out-of-control subgroups, the real two-phase SPC workflow (Montgomery), not limits recomputed from the very data being judged against them.

**Out-of-control detection.** Three of the Western Electric Rules (Western Electric Statistical Quality Control Handbook, 1956): Rule 1 (any point beyond the 3-sigma control limit), Rule 3 (2 of 3 consecutive points beyond 2-sigma, same side), and Rule 4 (8 consecutive points on the same side of the centerline).

**The drift.** One process (Bearing Race Width) is given a genuine, engineered tool-wear drift over its last third of subgroups — the single most common real out-of-control pattern on a shop floor — reaching 3 baseline sigmas of shift by the final subgroup. That's large enough to actually trip Rule 1 and Rule 4 where the drift happens (100% of the final 10% of subgroups) and stay silent everywhere else (0% before the drift starts) — a signature a pair of independently random measurement columns could never produce.

## The processes

| process | characteristic | spec | target Cpk | notes |
| --- | --- | --- | --- | --- |
| Shaft Diameter | outer diameter, mm | 24.95-25.05 | 1.67 | excellent / six-sigma-level, centered |
| Bore Diameter | inner bore diameter, mm | 39.96-40.04 | 1.33 | the AIAG/automotive-industry minimum, centered |
| Housing Bolt Torque | final assembly torque, Nm | 40-50 | 1.33 | off-center on purpose, to show Cp > Cpk |
| Valve Seal Thickness | seal thickness, mm | 1.92-2.08 | 0.85 | a real failing process, below the 1.33 minimum |
| Bearing Race Width | race width, mm | 11.94-12.06 | 1.33 | starts capable, ends with a tool-wear drift |

## Giveaways caught before shipping

Following the same audit that caught unrounded dollar amounts in [credit-risk-portfolio](credit-risk.md): measurement values are rounded to a real instrument's actual resolution (0.001mm for the dimensional processes' digital micrometer readings, 0.1Nm for the torque transducer), not the engine's raw float output. Subgroup timestamps fall on exact shift boundaries (06:00 / 14:00 / 22:00, a real three-shift production pattern), not a random time of day.

## What this is not

This is process-control math for continuous dimensional and torque measurements — it doesn't model attribute/pass-fail SPC (p-charts, c-charts), which need a different statistical basis entirely. Sigma is estimated from a 54-subgroup baseline, a realistic but modest sample; the measured Cpk for any single run carries the sampling noise that sample size implies, which is exactly why the verification checks use a tolerance band rather than requiring an exact match. Spec limits and target Cpk values are declared, realistic-shaped assumptions for five illustrative parts, not measured from a real production line's actual PPAP submission.
