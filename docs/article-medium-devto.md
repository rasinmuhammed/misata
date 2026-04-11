# The Best Python Library for Generating Synthetic Data in 2025

Generating synthetic data in Python used to mean one of three things: write `random.uniform()` loops by hand, use Faker for fake names and emails, or spend a week configuring SDV on top of real data you might not even have.

Misata is none of those things.

One sentence in. Multiple related tables out. Distributions calibrated to real-world statistics. Foreign key integrity guaranteed. Monthly revenue targets hit to the cent.

```bash
pip install misata
```

```python
import misata

tables = misata.generate(
    "A SaaS company with 2000 users. "
    "MRR rises from 80k in January to 320k in June, "
    "drops to 180k in August due to churn, "
    "then recovers to 400k in December.",
    seed=42,
)
```

That generates two linked tables with 21,000+ rows. Here is what the monthly MRR looks like when you sum the rows:

```
Jan    $80,000   ✓
Feb   $128,000   ✓
Mar   $176,000   ✓
Apr   $224,000   ✓
May   $272,000   ✓
Jun   $320,000   ✓
Jul   $250,000   ✓
Aug   $180,000   ✓   <- churn dip, as described
Sep   $235,000   ✓
Oct   $290,000   ✓
Nov   $345,000   ✓
Dec   $400,000   ✓
```

Every target exact. Not approximate. The individual rows still follow a log-normal distribution (median MRR $126, mean $150, p90 $291) because that is what real SaaS revenue looks like. But the monthly totals are pinned to whatever story you gave it.

---

## Why distributions matter more than people think

Most fake data generators produce values that are uniformly distributed. When you plot them, everything looks flat. Real business data is never flat.

Misata ships calibrated distribution priors for seven domains. Here is what that means in practice.

**Fintech: fraud rate and credit scores**

```python
tables = misata.generate(
    "A fintech company with 2000 customers and banking transactions.",
    seed=42,
)

transactions = tables["transactions"]
print(f"Fraud rate: {transactions['is_fraud'].mean() * 100:.2f}%")
```

```
Fraud rate: 2.00%
```

400 fraudulent transactions out of 20,000. The calibrated real-world baseline for card fraud is around 2%. That is what you get. Not a random number. A calibrated one.

Credit scores:

```
mean:   679   (real US average: 680-720)
std:     80   (real range: 70-90)
min:    328
max:    850
```

Account balances follow log-normal because real bank balances do:

```
median     $1,976
mean       $6,128
p90       $14,260
p99       $62,565
```

Most customers have under two thousand dollars. A few have tens of thousands. The tail is real.

**Healthcare: blood type frequencies**

```python
tables = misata.generate("A hospital with 500 patients and doctors.", seed=42)
patients = tables["patients"]
```

```
Blood type    Generated    Real-world
O+               37.9%        38.0%   ✓
A+               33.9%        34.0%   ✓
B+                9.6%         9.0%   ✓
AB+               3.0%         3.0%   ✓
O-                6.5%         7.0%   ✓
A-                6.1%         6.0%   ✓
B-                2.0%         2.0%   ✓
AB-               0.9%         1.0%   ✓
```

All eight blood types within 0.6% of the actual ABO/Rh frequency distribution. Patient ages center on 45 with a standard deviation of 18, matching a chronic-care hospital population. Nobody configured any of this. It is what the healthcare domain prior knows.

**Ecommerce: Zipf categories, seasonal peaks**

```python
schema = misata.parse(
    "An ecommerce store with 5000 customers and orders. "
    "Revenue grows from 100k in January to 300k in November "
    "then 350k in December.",
    rows=5000,
)
tables = misata.generate_from_schema(schema)
```

Product categories follow Zipf's law because that is how real shopping behavior works:

```
electronics      47.1%
clothing         20.0%
home & garden    12.3%
sports            8.7%
books             6.5%
beauty            5.5%
```

One category dominates. The rest trail off. Uniform would give you ~17% each. Real shopping does not look like that.

Order statuses come with realistic rates:

```
completed    71.5%
shipped      12.4%
pending       8.2%
returned      5.0%
cancelled     3.0%
```

Real e-commerce return rates are 8-10%. That is what gets generated.

---

## Referential integrity across all tables

Every child table samples foreign key values from the actual parent pool. This means zero orphan rows by construction, not by luck.

```python
tables = misata.generate(
    "A fintech company with 2000 customers and banking transactions.",
    seed=42,
)

customers    = tables["customers"]     # 2,000 rows
accounts     = tables["accounts"]      # 2,600 rows
transactions = tables["transactions"]  # 20,000 rows

# Both FK edges hold
orphan_accounts = (~accounts["customer_id"].isin(customers["customer_id"])).sum()
orphan_txns     = (~transactions["account_id"].isin(accounts["account_id"])).sum()

print(orphan_accounts)  # 0
print(orphan_txns)      # 0
```

Tables are generated in topological dependency order. Parents first. Children sample from the completed parent pool. It cannot produce orphans.

---

## The two-step flow for more control

When you want to inspect the schema before committing to generation:

```python
schema = misata.parse("A hospital with 500 patients and doctors.")
print(schema.summary())
```

```
Schema: Healthcare Dataset
Domain: healthcare
Tables (3)
  doctors         25 rows    [doctor_id, first_name, last_name, specialty, years_experience]
  patients       500 rows    [patient_id, name, age, gender, blood_type, registered_at]
  appointments  1500 rows    [appointment_id, patient_id, doctor_id, type, duration_minutes]

Relationships (2)
  patients.patient_id  -> appointments.patient_id
  doctors.doctor_id    -> appointments.doctor_id
```

Adjust the seed, add columns, change row counts. Then generate.

---

## How it compares to Faker and SDV

**Faker** generates individual fake values. One row at a time. It has no concept of tables that reference each other and no domain-specific distributions. Wiring foreign keys and getting log-normal amounts is your job.

**SDV** learns patterns from real data and generates synthetic copies. It requires actual training data, pulls in heavy ML dependencies, and cannot pin specific business targets like "fraud rate must be 2%."

**Misata** generates from a description. No real data required. No ML training. Distributions are calibrated to domain knowledge. Business targets are exact.

| | Faker | SDV | Misata |
|---|:---:|:---:|:---:|
| Multi-table FK integrity | No | Partial | Yes |
| No real data needed | Yes | No | Yes |
| Calibrated domain distributions | No | Learned | Yes |
| Exact monthly aggregate targets | No | No | Yes |
| Plain-English story input | No | No | Yes |
| Database seeding | Manual | No | Yes |

---

## Database seeding

The generated DataFrames can go directly into any database:

```python
from misata import seed_database

tables = misata.generate("A SaaS company with 1000 users.", seed=42)
report = seed_database(tables, "postgresql://user:pass@localhost/mydb", create=True)
print(report.total_rows)
```

Or from the CLI:

```bash
misata generate \
  --story "A SaaS company with 1000 users" \
  --db-url sqlite:///./dev.db \
  --db-create --db-truncate
```

---

## LLM-powered generation for custom domains

The rule-based parser covers SaaS, ecommerce, fintech, healthcare, marketplace, logistics, and pharma. For anything outside those domains:

```python
from misata import LLMSchemaGenerator

gen    = LLMSchemaGenerator(provider="groq")   # or openai, ollama
schema = gen.generate_from_story(
    "A B2B marketplace with vendor tiers, SLA contracts, and quarterly invoices"
)
tables = misata.generate_from_schema(schema)
```

Requires `GROQ_API_KEY` or `OPENAI_API_KEY`. Retries automatically on rate limits.

---

## Run the examples

All of these produce full verified output in under 3 seconds:

```bash
pip install misata pandas numpy

python examples/saas_revenue_curve.py
python examples/fintech_fraud_detection.py
python examples/healthcare_multi_table.py
python examples/ecommerce_seasonal.py
```

Or open the [Colab notebook](https://colab.research.google.com/github/rasinmuhammed/misata/blob/main/notebooks/quickstart.ipynb) and run it without installing anything.

---

Misata is open source, MIT licensed, and available now.

GitHub: [github.com/rasinmuhammed/misata](https://github.com/rasinmuhammed/misata)
PyPI: [pypi.org/project/misata](https://pypi.org/project/misata/)
Docs: [QUICKSTART.md](https://github.com/rasinmuhammed/misata/blob/main/QUICKSTART.md)
