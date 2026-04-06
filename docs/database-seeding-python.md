# Database Seeding in Python

Misata can generate synthetic data and seed a database directly from Python.

This is useful when you need:
- development data
- staging data
- QA fixtures
- demo environments with relational structure intact

## What Misata Handles

Misata can help with:
- multi-table generation
- referential integrity
- SQLite seeding
- PostgreSQL seeding
- SQLAlchemy-driven schema introspection

## Example

```python
from misata import seed_database
from misata.story_parser import StoryParser

config = StoryParser().parse(
    "A SaaS company with users, subscriptions, invoices, and support tickets"
)

report = seed_database(
    config,
    "sqlite:///./misata_demo.db",
    create=True,
    truncate=True,
    batch_size=5000,
)

print(report.total_rows)
print(report.table_rows)
```

## Why Misata Works Well For Seeding

Database seeding gets painful when child rows point at missing parents or table sizes feel flat and unrealistic.

Misata helps by:
- generating tables in dependency order
- filling foreign keys against valid parent values
- planning realistic row counts when realism planning is enabled
- keeping generation reproducible with a seed

## Related Examples

- [examples/database_seeding_postgres.py](../examples/database_seeding_postgres.py)
- [examples/multi_table_synthetic_data.py](../examples/multi_table_synthetic_data.py)

## Related Docs

- [FEATURES.md](../FEATURES.md)
- [QUICKSTART.md](../QUICKSTART.md)
