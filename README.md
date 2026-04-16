<div align="center">

# Misata

### Realistic multi-table synthetic data for testing and demos

[![PyPI version](https://img.shields.io/pypi/v/misata.svg?style=for-the-badge)](https://pypi.org/project/misata/)
[![Python versions](https://img.shields.io/pypi/pyversions/misata.svg?style=for-the-badge)](https://pypi.org/project/misata/)
[![CI](https://img.shields.io/github/actions/workflow/status/rasinmuhammed/misata/ci.yml?branch=main&style=for-the-badge&label=tests)](https://github.com/rasinmuhammed/misata/actions)
[![License](https://img.shields.io/github/license/rasinmuhammed/misata.svg?style=for-the-badge)](https://github.com/rasinmuhammed/misata/blob/main/LICENSE)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/rasinmuhammed/misata/blob/main/notebooks/quickstart.ipynb)

</div>

Misata generates consistent, relational datasets — linked tables, foreign key integrity, domain-realistic distributions — from a plain English description, a YAML schema file, an existing database, or a Python dict. No ML model required. No real data needed.

Built for:
- **Seeding dev/staging databases** with production-like data
- **Integration tests** that need referentially consistent multi-table fixtures
- **Demos and prototypes** that should feel real without exposing PII
- **BI and dashboard development** against a realistic data shape

---

## Install

```bash
pip install misata
```

Optional extras:
```bash
pip install "misata[llm]"        # multi-provider LLM schema generation
pip install "misata[documents]"  # PDF output via weasyprint
pip install "misata[advanced]"   # SDV/CTGAN ML synthesis
```

---

## Six ways to generate data

### 1. Plain English (no config needed)

```python
import misata

tables = misata.generate("A SaaS company with 5k users, monthly subscriptions, and 20% churn")
print(tables["users"].head())
print(tables["subscriptions"].head())
```

### 2. YAML schema-as-code (commit to git, reproduce anywhere)

```bash
# Scaffold a schema file
misata init

# Edit misata.yaml, then generate
misata generate
```

```yaml
# misata.yaml
name: my-app
seed: 42

tables:
  users:
    rows: 1000
    columns:
      user_id: { type: int, unique: true }
      email:   { type: text, text_type: email }
      plan:    { type: categorical, choices: [free, pro, enterprise] }

  orders:
    rows: 5000
    columns:
      order_id: { type: int, unique: true }
      user_id:  { type: foreign_key }
      amount:   { type: float, min: 5.0, max: 500.0 }

relationships:
  - "users.user_id → orders.user_id"

constraints:
  - name: amount_above_cost
    table: orders
    type: inequality
    column_a: amount
    operator: ">"
    column_b: cost
```

```python
schema = misata.load_yaml_schema("misata.yaml")
tables = misata.generate_from_schema(schema)
```

### 3. Seed an existing database

The most common production use case: point Misata at your database and fill it with realistic data.

```python
from misata import schema_from_db, generate_from_schema, seed_database

# Introspect your existing schema
schema = schema_from_db("postgresql://user:pass@localhost/myapp")

# Generate data that matches your real table structure
tables = generate_from_schema(schema)

# Seed it back — handles FK ordering automatically
from misata import seed_database
report = seed_database(tables, "postgresql://user:pass@localhost/myapp_dev")
print(report)
# SeedReport: seeded 6 tables, 47,300 rows in 1.2s
```

Or use the CLI:
```bash
# Introspect DB schema → write misata.yaml
misata init --db postgresql://user:pass@localhost/myapp

# Generate and seed in one command
misata generate --db-url postgresql://user:pass@localhost/myapp_dev --db-create
```

SQLAlchemy models are supported too:
```python
from misata import seed_from_sqlalchemy_models
from myapp.models import Base  # your SQLAlchemy declarative base

report = seed_from_sqlalchemy_models(
    Base,
    db_url="sqlite:///test.db",
    row_count=500,
    create_tables=True,
)
```

### 4. Python dict schema (import your own structure)

```python
schema = misata.from_dict_schema({
    "customers": {
        "id":    {"type": "integer", "primary_key": True},
        "email": {"type": "email"},
        "plan":  {"type": "string", "enum": ["free", "pro", "enterprise"]},
    },
    "orders": {
        "id":          {"type": "integer", "primary_key": True},
        "customer_id": {"type": "integer",
                        "foreign_key": {"table": "customers", "column": "id"}},
        "amount":      {"type": "float", "min": 1.0, "max": 999.0},
    },
}, row_count=5_000)

tables = misata.generate_from_schema(schema)
```

### 5. LLM-assisted (richer semantics, optional)

```python
from misata import LLMSchemaGenerator

gen = LLMSchemaGenerator(provider="groq")          # fast, free tier
# gen = LLMSchemaGenerator(provider="anthropic")   # Claude
# gen = LLMSchemaGenerator(provider="ollama", model="llama3")  # local

schema = gen.generate_from_story("A fraud detection dataset — 2% positive rate, FICO scores, transaction velocity features")
tables = misata.generate_from_schema(schema)
```

Requires: `pip install "misata[llm]"` + one of `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`.

### 6. Incremental generation (grow a dataset without re-seeding)

```python
# Initial seed
tables = misata.generate("A fintech company with 1000 customers", seed=1)

# Add 1000 more rows later — IDs auto-offset, FK integrity maintained
tables = misata.generate_more(tables, schema, n=1000, seed=2)
print(len(tables["customers"]))  # 2000
```

---

## CLI

```bash
# Scaffold a new misata.yaml
misata init

# Scaffold from an existing database
misata init --db postgresql://localhost/myapp

# Scaffold from a plain-English description
misata init --story "A marketplace with sellers, buyers, and listings"

# Generate from misata.yaml (auto-detected if present)
misata generate

# Generate with a specific story
misata generate --story "Ecommerce with 10k orders" --rows 10000 --output-dir data/

# Use a built-in domain template
misata template saas --scale 0.1 --output-dir data/

# List available templates
misata templates-list

# Export schema to YAML
misata schema --db-url postgresql://localhost/myapp --output schema.yaml
```

---

## Constraints

Enforce business rules that survive generation:

```python
from misata.constraints import (
    InequalityConstraint,   # price > cost on every row
    ColumnRangeConstraint,  # min_price <= price <= max_price
    RatioConstraint,        # 70% free / 30% pro
    UniqueConstraint,       # no duplicate (user_id, date) pairs
    SumConstraint,          # total hours per employee per day ≤ 8
)

# Apply programmatically
c = InequalityConstraint("price", ">", "cost")
df = c.apply(df)

# Or declare in a SchemaConfig / misata.yaml
```

---

## Export

```python
# Parquet
misata.to_parquet(tables, "data/")

# DuckDB
misata.to_duckdb(tables, "data/dataset.duckdb")

# JSON Lines
misata.to_jsonl(tables, "data/")
```

---

## Quality and privacy reports

```python
bundle = misata.analyze_generation(tables, schema)

print(bundle.data_card.summary())        # row counts, null rates, type distribution
print(bundle.fidelity_report.score)      # 0–1 statistical fidelity vs. schema intent
print(bundle.privacy_report.pii_risk)    # column-level PII exposure analysis
```

---

## Document generation

Turn any table into per-row documents — useful for demo datasets that need to look real end-to-end:

```python
# Built-in templates: invoice, patient_report, transaction_receipt, user_profile
paths = misata.generate_documents(tables, "invoice",
                                  table="orders", output_dir="/tmp/invoices",
                                  format="html")  # or "pdf" with misata[documents]

# Custom Jinja2 template
tmpl = "<h1>Order #{{ order_id }}</h1><p>Amount: ${{ amount }}</p>"
paths = misata.generate_documents(tables, tmpl, table="orders", output_dir="/tmp/custom")
```

---

## What makes Misata different

| | Faker | Synth | syda | SDV | **Misata** |
|---|:---:|:---:|:---:|:---:|:---:|
| No config, one line to multi-table data | No | No | No | No | **Yes** |
| YAML schema committed to git | No | **Yes** | **Yes** | No | **Yes** |
| DB introspection → schema | No | **Yes** | No | Limited | **Yes** |
| Direct DB seeding (Postgres, MySQL, SQLite) | No | No | No | No | **Yes** |
| SQLAlchemy model seeding | No | No | No | No | **Yes** |
| Referential integrity (multi-table FK) | No | **Yes** | **Yes** | **Yes** | **Yes** |
| Inequality / range constraints (price > cost) | No | Limited | No | **Yes** | **Yes** |
| Exact aggregate targets (monthly MRR curve) | No | No | No | No | **Yes** |
| Domain-realistic distributions | No | No | No | Limited | **Yes** |
| Multi-provider LLM (Groq / OpenAI / Claude / Gemini / Ollama) | No | No | **Yes** | No | **Yes** |
| No LLM required (full offline generation) | **Yes** | **Yes** | No | **Yes** | **Yes** |
| Document generation (HTML / PDF per row) | No | No | No | No | **Yes** |
| Quality + privacy reports | No | No | No | Limited | **Yes** |
| Pure Python, no external services | **Yes** | No | No | **Yes** | **Yes** |

**Faker** generates individual fake values — not relational, no schema.
**Synth** is schema-as-code focused, great for git workflows, limited distribution control.
**syda** uses an LLM for every single row — semantically rich but expensive and slow, no offline path.
**SDV** learns from real data (you need real data first) — different problem entirely.
**Misata** generates from intent or schema without real data, offline by default, seeds databases directly.

---

## Supported domains

| Domain | Trigger keywords | Tables generated |
|---|---|---|
| SaaS | saas, subscription, mrr, churn | users, subscriptions |
| Ecommerce | ecommerce, orders, store, retail | customers, orders |
| Fintech | fintech, payments, banking, fraud | customers, accounts, transactions |
| Healthcare | healthcare, patients, doctors, clinic | doctors, patients, appointments |
| Marketplace | marketplace, sellers, buyers, listings | sellers, buyers, listings, orders |
| Logistics | logistics, shipping, drivers, routes | drivers, vehicles, routes, shipments |

No keyword match → falls back to a generic single-table schema.

---

## How it works

```
story / YAML / dict / DB introspection
              ↓
        StoryParser / load_yaml_schema / from_dict_schema / schema_from_db
              ↓
        SchemaConfig  ← validate_schema() catches issues before generation
              ↓
        DataSimulator ← topological sort, FK sampling, domain priors
              ↓
        {table: DataFrame}  →  seed_database / to_parquet / to_duckdb
```

**Domain priors** — monetary columns get log-normal distributions. Categorical columns use Zipf sampling. Blood types use real-world probabilities.

**Outcome curves** — "revenue rises from 50k in Jan to 200k in Dec" becomes exact per-month targets that constrain row-by-row generation.

**Realism rules** — `cost` is always less than `price`. `delivered_at` is always after `shipped_at`. Email addresses derive from first and last name.

---

## Performance

Measured on Apple M-series (single core, no GPU):

| Workload | Rows | Time | Rows/s |
|---|---:|---:|---:|
| Single table, lognormal | 1,000,000 | 0.06s | ~16M |
| Star schema (5 tables, 4 FKs) | 1,055,030 | 1.54s | ~687k |

---

## Contributing

```bash
git clone https://github.com/rasinmuhammed/misata
cd misata
pip install -e ".[dev]"
pytest tests/
```

Issues and PRs welcome: [github.com/rasinmuhammed/misata/issues](https://github.com/rasinmuhammed/misata/issues)

---

<div align="center">
Built by <a href="https://github.com/rasinmuhammed">Muhammed Rasin</a>
</div>
