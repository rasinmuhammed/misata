---
title: A Warehouse Before the Product Has Users
description: Build a 291,000-row SaaS warehouse with an exact monthly revenue curve, exact plan shares and a declared refund rate, written as partitioned Parquet or one DuckDB file, so dashboards and models can be built before real data exists.
---

# A warehouse before the product has users

Dashboards, metrics layers and the first dbt models get built months before
there is real data to point them at. The usual stand-in is uniform noise,
which renders every chart as a flat line and hides every bug that depends on
growth, mix or seasonality. Declare the business you expect instead.

**Who:** founders, first data hires, analytics leads.
**Time:** about 2 seconds for 291,000 rows across four tables.

## The declaration

Revenue grows from 180k to 344k a month, starter, growth and enterprise
plans bring exactly 20%, 45% and 35% of it, and refunds fall from 4% to 2%
over the year:

```yaml
# misata.yaml
name: saas_warehouse
seed: 2025
tables:
  accounts:
    rows: 2000
    columns:
      account_id: {type: int, unique: true, min: 1, max: 2000}
      company: {type: text, text_type: company}
      region: {type: categorical, choices: [amer, emea, apac], probabilities: [0.5, 0.32, 0.18]}
      signed_up_at: {type: date, start: "2024-01-01", end: "2025-12-31"}
  users:
    rows: 9000
    columns:
      user_id: {type: int, unique: true, min: 1, max: 9000}
      account_id: {type: foreign_key}
      email: {type: email, unique: true}
      role: {type: categorical, choices: [owner, admin, member], probabilities: [0.2, 0.2, 0.6]}
  invoices:
    rows: 30000
    columns:
      invoice_id: {type: int, unique: true, min: 1, max: 10000000}
      account_id: {type: foreign_key}
      plan: {type: categorical, choices: [starter, growth, enterprise]}
      amount: {type: float, min: 20, max: 4000}
      is_refunded: {type: boolean}
      issued_on: {type: date, start: "2025-01-01", end: "2025-12-31"}
  events:
    rows: 250000
    columns:
      event_id: {type: int, unique: true, min: 1, max: 100000000}
      user_id: {type: foreign_key}
      event_type: {type: categorical, choices: [page_view, search, export, invite], probabilities: [0.7, 0.18, 0.08, 0.04]}
      occurred_at: {type: datetime, start: "2025-01-01", end: "2025-12-31"}
relationships:
  - accounts.account_id -> users.account_id
  - accounts.account_id -> invoices.account_id
  - users.user_id -> events.user_id
outcome_curves:
  - table: invoices
    column: amount
    time_column: issued_on
    value_mode: absolute
    start_date: "2025-01-01"
    curve_points:
      - {month: 1, target_value: 180000}
      - {month: 2, target_value: 192000}
      - {month: 3, target_value: 207000}
      - {month: 4, target_value: 221000}
      - {month: 5, target_value: 238000}
      - {month: 6, target_value: 251000}
      - {month: 7, target_value: 262000}
      - {month: 8, target_value: 270000}
      - {month: 9, target_value: 289000}
      - {month: 10, target_value: 305000}
      - {month: 11, target_value: 322000}
      - {month: 12, target_value: 344000}
group_shares:
  - table: invoices
    measure: amount
    group_column: plan
    shares: {starter: 0.2, growth: 0.45, enterprise: 0.35}
rate_curves:
  - table: invoices
    column: is_refunded
    time_column: issued_on
    rate_points:
      - {period: "2025-01", rate: 0.04}
      - {period: "2025-06", rate: 0.03}
      - {period: "2025-12", rate: 0.02}
```

## Run it

```bash
pip install "misata[parquet,duckdb]"
misata explain misata.yaml
misata generate -c misata.yaml -o lake --format parquet --partition-by plan --attest
misata generate -c misata.yaml -o warehouse --format duckdb
```

`lake/` holds one Parquet file per table, with `invoices` split Hive-style
into `invoices/plan=starter/`, `plan=growth/` and `plan=enterprise/`.
`warehouse/data.duckdb` holds the same four tables in one file that any
DuckDB client, Evidence, Rill or a dbt-duckdb profile can open.

## What a dashboard sees

Querying `lake/invoices` with DuckDB:

```text
plan          revenue     share
enterprise    1078350.0   0.35
growth        1386450.0   0.45
starter        616200.0   0.20

month     revenue    invoices   refund_rate
2025-01   180000.0   1753       0.0399
2025-06   251000.0   2444       0.0299
2025-12   344000.0   3350       0.0200
```

Row counts follow the revenue, because the curve plans how many invoices
each month needs at a plausible average value. The refund rate is
interpolated between the declared anchors and holds to the nearest invoice.

## The check

```bash
misata attest lake -s misata.yaml
python lake/verify.py
```

```text
ok    6 file(s) match their attested sha256
ok    80 of 80 invariant(s) hold
```

The 80 invariants are every monthly total and the grand total, the planned
invoice count per month, every plan share in every month and overall, the
refund rate at each anchor, three foreign keys, every unique key, and every
declared category domain.
