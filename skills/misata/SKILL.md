---
name: misata
description: Generate realistic multi-table test data, seed a development database, or build fixtures whose joins and totals actually hold. Use when the user needs test data, sample data, demo data, seed data, fixtures, a populated dev/staging database, or a relational dataset shaped to specific numbers (a revenue curve, a churn rate, exact monthly totals). Also use when asked to fill an existing Postgres or SQLite database from its own schema.
---

# Misata

Misata generates relational test data from declarations. You state what must be
true of the data, it solves for rows that satisfy that, and an independent
verifier confirms it held. Nothing is sampled from real data and no model is
fitted, so the output carries no personal information.

Install: `pip install misata`. Add `[db]` to seed a real database.

## Division of labour

You are good at designing schemas. Misata is good at guaranteeing arithmetic:
foreign key integrity, exact aggregates, distributions, reproducibility.

So when you know the tables and columns the user needs, design them yourself and
hand Misata a schema. Reach for the one-sentence path only for throwaway
requests where you do not care about the shape.

## Choosing an approach

| The user has | Do this |
| --- | --- |
| A description in prose | `misata generate --story "..."` |
| A schema in mind | write a `misata.yaml`, then `misata generate --config misata.yaml` |
| An existing database | `misata seed <db-url>` reads its schema and fills it |
| A dbt project | `misata dbt-seed --from-project .` uses its own tests as constraints |
| A Prisma schema | `misata prisma-seed` |

Run `misata init` to scaffold a `misata.yaml`, and `misata lint misata.yaml`
before generating. Lint catches declarations that cannot hold together and shows
the arithmetic.

## What is worth declaring

Plain column types get you Faker. The reason to use Misata is the rest. These
are top-level keys in `misata.yaml`:

- `outcome_curves`: a measure hits an exact total per period. Use for revenue,
  signups, anything the user described as a trend.
- `group_shares`: exact shares of a measure across a category. Shares must sum
  to 1.0 or it refuses.
- `waterfalls`: movements that reconcile to a declared ending balance.
- `stock_flows`: opening plus received minus shipped equals closing, per period.
- `lifecycles`: a status implies a legal, ordered, fully timestamped history.
  This is what stops "delivered" orders with no shipment date.
- `duplicates`, `outliers`, `typos`: an exact count of deliberate dirt, so
  dedupe and anomaly logic have something real to find.
- `missingness`, `retention`, `late_arrivals`, `time_grids`: the shapes real
  pipelines produce, declared rather than hoped for.
- `event_logs`, `bitemporal`, `dag_edges`, `closures`: event-sourced,
  as-of-versioned and graph structures.
- `seed`: set it. Same schema and seed produce identical bytes.

`partition_by` is a field on a **relationship**, not a top-level key. It says a
foreign key may never cross a tenant boundary.

Parent-to-child totals (`order_total` equals the sum of its line items) are
**inferred** from the shape, not declared. Consequence worth knowing: a column
cannot be both curve-driven and a roll-up target, and the roll-up wins. If the
user wants a revenue trend on a column that is also a sum of children, put the
curve on row volume instead and let the total stay a true sum.

## Refusals are the feature

If declarations contradict each other, Misata refuses and shows the sum that
cannot hold. Do not "fix" this by quietly renormalising the numbers. Show the
user the conflict and ask which declaration they meant, because the alternative
is silently generating a specification they did not write.

## Seeding a real database

`misata seed <url>` reads the schema from the database itself and inserts
parents before children.

- Run `--dry-run` first and show the user the plan. Always.
- It refuses non-empty tables unless `--truncate`. Never pass `--truncate`
  without explicit confirmation: it destroys data.
- `--append` fills only the empty tables and draws foreign keys from the rows
  already there.
- Tables in another schema, such as Supabase's `auth.users`, are read but never
  written. Children draw from the ids that exist.
- After inserting it re-queries the database to count orphans per relationship.
  Report those numbers to the user rather than asserting success.

## After generating

Run `misata.coherence_audit(tables)` and report the score. It detects defects a
reader would notice: timestamps out of order, labels used as filler, values at
absurd scale, derived arithmetic that does not recompute. A clean generation
that fails the audit means the schema is wrong, not the rows.

## Do not

- Do not present generated data as real, or as derived from anyone's real data.
- Do not pass `--truncate` or `apply=true` on your own initiative.
- Do not hand-write CSVs to "help" when a declaration would do it exactly.
