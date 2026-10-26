---
title: Known-Answer Tests for dbt Models
description: Generate dbt seeds whose correct output is declared before the data exists, so a model test can assert the exact number and catch the boundary bug that row counts miss.
---

# Known-answer tests for dbt models

A dbt test usually asserts that a column is unique or not null. It rarely
asserts that revenue is right, because nobody knows the right revenue for
test data. Here you declare it first: monthly revenue and the channel split
are part of the spec, so the model's correct output is known before a single
row is generated.

**Who:** analytics engineers testing models that aggregate.
**Time:** under a second to generate; `dbt build` adds about half a second.

## The declaration

```yaml
# misata.yaml
name: shop_revenue
seed: 11
tables:
  customers:
    rows: 400
    columns:
      customer_id: {type: int, unique: true, min: 1, max: 400}
      signed_up_at: {type: date, start: "2024-06-01", end: "2024-12-31"}
  orders:
    rows: 6000
    columns:
      order_id: {type: int, unique: true, min: 1, max: 1000000}
      customer_id: {type: foreign_key}
      channel: {type: categorical, choices: [web, app, marketplace]}
      amount: {type: float, min: 5, max: 900}
      ordered_at: {type: date, start: "2025-01-01", end: "2025-06-30"}
relationships:
  - customers.customer_id -> orders.customer_id
outcome_curves:
  - table: orders
    column: amount
    time_column: ordered_at
    value_mode: absolute
    start_date: "2025-01-01"
    curve_points:
      - {month: 1, target_value: 82000}
      - {month: 2, target_value: 88500}
      - {month: 3, target_value: 97250}
      - {month: 4, target_value: 101000}
      - {month: 5, target_value: 112400}
      - {month: 6, target_value: 125000}
group_shares:
  - table: orders
    measure: amount
    group_column: channel
    shares: {web: 0.5, app: 0.35, marketplace: 0.15}
```

Every month sums to its target to the cent, and inside every month web is
exactly 50% of revenue, app 35% and marketplace 15%.

## Run it

The folder is a small dbt project (`dbt_project.yml`, `profiles.yml` for a
local DuckDB file, one model, one test). Generate the seeds into it:

```bash
pip install "misata[duckdb]"
misata generate -c misata.yaml -o seeds --attest
```

Then build:

```bash
pip install dbt-duckdb
dbt build --profiles-dir .
```

```text
Done. PASS=4 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=4
```

## The test

`tests/revenue_matches_the_declaration.sql` holds the declared answer key and
returns any month where `fct_monthly_revenue` disagrees with it by more than
half a cent. Introduce the commonest date bug, an exclusive upper bound that
drops the last day of the period:

```sql
where ordered_at < date '2025-06-30'
```

and the test fails, because June now sums to 121,853.68 instead of the
declared 125,000. A uniqueness or row-count test passes on the same model.

## The check

The seeds themselves are attested before dbt ever reads them: 39 invariants,
including every monthly total and every channel share in every month.

```bash
misata attest seeds -s misata.yaml
```

## Unit tests, too

For dbt's own `unit_tests:` blocks, `misata dbt-unit-test --select
fct_monthly_revenue` reads your `target/manifest.json` and writes small
fixtures for every input the model refs, with keys that join.
