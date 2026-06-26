# Using Misata with dbt — Known-Answer Testing

Generate statistically realistic seed data for your dbt project, with exact aggregate targets and full referential integrity.

## Quick Start

```bash
# Install misata
pip install misata

# Generate dbt seeds from a story
misata dbt-seed --story "SaaS company with MRR from $50k to $200k, 20% churn"

# Or generate unit test fixtures
misata dbt-fixture --story "SaaS company" --rows 50

# Then run dbt normally
dbt seed && dbt run && dbt test
```

## What This Example Contains

```
examples/dbt/
├── README.md                      # This file
├── misata.yaml                    # Declared schema + MRR curve (the answer source)
├── dbt_project.yml                # Minimal dbt project config
├── generate_seeds.sh              # One-command seed regeneration
├── seeds/
│   └── expected_mrr.csv           # The answer key (declared monthly targets)
├── models/
│   ├── staging/
│   │   └── stg_subscriptions.sql  # Staging model
│   └── marts/
│       └── monthly_mrr.sql        # MRR aggregation mart
└── tests/
    └── assert_mrr_curve.sql       # Known-answer test (fails if MRR deviates)
```

After `./generate_seeds.sh`, `seeds/` also contains the generated `users.csv`,
`subscriptions.csv`, and `_misata_seeds.yml`. Those are gitignored because they
are regenerated; only `expected_mrr.csv`, the hand-declared answer key, is
tracked.

## The Known-Answer Testing Pattern

This is the workflow that makes Misata + dbt powerful, and it is fully wired in
this example:

1. **Declare** the target in `misata.yaml`: monthly MRR from $50k to $200k, as
   an exact `outcome_curves` spec. `seeds/expected_mrr.csv` mirrors those same
   targets as the answer key.
2. **Generate** seed data where row-level `amount` values sum to those targets
   to the cent (`./generate_seeds.sh`).
3. **Run** the dbt model (`monthly_mrr.sql`) on the generated data (`dbt run`).
4. **Assert** the model reproduces the answer key: `tests/assert_mrr_curve.sql`
   joins `monthly_mrr` against `expected_mrr` and returns any month off by more
   than a cent (`dbt test`).

If `dbt test` passes, your model's `SUM(amount) GROUP BY month` is provably
correct. If it fails, you found the bug before any production data existed.

## Generating Seeds

### From a story
```bash
misata dbt-seed \
  --story "SaaS with 1000 users, MRR from $50k to $200k, 20% churn" \
  --seeds-dir seeds/ \
  --rows 5000 \
  --seed 42
```

This generates:
- `seeds/users.csv` — user records
- `seeds/subscriptions.csv` — subscription records with FK integrity
- `seeds/_misata_seeds.yml` — dbt tests (unique, not_null, relationships)
- `seeds/misata.yaml` — reproducibility artifact

### From a config file
```bash
misata dbt-seed --config misata.yaml --seeds-dir seeds/
```

## Generating Unit Test Fixtures (dbt 1.8+)

```bash
misata dbt-fixture \
  --story "SaaS with 100 users" \
  --rows 30 \
  --output-dir tests/fixtures/
```

This generates:
- `tests/fixtures/users_fixture.csv` — 30 rows
- `tests/fixtures/subscriptions_fixture.csv` — 30 rows
- `tests/fixtures/_unit_tests_example.yml` — copy into your schema.yml

## How It Compares to dbt_synth_data

| Feature | dbt_synth_data | Misata |
|:---|:---:|:---:|
| Exact aggregate targets | ❌ | ✅ |
| Multi-table FK integrity | Limited | ✅ |
| Statistical distributions | Basic | ✅ 10+ |
| Correlations | ❌ | ✅ |
| Time-series patterns | ❌ | ✅ |
| Locale-aware (15 countries) | ❌ | ✅ |
| ML-safe data | ❌ | ✅ |
| Runs in-warehouse | ✅ | ❌ (pre-seed) |

## Tips

- **Seed size limit**: dbt seeds work best under 1 MB (~10K rows). For larger datasets, use `misata generate --db-url postgresql://...` and declare a dbt source instead.
- **Reproducibility**: The generated `misata.yaml` lets anyone on your team regenerate identical seeds with `misata dbt-seed --config seeds/misata.yaml`.
- **CI/CD**: Add `pip install misata && misata dbt-seed --config seeds/misata.yaml --force` before `dbt seed` in your CI pipeline.
- **dbt version**: the generated `_misata_seeds.yml` uses the dbt 1.9+ `arguments:` test format. This example is verified end to end on dbt 1.11 with `dbt-duckdb` (`dbt seed && dbt run && dbt test` all green).
