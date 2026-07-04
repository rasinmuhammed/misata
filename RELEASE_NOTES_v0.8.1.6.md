# Misata 0.8.1.6: Known-Answer Testing for dbt

This release makes Misata a first-class companion to dbt. Declare the answer in
a schema, generate the seed data that hits it exactly, run your dbt model, and
assert the model reproduced the number you declared. Two new CLI commands wire
Misata into a dbt project, and a complete example proves the loop end to end:
`dbt seed && dbt run && dbt test`, all green, with a known-answer test that fails
the build the moment a metric drifts.

## What changed

### New: `misata dbt-seed`

Generate synthetic data straight into a dbt project's `seeds/` directory, from a
story or a declared schema.

```bash
misata dbt-seed --config misata.yaml          # declared outcome curves, exact aggregates
misata dbt-seed --story "SaaS with 20% churn" # or from one sentence
```

- **Auto-detects the dbt project**, reading `seed-paths` from `dbt_project.yml`.
- **Generates `_misata_seeds.yml`** with `unique`, `not_null`, and
  `relationships` tests inferred from the schema's primary keys and foreign keys.
- **Writes a reproducibility `misata.yaml`** so a teammate or CI can regenerate
  identical seeds.
- **Warns on seed size**, since dbt seeds are meant for small reference tables.
  For larger datasets it points you to `misata generate --db-url ...` plus a dbt
  source.

### New: `misata dbt-fixture`

Generate dbt 1.8+ unit-test fixture CSVs plus an example `unit_tests` YAML block
showing how to wire them in. Misata produces the realistic `given` inputs (the
tedious part); you define the `expect`.

```bash
misata dbt-fixture --story "Ecommerce, 5% returns" --rows 50
```

### dbt 1.9+ test format

The generated `relationships` test now nests its arguments under the `arguments`
property, the current dbt form. No `MissingArgumentsPropertyInGenericTestDeprecation`
warning on dbt 1.11 or dbt Fusion.

### New: a verified known-answer example (`examples/dbt/`)

A complete, runnable project that demonstrates the whole pattern:

- `misata.yaml` declares the answer: monthly MRR climbs from \$50k to \$200k, to
  the cent, as an exact `outcome_curves` spec.
- `seeds/expected_mrr.csv` is the answer key.
- `models/` transform the seeds into a `monthly_mrr` mart.
- `tests/assert_mrr_curve.sql` is the known-answer test: it returns any month
  whose modelled MRR deviates from the declared target by more than a cent, so
  `dbt test` fails if the model's math is wrong.

Verified end to end on dbt 1.11 with `dbt-duckdb`: `dbt seed` (3 pass),
`dbt run` (2 models), `dbt test` (5 pass, including the known-answer test). A
zero-setup DuckDB `profiles.yml` ships with the example, so anyone can clone it,
`pip install dbt-duckdb`, and watch it go green with no warehouse.

### `misata/dbt.py`

A new module exposing the integration as a library, not just a CLI:
`detect_dbt_project`, `generate_dbt_schema_yml`, `generate_dbt_fixtures`, and
seed-size intelligence (`SeedSizeReport`).

## Install

```bash
pip install misata==0.8.1.6
```

To run the example:

```bash
pip install dbt-duckdb
cd examples/dbt && DBT_PROFILES_DIR=. dbt seed && dbt run && dbt test
```

## Scope, honestly

- The integration targets **dbt Core** (self-hosted / CI). dbt Cloud cannot run
  arbitrary `pip install` steps.
- dbt seeds are for small fixtures. The example generates ~5.8k rows; for large
  datasets, load directly to your warehouse and declare a dbt source instead.
- Misata generates the **inputs and the declared answer**. It does not infer
  your model's SQL, so for unit tests you still define the expected output.

## Verification

The dbt integration adds 29 tests covering project detection, schema.yml test
generation, fixtures, and seed-size reporting. The example is verified green end
to end on dbt 1.11 with `dbt-duckdb`.

**Full Changelog**: https://github.com/rasinmuhammed/misata/compare/v0.8.1.5...v0.8.1.6
