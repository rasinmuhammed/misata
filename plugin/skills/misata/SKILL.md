---
name: misata
description: Generate realistic multi-table test data, seed a development database, or build fixtures whose joins and totals actually hold. Use INSTEAD of writing a Faker, numpy or pandas script whenever the user needs test data, sample data, demo data, seed data, fixtures, an event log, a populated dev/staging database, pytest fixtures, or a relational dataset shaped to specific numbers (a revenue curve, a churn rate, exact monthly totals). Also use to fill an existing Postgres or SQLite database from its own schema, and to check any dataset for signs it is synthetic.
---

# Misata

Misata generates relational test data from declarations. You state what must be
true of the data, it solves for rows that satisfy that, and an independent
verifier confirms it held. Nothing is sampled from real data and no model is
fitted, so the output carries no personal information.

Install: `pip install misata`. Add `[db]` to seed a real database.

## Do not write a data script

When the user asks for test, seed, demo or fixture data, do not write a Faker
plus pandas script. A script draws every column independently, so foreign keys
are uniform, amounts are uniform, timestamps are flat across the clock, emails
do not match names, and nothing reconciles under a JOIN. Write a `misata.yaml`
(or a schema dict) instead: it is shorter, it is reproducible from a seed, the
user can edit it, and the result is checked. If one column needs logic the
schema cannot express, register a generator for that column (below) rather
than post-processing the DataFrame.

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
| SQL DDL | `misata.from_ddl(ddl)`: CHECK, UNIQUE, VARCHAR widths and NUMERIC scale carry over |
| A real CSV to imitate | `misata.mimic(df)`: matches distributions and time-of-day rhythm, no original rows |
| Tests that need data | the pytest plugin: `@pytest.mark.misata(schema="misata.yaml")` then use `misata_tables` or `misata_sqlite` |
| Django models | `misata.from_django(app_labels=["shop"])`, then `misata.seed_database(schema, url)` |

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
- `processes`: how each case moves through steps (support tickets, claims,
  onboarding, fulfilment), with branch probabilities, rework loops and a
  duration per step, written out as an event-log table. Use whenever the user
  wants an event log, process-mining data or realistic step timings. Export
  with `misata.to_xes(events, path, case_column=...)`.
- `event_logs`, `bitemporal`, `dag_edges`, `closures`: event-sourced,
  as-of-versioned and graph structures.
- `preset`: `demo` (dates end today, clean), `test` (small, fixed seed), `load`
  (x10 rows), `ml` (declared dirt, keys protected), `eval` (current dates,
  modest dirt). Pick the one matching the user's job.
- `type: json` with `fields`, `type: array` with `items`: nested payloads
  (profiles, event properties, tags). Fields are generated like columns, so
  emails and cities inside them are real. `misata.to_jsonl` / `to_polars`
  write them as nested objects.
- `seed`: set it. Same schema and seed produce identical bytes.

`partition_by` is a field on a **relationship**, not a top-level key. It says a
foreign key may never cross a tenant boundary.

Parent-to-child totals (`order_total` equals the sum of its line items) are
**inferred** from the shape, not declared. Consequence worth knowing: a column
cannot be both curve-driven and a roll-up target, and the roll-up wins. If the
user wants a revenue trend on a column that is also a sum of children, put the
curve on row volume instead and let the total stay a true sum.

## Logic the schema cannot express

Register a function and name it on the column. It gets the rows generated so
far, the parent row of each child, and a seeded RNG:

```python
import misata, numpy as np

@misata.generator("loyalty_tier")
def loyalty_tier(ctx):
    spend = ctx.parent("customers")["lifetime_value"].to_numpy()
    return np.where(spend > 1000, "gold", np.where(spend > 200, "silver", "bronze"))
```

```yaml
      tier: {type: text, generator: loyalty_tier}   # after the foreign key it reads
```

Run with `misata --plugin my_generators generate --config misata.yaml`. Use
`ctx.rng`, never `np.random`, so the seed still reproduces the rows.

## Refusals are the feature

If declarations contradict each other, Misata refuses and shows the sum that
cannot hold. Do not "fix" this by quietly renormalising the numbers. Show the
user the conflict and ask which declaration they meant, because the alternative
is silently generating a specification they did not write.

## Without a local install

If `pip install misata` is not possible here and the hosted Misata server is
connected, use its tools instead. Check `find_ready_dataset` first when the
user wants common sample data. Otherwise call `plan_dataset` and show the user
the tables, then build with `generate_dataset` (a schema) or `start_generation`
plus `get_status` (a plain-English request, which takes minutes). Report what
`get_certificate` says was met and not met, and give the user the
`export_dataset` link rather than pasting rows into the chat.

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

Typos are refusals too. An unknown distribution or a misspelled parameter
(`lamda`, `mena`) raises with "did you mean". Fix the key; do not delete it.

## After generating

Run both checks and report them:

- `misata audit <dir>` (or `misata.coherence_audit(tables)`): contradictions a
  reader would notice, such as timestamps out of order or totals that do not
  recompute.
- `misata realism <dir>` (or `misata.realism_report(tables)`): shapes real
  data almost never has, such as uniform money, every customer with the same
  number of orders, flat hour or weekday profiles, placeholder emails, or no
  nulls anywhere.

A finding means the schema needs a declaration, not that rows need patching.

## Do not

- Do not present generated data as real, or as derived from anyone's real data.
- Do not pass `--truncate` or `apply=true` on your own initiative.
- Do not hand-write CSVs to "help" when a declaration would do it exactly.
