---
title: Database Seeding in Python — Seed PostgreSQL and SQLite with Synthetic Data
description: Learn how to seed a PostgreSQL or SQLite database with realistic synthetic data in Python using Misata. Covers FK relationships, reproducible seeds, and CI/CD integration.
---

# Database Seeding in Python

Misata generates synthetic relational data and loads it directly into a database.
No migration scripts. No manual INSERT loops. No orphan rows.

## Quick start

```python
import misata
from misata import seed_database

# Generate + seed in two lines
tables = misata.generate("A SaaS company with 1000 users.", seed=42)
report = seed_database(tables, "sqlite:///./dev.db", create=True)

print(report.total_rows)   # 6,000+
print(report.table_rows)   # {"users": 1000, "subscriptions": 3000, ...}
```

## Supported databases

Misata uses SQLAlchemy under the hood — any SQLAlchemy-compatible database works:

```python
# SQLite (local dev)
seed_database(tables, "sqlite:///./local.db", create=True)

# PostgreSQL
seed_database(tables, "postgresql://user:pass@localhost/mydb", create=True)

# MySQL / MariaDB
seed_database(tables, "mysql+pymysql://user:pass@localhost/mydb", create=True)
```

## Truncate before seeding (CI / staging)

```python
report = seed_database(
    tables,
    "postgresql://user:pass@staging-db/app",
    create=True,    # CREATE TABLE IF NOT EXISTS
    truncate=True,  # TRUNCATE before INSERT
)
```

Use `truncate=True` in CI pipelines to reset the database to a known state before
each test run.

## Seed from a story (CLI)

```bash
misata generate \
  --story "A SaaS company with 1000 users" \
  --rows 1000 \
  --db-url sqlite:///./dev.db \
  --db-create \
  --db-truncate
```

## Seed into existing SQLAlchemy models

If your project already uses SQLAlchemy ORM models, Misata can introspect them and
seed against the existing schema:

```python
from misata import seed_from_sqlalchemy_models
from myapp.models import Base, engine

report = seed_from_sqlalchemy_models(
    Base,
    engine,
    story="A SaaS company with 500 users",
    truncate=True,
)
print(report.total_rows)
```

## Introspect an existing database

Misata can read a live database and generate a matching SchemaConfig, then generate
data that fits your existing table structure:

```python
from misata import schema_from_db, generate_from_schema

schema = schema_from_db("postgresql://user:pass@localhost/mydb")
print(schema.summary())  # shows your real table structure

# Generate data that matches your actual schema
tables = generate_from_schema(schema)
```

## Why Misata works well for seeding

Database seeding breaks in predictable ways:

| Problem | What usually happens | Misata |
|---|---|---|
| FK violations | Child rows reference missing parents | Tables generated in dependency order; FK values sampled from valid parent pool |
| Flat distributions | All rows look the same | Domain priors: log-normal amounts, Zipf categories, real demographic frequencies |
| Scale mismatch | Child table has wrong number of rows | Row counts planned proportionally per relationship |
| Repeatability | Tests produce different data each run | `seed=42` makes generation fully deterministic |

## Batch size control

For large databases, control memory usage with `batch_size`:

```python
report = seed_database(
    tables,
    "postgresql://user:pass@localhost/prod_clone",
    batch_size=10_000,  # INSERTs in batches of 10k rows
    create=True,
    truncate=True,
)
```

## Example: seed a test database in pytest

```python
# conftest.py
import pytest
import misata
from misata import seed_database
from sqlalchemy import create_engine

@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine("sqlite:///./test.db")
    return engine

@pytest.fixture(scope="session", autouse=True)
def seed_test_db(db_engine):
    tables = misata.generate("A SaaS company with 100 users.", seed=42)
    seed_database(tables, db_engine, create=True, truncate=True)
```

Every test run starts from a fresh, realistic seed. `seed=42` means the data is
identical across runs, so test assertions stay stable.

## Related

- [Multi-table synthetic data](multi-table-synthetic-data.md)
- [Python synthetic data generator](python-synthetic-data-generator.md)
- [Faker vs SDV vs Misata](faker-vs-sdv-vs-misata.md)
