---
title: Generate Healthcare Synthetic Data in Python | Misata
description: Generate realistic healthcare synthetic datasets in Python: patients, doctors, admissions, diagnoses, and lab results, with real ICD-10 codes, reconciled length-of-stay, and zero orphaned foreign keys. No real patient data required.
---

# Generate Healthcare Synthetic Data in Python

Healthcare data is among the most sensitive in existence, HIPAA, GDPR, and a dozen other regulations govern who can access real patient records. Yet developers building EHR systems, researchers training clinical ML models, and teams building healthcare analytics tools all need realistic patient data that behaves like the real thing. Misata generates a fully synthetic hospital dataset: patients with real ABO/Rh blood type frequencies, admissions with a reconciled length of stay, diagnoses drawn from real ICD-10 codes, and lab results checked against real clinical reference ranges.

No real patient records are ever used or exposed. Every name, date of birth, and diagnosis is generated from statistical priors and a real coded vocabulary, realistic enough to power your analytics queries, safe enough to share in any environment.

```python
import misata

schema = {
    "doctors": {
        "__rows__": 50,
        "doctor_id": {"type": "integer", "primary_key": True},
        "specialty": {"type": "string", "enum": ["Internal Medicine", "Cardiology", "Orthopedics"]},
    },
    "patients": {
        "__rows__": 500,
        "patient_id": {"type": "integer", "primary_key": True},
        "blood_type": {"type": "string",
                        "enum": ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"],
                        "weights": [0.374, 0.357, 0.085, 0.034, 0.066, 0.063, 0.015, 0.006]},
    },
    "admissions": {
        "__rows__": 1000,
        "admission_id": {"type": "integer", "primary_key": True},
        "patient_id": {"type": "integer", "foreign_key": {"table": "patients", "column": "patient_id"}},
        "doctor_id": {"type": "integer", "foreign_key": {"table": "doctors", "column": "doctor_id"}},
        "admit_date": {"type": "datetime", "min_date": "2024-01-01", "max_date": "2025-12-01"},
        "length_of_stay_days": {"type": "integer", "min": 1, "max": 21},
    },
}
tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=42))
print(list(tables.keys()))   # ['doctors', 'patients', 'admissions']
```

That is the minimal shape. The full five-table hospital, with diagnoses drawn from real ICD-10 codes and lab results checked against clinical reference ranges, is a working, runnable example: [`examples/healthcare_hospital.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/healthcare_hospital.py) in the repo. Run it directly:

```bash
python examples/healthcare_hospital.py
```

It prints every guarantee below, checked against the data it just generated, not asserted:

```
[OK] admit precedes discharge on every row
[OK] length of stay reconciles on every row
[OK] every diagnosis/icd_code pair is a real, matched pair
[OK] a doctor's total_admissions equals its actual admission row count
[OK] Hemoglobin: result_flag matches the stated reference range
[OK] White Blood Cells: result_flag matches the stated reference range
[OK] Glucose: result_flag matches the stated reference range
...
ALL CHECKS PASSED
```

## What the full example generates

Five tables, referentially intact.

| Table | Key columns |
|:--|:--|
| `doctors` | `doctor_id`, `specialty`, `years_experience`, `total_admissions` |
| `patients` | `patient_id`, `date_of_birth`, `blood_type`, `insurance_provider` |
| `admissions` | `admission_id`, `patient_id`, `doctor_id`, `admit_date`, `discharge_date`, `length_of_stay_days`, `status` |
| `diagnoses` | `diagnosis_row_id`, `admission_id`, `diagnosis_name`, `icd_code`, `is_primary` |
| `lab_tests` | `lab_test_id`, `admission_id`, `test_name`, `unit`, `result_value`, `result_flag` |

### Guarantees

- **Admit date precedes discharge date on every row, length of stay reconciles.** `discharge_date` is derived from `admit_date + length_of_stay_days`, so this holds by construction, not by chance.
- **Diagnoses use real ICD-10 codes, correctly paired with their diagnosis name** — never lorem ipsum, and never a code mismatched to the wrong condition.
- **A doctor's `total_admissions` equals the count of their actual admission rows.** Checked with a `groupby` against the real admissions table after generation, not declared and left unverified.
- **Lab result flags (`low` / `normal` / `high`) match the stated clinical reference range** for that specific test, for every row.
- **Zero orphaned foreign keys** across `admissions`, `diagnoses`, and `lab_tests`.
- **No real patient data is sourced**, so there is no PHI to protect.

## Declaring an exact operational KPI

Most synthetic patient-record generators build bottom-up: draw a plausible patient, walk them through plausible events, and whatever aggregate falls out, falls out. That works until a hospital-analytics demo needs to show something specific, bed-days trending up through a defined quarter for a capacity-planning story. Misata declares the aggregate first and solves the rows to satisfy it exactly, then measures the real result to prove it held:

```python
"__outcome_curves__": [{
    "table": "admissions", "column": "length_of_stay_days", "time_column": "admit_date",
    "time_unit": "month", "pattern_type": "custom", "value_mode": "absolute",
    "start_date": "2025-01-01",
    "curve_points": [
        {"date": "2025-07-01", "value": 432},
        {"date": "2025-08-01", "value": 481},
        {"date": "2025-09-01", "value": 531},   # bed-days peak, exactly, in Q3
    ],
}]
```

Before any row is generated, `misata.conformance.conformance_preview()` checks whether the declared total is even reachable given the row count and the declared bounds, and refuses with a specific, actionable warning if it is not — this caught an unrealistic average-length-of-stay target during the writing of this example, before a single row was generated. See [`examples/healthcare_declared_kpi.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/healthcare_declared_kpi.py) for the full runnable version, which measures the actual monthly bed-days total against the declared figure and prints the match for all twelve months.

## Quick start

```python
import misata

tables = misata.generate("A hospital with 500 patients and 50 doctors", rows=500, seed=42)
print(list(tables.keys()))   # ['doctors', 'patients', 'appointments']
```

This one-line, story-based form is the fastest way to get a plausible hospital dataset for prototyping, and it produces a simpler three-table shape (`doctors`, `patients`, `appointments`) rather than the full admissions/diagnoses/lab_tests structure above. For the complete hospital schema with reconciled length of stay, real ICD-10 codes, and lab reference ranges, use `generate_from_schema` with an explicit schema as shown above, or run `examples/healthcare_hospital.py` directly.
