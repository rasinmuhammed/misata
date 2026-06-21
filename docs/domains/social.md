---
title: Generate Social Media Synthetic Data in Python | Misata
description: Generate realistic social media synthetic datasets in Python, users, posts, follows, reactions, and comments with Pareto follower distributions, realistic captions, and engagement rate distributions. No real user data required.
---

# Generate Social Media Synthetic Data in Python

Social media data has a signature structure that random generators get completely wrong: follower counts follow a Pareto distribution (a tiny fraction of accounts captures most of the reach), engagement rates are beta-distributed between 1–5%, and captions include hashtags and contextual text, not lorem ipsum. Misata generates a five-table social platform dataset that looks like it came from a real app: users with realistic follower/following ratios, posts with media types, a follows graph, reactions, and threaded comments.

```python
import misata

tables = misata.generate("A social media app with 10k creators, posts, and viral content", rows=10_000, seed=42)
print(list(tables.keys()))   # ['users', 'posts', 'follows', 'reactions', 'comments']
print(tables["users"][["follower_count", "is_verified"]].describe())
```

## What Misata generates

Five tables: `users` → `posts` → `reactions`/`comments`, plus a `follows` graph linking users. Every post references a real user; every reaction and comment references a real post and user.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `users` | `user_id`, `username`, `display_name`, `bio`, `follower_count`, `following_count`, `is_verified`, `joined_at` |
| `posts` | `post_id`, `user_id`, `caption`, `media_type`, `like_count`, `comment_count`, `share_count`, `posted_at` |
| `follows` | `follow_id`, `follower_id`, `followee_id`, `followed_at` |
| `reactions` | `reaction_id`, `post_id`, `user_id`, `type`, `reacted_at` |
| `comments` | `comment_id`, `post_id`, `user_id`, `text`, `parent_comment_id`, `posted_at` |

### Realistic distributions

- **Follower counts** follow a Pareto power-law, most accounts have hundreds of followers, a small elite has millions
- **Engagement rate** (~likes/followers) is beta-distributed between 1–5%, matching real influencer benchmarks
- **`is_verified`** is rare (~2% of accounts), consistent with real platform verification sparsity
- **Media types** are distributed across image, video, carousel, and text, not uniformly random
- **Comments** include `parent_comment_id` for threaded replies, not all comments are top-level

## Quick start

```python
import misata
import numpy as np

tables = misata.generate("A social media app with 5k users and influencer content", rows=5000, seed=42)

# Pareto distribution check — top 5% of accounts
followers = tables["users"]["follower_count"].sort_values(ascending=False)
top5 = followers.head(len(followers) // 20).sum() / followers.sum()
print(f"Top 5% accounts hold {top5:.0%} of all followers")

# Verified account stats
verified = tables["users"][tables["users"]["is_verified"]]
print(f"Verification rate: {len(verified)/len(tables['users']):.1%}")
print(verified["follower_count"].describe())
```

## Common use cases

- **Content recommendation model training**: generate user-post interaction data (`reactions`, `watch_history`) for training collaborative filtering and interest models
- **Social graph analytics**: use the `follows` table to prototype graph algorithms, community detection, and influencer identification
- **Moderation and trust and safety tooling**: generate comments and posts at scale to test content classification and flagging pipelines
- **Creator analytics dashboards**: build engagement rate, reach, and growth analytics before real creator data is available
- **Feed ranking algorithm testing**: validate chronological and ranked feed logic against realistic like/comment/share distributions
- **A/B test framework validation**: generate user cohorts with varied follower counts and engagement rates for experiment design testing

## Advanced: viral content curves

```python
tables = misata.generate(
    "Social platform where a viral post caused a follower spike in March, "
    "engagement doubled for 2 weeks then normalized",
    rows=5000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# Indian social platform — Hindi/English usernames, Indian cultural context
tables = misata.generate("Indian social media platform with 5k users", rows=5000)

# Latin American creator economy — Spanish captions, regional trends
tables = misata.generate("Latin American creator platform with 3k influencers", rows=3000)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Social platform with 5k users and creator economy",
    min_quality_score=85,
    smart_correlations=True,  # auto-adds follower_count↔like_count correlation
    rows=5000,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Narrative Patterns](../guides/narrative-patterns.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
