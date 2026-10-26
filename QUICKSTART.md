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

print(tables["users"][["user_id", "name", "country", "signup_date", "churned"]].head(3))
#    user_id            name  country signup_date  churned
# 0      597  Olivier Durand  Germany  2023-04-20    False
# 1     1751   Robert Howard   France  2022-03-21    False
# 2     1809          Na Xie    Italy  2022-05-05    False

print(tables["subscriptions"][["subscription_id", "user_id", "plan", "mrr", "status"]].head(3))
#    subscription_id  user_id     plan    mrr     status
# 0              133      343  starter  28.43     paused
# 1               32       41  starter  56.37  cancelled
# 2              261       95     free   0.00  cancelled
```

No config files. No real data needed. Referential integrity is automatic.

---

## Core workflows

### 1. Story → DataFrames

```python
import misata

# One liner: picks domain, generates linked tables, applies realistic distributions
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
# Schema: Healthcare Dataset
# Domain: healthcare
# Tables: 3
# Total rows: 40,500
#
#   Table              Rows  Columns
#   -------------- --------  -------
#   doctors             500  doctor_id, first_name, last_name, specialty, years_experience
#   patients         10,000  patient_id, first_name, last_name, age, gender … (+2 more)
#   appointments     30,000  appointment_id, patient_id, doctor_id, appointment_date, status … (+2 more)
#
#   Relationships (2):
#     patients.patient_id → appointments.patient_id
#     doctors.doctor_id → appointments.doctor_id

# Adjust seed, then generate
schema.seed = 99
tables = misata.generate_from_schema(schema)
```

### 3. Exact aggregate targets (outcome curves)

Tell Misata what your numbers should sum to: it generates rows that hit those targets:

```python
schema = misata.parse(
    "A SaaS company with 1000 users. "
    "MRR rises from $50k in January to $200k in December with a dip in September.",
    rows=1000,
)
tables = misata.generate_from_schema(schema)

# Each month's MRR is its target to the cent: 50,000.00 in January rising to
# 200,000.00 in December, with September dipping to 111,363.64.
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

schema = misata.parse("A SaaS company with 1000 users", rows=1000)
report = seed_database(schema, "sqlite:///dev.db", create=True)
print(report.total_rows)   # 2200: 1,000 users and 1,200 subscriptions
```

The same call takes a PostgreSQL or MySQL URL. It inserts parents before
children in one transaction and refuses a table that already has rows unless
you pass `truncate=True` or `append=True`.

Or from the CLI:

```bash
misata generate \
  --story "A SaaS company with 1000 users" \
  --rows 1000 \
  --db-url sqlite:///./dev.db \
  --db-create
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

Seven of the 18 story domains; [docs/domains.md](docs/domains.md) lists them
all. A story that matches none gets a generic single-table schema. Write a
YAML schema, or use `LLMSchemaGenerator`, for anything custom.

---

## Run the examples

```bash
python examples/saas_revenue_curve.py       # all 12 MRR targets hit exactly
python examples/fintech_fraud_detection.py  # FICO-shaped credit scores, about 2% fraud
python examples/healthcare_multi_table.py   # ABO/Rh blood types, 2 FK edges
python examples/ecommerce_seasonal.py       # seasonal curve, power-law amounts
```

---

## Next steps

- [README](README.md): what Misata guarantees, the evidence, and twelve recipes
- [LANGUAGE.md](LANGUAGE.md): every declaration, what it guarantees and when it refuses
- [docs/guides/faker-vs-sdv-vs-misata.md](docs/guides/faker-vs-sdv-vs-misata.md): when to use each tool
- [docs/guides/database-seeding-python.md](docs/guides/database-seeding-python.md): seeding guide
- [CHANGELOG.md](CHANGELOG.md): what's new in each version
