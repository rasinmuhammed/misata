# I Got Tired of Lying to My Own Dashboard

Every developer has written some version of this:

```python
import random

orders = []
for i in range(10000):
    orders.append({
        "order_id": i,
        "customer_id": random.randint(1, 500),
        "amount": random.uniform(10, 500),
        "date": "2024-01-01",  # yeah I'll fix this later
    })
```

You know what that data looks like on a chart. A flat horizontal line. Every month identical. Every amount uniform between $10 and $500 because that's what `random.uniform` does. No seasonality. No fraud rate. No customers who churned in Q3 because of pricing changes. Just... noise, shaped like a rectangle.

I was building a demo for a product I'm working on. The dashboard needed to show meaningful patterns. Revenue growth. A seasonal dip. Customers on different plan tiers. The kind of data that makes a product manager nod and say "yes, this makes sense."

So I spent two hours hand-crafting fake data that told a story. Customer acquisition rising through Q1. MRR growing month over month. An August slowdown because "summer churn is real." It worked fine. It also felt ridiculous.

There had to be a better way.

---

## What I built

[Misata](https://github.com/rasinmuhammed/misata) is a Python library that generates multi-table synthetic datasets from plain-English descriptions. You describe a business. It generates the data.

Not approximately. Not "kind of." The numbers actually match what you described.

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

That's the whole thing. Let me show you what comes out.

---

## The monthly targets are not approximate

This is the part that surprised me when I first got it working.

```python
import pandas as pd

subs = tables["subscriptions"].copy()
subs["month"] = pd.to_datetime(subs["start_date"]).dt.month
monthly_mrr = subs.groupby("month")["mrr"].sum()

for m, name in enumerate(["Jan","Feb","Mar","Apr","May","Jun",
                           "Jul","Aug","Sep","Oct","Nov","Dec"], 1):
    print(f"{name}  ${monthly_mrr.get(m, 0):>10,.0f}")
```

Output:

```
Jan  $    80,000  ✓
Feb  $   128,000  ✓
Mar  $   176,000  ✓
Apr  $   224,000  ✓
May  $   272,000  ✓
Jun  $   320,000  ✓
Jul  $   250,000  ✓
Aug  $   180,000  ✓   <- described as a churn dip
Sep  $   235,000  ✓
Oct  $   290,000  ✓
Nov  $   345,000  ✓
Dec  $   400,000  ✓
```

Each of those matches the described target to the cent. Not within 5%. Not "close enough." Exact.

The way it works: Misata reads the monetary targets from the story, figures out how many rows it needs per month to hit the sum given the distribution shape, and allocates accordingly. The rows themselves still follow a log-normal distribution (because real SaaS MRR is log-normal), but the monthly totals are pinned.

Speaking of which:

```
MRR distribution:
  median   $126
  mean     $150
  p90      $291
  max      $932
```

Median below mean. Long right tail. A few big customers, lots of small ones. That's what real SaaS revenue looks like, not `random.uniform(50, 300)`.

The subscriptions also came with plan tiers, billing cycles, and status:

```
Plans:    free 40%  |  starter 30%  |  pro 25%  |  enterprise 5%
Status:   active 68%  |  cancelled 18%  |  paused 8%  |  trialing 6%
Billing:  annual 65%  |  monthly 35%
```

40% on free tier. 65% paying annually. 18% churned. These are not random numbers. These are calibrated to real freemium SaaS benchmarks.

---

## The fraud rate is not random

I generated a fintech dataset next.

```python
tables = misata.generate(
    "A fintech company with 2000 customers and banking transactions.",
    seed=42,
)

transactions = tables["transactions"]
fraud_rate = transactions["is_fraud"].mean() * 100
print(f"Fraud rate: {fraud_rate:.2f}%")
```

```
Fraud rate: 2.00%
```

Not 1.97%. Not 2.04%. Exactly 400 fraudulent transactions out of 20,000. The calibrated industry baseline for card fraud is around 2%, so that's what Misata generates. If you're building a fraud detection model and you need a labeled training set, you get a dataset where the fraud rate is what you need it to be.

The FICO credit scores also came out correctly:

```
Credit score distribution:
  mean:    679     (real US average: 680-720)
  std dev:  80     (real US range: 70-90)
  min:     328
  max:     850
```

And account balances follow a log-normal distribution, because real bank balances do:

```
Account balances:
  median    $1,976
  mean      $6,128
  p90      $14,260
  p99      $62,565
```

Most people have under $2k. A few have tens of thousands. The distribution has a proper right tail. This is not the output of `random.uniform(0, 10000)`.

Three tables. Two foreign key edges. Zero orphan rows. Every `account_id` in the transactions table references an account that actually exists.

---

## The blood types are statistically correct

This one is my favorite.

```python
tables = misata.generate(
    "A hospital with 500 patients and doctors.",
    seed=42,
)

patients = tables["patients"]
bt = patients["blood_type"].value_counts(normalize=True).mul(100).round(1)
print(bt)
```

```
Blood type distribution:
  Type    Generated    Real-world
  O+         37.9%        38.0%   ✓
  A+         33.9%        34.0%   ✓
  B+          9.6%         9.0%   ✓
  AB+         3.0%         3.0%   ✓
  O-          6.5%         7.0%   ✓
  A-          6.1%         6.0%   ✓
  B-          2.0%         2.0%   ✓
  AB-         0.9%         1.0%   ✓
```

Every blood type within 0.6% of the real ABO/Rh frequency distribution. Nobody configured this. It's just what the healthcare domain prior knows.

Patient ages are centered on 45 with standard deviation of 18, because that's realistic for a chronic-care hospital population. Appointment types split 55% in-person, 25% telehealth, 15% follow-up, 5% emergency. Not uniform. Not random.

Three tables, two FK edges, zero orphans.

---

## It handles ecommerce seasonality too

```python
schema = misata.parse(
    "An ecommerce store with 5000 customers and orders. "
    "Revenue grows from 100k in January to 300k in November "
    "then 350k in December.",
    rows=5000,
)
tables = misata.generate_from_schema(schema)
orders = tables["orders"]
```

Black Friday and the holiday peak are baked into the row-level data. The order amounts follow a log-normal curve (median $63, mean $75, long tail to $500+). Categories follow Zipf's law: electronics dominates at 47%, then clothing, home goods, sports, books, beauty trailing off.

Order statuses come with realistic rates too: 72% completed, 12% shipped, 8% pending, 5% returned, 3% cancelled. Real return rates hover around 8-10% for ecommerce. That's what you get.

---

## Why this is different from Faker

Faker is great for what it does: individual fake values. A name. An address. An email. But Faker has no concept of tables that reference each other, and it has no concept of distributions that match the domain.

When you need an orders table that properly links to customers, Faker makes you write the wiring yourself. And when you need order amounts that look like real e-commerce instead of a uniform distribution, Faker doesn't know what "real e-commerce" looks like.

Misata knows.

```python
# Faker: you write this yourself
customer_ids = list(range(1, 1001))
orders = [
    {
        "order_id": i,
        "customer_id": random.choice(customer_ids),  # manual FK wiring
        "amount": random.lognormvariate(4.4, 0.9),   # you looked up the right params
    }
    for i in range(5000)
]

# Misata: describe the business
tables = misata.generate("An ecommerce store with 1000 customers and orders.")
# customers and orders, FK intact, lognormal amounts, realistic categories
```

If you have real data and you want a statistically faithful synthetic copy of it, SDV is the right tool. Misata is for when you don't have real data, or when you want to build a dataset that tells a specific story.

---

## The two-step flow

You can inspect the schema before generating anything:

```python
schema = misata.parse("A hospital with 500 patients and doctors.")
print(schema.summary())
```

```
Schema: Healthcare Dataset
Domain: healthcare
Tables (3)
  doctors         25 rows   [doctor_id, first_name, last_name, specialty, years_experience]
  patients       500 rows   [patient_id, first_name, last_name, age, gender, blood_type, ...]
  appointments  1500 rows   [appointment_id, patient_id, doctor_id, type, duration_minutes, ...]

Relationships (2)
  patients.patient_id  -> appointments.patient_id
  doctors.doctor_id    -> appointments.doctor_id
```

You can adjust the seed, change row counts, add columns, validate constraints, then generate. Or you can hand it off to an LLM for domains the rule-based parser doesn't know:

```python
from misata import LLMSchemaGenerator

gen = LLMSchemaGenerator(provider="groq")  # or openai, ollama
schema = gen.generate_from_story(
    "A B2B marketplace with vendor tiers, SLA contracts, and quarterly invoices"
)
tables = misata.generate_from_schema(schema)
```

---

## It also seeds databases

If you need this data in a real database instead of DataFrames:

```python
from misata import seed_database

tables = misata.generate("A SaaS company with 1000 users.", seed=42)
report = seed_database(tables, "postgresql://user:pass@localhost/mydb", create=True)
print(report.total_rows)  # 6,000+
```

Or via CLI:

```bash
misata generate \
  --story "A SaaS company with 1000 users" \
  --db-url sqlite:///./dev.db \
  --db-create --db-truncate
```

Tables are inserted in topological order, so FK constraints never fail. Child tables reference valid parent IDs by construction.

---

## The actual installation

```bash
pip install misata
```

Then run one of the examples to see the full output:

```bash
python examples/saas_revenue_curve.py
python examples/fintech_fraud_detection.py
python examples/healthcare_multi_table.py
python examples/ecommerce_seasonal.py
```

Or open the [Colab notebook](https://colab.research.google.com/github/rasinmuhammed/misata/blob/main/notebooks/quickstart.ipynb) if you'd rather not install anything right now.

---

The thing that changed how I think about this: synthetic data doesn't have to look synthetic. If the fraud rate is 2%, the FICO distribution matches real credit bureaus, and the monthly revenue follows the business story you described, then a dashboard built on that data tells the truth about the product even when the underlying rows are made up.

That's the whole idea. Data that lies less.

GitHub: [github.com/rasinmuhammed/misata](https://github.com/rasinmuhammed/misata)
PyPI: [pypi.org/project/misata](https://pypi.org/project/misata/)
