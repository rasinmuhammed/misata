# Misata Quick Start

Get from zero to realistic multi-table data in under 60 seconds.

## Install

```bash
pip install misata
```

## 30-second demo

```python
import misata

tables = misata.generate("A SaaS company with 1000 users and monthly subscriptions", seed=42)

print(tables["users"].head(3))
#    user_id                    email            name signup_date   plan  churned
# 0        1  tricia23@example.com  Patricia Müller  2023-04-12  basic    False
# 1        2     evan44@example.com     Evan Schulz  2023-06-07   pro     True
# 2        3   helena@example.com   Helena Fischer  2023-09-15  starter  False

print(tables["subscriptions"].head(3))
#    subscription_id  user_id     plan     mrr  status  start_date
# 0                1        1  starter   49.00  active  2023-04-15
# 1                2        2      pro  149.00  churned 2023-06-10
# 2                3        3    basic   79.00  active  2023-09-20
```

No config files. No real data needed. Referential integrity is automatic.

---

## Core workflows

### 1. Story → DataFrames

```python
import misata

# One liner — picks domain, generates linked tables, applies realistic distributions
tables = misata.generate("A fintech company with 2000 customers and banking transactions.", seed=42)

customers    = tables["customers"]     # 2,000 rows
accounts     = tables["accounts"]      # ~4,000 rows
transactions = tables["transactions"]  # ~20,000 rows

# FK integrity guaranteed
assert (~transactions["account_id"].isin(accounts["account_id"])).sum() == 0
```

### 2. Inspect schema before generating

```python
schema = misata.parse("A healthcare clinic with patients, doctors, and appointments")
print(schema.summary())
# Schema: HealthcareDataset
# Domain: healthcare
# Tables (3)
#   doctors         25 rows  [doctor_id, name, specialty, department]
#   patients       500 rows  [patient_id, name, age, blood_type, ...]
#   appointments  1500 rows  [appointment_id, patient_id, doctor_id, type, ...]
# Relationships (2)
#   patients.patient_id  → appointments.patient_id
#   doctors.doctor_id    → appointments.doctor_id

# Adjust seed, then generate
schema.seed = 99
tables = misata.generate_from_schema(schema)
```

### 3. Exact aggregate targets (outcome curves)

Tell Misata what your numbers should sum to — it generates rows that hit those targets:

```python
schema = misata.parse(
    "A SaaS company with 1000 users. "
    "MRR rises from $50k in January to $200k in December with a dip in September.",
    rows=1000,
)
tables = misata.generate_from_schema(schema)

# All 12 monthly MRR targets hit exactly — to the cent
```

### 4. LLM-powered generation (optional)

When the rule-based parser isn't specific enough:

```bash
pip install "misata[llm]"
export GROQ_API_KEY=gsk_...   # or OPENAI_API_KEY
```

```python
from misata import LLMSchemaGenerator
import misata

gen    = LLMSchemaGenerator(provider="groq")
schema = gen.generate_from_story(
    "A B2B marketplace with vendor tiers, SLA contracts, and quarterly invoices"
)
tables = misata.generate_from_schema(schema)
```

### 5. Seed a database

```python
from misata import seed_database
import misata

tables = misata.generate("A SaaS company with 1000 users.", seed=42)
report = seed_database(tables, "postgresql://user:pass@localhost/mydb", create=True)
print(report.total_rows)
```

Or from the CLI:

```bash
misata generate \
  --story "A SaaS company with 1000 users" \
  --rows 1000 \
  --db-url sqlite:///./dev.db \
  --db-create \
  --db-truncate
```

### 6. Reusable runs (recipes)

Save a run configuration and replay it exactly:

```bash
misata recipe init \
  --name saas_seed \
  --story "A SaaS company with 1000 users" \
  --output ./saas_recipe.yaml

misata recipe run --config ./saas_recipe.yaml --rows 1000
```

Each run writes a `run_manifest.json`, `validation_report.json`, and `quality_report.json`.

---

## Supported domains

| Domain | Trigger keywords | Tables |
|---|---|---|
| SaaS | saas, subscription, mrr, churn | users, subscriptions |
| Ecommerce | ecommerce, orders, store, retail | customers, orders |
| Fintech | fintech, payments, banking, fraud | customers, accounts, transactions |
| Healthcare | healthcare, patients, doctors, clinic | doctors, patients, appointments |
| Marketplace | marketplace, sellers, buyers, listings | sellers, buyers, listings, orders |
| Logistics | logistics, shipping, drivers, routes | drivers, vehicles, routes, shipments |
| Pharma | pharma, clinical, trials | research_projects, timesheets |

No keyword match → generic single-table schema with a warning. Use `LLMSchemaGenerator` for custom domains.

---

## Run the examples

All examples produce real, impressive output:

```bash
python examples/saas_revenue_curve.py       # all 12 MRR targets hit exactly
python examples/fintech_fraud_detection.py  # FICO distribution, 2.00% fraud rate
python examples/healthcare_multi_table.py   # ABO/Rh blood types, 2 FK edges
python examples/ecommerce_seasonal.py       # seasonal curve, power-law amounts
```

---

## Next steps

- [README](README.md) — full API reference and architecture overview
- [docs/faker-vs-sdv-vs-misata.md](docs/faker-vs-sdv-vs-misata.md) — when to use each tool
- [docs/database-seeding-python.md](docs/database-seeding-python.md) — seeding guide
- [CHANGELOG.md](CHANGELOG.md) — what's new in each version
