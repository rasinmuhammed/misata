---
title: Plain-English Generation — Misata Synthetic Data Generator
description: Generate realistic multi-table synthetic datasets from a single sentence. Misata's StoryParser detects domain, scale, locale, and growth patterns automatically — no config required.
---

# Plain-English Generation

The fastest path to multi-table synthetic data: write one sentence, get back a `dict` of DataFrames with referential integrity, realistic distributions, and locale-accurate values.

```python
import misata

tables = misata.generate(
    "A fintech startup with 10k customers, 3% fraud rate, and IBAN accounts",
    rows=10_000,
    seed=42,
)
# Returns: {"customers": DataFrame, "accounts": DataFrame, "transactions": DataFrame}
```

---

## What the parser extracts

Misata's `StoryParser` reads the story and infers four things before a single row is generated:

| Signal | Example phrase | What happens |
|:--|:--|:--|
| **Domain** | `"fintech"`, `"saas"`, `"ecommerce"` | Selects the domain schema (tables, columns, FK relationships) |
| **Scale** | `"10k customers"`, `"500 employees"` | Sets row counts; child tables scale proportionally |
| **Locale** | `"German company"`, `"Brazilian fintech"` | Applies country-accurate names, salaries, national IDs, phone prefixes |
| **Growth curves** | `"MRR from $50k in Jan to $200k in Dec"` | Shapes numeric distributions to match exact monthly targets |

---

## Preview before generating

Use `preview()` to confirm what Misata understood before committing to a large generation:

```python
import misata

report = misata.preview(
    "A SaaS company with 5k users, MRR from $50k in Jan to $200k in Dec"
)

print(report.domain)            # "saas"
print(report.domain_confidence) # "high"
print(report.matched_keywords)  # ["saas", "mrr"]
print(report.scale_params)      # {"users": 5000}
print(report.locale)            # None (no locale detected)
print(report.table_preview)
# [{"name": "users", "rows": 5000, "columns": 12},
#  {"name": "subscriptions", "rows": 5000, "columns": 8}]
print(report.warnings)          # [] — clean detection

print(report.summary())
# ✓ Domain: saas  [high]  matched: saas, mrr
# ✓ Scale: users=5,000
# ✓ Events: 2 detected
#
#   Will generate 2 table(s), 10,000 total rows:
#     users          5,000 rows  (12 columns)
#     subscriptions  5,000 rows  (8 columns)
```

`preview()` calls no generators and produces no data — it is pure inspection.

### DetectionReport fields

| Field | Type | Description |
|:--|:--|:--|
| `domain` | `str \| None` | Detected domain code or `None` |
| `domain_confidence` | `str` | `"high"` (≥2 keywords), `"low"` (1 keyword), `"none"` |
| `matched_keywords` | `list[str]` | Keywords from the winning domain that appeared in the story |
| `near_misses` | `dict[str, list[str]]` | Other domains whose keywords also appeared |
| `scale_params` | `dict[str, int]` | Parsed numeric scale signals |
| `temporal_events` | `list[dict]` | Growth, churn, crash events detected |
| `locale` | `str \| None` | Auto-detected locale code (e.g. `"de_DE"`) |
| `table_preview` | `list[dict]` | `[{name, rows, columns}]` for every table |
| `total_rows` | `int` | Sum of all table row counts |
| `warnings` | `list[str]` | Fallback / ambiguity warnings |

---

## Domain detection — how it scores

Detection is scored, not first-match. For each domain:

- **+5** if the literal domain name appears in the story (e.g. `"fintech"` → fintech domain gets +5)
- **+1** per matched keyword

The highest-scoring domain wins. This means `"a fintech company with churn"` correctly detects as **fintech** even though `"churn"` is a SaaS keyword — `"fintech"` earns +5 and beats the single SaaS keyword hit.

If two stories are ambiguous, the `near_misses` field tells you which other domains also matched.

```python
report = misata.preview("A fintech company with crypto wallets and 5k users")
print(report.domain)        # "fintech"  (+5 for "fintech" literal)
print(report.near_misses)   # {"crypto": ["crypto", "wallet"]}
```

### Disambiguation tip

Name the domain explicitly and it always wins:

```python
# Ambiguous
misata.generate("A platform with subscription payments and crypto wallets")

# Unambiguous — fintech wins because the word "fintech" scores +5
misata.generate("A fintech platform with subscription payments and crypto wallets")
```

---

## Scale extraction

Any of these forms are recognised:

```
1000 users       → users: 1000
5k users         → users: 5000
1.5M customers   → users: 1500000
200 employees    → users: 200
500 doctors      → users: 500
10k orders       → orders: 10000
50k transactions → transactions: 50000
```

Child tables scale proportionally based on the domain's FK cardinality ratios. A SaaS company with `5k users` automatically produces ~5k subscriptions and ~20k invoices (4× ratio).

---

## Narrative growth curves

This is Misata's core differentiator: natural language maps to **exact per-month targets** that shape the generated data. Specify them in any order; Misata interpolates between control points.

### Monthly anchors

```python
# From–to with interpolation
misata.generate("SaaS company — MRR from $50k in January to $200k in December")

# Multiple control points
misata.generate("SaaS mrr $50k in Jan, $90k in June, $200k in December")

# Mixed: anchors + qualitative modifiers
misata.generate("SaaS mrr $50k in Jan, peak in November, $200k in Dec")
```

### Quarterly patterns

Quarter keywords expand to all three constituent months:

```python
# "Q4 spike" → months 10, 11, 12 all boosted by 1.3×
misata.generate("Ecommerce orders — Q4 spike, Q1 slump")

# "strong Q4" → months 10, 11, 12 lifted by 1.15×
misata.generate("SaaS revenue — strong Q4, flat Q2")

# Quarter-level anchors
misata.generate("SaaS mrr — $100k in Q1, $150k in Q2, $200k in Q3, $250k in Q4")
```

| Pattern | Months affected | Factor |
|:--|:--|:--|
| `Q1 dip / slump` | Jan, Feb, Mar | 0.7× |
| `Q2 flat` | Apr, May, Jun | 1.0× |
| `Q3 peak / spike` | Jul, Aug, Sep | 1.25–1.3× |
| `Q4 push / strong` | Oct, Nov, Dec | 1.15–1.2× |

### Named seasonal events

```python
misata.generate("Ecommerce orders — Black Friday spike, Christmas peak")
misata.generate("EdTech enrollments — back to school surge")
misata.generate("SaaS signups — New Year spike, summer slump")
```

| Event phrase | Month | Factor |
|:--|:--|:--|
| `Black Friday` | November | 1.55× |
| `Cyber Monday` / `Cyber Week` | November | 1.4–1.45× |
| `Christmas` / `Xmas` | December | 1.4× |
| `Holiday season` / `Festive season` | December | 1.3–1.35× |
| `New Year` | January | 1.25× |
| `Valentine` | February | 1.2× |
| `Tax season` | April | 1.2× |
| `Back to school` | August | 1.2× |
| `Summer slump` / `Slow summer` | July + August | 0.75× each |

### Relative multipliers

When you know the end-state but not the absolute numbers, use a multiplier:

```python
# Pure multiplier — Misata derives a sensible baseline and scales it
misata.generate("SaaS startup — MRR 10x growth over the year")
misata.generate("Fintech transaction volume doubled over the year")
misata.generate("Ecommerce GMV tripled in one year")

# Multiplier + one anchor — uses the anchor as the pivot
# Jan is pinned at $50k; Dec is derived as $100k (2× Jan)
misata.generate("SaaS mrr $50k in January, doubled by December")

# Halved (decline story)
misata.generate("SaaS revenue halved after the pivot")
```

| Word form | Factor |
|:--|:--|
| `halved` | 0.5× |
| `doubled` / `2x` | 2× |
| `tripled` / `3x` | 3× |
| `quadrupled` / `4x` | 4× |
| `5x` / `10x` | 5× / 10× |
| `grew 300%` | 4× (1 + 3.0) |

### Qualitative month modifiers

```python
misata.generate("SaaS mrr — dip in March, peak in November")
misata.generate("Ecommerce orders — slump in January, boom in December")
```

| Keyword | Factor |
|:--|:--|
| `crash` | 0.5× |
| `dip` / `drop` / `slump` | 0.7–0.72× |
| `decline` | 0.75× |
| `slow` / `low` | 0.8× |
| `flat` | 1.0× |
| `strong` / `push` | 1.15–1.2× |
| `high` | 1.2× |
| `peak` | 1.25× |
| `boom` / `spike` / `surge` | 1.3× |

### Trigger tokens

A curve is only built when the story contains at least one of these signal words:

`revenue`, `sales`, `mrr`, `arr`, `gmv`, `amount`, `orders`, `bookings`, `transactions`, `volume`, `churn`, `growth`, `peak`, `dip`, `spike`, `surge`, `drop`, `decline`, `slump`, `boom`, `doubled`, `tripled`, `halved`, `black friday`, `christmas`, `summer slump`, `q1`, `q2`, `q3`, `q4`

---

## All 18 domains

| Domain | Trigger keywords | Tables |
|:--|:--|:--|
| `saas` | saas, subscription, mrr, arr, churn | users, subscriptions, invoices |
| `ecommerce` | ecommerce, orders, store, retail, cart | customers, products, orders, order_items |
| `fintech` | fintech, payments, banking, fraud, wallet | customers, accounts, transactions |
| `healthcare` | healthcare, patients, doctors, clinic, hospital | doctors, patients, appointments |
| `marketplace` | marketplace, sellers, buyers, listings, freelance | sellers, buyers, listings, orders |
| `logistics` | logistics, shipping, drivers, fleet, routes | drivers, vehicles, routes, shipments |
| `hr` | hr, employees, payroll, workforce, headcount | departments, employees, payroll |
| `social` | social media, instagram, tiktok, followers, feed | users, posts, follows, reactions, comments |
| `realestate` | real estate, housing, mortgage, listings | agents, properties, transactions |
| `pharma` | pharma, clinical, trials, research | researchers, projects, trials, timesheets |
| `fooddelivery` | food delivery, restaurants, takeout, doordash | restaurants, customers, couriers, orders, order_items |
| `edtech` | edtech, courses, students, enrollments, lms | instructors, courses, students, enrollments, quiz_attempts |
| `gaming` | gaming, players, leaderboard, esports, matches | players, matches, sessions, achievements |
| `crm` | crm, contacts, deals, pipeline, salesforce | companies, contacts, deals, activities |
| `crypto` | crypto, blockchain, ethereum, defi, wallet | wallets, tokens, transactions, token_prices |
| `insurance` | insurance, policy, claims, premium | customers, policies, claims, payments |
| `travel` | travel, hotel, flights, bookings, airbnb | users, hotels, flights, bookings, reviews |
| `streaming` | streaming, netflix, subscribers, watch history | subscribers, content, watch_history, ratings |

[Detailed domain reference with column listings →](../domains.md)

---

## Step-by-step: inspect then generate

```python
import misata

# Step 1 — preview (zero rows generated)
report = misata.preview("A fintech with 5k customers, Black Friday spike", rows=5000)
if report.domain_confidence == "none":
    print("⚠ No domain detected")
    print(report.warnings)

# Step 2 — inspect full schema
schema = misata.parse("A fintech with 5k customers, Black Friday spike", rows=5000)
print(schema.summary())
# Tables: customers, accounts, transactions
# Outcome curves: 1 (transactions.amount, monthly)

# Step 3 — generate
tables = misata.generate_from_schema(schema, seed=42)
print(tables["transactions"].head())
```

---

## Tips

**Be explicit about scale:** `"5k users"` is always clearer than `"a medium-sized company"`.

**Name the domain:** `"A fintech company with..."` always wins over a story that only uses secondary keywords.

**Combine anchors freely:** Monthly anchors, quarter patterns, named events, and multipliers can all appear in the same story. Named events and quarter patterns stack multiplicatively.

**Use `seed` for reproducibility:** Same seed + same story = byte-identical output every time.

**Switch to LLM for open-ended stories:** If your story doesn't fit any of the 18 domains, `LLMSchemaGenerator` can interpret it using a large language model:

```python
from misata import LLMSchemaGenerator
gen = LLMSchemaGenerator(provider="groq")
schema = gen.generate_from_story("A B2B API platform with rate limits and invoicing")
tables = misata.generate_from_schema(schema)
```
