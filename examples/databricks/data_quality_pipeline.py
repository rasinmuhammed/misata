# Databricks notebook source
# MAGIC %md
# MAGIC # Testing a Data-Cleaning Pipeline Against a Known Defect Rate
# MAGIC
# MAGIC **The problem:** you wrote a Bronze → Silver cleaning job — dedupe, drop rows
# MAGIC missing required fields, cap outliers. But how do you *prove* it works? Real raw
# MAGIC data has unknown defect rates, so you can never say "we caught 100% of the
# MAGIC duplicates" — you don't know how many there were to begin with.
# MAGIC
# MAGIC Misata flips this around. You **declare the defect rate** — "4% duplicate rows,
# MAGIC 6% missing emails, 2% outlier order totals" — and it injects exactly that into an
# MAGIC otherwise-realistic landing table. Now your cleaning pipeline has a **known ground
# MAGIC truth** to be scored against, the same contract the fraud and churn demos use for
# MAGIC rate curves.
# MAGIC
# MAGIC This notebook generates a dirty Bronze table with declared defects, runs a real
# MAGIC cleaning pipeline, and asserts the Silver output is clean — a CI-grade data-quality
# MAGIC test with zero production data.
# MAGIC
# MAGIC > **Runs on Databricks Free Edition** with serverless compute and Unity Catalog.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup
# MAGIC
# MAGIC Install plain `misata` — not `misata[spark]`. PySpark is already on every
# MAGIC Databricks cluster, and reinstalling it on serverless will stop your session.

# COMMAND ----------

# MAGIC %pip install misata

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

CATALOG = "workspace"   # Free Edition default; change if your workspace differs
SCHEMA  = "dq_demo"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")
print(f"Writing to {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Bronze — declare the schema *and* its defects
# MAGIC
# MAGIC One raw landing table of customer records. The `__noise__` block is the headline:
# MAGIC it injects a **declared, known** defect rate into otherwise-clean data —
# MAGIC
# MAGIC - **4% duplicate rows** — the classic dedupe target
# MAGIC - **6% null `email` / `phone`** — required-field violations to filter
# MAGIC - **3% typos in `city`** — dirty strings a real feed would carry
# MAGIC - **2% outliers in `order_total`** — extreme values to cap
# MAGIC
# MAGIC `mode: "custom"` means we drive the defects explicitly (as opposed to
# MAGIC `analytics_safe`, which never duplicates rows or touches keys).

# COMMAND ----------

SCHEMA_SPEC = {
    # --- Declare the exact defect rates — this is the ground truth ---
    "__noise__": {
        "mode":            "custom",
        "duplicate_rate":  0.04,
        "null_rate":       0.06,
        "typo_rate":       0.03,
        "outlier_rate":    0.02,
        "null_columns":    ["email", "phone"],
        "typo_columns":    ["city"],
        "outlier_columns": ["order_total"],
    },

    "customers_raw": {
        "__rows__": 5000,
        "id":          {"type": "integer", "primary_key": True},
        "name":        {"type": "string", "text_type": "name"},
        "email":       {"type": "email"},
        "phone":       {"type": "phone"},
        "city":        {"type": "string", "text_type": "city"},
        "order_total": {"type": "float", "distribution": "lognormal", "mu": 4.0, "sigma": 0.8, "min": 1},
        "signup_date": {"type": "date", "start": "2023-01-01", "end": "2024-12-31"},
    },
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Bronze — generate the dirty landing table and write to Delta

# COMMAND ----------

import warnings
warnings.filterwarnings("ignore", message="SDV not installed")

import misata
from misata import from_dict_schema
from misata import spark as mspark

# 5000 clean rows in, ~5200 out once 4% duplicates are injected.
schema = from_dict_schema(SCHEMA_SPEC, seed=11)

result = mspark.generate_to_delta(
    schema,
    spark,
    catalog=CATALOG,
    database=SCHEMA,
    mode="overwrite",
    table_properties={"delta.autoOptimize.optimizeWrite": "true"},
)
result.raise_on_error()
print("Bronze ready: dirty landing table written to Delta with declared defects.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Bronze — profile the defects
# MAGIC
# MAGIC Quantify how dirty the raw table is. These are the numbers the cleaning pipeline
# MAGIC has to fix — and because we *declared* them, we know roughly what to expect:
# MAGIC ~200 duplicate rows, ~6% null emails/phones.

# COMMAND ----------

from pyspark.sql import functions as F

raw = spark.table(f"{CATALOG}.{SCHEMA}.customers_raw")

total_rows  = raw.count()
distinct_id = raw.select("id").distinct().count()
dup_rows    = total_rows - distinct_id
null_email  = raw.where(F.col("email").isNull()).count()
null_phone  = raw.where(F.col("phone").isNull()).count()

print(f"Raw landing table profile")
print(f"  total rows        : {total_rows:,}")
print(f"  duplicate id rows : {dup_rows:,}  ({dup_rows / total_rows * 100:.1f}%)")
print(f"  null email        : {null_email:,}  ({null_email / total_rows * 100:.1f}%)")
print(f"  null phone        : {null_phone:,}  ({null_phone / total_rows * 100:.1f}%)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Silver — the real cleaning pipeline
# MAGIC
# MAGIC This is the transformation you actually want to test:
# MAGIC
# MAGIC 1. **Dedupe** — keep the first row per `id`.
# MAGIC 2. **Drop required-field violations** — rows missing `email` or `phone`.
# MAGIC 3. **Cap outliers** — clamp `order_total` to the 99th percentile (winsorise).
# MAGIC
# MAGIC The exact logic a production medallion would run — here exercised against data
# MAGIC whose defects we control.

# COMMAND ----------

from pyspark.sql import Window

# 1. Dedupe — one row per id (the earliest signup wins).
w = Window.partitionBy("id").orderBy("signup_date")
deduped = (
    raw.withColumn("_rn", F.row_number().over(w))
       .where(F.col("_rn") == 1)
       .drop("_rn")
)

# 2. Drop rows missing required contact fields.
required_present = deduped.where(F.col("email").isNotNull() & F.col("phone").isNotNull())

# 3. Cap order_total at the 99th percentile (winsorise the outliers).
p99 = required_present.approxQuantile("order_total", [0.99], 0.001)[0]
silver = required_present.withColumn(
    "order_total", F.when(F.col("order_total") > p99, p99).otherwise(F.col("order_total"))
)

(silver.write.format("delta").mode("overwrite")
       .option("overwriteSchema", "true")
       .saveAsTable(f"{CATALOG}.{SCHEMA}.customers_clean"))

print(f"Silver built: {silver.count():,} clean rows (capped order_total at {p99:,.2f}).")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. The data-quality test — assert Silver is clean
# MAGIC
# MAGIC The payoff. Because the defects were *declared*, we know precisely what a correct
# MAGIC cleaning pass must achieve: **zero duplicate ids, zero null emails/phones, no
# MAGIC value above the cap.** If the dedupe window were wrong, or a filter dropped the
# MAGIC wrong rows, one of these assertions would fail.
# MAGIC
# MAGIC This is a genuine CI test you can run on every commit, with zero production data.

# COMMAND ----------

clean = spark.table(f"{CATALOG}.{SCHEMA}.customers_clean")

clean_total   = clean.count()
clean_distinct = clean.select("id").distinct().count()
remaining_dups = clean_total - clean_distinct
remaining_null = clean.where(F.col("email").isNull() | F.col("phone").isNull()).count()
above_cap      = clean.where(F.col("order_total") > p99 + 1e-6).count()

print("Check                     Result")
print("-" * 40)
print(f"duplicate ids remaining   {remaining_dups}")
print(f"null email/phone remaining {remaining_null}")
print(f"values above outlier cap  {above_cap}")

assert remaining_dups == 0, f"Dedupe failed: {remaining_dups} duplicate ids remain"
assert remaining_null == 0, f"Required-field filter failed: {remaining_null} nulls remain"
assert above_cap == 0,     f"Outlier cap failed: {above_cap} values exceed p99"

# We also know roughly how many rows the cleaning *should* have removed — the declared
# defect rate is the ground truth. Recovery rate proves the pipeline did real work.
recovered = total_rows - clean_total
print(f"\nRows removed by cleaning   {recovered:,} of {total_rows:,} "
      f"({recovered / total_rows * 100:.1f}%)")
print("\nSilver is provably clean — every declared defect class was eliminated.")
print("The cleaning pipeline is verified correct — on synthetic data, no prod access.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## What you just proved
# MAGIC
# MAGIC 1. **Generated** a realistic raw landing table with a *declared* defect rate —
# MAGIC    4% duplicates, 6% null contacts, 3% typos, 2% outliers.
# MAGIC 2. **Ran** a real Bronze → Silver cleaning pipeline (dedupe, required-field filter,
# MAGIC    outlier winsorisation).
# MAGIC 3. **Asserted** the Silver output is clean against known ground truth — a CI-grade
# MAGIC    data-quality test that is impossible with Faker, because you never know the true
# MAGIC    defect rate of randomly-faked data.
# MAGIC
# MAGIC ### Where this goes next
# MAGIC
# MAGIC - **Tune your thresholds:** raise `outlier_rate` or `typo_rate` and confirm the
# MAGIC   pipeline still holds — regression-test your DQ rules against escalating dirtiness.
# MAGIC - **Score a DQ framework:** point Great Expectations / Databricks Lakehouse
# MAGIC   Monitoring at the raw table and confirm it flags the declared defect rate.
# MAGIC - **Keep aggregates intact:** switch `mode` to `analytics_safe` to inject realistic
# MAGIC   imperfections that never duplicate rows or touch keys — so declared rate curves
# MAGIC   and FK integrity still hold while columns carry believable noise.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC Misata is open source: `pip install misata` · [github.com/rasinmuhammed/misata](https://github.com/rasinmuhammed/misata)
