---
title: Generate Gaming Synthetic Data in Python | Misata
description: Generate realistic gaming synthetic datasets in Python — players, matches, sessions, and achievements with Pareto XP distributions, realistic K/D ratios, and leaderboard data. No real player data required.
---

# Generate Gaming Synthetic Data in Python

Gaming data has a distinctive statistical signature: player levels and XP follow heavy-tailed distributions (most players are low-level, a small elite dominates leaderboards), K/D ratios are beta-distributed around 1.0, and achievement unlock patterns follow the player's progression timeline. Misata generates a four-table gaming dataset — players, matches, sessions, and achievements — where all of this is built in and every FK relationship is valid.

Whether you're testing a leaderboard API, training a churn prediction model on player activity, or building a game analytics dashboard, you can have a statistically accurate gaming dataset running in seconds.

```python
import misata

tables = misata.generate("A competitive FPS game with 10k players and ranked matchmaking", rows=10_000, seed=42)
print(list(tables.keys()))   # ['players', 'matches', 'sessions', 'achievements']
print(tables["players"][["level", "xp", "rank"]].describe())
```

## What Misata generates

Four tables: `players`, `matches`, `sessions` (linking players to matches with per-game stats), and `achievements` (player milestone records). All FKs are valid; achievement `unlocked_at` is always after player `joined_at`.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `players` | `player_id`, `username`, `level`, `xp`, `rank`, `country`, `joined_at`, `last_active` |
| `matches` | `match_id`, `game_mode`, `map`, `duration_seconds`, `winner_team`, `started_at` |
| `sessions` | `session_id`, `player_id`, `match_id`, `kills`, `deaths`, `assists`, `score`, `result` |
| `achievements` | `achievement_id`, `player_id`, `name`, `category`, `unlocked_at`, `points` |

### Realistic distributions

- **Player levels** follow a right-skewed lognormal — most players are low-to-mid level, a long elite tail reaches max level
- **XP** follows a Pareto distribution — top players have disproportionately high experience totals
- **K/D ratio** (kills/deaths per session) beta-distributed around 1.0, with correct shape for ranked play
- **`last_active`** is always after `joined_at` — temporal coherence enforced
- **Achievement `unlocked_at`** is always after `joined_at` — no achievements before registration

## Quick start

```python
import misata

tables = misata.generate("An esports platform with 5k ranked players", rows=5000, seed=42)

# K/D analysis
sessions = tables["sessions"]
sessions["kd_ratio"] = sessions["kills"] / (sessions["deaths"] + 0.001)
print(sessions["kd_ratio"].describe())

# Player level distribution
print(tables["players"]["level"].describe())

# Top players by XP
top_players = tables["players"].nlargest(10, "xp")[["username", "level", "xp", "rank"]]
print(top_players)
```

## Common use cases

- **Leaderboard and ranking API testing** — populate leaderboards with thousands of players across realistic level and XP distributions to stress-test sorting and pagination
- **Churn prediction models** — generate players with `last_active` timestamps and session frequency for training binary retention classifiers
- **Matchmaking algorithm development** — use session data with kills, deaths, and scores to prototype skill-based matchmaking without production logs
- **Game analytics dashboards** — seed BI tools with player activity data that produces sensible DAU/MAU and retention funnel metrics
- **Achievement system QA** — validate badge unlock logic against thousands of achievements across varied categories and point values
- **Anti-cheat detection training** — inject anomalous K/D ratios and XP progression patterns to develop detection rule classifiers

## Advanced: player growth narrative

```python
tables = misata.generate(
    "Battle royale game that launched 18 months ago — player surge at launch, "
    "plateau through mid-year, spike after a major update in month 12",
    rows=10_000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# Southeast Asian mobile game — regional usernames, Asian country distribution
tables = misata.generate("Mobile MOBA popular in Southeast Asia with 5k players", rows=5000)

# European esports — European player distribution, competitive ranks
tables = misata.generate("European esports platform with 3k ranked players", rows=3000)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Competitive gaming platform with 5k players",
    min_quality_score=85,
    smart_correlations=True,  # auto-adds level↔xp, rank↔kills correlations
    rows=5000,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Narrative Patterns](../guides/narrative-patterns.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
