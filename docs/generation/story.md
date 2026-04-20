# Plain English Generation

The fastest path: describe a dataset in plain English and get back a `dict` of DataFrames.

```python
import misata

tables = misata.generate(
    "A fintech startup with 10k customers, 3% fraud rate, and IBAN accounts",
    rows=10_000,
    seed=42,
)
```

## How it works

Misata's `StoryParser` reads the story and infers:

- **Domain** — fintech, SaaS, ecommerce, healthcare, HR, real estate, social media, logistics, marketplace
- **Scale** — "10k customers" → 10 000 rows in the primary table; child tables scale proportionally
- **Locale** — "German company in Berlin" → `de_DE` names, €45k salary median, German postcodes
- **Outcome curves** — "MRR rises from $50k in Jan to $200k in Dec" → exact per-month targets

## Two-step: inspect before generating

```python
schema = misata.parse("A SaaS company with 5k users and 20% churn", rows=5_000)
print(schema.summary())   # tables, relationships, column types

tables = misata.generate_from_schema(schema)
```

## Supported domains

| Domain | Trigger words | Tables |
|:--|:--|:--|
| SaaS | saas, subscription, mrr, churn | users, subscriptions |
| Ecommerce | ecommerce, orders, store, retail | customers, orders |
| Fintech | fintech, banking, payments, fraud | customers, accounts, transactions |
| Healthcare | healthcare, patients, doctors, clinic | doctors, patients, appointments |
| HR | hr, employees, payroll, workforce | departments, employees, payroll |
| Real estate | real estate, housing, mortgage | agents, properties, transactions |
| Social media | social media, influencer, followers, posts | users, posts, follows, reactions, comments |
| Marketplace | marketplace, sellers, buyers, listings | sellers, buyers, listings, orders |
| Logistics | logistics, shipping, drivers, routes | drivers, vehicles, routes, shipments |

!!! tip "No match → generic table"
    If no domain keyword is detected, Misata falls back to a single generic table with inferred columns. Use an explicit domain keyword or switch to `LLMSchemaGenerator` for open-ended stories.
