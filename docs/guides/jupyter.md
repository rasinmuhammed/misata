---
title: "Jupyter Magic — Generate Synthetic Data Inline in Notebooks"
description: "Load the %%misata cell magic to generate multi-table synthetic datasets directly inside Jupyter notebooks with zero boilerplate."
---

# Jupyter Magic

The `%%misata` cell magic lets you generate synthetic datasets from a plain-English story directly inside a Jupyter notebook — no imports, no schema objects, no boilerplate.

## Setup

Load the extension once per session (put it in your first cell):

```python
%load_ext misata.magic
```

To load automatically on every notebook startup, add it to your IPython profile:

```python
# ~/.ipython/profile_default/ipython_config.py
c.InteractiveShellApp.extensions = ["misata.magic"]
```

## Basic usage

```
%%misata
SaaS company with users, subscriptions, and monthly payments
```

After running, the following variables appear in your namespace:

- `_misata` — dict of all DataFrames
- `users_df`, `subscriptions_df`, `payments_df` — one variable per table

## Options

```
%%misata rows=5000 seed=42
fintech app with transactions, wallets, and fraud flags
```

| Option | Default | Description |
|---|---|---|
| `rows` | `1000` | Number of rows for the primary table |
| `seed` | `None` | Random seed for reproducibility |

## Example workflow

```
%%misata rows=2000 seed=123
food delivery app with restaurants, customers, couriers, and orders
```

```python
# Immediately available in the next cell:
orders_df.head()
```

```python
import matplotlib.pyplot as plt
orders_df["customer_rating"].hist(bins=20)
plt.title("Order Rating Distribution")
```

```python
# Check delivery time vs rating correlation
orders_df[["delivery_minutes", "customer_rating"]].corr()
```

## Rich output

The magic prints a summary table after generation:

```
[misata] Generating: "food delivery app with restaurants, customers..."  rows=2000
  → restaurants_df  (100 rows × 10 cols)
  → customers_df    (2000 rows × 8 cols)
  → couriers_df     (50 rows × 8 cols)
  → orders_df       (2000 rows × 13 cols)
  → order_items_df  (5000 rows × 7 cols)
```

Followed by an HTML table in Jupyter with table names, row counts, and column previews.

## Accessing the full dict

```python
# All tables in one place
for name, df in _misata.items():
    print(f"{name}: {df.shape}")
```

## Reproducibility

```
%%misata rows=500 seed=42
ecommerce store with products and orders
```

Same seed → identical output every time. Useful for notebook demos that need consistent results.

## Supported domains

All 12 built-in domains work with the magic: `saas`, `ecommerce`, `fintech`, `healthcare`, `marketplace`, `logistics`, `hr`, `social`, `realestate`, `fooddelivery`, `edtech`, `gaming`.

For open-ended stories, add `GROQ_API_KEY` to your environment and the magic will automatically use LLM-powered schema generation.
