---
title: Generate Insurance Synthetic Data in Python | Misata
description: Generate realistic insurance synthetic datasets in Python — customers, policies, claims, and payments with actuarially accurate premium distributions, claim rates, and temporal coherence. GDPR-safe by design.
---

# Generate Insurance Synthetic Data in Python

Insurance data is among the most sensitive and regulated data in any industry — GDPR, HIPAA, and state insurance regulations govern exactly who can access real policyholder records. Yet developers building insurtech platforms, actuaries prototyping pricing models, and data engineers testing claims pipelines all need realistic insurance data. Misata generates a four-table insurance dataset with lognormally distributed premiums by product line, a realistic ~8% claim rate, and complete temporal coherence: `incident_date` always falls within the policy's active period, `claim_date` follows `incident_date`, and policy `end_date` is always after `start_date`.

```python
import misata

tables = misata.generate("An insurance company with 2k customers, auto and home policies, and claims", rows=2000, seed=42)
print(list(tables.keys()))   # ['customers', 'policies', 'claims', 'payments']
print(tables["claims"].groupby("status")["amount"].describe())
```

## What Misata generates

Four tables: `customers` → `policies` → `claims` and `payments` (both linked to policies). Claim amounts, premium levels, and coverage values are all calibrated to real insurance product lines.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `customers` | `customer_id`, `name`, `email`, `date_of_birth`, `gender`, `state`, `credit_score` |
| `policies` | `policy_id`, `customer_id`, `type`, `premium`, `coverage_amount`, `start_date`, `end_date`, `status` |
| `claims` | `claim_id`, `policy_id`, `incident_date`, `claim_date`, `amount`, `status`, `description` |
| `payments` | `payment_id`, `policy_id`, `amount`, `payment_date`, `method`, `status` |

### Realistic distributions

- **Premiums** lognormal by type: auto ~$1,200/yr, home ~$1,500/yr, life ~$800/yr — with realistic within-line variance
- **Claim rate** ~8% of active policies — matching personal lines industry averages
- **`incident_date`** always falls within the policy's active `start_date` → `end_date` window
- **Coverage amounts** are correlated with premium — higher-coverage policies cost more
- **Credit scores** normally distributed around 690–710 — the realistic consumer credit distribution

## Quick start

```python
import misata
import pandas as pd

tables = misata.generate(
    "Personal lines insurance company with auto, home, and life policies",
    rows=2000,
    seed=42,
)

# Claim rate by policy type
policies = tables["policies"]
claims = tables["claims"]
claim_policies = set(claims["policy_id"])
policies["has_claim"] = policies["policy_id"].isin(claim_policies)
print(policies.groupby("type")["has_claim"].mean())

# Average claim amount by status
print(claims.groupby("status")["amount"].mean())

# Payment method mix
print(tables["payments"]["method"].value_counts(normalize=True))
```

## Common use cases

- **Fraud detection models** — generate labeled claims with realistic amounts, timing, and status patterns to train anomaly classifiers
- **Underwriting algorithm validation** — test pricing models against customers with varied credit scores, ages, and states
- **Policy management system testing** — seed full policy lifecycles — issuance, renewal, lapse, cancellation — with correct date semantics
- **Actuarial analysis prototypes** — build loss ratio, combined ratio, and claims frequency dashboards before connecting to real policy data
- **Billing system QA** — test payment processing, reminder workflows, and lapse detection against payments with varied methods and statuses
- **Regulatory compliance testing** — validate data masking and anonymization pipelines against realistic PII-containing insurance records

## Advanced: catastrophe event claims

```python
tables = misata.generate(
    "Home insurance portfolio with a hurricane claims surge in Q3 — "
    "claim rate spikes to 25% in August-September, average claim amount doubles",
    rows=3000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# US insurance — state distribution, US credit scoring
tables = misata.generate("US personal lines insurance with auto and home policies", rows=2000)

# UK insurance — GBP premiums, UK cities, British names
tables = misata.generate("UK motor and home insurance company with 1k customers", rows=1000)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Insurance company with 2k policyholders",
    min_quality_score=85,
    smart_correlations=True,  # auto-adds credit_score↔premium, coverage↔premium
    rows=2000,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Narrative Patterns](../guides/narrative-patterns.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
