---
title: Generate Streaming Platform Synthetic Data in Python | Misata
description: Generate realistic streaming platform synthetic datasets in Python, subscribers, content, watch history, and ratings with churn coherence, completion rates, and content type distributions. No real viewer data required.
---

# Generate Streaming Platform Synthetic Data in Python

Streaming platform data has a critical coherence requirement: `churned_at` must be null for active subscribers and non-null for churned ones, and `is_churned` must match. Get this wrong and your churn prediction model trains on contaminated labels. Misata generates a four-table streaming dataset where `is_churned` and `churned_at` are always consistent, content types follow realistic catalog distributions (series 55%, movies 35%, documentaries 10%), and watch completion rates match real streaming benchmarks (~65% for movies).

```python
import misata

tables = misata.generate(
    "A Netflix-like streaming service with 10k subscribers and a content library",
    rows=10_000,
    seed=42,
)
print(list(tables.keys()))   # ['subscribers', 'content', 'watch_history', 'ratings']

# churned_at is null for all active subscribers
active = tables["subscribers"][~tables["subscribers"]["is_churned"]]
assert active["churned_at"].isna().all()
```

## What Misata generates

Four tables: `subscribers`, `content`, `watch_history` (linking subscribers to content), and `ratings`. Churn logic is coherent, content distribution is realistic, and viewing patterns match real streaming behavior.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `subscribers` | `subscriber_id`, `name`, `email`, `plan`, `country`, `joined_at`, `is_churned`, `churned_at` |
| `content` | `content_id`, `title`, `type`, `genre`, `release_year`, `duration_minutes`, `rating`, `language` |
| `watch_history` | `view_id`, `subscriber_id`, `content_id`, `watched_at`, `watch_duration_minutes`, `completed`, `device` |
| `ratings` | `rating_id`, `subscriber_id`, `content_id`, `score`, `rated_at` |

### Realistic distributions

- **`churned_at` is null for active subscribers**: `is_churned` and `churned_at` are always consistent
- **Content type:** series 55%, movies 35%, documentaries 10%, matching real platform catalog ratios
- **Watch completion** rate ~65% for movies; lower per-episode completion for series
- **Plan distribution** across basic, standard, and premium tiers with realistic uptake ratios
- **Device mix** across mobile, smart TV, desktop, and tablet, matching real streaming device splits

## Quick start

```python
import misata
import pandas as pd

tables = misata.generate(
    "A streaming service with 5k subscribers and a diverse content library",
    rows=5000,
    seed=42,
)

# Churn rate
churn_rate = tables["subscribers"]["is_churned"].mean()
print(f"Churn rate: {churn_rate:.1%}")

# Watch completion by content type
merged = tables["watch_history"].merge(
    tables["content"][["content_id", "type"]], on="content_id"
)
print(merged.groupby("type")["completed"].mean())

# Plan distribution
print(tables["subscribers"]["plan"].value_counts(normalize=True))
```

## Common use cases

- **Recommendation model training**: use `watch_history` and `ratings` as the interaction matrix for collaborative filtering models before you have real viewing data
- **Churn prediction pipelines**: train models on subscriber engagement patterns (watch frequency, completion rates, last active date) against `is_churned` labels
- **Content performance analytics**: build watch time, completion rate, and rating dashboards by genre, type, and release year
- **A/B test framework validation**: generate subscriber cohorts with varied plan and country distributions to test experiment assignment pipelines
- **Personalization engine testing**: validate recommendation ranking logic and fallback strategies against a full content catalog
- **Subscriber lifecycle QA**: test onboarding, upgrade, downgrade, and cancellation workflows against subscribers with realistic join and churn patterns

## Advanced: viral growth narrative

```python
tables = misata.generate(
    "Streaming service that gained subscribers rapidly after a viral original series, "
    "now facing increasing churn as the content catalog ages",
    rows=10_000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# Latin American streaming — Spanish and Portuguese content, regional subscriber distribution
tables = misata.generate("Latin American streaming platform with Spanish content library", rows=5000)

# Asian streaming — Korean, Japanese, and Chinese content types
tables = misata.generate("Asian streaming platform with K-drama and anime content", rows=5000)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Streaming platform with 10k subscribers",
    min_quality_score=85,
    smart_correlations=True,  # auto-adds churn risk↔watch_duration correlation
    rows=10_000,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Narrative Patterns](../guides/narrative-patterns.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
