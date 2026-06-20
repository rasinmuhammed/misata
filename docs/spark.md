# Databricks & Apache Spark

The `misata.spark` module writes Misata-generated data straight into **Delta Lake** and
imports existing Spark schemas back into Misata. It runs on **Databricks** (Free Edition or
full), **AWS Glue**, **EMR**, **Dataproc**, or any local **PySpark 3.3+** environment.

Misata's value on Spark over the usual `dbldatagen`:

- **Multiple related tables in one call** — `dbldatagen` builds one table at a time with no
  awareness of relationships.
- **Referential integrity guaranteed and verifiable** — zero orphan foreign keys, checked in
  Delta with anti-joins.
- **Realistic distributions** — lognormal, Poisson, normal, uniform, and correlated columns.
- **Outcome conformance** — declare an exact aggregate or rate (e.g. a monthly fraud rate) and
  the generated data conforms, giving pipeline tests a **known ground truth to assert against**.

---

## Installation

=== "Databricks serverless / Free Edition"

    Install **plain `misata`** — *not* `misata[spark]`. PySpark is already on every Databricks
    cluster, and installing it on a serverless notebook will stop the session. The module
    imports the cluster's PySpark lazily.

    ```python
    %pip install misata
    dbutils.library.restartPython()
    ```

=== "Local / Glue / EMR / self-managed Spark"

    ```bash
    pip install misata[spark]    # pulls pyspark>=3.3.0
    ```

The module never imports PySpark at module-load time, so `import misata` stays lightweight.
Every function calls `import pyspark` lazily and raises a clear error if it is missing.

---

## Quick start

```python
import misata
from misata import spark as mspark

schema = misata.from_dict_schema({
    "customers": {
        "__rows__": 500,
        "id":      {"type": "integer", "primary_key": True},
        "email":   {"type": "email"},
        "country": {"type": "string", "text_type": "country"},
    },
    "orders": {
        "__rows__": 2000,
        "id":          {"type": "integer", "primary_key": True},
        "customer_id": {"type": "integer", "foreign_key": {"table": "customers", "column": "id"}},
        "total":       {"type": "float", "distribution": "lognormal", "mu": 4.5, "sigma": 0.9, "min": 4.99},
    },
})

result = mspark.generate_to_delta(schema, spark, catalog="dev", database="bronze", mode="overwrite")
print(result.summary())
result.raise_on_error()
```

`spark` is the active `SparkSession` — pre-defined in every Databricks notebook.

---

## API reference

### `to_spark(tables, spark, *, infer_schema=False, date_columns=None, schema_config=None)`

Convert Misata's `{table_name: pd.DataFrame}` output to `{table_name: SparkDataFrame}` using an
**explicit, type-correct schema**. Spark's own inference can widen nullable integers to doubles
or reject `datetime.date` objects; an explicit schema avoids both.

```python
tables = misata.generate_from_schema(schema)
spark_tables = mspark.to_spark(tables, spark, schema_config=schema)
spark_tables["orders"].printSchema()
```

Pass `schema_config` so columns declared `type: "date"` are mapped to Delta `DateType` (rather
than `TimestampType`). Misata stores both `date` and `datetime` as pandas `datetime64[ns]`, so
the schema is the only way to recover the distinction.

### `write_delta(tables, spark, *, catalog=None, database=None, schema=None, mode="overwrite", partition_by=None, cluster_by=None, merge_keys=None, table_properties=None, optimize_after_write=False, create_schema_if_not_exists=True, date_columns=None, schema_config=None, verbose=True)`

Write every table to Delta Lake. Returns a [`DeltaWriteResult`](#deltawriteresult).

```python
mspark.write_delta(
    tables, spark,
    catalog="dev", database="bronze",
    mode="overwrite",
    partition_by={"events": ["event_date"]},
    cluster_by={"transactions": ["txn_month"]},          # Delta liquid clustering
    table_properties={"delta.autoOptimize.optimizeWrite": "true"},
    optimize_after_write=True,
    schema_config=schema,                                 # preserve date typing
)
```

**Naming.** `catalog`, `database`/`schema`, and the table name assemble into Unity Catalog
3-part names (`catalog.database.table`), 2-part (`database.table`), or bare table names —
whatever you provide.

**Write modes:**

| `mode` | Behaviour |
|--------|-----------|
| `"overwrite"` | Replace the table; schema changes are applied (`overwriteSchema`). |
| `"append"` | Add rows to an existing table. |
| `"merge"` | Idempotent **`MERGE INTO`** upsert keyed on `merge_keys` — for CDC / SCD pipeline testing. Requires `merge_keys={"table": ["id"]}`. |
| `"error"` | Fail if the table already exists. |

```python
# Upsert: re-running this updates matched rows instead of duplicating them
mspark.write_delta(tables, spark, database="bronze",
                   mode="merge", merge_keys={"customers": ["id"]})
```

`cluster_by` uses Delta's `clusterBy` writer when available and **falls back gracefully**
(writing without clustering, with a warning) on older Delta builds.

### `verify_delta_integrity(spark, relationships, *, catalog=None, database=None, schema=None, sample_size=5)`

Verify referential integrity of Delta tables with a Spark SQL `LEFT ANTI JOIN` per relationship.
Returns a [`SparkIntegrityReport`](#sparkintegrityreport).

```python
relationships = [
    {"from_table": "orders",      "from_column": "customer_id", "to_table": "customers", "to_column": "id"},
    {"from_table": "order_items", "from_column": "order_id",    "to_table": "orders",    "to_column": "id"},
]
report = mspark.verify_delta_integrity(spark, relationships, catalog="dev", database="bronze")
print(report.summary())
report.raise_if_invalid()       # raises ValueError listing orphan counts + samples
```

Shorthand dot-notation is also accepted: `{"from": "orders.customer_id", "to": "customers.id"}`.

### `from_spark_schema(source, spark=None, *, table_name="table", row_count=1000, foreign_keys=None, seed=42)`

Convert a single Spark schema into a Misata `SchemaConfig`. `source` may be a `StructType`, a
`DataFrame`, or a fully-qualified table-name string. Reads only the public `.schema`, so it works
on Spark Connect / serverless.

```python
schema = mspark.from_spark_schema(
    spark.table("prod.bronze.orders"),
    row_count=5000,
    foreign_keys={"customer_id": {"table": "customers", "column": "id"}},
)
```

### `from_catalog_table(table_name, spark, *, row_count=1000, foreign_keys=None, seed=42)`

Import one Unity Catalog / Hive table by name.

```python
schema = mspark.from_catalog_table("dev.bronze.orders", spark, row_count=5000)
```

### `from_catalog_schema(spark, database, *, catalog=None, row_counts=None, foreign_keys=None, infer_foreign_keys=True, seed=42)`

Import **every table** in a database and assemble a multi-table `SchemaConfig`. FK relationships
are inferred from `{parent}_id` column naming (de-pluralisation aware: `order_id` → `orders.id`).
Unmapped `*_id` columns produce a warning rather than a silent miss.

```python
schema = mspark.from_catalog_schema(
    spark, database="bronze", catalog="prod",
    row_counts={"customers": 500, "orders": 2000, "order_items": 6000},
    foreign_keys={                                   # override / supplement inference
        "order_items": {"sku_ref": {"table": "products", "column": "sku"}},
    },
)
tables = misata.generate_from_schema(schema)
```

Use this to **mirror a production schema into a dev environment** — structure only, no data
copied — and generate matching synthetic data.

### `append_to_delta(schema_config, spark, n_rows, *, catalog=None, database=None, schema=None, seed=None, verbose=True)`

Generate additional rows and append them to existing Delta tables. Reads each table's current
`MAX(id)` to offset new primary keys so they never collide. FK integrity is maintained within the
new batch. Date typing conforms to the existing target table.

```python
mspark.append_to_delta(schema, spark, n_rows={"customers": 200, "orders": 800}, database="bronze")
```

### `write_delta_stream(schema_config, spark, *, catalog=None, database=None, schema=None, batch_size=100_000, partition_by=None, table_properties=None, optimize_after_write=False, create_schema_if_not_exists=True, verbose=True)`

Stream-write very large datasets. Uses Misata's batch generator so the full dataset is never
buffered in memory — suitable for tens or hundreds of millions of rows.

```python
schema.tables[0].row_count = 50_000_000
mspark.write_delta_stream(schema, spark, database="bronze", batch_size=250_000)
```

### `generate_to_spark(schema_or_story, spark, *, rows=10_000, seed=None, smart_correlations=False)`

One-liner: generate and return Spark DataFrames. Accepts a `SchemaConfig` or a plain-English
story string.

```python
spark_tables = mspark.generate_to_spark("An ecommerce store with 5k orders", spark)
```

### `generate_to_delta(schema_or_story, spark, *, catalog=None, database=None, schema=None, rows=10_000, seed=None, mode="overwrite", partition_by=None, cluster_by=None, table_properties=None, optimize_after_write=False, create_schema_if_not_exists=True, smart_correlations=False, verbose=True)`

One-liner: generate and write to Delta. Accepts a `SchemaConfig` or a story string.

---

## Result types

### `DeltaWriteResult`

Returned by `write_delta`, `write_delta_stream`, `append_to_delta`, `generate_to_delta`.

| Member | Description |
|--------|-------------|
| `.table_paths` | `{table: fully-qualified Delta path}` |
| `.rows_written` | `{table: row count}` |
| `.errors` | `{table: error message}` — empty on full success |
| `.ok` | `True` if no errors |
| `.summary()` | Human-readable per-table report |
| `.raise_on_error()` | Raise `RuntimeError` if any table failed |

### `SparkIntegrityReport`

Returned by `verify_delta_integrity`.

| Member | Description |
|--------|-------------|
| `.violations` | List of `SparkIntegrityViolation` |
| `.ok` | `True` if no violations |
| `.summary()` | Human-readable report |
| `.raise_if_invalid()` | Raise `ValueError` listing all violations |

Each `SparkIntegrityViolation` carries `child_table`, `child_column`, `parent_table`,
`parent_column`, `orphan_count`, and `sample_orphan_values`.

---

## End-to-end tutorial

[`examples/databricks/medallion_fraud_pipeline.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/databricks/medallion_fraud_pipeline.py)
builds a complete fraud-detection **medallion pipeline**:

1. **Bronze** — generate four FK-linked tables (`customers`, `accounts`, `merchants`,
   `transactions`) with a declared monthly fraud-rate curve (1.8% → 4.1%).
2. **Silver** — join all four tables, derive fraud-signal features.
3. **Gold** — aggregate monthly fraud rate and dollar volume.
4. **Assert** the Gold output matches the *declared* fraud rate — a CI-grade correctness test
   that's impossible with Faker or dbldatagen, because they give you no ground truth to check.

Import the `.py` file into Databricks (**Workspace → Import → File**) and **Run all** on
serverless.

---

## Compatibility

| | |
|---|---|
| Spark | 3.3+ (verified on 3.5.3) |
| Delta Lake | 2.x / 3.x (verified on 3.2.1) |
| Spark Connect / serverless | ✅ no `sparkContext`, `_jdf`, or RDD access |
| Unity Catalog | ✅ 3-part naming, managed tables |
| JDK | 8 / 11 / 17 (verified on 17) |

The full integration is covered by `tests/test_spark.py`, guarded by
`pytest.importorskip("pyspark")` so it runs in CI/Databricks and skips cleanly elsewhere.
