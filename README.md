<div align="center">

# Misata

### Synthetic data from intent — not from config files

[![PyPI version](https://img.shields.io/pypi/v/misata.svg?style=for-the-badge)](https://pypi.org/project/misata/)
[![Python versions](https://img.shields.io/pypi/pyversions/misata.svg?style=for-the-badge)](https://pypi.org/project/misata/)
[![CI](https://img.shields.io/github/actions/workflow/status/rasinmuhammed/misata/ci.yml?branch=main&style=for-the-badge&label=tests)](https://github.com/rasinmuhammed/misata/actions)
[![License](https://img.shields.io/github/license/rasinmuhammed/misata.svg?style=for-the-badge)](https://github.com/rasinmuhammed/misata/blob/main/LICENSE)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/rasinmuhammed/misata/blob/main/notebooks/quickstart.ipynb)

</div>

```python
import misata

tables = misata.generate("A SaaS company with 5k users, monthly subscriptions, and 20% churn")

print(tables["users"].head())
print(tables["subscriptions"].head())
```

That's it. Misata reads your intent, infers a relational schema, generates linked tables with referential integrity, and applies domain-realistic distributions — all without a config file.

---

## Install

```bash
pip install misata
```

For LLM-assisted generation (optional):
```bash
pip install "misata[llm]"
export GROQ_API_KEY=gsk_...   # or OPENAI_API_KEY
```

---

## Three examples

### SaaS — revenue curve + churn

```python
import misata

tables = misata.generate(
    "A SaaS company with 5k users. Revenue rises from 50k in Jan to 200k in Dec "
    "with a dip in September. 20% churn in Q3.",
    rows=5000,
    seed=42,
)

# users, subscriptions — with exact monthly MRR targets baked in
for name, df in tables.items():
    print(f"{name}: {len(df):,} rows")
```

### Ecommerce — multi-table with FK integrity

```python
tables = misata.generate("An ecommerce store with customers and orders", rows=10_000)

# customers → orders (FK always holds)
assert tables["orders"]["customer_id"].isin(tables["customers"]["customer_id"]).all()
```

### Inspect before generating

```python
schema = misata.parse("A healthcare clinic with patients, doctors, and appointments")
print(schema.summary())
# Schema: Healthcare Dataset
# Domain: healthcare
# Tables: 3  /  Total rows: 15,300
#
#   Table            Rows  Columns
#   ------------ --------  -------
#   doctors           765  doctor_id, first_name, last_name, specialty, years_experience
#   patients        5,000  patient_id, first_name, last_name, age, gender, blood_type ...
#   appointments   10,000  appointment_id, patient_id, doctor_id, appointment_date ...
#
#   Relationships (2):
#     patients.patient_id → appointments.patient_id
#     doctors.doctor_id → appointments.doctor_id

tables = misata.generate_from_schema(schema)
```

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
| Pharma | pharma, clinical, trials | research_projects, timesheets |

No keyword match → falls back to a generic single-table schema with a warning.

---

## What makes Misata different

| | Faker | SDV | Misata |
|---|:---:|:---:|:---:|
| One-liner API | No | No | **Yes** |
| Story-driven schema inference | No | No | **Yes** |
| Exact monthly aggregate targets | No | No | **Yes** |
| Referential integrity | No | Yes | **Yes** |
| Domain-realistic distributions | No | Limited | **Yes** |
| Pre-generation schema validation | No | No | **Yes** |
| Streaming-safe for large datasets | No | No | **Yes** |

The core difference: Faker generates individual fake values. SDV learns from real data. **Misata generates from intent** — you describe a business, and it builds a logically consistent world.

---

## How it works

```
story / intent
      ↓
 StoryParser  ←→  domain priors (lognormal for MRR, Zipf for categories…)
      ↓
 SchemaConfig    ← validate_schema() catches problems before generation
      ↓
 DataSimulator   ← topological sort, FK sampling, realism rules
      ↓
 {table: DataFrame}
```

**Domain priors** — monetary columns automatically get log-normal distributions. Categorical columns get Zipf sampling so one value dominates naturally. Blood types get real-world probabilities.

**Outcome curves** — "revenue rises from 50k in Jan to 200k in Dec" becomes exact per-month targets that constrain generation row by row.

**Realism rules** — `cost` is always less than `price`. `delivered_at` is always after `shipped_at`. Email addresses derive from first and last name.

---

## Full API

```python
import misata

# One-liner
tables = misata.generate(story, rows=10_000, seed=42)

# Two-step
schema = misata.parse(story, rows=10_000)
print(schema.summary())
tables = misata.generate_from_schema(schema)

# Validate a schema before generation
misata.validate_schema(schema)   # raises SchemaValidationError with all issues listed

# LLM-powered (requires misata[llm] + API key)
from misata import LLMSchemaGenerator
gen = LLMSchemaGenerator(provider="groq")   # or "openai", "ollama"
schema = gen.generate_from_story("A fraud detection dataset with 2% positive rate")
tables = misata.generate_from_schema(schema)
```

---

## Performance

Measured on Apple M-series (single core, no GPU):

| Workload | Rows | Time | Rows/s |
|---|---:|---:|---:|
| Single table, lognormal | 1,000,000 | 0.06s | ~16M |
| Star schema (5 tables, 4 FKs) | 1,055,030 | 1.54s | ~687k |

---

## Run the examples

```bash
pip install misata pandas numpy

# SaaS: all 12 monthly MRR targets hit exactly
python examples/saas_revenue_curve.py

# Fintech: FICO distribution matches real-world, fraud rate = 2.00%
python examples/fintech_fraud_detection.py

# Healthcare: ABO/Rh blood types, 2 FK edges, 0 orphans
python examples/healthcare_multi_table.py

# Ecommerce: seasonal revenue curve, power-law order amounts
python examples/ecommerce_seasonal.py
```

---

## Contributing

```bash
git clone https://github.com/rasinmuhammed/misata
cd misata
pip install -e ".[dev]"
pytest tests/
```

Issues and PRs are welcome: [github.com/rasinmuhammed/misata/issues](https://github.com/rasinmuhammed/misata/issues)

---

<div align="center">
Built by <a href="https://github.com/rasinmuhammed">Muhammed Rasin</a>
</div>
