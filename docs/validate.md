# Validate

Profile any CSV file and optionally check it against a Misata schema. Useful for verifying that real data matches your expectations, or for auditing generated data before seeding.

## CLI

```bash
# Profile a CSV — type inference, null rates, range stats
misata validate customers.csv

# Check against a YAML schema
misata validate orders.csv --schema misata.yaml

# Parse a story into a schema and check against it
misata validate orders.csv --story "A SaaS company with an orders table"
```

Example output:

```
Validating 'customers' — 5,000 rows × 8 columns
──────────────────────────────────────────────────────────────────────
  Column                 Type          Nulls  Range / Values              Notes
  ────────────────────────────────────────────────────────────────────
  customer_id            int            0.0%  1 → 5000                    unique · schema ✓
  email                  text           0.2%  4989 unique                 0.2% nulls · schema ✓
  plan                   categorical    0.0%  free, pro, enterprise       schema ✓
  mrr                    float          0.0%  0.0 → 2399.8               schema ✓
  signup_date            date           0.0%  2022-01-03 → 2024-12-29    unique
  credit_score           int            1.1%  582 → 848                   1.1% nulls
  is_active              boolean        0.0%
  country                text           0.0%  94 unique
  ────────────────────────────────────────────────────────────────────

  Quality score: 94/100
  1 issue(s) found:
    · credit_score: 1.1% nulls — column may be mostly empty
```

## Python API

```python
import misata

# Profile only
report = misata.validate_csv("customers.csv")
print(report.score)         # 0–100
print(report.issues)        # list of strings
print(report)               # formatted table

# With a schema
schema = misata.load_yaml_schema("misata.yaml")
report = misata.validate_csv("customers.csv", schema=schema, table_name="customers")

# From a DataFrame directly
import pandas as pd
df = pd.read_csv("customers.csv")
report = misata.validate_csv(df, table_name="customers")
```

## Report attributes

| Attribute | Type | Description |
|:--|:--|:--|
| `score` | `int` | Quality score 0–100. Deductions for nulls >50%, type mismatches, uniqueness violations |
| `rows` | `int` | Number of rows in the CSV |
| `columns` | `list[dict]` | Per-column stats: name, type, nulls, range, notes |
| `issues` | `list[str]` | Human-readable list of detected problems |
