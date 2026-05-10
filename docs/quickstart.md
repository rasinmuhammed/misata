---
title: Quick Start — Misata Synthetic Data Generator
description: Get started with Misata in 5 minutes. Install, generate multi-table synthetic datasets from plain English, shape data with narrative growth curves, and export to CSV, Parquet, or your database.
---

# Quick Start

## Install

```bash
pip install misata
```

Optional extras:

```bash
pip install "misata[mcp]"        # MCP server — use Misata from Claude / Cursor
pip install "misata[llm]"        # Groq / OpenAI / Claude / Gemini / Ollama schema generation
pip install "misata[documents]"  # PDF output via weasyprint
pip install "misata[advanced]"   # SDV/CTGAN statistical synthesis
```

---

## Your first dataset

Write one sentence. Get back a `dict[str, pd.DataFrame]` with referential integrity, realistic distributions, and locale-accurate values.

```python
import misata

tables = misata.generate(
    "A SaaS company with 5k users, monthly subscriptions, and 20% churn",
    seed=42,
)

for name, df in tables.items():
    print(f"{name}: {len(df):,} rows")
    print(df.head(3))
    print()
# users:          5,000 rows
# subscriptions:  5,000 rows
# invoices:      20,000 rows
```

---

## Preview before generating

Use `preview()` to confirm what Misata understood before committing to a large generation run. It calls no generators and produces no rows.

```python
import misata

report = misata.preview(
    "A fintech startup with 10k customers, 3% fraud rate, and IBAN accounts"
)

print(report.domain)             # "fintech"
print(report.domain_confidence)  # "high"
print(report.matched_keywords)   # ["fintech", "fraud"]
print(report.scale_params)       # {"users": 10000}
print(report.locale)             # None

print(report.table_preview)
# [{"name": "customers", "rows": 10000, "columns": 9},
#  {"name": "accounts",  "rows": 10000, "columns": 6},
#  {"name": "transactions", "rows": 80000, "columns": 8}]

print(report.warnings)           # [] — clean detection

print(report.summary())
# ✓ Domain: fintech  [high]  matched: fintech, fraud
# ✓ Scale: users=10,000
# ✓ Events: 0 detected
#
#   Will generate 3 table(s), 100,000 total rows:
#     customers      10,000 rows  (9 columns)
#     accounts       10,000 rows  (6 columns)
#     transactions   80,000 rows  (8 columns)
```

### DetectionReport fields

| Field | Type | Description |
|:--|:--|:--|
| `domain` | `str \| None` | Detected domain code or `None` |
| `domain_confidence` | `str` | `"high"` (≥2 keywords), `"low"` (1 keyword), `"none"` |
| `matched_keywords` | `list[str]` | Keywords that fired for the winning domain |
| `near_misses` | `dict[str, list[str]]` | Other domains whose keywords also appeared |
| `scale_params` | `dict[str, int]` | Parsed numeric scale signals |
| `temporal_events` | `list[dict]` | Growth, churn, crash events detected |
| `locale` | `str \| None` | Auto-detected locale code (e.g. `"de_DE"`) |
| `table_preview` | `list[dict]` | `[{name, rows, columns}]` for each table |
| `total_rows` | `int` | Sum of all table row counts |
| `warnings` | `list[str]` | Fallback and ambiguity warnings |

---

## Narrative growth curves

Describe a growth trajectory in plain English — Misata builds exact per-month targets and shapes generated data to match.

```python
# Ecommerce with seasonal story
tables = misata.generate(
    "Ecommerce store with 10k customers — "
    "revenue from $200k in Jan to $350k in Sep, "
    "Black Friday spike, Christmas peak, Q1 slump after holidays",
    rows=10_000, seed=42
)

# SaaS hockey-stick
tables = misata.generate(
    "SaaS startup with 2k users — MRR $5k in January, 10x growth over the year, "
    "strong Q4 push",
    rows=2000, seed=42
)

# B2B with summer slump
tables = misata.generate(
    "B2B SaaS platform with 1k enterprise customers — "
    "ARR $500k in Jan, doubled by December, summer slump",
    rows=1000, seed=42
)
```

All three pattern types compose freely:

| Pattern type | Example phrase | What it does |
|:--|:--|:--|
| Monthly anchor | `"MRR $50k in January"` | Pins exact value for that month |
| Quarter modifier | `"Q4 spike"` | Boosts Oct/Nov/Dec by 1.3× |
| Named event | `"Black Friday spike"` | November +1.55× |
| Multiplier | `"doubled by December"` | End value = 2× start |
| From–to | `"from $50k to $200k"` | Linear interpolation across the year |

[Full narrative patterns reference →](guides/narrative-patterns.md)

---

## All 18 domains

Misata ships with schemas for 18 industry verticals:

| Domain | Trigger keywords | Tables |
|:--|:--|:--|
| `saas` | saas, mrr, arr, churn | users, subscriptions, invoices |
| `ecommerce` | ecommerce, orders, retail | customers, products, orders, order_items |
| `fintech` | fintech, payments, fraud | customers, accounts, transactions |
| `healthcare` | healthcare, patients, clinic | doctors, patients, appointments |
| `marketplace` | marketplace, sellers, listings | sellers, buyers, listings, orders |
| `logistics` | logistics, shipping, fleet | drivers, vehicles, routes, shipments |
| `hr` | hr, employees, payroll | departments, employees, payroll |
| `social` | social media, followers, feed | users, posts, follows, reactions, comments |
| `realestate` | real estate, mortgage | agents, properties, transactions |
| `pharma` | pharma, clinical, trials | researchers, projects, trials, timesheets |
| `fooddelivery` | food delivery, restaurants | restaurants, customers, couriers, orders |
| `edtech` | edtech, courses, students | instructors, courses, students, enrollments |
| `gaming` | gaming, players, leaderboard | players, matches, sessions, achievements |
| `crm` | crm, contacts, deals | companies, contacts, deals, activities |
| `crypto` | crypto, blockchain, defi | wallets, tokens, transactions, token_prices |
| `insurance` | insurance, policy, claims | customers, policies, claims, payments |
| `travel` | travel, hotel, flights | users, hotels, flights, bookings, reviews |
| `streaming` | streaming, netflix, subscribers | subscribers, content, watch_history, ratings |

[Full domain reference with column listings →](domains.md)

---

## Inspect the schema first

```python
schema = misata.parse("A fintech company with 10k customers")
print(schema.summary())
# Tables: customers, accounts, transactions
# Relationships: customers → accounts → transactions
# Rows: 10,000 / 25,000 / 80,000

tables = misata.generate_from_schema(schema, seed=42)
```

---

## Locale support

Add a country to get locale-accurate names, addresses, national IDs, phone prefixes, and currency-appropriate values:

```python
# German names, IBAN accounts, European address format
tables = misata.generate("A German fintech with 5k customers", seed=42)

# Brazilian locale — CPF national IDs, BRL salaries
tables = misata.generate("A Brazilian HR system with 200 employees", seed=42)

# UK healthcare — NHS numbers, British names
tables = misata.generate("A UK healthcare provider with 1k patients", seed=42)
```

[Localisation reference →](localisation.md)

---

## Export

```python
misata.to_csv(tables, "data/")
misata.to_parquet(tables, "data/")
misata.to_duckdb(tables, "data/dataset.duckdb")
misata.to_jsonl(tables, "data/")
```

---

## CLI

```bash
# Generate from a story
misata generate --story "A marketplace with 10k sellers" --rows 10000

# Generate from YAML schema
misata init        # scaffold misata.yaml
misata generate    # reads misata.yaml automatically

# Profile a CSV file
misata validate customers.csv

# Preview what would be generated (no rows)
misata preview --story "A SaaS company with 5k users"
```

---

## Use from an AI assistant

If you have `misata[mcp]` installed, wire it into Claude Desktop, Cursor, or Windsurf and describe datasets in plain English:

> "Generate a fintech fraud dataset with 10k customers."

> "Build me SaaS subscription data with MRR growing from $50k to $200k over the year."

[MCP server setup →](guides/mcp.md)

---

## Next steps

- [All generation methods →](generation/index.md)
- [Narrative growth patterns →](guides/narrative-patterns.md)
- [Localisation (15 country packs) →](localisation.md)
- [Domain reference (all 18 schemas) →](domains.md)
- [CLI reference →](cli.md)
- [MCP server for AI agents →](guides/mcp.md)
