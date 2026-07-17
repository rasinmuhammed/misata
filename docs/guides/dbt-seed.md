---
title: dbt Seed Integration | Misata
description: Generate synthetic data and write CSV seed files directly into your dbt project with misata dbt-seed. One command, realistic test data in your warehouse.
---

# dbt Seed Integration

`misata dbt-seed` generates synthetic data and writes one CSV file per table directly into your dbt `seeds/` directory. Run `dbt seed` afterwards and your data is in the warehouse.

## Quick start: from your project's own contract

Run it bare inside a dbt project and Misata builds the schema from the properties YAML you already have:

```bash
cd my-dbt-project
misata dbt-seed      # reads models/**/*.yml and seeds/**/*.yml
dbt build            # seed + run + test — your own tests, passing
```

The translation is exact where it matters:

| Your dbt declaration | What Misata generates |
|:--|:--|
| `relationships` test | A foreign key with guaranteed integrity (zero orphans) |
| `accepted_values` test | A categorical column restricted to exactly those values |
| `unique` test | A unique column (sequential ids for keys) |
| `not_null` test | A column with no nulls |
| `data_type` | The matching column type; `date` columns are written date-only |
| No type declared | Semantic inference from the name (`email`, `*_date`, `first_name`, `amount`, …) |

Both the legacy inline test syntax and the dbt 1.9+ `arguments:` nesting are parsed. Tests Misata can't translate (`dbt_utils.*`, custom generic tests) are listed in the output rather than silently guessed at. If your project declares seeds, those are generated; otherwise the declared models are.

This is verified end-to-end against dbt-duckdb: on a jaffle-shop-style demo project, `dbt build` passes 24/24 tests, including model-level relationship tests, on data Misata generated from the schema.yml alone.

## Quick start: from a story

No dbt contract yet? Describe the data instead:

```bash
# Generate SaaS seed data into dbt's seeds directory
misata dbt-seed --story "A SaaS company with 1k users" --seeds-dir seeds/

# Then load into your warehouse
dbt seed
```

Output:

```
✓ users         — 1,000 rows → seeds/users.csv
✓ subscriptions — 1,200 rows → seeds/subscriptions.csv
✓ invoices      — 3,500 rows → seeds/invoices.csv

Run dbt seed to load 3 table(s) into your warehouse.
```

## Options

| Flag | Default | Description |
|:--|:--|:--|
| `--from-project` | auto | Build the schema from the dbt project's own properties YAML |
| `--story`, `-s` |: | Plain-English dataset description |
| `--config`, `-c` |: | Path to a `misata.yaml` schema file |
| `--seeds-dir` | `seeds/` | dbt seeds directory |
| `--rows`, `-n` | `1000` | Row count for the primary table |
| `--seed` | `42` | Random seed for reproducibility |
| `--force` | `False` | Overwrite existing CSV files |

## Use a YAML schema

For precise control over column types and distributions, point to a `misata.yaml`:

```bash
misata dbt-seed --config misata.yaml --seeds-dir dbt/seeds/ --rows 5000
```

## Recommended workflow

### 1. Generate seeds during development

```bash
# In your dbt project root
misata dbt-seed \
  --story "An ecommerce store with customers, products, and orders" \
  --seeds-dir seeds/ \
  --rows 2000
```

### 2. Add seeds to `dbt_project.yml`

```yaml
# dbt_project.yml
seeds:
  my_project:
    customers:
      +column_types:
        customer_id: bigint
        created_at: timestamp
    orders:
      +column_types:
        order_id: bigint
        amount: numeric(10,2)
```

### 3. Load into your warehouse

```bash
dbt seed
dbt run
dbt test
```

## Regenerating seeds

Seeds are reproducible, same `--seed` value produces identical data:

```bash
# Regenerate with the same data (idempotent)
misata dbt-seed --story "A SaaS company" --rows 1000 --seed 42 --force

# Generate a different dataset variant
misata dbt-seed --story "A SaaS company" --rows 1000 --seed 99 --force
```

## CI/CD integration

Generate seeds as part of your CI pipeline before running `dbt test`:

```yaml
# .github/workflows/dbt.yml
- name: Generate synthetic seed data
  run: |
    pip install misata
    misata dbt-seed \
      --story "An ecommerce store with customers and orders" \
      --seeds-dir seeds/ \
      --rows 500 \
      --force

- name: Run dbt
  run: |
    dbt seed
    dbt run
    dbt test
```

## Python API alternative

If you need more control, use the Python API directly:

```python
import misata
import pandas as pd
from pathlib import Path

tables = misata.generate("An ecommerce store with 2k customers", rows=2000, seed=42)

seeds_dir = Path("seeds/")
seeds_dir.mkdir(exist_ok=True)

for table_name, df in tables.items():
    df.to_csv(seeds_dir / f"{table_name}.csv", index=False)
    print(f"Written: {table_name}.csv ({len(df):,} rows)")
```

## Related

- [Database Seeding in Python](database-seeding-python.md), seed directly into a live database
- [SQL DDL to Schema](from-ddl.md), generate from your existing CREATE TABLE statements
- [Export](../export.md), Parquet, DuckDB, JSONL export options
