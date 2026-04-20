---
title: Synthetic Data for BI Demos — Realistic Dashboard Datasets in Python
description: Create compelling BI demo datasets with realistic trends, seasonality, and growth curves using Misata. Perfect for Tableau, Power BI, Looker, and Metabase demos.
---

# Synthetic Data for BI Demos

BI dashboards live or die by their data story. A chart that shows flat revenue or
perfectly uniform distributions looks fake in a demo. Misata lets you specify the
story — "revenue grows through the year, dips in September, peaks in December" — and
generates rows that actually sum to those targets.

## The problem with generic fake data in BI

Most synthetic data tools generate rows independently. If you ask for 6,000 sales
rows in 2024, you get uniform random amounts spread evenly across all 12 months.
That does not look like any real business.

Misata works top-down: define the aggregate shape, then generate rows that fill it.

## Exact monthly targets

```python
import misata

schema = misata.parse(
    "A SaaS company with 1000 users. "
    "MRR rises from $50k in January to $200k in December with a dip in September.",
    rows=1000,
)
tables = misata.generate_from_schema(schema)
subscriptions = tables["subscriptions"]

import pandas as pd
monthly = subscriptions.copy()
monthly["month"] = pd.to_datetime(monthly["start_date"]).dt.month
monthly_mrr = monthly.groupby("month")["mrr"].sum()

# Jan: $50,000  ✓
# Sep: dip      ✓
# Dec: $200,000 ✓
# All 12 months hit their targets to the cent
```

## Demo output

```
Month   Target MRR    Actual MRR   Match
─────  ────────────  ────────────  ─────
Jan    $     50,000  $     50,000      ✓
Feb    $     68,182  $     68,182      ✓
Mar    $     86,364  $     86,364      ✓
Apr    $    104,545  $    104,545      ✓
May    $    122,727  $    122,727      ✓
Jun    $    140,909  $    140,909      ✓
Jul    $    159,091  $    159,091      ✓
Aug    $    177,273  $    177,273      ✓
Sep    $    100,000  $    100,000      ✓  ← dip
Oct    $    163,636  $    163,636      ✓
Nov    $    181,818  $    181,818      ✓
Dec    $    200,000  $    200,000      ✓
```

All 12 monthly targets hit exactly.

## Realistic distributions (not uniform)

Real business data is never uniform. Misata applies domain-specific distributions
automatically:

```python
# Fintech — credit score matches real FICO statistics
tables = misata.generate("A fintech company with 2000 customers.", seed=42)
cs = tables["customers"]["credit_score"]

print(f"Mean: {cs.mean():.0f}")   # ~680–720 (real FICO range)
print(f"Std:  {cs.std():.0f}")    # ~70–90   (real FICO range)

# Transaction types follow Zipf's law (one type dominates naturally)
txn_types = tables["transactions"]["transaction_type"].value_counts(normalize=True)
# purchase    42%
# transfer    28%
# withdrawal  18%
# deposit     12%
```

## Healthcare dashboard data

```python
tables = misata.generate("A hospital with 500 patients and doctors.", seed=42)
patients = tables["patients"]

# Blood type distribution matches real ABO/Rh frequencies
bt = patients["blood_type"].value_counts(normalize=True).mul(100).round(1)
# O+   38%  (real: 38%)
# A+   34%  (real: 34%)
# B+    9%  (real:  9%)
# ...

# Age distribution: normal, centred on chronic-care population (mean ≈ 45)
print(patients["age"].mean())   # ≈ 44.7
print(patients["age"].std())    # ≈ 18.0
```

## Ecommerce seasonal curve

```python
schema = misata.parse(
    "An ecommerce store with 5000 customers and orders. "
    "Revenue grows from $100k in January to $300k in November "
    "then $350k in December.",
    rows=5000,
)
tables = misata.generate_from_schema(schema)

# Nov: $300,000 (Black Friday)  ✓
# Dec: $350,000 (Holiday peak)  ✓
```

## Fraud rate calibration

```python
tables = misata.generate(
    "A fintech company with 2000 customers and banking transactions.", seed=42
)
transactions = tables["transactions"]

fraud_rate = transactions["is_fraud"].mean() * 100
print(f"Fraud rate: {fraud_rate:.2f}%")  # 2.00% — calibrated, not random
```

## Connecting to BI tools

Generated DataFrames can be written directly to any database your BI tool connects to:

```python
from misata import seed_database

tables = misata.generate("A SaaS company with 5000 users.", seed=42)
seed_database(tables, "postgresql://user:pass@localhost/bi_demo", create=True)
```

Then point Tableau, Metabase, Looker, or Power BI at `postgresql://localhost/bi_demo`.
The data has a coherent story, realistic distributions, and proper FK relationships —
ready to demo without disclaimers.

## Running the examples

```bash
pip install misata
python examples/saas_revenue_curve.py
python examples/fintech_fraud_detection.py
python examples/healthcare_multi_table.py
python examples/ecommerce_seasonal.py
```

## Related

- [Python synthetic data generator](python-synthetic-data-generator.md)
- [Multi-table synthetic data](multi-table-synthetic-data.md)
- [Database seeding with Python](database-seeding-python.md)
