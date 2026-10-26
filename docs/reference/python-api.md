---
title: "Python API Reference: generate, from_ddl, attest, solve and More"
description: "The public Python API of the Misata synthetic data library, grouped by job: build a schema, generate, stream, seed a database, check, attest, solve, build evalpacks, publish and export."
---

# Python API reference

Everything below is importable from the top-level package (`import misata`)
unless a module is named. Signatures are those of Misata 0.9.8; each section
links to the guide that explains the behaviour in full.

## Build a schema

| Call | Returns | What it does |
|---|---|---|
| `misata.from_ddl(ddl, *, infer_fks=True, default_rows=1000)` | `SchemaConfig` | Parses `CREATE TABLE` statements: keys, NOT NULL, UNIQUE, composite keys, CHECK ranges, enums and column-to-column rules, self-references. [Guide](../guides/from-ddl.md) |
| `misata.load_yaml_schema(path, rows=1000, seed=42)` | `SchemaConfig` | Loads a `misata.yaml` file. [Guide](../generation/yaml.md) |
| `misata.yaml_schema.load_schema_file(path, *, seed=None, rows=None)` | `SchemaConfig` | Loads any schema file form the CLI accepts: `misata.yaml`, a `SchemaConfig` dump or the dict form. |
| `misata.save_yaml_schema(schema, path)` | `Path` | Writes every declaration back to YAML; `load_yaml_schema` reads it back to an equal model. |
| `misata.from_dict_schema(schemas, row_count=None)` | `SchemaConfig` | Converts a plain dict of tables and columns. [Guide](../generation/dict.md) |
| `misata.schema_from_db(db_url, *, default_rows=1000, include_tables=None)` | `SchemaConfig` | Introspects a live database, foreign keys included. [Guide](../generation/database.md) |
| `misata.from_django(models=None, *, app_labels=None, default_rows=1000, include_contrib=False)` | `SchemaConfig` | Reads Django models after `django.setup()`. [Guide](../guides/django.md) |
| `misata.parse(story, rows=10000)` | `SchemaConfig` | Turns a sentence into a schema without generating. [Guide](../generation/story.md) |
| `misata.preview(story, rows=10000)` | `DetectionReport` | What a sentence was understood as: domain, scale, events, tables. |
| `misata.apply_preset(schema, name, *, scale=None, today=None)` | `SchemaConfig` | A copy with the `demo`, `test`, `load`, `ml` or `eval` defaults filled in. [Guide](../guides/presets.md) |

A `SchemaConfig` carries its seed as `schema.seed`; set it before generating
when the source did not declare one.

## Plan before generating

| Call | Returns | What it does |
|---|---|---|
| `misata.explain(schema)` | `Explanation` | Planned rows (exact, curve plans included), approximate memory, which declaration writes which column, the invariants an attestation will check, and every conflict with its remedy. `summary()` prints it; `to_dict()` is the JSON form. The CLI is `misata explain`. |

## Generate

| Call | Returns | What it does |
|---|---|---|
| `misata.generate(story, rows=10000, seed=None, ...)` | `dict[str, DataFrame]` | One sentence to a set of related tables. |
| `misata.generate_from_schema(schema, ..., strict=True, preset=None)` | `dict[str, DataFrame]` | Generates from a `SchemaConfig`. Contradictory declarations raise `InfeasibleSchema` before any row is generated; `strict=False` keeps the old behaviour. |
| `misata.generate_stream(story, rows=10000, seed=None)` | iterator of `(table, DataFrame)` | Bounded-memory generation from a story, a dict schema, a `SchemaConfig`, a schema file or DDL. One-hop roll-ups reconcile while streaming. [Guide](../guides/streaming.md) |
| `misata.mimic(source, rows=None, seed=None, table_name="table")` | `dict[str, DataFrame]` | A twin fitted to a CSV or DataFrame. Fitted to real rows, so not anonymous. [Guide](../guides/mimic.md) |

## Write to a database

| Call | Returns | What it does |
|---|---|---|
| `misata.seed_database(config, db_url, *, create=False, truncate=False, batch_size=10000, append=False, ...)` | `SeedReport` | Generates from a `SchemaConfig` and inserts parents first, in one transaction. `truncate` wipes target tables first; never pass it without the owner's consent. `append` keeps populated tables and fills only the empty ones. [Guide](../guides/database-seeding-python.md) |

`SeedReport` has `total_rows`, `table_rows`, `created_tables`,
`truncated_tables` and `duration_seconds`.

## Check the result

| Call | Returns | What it does |
|---|---|---|
| `misata.realism_report(tables, schema=None, *, skip=())` | `RealismReport` | Looks for the statistical tells of generated data, with no real data needed. `score`, `passed`, `summary()`, `to_dict()`. [Guide](../realism.md) |
| `misata.coherence_audit(tables, *, repair=False, seed=42, schema=None)` | `CoherenceReport` | Reader-visible contradictions: a churn date on an active subscription, a payment before its customer existed. |
| `misata.fingerprint(tables)` | `dict[str, str]` | A canonical hash per table and for the whole dataset (`"__all__"`), independent of file format and dtype. Put it in fixtures you commit. |
| `misata.validate_csv(path_or_df, schema=None, story=None, table_name=None)` | `CsvValidationReport` | Profiles a CSV, optionally against a schema. [Guide](../validate.md) |
| `misata.fidelity_report(synthetic, real, target_column=None, ml_efficacy=True)` | `FidelityReport` | How closely a synthetic table matches a real one, when you have the real one. |

## Attest

| Call | Returns | What it does |
|---|---|---|
| `misata.attest(data_dir, schema, *, spec_path=None, write=True, script_name="verify.py")` | `Attestation` | Re-checks every invariant the schema implies against the files on disk with DuckDB, pins each file by SHA-256, and writes `attestation.intoto.json`, `attestation.dsse.json` and `verify.py`. `passed`, `invariants`, `failures`, `statement`, `summary()`. [Guide](../guides/attest.md) |

The predicate is specified in [Certificate predicate v1](../attestation/certificate-v1.md).

## Solve for a pipeline's output

| Call | Returns | What it does |
|---|---|---|
| `misata.solve(schema, runner, targets, *, tolerance="1%", max_iterations=25, max_seconds=None, damping=0.85)` | `SolveResult` | Moves the outcome curves each target names as its lever until the pipeline's metrics hit their per-period targets. [Guide](../guides/solve.md) |
| `misata.Target(metric, lever, values, direction="direct")` | | A metric, the `table.column` curve that moves it, and its value per period. `direction="inverse"` for levers that lower their metric. |
| `misata.SQLRunner(queries, *, timeout=60.0, memory_limit=None)` | | DuckDB SQL over the generated tables, one query per metric, in a sandbox. |
| `misata.DbtDuckDBRunner(project_dir, metrics, *, select=None, source_schema="main", seeds=False, ...)` | | A dbt project built on a temporary DuckDB warehouse. |
| `misata.PythonRunner(fn, name=None)` | | Any function of the tables that returns `{metric: values by period}`. A plain function passed as `runner` is wrapped in one. |

`SolveResult` has `converged`, `reason`, `iterations`, `best`, `summary()`,
`write(dir)` (the closest dataset, `schema.solved.json`, the solved YAML and
`solve.json`) and `attest(dir)`, which adds each solved period of a SQL
pipeline as an invariant.

## Evalpacks

| Call | Returns | What it does |
|---|---|---|
| `misata.evalpack.build_evalpack(schema, output_dir, *, tables=None, rotations=1)` | `EvalPackResult` | Questions with answers fixed by the declarations, a database per rotation, gold SQL verified on every one. `all_verified`, `questions`, `dropped`, `summary()`. [Guide](../guides/evalpack.md) |
| `misata.evalpack.verify_questions(con, questions)` | `(shipped, dropped, certificate)` | Keeps the questions whose gold SQL returns the expected answer on a connection, for packs built from an answer key rather than from declarations. Dropped questions carry their `drop_reason`. |

## Publish

| Call | Returns | What it does |
|---|---|---|
| `misata.prepare_hub_release(directory, repo_id, *, license_id="cc-by-4.0", schema_path=None, allow_fitted=False)` | `HubRelease` | Re-verifies every digest and invariant and assembles the upload. Raises `misata.publish.PublishRefused` when anything does not hold. `write_card()` writes `DATASET_CARD.md`. |
| `misata.publish_to_hub(release, *, private=False, commit_message=None)` | `str` | Uploads the release to the Hugging Face Hub in one commit and returns its URL. [Guide](../guides/publish.md) |

## Export

| Call | What it writes |
|---|---|
| `misata.to_parquet(tables, output_dir, compression="snappy")` | one Parquet file per table |
| `misata.to_duckdb(tables, db_path=None, *, replace=True)` | a DuckDB database; returns the connection |
| `misata.to_jsonl(tables, output_dir, schema=None)` | one JSON Lines file per table, nested columns as objects |
| `misata.to_sql(tables, output_dir, dialect="ansi")` | one `.sql` file per table with `CREATE TABLE` and `INSERT` |
| `misata.to_seed_sql(tables, output_path, *, dialect="postgresql", config=None, truncate=False)` | one seed file, tables in dependency order |
| `misata.to_arrow(tables, output_dir)` | one Arrow IPC file per table |
| `misata.to_polars(tables, schema=None)` | Polars DataFrames, in memory |

For CSV, write each DataFrame with pandas (`df.to_csv(path, index=False)`),
or use `misata generate --format csv`. More in [Export](../export.md).

## Warnings and errors

- `misata.MisataWarning` is the category of every warning Misata emits.
- `misata.ConformanceWarning` marks the ones where a declaration will not
  hold exactly as written. Both subclass `UserWarning`, so
  `warnings.simplefilter("error", misata.ConformanceWarning)` makes them
  fatal in CI.
- `misata.feasibility.InfeasibleSchema` is raised before generation when
  declarations cannot all hold; the CLI exits 3 with the same conflicts.

[When Misata refuses](../failure-modes.md) explains each warning and refusal.
