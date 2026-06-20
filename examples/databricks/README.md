# Misata on Databricks

Realistic, referentially-correct, **outcome-conformant** synthetic data for Databricks —
generated directly into Delta Lake, with no production data required.

These examples run on **Databricks Free Edition** (serverless + Unity Catalog), the
full platform, AWS Glue, or any PySpark 3.3+ environment.

## Examples

| Notebook | Vertical | What it shows |
|----------|----------|---------------|
| [`medallion_fraud_pipeline.py`](./medallion_fraud_pipeline.py) | Fintech | 4-table fraud pipeline (customers → accounts → transactions ← merchants). Declares an exact monthly fraud-rate curve (1.8% → 4.1%), generates 45k rows, runs Bronze → Silver → Gold, and **asserts Gold against known ground truth** — impossible with Faker or dbldatagen. |
| [`saas_churn_pipeline.py`](./saas_churn_pipeline.py) | SaaS | 2-table churn pipeline (companies → subscriptions). Declares a rising churn curve (3.8% → 7.1%), adds feature engineering (cohort age, ARR tier, seat utilisation), and verifies the Gold churn rate hits the declared target — ready as MLflow training data. |

## Why Misata on Databricks

`dbldatagen` is the usual answer for synthetic data on Databricks, but it generates one
table at a time with no awareness of relationships — orphan foreign keys silently break
your joins. Misata is built for the multi-table case:

| | dbldatagen | **Misata** |
|---|:---:|:---:|
| Multiple related tables in one call | ❌ | ✅ |
| Referential integrity guaranteed + verifiable | ❌ | ✅ |
| Realistic distributions (lognormal, Poisson, normal, correlated) | partial | ✅ |
| **Declare exact aggregates / rates as ground truth** | ❌ | ✅ |
| Write straight to Delta (managed tables, partitioning, liquid clustering) | manual | ✅ one call |
| Import an existing Unity Catalog schema → generate matching data | ❌ | ✅ |

## Setup (read this first)

On **serverless / Free Edition**, install plain `misata` — **not** `misata[spark]`:

```python
%pip install misata
dbutils.library.restartPython()
```

PySpark is already on every Databricks cluster. Databricks' own docs warn that installing
PySpark on a serverless notebook will stop your session, and `misata[spark]` would pull it
in. The `misata.spark` module imports the cluster's PySpark lazily, so plain `misata` is all
you need. (On classic clusters either works, but plain `misata` is still the lighter choice.)

## The `misata.spark` API at a glance

```python
from misata import spark as mspark

# One-liner: generate + write all tables to Delta
mspark.generate_to_delta(schema, spark, catalog="dev", database="bronze")

# Convert Misata pandas output to Spark DataFrames (explicit, type-correct schema)
mspark.to_spark(tables, spark, schema_config=schema)

# Write with partitioning, liquid clustering, properties, or MERGE upsert
mspark.write_delta(tables, spark, catalog="dev", database="bronze",
                   cluster_by={"transactions": ["txn_month"]},
                   mode="merge", merge_keys={"customers": ["id"]})

# Verify referential integrity of Delta tables (Spark SQL anti-joins)
mspark.verify_delta_integrity(spark, relationships, catalog="dev", database="bronze")

# Import an existing schema (structure only, no data) → generate matching data
schema = mspark.from_catalog_schema(spark, "bronze", catalog="prod",
                                    row_counts={"orders": 5000})

# Append incremental rows with non-colliding PKs
mspark.append_to_delta(schema, spark, n_rows={"orders": 1000}, catalog="dev", database="bronze")

# Stream-write very large datasets without buffering
mspark.write_delta_stream(schema, spark, catalog="dev", database="bronze", batch_size=200_000)
```

Full reference: [`docs/spark.md`](../../docs/spark.md).

## Importing a notebook into Databricks

The `.py` files are in **Databricks source format**. To run one:

1. In your Databricks workspace, go to **Workspace → (your folder) → Import**.
2. Choose **File**, upload `medallion_fraud_pipeline.py`, and import.
3. It opens as a notebook with all cells intact. Attach to serverless and **Run all**.

Or clone the repo with Databricks Repos and open the file directly.

## Verified

Every code cell in these notebooks is tested against **Apache Spark 3.5.3 + Delta Lake
3.2.1** (the engine Databricks serverless runs) in the project's CI suite
(`tests/test_spark.py`). The medallion pipeline's ground-truth assertion passes to within
0.01 percentage points.
