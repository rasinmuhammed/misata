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

## 🔥 New in v0.5.0

### 🔄 Schema Introspection & Seeding
Already have a database? Misata can reverse-engineer your schema and seed it with realistic data.

```bash
# 1. Introspect your existing DB
misata schema --db-url postgresql://user:pass@localhost:5432/mydb --output schema.yaml

# 2. Seed it with 100K rows of realistic data
misata generate --config schema.yaml --db-url postgresql://... --db-truncate
```

### 📈 Reverse Engineering from Charts
Describe a chart, and Misata generates the underlying data to match it.

```bash
misata graph "Monthly revenue growing from $10k to $1M over 2 years, with a dip in August"
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
