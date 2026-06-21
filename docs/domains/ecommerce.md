---
title: Generate Ecommerce Synthetic Data in Python | Misata
description: Generate realistic ecommerce synthetic datasets in Python, customers, products, orders, and order items with correct FK relationships, temporal coherence, and Black Friday curves. No training data required.
---

# Generate Ecommerce Synthetic Data in Python

Ecommerce data is inherently relational: customers place orders, orders contain items, items reference products. If you generate these tables independently you get orphaned foreign keys, negative delivery times, and order amounts that don't match line-item totals. Misata generates a fully wired ecommerce dataset, customers, products, orders, and order_items, where every FK relationship is valid, every `delivered_at` is after `shipped_at`, and order amounts follow realistic lognormal distributions.

Whether you're building a Shopify analytics tool, training a product recommendation model, or demoing a warehouse management system, you can have a realistic ecommerce dataset running in under 10 seconds.

```python
import misata

tables = misata.generate("An ecommerce store with 10k customers", rows=10_000, seed=42)
print(list(tables.keys()))   # ['customers', 'products', 'orders', 'order_items']
print(tables["orders"][["amount", "status", "ordered_at"]].describe())
```

## What Misata generates

Four tables with complete referential integrity: `customers` → `orders` → `order_items` → `products`. Temporal columns respect real-world constraints: `shipped_at` is always after `ordered_at`, `delivered_at` is always after `shipped_at`.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `customers` | `customer_id`, `name`, `email`, `city`, `country`, `signup_date`, `lifetime_value` |
| `products` | `product_id`, `name`, `category`, `price`, `cost`, `stock_count`, `rating` |
| `orders` | `order_id`, `customer_id`, `amount`, `status`, `ordered_at`, `shipped_at`, `delivered_at` |
| `order_items` | `item_id`, `order_id`, `product_id`, `quantity`, `unit_price`, `discount` |

### Realistic distributions

- **Order amounts** are lognormal with median ~$85, matching real consumer ecommerce spend patterns
- **Order status distribution:** ~88% delivered, ~8% returned, ~4% in other states (pending, shipped, cancelled)
- **Temporal coherence:** `shipped_at` is always 1–5 days after `ordered_at`; `delivered_at` is always after `shipped_at`
- **Product prices** are lognormal with heavy right tail (cheap commodities + premium items)
- **Customer lifetime value** correlates with order history, high-CLV customers have more orders

## Quick start

```python
import misata

tables = misata.generate(
    "Ecommerce store with 10k customers and 50k orders",
    rows=10_000,
    seed=42,
)

# Verify temporal coherence
orders = tables["orders"].copy()
orders["ordered_at"] = orders["ordered_at"].astype("datetime64[ns]")
orders["shipped_at"] = orders["shipped_at"].astype("datetime64[ns]")
assert (orders["shipped_at"] >= orders["ordered_at"]).all()

# Revenue by category via order_items join
items = tables["order_items"].merge(tables["products"], on="product_id")
print(items.groupby("category")["unit_price"].sum().sort_values(ascending=False))
```

## Common use cases

- **Product recommendation ML**: generate customer purchase histories with realistic category affinities for training collaborative filtering models
- **Shopify analytics development**: build revenue dashboards, cohort analyses, and funnel reports before your store has enough real sales
- **Warehouse / fulfillment system testing**: validate shipment tracking logic against thousands of orders in all status states
- **Fraud detection training data**: combine with `anomaly_rate` to inject outlier transactions for classifier training
- **A/B test simulation**: generate two cohorts with different discount rates and measure the impact on order volume
- **GDPR-safe data exports**: replace real customer PII with synthetic equivalents that preserve statistical properties for analytics

## Advanced: seasonal narrative curves

Ecommerce revenue is highly seasonal, Black Friday, Christmas, and post-holiday slumps are the defining patterns. Misata extracts these from your story and generates row-level data that rolls up to your target monthly revenue.

```python
tables = misata.generate(
    "Ecommerce store with 10k customers — "
    "Black Friday spike in November, Christmas peak in December, Q1 slump, "
    "steady growth through the year from $500k to $2M",
    rows=10_000,
    seed=42,
)

# Monthly revenue follows the narrative
monthly_revenue = tables["orders"].groupby(
    tables["orders"]["ordered_at"].str[:7]
)["amount"].sum()
print(monthly_revenue)
```

## Advanced: locale-aware generation

```python
# Brazilian ecommerce — BRL currency, Portuguese names, São Paulo/Rio cities
tables = misata.generate("Brazilian ecommerce store with 5k customers", rows=5000)

# UK ecommerce — GBP, British names and addresses
tables = misata.generate("UK online shop with 3k customers", rows=3000)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Ecommerce store with 10k customers",
    min_quality_score=85,
    smart_correlations=True,  # auto-correlates price↔quantity sold
    rows=10_000,
    seed=42,
)
```

## Export and seed

```python
# Seed a test Postgres database
misata.seed_database(tables, "postgresql://user:pass@localhost/shop_test")

# Export to CSV for dbt seeds
misata.to_parquet(tables, output_dir="./ecommerce_data/")
```

## Related guides

- [Narrative Patterns](../guides/narrative-patterns.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Anomaly Injection](../guides/anomaly-injection.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
