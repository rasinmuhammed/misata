---
title: Streaming Large Synthetic Datasets | Misata
description: Generate 10M+ row synthetic datasets without loading everything into memory using misata.generate_stream(). Yields (table_name, batch_df) tuples for memory-efficient processing.
---

# Streaming Large Synthetic Datasets

`misata.generate_stream()` yields `(table_name, batch_df)` tuples one batch at a time, the full dataset is never held in memory. This is the right interface for generating 10M+ row datasets, writing directly to Parquet, or streaming into a database without buffering.

## When to use streaming vs standard generation

| | `misata.generate()` | `misata.generate_stream()` |
|:--|:--|:--|
| Return type | `dict[str, DataFrame]` | Generator of `(name, DataFrame)` |
| Memory usage | Full dataset in RAM | One batch at a time |
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

```python
import misata
from pathlib import Path
import pandas as pd

output_dir = Path("./large_dataset/")
output_dir.mkdir(exist_ok=True)
writers: dict = {}

for table_name, batch in misata.generate_stream(
    "A SaaS company with 2M users",
    rows=2_000_000,
    seed=42,
):
    path = output_dir / f"{table_name}.parquet"
    if table_name not in writers:
        # First batch — write with schema
        batch.to_parquet(path, index=False)
    else:
        # Append subsequent batches
        existing = pd.read_parquet(path)
        pd.concat([existing, batch], ignore_index=True).to_parquet(path, index=False)
    writers[table_name] = True
    print(f"  {table_name}: wrote {len(batch):,} rows")
```

For very large datasets, use PyArrow's `ParquetWriter` directly:

```python
import misata
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path

output_dir = Path("./output/")
output_dir.mkdir(exist_ok=True)
pq_writers: dict = {}

for table_name, batch in misata.generate_stream(
    "A fintech with 10M transactions",
    rows=10_000_000,
    seed=42,
):
    arrow_table = pa.Table.from_pandas(batch)
    if table_name not in pq_writers:
        pq_writers[table_name] = pq.ParquetWriter(
            output_dir / f"{table_name}.parquet",
            arrow_table.schema,
        )
    pq_writers[table_name].write_table(arrow_table)

for writer in pq_writers.values():
    writer.close()
```

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
