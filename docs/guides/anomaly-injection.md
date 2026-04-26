---
title: "Anomaly Injection — Deliberate Outliers for ML Training and Alerting Tests"
description: "Inject statistical outliers into any numeric or categorical column at a configurable rate. Essential for fraud detection models, alerting systems, and anomaly detection benchmarks."
---

# Anomaly Injection

Real datasets contain anomalies — a transaction 10× the normal amount, a delivery time of 400 minutes, a sensor reading far outside its normal range. Misata lets you inject these deliberately so your ML models, alerting rules, and anomaly detectors have something to learn from.

## Usage

Add `anomaly_rate` to any column's `distribution_params`:

```python
from misata.schema import SchemaConfig, Table, Column

Column(name="transaction_amount", type="float", distribution_params={
    "distribution": "lognormal",
    "mu": 4.0, "sigma": 1.2,
    "min": 0.01, "max": 5000.0,
    "decimals": 2,
    "anomaly_rate": 0.02,   # 2% of rows will be outliers
})
```

## How outliers are generated

**Numeric columns:** Outlier values are injected at 3–6 standard deviations from the column mean, in a random direction (positive or negative). This matches the statistical definition of an outlier while keeping the magnitude realistic for the column's scale.

```
outlier_value = mean ± uniform(3.0, 6.0) × std
```

**Categorical / text columns:** Anomalous rows get the sentinel value `"__anomaly__"`. Downstream systems can detect and handle these explicitly.

## Typical anomaly rates by use case

| Use case | Recommended `anomaly_rate` |
|---|---|
| Fraud detection training | `0.01` – `0.05` (1–5%) |
| Sensor/IoT data | `0.005` – `0.02` |
| Financial transactions | `0.001` – `0.01` |
| Alerting system testing | `0.05` – `0.10` |
| Anomaly detection benchmarks | `0.10` – `0.20` |

## Full example: fraud dataset

```python
from misata.schema import SchemaConfig, Table, Column, Relationship

schema = SchemaConfig(
    name="Fraud Detection Dataset",
    tables=[
        Table(name="users",        row_count=5000),
        Table(name="transactions", row_count=50000),
    ],
    columns={
        "users": [
            Column(name="user_id",      type="int", unique=True, distribution_params={"min": 1, "max": 5001}),
            Column(name="account_age_days", type="int", distribution_params={
                "distribution": "lognormal", "mu": 6.0, "sigma": 1.2, "min": 1, "max": 3650,
            }),
            Column(name="avg_txn_amount", type="float", distribution_params={
                "distribution": "lognormal", "mu": 4.2, "sigma": 0.8, "min": 1.0, "decimals": 2,
            }),
        ],
        "transactions": [
            Column(name="txn_id",    type="int", unique=True, distribution_params={"min": 1, "max": 50001}),
            Column(name="user_id",   type="foreign_key"),
            Column(name="amount",    type="float", distribution_params={
                "distribution": "lognormal", "mu": 4.0, "sigma": 1.2,
                "min": 0.01, "max": 50000.0, "decimals": 2,
                "anomaly_rate": 0.02,   # 2% fraudulent high-value transactions
            }),
            Column(name="merchant_category", type="categorical", distribution_params={
                "choices": ["retail", "food", "travel", "entertainment", "crypto", "wire"],
                "probabilities": [0.40, 0.25, 0.15, 0.10, 0.06, 0.04],
                "anomaly_rate": 0.01,   # 1% with unexpected merchant type
            }),
            Column(name="status", type="categorical", distribution_params={
                "choices": ["approved", "declined", "pending"],
                "probabilities": [0.88, 0.09, 0.03],
            }),
            Column(name="txn_at", type="date", distribution_params={
                "start": "2023-01-01", "end": "2024-12-31",
            }),
        ],
    },
    relationships=[
        Relationship(parent_table="users", child_table="transactions",
                     parent_key="user_id", child_key="user_id"),
    ],
)

import misata
tables = misata.generate_from_schema(schema)

txns = tables["transactions"]
anomalies = txns[txns["amount"] > txns["amount"].mean() + 3 * txns["amount"].std()]
print(f"Flagged {len(anomalies)} high-value anomalies out of {len(txns)} transactions")
```

## Combining with `null_if`

Anomaly injection and conditional nulls compose naturally:

```python
Column(name="delivered_at", type="date", distribution_params={
    "after_column": "placed_at",
    "null_if": {"column": "status", "values": ["cancelled"]},
    "anomaly_rate": 0.01,   # 1% delivered suspiciously fast or slow
})
```
