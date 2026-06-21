---
title: Generate HR & Workforce Synthetic Data in Python | Misata
description: Generate realistic HR synthetic datasets in Python, employees, departments, payroll, salary distributions, and tenure coherence. No real employee data required. GDPR-safe by design.
---

# Generate HR and Workforce Synthetic Data in Python

HR data is deeply sensitive, employee salaries, personal dates of birth, and compensation details are among the most protected data in any organisation. But HR analytics tools, payroll system integrations, workforce planning models, and people analytics dashboards all need realistic employee data to develop against. Misata generates a coherent HR synthetic dataset: departments with realistic headcounts, employees with age-and-seniority-appropriate salaries, and payroll records where `net_pay` is mathematically consistent with `gross_pay` and `tax_withheld`.

The temporal coherence rules are the key differentiator: every employee's `hire_date` is after their `date_of_birth + 18 years`, never in the future, and `tenure_years` is derived directly from `hire_date`, not from a separate random distribution that could produce impossible values like negative tenure.

```python
import misata

tables = misata.generate("A tech company with 1000 employees and 4 departments", rows=1000, seed=42)
print(list(tables.keys()))   # ['departments', 'employees', 'payroll']
print(tables["employees"][["role", "seniority", "salary", "tenure_years"]].describe())
```

## What Misata generates

Three tables: `departments` → `employees` → `payroll`. Every employee belongs to a department; every payroll record belongs to an employee. Salary, tenure, and seniority are logically consistent across the entire dataset.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `departments` | `department_id`, `name`, `head_count`, `budget`, `location` |
| `employees` | `employee_id`, `department_id`, `name`, `email`, `role`, `seniority`, `hire_date`, `date_of_birth`, `salary`, `tenure_years` |
| `payroll` | `payroll_id`, `employee_id`, `period_start`, `gross_pay`, `tax_withheld`, `net_pay`, `pay_type` |

### Realistic distributions

- **Salary by seniority:** junior ~$65k, mid ~$95k, senior ~$140k, lead ~$180k, lognormal within each band for realistic spread
- **Tax rate:** Beta(3, 7) clipped to 18–40%, not uniform, not a fixed percentage
- **`tenure_years`** is derived from `hire_date`, not random, no employee has negative or impossible tenure
- **Age coherence:** hire_date is always ≥18 years after date_of_birth, and never in the future
- **`net_pay`** = `gross_pay × (1 − tax_withheld)`, mathematically enforced on every row

## Quick start

```python
import misata

tables = misata.generate(
    "A tech company with 1000 employees, monthly payroll, engineering and sales departments",
    rows=1000,
    seed=42,
)

# Verify age coherence — no employees hired before age 18
import pandas as pd
employees = tables["employees"].copy()
employees["hire_date"] = pd.to_datetime(employees["hire_date"])
employees["date_of_birth"] = pd.to_datetime(employees["date_of_birth"])
employees["age_at_hire"] = (employees["hire_date"] - employees["date_of_birth"]).dt.days / 365
assert (employees["age_at_hire"] >= 18).all()

# Salary distribution by seniority
print(employees.groupby("seniority")["salary"].describe())
```

## Common use cases

- **People analytics platform development**: build attrition dashboards, salary band analyses, and diversity reports on realistic employee data before your HRIS is connected
- **Payroll system integration testing**: validate your payroll calculation engine against thousands of employees with varied tax rates and pay types
- **GDPR-safe HR reporting**: replace real employee exports with synthetic equivalents for vendor demos and external audits
- **Workforce planning model training**: generate historical headcount and attrition data across departments to train staffing prediction models
- **Compensation benchmarking tools**: build salary comparison features against synthetic market data without licensing real salary surveys
- **Applicant tracking system (ATS) load testing**: generate realistic employee databases with department hierarchies for performance testing

## Advanced: headcount growth curves

Model headcount evolution over time, hiring sprees, layoffs, and department restructuring:

```python
tables = misata.generate(
    "Tech company with 1000 employees — engineering headcount doubled in 2022, "
    "layoffs in Q1 2023, rehiring from Q3 2023",
    rows=1000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# Indian IT company — Indian names, INR salaries, PAN/Aadhaar references
tables = misata.generate("Indian IT services company with 500 employees", rows=500)

# German company — German names, EUR salaries, German tax brackets
tables = misata.generate("German manufacturing company with 800 employees, EUR payroll", rows=800)

# UK workforce — GBP salaries, PAYE tax structure
tables = misata.generate("UK technology company with 300 employees, GBP payroll", rows=300)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Tech company with 1000 employees",
    min_quality_score=85,
    smart_correlations=True,  # auto-adds tenure↔salary, experience↔compensation
    rows=1000,
    seed=42,
)
```

## Formula consistency

Payroll records use formula columns, `net_pay` is not independently sampled but derived:

```python
# Every row satisfies: net_pay = gross_pay * (1 - tax_withheld)
payroll = tables["payroll"]
calculated = payroll["gross_pay"] * (1 - payroll["tax_withheld"])
assert (abs(payroll["net_pay"] - calculated) < 0.01).all()
```

## Related guides

- [Column Correlations](../guides/correlations.md)
- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Localisation](../localisation.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
