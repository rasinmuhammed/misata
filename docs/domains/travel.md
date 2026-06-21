---
title: Generate Travel Synthetic Data in Python | Misata
description: Generate realistic travel synthetic datasets in Python, users, hotels, flights, bookings, and reviews with temporal coherence, conditional cancellation reasons, and loyalty tier distributions. No real booking data required.
---

# Generate Travel Synthetic Data in Python

Travel platform data has subtle but critical coherence requirements: `check_out` must be after `check_in`, `arrival_at` must be after `departure_at`, and `cancellation_reason` should only be populated for cancelled bookings, never for active or completed ones. Get any of these wrong and your analytics will look broken from the first query. Misata generates a five-table travel dataset where all of these invariants are enforced from the start, across users, hotels, flights, bookings, and reviews.

```python
import misata

tables = misata.generate(
    "A travel booking platform with 5k users, hotels, and international flights",
    rows=5000,
    seed=42,
)
print(list(tables.keys()))   # ['users', 'hotels', 'flights', 'bookings', 'reviews']

# Cancellation reason is only set for cancelled bookings
cancelled = tables["bookings"][tables["bookings"]["status"] == "cancelled"]
active = tables["bookings"][tables["bookings"]["status"] != "cancelled"]
assert cancelled["cancellation_reason"].notna().all()
assert active["cancellation_reason"].isna().all()
```

## What Misata generates

Five tables: `users` → `bookings` (linking users, hotels, and flights) → `reviews`. Hotel star ratings and prices are correlated; flight prices vary by seat class; users are distributed across loyalty tiers.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `users` | `user_id`, `name`, `email`, `country`, `loyalty_tier`, `joined_at` |
| `hotels` | `hotel_id`, `name`, `city`, `country`, `stars`, `price_per_night`, `total_rooms` |
| `flights` | `flight_id`, `origin`, `destination`, `airline`, `departure_at`, `arrival_at`, `seat_class`, `price` |
| `bookings` | `booking_id`, `user_id`, `hotel_id`, `flight_id`, `check_in`, `check_out`, `total_price`, `status`, `cancellation_reason` |
| `reviews` | `review_id`, `booking_id`, `rating`, `title`, `body`, `reviewed_at` |

### Realistic distributions

- **`cancellation_reason` is null for non-cancelled bookings**: conditional null enforced consistently
- **`check_out`** always after `check_in`; **`arrival_at`** always after `departure_at`
- **Hotel `price_per_night`** is correlated with `stars`, 5-star hotels cost more than 2-star
- **Loyalty tier** follows a realistic pyramid: most users are base tier, fewer are gold/platinum
- **Review ratings** slightly right-skewed with a realistic 1-star tail

## Quick start

```python
import misata
import pandas as pd

tables = misata.generate(
    "Global travel platform with 3k users, hotels, and flights",
    rows=3000,
    seed=42,
)

# Hotel price by star rating
print(tables["hotels"].groupby("stars")["price_per_night"].describe())

# Booking status distribution
print(tables["bookings"]["status"].value_counts(normalize=True))

# Average review by loyalty tier
merged = tables["reviews"].merge(
    tables["bookings"][["booking_id", "user_id"]], on="booking_id"
).merge(
    tables["users"][["user_id", "loyalty_tier"]], on="user_id"
)
print(merged.groupby("loyalty_tier")["rating"].mean())
```

## Common use cases

- **Hotel recommendation engine development**: use booking history, star ratings, and review scores to build and evaluate hotel ranking models
- **Cancellation prediction models**: train classifiers on bookings with status, total_price, loyalty_tier, and lead time to predict cancellation likelihood
- **Dynamic pricing prototype**: test pricing algorithms against flights and hotels with realistic base price distributions
- **Booking flow QA**: validate end-to-end booking, modification, and cancellation workflows against data with correct date semantics and status transitions
- **Customer support tooling**: test support dashboards with realistic booking histories, cancellation reasons, and review text
- **Loyalty program analytics**: analyse tier upgrade patterns and booking frequency across a realistic loyalty tier distribution

## Advanced: seasonal booking narrative

```python
tables = misata.generate(
    "European travel platform — summer beach holiday peak in July-August, "
    "winter ski bookings in December-January, autumn shoulder season",
    rows=5000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# Southeast Asian travel platform — SEA destinations, regional airlines
tables = misata.generate("Southeast Asian travel platform with flights to Bangkok and Bali", rows=2000)

# European OTA — European cities, EU airlines, EUR pricing
tables = misata.generate("European travel agency with flights and hotels across EU cities", rows=3000)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Travel platform with 5k users",
    min_quality_score=85,
    smart_correlations=True,  # auto-adds hotel_stars↔total_price, loyalty_tier↔rating
    rows=5000,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Narrative Patterns](../guides/narrative-patterns.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
