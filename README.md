<div align="center">

# 🧠 Misata
### The Intelligent Synthetic Data Engine

[![PyPI version](https://img.shields.io/pypi/v/misata.svg?color=purple&style=for-the-badge)](https://pypi.org/project/misata/)
[![Python versions](https://img.shields.io/pypi/pyversions/misata.svg?style=for-the-badge)](https://pypi.org/project/misata/)
[![License](https://img.shields.io/github/license/rasinmuhammed/misata.svg?style=for-the-badge)](https://github.com/rasinmuhammed/misata/blob/main/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/misata?style=for-the-badge&color=blue)](https://pypi.org/project/misata/)

**Stop writing fake data scripts.**  
**Generate production-grade datasets from natural language.**

[Quick Start](#-quick-start) • [Features](#-features) • [Python API](#-python-api) • [Enterprise](#-enterprise)

</div>

---

## 🚀 Why Misata?

Misata isn't just a random data generator. It's an **intelligent engine** that understands your business logic, relationships, and constraints. Whether you need 50 rows for unit tests or 10 million rows for load testing, Misata delivers **statistically realistic** data that looks and behaves like the real thing.

| Feature | Faker | SDV | **Misata** |
|:---|:---:|:---:|:---:|
| **Natural Language Input** | ❌ | ❌ | ✅ |
| **Auto Schema Generation** | ❌ | ❌ | ✅ |
| **Relational Integrity** | ❌ | ✅ | ✅ |
| **Business Constraints** | ❌ | ❌ | ✅ |
| **No Training Data Needed** | ✅ | ❌ | ✅ |
| **Streaming (10M+ rows)** | ❌ | ❌ | ✅ |

---

## ⚡ Quick Start

### 1. Install
```bash
pip install misata
```

### 2. Generate
Describe what you need in plain English. Misata handles the rest.

```bash
# Basic generation (Rule-based, instant)
misata generate --story "A SaaS platform with 50K users, monthly subscriptions, and a 20% churn rate in Q3"

# Intelligent generation (LLM-powered)
export GROQ_API_KEY=gsk_...
misata generate --story "E-commerce store with seasonal trends and customer segments" --use-llm
```

### 3. Result
Misata creates a relational schema, generates the data, and saves it to `./generated_data`.

```text
📋 Schema: SaaS_Platform
   Tables: 4 (users, subscriptions, payments, events)
   Relationships: 3
   Events: 1 (Churn Spike Q3)

🚀 Performance: 385,000 rows/second
💾 Data saved to: ./generated_data
```

---

## 🆕 New in v0.5.3 — Reusable Runs

Misata can now save generation settings as a recipe and rerun them with machine-readable reports.

```bash
# Create a reusable recipe
misata recipe init \
  --name saas_smoke \
  --story "A SaaS platform with 1K users and subscriptions" \
  --output ./saas_recipe.yaml

# Run it later
misata recipe run --config ./saas_recipe.yaml --rows 1000
```

Each recipe run writes:
- `run_manifest.json`
- `validation_report.json` when validation is enabled
- `quality_report.json` when quality checks are enabled
- `audit_report.json` when audit mode is enabled

This keeps Misata’s current generation flow intact, but makes it easier to repeat, review, and share working runs.

---

## 🔥 New in v0.5.2 — The Realism Engine

Every column is now aware of every other column. Misata generates data that is **mathematically consistent**, not randomly independent.

### What makes this different from Faker?

```text
                 Faker/Random              Misata v0.5.3
─────────────────────────────────────────────────────────
order.total      $847.23 (random)          $847.23 = $798.50 + $29.99 + $18.74
product.cost     $96.00 (> price!)         $41.20 (43% of price $95.81)
line_total       $3,291.00 (random)        $3,291.00 = 5 × $662.00 − $19.00
user.email       luke.ri@wanadoo.co.uk     emma.chen@gmail.com (from name)
rating           137 (wat?)                4 ★ (J-curve weighted)
categories       "Hypothyroidism"          "Electronics"
delivered_at     2021-01-03 (before order) 2024-03-15 (+7 days after order)
─────────────────────────────────────────────────────────
Row counts       100 × every table         15 categories, 500 order_items
```

### Smart Row Proportions

Misata analyzes your FK graph to size tables realistically:

```bash
misata generate --db-url sqlite:///shop.db --smart --rows 100

# categories:    15   (reference — fewer, no duplicates)
# users:        100   (entities — your base count)
# products:     250   (entities with variety)
# orders:       250   (transactions — more than users)
# order_items:  500   (line items — most rows)
# reviews:      150   (activity — subset of orders)
```

### Seed Any Existing Database

```bash
# PostgreSQL, MySQL, SQLite — just point and seed
misata generate \
  --db-url postgresql://user:pass@localhost:5432/mydb \
  --smart --rows 10000 --db-truncate
```

---

## 💻 Python API

Seamlessly integrate Misata into your test suites and CI/CD pipelines.

### Standard Generation
```python
from misata import DataSimulator
from misata.llm_parser import LLMSchemaGenerator

# 1. Design schema with AI
llm = LLMSchemaGenerator(provider="groq")
config = llm.generate_from_story(
    "Healthcare app with patients, doctors, and appointments"
)

# 2. Generate data
simulator = DataSimulator(config)
for table_name, df in simulator.generate_all():
    print(f"Generated {len(df)} rows for {table_name}")
    df.to_csv(f"{table_name}.csv", index=False)
```

### SQLAlchemy Seeding (Powerful!)
Directly seed your SQLAlchemy models without writing factories.

```python
from misata import seed_from_sqlalchemy_models
from myapp.models import Base, engine

# Automatically analyzes your models and foreign keys
report = seed_from_sqlalchemy_models(
    engine, 
    Base, 
    default_rows=10_000, 
    create=True, 
    smart_mode=True  # Infers realistic values from column names
)

print(f"Seeded {report.total_rows} rows in {report.duration_seconds}s")
```

### Reusable Recipes
Save a run once, then keep it in source control.

```python
from misata import RecipeSpec, load_recipe

recipe = load_recipe("./saas_recipe.yaml")
print(recipe.name)
print(recipe.output_dir)
```

---

## 🎯 Business Constraints

Define complex rules that simple random generators can't handle.

```python
from misata import Constraint, Table

timesheets = Table(
    name="timesheets",
    row_count=10000,
    constraints=[
        Constraint(
            name="max_daily_hours",
            type="sum_limit",
            group_by=["employee_id", "date"],
            column="hours",
            value=8.0,
            action="redistribute"  # Automatically fixes violations
        )
    ]
)
```

---

## 🔌 Providers

Misata supports multiple LLM providers for schema generation.

| Provider | Env Var | Tier | Best For |
|:---|:---|:---|:---|
| **Groq** | `GROQ_API_KEY` | Free | **Speed** (Recommended) |
| **OpenAI** | `OPENAI_API_KEY` | Paid | **Quality** |
| **Ollama** | None | Free | **Privacy** (Local) |

---

## 🏢 Enterprise

**Building a platform?** Misata Studio is our commercial offering for teams.

- 🖥️ **Visual Schema Editor**: Drag-and-drop schema design.
- 🔒 **Privacy Filters**: PII scanning and masking.
- 📦 **One-Click Deploy**: Docker & Kubernetes ready.
- 🤝 **Support**: Dedicated support and custom integration.

[Contact Sales](mailto:rasinbinabdulla@gmail.com) for a demo.

---

<div align="center">
Built with ❤️ by <a href="https://github.com/rasinmuhammed">Muhammed Rasin</a>
</div>
