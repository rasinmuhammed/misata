---
title: Generate Synthetic Data from SQL DDL | Misata
description: Use misata.from_ddl() to parse CREATE TABLE statements and generate synthetic data that matches your real database schema, no YAML authoring required.
---

# Generate Synthetic Data from SQL DDL

`misata.from_ddl()` parses SQL `CREATE TABLE` statements and converts them into a `SchemaConfig` ready for data generation. Paste your real schema DDL and get synthetic data that matches your database structure, column types, foreign key relationships, and NOT NULL constraints all preserved.

## Quick start

```python
import misata

schema = misata.from_ddl("""
    CREATE TABLE users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        created_at TIMESTAMP
    );

    CREATE TABLE orders (
        id SERIAL PRIMARY KEY,
        user_id INT REFERENCES users(id),
        amount DECIMAL(10, 2),
        status VARCHAR(50),
        placed_at TIMESTAMP
    );
""")

tables = misata.generate_from_schema(schema)
print(tables["users"].head())
print(tables["orders"].head())

# FK integrity guaranteed
assert tables["orders"]["user_id"].isin(tables["users"]["id"]).all()
```

## Supported SQL dialects

- **PostgreSQL**: `SERIAL`, `BIGSERIAL`, `TIMESTAMP WITH TIME ZONE`, schema-qualified names, `"quoted"` identifiers
- **MySQL**: `INT AUTO_INCREMENT`, `DATETIME`, `TINYINT`
- **SQLite**: `INTEGER PRIMARY KEY`, `TEXT`, `REAL`
- **Generic ANSI SQL**: standard `CREATE TABLE` with `REFERENCES` clauses

## SQL type mapping

| SQL types | Misata type |
|:--|:--|
| `INT`, `INTEGER`, `BIGINT`, `SMALLINT`, `SERIAL` | `int` |
| `FLOAT`, `REAL`, `DOUBLE`, `DECIMAL`, `NUMERIC`, `MONEY` | `float` |
| `VARCHAR`, `TEXT`, `CHAR`, `STRING`, `UUID`, `JSON`, `JSONB` | `text` |
| `DATE` | `date` |
| `TIMESTAMP`, `DATETIME` (any variant) | `date` |
| `BOOLEAN`, `BOOL` | `boolean` |

## Foreign key detection

Three sources of FK relationships are supported:

**1. Inline `REFERENCES` clause:**
```sql
user_id INT REFERENCES users(id)
```

**2. Standalone `FOREIGN KEY` constraint:**
```sql
FOREIGN KEY (user_id) REFERENCES users(id)
```

**3. Naming convention inference (`infer_fks=True`, default):**

Columns ending in `_id` that don't have an explicit `REFERENCES` clause are automatically inferred as foreign keys to the table named by the prefix:

```sql
-- order_id → orders(id) inferred automatically
order_id INT
```

Disable with `infer_fks=False` if you don't want this behavior.

## Configuration

```python
schema = misata.from_ddl(
    ddl,
    infer_fks=True,       # infer FKs from _id naming convention (default True)
    default_rows=1000,    # row count per table (default 1000)
)
```

Adjust per-table row counts after parsing:

```python
schema = misata.from_ddl(ddl)
# Customize row counts
for table in schema.tables:
    if table.name == "users":
        table.row_count = 5000
    elif table.name == "orders":
        table.row_count = 20000

tables = misata.generate_from_schema(schema)
```

## Full example: PostgreSQL schema

```python
import misata

schema = misata.from_ddl("""
    CREATE TABLE public.customers (
        id          BIGSERIAL PRIMARY KEY,
        email       VARCHAR(255) NOT NULL,
        country     VARCHAR(2),
        created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    CREATE TABLE public.products (
        id          BIGSERIAL PRIMARY KEY,
        name        TEXT NOT NULL,
        price       NUMERIC(10, 2) NOT NULL,
        category    VARCHAR(100),
        created_at  TIMESTAMP WITH TIME ZONE
    );

    CREATE TABLE public.orders (
        id          BIGSERIAL PRIMARY KEY,
        customer_id BIGINT NOT NULL REFERENCES public.customers(id),
        status      VARCHAR(50) DEFAULT 'pending',
        total       NUMERIC(12, 2),
        placed_at   TIMESTAMP WITH TIME ZONE
    );

    CREATE TABLE public.order_items (
        id          BIGSERIAL PRIMARY KEY,
        order_id    BIGINT NOT NULL REFERENCES public.orders(id),
        product_id  BIGINT NOT NULL REFERENCES public.products(id),
        quantity    INT NOT NULL DEFAULT 1,
        unit_price  NUMERIC(10, 2) NOT NULL
    );
""", default_rows=500)

# Scale appropriately
for t in schema.tables:
    if t.name == "order_items":
        t.row_count = 2000

tables = misata.generate_from_schema(schema, min_quality_score=80)
for name, df in tables.items():
    print(f"{name}: {len(df)} rows")
```

## Export to your database

Generate and seed directly:

```python
import misata

schema = misata.from_ddl(open("schema.sql").read())
tables = misata.generate_from_schema(schema)

# Seed PostgreSQL
misata.seed_database(tables, "postgresql://user:pass@localhost/mydb")
```

## Limitations

- **Computed / generated columns**: `GENERATED ALWAYS AS` expressions are not evaluated; the column is treated as its base type
- **`CHECK` constraints**: parsed but not enforced during generation; use `misata.yaml` for custom constraint rules
- **Enum types**: `CREATE TYPE ... AS ENUM` is not parsed; use `misata.yaml` to define categorical choices
- **Complex DEFAULT expressions**: `DEFAULT NOW()`, `DEFAULT uuid_generate_v4()` are ignored; Misata generates values from type-appropriate distributions

## Related

- [YAML Schema](../generation/yaml.md), full control over distributions and constraints
- [Database Seeding](database-seeding-python.md), seed your generated data into a real database
- [Validate](../validate.md), verify generated data quality
