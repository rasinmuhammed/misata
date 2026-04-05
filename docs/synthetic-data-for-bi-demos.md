# Synthetic Data for BI Demos

Misata is a strong fit for BI demo data because it can generate rows that add up to a story.

This matters when a dashboard needs to show:
- revenue growth over time
- a dip in a specific month
- a target split by product or region
- customer-level rows that still match the top-line numbers

## What Makes BI Demo Data Hard

Most generators create rows independently and hope the aggregates feel close enough.

Misata can work top-down:
- define the business target
- allocate rows by time bucket
- generate amounts that roll up correctly
- validate the final result

## Example

```python
from misata import DataSimulator, SchemaConfig, Table, Column, OutcomeCurve

config = SchemaConfig(
    name="BI Revenue Demo",
    seed=42,
    tables=[Table(name="sales", row_count=6000)],
    columns={
        "sales": [
            Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 6000}, unique=True),
            Column(name="sale_date", type="date", distribution_params={"start": "2025-01-01", "end": "2025-12-31"}),
            Column(name="revenue", type="float", distribution_params={"distribution": "uniform", "min": 25.0, "max": 500.0, "decimals": 2}),
        ]
    },
    outcome_curves=[
        OutcomeCurve(
            table="sales",
            column="revenue",
            time_column="sale_date",
            value_mode="absolute",
            avg_transaction_value=180.0,
            curve_points=[
                {"month": 1, "target_value": 50000},
                {"month": 2, "target_value": 65000},
                {"month": 3, "target_value": 80000},
                {"month": 4, "target_value": 90000},
                {"month": 5, "target_value": 105000},
                {"month": 6, "target_value": 115000},
                {"month": 7, "target_value": 125000},
                {"month": 8, "target_value": 135000},
                {"month": 9, "target_value": 95000},
                {"month": 10, "target_value": 150000},
                {"month": 11, "target_value": 175000},
                {"month": 12, "target_value": 200000},
            ],
        )
    ],
)

result = DataSimulator(config).generate_with_reports()
print(result.validation_report.summary())
```

## Related Examples

- [examples/bi_demo_dataset.py](/Users/muhammedrasin/misata-project/Misata/examples/bi_demo_dataset.py)

## Related Docs

- [FEATURES.md](/Users/muhammedrasin/misata-project/Misata/FEATURES.md)
- [README.md](/Users/muhammedrasin/misata-project/Misata/README.md)
