# Multi-Table Synthetic Data in Python

Misata is built for multi-table synthetic data generation in Python.

If you need `customers`, `orders`, and `order_items` to line up correctly, Misata is designed for that kind of structure.

## What Matters In Multi-Table Data

A useful multi-table generator needs to do more than create isolated records.

It should:
- preserve foreign keys
- generate tables in dependency order
- size child tables realistically
- keep rows coherent across related entities

Misata focuses on exactly that.

## Example

```python
from misata import DataSimulator, SchemaConfig, Table, Column, Relationship

config = SchemaConfig(
    name="Retail Demo",
    tables=[
        Table(name="customers", row_count=1000),
        Table(name="orders", row_count=4000),
        Table(name="order_items", row_count=12000),
    ],
    columns={
        "customers": [
            Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 1000}, unique=True),
            Column(name="first_name", type="text", distribution_params={"text_type": "first_name"}),
            Column(name="last_name", type="text", distribution_params={"text_type": "last_name"}),
        ],
        "orders": [
            Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 4000}, unique=True),
            Column(name="customer_id", type="foreign_key", distribution_params={}),
            Column(name="order_date", type="date", distribution_params={"start": "2025-01-01", "end": "2025-12-31"}),
        ],
        "order_items": [
            Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 12000}, unique=True),
            Column(name="order_id", type="foreign_key", distribution_params={}),
            Column(name="quantity", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 5}),
        ],
    },
    relationships=[
        Relationship(parent_table="customers", child_table="orders", parent_key="id", child_key="customer_id"),
        Relationship(parent_table="orders", child_table="order_items", parent_key="id", child_key="order_id"),
    ],
)

for table_name, batch in DataSimulator(config).generate_all():
    print(table_name, len(batch))
```

## Related Examples

- [examples/multi_table_synthetic_data.py](/Users/muhammedrasin/misata-project/Misata/examples/multi_table_synthetic_data.py)
- [examples/python_synthetic_data_generator.py](/Users/muhammedrasin/misata-project/Misata/examples/python_synthetic_data_generator.py)

## Related Docs

- [FEATURES.md](/Users/muhammedrasin/misata-project/Misata/FEATURES.md)
- [README.md](/Users/muhammedrasin/misata-project/Misata/README.md)
