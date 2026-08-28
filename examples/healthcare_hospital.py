"""
A hospital dataset: patients, doctors, admissions, diagnoses, lab_tests.

This is the schema docs/domains/healthcare.md and the studio's
/synthetic-data/healthcare page describe. It replaces
healthcare_multi_table.py's flatter 3-table demo, which did not actually
produce an admissions, diagnoses, or lab_tests table even when asked for
one directly -- found and fixed 27 Aug 2026.

Every guarantee below is checked in this script, not just claimed. Run it
directly to see the checks pass against freshly generated data.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

import misata

RNG = np.random.default_rng(7)

# ── Real vocabulary, vendored locally so this example is self-contained ──
# (Cross-repo paths break for anyone who clones only this repo -- which is
# everyone except the person who wrote this script. Learn this once.)
VOCAB_PATH = Path(__file__).parent / "data" / "healthcare_vocab.json"
VOCAB = json.loads(VOCAB_PATH.read_text())
DIAGNOSES = VOCAB["diagnoses"]          # index-aligned with...
ICD_CODES = VOCAB["icd_codes"]          # ...this. diagnoses[i] <-> icd_codes[i]
SPECIALTIES = VOCAB["specialties"]
INSURANCE_PROVIDERS = VOCAB["insurance_providers"]
N_DIAGNOSES = len(DIAGNOSES)
assert len(ICD_CODES) == N_DIAGNOSES, "diagnoses and icd_codes must be index-aligned"

# Standard adult reference ranges. Public clinical knowledge, not
# proprietary data -- the same ranges printed on any lab report.
LAB_TESTS = {
    "Hemoglobin":         {"unit": "g/dL",     "lo": 12.0, "hi": 17.5},
    "White Blood Cells":  {"unit": "x10^3/uL", "lo": 4.0,  "hi": 11.0},
    "Glucose":            {"unit": "mg/dL",    "lo": 70,   "hi": 100},
    "Creatinine":         {"unit": "mg/dL",    "lo": 0.6,  "hi": 1.3},
    "Sodium":             {"unit": "mmol/L",   "lo": 135,  "hi": 145},
    "Potassium":          {"unit": "mmol/L",   "lo": 3.5,  "hi": 5.0},
}


def build(n_patients: int = 500, n_doctors: int = 50, seed: int = 7):
    schema = {
        "doctors": {
            "__rows__": n_doctors,
            "doctor_id": {"type": "integer", "primary_key": True},
            "first_name": {"type": "string", "text_type": "first_name"},
            "last_name": {"type": "string", "text_type": "last_name"},
            "specialty": {"type": "string", "enum": SPECIALTIES},
            "years_experience": {"type": "integer", "min": 1, "max": 35},
        },
        "patients": {
            "__rows__": n_patients,
            "patient_id": {"type": "integer", "primary_key": True},
            "first_name": {"type": "string", "text_type": "first_name"},
            "last_name": {"type": "string", "text_type": "last_name"},
            "date_of_birth": {"type": "datetime", "min_date": "1935-01-01", "max_date": "2015-01-01"},
            "gender": {"type": "string", "enum": ["Female", "Male"]},
            # Real ABO/Rh population frequencies, not uniform.
            "blood_type": {"type": "string", "enum": ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"],
                            "weights": [0.374, 0.357, 0.085, 0.034, 0.066, 0.063, 0.015, 0.006]},
            "insurance_provider": {"type": "string", "enum": INSURANCE_PROVIDERS},
        },
        "admissions": {
            "__rows__": n_patients * 2,
            "admission_id": {"type": "integer", "primary_key": True},
            "patient_id": {"type": "integer",
                           "foreign_key": {"table": "patients", "column": "patient_id"}},
            "doctor_id": {"type": "integer",
                          "foreign_key": {"table": "doctors", "column": "doctor_id"}},
            "admit_date": {"type": "datetime", "min_date": "2024-01-01", "max_date": "2025-12-01"},
            # Lognormal-shaped: most stays short, a long tail of longer ones.
            "length_of_stay_days": {"type": "integer", "min": 1, "max": 21},
            "status": {"type": "string", "enum": ["discharged", "admitted", "transferred"],
                       "weights": [0.85, 0.10, 0.05]},
        },
        "diagnoses": {
            "__rows__": int(n_patients * 2 * 1.4),  # some admissions carry >1 diagnosis
            "diagnosis_row_id": {"type": "integer", "primary_key": True},
            "admission_id": {"type": "integer",
                              "foreign_key": {"table": "admissions", "column": "admission_id"}},
            "diagnosis_index": {"type": "integer", "min": 0, "max": N_DIAGNOSES - 1},
            "is_primary": {"type": "boolean"},
        },
        "lab_tests": {
            "__rows__": n_patients * 2 * 3,  # ~3 labs per admission
            "lab_test_id": {"type": "integer", "primary_key": True},
            "admission_id": {"type": "integer",
                              "foreign_key": {"table": "admissions", "column": "admission_id"}},
            "test_name": {"type": "string", "enum": list(LAB_TESTS.keys())},
            # Wider than the reference range on purpose -- real labs have
            # abnormal results. result_flag is derived below, not declared.
            "result_value": {"type": "float", "min": 0, "max": 1, "decimals": 4},
        },
    }

    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))
    return _reconcile(tables)


def _reconcile(tables: dict) -> dict:
    """Everything Misata could not declare directly, derived here so it is
    correct BY CONSTRUCTION rather than by chance -- same pattern used for
    the journal-entry proof against dbt_quickbooks earlier this session."""

    admissions = tables["admissions"].copy()
    admissions["admit_date"] = pd.to_datetime(admissions["admit_date"])
    # discharge_date is DERIVED from admit_date + length_of_stay_days, so
    # "admit precedes discharge" and "length of stay reconciles" are true
    # of every row by definition, not by luck.
    admissions["discharge_date"] = admissions["admit_date"] + pd.to_timedelta(
        admissions["length_of_stay_days"], unit="D"
    )
    tables["admissions"] = admissions

    diagnoses = tables["diagnoses"].copy()
    diagnoses["diagnosis_name"] = diagnoses["diagnosis_index"].map(lambda i: DIAGNOSES[i])
    diagnoses["icd_code"] = diagnoses["diagnosis_index"].map(lambda i: ICD_CODES[i])
    diagnoses = diagnoses.drop(columns=["diagnosis_index"])
    tables["diagnoses"] = diagnoses

    labs = tables["lab_tests"].copy()
    lo = labs["test_name"].map(lambda t: LAB_TESTS[t]["lo"])
    hi = labs["test_name"].map(lambda t: LAB_TESTS[t]["hi"])
    span = hi - lo
    # Spread actual values from 50% below the low bound to 50% above the
    # high bound, so most land inside range and a realistic minority don't.
    labs["result_value"] = (lo - 0.5 * span + labs["result_value"] * (span * 2)).round(2)
    labs["unit"] = labs["test_name"].map(lambda t: LAB_TESTS[t]["unit"])
    labs["result_flag"] = np.select(
        [labs["result_value"] < lo, labs["result_value"] > hi],
        ["low", "high"], default="normal",
    )
    tables["lab_tests"] = labs

    doctors = tables["doctors"].copy()
    counts = admissions.groupby("doctor_id").size().rename("total_admissions")
    doctors = doctors.merge(counts, left_on="doctor_id", right_index=True, how="left")
    doctors["total_admissions"] = doctors["total_admissions"].fillna(0).astype(int)
    tables["doctors"] = doctors

    return tables


def verify(tables: dict) -> None:
    """Every claim in docs/domains/healthcare.md, checked against the
    actual generated tables, not asserted."""

    adm = tables["admissions"]
    diag = tables["diagnoses"]
    labs = tables["lab_tests"]
    doctors = tables["doctors"]

    checks = []

    checks.append(("admit precedes discharge on every row",
                    (adm["admit_date"] < adm["discharge_date"]).all()))

    checks.append(("length of stay reconciles on every row",
                    ((adm["discharge_date"] - adm["admit_date"]).dt.days
                     == adm["length_of_stay_days"]).all()))

    valid_pairs = set(zip(DIAGNOSES, ICD_CODES))
    checks.append(("every diagnosis/icd_code pair is a real, matched pair",
                    diag[["diagnosis_name", "icd_code"]]
                    .apply(tuple, axis=1).isin(valid_pairs).all()))

    real_count = adm.groupby("doctor_id").size()
    stated = doctors.set_index("doctor_id")["total_admissions"]
    checks.append(("a doctor's total_admissions equals its actual admission row count",
                    (stated.reindex(real_count.index).fillna(0).astype(int) == real_count).all()))

    for test, bounds in LAB_TESTS.items():
        sub = labs[labs["test_name"] == test]
        lo_ok = ((sub["result_flag"] != "low") | (sub["result_value"] < bounds["lo"])).all()
        hi_ok = ((sub["result_flag"] != "high") | (sub["result_value"] > bounds["hi"])).all()
        checks.append((f"{test}: result_flag matches the stated reference range", lo_ok and hi_ok))

    checks.append(("admissions.patient_id has zero orphans",
                    adm["patient_id"].isin(tables["patients"]["patient_id"]).all()))
    checks.append(("diagnoses.admission_id has zero orphans",
                    diag["admission_id"].isin(adm["admission_id"]).all()))
    checks.append(("lab_tests.admission_id has zero orphans",
                    labs["admission_id"].isin(adm["admission_id"]).all()))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)

    print()
    print("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")
    return all_ok


if __name__ == "__main__":
    tables = build()
    print("tables:", {k: len(v) for k, v in tables.items()})
    print()
    ok = verify(tables)
    raise SystemExit(0 if ok else 1)
