---
title: "Column Correlations — Make Age Correlate with Salary, Experience with Level"
description: "Enforce Pearson correlations between numeric columns using the Iman-Conover method. Preserves marginal distributions while imposing realistic statistical relationships."
---

# Column Correlations

Real-world data has structure: older employees tend to earn more, high-traffic pages tend to have more conversions, longer delivery times tend to lower customer ratings. Misata's correlation engine lets you declare these relationships explicitly — and enforces them without distorting the marginal distributions you already configured.

## How to declare correlations

Add a `correlations` list to any `Table`:

```python
from misata.schema import SchemaConfig, Table, Column

schema = SchemaConfig(
    name="HR Dataset",
    tables=[
        Table(
            name="employees",
            row_count=5000,
            correlations=[
                {"col_a": "age",        "col_b": "salary",          "r": 0.65},
                {"col_a": "tenure",     "col_b": "salary",          "r": 0.55},
                {"col_a": "age",        "col_b": "tenure",          "r": 0.70},
                {"col_a": "performance","col_b": "bonus_multiplier", "r": 0.80},
            ],
        )
    ],
    columns={"employees": [
        Column(name="age",              type="int",   distribution_params={"distribution": "normal", "mean": 38, "std": 10, "min": 22, "max": 65}),
        Column(name="salary",           type="float", distribution_params={"distribution": "lognormal", "mu": 11.0, "sigma": 0.4, "min": 35000, "decimals": 0}),
        Column(name="tenure",           type="float", distribution_params={"distribution": "exponential", "scale": 4.0, "min": 0.0, "max": 30.0, "decimals": 1}),
        Column(name="performance",      type="float", distribution_params={"distribution": "beta", "a": 5.0, "b": 2.0, "min": 1.0, "max": 5.0, "decimals": 2}),
        Column(name="bonus_multiplier", type="float", distribution_params={"distribution": "beta", "a": 3.0, "b": 2.0, "min": 0.5, "max": 3.0, "decimals": 2}),
    ]},
    relationships=[],
)
```

## The `r` parameter

`r` is the target Pearson correlation coefficient, ranging from -1.0 to 1.0:

| Value | Meaning |
|---|---|
| `1.0` | Perfect positive correlation |
| `0.7` | Strong positive correlation |
| `0.4` | Moderate positive correlation |
| `0.0` | No correlation (independent) |
| `-0.4` | Moderate negative correlation |
| `-0.7` | Strong negative correlation |
| `-1.0` | Perfect negative correlation |

**What you get in practice:** Misata uses the Iman-Conover rank correlation method, which achieves the target correlation within ±0.03–0.05 of the declared value.

## How it works (Iman-Conover method)

Declaring correlations does **not** change your marginal distributions. The per-column `distribution` params are respected exactly. Instead, Misata:

1. Generates all columns independently (their distributions are preserved)
2. Builds a target correlation matrix from your declarations
3. Decomposes it with Cholesky factorization to generate correlated normal scores
4. Re-ranks each column's values to match the target rank structure

The result: `age` still follows your normal distribution, `salary` still follows your lognormal — but their *joint distribution* now reflects the declared correlation.

## Negative correlations

```python
Table(
    name="products",
    row_count=1000,
    correlations=[
        {"col_a": "price",         "col_b": "return_rate",   "r": -0.45},
        {"col_a": "review_score",  "col_b": "support_tickets","r": -0.60},
    ],
)
```

Higher-priced products tend to have fewer returns. Better-reviewed products generate fewer support tickets.

## Multiple correlations

You can declare as many pairs as you like. Misata builds a joint correlation matrix and enforces all of them simultaneously. The only constraint: the full matrix must be positive semi-definite (i.e. your correlations can't be logically contradictory — if A↑→B↑ and B↑→C↓, then A↑→C↓ must be consistent).

If the matrix is not positive-definite (contradictory spec), Misata skips correlation enforcement silently and generates independent columns.

## Common correlation patterns by domain

### E-commerce
```python
correlations=[
    {"col_a": "price",        "col_b": "rating",        "r": 0.35},
    {"col_a": "price",        "col_b": "return_rate",   "r": -0.40},
    {"col_a": "rating",       "col_b": "review_count",  "r": 0.60},
]
```

### SaaS
```python
correlations=[
    {"col_a": "mrr",          "col_b": "seats",         "r": 0.85},
    {"col_a": "tenure_months","col_b": "health_score",  "r": 0.45},
    {"col_a": "health_score", "col_b": "churn_risk",    "r": -0.75},
]
```

### Gaming
```python
correlations=[
    {"col_a": "total_hours",  "col_b": "level",         "r": 0.80},
    {"col_a": "level",        "col_b": "win_rate",      "r": 0.55},
    {"col_a": "total_hours",  "col_b": "spend",         "r": 0.65},
]
```
