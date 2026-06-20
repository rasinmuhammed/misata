# Databricks notebook source
# MAGIC %md
# MAGIC # Testing a SaaS Churn Pipeline Without Production Data
# MAGIC
# MAGIC **The problem:** your growth team wants a churn dashboard and your ML team wants
# MAGIC training data — but the product just launched and you have three months of real
# MAGIC subscriptions, not enough to build anything reliable.
# MAGIC
# MAGIC The usual answers are painful: wait for data, sample from prod (risky), or fake
# MAGIC it with Faker (meaningless distributions, zero FK integrity, no ground truth).
# MAGIC
# MAGIC Misata does something none of those can: you **declare the churn rate you want**
# MAGIC ("3.8% monthly in Jan, rising to 7.1% by June as free trials expire") and it
# MAGIC generates data that hits those rates **exactly** — across FK-linked tables, with
# MAGIC realistic lognormal ARR distributions and company-to-subscription relationships
# MAGIC that hold under a real Spark join.
# MAGIC
# MAGIC This notebook builds a complete SaaS Bronze → Silver → Gold pipeline:
# MAGIC - **Bronze:** 500 companies, 3000 subscription periods with a declared churn curve
# MAGIC - **Silver:** feature engineering (cohort age, ARR tier, plan type)
# MAGIC - **Gold:** monthly churn dashboard asserted against known ground truth
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
SCHEMA  = "saas_demo"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")
print(f"Writing to {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Bronze — declare the schema
# MAGIC
# MAGIC Two related tables:
# MAGIC ```
# MAGIC companies ──< subscriptions
# MAGIC ```
# MAGIC
# MAGIC The `__rate_curves__` block is what makes this different from every other synthetic
# MAGIC data tool. We're declaring that `churned` (a boolean column on `subscriptions`) must
# MAGIC hit **exactly 3.8% in January, 5.2% in March, 7.1% in June** — with smooth
# MAGIC interpolation across months in between. This is the ground truth the Gold layer
# MAGIC will be asserted against.

# COMMAND ----------

SCHEMA_SPEC = {
    # --- Declare the exact churn rate curve — this is the ground truth ---
    "__rate_curves__": [{
        "table":       "subscriptions",
        "column":      "churned",
        "time_column": "period_end",
        "time_unit":   "month",
        "true_value":  True,
        "rate_points": [
            {"period": "2025-01", "rate": 0.038},   # post-holiday lull
            {"period": "2025-03", "rate": 0.052},   # Q1 budget cuts
            {"period": "2025-06", "rate": 0.071},   # free-trial wave expires
        ],
    }],

    "companies": {
        "__rows__": 500,
        "id":          {"type": "integer", "primary_key": True},
        "name":        {"type": "string", "text_type": "company"},
        "plan":        {"type": "string", "enum": ["starter", "growth", "enterprise"],
                        "enum_weights": [0.5, 0.35, 0.15]},
        "mrr":         {"type": "float", "distribution": "lognormal", "mu": 7.0, "sigma": 1.0, "min": 49},
        "seats":       {"type": "integer", "distribution": "lognormal", "mu": 2.5, "sigma": 1.2, "min": 1},
        "signup_date": {"type": "date", "start": "2023-01-01", "end": "2024-12-31"},
        "country":     {"type": "string", "text_type": "country"},
    },

    "subscriptions": {
        "__rows__": 3000,
        "id":           {"type": "integer", "primary_key": True},
        "company_id":   {"type": "integer", "foreign_key": {"table": "companies", "column": "id"}},
        "period_start": {"type": "date", "start": "2025-01-01", "end": "2025-06-01"},
        "period_end":   {"type": "date", "start": "2025-01-31", "end": "2025-06-30"},
        "churned":      {"type": "boolean"},
        "arr":          {"type": "float", "distribution": "lognormal", "mu": 9.0, "sigma": 1.2, "min": 588},
        "seats_used":   {"type": "integer", "distribution": "normal", "mean": 8, "std": 5, "min": 1},
    },
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Bronze — generate and write to Delta

# COMMAND ----------

import warnings
warnings.filterwarnings("ignore", message="SDV not installed")

import misata
from misata import from_dict_schema
from misata import spark as mspark

schema = from_dict_schema(SCHEMA_SPEC, seed=42)

result = mspark.generate_to_delta(
    schema,
    spark,
    catalog=CATALOG,
    database=SCHEMA,
    mode="overwrite",
    table_properties={"delta.autoOptimize.optimizeWrite": "true"},
)
print(result.summary())
result.raise_on_error()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Bronze — verify FK integrity
# MAGIC
# MAGIC Every subscription must reference a real company. Zero orphan rows, guaranteed.

# COMMAND ----------

integrity = mspark.verify_delta_integrity(
    spark,
    [{"from_table": "subscriptions", "from_column": "company_id",
      "to_table": "companies",       "to_column": "id"}],
    catalog=CATALOG,
    database=SCHEMA,
)
print(integrity.summary())
integrity.raise_if_invalid()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Silver — feature engineering
# MAGIC
# MAGIC Enrich subscriptions with company attributes and derive churn-signal features:
# MAGIC - `cohort_age_months` — how long the company has been a customer
# MAGIC - `arr_tier` — ARR bucket (SMB / mid-market / enterprise)
# MAGIC - `seats_utilisation` — what fraction of seats are being used

# COMMAND ----------

from pyspark.sql import functions as F

subs = spark.table(f"{CATALOG}.{SCHEMA}.subscriptions")
cos  = spark.table(f"{CATALOG}.{SCHEMA}.companies")

silver = (
    subs.alias("s")
        .join(cos.alias("c"), F.col("s.company_id") == F.col("c.id"))
        .select(
            F.col("s.id").alias("sub_id"),
            "s.company_id",
            F.col("c.name").alias("company_name"),
            F.col("c.plan"),
            "s.period_start", "s.period_end",
            "s.churned", "s.arr", "s.seats_used",
            F.col("c.mrr").alias("company_mrr"),
            F.col("c.seats").alias("company_seats"),
            F.col("c.signup_date"),
            F.col("c.country"),
            F.date_format("s.period_end", "yyyy-MM").alias("period_month"),
        )
        .withColumn(
            "cohort_age_months",
            F.months_between(F.col("s.period_end"), F.col("c.signup_date")).cast("int"),
        )
        .withColumn(
            "arr_tier",
            F.when(F.col("arr") < 5000,  "smb")
             .when(F.col("arr") < 50000, "mid_market")
             .otherwise("enterprise"),
        )
        .withColumn(
            "seats_utilisation",
            F.col("seats_used") / (F.col("company_seats") + F.lit(1)),
        )
)

(silver.write.format("delta").mode("overwrite")
       .option("overwriteSchema", "true")
       .saveAsTable(f"{CATALOG}.{SCHEMA}.silver_subscriptions"))

sub_n    = subs.count()
silver_n = spark.table(f"{CATALOG}.{SCHEMA}.silver_subscriptions").count()
assert silver_n == sub_n, f"Join dropped rows! silver={silver_n} bronze={sub_n}"
print(f"Silver built: {silver_n:,} rows. No subscriptions lost in the company join.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Gold — monthly churn dashboard

# COMMAND ----------

gold = (
    spark.table(f"{CATALOG}.{SCHEMA}.silver_subscriptions")
         .groupBy("period_month")
         .agg(
             F.count("*").alias("total_subs"),
             F.sum(F.col("churned").cast("int")).alias("churned_count"),
             F.avg(F.col("churned").cast("int")).alias("churn_rate"),
             F.sum(F.when(F.col("churned"), F.col("arr")).otherwise(0)).alias("arr_lost"),
             F.avg("arr").alias("avg_arr"),
         )
         .orderBy("period_month")
)

(gold.write.format("delta").mode("overwrite")
     .option("overwriteSchema", "true")
     .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_monthly_churn"))

display(spark.table(f"{CATALOG}.{SCHEMA}.gold_monthly_churn"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Pipeline assertion — Gold vs declared ground truth
# MAGIC
# MAGIC Because we declared the churn curve in the Bronze schema, we know the exact target
# MAGIC for every month. If the Silver join or Gold aggregation had a bug, the numbers would
# MAGIC drift and this assertion would catch it — a genuine CI test with zero production data.

# COMMAND ----------

declared   = {"2025-01": 0.038, "2025-03": 0.052, "2025-06": 0.071}
TOLERANCE  = 0.008   # 0.8 pp — sampling noise at 3k rows is slightly higher than 40k

gold_rows  = {
    r["period_month"]: r["churn_rate"]
    for r in spark.table(f"{CATALOG}.{SCHEMA}.gold_monthly_churn").collect()
}

print("Month     Gold rate   Declared   Diff")
print("-" * 42)
failures = []
for month in sorted(gold_rows):
    rate = gold_rows[month]
    if month in declared:
        diff   = abs(rate - declared[month])
        status = "OK" if diff < TOLERANCE else "FAIL"
        if diff >= TOLERANCE:
            failures.append((month, rate, declared[month]))
        print(f"{month}   {rate*100:6.2f}%    {declared[month]*100:5.1f}%    {diff*100:.2f}pp  {status}")
    else:
        print(f"{month}   {rate*100:6.2f}%      (interpolated)")

assert not failures, f"Pipeline produced wrong churn rates: {failures}"
print("\nGold churn rates match the declared ground truth within tolerance.")
print("The Bronze→Silver→Gold pipeline is verified correct — on synthetic data, no prod access.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Bonus — churn by plan tier
# MAGIC
# MAGIC Because plan distribution and ARR are realistic (lognormal, not uniform), churn
# MAGIC analysis by segment produces meaningful insights rather than noise — useful for
# MAGIC training a real model before real data arrives.

# COMMAND ----------

churn_by_plan = (
    spark.table(f"{CATALOG}.{SCHEMA}.silver_subscriptions")
         .groupBy("plan")
         .agg(
             F.count("*").alias("total_subs"),
             F.avg(F.col("churned").cast("int")).alias("churn_rate"),
             F.avg("arr").alias("avg_arr"),
             F.sum(F.when(F.col("churned"), F.col("arr")).otherwise(0)).alias("arr_at_risk"),
         )
         .orderBy(F.desc("churn_rate"))
)
display(churn_by_plan)

# COMMAND ----------

# MAGIC %md
# MAGIC ## What you just proved
# MAGIC
# MAGIC 1. **Generated** a realistic 2-table SaaS dataset (500 companies, 3000 subscription
# MAGIC    periods) with lognormal ARR, company-level plan distribution, and FK integrity.
# MAGIC 2. **Declared** an exact churn rate curve — 3.8% in Jan rising to 7.1% by June —
# MAGIC    and verified it holds to within 0.8 percentage points in the Gold layer.
# MAGIC 3. **Ran** real feature engineering (cohort age, ARR tier, seat utilisation) and
# MAGIC    confirmed no subscriptions were dropped in the company join.
# MAGIC 4. **Demonstrated** a CI-grade pipeline test on synthetic data with known ground truth.
# MAGIC
# MAGIC ### Where this goes next
# MAGIC
# MAGIC - **Train a model:** the Silver table is ready for a churn-prediction model in
# MAGIC   Databricks AutoML or MLflow. The declared churn rate gives you a baseline AUC to
# MAGIC   beat.
# MAGIC - **Add engagement signals:** extend the schema with a `events` table (logins, feature
# MAGIC   usage) FK-linked to companies and wire up informative missingness so inactive
# MAGIC   companies are more likely to churn.
# MAGIC - **Append incremental data:** `mspark.append_to_delta(schema, spark, n_rows={"subscriptions": 500})`
# MAGIC   generates a new month of subscriptions with non-colliding PKs and correctly offset
# MAGIC   FK references — no manual ID management.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC Misata is open source: `pip install misata` · [github.com/rasinmuhammed/misata](https://github.com/rasinmuhammed/misata)
