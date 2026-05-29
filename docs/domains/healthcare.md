---
title: Generate Healthcare Synthetic Data in Python | Misata
description: Generate realistic healthcare synthetic datasets in Python — patients, doctors, appointments with real blood type frequencies, diagnosis distributions, and HIPAA-safe synthetic PII. No real patient data required.
---

# Generate Healthcare Synthetic Data in Python

Healthcare data is among the most sensitive in existence — HIPAA, GDPR, and a dozen other regulations govern who can access real patient records. Yet developers building EHR systems, researchers training clinical ML models, and teams building healthcare analytics tools all need realistic patient data that behaves like the real thing. Misata generates fully synthetic healthcare data: patients with statistically accurate blood type distributions, doctors with realistic specialty assignments, and appointments with realistic no-show rates and duration distributions.

No real patient records are ever used or exposed. Every name, date of birth, and diagnosis is generated from statistical priors — realistic enough to power your analytics queries, safe enough to share in any environment.

```python
import misata

tables = misata.generate("A hospital with 500 patients and 50 doctors", rows=500, seed=42)
print(list(tables.keys()))   # ['doctors', 'patients', 'appointments']
print(tables["patients"][["blood_type", "diagnosis"]].head())
```

## What Misata generates

Three tables: `doctors`, `patients`, and `appointments`. Appointments reference both a patient and a doctor, enforcing complete referential integrity. Patient demographics match real-world chronic care population distributions.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `doctors` | `doctor_id`, `name`, `specialty`, `department`, `years_experience`, `rating` |
| `patients` | `patient_id`, `name`, `date_of_birth`, `blood_type`, `gender`, `diagnosis`, `insurance_provider` |
| `appointments` | `appointment_id`, `patient_id`, `doctor_id`, `scheduled_at`, `duration_minutes`, `status`, `notes` |

### Realistic distributions

- **Blood types** match real ABO/Rh frequencies: O+ 37.4%, A+ 35.7%, B+ 8.5%, AB+ 3.4%, and negative variants — not uniform random
- **Patient ages** are centered on chronic-care population (μ=52, σ=18) — not uniformly distributed from 0–100
- **No-show rate** is ~15%, matching published hospital no-show statistics
- **Doctor specialties** drawn from realistic distribution: internal medicine, cardiology, orthopedics, general surgery, pediatrics, and more
- **Appointment duration** lognormal with median ~25 minutes — shorter for follow-ups, longer for new patient visits

## Quick start

```python
import misata

tables = misata.generate("A hospital with 500 patients and 50 doctors", rows=500, seed=42)

# Blood type distribution matches real ABO/Rh frequencies
print(tables["patients"]["blood_type"].value_counts(normalize=True).head())
# O+     0.374
# A+     0.357
# B+     0.085
# ...

# Appointment status breakdown
print(tables["appointments"]["status"].value_counts())
# completed    0.72
# no_show      0.15
# cancelled    0.08
# scheduled    0.05
```

## Common use cases

- **EHR system development** — populate a test database with patients, appointments, and doctor schedules before your healthcare app goes live
- **Clinical ML model training** — generate training data for readmission prediction, no-show prediction, or diagnosis classification with realistic demographic distributions
- **Healthcare analytics dashboards** — build utilization reports, specialty throughput charts, and appointment funnel analyses on realistic data
- **HIPAA-compliant data sharing** — replace real patient exports with statistically equivalent synthetic data for vendor integration testing
- **Appointment scheduling algorithm testing** — validate your optimization logic against thousands of appointments across multiple specialties
- **Medical billing integration testing** — generate complete patient-appointment-billing pipelines without exposing real insurance information

## Advanced: patient volume curves

Model seasonal appointment patterns — flu season spikes, elective surgery drops in summer:

```python
tables = misata.generate(
    "Hospital with 2k patients — flu season surge November through February, "
    "elective surgery dip in August, steady growth overall",
    rows=2000,
    seed=42,
)

# Monthly appointment volume follows the seasonal pattern
import pandas as pd
appts = tables["appointments"].copy()
appts["month"] = pd.to_datetime(appts["scheduled_at"]).dt.month
print(appts.groupby("month").size())
```

## Advanced: locale-aware generation

```python
# Indian hospital — Indian names, regional diagnoses, INR billing
tables = misata.generate("Indian multi-specialty hospital with 1k patients", rows=1000)

# German clinic — German names, German insurance providers
tables = misata.generate("German private clinic with 300 patients", rows=300)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Hospital with 1000 patients",
    min_quality_score=85,
    smart_correlations=True,  # auto-correlates age↔diagnosis frequency
    rows=1000,
    seed=42,
)
```

## HIPAA-safe by design

All patient data is generated, never sampled from real records:

- Names are generated from locale-appropriate name distributions
- Dates of birth are statistically derived, not from real people
- Diagnoses are drawn from ICD-10 category distributions, not real patient charts
- Insurance provider names are synthetic

Safe for development, staging, ML training, and vendor demos without a BAA or privacy review.

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Localisation](../localisation.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Anomaly Injection](../guides/anomaly-injection.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
