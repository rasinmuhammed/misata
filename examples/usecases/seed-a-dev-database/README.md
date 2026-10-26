---
title: Seed a Dev Database From Its DDL
description: Fill a development or CI database straight from its CREATE TABLE statements, with every foreign key, CHECK rule, UNIQUE and NOT NULL holding, and a certificate that proves it.
---

# Seed a dev database from its DDL

You have the schema. You do not have data you are allowed to use, and a
Faker script breaks the first CHECK constraint it meets. Misata reads the
DDL itself, so the rules in it are the rules the data follows.

**Who:** application developers and coding agents setting up a local, CI or
preview database.
**Time:** about a second for 6,000 rows.

## The schema

`schema.sql` is plain DDL. Nothing about it is written for Misata:

```sql
CREATE TABLE accounts (
  id SERIAL PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  plan VARCHAR(10) NOT NULL CHECK (plan IN ('free', 'team', 'enterprise')),
  created_at TIMESTAMP NOT NULL
);
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  account_id INT NOT NULL REFERENCES accounts(id),
  email VARCHAR(200) NOT NULL UNIQUE,
  role VARCHAR(10) NOT NULL CHECK (role IN ('owner', 'admin', 'member'))
);
CREATE TABLE invoices (
  id SERIAL PRIMARY KEY,
  account_id INT NOT NULL REFERENCES accounts(id),
  amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
  issued_on DATE NOT NULL,
  due_on DATE NOT NULL,
  CHECK (due_on > issued_on)
);
```

## Run it

See what will be generated, then generate it:

```bash
pip install "misata[duckdb]"
misata explain schema.sql --seed 7
misata generate -c schema.sql -o out -n 2000 --seed 7 --format duckdb --attest
```

`out/data.duckdb` holds all three tables. To seed a real database instead,
point the same command at it. Tables are created in dependency order and
loaded in one transaction:

```bash
misata generate -c schema.sql -n 2000 --seed 7 --db-url postgresql://localhost/dev --db-create
```

## The check

`--attest` already checked the files. Run it again, or hand the folder to
someone without Misata and let them run the verifier:

```bash
misata attest out -s schema.sql
python out/verify.py
```

```text
ok    1 file(s) match their attested sha256
ok    22 of 22 invariant(s) hold
```

The 22 invariants come from the DDL alone:

| Rule in the DDL | Invariants |
|---|---|
| `REFERENCES accounts(id)` | 2: no user or invoice points at a missing account |
| `PRIMARY KEY`, `UNIQUE` | 4: no id or email appears twice |
| `CHECK (... IN (...))` | 2: every plan and role is a declared value |
| `CHECK (due_on > issued_on)` | 1: no invoice is due before it is issued |
| `NOT NULL` | 13: no null in any declared column |

Each one is a DuckDB query in `out/attestation.intoto.json` whose answer
must be 0. Same schema, same seed and same Misata version give the same
rows, so a CI job can seed, attest and compare `misata.fingerprint`.

## From Python

```python
import misata

schema = misata.from_ddl(open("schema.sql").read(), default_rows=2000)
schema.seed = 7
tables = misata.generate_from_schema(schema)
```
