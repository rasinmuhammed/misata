# Multi-Table Synthetic Data in Python

Most synthetic data tools generate rows one table at a time. That breaks the moment
you need two tables to reference each other. Misata is designed specifically for
multi-table relational generation.

## The problem with single-table generators

```python
# Faker approach — you write FK logic by hand
import random
from faker import Faker

fake = Faker()
customer_ids = list(range(1, 1001))

customers = [{"id": i, "email": fake.email()} for i in customer_ids]

# Nothing stops order.customer_id from referencing a non-existent customer
orders = [{"id": j, "customer_id": random.randint(1, 10000)} for j in range(5000)]
# ^ broken — 10x the valid range, no referential integrity enforced
```

Every relationship is your problem. Misata handles this automatically.

## One-liner multi-table generation

```python
import misata

# Story → multiple DataFrames with guaranteed FK integrity
tables = misata.generate("An ecommerce store with 1000 customers and orders.", seed=42)

customers = tables["customers"]  # 1,000 rows
orders    = tables["orders"]     # 5,000+ rows

# FK integrity is automatic — no orphans
assert (~orders["customer_id"].isin(customers["customer_id"])).sum() == 0
```

## Three-table chains

```python
tables = misata.generate(
    "A fintech company with 2000 customers and banking transactions.",
    seed=42,
)

# customers → accounts → transactions (two FK hops)
customers    = tables["customers"]     # 2,000 rows
accounts     = tables["accounts"]      # ~4,000 rows
transactions = tables["transactions"]  # ~20,000 rows

# Both FK edges hold
assert (~accounts["customer_id"].isin(customers["customer_id"])).sum() == 0
assert (~transactions["account_id"].isin(accounts["account_id"])).sum() == 0
```

## How it works

Misata generates tables in topological dependency order:

1. Parent tables are generated first (e.g. `customers`).
2. Primary key pools are collected.
3. Child tables sample FK columns from the parent pool — every value is valid by construction.
4. The process repeats depth-first down the relationship graph.

Circular dependencies are detected before generation starts and raise a clear error.

## 1M-row relational dataset

```python
tables = misata.generate(
    "A large retail company with 50000 customers, 5000 products, and 1 million orders.",
    seed=42,
)
# Generates in ~2 seconds
# regions:   10 rows
# categories: 20 rows
# customers: 50,000 rows
# products:   5,000 rows
# orders:  1,000,000 rows
# All FK edges intact
```

## Inspecting the schema first

```python
schema = misata.parse("A hospital with 500 patients and doctors.")
print(schema.summary())
# Schema: HealthcareDataset
# Domain: healthcare
# Tables (3)
#   doctors       25 rows  [doctor_id, name, specialty, department]
#   patients     500 rows  [patient_id, name, age, blood_type, ...]
#   appointments 1500 rows [appointment_id, patient_id, doctor_id, type, ...]
# Relationships (2)
#   patients.patient_id → appointments.patient_id
#   doctors.doctor_id   → appointments.doctor_id
```

## Building a schema manually

When you need precise control over every column:

```python
from misata import SchemaConfig, Table, Column, Relationship, DataSimulator
import pandas as pd

config = SchemaConfig(
    name="Retail Dataset",
    seed=42,
    tables=[
        Table(name="customers",   row_count=1_000),
        Table(name="orders",      row_count=5_000),
        Table(name="order_items", row_count=15_000),
    ],
    columns={
        "customers": [
            Column(name="customer_id", type="int",
                   distribution_params={"distribution": "uniform", "min": 1, "max": 1000},
                   unique=True),
            Column(name="email", type="text",
                   distribution_params={"text_type": "email"}),
            Column(name="signup_date", type="date",
                   distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
        ],
        "orders": [
            Column(name="order_id", type="int",
                   distribution_params={"distribution": "uniform", "min": 1, "max": 5000},
                   unique=True),
            Column(name="customer_id", type="foreign_key", distribution_params={}),
            Column(name="order_date", type="date",
                   distribution_params={"start": "2023-01-01", "end": "2024-12-31"}),
            Column(name="total", type="float",
                   distribution_params={"distribution": "lognormal", "mean": 4.5, "std": 0.8}),
        ],
        "order_items": [
            Column(name="item_id", type="int",
                   distribution_params={"distribution": "uniform", "min": 1, "max": 15000},
                   unique=True),
            Column(name="order_id", type="foreign_key", distribution_params={}),
            Column(name="quantity", type="int",
                   distribution_params={"distribution": "uniform", "min": 1, "max": 5}),
            Column(name="unit_price", type="float",
                   distribution_params={"distribution": "lognormal", "mean": 3.5, "std": 0.6}),
        ],
    },
    relationships=[
        Relationship(parent_table="customers",  child_table="orders",
                     parent_key="customer_id",  child_key="customer_id"),
        Relationship(parent_table="orders",     child_table="order_items",
                     parent_key="order_id",     child_key="order_id"),
    ],
)

sim    = DataSimulator(config)
tables = {name: pd.concat([tables.get(name, pd.DataFrame()), batch], ignore_index=True)
          if name in tables else batch
          for name, batch in sim.generate_all()}
```

## Performance

| Dataset size | Tables | Generation time |
|---|---|---|
| 10,000 rows | 2 | < 0.1 s |
| 100,000 rows | 3 | < 0.5 s |
| 1,000,000 rows | 5 | ~1.5 s |

## Related

- [Faker vs SDV vs Misata](faker-vs-sdv-vs-misata.md)
- [Database seeding with Python](database-seeding-python.md)
- [Python synthetic data generator](python-synthetic-data-generator.md)
