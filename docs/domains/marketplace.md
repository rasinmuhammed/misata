---
title: Generate Marketplace Synthetic Data in Python | Misata
description: Generate realistic marketplace synthetic datasets in Python — sellers, buyers, listings, and orders with power-law seller distributions, beta-rated reviews, and referential integrity. No real user data required.
---

# Generate Marketplace Synthetic Data in Python

Online marketplaces have a distinctive data shape: a small number of power sellers drive most of the volume, buyer ratings cluster high, and listing prices follow a long-tailed distribution. If you generate seller, buyer, and listing data independently you lose all of this structure — and your marketplace analytics tool will look wrong from the first dashboard query. Misata generates a fully wired marketplace dataset where seller volume follows a power-law, ratings are beta-distributed toward 4–5 stars, and every order references a real buyer and listing.

```python
import misata

tables = misata.generate("A freelance marketplace with 500 sellers and 2000 buyers", rows=2000, seed=42)
print(list(tables.keys()))   # ['sellers', 'buyers', 'listings', 'orders']
print(tables["orders"][["amount", "status"]].describe())
```

## What Misata generates

Four tables: `sellers`, `buyers`, `listings` (linked to sellers), and `orders` (linked to buyers and listings). Order completion rate is ~85% by default.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `sellers` | `seller_id`, `name`, `email`, `rating`, `total_sales`, `joined_at`, `country` |
| `buyers` | `buyer_id`, `name`, `email`, `total_spent`, `joined_at` |
| `listings` | `listing_id`, `seller_id`, `title`, `category`, `price`, `status`, `created_at` |
| `orders` | `order_id`, `buyer_id`, `listing_id`, `amount`, `status`, `created_at`, `completed_at` |

### Realistic distributions

- **Seller volume** follows a power-law — top 10% of sellers account for ~60% of total_sales
- **Seller ratings** beta-distributed (skewed toward 4–5 stars) — matching real platform rating inflation
- **Listing prices** lognormal — affordable commodities plus premium service listings
- **Order completion rate** ~85% — remaining 15% in pending, disputed, or cancelled states
- **`completed_at`** is always after `created_at` for completed orders

## Quick start

```python
import misata

tables = misata.generate("A freelance marketplace with 500 sellers and 2000 buyers", rows=2000, seed=42)

# Power-law seller distribution
import numpy as np
total_sales = tables["sellers"]["total_sales"].sort_values(ascending=False)
top10_pct = total_sales.head(len(total_sales) // 10).sum() / total_sales.sum()
print(f"Top 10% sellers: {top10_pct:.0%} of total sales")

# Order completion rate
print(tables["orders"]["status"].value_counts(normalize=True))
```

## Common use cases

- **Marketplace trust and safety** — generate seller profiles with varied rating histories for testing fraud detection and account suspension workflows
- **Search ranking model training** — use `listings` with price, category, and seller rating features to train relevance ranking models
- **Commission and fee calculation testing** — validate fee structures against thousands of orders with varied amounts and statuses
- **Seller analytics dashboard development** — build GMV, conversion rate, and listing performance reports on realistic power-law distributed seller data
- **Buyer recommendation systems** — use `orders` history to prototype collaborative filtering before real purchase data exists
- **Dispute resolution workflow testing** — generate orders in all status states including disputed for testing escalation logic

## Advanced: GMV narrative curves

```python
tables = misata.generate(
    "Marketplace with 1k sellers — Black Friday GMV spike, slow January, growing through the year",
    rows=5000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# Latin American marketplace — BRL/MXN pricing, regional product categories
tables = misata.generate("Brazilian ecommerce marketplace with 500 sellers", rows=2000)

# Southeast Asian gig marketplace — SGD pricing, regional skills
tables = misata.generate("Freelance platform in Southeast Asia with 300 sellers", rows=1000)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Freelance marketplace with 500 sellers",
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
