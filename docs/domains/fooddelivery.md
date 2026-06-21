---
title: Generate Food Delivery Synthetic Data in Python | Misata
description: Generate realistic food delivery synthetic datasets in Python, restaurants, customers, couriers, orders, and order items with delivery time coherence and cuisine distributions. No real order data required.
---

# Generate Food Delivery Synthetic Data in Python

Food delivery platforms have a five-entity data model: restaurants, customers, couriers, orders, and the individual items within each order. Misata generates all five tables in one call, with every `delivered_at` timestamp guaranteed to be after `placed_at`, cuisine types drawn from realistic distributions, and delivery fees and order amounts matching real-world food app economics.

The data is built for immediate use, no orphaned order_items, no couriers assigned to non-existent restaurants, no negative delivery times.

```python
import misata

tables = misata.generate(
    "A food delivery app with 500 restaurants, 2k customers, and 1k couriers",
    rows=2000,
    seed=42,
)
print(list(tables.keys()))   # ['restaurants', 'customers', 'couriers', 'orders', 'order_items']
print(tables["orders"][["total_amount", "delivery_fee", "status"]].describe())
```

## What Misata generates

Five tables: `restaurants`, `customers`, `couriers`, `orders` (linking all three), and `order_items` (line items per order). Complete referential integrity throughout.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `restaurants` | `restaurant_id`, `name`, `cuisine`, `city`, `rating`, `avg_prep_time`, `is_active` |
| `customers` | `customer_id`, `name`, `email`, `phone`, `city`, `joined_at` |
| `couriers` | `courier_id`, `name`, `vehicle_type`, `rating`, `deliveries_completed` |
| `orders` | `order_id`, `customer_id`, `restaurant_id`, `courier_id`, `total_amount`, `delivery_fee`, `status`, `placed_at`, `delivered_at` |
| `order_items` | `item_id`, `order_id`, `name`, `quantity`, `unit_price` |

### Realistic distributions

- **`delivered_at`** is always after `placed_at`, enforced, not probabilistic
- **Cuisine types** drawn from realistic distribution: pizza, sushi, burgers, Indian, Chinese, Mexican, Thai, and more
- **Delivery fees** lognormal, consistent with platform fee structures
- **Courier ratings** beta-distributed toward 4–5 stars
- **Order totals** match the sum of order_items with realistic variation for fees and promotions

## Quick start

```python
import misata
import pandas as pd

tables = misata.generate(
    "Food delivery app in a major city with 300 restaurants and 1k orders",
    rows=1000,
    seed=42,
)

# Average order value by cuisine
merged = tables["orders"].merge(tables["restaurants"][["restaurant_id", "cuisine"]], on="restaurant_id")
print(merged.groupby("cuisine")["total_amount"].mean().sort_values(ascending=False))

# Delivery time distribution
orders = tables["orders"].copy()
orders["placed_at"] = pd.to_datetime(orders["placed_at"])
orders["delivered_at"] = pd.to_datetime(orders["delivered_at"])
delivered = orders.dropna(subset=["delivered_at"])
delivered["delivery_minutes"] = (delivered["delivered_at"] - delivered["placed_at"]).dt.seconds / 60
print(delivered["delivery_minutes"].describe())
```

## Common use cases

- **Delivery routing algorithm testing**: generate orders with restaurant locations and courier positions to validate dispatch and routing logic
- **Food tech platform development**: seed test databases with full order histories before your app has real restaurant partners
- **Demand forecasting models**: generate order volumes with hour-of-day and day-of-week patterns to train surge prediction models
- **Courier performance analytics**: build delivery time, rating, and completion rate dashboards on realistic courier histories
- **Restaurant analytics tools**: develop order volume, revenue, and rating trend reports before real restaurant data is available
- **Customer LTV and retention models**: generate customer order histories with realistic reorder rates and recency patterns

## Advanced: peak hour curves

```python
tables = misata.generate(
    "Food delivery app with lunchtime and dinner peaks, low overnight volume, "
    "Friday and Saturday surge",
    rows=3000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# Indian food delivery — Indian cuisines, INR pricing, Indian cities
tables = misata.generate("Indian food delivery app with 200 restaurants in Mumbai and Delhi", rows=1000)

# UK platform — British and international cuisines, GBP pricing, UK cities
tables = misata.generate("UK food delivery platform with 150 restaurants in London", rows=800)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Food delivery platform with 500 restaurants",
    min_quality_score=85,
    smart_correlations=True,
    rows=2000,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Narrative Patterns](../guides/narrative-patterns.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
