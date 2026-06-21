---
title: Generate Pharma & Clinical Research Synthetic Data in Python | Misata
description: Generate realistic pharma and clinical research synthetic datasets in Python, researchers, clinical trials, projects, and timesheets with phase-accurate distributions. HIPAA-safe by design. No real trial data required.
---

# Generate Pharma and Clinical Research Synthetic Data in Python

Pharmaceutical and clinical research data is among the most regulated in any industry, FDA 21 CFR Part 11, ICH E6 GCP, and HIPAA govern how trial data is stored, accessed, and shared. Yet research informatics teams, clinical data management (CDM) software developers, and healthcare IT vendors all need realistic trial data to develop against. Misata generates a four-table pharma synthetic dataset: researchers, research projects, clinical trials, and timesheets, with phase-accurate distributions and no real patient or researcher records involved.

```python
import misata

tables = misata.generate("A pharma research company with 200 researchers and clinical trials", rows=200, seed=42)
print(list(tables.keys()))   # ['researchers', 'projects', 'trials', 'timesheets']
print(tables["trials"][["phase", "success_rate", "participants"]].describe())
```

## What Misata generates

Four tables: `researchers` (staff), `projects` (research programs), `trials` (clinical trial records per project), and `timesheets` (researcher time allocation). Every trial references a valid project; every timesheet references a researcher and project.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `researchers` | `researcher_id`, `name`, `email`, `department`, `seniority`, `publications` |
| `projects` | `project_id`, `name`, `status`, `phase`, `budget`, `start_date`, `end_date` |
| `trials` | `trial_id`, `project_id`, `phase`, `participants`, `success_rate`, `duration_weeks` |
| `timesheets` | `timesheet_id`, `researcher_id`, `project_id`, `week_start`, `hours_logged`, `task_type` |

### Realistic distributions

- **Trial phases** follow a realistic R&D pipeline: Phase I (safety) → Phase II (efficacy) → Phase III (large-scale) → Phase IV (post-market)
- **Participant counts** scale with phase, Phase I trials have 20–100 participants, Phase III has 1,000+
- **Success rates** are phase-appropriate: Phase I ~70%, Phase II ~45%, Phase III ~25% (matching industry attrition)
- **Project budgets** lognormal, early-phase projects cost less than late-stage pivotal trials
- **Timesheet hours** are constrained to 0–8 per day, no researcher logs 20 hours in a single day

## Quick start

```python
import misata

tables = misata.generate(
    "A pharma company with 200 researchers, oncology and rare disease projects, Phase I-III trials",
    rows=200,
    seed=42,
)

# Phase distribution
print(tables["trials"]["phase"].value_counts())

# Average participants per phase
print(tables["trials"].groupby("phase")["participants"].mean())

# Researcher time allocation by task type
print(tables["timesheets"].groupby("task_type")["hours_logged"].sum())
```

## Common use cases

- **Electronic lab notebook (ELN) system testing**: seed researcher records, project assignments, and timesheet data for workflow and access control testing
- **Clinical data management (CDM) platform development**: build trial registration, protocol management, and data entry validation on realistic trial records
- **Research resource planning tools**: generate researcher-project allocation data to develop capacity planning and burn rate analytics
- **Regulatory submission data pipeline testing**: validate data transformation and export pipelines against realistic Phase II/III trial structures
- **Grant management system development**: test budget tracking, milestone reporting, and researcher allocation features against synthetic project financials
- **R&D analytics dashboards**: build pipeline stage, success rate, and resource utilization reports before connecting to real CTMS data

## Advanced: R&D pipeline narrative

```python
tables = misata.generate(
    "Pharma company with a major Phase III trial success in Q2 driving new project launches in Q3-Q4",
    rows=300,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# European pharma — EU clinical trial regulations, GDPR-compliant researcher records
tables = misata.generate("European pharma research company with 150 researchers", rows=150)

# US pharma — FDA-track trials, US institutional affiliations
tables = misata.generate("US oncology research company with Phase I-III trials", rows=200)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Pharma company with 200 researchers",
    min_quality_score=85,
    smart_correlations=True,
    rows=200,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Validate](../validate.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
