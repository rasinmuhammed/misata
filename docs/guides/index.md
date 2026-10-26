---
title: "Misata Guides by Job: Seed, Test, Attest, Publish, Solve, Evaluate"
description: "Find the Misata guide for the job in front of you: seeding databases, testing pipelines, attesting and publishing datasets, solving for pipeline outputs, building eval packs, streaming at scale and imitating real files."
---

# Guides

Each guide covers one job end to end. If you would rather start from a
complete, runnable example, the [use cases](../usecases/index.md) are
recipes with measured results.

## Seed a database

- [SQL DDL to schema](from-ddl.md): generate from `CREATE TABLE`
  statements, honouring keys, CHECK rules, UNIQUE and NOT NULL.
- [Seed a live database](seed-a-live-database.md): `misata seed` reads a
  Postgres or SQLite schema and fills it, parents first.
- [Database seeding in Python](database-seeding-python.md):
  `seed_database(schema, url)` from code and from pytest.
- [From a database](../generation/database.md): introspect, edit, regenerate.
- [Django](django.md) and [dbt seed integration](dbt-seed.md).

## Test pipelines and code

- [pytest fixtures](testing.md): data inside a test suite, with fingerprints.
- [Validate and preview](../validate.md): profile a CSV, inspect what a story
  will produce.
- [Realism report](../realism.md): the statistical tells of generated data.
- [When Misata refuses](../failure-modes.md): every refusal and warning, and
  how to make warnings fatal in CI.

## Prove what the data holds

- [Attest a dataset](attest.md): an in-toto attestation and a `verify.py`
  anyone can rerun with DuckDB.
- [Certificate predicate v1](../attestation/certificate-v1.md): the format,
  field by field.

## Share it

- [Publish to Hugging Face](publish.md): verified before upload, with a
  dataset card generated from the attestation.

## Hit a number a pipeline computes

- [Solve for a pipeline's output](solve.md): move outcome curves until a dbt
  model, a SQL query or a Python function produces the targets.

## Evaluate SQL models and agents

- [Build an evalpack](evalpack.md): questions whose answers were declared
  before the data, checked on rotated databases.
- [MCP server](mcp.md): give an agent tools to explain, generate, audit,
  attest, solve and seed.

## Generate at scale

- [Streaming large datasets](streaming.md): bounded memory, straight to
  Parquet, JSON Lines, CSV or DuckDB.
- [Export](../export.md) and [Databricks and Spark](../spark.md).

## Imitate a real file

- [Mimic](mimic.md): a twin fitted to a CSV. It is fitted to real rows and is
  not anonymous; use declared generation when the data must not derive from
  real records.

## Shape the data

- [Outcome curves](outcome_curves.md) and [rate curves](rate_curves.md):
  totals and rates per period that hold exactly.
- [Distributions](distributions.md), [correlations](correlations.md) and
  [conditional columns](conditional-columns.md).
- [Narrative patterns](narrative-patterns.md): growth stories in plain
  English.
- [Processes and event logs](processes.md),
  [nested JSON and arrays](nested-columns.md),
  [long-form text](long-form-text.md) and [geospatial realism](geospatial.md).
- [Lexicons, motifs and joint margins](declared-vocabulary-and-structure.md),
  [anomaly injection](anomaly-injection.md),
  [custom generators](custom-generators.md) and
  [use-case presets](presets.md).

## Comparisons

- [Faker vs SDV vs Misata](faker-vs-sdv-vs-misata.md)
- [Multi-table synthetic data](multi-table-synthetic-data.md)
- [Synthetic data for BI demos](synthetic-data-for-bi-demos.md)
- [Python synthetic data generator](../python-synthetic-data-generator.md)
