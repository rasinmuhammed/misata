---
title: Generate SaaS Synthetic Data in Python | Misata
description: Generate realistic SaaS synthetic datasets in Python, users, subscriptions, MRR, churn, and invoices with correct FK relationships and narrative growth curves. No API key required.
---

# Generate SaaS Synthetic Data in Python

Building a SaaS product means working with data that has complex relationships: users who subscribe to plans, subscriptions that churn, invoices tied to billing cycles. When you need realistic test data for your billing engine, BI dashboard, ML churn model, or load tests, generating it by hand wastes hours. Misata generates a production-realistic SaaS dataset, users, subscriptions, and invoices with correct FK wiring, from a single line of Python.

The generated data reflects how real SaaS businesses look: MRR follows a lognormal distribution, churn rates are configurable from the story description, `churned_at` is only populated for churned subscriptions (never for active ones), and plan distributions match typical freemium SaaS splits. You get data that passes `GROUP BY plan` queries without bizarre outliers.

```python
import misata

tables = misata.generate("A SaaS company with 5k users and 20% monthly churn", rows=5000, seed=42)
print(list(tables.keys()))        # ['users', 'subscriptions', 'invoices']
print(tables["users"].head())
print(tables["subscriptions"][["plan", "mrr", "status"]].describe())
```

## What Misata generates

Three tables with full referential integrity: `users` → `subscriptions` → `invoices`. Every subscription references a real user ID; every invoice references a real subscription ID. The churn logic is coherent, `churned_at` timestamps are only set on rows where `status = "churned"`.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `users` | `user_id`, `name`, `email`, `plan`, `signup_date`, `country`, `is_active` |
| `subscriptions` | `subscription_id`, `user_id`, `plan`, `mrr`, `start_date`, `status`, `churned_at` |
| `invoices` | `invoice_id`, `subscription_id`, `amount`, `invoice_date`, `status` |

### Realistic distributions

- **MRR** is lognormal with median ~$150/month, the right shape for a freemium SaaS (long tail of enterprise deals)
- **Plan split:** free 55%, pro 30%, enterprise 15%, configurable by mentioning specific numbers in the story
- **Churn rate** is extracted from the story (`"20% churn"`, `"high churn"`, `"5% monthly churn"`) and applied as a probability
- **`churned_at`** is only non-null for churned subscriptions, guaranteed, not just probable
- **Invoice amounts** match the subscription's MRR with realistic variation for usage-based billing

## Quick start

```python
import misata

# Basic SaaS dataset
tables = misata.generate("A SaaS company with 5k users", rows=5000, seed=42)

# Check coherence: churned_at is null for all active subscriptions
active = tables["subscriptions"][tables["subscriptions"]["status"] == "active"]
assert active["churned_at"].isna().all()

# MRR breakdown by plan
print(tables["subscriptions"].groupby("plan")["mrr"].describe())
```

## Common use cases

- **Seed a billing test database**: get `users`, `subscriptions`, and `invoices` tables pre-joined with realistic MRR values before your billing engine ships
- **Train a churn prediction model**: generate balanced training data with controllable churn rates (e.g. `"40% churn"`) without touching production data
- **BI dashboard development**: build Looker or Metabase dashboards on realistic MRR time series before your product has enough real data
- **Load testing a subscription API**: generate 100k users and subscriptions with valid FK relationships to test pagination and filter endpoints
- **Privacy-safe demos**: replace real customer data in sales demos with statistically identical synthetic data
- **Pytest fixtures**: use `misata.testing.misata_fixture` to get fresh SaaS tables in each test run without database setup

## Advanced: narrative growth curves

The most powerful SaaS feature is outcome curves, you describe a revenue narrative and Misata generates row-level data that rolls up to your specified monthly totals. The `subscriptions.mrr` column supports monthly anchors, quarterly patterns, multipliers, and named events.

```python
tables = misata.generate(
    "SaaS startup — MRR from $50k in January growing to $200k by December, "
    "Q3 slump, strong Q4 push, doubled by year end",
    rows=5000,
    seed=42,
)
# Monthly MRR matches the described narrative
monthly = tables["subscriptions"].groupby(
    tables["subscriptions"]["start_date"].str[:7]
)["mrr"].sum()
print(monthly)
```

## Advanced: locale-aware generation

Misata detects locale from the story and applies the right currency, name format, and regional distributions:

```python
# German SaaS — EUR pricing, German names, DE locale
tables = misata.generate("A German SaaS company with 2000 users, EUR pricing", rows=2000)

# Multi-region — mixed locale names and country distribution
tables = misata.generate("A global SaaS with users across US, UK, India, and Germany", rows=10_000)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "A SaaS company with 5k users",
    min_quality_score=85,   # retries until FidelityChecker score >= 85
    smart_correlations=True, # auto-adds tenure↔MRR correlations
    rows=5000,
    seed=42,
)
```

## Export to database

```python
import misata

tables = misata.generate("A SaaS with 10k users", rows=10_000)

# Seed a PostgreSQL database directly
misata.seed_database(
    tables,
    connection_string="postgresql://user:pass@localhost/testdb",
)

# Or export to Parquet
misata.to_parquet(tables, output_dir="./saas_data/")
```

## Related guides

- [Narrative Patterns](../guides/narrative-patterns.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
- [Column Correlations](../guides/correlations.md)
