# Faker vs SDV vs Misata: Choosing the Right Python Synthetic Data Tool

Generating synthetic data in Python means picking from three very different tools:
**Faker**, **SDV**, and **Misata**. Each solves a distinct problem. This page shows
the difference with working code so you can pick the right one in under five minutes.

---

## Quick comparison

| Feature | Faker | SDV | Misata |
|---|---|---|---|
| Multi-table relational output | ✗ | ✓ (limited) | **✓ (Topological DAG)** |
| Referential integrity (FK) | Manual (broken) | ✓ | **✓ (0 orphan keys guaranteed)** |
| Cross-column coherence (dates, math, geo) | ✗ | Partial | **✓ (Provable causality)** |
| Text column realism | ✗ (Lorem Ipsum / canned) | ✗ (Static tokens) | **✓ (15+ domain microtext pools)** |
| Vectorized speed | ~10k rows/s | ~5k rows/s | **500k – 16M rows/s (100x+ faster)** |
| Direct text enrichment (`enrich_text`) | ✗ | ✗ | **✓ (Series, DF, or array)** |
| Plain-English story → schema | ✗ | ✗ | **✓** |
| Exact aggregate targets (MRR, fraud rate) | ✗ | ✗ | **✓ ($0.00 error)** |
| No real data required | ✓ | ✗ (needs training data) | **✓** |
| Domain-realistic distributions | Partial | ✓ | **✓** |
| Database seeding (SQLAlchemy / Postgres) | Manual | ✗ | **✓ (Instant sandbox)** |
| Outcome curves / scenario events | ✗ | ✗ | **✓** |
| LLM-powered schema generation | ✗ | ✗ | **✓** |
| Reproducible seed | ✓ | ✓ | **✓ (Deterministic)** |
| Install size | Small | Large (~1 GB w/ deps) | **Medium** |

---

## Faker: row-level mock data from 2012

Faker was built over a decade ago for single-attribute unit test mocks (`fake.name()`, `fake.email()`). It was never designed for relational databases, analytics pipelines, AI agent evaluation, or realistic domain applications.

```python
from faker import Faker
fake = Faker()

# One row of isolated user data
print(fake.name())         # "Patricia Mueller"
print(fake.email())        # "tricia23@example.net"
print(fake.text())         # "Lorem ipsum dolor sit amet consectetur..."
```

**Where Faker fails catastrophically in 2026:**

1. **Relational Blindness & Orphan Keys**: Faker generates values one by one in Python loops. It has no topological ordering, no foreign key graphs, and no multi-table coordination.
```python
# The painful Faker loop — manual glue code with frequent orphan keys:
customers = [{"id": i, "email": fake.email()} for i in range(1000)]
orders = [
    {
        "order_id": j,
        "customer_id": random.randint(0, 999),  # Fragile: no guarantee of integrity
        "amount": round(random.uniform(10, 500), 2),
    }
    for j in range(5000)
]
```

2. **Cross-Column Incoherence**: Faker does not know that a user's email should match their name, their city must belong to their country, or their salary should match their job title.
3. **Temporal Paradoxes & Math Errors**: Faker will gladly set `order_date` after `shipped_date`, or generate line items whose sum does not equal `total_amount`.
4. **"Lorem Ipsum" Text**: When asked for a product description, customer support ticket, medical note, or error message, Faker generates Latin gibberish that renders modern analytics, demos, and AI evaluation useless.
5. **Slow Python Loops**: Faker averages 5,000–15,000 values/second. Misata's vectorized NumPy engine generates 500,000 to 16,000,000 rows/second.

**The modern replacement:** Use Misata. If you just need to enrich an existing DataFrame or Series with domain text, call `misata.enrich_text(df)`. If you need multi-table datasets, call `misata.generate(...)`.

---

## SDV (Synthetic Data Vault): statistical models from real data

SDV learns statistical patterns from your actual data and generates synthetic rows
that match those patterns. It handles single tables, conditional sampling, and some
relational modeling.

```python
from sdv.tabular import GaussianCopula

# SDV requires your real data to fit a model
model = GaussianCopula()
model.fit(real_customers_df)          # ← needs real data

synthetic = model.sample(num_rows=1000)
```

**Where SDV falls short:**

- You must have real data to train from, no real data, no model.
- Exact business rules ("fraud rate must be exactly 2%") cannot be pinned.
- Install pulls in PyTorch, CUDA libs, and ~1 GB of dependencies.
- Multi-table relational support is limited; deep FK chains require significant
  configuration.

**Use SDV when:** you have real data you cannot use directly (privacy concerns),
and you want statistically faithful synthetic copies of it.

---

## Misata: story-driven relational synthetic data

Misata generates multi-table datasets from plain-English descriptions. No real data
required. Referential integrity is guaranteed. Business constraints (fraud rates,
MRR targets, churn percentages) are pinned exactly.

```python
import misata

# One line — no real data, no model training, no FK wiring
tables = misata.generate("A fintech company with 2000 customers and banking transactions.", seed=42)

customers    = tables["customers"]     # 2,000 rows
accounts     = tables["accounts"]      # ~4,000 rows
transactions = tables["transactions"]  # ~20,000 rows

# Referential integrity is automatic
assert (~transactions["account_id"].isin(accounts["account_id"])).sum() == 0
```

### Exact aggregate pinning

```python
schema = misata.parse(
    "A SaaS company with 1000 users. "
    "MRR rises from $50k in January to $200k in December with a dip in September.",
    rows=1000,
)
tables = misata.generate_from_schema(schema)

# Monthly MRR sums match the targets exactly — not approximately
monthly = tables["subscriptions"].groupby(
    pd.to_datetime(tables["subscriptions"]["start_date"]).dt.month
)["mrr"].sum()

# Jan → $50,000.00  ✓
# Dec → $200,000.00 ✓
# All 12 months hit their targets to the cent
```

### Domain-realistic distributions out of the box

Misata ships calibrated priors for 7 domains. Healthcare blood-type frequencies
match real ABO/Rh statistics. Credit scores match real FICO distributions. MRR
follows a log-normal curve because real SaaS revenue is log-normal.

```python
# Healthcare — blood types follow real ABO/Rh frequencies (no config needed)
tables = misata.generate("A hospital with 500 patients and doctors.", seed=42)
patients = tables["patients"]

# O+: 38% real-world → ~38% generated  ✓
# A+: 34% real-world → ~34% generated  ✓
print(patients["blood_type"].value_counts(normalize=True).mul(100).round(1))
```

### Schema inspection before generation

```python
schema = misata.parse("An ecommerce store with 10k orders")
print(schema.summary())
# Schema: EcommerceDataset
# Domain: ecommerce
# Tables (2)
#   customers  10,000 rows  [customer_id, email, name, signup_date]
#   orders     60,000 rows  [order_id, customer_id, order_date, amount, status]
# Relationships (1)
#   customers.customer_id → orders.customer_id
```

**Use Misata when:** you need relational multi-table data with business logic,
exact aggregate targets, or domain-realistic distributions, and you don't want to
write schema config by hand.

---

## Side-by-side: the same task in each tool

**Task:** Generate 1,000 customers and 5,000 orders with referential integrity,
where order amounts follow a realistic right-skewed distribution.

### Faker

```python
import random
from faker import Faker

fake   = Faker()
ids    = list(range(1, 1001))
valid  = set(ids)

customers = [{"customer_id": i, "email": fake.email(), "name": fake.name()} for i in ids]

# Manual FK wiring — you're responsible for this
orders = [
    {
        "order_id":    j,
        "customer_id": random.choice(ids),             # could be any id
        "amount":      round(random.lognormvariate(4, 0.8), 2),  # lognormal by hand
        "order_date":  fake.date_between("-2y", "today"),
    }
    for j in range(1, 5001)
]

# No integrity guarantee — you'd need to assert this yourself
```

~30 lines. You wrote the distribution, the FK logic, and the date range manually.

### SDV

```python
# SDV requires real data — this task cannot be completed from scratch.
# You would need real customer and order tables to fit the model first.
```

Not applicable without a real dataset to train from.

### Misata

```python
import misata

tables    = misata.generate("An ecommerce store with 1000 customers and orders.", seed=42)
customers = tables["customers"]   # 1,000 rows, realistic email/name/signup_date
orders    = tables["orders"]      # 5,000+ rows, right-skewed amounts

# FK integrity is guaranteed — no assertion needed, but it holds:
assert (~orders["customer_id"].isin(customers["customer_id"])).sum() == 0
```

3 lines. Referential integrity, realistic distributions, and reproducibility included.

---

## When to use each

| You want to… | Use |
|---|---|
| Generate fake names/emails/addresses for a form or test fixture | **Faker** |
| Create a statistical copy of your production database (use DP if it must be private) | **SDV** |
| Build a realistic multi-table dataset from scratch (no real data) | **Misata** |
| Seed a test database with consistent relational data | **Misata** |
| Pin exact KPIs (fraud rate, churn %, MRR targets) in generated data | **Misata** |
| Generate data for BI demos, load testing, or ML training | **Misata** |
| Learn distributions from existing data | **SDV** |
| One-off fake value in a script | **Faker** |

---

## Installation

```bash
# Faker
pip install faker

# SDV (large, requires Python 3.8–3.11)
pip install sdv

# Misata (no real data required)
pip install misata

# Misata with LLM-powered schema generation
pip install "misata[llm]"
```

---

## Related

- [Multi-table synthetic data in Python](multi-table-synthetic-data.md)
- [Database seeding with Python](database-seeding-python.md)
- [Synthetic data for BI demos](synthetic-data-for-bi-demos.md)
- [Python synthetic data generator guide](python-synthetic-data-generator.md)
