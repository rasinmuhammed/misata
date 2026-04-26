---
title: "Mimic Mode — Privacy-Safe Synthetic Twins from Real CSV Files"
description: "Analyze any CSV and generate a statistically matching synthetic dataset without retaining real values. Perfect for GDPR compliance, ML training data, and staging environments."
---

# Mimic Mode

Mimic mode takes a real CSV file (or DataFrame), analyzes every column's statistical fingerprint, and produces a fresh synthetic dataset that matches the original's structure — without reusing a single real value.

It's the fastest path from *"I have sensitive production data"* to *"I have safe, shareable synthetic data"*.

## Quickstart

```python
import misata

# From a CSV file
tables = misata.mimic("customers.csv")

# Scale to a different size
tables = misata.mimic("customers.csv", rows=100_000)

# From a DataFrame you already have
import pandas as pd
df = pd.read_csv("orders.csv")
synthetic = misata.mimic(df, rows=50_000)
```

## CLI

```bash
# Same number of rows as the source
misata mimic customers.csv

# Scale up to 100 k rows, write to ./synthetic/
misata mimic orders.csv --rows 100000 --output ./synthetic

# Reproducible output
misata mimic data.csv --seed 42
```

## Multi-table

Pass a list of files. Each becomes its own synthetic table, named after the file stem:

```python
tables = misata.mimic(["customers.csv", "orders.csv", "products.csv"])
# tables["customers"], tables["orders"], tables["products"]
```

## How it works

For each column, Misata's `DataProfiler` runs a five-step analysis:

| Step | What it does |
|---|---|
| **Type detection** | Identifies boolean, date, integer, float, or text |
| **Distribution fitting** | Fits lognormal (right-skewed), normal, or uniform — whichever matches the data |
| **Cardinality check** | Low-cardinality columns become categoricals with real frequency weights |
| **Semantic inference** | Detects email, name, city, country, latitude, URL, phone, etc. |
| **Range capture** | Records min/max for numerics, start/end for dates |

None of the original values are stored or emitted. The profiler only retains statistical parameters.

## Distribution fitting logic

```
if all values > 0 AND skew > 1.0:
    → lognormal (mu, sigma from log-space moments)
elif cardinality < 5% of rows AND unique values < 200:
    → categorical with observed frequencies
else:
    → normal (mean, std)
```

## Supported column types

| Source column | What Misata generates |
|---|---|
| `email` | Realistic email addresses (never real ones) |
| `first_name` / `last_name` | Diverse synthetic names |
| `city`, `country`, `state` | Real place names from vocab |
| `latitude` / `longitude` | Coordinates clustered around real cities |
| `postal_code` / `zip` | Format-correct postal codes |
| Dates | Dates within the observed range |
| Booleans | Same true/false ratio |
| Low-cardinality text | Category distribution preserved |
| High-cardinality text | Semantic type inferred and regenerated |

## Reproducibility

```python
# Same seed → identical output every run
tables = misata.mimic("customers.csv", rows=10_000, seed=42)
```

## When to use mimic vs. `generate`

| Situation | Use |
|---|---|
| You have a real schema to copy | `mimic()` |
| You want to describe a dataset from scratch | `generate()` |
| You need relational FK integrity across tables | `generate()` with relationships |
| You need to match an existing DB's distributions | `mimic()` with multiple CSVs |

## API reference

```python
misata.mimic(
    source,          # str | Path | pd.DataFrame | list of those
    rows=None,       # int — defaults to same count as source
    seed=None,       # int — for reproducibility
    table_name="table",  # str — used when source is a DataFrame
) -> dict[str, pd.DataFrame]
```
