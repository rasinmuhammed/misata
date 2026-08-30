"""
Manufacturing process-control data: processes, subgroups, and individual
measurements, generated the way a real Xbar-R control chart actually works
-- not a column of random floats with a "Cpk" number written in the README.

Every number below traces to a named, standard formula:

  * Process capability: Cp = (USL - LSL) / (6 x sigma), Cpk = Cp x (1 - k),
    where k is how far the process mean sits off-center as a fraction of
    the tolerance band's half-width (Montgomery, "Introduction to
    Statistical Quality Control"). Cpk <= Cp always, with equality only
    when the process is perfectly centered -- this example generates one
    process off-center on purpose so that distinction is a measured fact
    about the data, not a claim in a docstring.

  * sigma is estimated the way a real Xbar-R chart estimates it: from the
    average subgroup range, sigma_within = Rbar / d2, not the pooled
    standard deviation of every raw measurement. d2 = 2.326 for a subgroup
    of size 5, from the standard control-chart-constants table (ASQ /
    Montgomery Table VI).

  * Control limits are the standard Xbar-R chart limits:
    UCL/LCL = grand_mean +/- A2 x Rbar, A2 = 0.577 for n = 5 (the same
    constants table). Limits are set during a baseline (Phase I) period
    and then applied forward (Phase II) to flag out-of-control subgroups
    -- the real two-phase SPC workflow, not limits recomputed from the
    very data being judged against them.

  * Out-of-control detection uses three of the Western Electric Rules
    (Western Electric Statistical Quality Control Handbook, 1956):
      Rule 1: any single point beyond the 3-sigma control limit.
      Rule 3: 2 of 3 consecutive points beyond 2-sigma, same side.
      Rule 4: 8 consecutive points on the same side of the centerline.

One process is given a genuine, engineered tool-wear drift over its last
third of subgroups -- the single most common real out-of-control pattern
on a shop floor -- specifically so that Rule 1 and Rule 4 actually fire
where the drift happens and stay silent everywhere else, a real signature
a pair of independently random measurement columns could never produce.
"""

import numpy as np
import pandas as pd

import misata

RNG_SEED = 19
SUBGROUP_SIZE = 5          # the standard Xbar-R subgroup size
N_SUBGROUPS = 90           # 30 days x 3 shifts
BASELINE_FRACTION = 0.6    # Phase I: the first 60% of subgroups set the limits

# Control-chart constants for subgroup size n=5 (ASQ / Montgomery Table VI).
A2 = 0.577
D3 = 0.0
D4 = 2.114
D2_CONST = 2.326

# Five real-sounding processes, each with a genuine spec (tolerance band)
# and a declared target Cpk that spans the range an actual plant audit
# would find: excellent, industry-minimum, off-center-but-nominally-okay,
# and outright failing.
PROCESSES = {
    "Shaft Diameter":        {"characteristic": "outer diameter", "unit": "mm", "lsl": 24.95, "usl": 25.05, "target_cpk": 1.67, "k": 0.00, "drift": False},
    "Bore Diameter":         {"characteristic": "inner bore diameter", "unit": "mm", "lsl": 39.96, "usl": 40.04, "target_cpk": 1.33, "k": 0.00, "drift": False},
    "Housing Bolt Torque":   {"characteristic": "final assembly torque", "unit": "Nm", "lsl": 40.0, "usl": 50.0, "target_cpk": 1.33, "k": 0.30, "drift": False},
    "Valve Seal Thickness":  {"characteristic": "seal thickness", "unit": "mm", "lsl": 1.92, "usl": 2.08, "target_cpk": 0.85, "k": 0.00, "drift": False},
    "Bearing Race Width":    {"characteristic": "race width", "unit": "mm", "lsl": 11.94, "usl": 12.06, "target_cpk": 1.33, "k": 0.00, "drift": True},
}

# The tool-wear drift: over the last third of subgroups, the mean walks
# steadily toward USL, reaching this many baseline sigmas of shift by the
# final subgroup -- large enough to actually trip Western Electric rules,
# the entire point of including it.
DRIFT_FINAL_SIGMA_SHIFT = 3.0
DRIFT_START_FRACTION = 0.67


def _measurement_decimals(unit: str) -> int:
    # A digital micrometer reads to 0.001 mm; a torque transducer to 0.1 Nm.
    # Left at the engine's raw float output, this is exactly the kind of
    # giveaway the credit-risk-portfolio example's unrounded dollar amounts
    # were.
    return 3 if unit == "mm" else 1


def build(seed: int = RNG_SEED):
    schema = {
        "processes": {
            "__rows__": len(PROCESSES),
            "process_id": {"type": "integer", "primary_key": True},
        },
        "subgroups": {
            "__rows__": len(PROCESSES) * N_SUBGROUPS,
            "subgroup_id": {"type": "integer", "primary_key": True},
            "process_id": {"type": "integer", "foreign_key": {"table": "processes", "column": "process_id"}},
        },
        "measurements": {
            "__rows__": len(PROCESSES) * N_SUBGROUPS * SUBGROUP_SIZE,
            "measurement_id": {"type": "integer", "primary_key": True},
            "subgroup_id": {"type": "integer", "foreign_key": {"table": "subgroups", "column": "subgroup_id"}},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))
    return _reconcile(tables, seed)


def _reconcile(tables: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed + 1)

    processes = tables["processes"].copy()
    proc_ids = processes["process_id"].sort_values().to_numpy()
    names = list(PROCESSES.keys())
    processes = processes.set_index("process_id").loc[proc_ids].reset_index()
    processes["part_name"] = names
    for field in ("characteristic", "unit", "lsl", "usl", "target_cpk"):
        processes[field] = [PROCESSES[n][field] for n in names]
    processes = processes[["process_id", "part_name", "characteristic", "unit", "lsl", "usl", "target_cpk"]]
    tables["processes"] = processes

    # Rebuild subgroups and measurements directly: a clean, ordered
    # cross-product of (process x subgroup_seq x sample_index) with real
    # shift timestamps, rather than misata's per-row random FK assignment,
    # which can't express "exactly 90 ordered subgroups per process."
    shift_times = pd.date_range("2026-05-01 06:00:00", periods=N_SUBGROUPS, freq="8h")

    subgroup_rows = []
    measurement_rows = []
    subgroup_id = 1
    measurement_id = 1

    for _, proc in processes.iterrows():
        name = proc["part_name"]
        spec = PROCESSES[name]
        lsl, usl, target_cpk, k = spec["lsl"], spec["usl"], spec["target_cpk"], spec["k"]
        nominal = (usl + lsl) / 2
        tol_half_width = (usl - lsl) / 2

        cp = target_cpk / (1 - k)
        sigma = (usl - lsl) / (6 * cp)
        base_mean = nominal + k * tol_half_width

        decimals = _measurement_decimals(spec["unit"])
        drift_start = int(N_SUBGROUPS * DRIFT_START_FRACTION)

        for seq in range(N_SUBGROUPS):
            mean_here = base_mean
            if spec["drift"] and seq >= drift_start:
                progress = (seq - drift_start) / (N_SUBGROUPS - 1 - drift_start)
                mean_here = base_mean + progress * DRIFT_FINAL_SIGMA_SHIFT * sigma

            values = rng.normal(mean_here, sigma, size=SUBGROUP_SIZE).round(decimals)
            ts = shift_times[seq]

            subgroup_rows.append({
                "subgroup_id": subgroup_id, "process_id": proc["process_id"],
                "subgroup_seq": seq + 1, "timestamp": ts,
                "xbar": round(float(values.mean()), decimals + 1),
                "r": round(float(values.max() - values.min()), decimals + 1),
            })
            for sample_index, v in enumerate(values, start=1):
                measurement_rows.append({
                    "measurement_id": measurement_id, "subgroup_id": subgroup_id,
                    "process_id": proc["process_id"], "sample_index": sample_index,
                    "value": float(v),
                })
                measurement_id += 1
            subgroup_id += 1

    subgroups = pd.DataFrame(subgroup_rows)
    measurements = pd.DataFrame(measurement_rows)

    # Phase I / Phase II: control limits are set from a baseline period,
    # then applied to the whole run -- not recomputed from data that
    # includes the very drift they're supposed to catch.
    capability_rows = []
    rule1 = np.zeros(len(subgroups), dtype=bool)
    rule3 = np.zeros(len(subgroups), dtype=bool)
    rule4 = np.zeros(len(subgroups), dtype=bool)

    for _, proc in processes.iterrows():
        pid = proc["process_id"]
        mask = subgroups["process_id"] == pid
        idx = subgroups.index[mask]
        g = subgroups.loc[idx].sort_values("subgroup_seq")
        n_baseline = int(len(g) * BASELINE_FRACTION)
        baseline = g.iloc[:n_baseline]

        grand_mean = baseline["xbar"].mean()
        rbar = baseline["r"].mean()
        sigma_within = rbar / D2_CONST
        sigma_xbar = A2 * rbar / 3
        ucl = grand_mean + A2 * rbar
        lcl = grand_mean - A2 * rbar

        lsl, usl, target_cpk = proc["lsl"], proc["usl"], proc["target_cpk"]
        cp_measured = (usl - lsl) / (6 * sigma_within)
        k_measured = abs(grand_mean - (usl + lsl) / 2) / ((usl - lsl) / 2)
        cpk_measured = cp_measured * (1 - k_measured)

        capability_rows.append({
            "process_id": pid, "n_subgroups_baseline": n_baseline,
            "grand_mean": round(float(grand_mean), 4), "rbar": round(float(rbar), 4),
            "sigma_within": round(float(sigma_within), 5),
            "ucl_xbar": round(float(ucl), 4), "lcl_xbar": round(float(lcl), 4),
            "cp": round(float(cp_measured), 3), "cpk": round(float(cpk_measured), 3),
            "target_cpk": target_cpk,
        })

        xbar_vals = g["xbar"].to_numpy()
        z = (xbar_vals - grand_mean) / sigma_xbar  # standardized position, in sigma_xbar units

        r1 = np.abs(z) > 3
        r3 = np.zeros(len(z), dtype=bool)
        for i in range(2, len(z)):
            window = z[i - 2:i + 1]
            r3[i] = (np.sum(window > 2) >= 2) or (np.sum(window < -2) >= 2)
        r4 = np.zeros(len(z), dtype=bool)
        for i in range(7, len(z)):
            window = z[i - 7:i + 1]
            r4[i] = np.all(window > 0) or np.all(window < 0)

        order = g.index.to_numpy()
        rule1[order] = r1
        rule3[order] = r3
        rule4[order] = r4

    subgroups["rule1_beyond_3sigma"] = rule1
    subgroups["rule3_2of3_beyond_2sigma"] = rule3
    subgroups["rule4_8_consecutive_same_side"] = rule4
    subgroups["out_of_control"] = rule1 | rule3 | rule4

    capability = pd.DataFrame(capability_rows)

    tables["processes"] = processes
    tables["subgroups"] = subgroups
    tables["measurements"] = measurements
    tables["capability_summary"] = capability
    return tables


def verify(tables: dict) -> bool:
    processes = tables["processes"]
    subgroups = tables["subgroups"]
    measurements = tables["measurements"]
    capability = tables["capability_summary"].merge(
        processes[["process_id", "part_name"]], on="process_id")

    checks = []

    # 1. Measured Cpk (from the baseline Xbar-R chart's own Rbar/d2
    # sigma estimate) reconciles to the declared target, within the
    # sampling tolerance a real baseline period of this size carries.
    for _, row in capability.iterrows():
        declared = row["target_cpk"]
        measured = row["cpk"]
        ok = abs(measured - declared) < max(0.15, declared * 0.20)
        checks.append((f"'{row['part_name']}': measured Cpk {measured:.2f} vs target {declared:.2f}", ok))

    # 2. Cp >= Cpk always, mathematical identity from the Cp/Cpk relation
    # -- and strictly greater for the one process built off-center.
    checks.append(("Cp >= Cpk on every process (the Cp/Cpk identity)",
                    (capability["cp"] >= capability["cpk"] - 1e-9).all()))
    off_center = capability[capability["part_name"] == "Housing Bolt Torque"].iloc[0]
    checks.append((f"'Housing Bolt Torque' is off-center: Cp {off_center['cp']:.2f} > Cpk {off_center['cpk']:.2f}",
                    off_center["cp"] > off_center["cpk"] + 0.05))

    # 3. The declared "not capable" process really does measure below the
    # AIAG/automotive-industry 1.33 minimum -- a real failing example, not
    # smoothed into passing.
    failing = capability[capability["part_name"] == "Valve Seal Thickness"].iloc[0]
    checks.append((f"'Valve Seal Thickness' measures Cpk {failing['cpk']:.2f}, below the 1.33 capability minimum",
                    failing["cpk"] < 1.20))

    # 4. Control limits recompute exactly from the baseline grand mean and
    # Rbar via the A2 constant, on every process.
    recomputed_ucl = capability["grand_mean"] + A2 * capability["rbar"]
    checks.append(("UCL_xbar reconciles to grand_mean + A2 x Rbar on every process",
                    np.allclose(capability["ucl_xbar"], recomputed_ucl, atol=1e-3)))

    # 5. Every subgroup's xbar and r reconcile to its own 5 raw measurements.
    check_group = measurements.groupby("subgroup_id")["value"].agg(["mean", lambda s: s.max() - s.min()])
    check_group.columns = ["xbar_check", "r_check"]
    merged = subgroups.merge(check_group, on="subgroup_id")
    checks.append(("every subgroup's xbar equals the mean of its own 5 measurements",
                    np.allclose(merged["xbar"], merged["xbar_check"], atol=1e-6)))
    checks.append(("every subgroup's r equals the range of its own 5 measurements",
                    np.allclose(merged["r"], merged["r_check"], atol=1e-6)))

    # 6. Stable processes barely ever trip a rule (low false-alarm rate);
    # the drift process trips one heavily in its final third and almost
    # never before it -- the actual signature Western Electric rules exist
    # to catch, measured directly rather than asserted.
    for name in ["Shaft Diameter", "Bore Diameter", "Housing Bolt Torque", "Valve Seal Thickness"]:
        g = subgroups.merge(processes[["process_id", "part_name"]], on="process_id")
        g = g[g["part_name"] == name]
        rate = g["out_of_control"].mean()
        checks.append((f"'{name}' (stable) trips a Western Electric rule on only {rate:.1%} of subgroups",
                        rate < 0.10))

    drift = subgroups.merge(processes[["process_id", "part_name"]], on="process_id")
    drift = drift[drift["part_name"] == "Bearing Race Width"].sort_values("subgroup_seq")
    n = len(drift)
    early = drift.iloc[:int(n * 0.6)]["out_of_control"].mean()
    late = drift.iloc[int(n * 0.9):]["out_of_control"].mean()
    checks.append((f"'Bearing Race Width' (tool-wear drift): {late:.0%} of its final subgroups trip a rule "
                    f"vs {early:.0%} before the drift started",
                    late > 0.5 and late > early * 3))

    # 7. Structural guarantees.
    checks.append(("every subgroup has exactly 5 measurements",
                    (measurements.groupby("subgroup_id").size() == SUBGROUP_SIZE).all()))
    checks.append(("subgroups.process_id has zero orphans against processes",
                    subgroups["process_id"].isin(processes["process_id"]).all()))
    checks.append(("measurements.subgroup_id has zero orphans against subgroups",
                    measurements["subgroup_id"].isin(subgroups["subgroup_id"]).all()))
    checks.append(("every process has USL strictly greater than LSL",
                    (processes["usl"] > processes["lsl"]).all()))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)
    return all_ok


if __name__ == "__main__":
    tables = build(seed=RNG_SEED)
    print(f"processes: {len(tables['processes'])}  subgroups: {len(tables['subgroups'])}  "
          f"measurements: {len(tables['measurements'])}")
    print()
    ok = verify(tables)
    print()
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    raise SystemExit(0 if ok else 1)
