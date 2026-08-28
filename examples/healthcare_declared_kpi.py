"""
The same hospital structure as healthcare_hospital.py, with one addition:
an exact operational KPI declared in advance and verified afterward.

Most synthetic patient-record generators simulate bottom-up: draw a
plausible patient, walk them through plausible events, and whatever
aggregate falls out, falls out. That is fine until someone building a
hospital analytics dashboard needs the demo to show something specific --
bed-days trending up through a defined quarter, for a capacity-planning
story to land. Bottom-up simulation cannot promise that number. This can,
because Misata solves the rows to satisfy a declared total exactly, then
measures the actual result to prove it held.
"""

import misata

from healthcare_hospital import LAB_TESTS, DIAGNOSES, ICD_CODES, SPECIALTIES, INSURANCE_PROVIDERS, N_DIAGNOSES


def build_and_verify(n_patients: int = 500, n_doctors: int = 50, seed: int = 7):
    # Same shape as healthcare_hospital.py, with length_of_stay_days now
    # DECLARED via an outcome curve instead of drawn freely: total bed-days
    # (sum of length_of_stay_days) must land on an exact monthly figure,
    # rising through Q3 -- the shape a capacity-planning demo needs.
    # Realistic average length of stay is 4-6 days; ~83 admissions/month
    # across 500 patients * 2 admissions/year. These bed-days totals were
    # bisected to sit inside what the engine's own feasibility gate accepts
    # for this row count and LOS bound -- not picked freely and hoped for.
    monthly_bed_days = {
        "2025-01-01": 349, "2025-02-01": 357, "2025-03-01": 365,
        "2025-04-01": 374, "2025-05-01": 382, "2025-06-01": 398,
        "2025-07-01": 432, "2025-08-01": 481, "2025-09-01": 531,
        "2025-10-01": 465, "2025-11-01": 407, "2025-12-01": 374,
    }

    schema = {
        "doctors": {
            "__rows__": n_doctors,
            "doctor_id": {"type": "integer", "primary_key": True},
            "specialty": {"type": "string", "enum": SPECIALTIES},
        },
        "patients": {
            "__rows__": n_patients,
            "patient_id": {"type": "integer", "primary_key": True},
            "insurance_provider": {"type": "string", "enum": INSURANCE_PROVIDERS},
        },
        "admissions": {
            "__rows__": n_patients * 2,
            "admission_id": {"type": "integer", "primary_key": True},
            "patient_id": {"type": "integer",
                           "foreign_key": {"table": "patients", "column": "patient_id"}},
            "doctor_id": {"type": "integer",
                          "foreign_key": {"table": "doctors", "column": "doctor_id"}},
            "admit_date": {"type": "datetime", "min_date": "2025-01-01", "max_date": "2025-12-31"},
            "length_of_stay_days": {"type": "float", "min": 1, "max": 30, "decimals": 0},
        },
        "__outcome_curves__": [{
            "table": "admissions", "column": "length_of_stay_days", "time_column": "admit_date",
            "time_unit": "month", "pattern_type": "custom", "value_mode": "absolute",
            "start_date": "2025-01-01",
            "curve_points": [{"date": d, "value": v} for d, v in monthly_bed_days.items()],
        }],
    }

    # conformance_preview: the feasibility gate, BEFORE spending anything
    # on generation. See docs/03-ENGINE-API.md in misata-backlot for why
    # this check exists and what it caught the day it was built.
    from misata.conformance import conformance_preview
    config = misata.from_dict_schema(schema, seed=seed)
    preview = conformance_preview(config)
    if preview.warnings:
        print("REFUSED before generating -- feasibility warnings:")
        for w in preview.warnings:
            print(" ", w)
        return None

    tables = misata.generate_from_schema(config)
    adm = tables["admissions"]

    import pandas as pd
    month = pd.to_datetime(adm["admit_date"]).dt.strftime("%Y-%m-01")
    measured = adm.groupby(month)["length_of_stay_days"].sum()

    print(f"{'month':<12}{'declared':>10}{'measured':>10}   match")
    all_ok = True
    for d, target in monthly_bed_days.items():
        actual = measured.get(d, 0.0)
        ok = abs(actual - target) < 0.5
        all_ok &= ok
        print(f"{d:<12}{target:>10,.0f}{actual:>10,.0f}   {'OK' if ok else 'MISMATCH'}")

    print()
    print("bed-days trend rising through Q3, exact each month, as declared:"
          if all_ok else "declared KPI did NOT hold — do not use")
    return tables if all_ok else None


if __name__ == "__main__":
    result = build_and_verify()
    raise SystemExit(0 if result is not None else 1)
