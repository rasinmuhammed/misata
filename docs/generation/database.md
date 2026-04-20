# Database Seeding

Point Misata at an existing database schema and fill a dev or staging environment with production-like data — FK ordering handled automatically.

## Introspect and seed

```python
from misata import schema_from_db, generate_from_schema, seed_database

# Read your live schema — no column definitions needed
schema = schema_from_db("postgresql://user:pass@localhost/myapp")
tables = generate_from_schema(schema)

report = seed_database(tables, "postgresql://user:pass@localhost/myapp_dev")
print(report)
# SeedReport: seeded 6 tables, 47,300 rows in 1.2s
```

## CLI workflow

```bash
# Step 1 — introspect into a YAML file
misata init --db postgresql://user:pass@localhost/myapp

# Step 2 — review / edit misata.yaml, then seed
misata generate --db-url postgresql://user:pass@localhost/myapp_dev --db-create
```

## SQLAlchemy models

```python
from misata import seed_from_sqlalchemy_models
from myapp.models import Base

report = seed_from_sqlalchemy_models(
    Base,
    db_url="sqlite:///test.db",
    row_count=500,
    create_tables=True,
)
```

## Read back from a database

```python
from misata import load_tables_from_db

tables = load_tables_from_db("postgresql://user:pass@localhost/myapp_dev")
print(tables["orders"].head())
```

## Supported databases

- **PostgreSQL** — `pip install "misata[db]"` (psycopg3)
- **MySQL / MariaDB** — via SQLAlchemy `pip install "misata[orm]"`
- **SQLite** — built-in, no extras needed
- Any SQLAlchemy-compatible engine

!!! note "FK insert order"
    Misata performs a topological sort on the relationship graph before inserting, so parent rows always exist before child rows are inserted. Circular FK references raise a `ConfigurationError`.
