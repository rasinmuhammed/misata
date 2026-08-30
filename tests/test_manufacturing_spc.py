import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))

from manufacturing_spc import PROCESSES, build, verify


def test_full_verify_suite_passes():
    tables = build(seed=51)
    assert verify(tables) is True


def test_cpk_reconciles_to_declared_target_per_process():
    tables = build(seed=52)
    capability = tables["capability_summary"].merge(
        tables["processes"][["process_id", "part_name"]], on="process_id")
    for _, row in capability.iterrows():
        assert abs(row["cpk"] - row["target_cpk"]) < max(0.15, row["target_cpk"] * 0.20)


def test_cp_is_never_less_than_cpk():
    tables = build(seed=53)
    capability = tables["capability_summary"]
    assert (capability["cp"] >= capability["cpk"] - 1e-9).all()


def test_off_center_process_shows_cp_greater_than_cpk():
    tables = build(seed=54)
    capability = tables["capability_summary"].merge(
        tables["processes"][["process_id", "part_name"]], on="process_id")
    row = capability[capability["part_name"] == "Housing Bolt Torque"].iloc[0]
    assert row["cp"] > row["cpk"] + 0.05


def test_failing_process_measures_below_the_capability_minimum():
    tables = build(seed=55)
    capability = tables["capability_summary"].merge(
        tables["processes"][["process_id", "part_name"]], on="process_id")
    row = capability[capability["part_name"] == "Valve Seal Thickness"].iloc[0]
    assert row["cpk"] < 1.20


def test_subgroup_xbar_and_r_reconcile_to_their_own_measurements():
    tables = build(seed=56)
    measurements, subgroups = tables["measurements"], tables["subgroups"]
    check = measurements.groupby("subgroup_id")["value"].agg(["mean", lambda s: s.max() - s.min()])
    check.columns = ["xbar_check", "r_check"]
    merged = subgroups.merge(check, on="subgroup_id")
    assert np.allclose(merged["xbar"], merged["xbar_check"], atol=1e-6)
    assert np.allclose(merged["r"], merged["r_check"], atol=1e-6)


def test_stable_processes_have_a_low_false_alarm_rate():
    tables = build(seed=57)
    subgroups = tables["subgroups"].merge(tables["processes"][["process_id", "part_name"]], on="process_id")
    for name in ["Shaft Diameter", "Bore Diameter", "Housing Bolt Torque", "Valve Seal Thickness"]:
        rate = subgroups[subgroups["part_name"] == name]["out_of_control"].mean()
        assert rate < 0.10


def test_drift_process_trips_rules_concentrated_at_the_end():
    tables = build(seed=58)
    subgroups = tables["subgroups"].merge(tables["processes"][["process_id", "part_name"]], on="process_id")
    drift = subgroups[subgroups["part_name"] == "Bearing Race Width"].sort_values("subgroup_seq")
    n = len(drift)
    early = drift.iloc[:int(n * 0.6)]["out_of_control"].mean()
    late = drift.iloc[int(n * 0.9):]["out_of_control"].mean()
    assert late > 0.5
    assert late > early * 3


def test_every_subgroup_has_exactly_5_measurements():
    tables = build(seed=59)
    counts = tables["measurements"].groupby("subgroup_id").size()
    assert (counts == 5).all()


def test_no_orphan_foreign_keys():
    tables = build(seed=60)
    processes, subgroups, measurements = tables["processes"], tables["subgroups"], tables["measurements"]
    assert subgroups["process_id"].isin(processes["process_id"]).all()
    assert measurements["subgroup_id"].isin(subgroups["subgroup_id"]).all()


def test_all_declared_processes_present_exactly_once():
    tables = build(seed=61)
    names = set(tables["processes"]["part_name"])
    assert names == set(PROCESSES.keys())
    assert tables["processes"]["process_id"].is_unique
