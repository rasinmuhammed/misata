---
title: "Stream Millions of Rows of Synthetic Data in Bounded Memory"
description: "Generate datasets larger than memory with generate_stream or misata generate --format parquet, csv, jsonl or duckdb, with one-hop roll-ups reconciled while streaming."
---

# Streaming Large Synthetic Datasets

`misata.generate_stream()` yields `(table_name, batch_df)` tuples one batch at a time, the full dataset is never held in memory. This is the right interface for generating 10M+ row datasets, writing directly to Parquet, or streaming into a database without buffering.

## When to use streaming vs standard generation

| | `misata.generate()` | `misata.generate_stream()` |
|:--|:--|:--|
| Return type | `dict[str, DataFrame]` | Generator of `(name, DataFrame)` |
| Memory usage | Full dataset in RAM | One batch of each child table; parent tables whole |
| Suitable for | < 1M rows, interactive use | 1M+ rows, pipelines, ETL |
| Supports `min_quality_score` | ✓ | ✗ (retry requires full buffering) |

## Quick start

```python
import misata

# Stream 5M rows without loading everything into memory
for table_name, batch in misata.generate_stream(
    "An ecommerce store with many customers",
    rows=5_000_000,
    seed=42,
):
    print(f"{table_name}: {len(batch)} rows in this batch")
```

## Stream directly to Parquet

From the command line, `--format` writes each batch as it is generated:

```bash
misata generate -c misata.yaml -o large_dataset --format parquet   # pip install "misata[parquet]"
```

From Python, a sink does the same: one Parquet writer per table, each batch
appended as a row group, nothing read back.

```python
import misata
from misata.sinks import open_sink

schema = misata.parse("A SaaS company with many users", rows=2_000_000)
with open_sink("parquet", "large_dataset", schema) as sink:
    for table_name, batch in misata.generate_stream(schema, seed=42):
        sink.write(table_name, batch)
print(sink.rows)
```

`open_sink` also takes `"csv"`, `"jsonl"` and `"duckdb"`, and
`partition_by="column"` for Hive-style Parquet folders.

## How fast, and how much memory

Measured on an Apple M1 with 8 GB, generating a fourteen-table retail
schema to Parquet and then checking every key, every order's line items and
every order total with DuckDB over the written files:

| Rows | Seconds | Peak memory |
|--:|--:|--:|
| 1,000,000 | 2.1 | 0.5 GB |
| 10,000,000 | 34 | 1.0 GB |

```bash
python benchmarks/bench_r3_volume.py --scale 10 --stream out/
```

Child rows are held one batch at a time. A table that children reference
(customers for orders, orders for line items) is held whole until its
children are done, so memory follows the size of the parent tables rather
than the total row count.

## Stream into a database

```python
import misata
import sqlalchemy as sa

engine = sa.create_engine("postgresql://user:pass@localhost/bigdb")

for table_name, batch in misata.generate_stream(
    "A logistics company with 5M shipments",
    rows=5_000_000,
    seed=42,
):
    batch.to_sql(
        table_name,
        engine,
        if_exists="append",
        index=False,
        chunksize=10_000,
    )
    print(f"Inserted {len(batch):,} rows into {table_name}")
```

## With smart correlations

```python
for table_name, batch in misata.generate_stream(
    "An HR dataset with 1M employees",
    rows=1_000_000,
    seed=42,
    smart_correlations=True,  # auto-adds tenure↔salary correlations
):
    process(table_name, batch)
```

## Collect specific tables

If you need one table in memory but want to stream others:

```python
import misata
import pandas as pd

users_batches = []
order_count = 0

for table_name, batch in misata.generate_stream(
    "An ecommerce store",
    rows=1_000_000,
    seed=42,
):
    if table_name == "users":
        users_batches.append(batch)   # collect users
    elif table_name == "orders":
        order_count += len(batch)     # just count orders
        # process batch immediately without storing

users = pd.concat(users_batches, ignore_index=True)
print(f"Users in memory: {len(users):,}")
print(f"Orders processed: {order_count:,}")
```

## Memory-efficient CSV export

```python
import misata
from pathlib import Path

output_dir = Path("./csv_export/")
output_dir.mkdir(exist_ok=True)
file_handles: dict = {}

for table_name, batch in misata.generate_stream("A streaming platform with 5M views", rows=5_000_000):
    path = output_dir / f"{table_name}.csv"
    if table_name not in file_handles:
        file_handles[table_name] = open(path, "w")
        batch.to_csv(file_handles[table_name], index=False)
    else:
        batch.to_csv(file_handles[table_name], index=False, header=False)

for fh in file_handles.values():
    fh.close()
```

## API reference

```python
misata.generate_stream(
    story: str,
    rows: int = 10_000,
    seed: Optional[int] = None,
    smart_correlations: bool = False,
) -> Iterator[Tuple[str, pd.DataFrame]]
```

| Parameter | Description |
|:--|:--|
| `story` | Plain-English description of the dataset |
| `rows` | Row count for the primary table |
| `seed` | Optional random seed for reproducibility |
| `smart_correlations` | Auto-infer Pearson correlations between related numeric columns |

## Related

- [generate()](../quickstart.md), standard in-memory generation
- [Export](../export.md), Parquet, DuckDB, JSONL export
- [Database Seeding](database-seeding-python.md), seed directly into a database
- [A warehouse before the product has users](../usecases/warehouse-before-users.md), 291,000 rows to partitioned Parquet with an attestation
- [CLI reference](../cli.md#misata-generate), `--format` and `--partition-by`
