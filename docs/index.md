---
title: Misata — Python Synthetic Data Generator
description: Generate realistic multi-table synthetic data from plain English, YAML, or your own database. The best Faker alternative for test data, database seeding, and ML datasets. Free and open-source.
---

# Misata — Python Synthetic Data Generator

**Realistic multi-table synthetic data — from a sentence, a YAML file, or your own database.**

No ML model. No real data needed. Referential integrity guaranteed across every table.

---

=== "Plain English"

    ```python
    import misata

    tables = misata.generate(
        "A SaaS company with 5k users, monthly subscriptions, and 20% churn"
    )
    print(tables["users"].head())
    print(tables["subscriptions"].head())
    ```

=== "YAML Schema"

    ```yaml
    # misata.yaml
    name: my-app
    seed: 42

    tables:
      users:
        rows: 1000
        columns:
          user_id: { type: int, unique: true }
          email:   { type: text, text_type: email }
          plan:    { type: categorical, choices: [free, pro, enterprise] }
      orders:
        rows: 5000
        columns:
          order_id: { type: int, unique: true }
          user_id:  { type: foreign_key }
          amount:   { type: float, min: 5.0, max: 500.0 }

    relationships:
      - "users.user_id → orders.user_id"
    ```

    ```python
    schema = misata.load_yaml_schema("misata.yaml")
    tables = misata.generate_from_schema(schema)
    ```

=== "From a Database"

    ```python
    from misata import schema_from_db, generate_from_schema, seed_database

    schema = schema_from_db("postgresql://user:pass@localhost/myapp")
    tables = generate_from_schema(schema)
    report = seed_database(tables, "postgresql://user:pass@localhost/myapp_dev")
    # SeedReport: seeded 6 tables, 47,300 rows in 1.2s
    ```

---

## Install

```bash
pip install misata
```

[Get started →](quickstart.md){ .md-button .md-button--primary }
[View on GitHub →](https://github.com/rasinmuhammed/misata){ .md-button }

---

## Why Misata over Faker or SDV?

Faker generates one column at a time — you write the loop, manage the IDs, enforce uniqueness yourself.
SDV requires real training data and a fitted model before you get anything.
**Misata generates a complete relational dataset from a single sentence — no training data, no boilerplate.**

| Feature | Faker | SDV | **Misata** |
|:--|:--:|:--:|:--:|
| One-liner multi-table generation | — | — | **✓** |
| Story auto-detects locale + country stats | — | — | **✓** |
| YAML schema committed to git | — | — | **✓** |
| DB introspection → generate → re-seed | — | Limited | **✓** |
| Direct PostgreSQL / SQLite seeding | — | — | **✓** |
| FK integrity across all tables | — | **✓** | **✓** |
| Fully offline, no LLM required | **✓** | **✓** | **✓** |
| Time-series generation | — | — | **✓** |
| 15 country locale packs | — | — | **✓** |
| CSV quality validation | — | — | **✓** |

---

## What people use Misata for

- **Test data generation** — seed your dev/staging database with realistic data in seconds
- **BI and dashboard demos** — populate a demo environment with coherent, believable numbers
- **Machine learning datasets** — create labelled training data without touching real user data
- **Database seeding in CI/CD** — reproducible, seed-controlled datasets for every test run
- **Privacy-safe development** — work with realistic schemas without exposure to PII

---

## Supported domains

Misata auto-detects your domain from the story and applies statistically accurate priors:

`saas` · `ecommerce` · `fintech` · `healthcare` · `marketplace` · `logistics` · `hr` · `social` · `realestate`

[See all domains →](domains.md)
