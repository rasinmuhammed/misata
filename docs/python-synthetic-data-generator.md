---
title: Python Synthetic Data Generator — Misata
description: Misata is an open-source Python synthetic data generator. Create realistic multi-table test datasets from plain English — no training data, no config. The best Faker alternative for developers.
---

# Python Synthetic Data Generator

Misata is a Python synthetic data generator for teams who need more than random rows.

If you are searching for a library that can generate realistic multi-table test data
or scenario-based business data from a plain-English description, this page explains
what Misata does and how to get started.

## Quick start (no config required)

```bash
pip install misata
```

```python
import misata

# One line — story → dict of DataFrames
tables = misata.generate("A SaaS company with 5000 users and monthly subscriptions.", seed=42)

print(tables["users"].head())
#    user_id                 email           name signup_date
# 0        1  tricia23@example.com  Patricia Müller  2023-04-12
# ...

print(tables["subscriptions"].head())
#    subscription_id  user_id     plan     mrr     status  start_date
# 0                1        1  starter   49.00     active  2023-04-15
# ...
```

## What Misata generates

Misata understands 7 business domains out of the box:

| Domain | Example prompt | Tables |
|---|---|---|
| SaaS | "5k users, 20% churn" | users, subscriptions, invoices |
| Ecommerce | "10k orders, seasonal peak" | customers, orders |
| Fintech | "2k customers, fraud detection" | customers, accounts, transactions |
| Healthcare | "500 patients and doctors" | doctors, patients, appointments |
| Marketplace | "sellers and buyers" | sellers, buyers, listings, transactions |
| Logistics | "1000 shipments across routes" | drivers, routes, shipments |
| Pharma | "clinical trials" | patients, trials, compounds, outcomes |

## Multi-table with referential integrity

Every child table's foreign key column references a valid parent ID — guaranteed,
not random:

```python
tables = misata.generate("A fintech company with 2000 customers and banking transactions.", seed=42)

customers    = tables["customers"]     # 2,000 rows
accounts     = tables["accounts"]      # ~4,000 rows
transactions = tables["transactions"]  # ~20,000 rows

# No orphan rows — FK integrity is automatic
orphans = (~transactions["account_id"].isin(accounts["account_id"])).sum()
assert orphans == 0  # always passes
```

## Inspect the schema before generating

```python
schema = misata.parse("An ecommerce store with 10k orders")
print(schema.summary())
# Schema: EcommerceDataset
# Domain: ecommerce
# Tables (2)
#   customers  10,000 rows  [customer_id, email, name, signup_date]
#   orders     60,000 rows  [order_id, customer_id, order_date, amount, status]
# Relationships (1)
#   customers.customer_id → orders.customer_id

# Tweak, then generate
schema.seed = 42
tables = misata.generate_from_schema(schema)
```

## Exact aggregate targets

Misata can pin monthly sums so that rows actually add up to specified targets:

```python
schema = misata.parse(
    "A SaaS company with 1000 users. "
    "MRR rises from $50k in January to $200k in December with a dip in September.",
    rows=1000,
)
tables = misata.generate_from_schema(schema)

# All 12 monthly MRR targets hit exactly — to the cent
```

## Domain-realistic distributions

Misata ships calibrated priors so you don't have to configure them:

- **Credit scores** — normal distribution centred on real FICO statistics (mean ≈ 680–720, std ≈ 75)
- **MRR** — log-normal, because real SaaS revenue is right-skewed
- **Transaction types** — Zipf distribution, because one type always dominates
- **Blood types** — exact ABO/Rh frequencies (O+ 38%, A+ 34%, …)
- **Monetary amounts** — log-normal with realistic min/max bounds

## LLM-powered generation (optional)

When the rule-based parser isn't specific enough, hand off to an LLM:

```python
from misata import LLMSchemaGenerator

gen    = LLMSchemaGenerator(provider="groq")   # or "openai"
schema = gen.generate_from_story("A B2B marketplace with vendor tiers, SLA contracts, and quarterly invoices")
tables = misata.generate_from_schema(schema)
```

Requires `GROQ_API_KEY` or `OPENAI_API_KEY`. Retries automatically on rate limits.

## Database seeding

```python
from misata import seed_database

tables = misata.generate("A SaaS company with 1000 users.", seed=42)
report = seed_database(tables, "postgresql://user:pass@localhost/mydb", create=True)
print(report.total_rows)  # 6,000+
```

## Why Misata instead of Faker or SDV

- **vs Faker**: Faker generates standalone fake values. Misata generates *related tables*
  that reference each other correctly, with business constraints and distribution control.
- **vs SDV**: SDV requires real training data. Misata generates from scratch — no data,
  no model, no privacy risk.

See [faker-vs-sdv-vs-misata.md](faker-vs-sdv-vs-misata.md) for a full comparison with
side-by-side code.

## Related

- [Multi-table synthetic data in Python](multi-table-synthetic-data.md)
- [Database seeding with Python](database-seeding-python.md)
- [Faker vs SDV vs Misata](faker-vs-sdv-vs-misata.md)
