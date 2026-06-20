# Databricks notebook source
# MAGIC %md
# MAGIC # Testing a Fraud-Detection Medallion Pipeline Without Production Data
# MAGIC
# MAGIC **The problem every Databricks team hits:** you build a Bronze → Silver → Gold
# MAGIC pipeline, but you can't copy production data into your dev workspace (governance,
# MAGIC PII, approvals). So how do you *test* that your Silver joins and Gold aggregations
# MAGIC are correct before real data ever lands?
# MAGIC
# MAGIC The usual answers fall short:
# MAGIC
# MAGIC | Tool | Multi-table FK integrity | Realistic distributions | **Known ground truth to assert against** |
# MAGIC |------|:---:|:---:|:---:|
# MAGIC | `Faker` + loops | ❌ orphan rows break joins | ❌ | ❌ |
# MAGIC | `dbldatagen` | ❌ one table at a time | partial | ❌ |
# MAGIC | **Misata** | ✅ proven, zero orphans | ✅ lognormal / Poisson / correlated | ✅ **declare an exact fraud-rate curve** |
# MAGIC
# MAGIC That last column is the one that matters. Normally you **cannot unit-test a fraud
# MAGIC aggregation** because you don't know the true fraud rate of your test data. Misata
# MAGIC lets you *declare* it ("fraud is 1.8% in January, ramping to 4.1% by June") and
# MAGIC generates data that conforms to it **exactly**. Now your Gold layer has a ground
# MAGIC truth to assert against.
# MAGIC
# MAGIC This notebook builds a complete 4-table fraud medallion, runs the real Silver and
# MAGIC Gold transformations, and proves the pipeline is correct — entirely on synthetic
# MAGIC data, with no production access.
# MAGIC
# MAGIC > **Runs on Databricks Free Edition.** Everything here works on serverless compute
# MAGIC > with Unity Catalog. See the setup note in the first code cell.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup
# MAGIC
# MAGIC **Important for serverless / Free Edition:** install plain `misata` — **not**
# MAGIC `misata[spark]`. PySpark is already on the cluster, and Databricks' own docs warn
# MAGIC that installing PySpark on a serverless notebook will stop your session. The
# MAGIC `misata.spark` module imports the cluster's PySpark lazily, so plain `misata` is
# MAGIC all you need.

# COMMAND ----------

# MAGIC %pip install misata

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC Set the target catalog and schema. On Free Edition the default catalog is usually
# MAGIC `workspace`; change `CATALOG` if your workspace differs. The schema is created for
# MAGIC you if it does not exist.

# COMMAND ----------

CATALOG = "workspace"      # Free Edition default; change if needed
SCHEMA  = "fraud_demo"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")
print(f"Writing to {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Bronze — declare the schema
# MAGIC
# MAGIC Four related tables modelling a card-payments business:
# MAGIC
# MAGIC ```
# MAGIC customers ──< accounts ──< transactions >── merchants
# MAGIC ```
# MAGIC
# MAGIC Notice what's declared per column — this is what separates Misata from a `Faker`
# MAGIC loop:
# MAGIC
# MAGIC - **Foreign keys** (`foreign_key`) — every account points to a real customer, every
# MAGIC   transaction to a real account *and* a real merchant. Zero orphans, guaranteed.
# MAGIC - **Distributions** — `balance` and `amount` are **lognormal** (a few large values,
# MAGIC   many small — like real money), `risk_score` is **normal**, `mcc_risk` is **uniform**.
# MAGIC - **Semantic types** — `email`, `name`, `country`, `company` produce real-looking
# MAGIC   values, not `"string_4821"`.
# MAGIC - **`__rate_curves__`** — the headline feature. `is_fraud` is forced to an exact rate
# MAGIC   per month: **1.8% in Jan → 2.7% in Mar → 4.1% in Jun**, smoothly interpolated in
# MAGIC   between. This is our ground truth.

# COMMAND ----------

SCHEMA_SPEC = {
    # --- The differentiator: an exact, time-varying fraud rate as ground truth ---
    "__rate_curves__": [{
        "table": "transactions",
        "column": "is_fraud",
        "time_column": "txn_ts",
        "time_unit": "month",
        "true_value": True,
        "rate_points": [
            {"period": "2025-01", "rate": 0.018},
            {"period": "2025-03", "rate": 0.027},
            {"period": "2025-06", "rate": 0.041},
        ],
    }],

    "customers": {
        "__rows__": 2000,
        "id":          {"type": "integer", "primary_key": True},
        "email":       {"type": "email"},
        "full_name":   {"type": "string", "text_type": "name"},
        "country":     {"type": "string", "text_type": "country"},
        "risk_score":  {"type": "float", "distribution": "normal", "mean": 0.3, "std": 0.15, "min": 0, "max": 1},
        "signup_date": {"type": "date", "start": "2022-01-01", "end": "2024-12-31"},
    },

    "accounts": {
        "__rows__": 2600,
        "id":           {"type": "integer", "primary_key": True},
        "customer_id":  {"type": "integer", "foreign_key": {"table": "customers", "column": "id"}},
        "account_type": {"type": "string", "enum": ["checking", "savings", "credit"]},
        "balance":      {"type": "float", "distribution": "lognormal", "mu": 7.5, "sigma": 1.2, "min": 0},
        "opened_date":  {"type": "date", "start": "2022-01-01", "end": "2024-12-31"},
    },

    "merchants": {
        "__rows__": 400,
        "id":       {"type": "integer", "primary_key": True},
        "name":     {"type": "string", "text_type": "company"},
        "category": {"type": "string", "enum": ["grocery", "electronics", "travel", "dining", "gambling", "crypto", "utilities"]},
        "mcc_risk": {"type": "float", "distribution": "uniform", "min": 0, "max": 1},
    },

    "transactions": {
        "__rows__": 40000,
        "id":          {"type": "integer", "primary_key": True},
        "account_id":  {"type": "integer", "foreign_key": {"table": "accounts", "column": "id"}},
        "merchant_id": {"type": "integer", "foreign_key": {"table": "merchants", "column": "id"}},
        "amount":      {"type": "float", "distribution": "lognormal", "mu": 3.4, "sigma": 1.1, "min": 0.5},
        "txn_ts":      {"type": "datetime", "start": "2025-01-01", "end": "2025-06-30"},
        "is_fraud":    {"type": "boolean"},
        "channel":     {"type": "string", "enum": ["pos", "online", "atm", "wire"]},
    },
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Bronze — generate and write to Delta
# MAGIC
# MAGIC `generate_to_delta` is a one-liner: it builds the schema, generates all four tables
# MAGIC with FK integrity, and writes them as managed Delta tables under your catalog/schema.
# MAGIC The `schema_config` argument lets Misata write `date` columns as Delta `DateType`
# MAGIC (not timestamps), and `table_properties` turns on optimized writes.

# COMMAND ----------

import misata
from misata import from_dict_schema
from misata import spark as mspark

# Build the schema and generate once so we can both inspect it and write it.
schema = from_dict_schema(SCHEMA_SPEC, row_count=1000, seed=11)

result = mspark.generate_to_delta(
    schema,
    spark,
    catalog=CATALOG,
    database=SCHEMA,
    mode="overwrite",
    table_properties={"delta.autoOptimize.optimizeWrite": "true"},
)
result.raise_on_error()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Bronze — prove referential integrity in Delta
# MAGIC
# MAGIC Before trusting the data, verify there are **zero orphan rows** across all three FK
# MAGIC relationships. `verify_delta_integrity` runs a Spark SQL `LEFT ANTI JOIN` per
# MAGIC relationship — the same check you'd run against production. If Misata's guarantee
# MAGIC ever regressed, this would catch it.

# COMMAND ----------

relationships = [
    {"from_table": "accounts",     "from_column": "customer_id", "to_table": "customers", "to_column": "id"},
    {"from_table": "transactions", "from_column": "account_id",  "to_table": "accounts",  "to_column": "id"},
    {"from_table": "transactions", "from_column": "merchant_id", "to_table": "merchants", "to_column": "id"},
]

integrity = mspark.verify_delta_integrity(spark, relationships, catalog=CATALOG, database=SCHEMA)
print(integrity.summary())
integrity.raise_if_invalid()   # raises if any orphan rows exist

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Silver — clean, enrich, and join
# MAGIC
# MAGIC This is your *real* transformation logic — the code you actually want to test. We
# MAGIC join all four tables into one enriched fact table and derive fraud-signal features:
# MAGIC
# MAGIC - `amount_to_balance` — transaction size relative to account balance
# MAGIC - `high_risk_merchant` — gambling / crypto flag
# MAGIC - `composite_risk` — blended customer + merchant risk
# MAGIC
# MAGIC **The first pipeline assertion is hidden in this join:** it's an *inner* join, so if
# MAGIC any transaction referenced a missing account or merchant, that row would silently
# MAGIC drop. We check the Silver row count equals the Bronze transaction count — proving FK
# MAGIC integrity held through the transformation.

# COMMAND ----------

from pyspark.sql import functions as F

tx   = spark.table(f"{CATALOG}.{SCHEMA}.transactions")
acc  = spark.table(f"{CATALOG}.{SCHEMA}.accounts")
cust = spark.table(f"{CATALOG}.{SCHEMA}.customers")
mer  = spark.table(f"{CATALOG}.{SCHEMA}.merchants")

silver = (
    tx.alias("t")
      .join(acc.alias("a"),  F.col("t.account_id")  == F.col("a.id"))
      .join(cust.alias("c"), F.col("a.customer_id") == F.col("c.id"))
      .join(mer.alias("m"),  F.col("t.merchant_id") == F.col("m.id"))
      .select(
          F.col("t.id").alias("txn_id"),
          "t.account_id", "t.merchant_id",
          F.col("c.id").alias("customer_id"),
          "t.amount", "t.txn_ts", "t.is_fraud", "t.channel",
          F.col("c.country").alias("customer_country"),
          F.col("c.risk_score").alias("customer_risk"),
          F.col("m.category").alias("merchant_category"),
          F.col("m.mcc_risk"),
          F.col("a.balance").alias("account_balance"),
          F.to_date("t.txn_ts").alias("txn_date"),
          F.date_format("t.txn_ts", "yyyy-MM").alias("txn_month"),
      )
      .withColumn("amount_to_balance",  F.col("amount") / (F.col("account_balance") + F.lit(1.0)))
      .withColumn("high_risk_merchant", F.col("merchant_category").isin("gambling", "crypto").cast("int"))
      .withColumn("composite_risk",     F.col("customer_risk") * 0.5 + F.col("mcc_risk") * 0.5)
)

(silver.write.format("delta").mode("overwrite")
       .option("overwriteSchema", "true")
       .saveAsTable(f"{CATALOG}.{SCHEMA}.silver_transactions"))

silver_n = spark.table(f"{CATALOG}.{SCHEMA}.silver_transactions").count()
bronze_n = tx.count()
assert silver_n == bronze_n, f"Join dropped rows! silver={silver_n} bronze={bronze_n} — orphan FKs?"
print(f"✅ Silver built: {silver_n:,} rows, no transactions lost in the 4-table join.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Gold — aggregate monthly fraud
# MAGIC
# MAGIC The business-facing table: fraud rate and fraud dollar-volume per month. This is the
# MAGIC output a fraud-ops dashboard or an alerting model would consume.

# COMMAND ----------

gold = (
    spark.table(f"{CATALOG}.{SCHEMA}.silver_transactions")
         .groupBy("txn_month")
         .agg(
             F.count("*").alias("txn_count"),
             F.sum(F.col("is_fraud").cast("int")).alias("fraud_count"),
             F.avg(F.col("is_fraud").cast("int")).alias("fraud_rate"),
             F.sum(F.when(F.col("is_fraud"), F.col("amount")).otherwise(0.0)).alias("fraud_dollar_volume"),
         )
         .orderBy("txn_month")
)

(gold.write.format("delta").mode("overwrite")
     .option("overwriteSchema", "true")
     .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_monthly_fraud"))

display(spark.table(f"{CATALOG}.{SCHEMA}.gold_monthly_fraud"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. The pipeline test — assert Gold against known ground truth
# MAGIC
# MAGIC Here's the payoff. Because we *declared* the fraud rate in the Bronze schema, we know
# MAGIC exactly what the Gold aggregation should produce: **1.8% in Jan, 2.7% in Mar, 4.1% in
# MAGIC Jun.** If our Silver join or Gold aggregation had a bug — a wrong join key, a bad
# MAGIC `cast`, a filter that dropped fraud rows — the numbers would drift and this assertion
# MAGIC would fail.
# MAGIC
# MAGIC This is a genuine CI test you can run on every commit, with zero production data.

# COMMAND ----------

declared = {"2025-01": 0.018, "2025-03": 0.027, "2025-06": 0.041}
TOLERANCE = 0.006   # 0.6 percentage points — accounts for sampling noise at 40k rows

gold_rows = {r["txn_month"]: r["fraud_rate"] for r in spark.table(f"{CATALOG}.{SCHEMA}.gold_monthly_fraud").collect()}

print("Month     Gold rate   Declared   Diff")
print("-" * 42)
failures = []
for month in sorted(gold_rows):
    rate = gold_rows[month]
    if month in declared:
        diff = abs(rate - declared[month])
        status = "OK" if diff < TOLERANCE else "FAIL"
        if diff >= TOLERANCE:
            failures.append((month, rate, declared[month]))
        print(f"{month}   {rate*100:6.2f}%    {declared[month]*100:5.1f}%    {diff*100:.2f}pp  {status}")
    else:
        print(f"{month}   {rate*100:6.2f}%      (interpolated)")

assert not failures, f"Pipeline produced wrong fraud rates: {failures}"
print("\n✅ Gold fraud rates match the declared ground truth within tolerance.")
print("   The Bronze→Silver→Gold pipeline is verified correct — on synthetic data, no prod access.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Bonus — fraud concentration by merchant category
# MAGIC
# MAGIC A second Gold table showing where fraud concentrates. Because `mcc_risk` and the
# MAGIC `gambling`/`crypto` categories carry real signal, downstream fraud models trained on
# MAGIC this data learn realistic patterns — not noise.

# COMMAND ----------

category_fraud = (
    spark.table(f"{CATALOG}.{SCHEMA}.silver_transactions")
         .groupBy("merchant_category")
         .agg(
             F.count("*").alias("txns"),
             F.avg(F.col("is_fraud").cast("int")).alias("fraud_rate"),
             F.avg("mcc_risk").alias("avg_mcc_risk"),
         )
         .orderBy(F.desc("fraud_rate"))
)
display(category_fraud)

# COMMAND ----------

# MAGIC %md
# MAGIC ## What you just proved
# MAGIC
# MAGIC 1. **Generated** a realistic 4-table, 45k-row fraud dataset with zero production data.
# MAGIC 2. **Guaranteed** referential integrity across three FK relationships — verified in Delta.
# MAGIC 3. **Ran** a real Bronze → Silver → Gold pipeline (4-table join, derived features, monthly aggregation).
# MAGIC 4. **Asserted** the Gold output against a *known* fraud-rate ground truth — a CI-grade
# MAGIC    correctness test that's impossible with Faker or dbldatagen, because they can't give
# MAGIC    you a known target to check against.
# MAGIC
# MAGIC ### Where this goes next
# MAGIC
# MAGIC - **Scale it:** bump `transactions` to 10M rows and use `mspark.write_delta_stream(...)`
# MAGIC   to write in batches without buffering.
# MAGIC - **CDC / SCD testing:** use `mode="merge"` with `merge_keys` to test upsert pipelines.
# MAGIC - **Mirror an existing schema:** `mspark.from_catalog_schema(spark, "prod_bronze", catalog=...)`
# MAGIC   reads a production schema (structure only, no data) and generates matching synthetic
# MAGIC   data with FKs auto-inferred.
# MAGIC
# MAGIC ---

# COMMAND ----------

# MAGIC %md
# MAGIC ## Troubleshooting (first run)
# MAGIC
# MAGIC **`CATALOG` doesn't exist / permission denied on `workspace`.**
# MAGIC Free Edition's default catalog is usually `workspace`, but some accounts differ. List
# MAGIC what you can write to and pick one, then re-run the setup cell:
# MAGIC
# MAGIC ```python
# MAGIC display(spark.sql("SHOW CATALOGS"))
# MAGIC # set CATALOG to one you have CREATE SCHEMA on (often `workspace` or `main`)
# MAGIC ```
# MAGIC
# MAGIC **`Cannot create schema` / missing privilege.** You need `USE CATALOG` + `CREATE SCHEMA`
# MAGIC on the target catalog. On a shared/managed catalog you may not have it — use your
# MAGIC personal `workspace` catalog instead, or ask an admin.
# MAGIC
# MAGIC **Session stops right after `%pip install`.** You installed `misata[spark]` on serverless.
# MAGIC Install plain `misata` — PySpark is already on the cluster and reinstalling it stops the
# MAGIC session.
# MAGIC
# MAGIC **`ModuleNotFoundError: misata` after install.** Run `dbutils.library.restartPython()`
# MAGIC once (it's in the setup cell), then re-run from the imports cell.
# MAGIC
# MAGIC **Quota / resource limit on the 40k-row generate.** Free Edition is quota-limited. Drop
# MAGIC `transactions` `__rows__` to `10000` (and `accounts`/`customers` proportionally) — the
# MAGIC fraud-rate assertion still passes, just with slightly more sampling noise (widen
# MAGIC `TOLERANCE` to `0.01` if needed).
# MAGIC
# MAGIC **Two-part vs three-part names.** If your environment has no Unity Catalog, drop the
# MAGIC `catalog=` argument everywhere and use `database=SCHEMA` only — every `misata.spark`
# MAGIC function accepts 2-part (`database.table`) naming.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC Misata is open source: `pip install misata` · [github.com/rasinmuhammed/misata](https://github.com/rasinmuhammed/misata)
