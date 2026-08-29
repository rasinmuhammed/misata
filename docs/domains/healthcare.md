---
title: Generate Healthcare Synthetic Data in Python | Misata
description: Generate realistic healthcare synthetic datasets in Python: patients, doctors, admissions, diagnoses, and lab results, with real ICD-10 codes, reconciled length-of-stay, comorbidity clusters, severity-driven length of stay, and zero orphaned foreign keys. No real patient data required.
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

## Comorbidity clusters and severity-driven length of stay

The five-table example above draws each admission's diagnoses independently of the others. Real EHR data does not work that way: a patient with chronic kidney disease is far more likely to also carry hypertension and type 2 diabetes than an unrelated diagnosis, because these conditions cluster in real physiology, not by chance. And length of stay is not independent of how sick the admission actually was.

[`examples/healthcare_comorbidity.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/healthcare_comorbidity.py) extends the hospital schema with both, and grounds each number rather than inventing it:

```
patients: 2000  admissions: 4000  diagnoses: 5600

  [OK] comorbidity_cluster 'kidney_metabolic' matches cited prevalence (0.141 vs 0.133)
  [OK] comorbidity_cluster 'diabetes_hypertension' matches cited prevalence (0.173 vs 0.170)
  [OK] comorbidity_cluster 'independent' matches cited prevalence (0.685 vs 0.697)
  [OK] 'kidney_metabolic' patients show their cluster's diagnoses at 0.82 vs a 0.06 random baseline (13.7x)
  [OK] 'diabetes_hypertension' patients show their cluster's diagnoses at 0.80 vs a 0.04 random baseline (20.1x)
  [OK] mean length of stay strictly increases minor -> extreme
  [OK] 'extreme' mean LOS (18.3d) is close to the cited ~17d
  [OK] admit precedes discharge on every row
  [OK] length of stay reconciles on every row

ALL CHECKS PASSED
```

**Comorbidity clusters.** Each patient is assigned one of three clusters at creation: `kidney_metabolic` (CKD + hypertension + type 2 diabetes, 13.3% prevalence, cited from a 163,626-patient elderly inpatient cohort, Xu et al. 2026), `diabetes_hypertension` (diabetes and hypertension co-occurring without CKD, 17% prevalence among community-dwelling older adults, Pham et al., PubMed 30094913), or `independent` (the remainder). These are two separate studies of overlapping but distinct populations, applied here as non-overlapping synthetic categories for construction — a modeling simplification stated plainly rather than left implicit.

The connection this produces: a patient's own cluster measurably predicts what shows up in their diagnoses. A `kidney_metabolic` patient's admissions show a diagnosis from {CKD, hypertension, type 2 diabetes} at roughly 80% of rows, against a ~6% baseline if diagnoses were drawn independently of the patient — an 13x concentration, checked against the actual generated data, not declared. A patient in neither cluster shows no such concentration, confirming the effect comes from the cluster assignment and not an artifact of the vocabulary.

**Severity-driven length of stay.** Every admission gets one of the four real APR-DRG (All Patient Refined Diagnosis Related Groups) severity-of-illness tiers: minor, moderate, major, extreme. Only one tier has a specific cited figure: patients at APR severity level 4 ("extreme") have a mean length of stay of almost 17 days. The other three tiers are a designed, monotonically increasing progression anchored at that one real number (minor≈2.5d, moderate≈5d, major≈9d, extreme≈17d), not independently cited each — the same honesty split used for the bearing damage trajectory in the [predictive maintenance capability](predictive-maintenance.md), where the geometry is textbook and the growth curve is declared.

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
