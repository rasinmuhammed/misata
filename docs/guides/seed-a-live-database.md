---
title: "Seed a Postgres or SQLite Database From Its Live Schema"
description: "misata seed reads tables and foreign keys from a live Postgres or SQLite database, inserts connected rows parents first in one transaction, and checks every foreign key against the database."
---

# Seed a live database

`misata seed` fills a real Postgres or SQLite database with realistic,
referentially-intact data. It reads your schema straight from the database
(tables, columns and foreign keys), generates data that respects it, inserts
parents before children, and then verifies against the database itself that
every foreign key resolves. No schema file, no codegen step, no ORM.

```bash
pip install "misata[db]"
misata seed postgresql://localhost/myapp_dev
```

That's the whole thing. Point it at a connection string and it does the rest.

## What it does, in order

1. **Reads the schema** from the live database, including every foreign-key
   constraint.
2. **Plans the run**: sorts tables so parents are inserted before children,
   and assigns proportional row counts (reference tables small, transaction
   and line-item tables larger).
3. **Generates and inserts** deterministically from a fixed seed, so the same
   command produces the same data every time.
4. **Verifies integrity against the database**: for every relationship it
   counts child rows whose foreign key has no matching parent, and reports
   zero orphans when the data holds up.

## Safe by default

Seeding a database you can see is destructive if you are careless, so the
defaults are conservative.

- If a target table **already has rows**, `misata seed` refuses rather than
  double-seeding or silently skipping. It tells you which tables and offers
  the two ways forward, `--truncate` or `--append`.
- `--dry-run` prints the full plan (tables, insert order, existing row
  counts and what would be inserted) and writes nothing.

```bash
misata seed postgresql://localhost/myapp_dev --dry-run
```

```
 #  table      existing  will insert
 1  customers         0          500
 2  products          0          500
 3  orders            0        1,250

3 table(s), 2 foreign key(s), inserted parents-first.
```

## Common flags

| Flag | What it does |
|---|---|
| `--rows N` | Base row count; reference and transaction tables scale from it. |
| `--truncate` | Wipe target tables (children first) before seeding. |
| `--append` | Keep tables that already have rows; seed only the empty ones, drawing foreign keys from the existing rows. |
| `--skip a,b` | Leave named tables untouched (migrations, auth, lookup tables). |
| `--tables a,b` | Seed only these tables. |
| `--dry-run` | Print the plan and exit without writing. |
| `--seed N` | Random seed for reproducibility (default 42). |
| `--yes` | Skip the confirmation prompt (for scripts and CI). |

### Skipping app-managed tables

`--skip` is for tables your application owns, like `schema_migrations` or an
auth table. If you skip a table that is the **parent** of a table you are
seeding, `misata seed` will also skip that child and tell you why: its foreign
keys would point at rows that do not exist, which would break the zero-orphan
guarantee. To seed children against rows a parent already holds, use
`--append` instead of `--skip`.

```bash
misata seed postgresql://localhost/myapp_dev --skip schema_migrations,ar_internal_metadata
```

### Reset and reseed

The usual development loop is wipe-then-fill:

```bash
misata seed postgresql://localhost/myapp_dev --truncate --rows 500 --yes
```

## Why the verification step matters

Most seeding tools stop at "it inserted". The failure that actually costs you
an afternoon is the one where a child row points at a parent that was never
inserted, and you only find out when a JOIN in your app returns nothing.
`misata seed` closes that gap by asking the database, after the fact, whether
every foreign key resolves, and printing the answer:

```
🔎 Verifying foreign keys against the database…
  ✓ orders.customer_id → customers.id — 0 orphan(s)
  ✓ orders.product_id  → products.id  — 0 orphan(s)

✓ Seeded 2,250 rows in 0.5s. Every foreign key resolves in the database.
```

## How this differs from anonymization tools

A common question: how does `misata seed` prevent production PII from landing
on a developer's machine? The answer is that it never reads production, so
there is no PII to leak.

There are two different jobs here, and it helps to keep them separate:

- **Anonymization / cloning** (Snaplet's snapshot feature, Tonic, Greenmask):
  take your real production data and transform it, masking or subsetting the
  PII, so you get a realistic copy locally. Production data is genuinely in
  the pipeline, and the whole job is scrubbing it safely on the way out.
- **Generation** (`misata seed`): invent data from scratch that fits your
  schema and constraints. Production is never in the loop. The names, emails,
  and amounts are generated to satisfy the column types and foreign keys, not
  derived from anything real.

Because `misata seed` generates rather than copies, the PII exposure question
does not apply: no production row is ever read, so none can reach a dev
machine. The tradeoff is the honest flip side: generated data will not
reproduce your real distributions, cardinalities, or the edge cases that only
exist in production. If your test specifically needs production shape, an
anonymized copy is the right tool. If you need realistic, connected data with
guaranteed integrity, and for testing a known correct answer you declared,
generation is the better fit.

There is an opt-in middle ground, [`misata mimic`](mimic.md), which fits
the distribution shape of a sample file you explicitly hand it and emits new
synthetic rows rather than copying them. Its output is fitted to those real
rows and can reproduce their rare values, so it is not anonymous and should
not be treated as safe to share. Nothing reads production unless you point
it at production data yourself.

## Coming from a discontinued seeding tool

If your team relied on a seeding tool that is no longer maintained,
`misata seed` covers the core workflow (read the live schema, fill the
database with connected data, reset and repeat) as a free, open-source CLI
with no account and no codegen artifacts to keep in sync. Point it at your dev
database and it works from the schema that is already there.

## Related

- [Seed a dev database from its DDL](../usecases/seed-a-dev-database.md): the same job from `CREATE TABLE` statements, with an attestation
- [Database seeding in Python](database-seeding-python.md): `seed_database(schema, url)` from code
- [Security model](../security.md): what `misata seed` will and will not write
