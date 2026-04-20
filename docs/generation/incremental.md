# Incremental Generation

Grow an existing dataset without regenerating from scratch. IDs auto-offset, FK integrity is maintained across both batches.

```python
import misata

# Initial seed
schema = misata.parse("A fintech company with 1000 customers", rows=1000)
tables = misata.generate_from_schema(schema, seed=1)
print(len(tables["customers"]))  # 1000

# Add 1000 more rows later
tables = misata.generate_more(tables, schema, n=1000, seed=2)
print(len(tables["customers"]))  # 2000
```

## How IDs are handled

`generate_more` offsets integer `id` columns in the new batch so they don't collide with existing rows:

```python
existing_max_id = tables["customers"]["id"].max()   # e.g. 1000
# New batch IDs start from 1001 automatically
```

## Use cases

- **Streaming test fixtures** — generate a baseline, then add rows as tests progress
- **Dataset growth simulation** — model a platform growing from 1k → 100k users over time
- **Append-only seeding** — add rows to a live dev database without truncating

!!! warning "Seed independence"
    Each call to `generate_more` uses a different seed (`schema.seed + 1` by default). Pass an explicit `seed` for full reproducibility across calls.
