---
title: Generate CRM Synthetic Data in Python | Misata
description: Generate realistic CRM synthetic datasets in Python, companies, contacts, deals, and activities with accurate B2B pipeline stage distributions, lognormal deal values, and sales activity mixes. No real customer data required.
---

# Generate CRM Synthetic Data in Python

CRM data is the backbone of every B2B sales tool, but it's also sensitive, and real pipeline data is never available early in development. Misata generates a four-table CRM dataset: companies, contacts, deals, and activities. Deal values are lognormally distributed with a median around $25k (the shape of real B2B pipelines), stage distribution reflects real funnel drop-off, and activity types mirror actual sales rep behavior, 40% email, 30% call, 20% meeting, 10% demo.

Every deal references a valid contact and company. Activities are tied to real deals and contacts. `probability` increases monotonically with stage advancement. `close_date` falls in the future for open-stage deals.

```python
import misata

tables = misata.generate("A B2B SaaS CRM with 500 companies and a full sales pipeline", rows=500, seed=42)
print(list(tables.keys()))   # ['companies', 'contacts', 'deals', 'activities']
print(tables["deals"].groupby("stage")["value"].describe())
```

## What Misata generates

Four tables: `companies` → `contacts` and `deals` (both linked to companies), and `activities` (linked to deals and contacts). Full referential integrity throughout.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `companies` | `company_id`, `name`, `industry`, `size`, `country`, `revenue`, `website` |
| `contacts` | `contact_id`, `company_id`, `name`, `email`, `phone`, `title`, `lead_source`, `created_at` |
| `deals` | `deal_id`, `contact_id`, `company_id`, `name`, `value`, `stage`, `probability`, `close_date`, `owner` |
| `activities` | `activity_id`, `deal_id`, `contact_id`, `type`, `subject`, `outcome`, `activity_date` |

### Realistic distributions

- **Deal values** lognormal ~$25k median, long tail of enterprise deals matching real B2B pipelines
- **Pipeline stages:** prospecting 35%, qualification 25%, proposal 20%, negotiation 12%, closed-won 8%
- **Activity types:** email 40%, call 30%, meeting 20%, demo 10%, matching real sales rep behavior
- **`probability`** is correlated with stage, later stage = higher close probability
- **`lead_source`** varies across organic, paid, referral, and outbound channels

## Quick start

```python
import misata

tables = misata.generate(
    "B2B SaaS company with 500 accounts and a 6-month sales pipeline",
    rows=500,
    seed=42,
)

# Pipeline value by stage
print(tables["deals"].groupby("stage")["value"].agg(["count", "sum", "mean"]))

# Activity volume by type
print(tables["activities"]["type"].value_counts())

# Win rate
closed = tables["deals"][tables["deals"]["stage"] == "closed-won"]
print(f"Win rate: {len(closed)/len(tables['deals']):.1%}")
```

## Common use cases

- **CRM platform demos**: populate a demo environment with realistic accounts, contacts, and pipeline data so prospects see a lived-in product
- **Lead scoring model training**: generate thousands of contacts with source, title, and deal outcomes to train and evaluate propensity models
- **Revenue forecasting prototypes**: build weighted pipeline models against deals with stage-accurate probability values before connecting real data
- **CRM migration testing**: validate ETL scripts and field mappings against a full relational dataset before touching production records
- **Sales analytics dashboards**: build conversion rate, activity cadence, and pipeline velocity reports on realistic CRM data
- **Integration QA**: test webhooks, sync jobs, and API integrations against realistic email formats, phone numbers, and company sizes

## Advanced: Q4 close push narrative

```python
tables = misata.generate(
    "SaaS company with aggressive Q4 close push — deal activity spikes in October-November, "
    "strong closed-won in December",
    rows=1000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# European B2B — German, French, Spanish company names and contacts
tables = misata.generate("European B2B software company with accounts in Germany and France", rows=500)

# US enterprise — US company names, enterprise deal sizes
tables = misata.generate("US enterprise software company with Fortune 500 accounts", rows=300)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "B2B SaaS CRM with 500 accounts",
    min_quality_score=85,
    smart_correlations=True,  # auto-adds company_revenue↔deal_value correlation
    rows=500,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Column Correlations](../guides/correlations.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
