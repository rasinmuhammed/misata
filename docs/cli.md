---
title: "Misata CLI Reference: generate, explain, attest, solve, evalpack, publish"
description: "Every Misata command-line command: generate synthetic data from DDL, YAML or a sentence, seed databases, explain a schema, attest files, solve for pipeline targets, build evalpacks and publish, with JSON output and exit codes."
---

# CLI Reference

```bash
pip install "misata[duckdb]"   # DuckDB and Parquet: attest, evalpack, --format parquet and duckdb
misata --help
```

## JSON output and exit codes

Every command except the servers (`serve`, `studio`, `mcp run`) takes
`--json`, or reads `MISATA_JSON=1` from the environment, and then prints
exactly one JSON document on stdout:

```json
{
  "envelope": 1,
  "ok": false,
  "command": "misata generate",
  "exit_code": 3,
  "code": "infeasible",
  "message": "1 declaration cannot be satisfied together: ...",
  "conflicts": [{"kind": "unique_range_too_narrow", "where": "a.code",
                 "declarations": ["unique + min/max on code", "row_count on a"],
                 "arithmetic": "10 unique values needed but the range [1, 5] holds only 5",
                 "remedy": "raise max to at least 10, lower row_count to 5, or drop unique"}],
  "hint": "Nothing was generated. Change the declarations each conflict names; its remedy says how.",
  "data": null,
  "warnings": [],
  "text": "what the command would have printed",
  "misata_version": "0.9.8"
}
```

`data` holds the command's result (`generate` lists each table's rows and
files, `attest` the summary and the Statement, `explain` the plan, `lint` the
findings). `warnings` collects every warning raised during the run. The JSON
Schema ships in the package at `misata/_schemas/cli-envelope.schema.json`.

The exit code means the same thing with or without `--json`:

| Exit | `code` | Meaning |
|---|---|---|
| 0 | `ok` | the command did what was asked |
| 1 | `failed` | it ran and a check failed, or it could not finish |
| 2 | `usage` | bad arguments, or input it could not read |
| 3 | `infeasible` | the declarations cannot all hold; nothing was written |

---

## `misata explain`

What a schema will generate, without generating it: each table's planned
row count and approximate memory, the declarations and the columns each one
writes, curve plans and their warnings, and how many invariants an
attestation will check. Exits 3, naming every conflict, when generation
would refuse.

```bash
misata explain misata.yaml
misata explain misata.yaml --json     # data.explanation
```

The same plan is `misata.explain(schema)` in Python and the MCP tool
`explain_schema`.

---

## `misata solve`

Move outcome curves until a pipeline's metrics hit their targets. The
pipeline is DuckDB SQL over the generated tables or a dbt project; see
[Solve for a pipeline's output](guides/solve.md).

```bash
misata solve -c solve.yaml
misata solve -c solve.yaml -o solved --format parquet   # data, solved spec, certificate
misata solve -c solve.yaml --max-iterations 40 --json   # data.solve has every iteration
```

Exits 0 when every period is within tolerance, 1 when the run stops short
(`max_iterations`, `diverging`, `unresponsive`, `pipeline_error`), 2 for a
config it cannot use, and 3 when the schema cannot generate.

---

## `misata init`

Scaffold a `misata.yaml` schema file.

```bash
misata init                                          # blank template
misata init --story "A marketplace with sellers"     # story → YAML
misata init --db postgresql://localhost/myapp        # DB introspection → YAML
misata init --output custom.yaml                     # custom output path
misata init --force                                  # overwrite existing file
```

---

## `misata generate`

Generate data and write to files or a database.

```bash
misata generate                                      # reads misata.yaml
misata generate --story "A SaaS company with 5k users" --rows 5000
misata generate --output-dir data/
misata generate --locale de_DE                       # force locale
misata generate --seed 42
misata generate --db-url postgresql://localhost/dev --db-create
misata generate --format parquet --partition-by status   # pip install "misata[parquet]"
misata generate --format duckdb                          # pip install "misata[duckdb]"
misata generate -c schema.sql -o out --attest           # SQL DDL: keys, CHECKs, NOT NULL
```

| Flag | Default | Description |
|:--|:--|:--|
| `--story` | none | Plain-English story |
| `--rows` | 10 000 | Row count for primary table |
| `--locale` | auto-detected | BCP-47 locale code (e.g. `de_DE`) |
| `--seed` | random | Integer seed for reproducibility |
| `--output-dir` | `.` | Directory to write output files |
| `--format` | `csv` | `csv`, `jsonl` and `parquet` write one file per table; `jsonl` keeps nested columns as objects and lists; `duckdb` (DuckDB 1.3 or later) writes every table into `data.duckdb`. Rows are written as they are generated, so output size is bounded by disk, not memory |
| `--partition-by` | none | With `--format parquet`, tables that have this column are written Hive-style: `orders/status=paid/part-00000.parquet`, one file per partition with a row group per batch. A column with more than 10,000 values is refused |
| `--db-url` | none | Database URL for direct seeding |
| `--db-create` | false | Create tables if they don't exist |
| `--attest` | false | Attest the written files against the schema; exits 1 if a declaration does not hold |

---

## `misata seed`

Fill a live Postgres or SQLite database from its own schema: tables and
foreign keys are read from the database, rows are inserted parents first in
one transaction, and every foreign key is checked against the database
afterwards. See [Seed a live database](guides/seed-a-live-database.md).

```bash
misata seed postgresql://localhost/myapp_dev --dry-run      # the plan, nothing written
misata seed postgresql://localhost/myapp_dev --rows 500
misata seed sqlite:///dev.db --skip schema_migrations
misata seed postgresql://localhost/myapp_dev --append       # keep populated tables
misata seed postgresql://localhost/myapp_dev --truncate --yes
```

A table that already has rows is refused unless you pass `--truncate`
(wipe it first) or `--append` (leave it and fill only the empty tables).

---

## `misata attest`

Check written files against the schema that generated them and record the
result as an in-toto Statement. See [Attest a dataset](guides/attest.md).

```bash
misata generate -c misata.yaml -o out
misata attest out --schema misata.yaml
misata attest out --schema misata.yaml --export odcs --export openlineage
misata attest out --schema misata.yaml --json        # envelope; data.statement is the Statement
```

Writes `attestation.intoto.json`, `attestation.dsse.json` and `verify.py`
into the folder. Exits 0 when every invariant holds, 1 when one does not,
and 2 when the folder cannot be attested.

---

## `misata publish`

Upload an attested dataset or an evalpack to the Hugging Face Hub with its
spec, attestation, `verify.py` and a generated dataset card. Every digest
and invariant is re-checked first. See
[Publish to Hugging Face](guides/publish.md).

```bash
misata publish out --hf acme/shop --schema misata.yaml --dry-run   # writes DATASET_CARD.md
misata publish out --hf acme/shop --schema misata.yaml --private
misata publish pack --hf acme/retail-answer-key --license cc-by-4.0
```

Needs `pip install "misata[hf]"` and `hf auth login` or `HF_TOKEN`. Exits 0
when published, 1 when the data does not verify or the Hub refuses, and 2
when the attestation or spec is missing or the folder holds `misata mimic`
output without `--allow-fitted`.

---

## `misata evalpack`

Build a text-to-SQL evaluation pack whose answers come from the schema's
declarations and are verified against the written files with DuckDB. See
[Build an evalpack](guides/evalpack.md).

```bash
misata evalpack -c misata.yaml -o pack --seed 42
misata evalpack -c misata.yaml -o pack --seed 42 --rotations 3
python pack/verify.py --candidates answers.jsonl
```

`--rotations N` writes N databases that share every answer, and a query
counts as correct only when it matches on all of them. Exits 1 when no
question verifies.

---

## `misata audit` and `misata realism`

Two checks for any folder of CSVs, whoever generated it.

```bash
misata audit out                         # reader-visible contradictions
misata audit out --schema misata.yaml --strict
misata realism out                       # statistical tells of generated data
misata realism out --json                # the report is data.realism
```

`audit` finds what a reader would notice: an order shipped before it was
placed, a churn date on an active subscription, and with a schema, orphaned
foreign keys and parent totals that disagree with their children. `realism`
finds shapes real data almost never has: flat weekdays, uniform amounts,
every customer with the same number of orders. See the
[realism report](realism.md).

---

## `misata lint`

Check a schema file for declarations that cannot hold, before generating
anything.

```bash
misata lint misata.yaml
misata lint misata.yaml --strict
```

---

## `misata sandbox`

Create a SQLite database for an agent or a person to query. It refuses to
overwrite a database it did not create, and queries run read-only. With
`-c`, it holds the same rows as `misata generate` and an evalpack's first
rotation for that schema, so an agent's SQL returns the same number in the
sandbox and in the grader.

```bash
misata sandbox -c misata.yaml --db sandbox.db
misata sandbox -c misata.yaml --db sandbox.db --sql "SELECT COUNT(*) FROM orders"
misata sandbox --domain saas --rows 250
```

See [A sandbox an AI agent can act in](usecases/agent-sandbox.md).

---

## `misata mimic`

Generate a twin of a CSV file. The twin is fitted to the real rows, reuses
their category values and quantiles, and is not anonymous. It writes
`fitted.json` beside the output, and `misata publish` refuses that folder
without `--allow-fitted`. See [Mimic](guides/mimic.md).

```bash
misata mimic customers.csv --rows 100000 --output ./synthetic --seed 42
```

---

## `misata provenance`

Print what a dataset was made from, for a security or data-sharing review.
Without a folder it prints the statement: generation from a schema reads no
rows and needs no network, and the same version, schema and seed give the
same bytes. With a folder it adds the inputs the attestation records
(Misata version, schema hash, seed, result), whether `misata mimic` fitted
it to real rows, and a sha256 and row count for every data file.

```bash
misata provenance
misata provenance out
misata provenance out --json
```

Regenerating the folder and comparing the hashes shows the schema and seed
were the whole input. See [Data provenance](data-provenance.md) for the full
statement and [PII-free staging and test environments](usecases/pii-free-environments.md)
for the review it supports.

---

## `misata validate`

Profile a CSV and optionally check it against a schema.

```bash
misata validate customers.csv
misata validate orders.csv --schema misata.yaml
misata validate orders.csv --story "A SaaS company with orders table"
misata validate orders.csv --table orders            # specify table name in schema
```

---

## `misata template`

Generate from a built-in industry template.

```bash
misata template saas --scale 0.1 --output-dir data/
misata template fintech --scale 2.0                  # 2x the template's row counts
```

---

## `misata templates-list`

List all available industry templates.

```bash
misata templates-list
```

---

## `misata schema`

Introspect a database and print or save the schema.

```bash
misata schema --db-url postgresql://localhost/myapp
misata schema --db-url postgresql://localhost/myapp --output schema.yaml
```

---

## `misata studio`

Launch the visual schema designer (requires `pip install "misata[studio]"`).

```bash
misata studio
misata studio --port 8080 --no-browser
```

---

## Other commands

| Command | What it does | Read |
|---|---|---|
| `misata dbt-seed` | generate into a dbt `seeds/` directory | [dbt seed integration](guides/dbt-seed.md) |
| `misata dbt-unit-test` | fixtures for dbt `unit_tests:` from your project's `target/manifest.json` | [Known-answer tests for dbt](usecases/dbt-known-answer-tests.md) |
| `misata dbt-fixture` | dbt 1.8+ unit test fixture CSVs from a story or schema | [dbt seed integration](guides/dbt-seed.md) |
| `misata dbt-mutate` | measure whether your data tells correct SQL from plausible wrong SQL | |
| `misata prisma-seed` | seed data from a Prisma schema | |
| `misata mcp` | the MCP server for AI agents | [MCP server](guides/mcp.md) |
| `misata serve` | the REST API, on 127.0.0.1 unless you pass `--host` | [REST API](guides/rest-api.md) |

`misata COMMAND --help` lists every option.
