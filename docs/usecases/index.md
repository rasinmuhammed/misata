---
title: Synthetic Data Use Cases, Recipes With Measured Results
description: Pick a Misata recipe by the job in front of you, from seeding a dev database out of its DDL to known-answer dbt tests, PII-free staging, ledgers that reconcile, eval databases for SQL agents and labelled fraud graphs.
---

# Use cases

Each recipe is a folder you can run as it is: a schema, the commands, the
output you should see, and the check that proves the result. The numbers on
these pages were measured on the recipe's own files, and each page says how
to reproduce them.

## Pick by the job

| You need to | Recipe | What proves it worked |
|---|---|---|
| Fill a dev, CI or preview database that has CHECK rules and foreign keys | [Seed a dev database from its DDL](seed-a-dev-database.md) | 22 of 22 invariants derived from the DDL hold on the files |
| Test that a dbt model computes the right revenue, not only unique keys | [Known-answer tests for dbt models](dbt-known-answer-tests.md) | a dbt test that fails on the exclusive-upper-bound bug |
| Give a sales demo an account whose history holds up to questions | [A demo tenant that tells a story](demo-tenant.md) | realism score 0.96 and a clean coherence audit |
| Build dashboards and models before the product has users | [A warehouse before the product has users](warehouse-before-users.md) | 80 of 80 invariants: every month, every plan share, the refund rate |
| Score text-to-SQL models or data agents against a correct answer key | [An eval database with a correct answer key](eval-database.md) | 46 of 46 gold answers match on three rotated databases |
| Let an agent practise SQL on a database and grade what it wrote | [A sandbox an AI agent can act in](agent-sandbox.md) | 27 of 27 declared answers hold before any grading |
| Train or score a fraud or AML detector on labels you can trust | [Fraud and AML data with labelled truth](fraud-aml.md) | 10 of 10 invariants, including no cycle outside a declared case |
| Load test with hot keys, a daily traffic curve and a latency tail | [Load and performance test data](load-testing.md) | 6 of 6 invariants on 2.6 million streamed rows |
| Fill staging, QA or demo databases without reading a production row | [PII-free staging and test environments](pii-free-environments.md) | 23 of 23 invariants, and a regeneration whose file hashes match |
| Test a close, a reconciliation or a ledger report on books that balance | [Ledgers that reconcile to the cent](ledgers-that-reconcile.md) | 52 of 52 invariants: every entry, the trial balance, every quarter's roll-forward |
| Give every candidate or student the same SQL questions with their own answers | [SQL take-home exercises with a key per candidate](take-home-exercises.md) | 31 of 31 answers match on both databases, for every candidate |
| Fill API docs, SDK tests and mock servers with JSON whose ids resolve | [Example data for docs, SDK tests and mock APIs](example-data-for-docs.md) | 9 of 9 invariants, including no task assigned across tenants |

```diagram
# Which recipe, by what you start from
What do you have?
│
├── SQL DDL or a live database ─────────▶ Seed a dev database from its DDL
│       └── a review asks where the ────▶ PII-free staging and test environments
│           data came from
│
├── an API to document or mock ─────────▶ Example data for docs, SDK tests and mock APIs
│
├── books that must balance ────────────▶ Ledgers that reconcile to the cent
│
├── a dbt project ──────────────────────▶ Known-answer tests for dbt models
│       └── the number is computed by     (then: guides/solve)
│           the models, not stored
│
├── a story to tell in a demo ──────────▶ A demo tenant that tells a story
│
├── a business plan, no users yet ──────▶ A warehouse before the product has users
│
├── a system to load test ──────────────▶ Load and performance test data
│
└── a model or agent to evaluate
        ├── SQL answers ────────────────▶ An eval database with a correct answer key
        ├── an agent that acts ─────────▶ A sandbox an AI agent can act in
        ├── people taking a test ───────▶ SQL take-home exercises with a key per candidate
        └── a detector ─────────────────▶ Fraud and AML data with labelled truth
```

## What every recipe has in common

- **A declaration, not a script.** The schema says what must be true (a
  monthly total, a share, a rate, a legal order of states) and Misata
  generates rows that satisfy it. Nothing is patched after generation.
- **A seed.** The same schema, seed and Misata version give the same rows on
  Linux, macOS and Windows. The exceptions are the `demo` and `eval`
  [presets](../guides/presets.md), which move dates so the latest one is the
  day you run them.
- **A check that does not trust Misata.** `--attest` writes an
  [in-toto attestation](../guides/attest.md) and a `verify.py` that reruns
  every invariant with DuckDB alone, so whoever receives the files can check
  them without installing Misata.

## Not covered here

Recipes start from declarations. If you need a statistical copy of a
specific real table, see [mimic](../guides/mimic.md), and note that its
output is fitted to the real rows and is not anonymous. The
[limitations](../limitations.md) page lists what the checks do not cover.
