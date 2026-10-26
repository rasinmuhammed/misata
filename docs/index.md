---
title: "Misata: Synthetic Data Generator for Python With Exact, Verifiable Outcomes"
description: "Misata generates multi-table synthetic data from SQL DDL, a YAML schema, a live database or one sentence. Foreign keys, CHECK rules and declared totals hold, and an attestation proves it."
---

# Misata

**Misata generates relational synthetic data from a declaration of what must
be true, and proves afterwards that it is.**

You say what the data has to satisfy: the tables and keys, the CHECK rules,
a monthly revenue curve, a refund rate, a 50/35/15 channel split, the legal
order of a subscription's states. Misata generates rows that satisfy all of
it, refuses before generating when two declarations contradict each other,
and writes an attestation that anyone can rerun with DuckDB to confirm every
declared number on the files themselves.

It is an open-source Python library (MIT), a CLI and an MCP server. It needs
no real data, no trained model and no API key, and within one Misata version
the same schema and seed give the same rows on every machine.

```bash
pip install misata
```

```diagram
# From a declaration to a verified dataset
 schema.sql · misata.yaml · a sentence · a live database
                         │
                         ▼
 misata explain ──────▶ planned rows, which declaration writes which column,
                        every conflict and its remedy (exit 3: nothing written)
                         │
                         ▼
 misata generate ─────▶ CSV · JSON Lines · Parquet · DuckDB · Postgres · SQLite
                         │
                         ▼
 --attest ────────────▶ attestation.intoto.json   every file pinned by SHA-256,
                        verify.py                 every invariant as DuckDB SQL
                         │
          ┌──────────────┼──────────────────┬───────────────────┐
          ▼              ▼                  ▼                   ▼
   python verify.py   misata publish    misata evalpack     misata solve
   (anyone, no        (Hugging Face,    (questions with     (make a dbt or
    Misata needed)     verified first)   known answers)      SQL pipeline hit
                                                             its targets)
```

## Start from what you have

| You have | Call | Read |
|---|---|---|
| SQL DDL (`CREATE TABLE ...`) | `misata generate -c schema.sql`, or `misata.from_ddl(ddl)` | [Seed a dev database from its DDL](usecases/seed-a-dev-database.md) |
| A live Postgres or SQLite database | `misata seed postgresql://...`, or `schema_from_db(url)` then `seed_database(schema, url)` | [Seed a live database](guides/seed-a-live-database.md) |
| A YAML or dict schema | `misata generate -c misata.yaml`, or `misata.generate_from_schema(schema)` | [YAML schema](generation/yaml.md) |
| A sentence | `misata.generate("A SaaS company with 1,000 customers", seed=42)` | [Plain English](generation/story.md) |
| Django models | `misata.from_django(app_labels=[...])` | [Django](guides/django.md) |
| More rows than fit in memory | `misata generate --format parquet`, or `misata.generate_stream(...)` | [Streaming](guides/streaming.md) |
| A number a dbt or SQL pipeline must produce | `misata solve -c solve.yaml` | [Solve for a pipeline's output](guides/solve.md) |
| Real rows to imitate | `misata.mimic(df_or_csv)` | [Mimic](guides/mimic.md). Fitted to real rows, so not anonymous |

Always pass a seed (`--seed`, `seed:` in YAML, `__seed__` in a dict) so the
result can be reproduced.

## A first dataset

```python
import misata

tables = misata.generate(
    "A SaaS company with 5k users, monthly subscriptions, and 20% churn",
    seed=42,
)
for name, df in tables.items():
    print(name, len(df))
```

The same data as a file you can commit and review:

```yaml
# misata.yaml
name: my-app
seed: 42
tables:
  users:
    rows: 1000
    columns:
      user_id: {type: int, unique: true}
      email: {type: email, unique: true}
      plan: {type: categorical, choices: [free, pro, enterprise]}
  orders:
    rows: 5000
    columns:
      order_id: {type: int, unique: true}
      user_id: {type: foreign_key}
      amount: {type: float, min: 5, max: 500}
      ordered_at: {type: date, start: "2025-01-01", end: "2025-06-30"}
relationships:
  - users.user_id -> orders.user_id
```

```bash
misata explain misata.yaml
misata generate -c misata.yaml -o out --attest
python out/verify.py
```

The [quickstart](quickstart.md) walks through both, and the
[use cases](usecases/index.md) are complete recipes for specific jobs.

## What it is for

- **Seeding** development, CI and preview databases whose schemas have
  foreign keys, CHECK rules, unique and composite keys, and self-references.
- **Testing** pipelines and dbt models against data whose correct output is
  known before it exists.
- **Demos and dashboards** that need believable shapes: skewed money, a few
  large customers, weekday rhythms, histories that hold up to questions.
- **Evaluating** text-to-SQL models and data agents against answer keys that
  are checked on several databases at once.
- **Volume**: ten million rows across fourteen tables stream to Parquet in
  36 seconds on an Apple M1, at 0.78 GB peak.

## What the evidence supports

- **Valid by construction.** On five DDL schemas, zero violations of keys,
  CHECK rules, UNIQUE, NOT NULL and self-reference trees, against 15,014 to
  50,416 per schema for a per-column Faker script, and 3,055 to 5,557 for
  SDV's multi-table model trained on valid data, which refuses two of the
  five schemas. See the [validity benchmark](validity-benchmark.md).
- **Realistic without data, within limits.** Blind e-commerce data is harder
  to tell from real orders than a Faker script or SDV trained on the real
  data (detection AUC 0.629 against 0.783 and 0.711 on Olist, mean of five
  seeds; 0.5 means a classifier cannot tell them apart). On taxi trips it
  beats the script (0.750 against 0.788) but not SDV trained on the trips
  (0.675). See the [realism benchmark](realism-benchmark.md).
- **Honest about the rest.** The [limitations](limitations.md) page lists
  what the checks do not cover, and [When Misata refuses](failure-modes.md)
  explains every refusal and warning.

What Misata does not claim: that `mimic` output is private or anonymous,
that any data is indistinguishable from a particular production table, or
that rows are byte-identical across Misata versions (they are within one
version; see the [stability policy](stability.md)).

## Use it from an AI agent

```bash
pip install "misata[mcp]"
claude mcp add misata misata-mcp
```

The [MCP server](guides/mcp.md) gives Claude, Cursor and other agents tools
to explain, generate, audit, attest, solve and seed. Agents writing code
against the library should read
[AGENTS.md](https://github.com/rasinmuhammed/misata/blob/main/AGENTS.md),
and every page here is also served as Markdown at its URL plus `.md`.

## Questions

### Does Misata need real data?

No. Declared generation starts from a schema, DDL, a database's structure
or a sentence, and no real row is read. The one exception is
[`misata.mimic`](guides/mimic.md), which you point at a real file on
purpose.

### Is the output of `mimic` anonymous or privacy-safe?

No. A twin is fitted to the real rows, reuses their category values and
quantiles, and can reproduce a rare record. When the data must be private,
use a differentially private synthesizer with a stated epsilon, or declare
the data instead of fitting it.

### Can it fill a Postgres database directly?

Yes. `misata seed postgresql://...` reads the live schema and inserts rows
parents first in one transaction; `misata generate -c schema.sql --db-url
... --db-create` does the same from DDL. Neither empties a table unless
you ask (`--truncate` for `seed`, `--db-truncate` for `generate`). See [Seed a live database](guides/seed-a-live-database.md).

### Will the same seed give the same rows after an upgrade?

Within one Misata version, yes, on Linux, macOS and Windows. Across versions,
declared totals, rates, shares and integrity hold, but individual rows may
change; each release lists them under Output changes. Pin the version for
byte-identical fixtures and record `misata.fingerprint(tables)["__all__"]`.
See the [stability policy](stability.md).

### How is this different from Faker?

Faker produces one value at a time and leaves keys, CHECK rules and totals to
the script around it. Misata generates whole tables together, so keys
resolve, rules hold and declared numbers come out exact. On five DDL schemas
a per-column Faker script broke 15,014 to 50,416 rules per schema where
Misata broke none. See [Faker vs SDV vs Misata](guides/faker-vs-sdv-vs-misata.md).
