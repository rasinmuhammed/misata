---
title: Generate Real Estate Synthetic Data in Python | Misata
description: Generate realistic real estate synthetic datasets in Python, agents, properties, and transactions with lognormal home price distributions, realistic days-on-market, and referential integrity. No real MLS data required.
---

# Generate Real Estate Synthetic Data in Python

Real estate data has patterns that random generation misses: home prices follow a lognormal distribution with a heavy right tail (the $1M+ tier), days-on-market is lognormal with a median around 23 days, and agent ratings cluster toward 4–5 stars due to platform selection effects. Misata generates a three-table real estate dataset, agents, properties, and transactions, where these distributions are built in and FK relationships are always valid.

```python
import misata

tables = misata.generate("A real estate agency with 500 properties and 50 agents", rows=500, seed=42)
print(list(tables.keys()))   # ['agents', 'properties', 'transactions']
print(tables["properties"][["price", "bedrooms", "status"]].describe())
```

## What Misata generates

Three tables: `agents` (who manage listings), `properties` (listed inventory), and `transactions` (closed sales). Every property references a valid agent; every transaction references a valid property.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `agents` | `agent_id`, `name`, `email`, `agency`, `rating`, `listings_sold`, `years_experience` |
| `properties` | `property_id`, `agent_id`, `address`, `city`, `state`, `price`, `bedrooms`, `bathrooms`, `sqft`, `listing_date`, `status` |
| `transactions` | `transaction_id`, `property_id`, `buyer_name`, `sale_price`, `close_date`, `commission_rate`, `days_on_market` |

### Realistic distributions

- **Home prices** lognormal with US median ~$410k, realistic heavy right tail for luxury properties
- **Days on market** lognormal with median ~23 days, fast movers and long-stale listings both present
- **Agent ratings** beta-distributed toward 4–5 stars, reflecting real platform rating dynamics
- **~60% of listings close**: remainder are active, expired, or withdrawn
- **`sqft`** and `price` are correlated, larger properties cost more

## Quick start

```python
import misata

tables = misata.generate("A real estate agency with 500 properties and 50 agents", rows=500, seed=42)

# Price distribution
print(tables["properties"]["price"].describe())
# Listing status breakdown
print(tables["properties"]["status"].value_counts())
# Commission revenue
transactions = tables["transactions"]
transactions["commission"] = transactions["sale_price"] * transactions["commission_rate"]
print(f"Total commission revenue: ${transactions['commission'].sum():,.0f}")
```

## Common use cases

- **MLS / property search platform development**: seed a test database with listings across price tiers and bedroom counts for search, filter, and sort testing
- **AVMs (automated valuation models)**: generate training data with realistic price, sqft, bedrooms, and location features for regression model development
- **Agent performance analytics**: build conversion rate, average days-on-market, and commission dashboards on realistic agent histories
- **CRM for real estate agents**: test lead management and listing pipeline workflows with realistic property and transaction data
- **Proptech demo environments**: replace real MLS data exports with synthetic equivalents for vendor demos and investor presentations
- **Market report generation**: validate report templates and calculations against a full year of synthetic transaction data

## Advanced: market cycle narrative

```python
tables = misata.generate(
    "Real estate market with rising prices through mid-year, rate hike slowdown in Q3, "
    "slight recovery in Q4",
    rows=1000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# UK property market — GBP pricing, British address format, UK cities
tables = misata.generate("UK estate agency with 300 properties in London and Manchester", rows=300)

# Australian market — AUD pricing, Australian cities, state codes
tables = misata.generate("Australian real estate agency with 400 properties", rows=400)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Real estate market with 500 listings",
    min_quality_score=85,
    smart_correlations=True,  # auto-adds sqft↔price, bedrooms↔price correlations
    rows=500,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Column Correlations](../guides/correlations.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
