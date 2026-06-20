"""
Apache Spark and Delta Lake integration for Misata.

Provides a complete bridge between Misata's pandas-based generation and
Spark/Delta Lake ecosystems — Databricks, Apache Spark, AWS Glue, or any
Delta-compatible environment.

Capabilities
------------
- **Convert** Misata output to Spark DataFrames with an explicit, type-correct schema
- **Write** all generated tables to Delta Lake in one call (catalog.database.table naming)
- **Append** incremental rows to existing Delta tables while preserving FK integrity
- **Stream-write** massive datasets (100M+ rows) in batches without buffering
- **Import** existing Spark/Unity Catalog schemas back into Misata for data generation
- **Verify** referential integrity of existing Delta tables via Spark SQL anti-joins
- **One-liner** helpers that combine generation + write in a single call

Requirements
------------
PySpark 3.3+ (not listed as a hard dependency — installed separately or pre-installed
in the Spark environment)::

    pip install pyspark>=3.3.0        # local development
    # or: Databricks Runtime ≥ 11.x, AWS Glue 4.0+, Dataproc 2.1+

Quick start (Databricks notebook)
----------------------------------
::

    from misata.spark import generate_to_delta
    import misata

    # One-liner: build schema → generate → write all tables to Delta
    result = generate_to_delta(
        schema,
        spark,
        catalog="dev_catalog",
        database="bronze",
        mode="overwrite",
    )
    print(result.summary())
    # ✅ customers (500 rows) → dev_catalog.bronze.customers
    # ✅ orders    (2000 rows) → dev_catalog.bronze.orders
    # ✅ order_items (6000 rows) → dev_catalog.bronze.order_items

    # Import an existing Unity Catalog schema and generate matching synthetic data
    from misata.spark import from_catalog_schema

    schema = from_catalog_schema(spark, "prod_bronze", catalog="prod_catalog", row_counts={
        "customers": 500, "orders": 2000, "order_items": 6000,
    })
    tables = misata.generate_from_schema(schema)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import pandas as pd

if TYPE_CHECKING:
    from pyspark.sql import DataFrame as SparkDataFrame, SparkSession
    from pyspark.sql.types import DataType, StructType
    from misata.schema import SchemaConfig


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def _require_pyspark(feature: str = "this feature") -> None:
    """Raise a helpful ImportError if PySpark is not available."""
    try:
        import pyspark  # noqa: F401
    except ImportError:
        raise ImportError(
            f"PySpark is required for {feature}.\n\n"
            "Install it with:\n"
            "    pip install pyspark>=3.3.0\n\n"
            "Or use Misata's Spark extra:\n"
            "    pip install misata[spark]"
        ) from None


# ---------------------------------------------------------------------------
# Type mapping helpers
# ---------------------------------------------------------------------------

# Mapping from PySpark type class names → Misata dict-schema type strings
_SPARK_TO_MISATA: Dict[str, str] = {
    "ByteType":        "integer",
    "ShortType":       "integer",
    "IntegerType":     "integer",
    "LongType":        "integer",
    "FloatType":       "float",
    "DoubleType":      "float",
    "DecimalType":     "float",
    "StringType":      "string",
    "BooleanType":     "boolean",
    "DateType":        "date",
    "TimestampType":   "datetime",
    "TimestampNTZType":"datetime",
    "BinaryType":      "string",   # base64-encoded fallback
    "ArrayType":       "string",   # JSON-serialized
    "MapType":         "string",   # JSON-serialized
    "NullType":        "string",
}


def _spark_field_to_col_def(f: Any) -> Dict[str, Any]:
    """Convert a single PySpark ``StructField`` to a Misata column-def dict."""
    from pyspark.sql import types as T

    type_name = type(f.dataType).__name__
    misata_type = _SPARK_TO_MISATA.get(type_name, "string")

    col_def: Dict[str, Any] = {
        "type": misata_type,
        "nullable": bool(f.nullable),
    }

    # Preserve decimal precision as rounding
    if isinstance(f.dataType, T.DecimalType):
        col_def["decimals"] = f.dataType.scale

    # Extract human comment from Unity Catalog / Hive metadata
    comment = (
        f.metadata.get("comment")
        or f.metadata.get("description")
        or f.metadata.get("delta.columnMapping.physicalName")
    )
    if comment and "comment" in f.metadata:
        col_def["description"] = f.metadata["comment"]

    # Complex types → note in description
    if isinstance(f.dataType, (T.ArrayType, T.MapType, T.StructType)):
        col_def["description"] = (col_def.get("description") or "") + f" [{type_name}]"

    return col_def


def _pandas_dtype_to_spark_type(
    col_name: str,
    series: pd.Series,
    *,
    is_date: bool = False,
) -> Any:
    """Return the most precise PySpark DataType for a pandas Series.

    Args:
        col_name: Column name (used only for diagnostics).
        series:   The pandas Series whose dtype is being mapped.
        is_date:  If ``True``, a datetime-like column is mapped to ``DateType``
                  instead of ``TimestampType``. Misata stores both ``date`` and
                  ``datetime`` columns as ``datetime64[ns]`` with real time
                  components, so a column declared ``type: "date"`` is
                  indistinguishable from a ``datetime`` at the pandas level —
                  the schema is the only source of truth, threaded in here.
    """
    from pyspark.sql.types import (
        BooleanType, DateType, DoubleType, LongType,
        StringType, TimestampType,
    )

    dtype = series.dtype

    if pd.api.types.is_bool_dtype(dtype):
        return BooleanType()
    # Integer (including nullable pandas Int64Dtype). A nullable int that picked
    # up NaN is widened to float64 by pandas; in that case fall through to Double
    # so createDataFrame does not reject NaN against a LongType schema.
    if pd.api.types.is_integer_dtype(dtype) or str(dtype).startswith("Int"):
        return LongType()
    if pd.api.types.is_float_dtype(dtype):
        return DoubleType()
    if pd.api.types.is_datetime64_any_dtype(dtype) or hasattr(dtype, "tz"):
        return DateType() if is_date else TimestampType()
    # Object column holding python date objects (e.g. an already-normalised date)
    if isinstance(dtype, pd.CategoricalDtype):
        return StringType()
    if dtype == object:
        non_null = series.dropna()
        if len(non_null) > 0:
            import datetime
            sample = non_null.iloc[0]
            if isinstance(sample, datetime.date) and not isinstance(sample, datetime.datetime):
                return DateType()
    return StringType()


def _build_spark_schema(
    df: pd.DataFrame,
    date_columns: Optional[set] = None,
) -> "StructType":
    """Build an explicit PySpark ``StructType`` from a pandas DataFrame.

    Using an explicit schema avoids Spark's type inference, which can silently
    widen ints to doubles or mis-detect nullable columns.

    Args:
        df:           Source DataFrame.
        date_columns: Names of columns declared as ``date`` (not ``datetime``)
                      in the originating schema. These map to ``DateType``.
    """
    from pyspark.sql.types import StructField, StructType

    date_columns = date_columns or set()
    return StructType([
        StructField(
            col,
            _pandas_dtype_to_spark_type(col, df[col], is_date=col in date_columns),
            nullable=bool(df[col].isna().any()),
        )
        for col in df.columns
    ])


def _normalize_for_spark(
    df: pd.DataFrame,
    date_columns: Optional[set] = None,
) -> pd.DataFrame:
    """Coerce a Misata pandas DataFrame into a Spark-safe state.

    - String (object) columns: replace NaN with None (Spark null)
    - Datetime columns: drop any timezone so they are tz-naive
    - Declared date columns: truncate to python ``date`` objects so they line up
      with a ``DateType`` schema field (Spark rejects ``Timestamp`` against
      ``DateType`` and vice-versa)
    - Float columns: leave NaN in place — Spark maps NaN/None to null under an
      explicit nullable schema

    Args:
        df:           Source DataFrame.
        date_columns: Names of columns declared as ``date``.
    """
    date_columns = date_columns or set()
    df = df.copy()
    for col in df.columns:
        if col in date_columns and pd.api.types.is_datetime64_any_dtype(df[col]):
            # Truncate to date; NaT becomes None for Spark null.
            # Vectorised: avoid building a Python list over 100M+ rows.
            ser = pd.to_datetime(df[col])
            try:
                ser = ser.dt.tz_localize(None)
            except (TypeError, AttributeError):
                pass
            df[col] = ser.apply(lambda d: d.date() if not pd.isna(d) else None)
        elif isinstance(df[col].dtype, pd.CategoricalDtype):
            # Categorical → plain string so Spark maps it to StringType
            df[col] = df[col].astype(object).where(df[col].notna(), other=None)
        elif df[col].dtype == object:
            df[col] = df[col].where(df[col].notna(), other=None)
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            try:
                df[col] = pd.to_datetime(df[col]).dt.tz_localize(None)
            except (TypeError, AttributeError):
                pass
    # Consolidate internal Arrow buffers. Pandas 2.x + PyArrow backend leaves
    # ChunkedArrays after column-wise assignment; PySpark's createDataFrame
    # rejects these when an explicit StructType schema is provided.
    # combine_chunks() is always safe — pyarrow ships with every PySpark install.
    try:
        import pyarrow as pa
        return pa.Table.from_pandas(df, preserve_index=False).combine_chunks().to_pandas()
    except (ImportError, Exception):
        return df.copy()


def _date_columns_from_schema(schema_config: Any) -> Dict[str, set]:
    """Extract ``{table_name: {col, ...}}`` for columns declared ``type == "date"``.

    Misata's :class:`~misata.schema.Column` distinguishes ``date`` from
    ``datetime`` only in its ``type`` field — both land in pandas as
    ``datetime64[ns]``. This recovers the distinction so date columns can be
    written to Delta as ``DateType``.
    """
    result: Dict[str, set] = {}
    try:
        for table in schema_config.tables:
            cols = schema_config.get_columns(table.name)
            date_cols = {c.name for c in cols if getattr(c, "type", None) == "date"}
            if date_cols:
                result[table.name] = date_cols
    except Exception:
        # Be forgiving — if the schema shape is unexpected, fall back to no date hints
        pass
    return result


def _date_columns_from_delta(spark: Any, full_name: str) -> set:
    """Return the set of ``DateType`` column names in an existing Delta table.

    Used by :func:`append_to_delta` so the appended batch conforms to the
    target table's existing date typing rather than imposing its own.
    """
    try:
        from pyspark.sql.types import DateType
        return {
            f.name for f in spark.table(full_name).schema.fields
            if isinstance(f.dataType, DateType)
        }
    except Exception:
        return set()


def _full_table_name(
    table: str,
    catalog: Optional[str],
    database: Optional[str],
) -> str:
    """Assemble a fully-qualified Delta table identifier.

    Examples::

        _full_table_name("orders", "dev_cat", "bronze") → "dev_cat.bronze.orders"
        _full_table_name("orders", None, "bronze")       → "bronze.orders"
        _full_table_name("orders", None, None)            → "orders"
    """
    parts = [p for p in [catalog, database, table] if p]
    return ".".join(parts)


def _sql_quote(identifier: str) -> str:
    """Backtick-quote each part of a dot-separated Spark SQL identifier.

    Prevents SQL injection when catalog/database/table names contain special
    characters or come from user-supplied arguments.

    Examples::

        _sql_quote("dev_cat.bronze.orders") → "`dev_cat`.`bronze`.`orders`"
        _sql_quote("workspace")             → "`workspace`"
    """
    return ".".join(f"`{part.replace('`', '')}`" for part in identifier.split("."))


def _table_exists_uc(spark: Any, full_name: str) -> bool:
    """UC-safe table existence check that works with 3-part ``catalog.schema.table`` names.

    ``spark.catalog.tableExists()`` raises or returns incorrect results for
    3-part names on some Databricks runtimes (DBR < 13). Using
    ``DESCRIBE TABLE`` is reliable across Hive metastore and Unity Catalog.
    """
    try:
        spark.sql(f"DESCRIBE TABLE {_sql_quote(full_name)}")
        return True
    except Exception:
        return False


def _uc_foreign_keys(spark: Any, catalog: str, database: str) -> Dict[str, Dict[str, Any]]:
    """Read FK relationships declared in Unity Catalog INFORMATION_SCHEMA.

    Unity Catalog (DBR 11.2+) supports formal PK/FK constraints.  When present
    these are more reliable than the name-heuristic ``{parent}_id`` inference.

    Returns a dict in the same shape as the ``foreign_keys`` parameter of
    :func:`from_catalog_schema`::

        {"orders": {"customer_id": {"table": "customers", "column": "id"}}}

    Silently returns ``{}`` on:
    - Hive metastore (no INFORMATION_SCHEMA)
    - DBR < 11.2 (INFORMATION_SCHEMA exists but lacks referential constraints)
    - Any permission or network error
    """
    # Quick probe: check that INFORMATION_SCHEMA.TABLES is accessible before
    # running the heavier multi-join query.  Avoids long timeouts on old runtimes.
    try:
        spark.sql(
            f"SELECT 1 FROM `{catalog}`.INFORMATION_SCHEMA.TABLES LIMIT 0"
        ).collect()
    except Exception:
        return {}

    try:
        rows = spark.sql(f"""
            SELECT
                kcu.TABLE_NAME  AS child_table,
                kcu.COLUMN_NAME AS child_column,
                ccu.TABLE_NAME  AS parent_table,
                ccu.COLUMN_NAME AS parent_column
            FROM `{catalog}`.INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            JOIN `{catalog}`.INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
              ON  kcu.CONSTRAINT_NAME   = rc.CONSTRAINT_NAME
              AND kcu.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA
            JOIN `{catalog}`.INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu
              ON  rc.UNIQUE_CONSTRAINT_NAME   = ccu.CONSTRAINT_NAME
              AND rc.UNIQUE_CONSTRAINT_SCHEMA = ccu.CONSTRAINT_SCHEMA
            WHERE kcu.TABLE_SCHEMA = '{database}'
        """).collect()
        fks: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            fks.setdefault(row["child_table"], {})[row["child_column"]] = {
                "table": row["parent_table"],
                "column": row["parent_column"],
            }
        return fks
    except Exception:
        return {}


def _infer_fk_relationships(
    table_names: List[str],
    schemas: Dict[str, Any],
) -> Dict[str, Dict[str, str]]:
    """Heuristic: infer FK relationships from column names of the form ``{parent_singular}_id``.

    Returns a dict in the same format as the ``foreign_keys`` parameter of
    :func:`from_catalog_schema`, e.g.::

        {"orders": {"customer_id": {"table": "customers", "column": "id"}}}
    """
    table_set = set(table_names)
    fks: Dict[str, Dict[str, str]] = {}

    # Build a lookup: singular form → table name
    singular_to_table: Dict[str, str] = {}
    for t in table_names:
        singular_to_table[t] = t
        # naive de-pluralisation: strip trailing 's' or 'es'
        if t.endswith("ies"):
            singular_to_table[t[:-3] + "y"] = t
        elif t.endswith("ses") or t.endswith("xes") or t.endswith("zes"):
            singular_to_table[t[:-2]] = t
        elif t.endswith("s"):
            singular_to_table[t[:-1]] = t

    unresolved: List[str] = []
    for table_name, col_defs in schemas.items():
        for col_name in col_defs:
            if not col_name.endswith("_id") or col_name == "id":
                continue
            prefix = col_name[:-3]  # strip "_id"
            parent = singular_to_table.get(prefix)
            if parent and parent != table_name:
                fks.setdefault(table_name, {})[col_name] = {
                    "table": parent,
                    "column": "id",
                }
            elif parent is None:
                # A *_id column we could not map to any table — the user may have
                # an FK we cannot see (non-conventional naming). Surface it loudly
                # rather than silently producing a table with no relationship,
                # which would undermine the referential-integrity guarantee.
                unresolved.append(f"{table_name}.{col_name}")

    if unresolved:
        warnings.warn(
            "from_catalog_schema could not auto-infer a parent table for these "
            f"FK-looking columns: {unresolved}. Pass them explicitly via "
            "foreign_keys={'<table>': {'<col>': {'table': '<parent>', 'column': 'id'}}} "
            "to guarantee referential integrity.",
            UserWarning,
            stacklevel=3,
        )

    return fks


# ---------------------------------------------------------------------------
# Core: pandas → Spark conversion
# ---------------------------------------------------------------------------

def to_spark(
    tables: Dict[str, pd.DataFrame],
    spark: "SparkSession",
    *,
    infer_schema: bool = False,
    date_columns: Optional[Dict[str, Any]] = None,
    schema_config: Optional["SchemaConfig"] = None,
) -> Dict[str, "SparkDataFrame"]:
    """Convert a dict of pandas DataFrames to a dict of Spark DataFrames.

    Misata returns ``{table_name: pd.DataFrame}``; this function promotes
    every DataFrame to a Spark DataFrame with an explicit, type-correct schema.

    Args:
        tables:        Dict mapping table name → ``pd.DataFrame`` (Misata output).
        spark:         Active ``SparkSession``.
        infer_schema:  If ``True``, let Spark infer the schema from the data.
                       Not recommended — Spark can widen ints to doubles or fail
                       on nullable integer columns. Default: ``False``.
        date_columns:  Optional ``{table_name: [col, ...]}`` naming columns that
                       should be written as ``DateType`` rather than
                       ``TimestampType``. Misata represents both ``date`` and
                       ``datetime`` as ``datetime64[ns]``, so this distinction
                       must come from the schema.
        schema_config: Optional :class:`~misata.schema.SchemaConfig`. If given,
                       date columns are auto-detected from it (overrides nothing
                       you pass explicitly via ``date_columns``).

    Returns:
        Dict mapping table name → ``pyspark.sql.DataFrame``.

    Example::

        import misata
        from misata.spark import to_spark

        tables = misata.generate_from_schema(schema)
        spark_tables = to_spark(tables, spark, schema_config=schema)

        spark_tables["orders"].printSchema()
        spark_tables["orders"].show(5)
    """
    _require_pyspark("to_spark()")

    # Resolve per-table date columns: schema auto-detect ∪ explicit override
    resolved: Dict[str, set] = {}
    if schema_config is not None:
        resolved.update(_date_columns_from_schema(schema_config))
    if date_columns:
        for tname, cols in date_columns.items():
            resolved.setdefault(tname, set()).update(set(cols))

    result: Dict[str, SparkDataFrame] = {}
    for name, df in tables.items():
        dcols = resolved.get(name, set())
        clean = _normalize_for_spark(df, date_columns=dcols)
        if infer_schema:
            result[name] = spark.createDataFrame(clean)
        else:
            struct = _build_spark_schema(clean, date_columns=dcols)
            result[name] = spark.createDataFrame(clean, schema=struct)
    return result


# ---------------------------------------------------------------------------
# Delta write
# ---------------------------------------------------------------------------

@dataclass
class DeltaWriteResult:
    """Result returned by :func:`write_delta` and :func:`generate_to_delta`.

    Attributes:
        table_paths:   Mapping of table name → fully-qualified Delta path written.
        rows_written:  Mapping of table name → row count written.
        errors:        Mapping of table name → error message (empty on full success).
    """

    table_paths: Dict[str, str] = field(default_factory=dict)
    rows_written: Dict[str, int] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """``True`` if all tables were written without errors."""
        return len(self.errors) == 0

    def summary(self) -> str:
        lines: List[str] = []
        for name, path in self.table_paths.items():
            if name in self.errors:
                lines.append(f"  ✗ {name}: {self.errors[name]}")
            else:
                rows = self.rows_written.get(name, "?")
                lines.append(f"  ✅ {name} ({rows:,} rows) → {path}" if isinstance(rows, int) else f"  ✅ {name} → {path}")
        if self.errors:
            for name, err in self.errors.items():
                if name not in self.table_paths:
                    lines.append(f"  ✗ {name}: {err}")
        return "\n".join(lines) if lines else "  (no tables written)"

    def raise_on_error(self) -> "DeltaWriteResult":
        """Raise ``RuntimeError`` if any tables failed to write."""
        if self.errors:
            msgs = "\n".join(f"  {k}: {v}" for k, v in self.errors.items())
            raise RuntimeError(f"Delta write failed for {len(self.errors)} table(s):\n{msgs}")
        return self


def write_delta(
    tables: Dict[str, pd.DataFrame],
    spark: "SparkSession",
    *,
    catalog: Optional[str] = None,
    database: Optional[str] = None,
    schema: Optional[str] = None,
    mode: str = "overwrite",
    partition_by: Optional[Dict[str, List[str]]] = None,
    cluster_by: Optional[Dict[str, List[str]]] = None,
    merge_keys: Optional[Dict[str, List[str]]] = None,
    table_properties: Optional[Dict[str, str]] = None,
    optimize_after_write: bool = False,
    create_schema_if_not_exists: bool = True,
    date_columns: Optional[Dict[str, Any]] = None,
    schema_config: Optional["SchemaConfig"] = None,
    location: Optional[Union[str, Dict[str, str]]] = None,
    verbose: bool = True,
) -> DeltaWriteResult:
    """Write Misata-generated tables to Delta Lake.

    Converts each pandas DataFrame to a Spark DataFrame with an explicit schema
    and writes it as a Delta table. Supports catalog.database.table naming
    (Unity Catalog, AWS Glue Data Catalog, Hive metastore).

    Schema-evolution semantics follow Delta best practice automatically:

    - ``mode="overwrite"`` sets ``overwriteSchema=true`` — the new schema fully
      replaces the old one (dropped columns disappear; this is what you almost
      always want when regenerating a test table).
    - ``mode="append"`` sets ``mergeSchema=true`` — new columns are added to the
      existing table and back-filled with null.
    - ``mode="merge"`` performs an idempotent upsert (``MERGE INTO``) keyed on
      ``merge_keys`` — used for CDC / SCD-style pipeline testing.

    Args:
        tables:                    Misata output — ``{table_name: pd.DataFrame}``.
        spark:                     Active ``SparkSession``.
        catalog:                   Unity Catalog catalog name (optional).
        database:                  Target database / schema name (optional).
        schema:                    Alias for ``database``.
        mode:                      ``"overwrite"`` (default), ``"append"``,
                                   ``"merge"`` (upsert — requires ``merge_keys``),
                                   or ``"error"`` (fail if exists).
        partition_by:              Per-table Hive-style partition columns, e.g.
                                   ``{"events": ["event_date"]}``. Mutually
                                   exclusive with ``cluster_by`` per table.
        cluster_by:                Per-table **liquid clustering** columns
                                   (Delta 3.1+ / Databricks Runtime 13.3+), e.g.
                                   ``{"orders": ["customer_id", "status"]}``.
                                   Preferred over ``partition_by`` on modern Delta.
        merge_keys:                Per-table key columns for ``mode="merge"``,
                                   e.g. ``{"customers": ["id"]}``.
        table_properties:          Delta table properties applied to every table,
                                   e.g. ``{"delta.autoOptimize.optimizeWrite": "true"}``.
        optimize_after_write:      Run ``OPTIMIZE`` on each table after writing.
        create_schema_if_not_exists: Issue ``CREATE SCHEMA IF NOT EXISTS`` first.
        date_columns:              Optional ``{table: [col, ...]}`` of columns to
                                   write as ``DateType`` (see :func:`to_spark`).
        schema_config:             Optional ``SchemaConfig`` — date columns are
                                   auto-detected from it.
        location:                  Cloud storage root for **external** Unity Catalog
                                   tables.  Can be a single base path (each table is
                                   written to ``<location>/<table_name>``) or a
                                   per-table dict (``{"orders": "gs://bucket/orders"}``).
                                   When ``None`` (default) tables are written as
                                   **managed** Delta tables — the recommended mode for
                                   Unity Catalog.
        verbose:                   Print a progress line per table. Default ``True``.

    Returns:
        :class:`DeltaWriteResult` with paths, row counts, and any errors.

    Raises:
        ImportError: If PySpark is not installed.

    Example::

        from misata.spark import write_delta

        tables = misata.generate_from_schema(schema)
        result = write_delta(
            tables, spark,
            catalog="dev_catalog", database="bronze", mode="overwrite",
            cluster_by={"orders": ["customer_id"]},
            table_properties={"delta.autoOptimize.optimizeWrite": "true"},
            schema_config=schema,
        )
        result.raise_on_error()
    """
    _require_pyspark("write_delta()")

    db = database or schema
    result = DeltaWriteResult()

    # Resolve per-table date columns (schema auto-detect ∪ explicit override)
    date_map: Dict[str, set] = {}
    if schema_config is not None:
        date_map.update(_date_columns_from_schema(schema_config))
    if date_columns:
        for tname, cols in date_columns.items():
            date_map.setdefault(tname, set()).update(set(cols))

    # Create database/schema if requested
    if create_schema_if_not_exists and db:
        db_full = f"{catalog}.{db}" if catalog else db
        try:
            spark.sql(f"CREATE SCHEMA IF NOT EXISTS {_sql_quote(db_full)}")
        except Exception as exc:
            warnings.warn(f"Could not create schema '{db_full}': {exc}")

    for table_name, df in tables.items():
        full_name = _full_table_name(table_name, catalog, db)
        try:
            dcols = date_map.get(table_name, set())
            clean = _normalize_for_spark(df, date_columns=dcols)
            struct = _build_spark_schema(clean, date_columns=dcols)
            spark_df = spark.createDataFrame(clean, schema=struct)

            if mode == "merge":
                keys = (merge_keys or {}).get(table_name)
                if not keys:
                    raise ValueError(
                        f"mode='merge' requires merge_keys for table '{table_name}', "
                        f"e.g. merge_keys={{'{table_name}': ['id']}}"
                    )
                _merge_into_delta(spark, spark_df, full_name, keys,
                                  create_if_missing=True)
            else:
                writer = spark_df.write.format("delta").mode(mode)

                # Schema-evolution option must match the write mode:
                #   overwrite → overwriteSchema (replace), append → mergeSchema (add)
                if mode == "overwrite":
                    writer = writer.option("overwriteSchema", "true")
                elif mode == "append":
                    writer = writer.option("mergeSchema", "true")

                # Liquid clustering takes precedence over Hive partitioning
                clustered = bool(cluster_by and table_name in cluster_by)
                if clustered:
                    try:
                        writer = writer.clusterBy(*cluster_by[table_name])
                    except (AttributeError, TypeError):
                        # clusterBy unavailable on this Delta version — fall back
                        warnings.warn(
                            f"Liquid clustering not supported by this Delta build; "
                            f"writing '{table_name}' without clustering."
                        )
                        clustered = False
                if not clustered and partition_by and table_name in partition_by:
                    writer = writer.partitionBy(*partition_by[table_name])

                if table_properties:
                    for k, v in table_properties.items():
                        writer = writer.option(k, v)

                # External table: write to a caller-supplied cloud path.
                # UC managed tables (no location) are the default.
                if location:
                    tbl_path = (
                        location.get(table_name)
                        if isinstance(location, dict)
                        else f"{location.rstrip('/')}/{table_name}"
                    )
                    if tbl_path:
                        writer = writer.option("path", tbl_path)

                writer.saveAsTable(full_name)

            if optimize_after_write:
                try:
                    spark.sql(f"OPTIMIZE {_sql_quote(full_name)}")
                except Exception:
                    pass  # OPTIMIZE is best-effort

            result.table_paths[table_name] = full_name
            result.rows_written[table_name] = len(df)

            if verbose:
                print(f"  ✅ {table_name} ({len(df):,} rows) → {full_name}")

        except Exception as exc:
            result.errors[table_name] = str(exc)
            result.table_paths[table_name] = full_name
            if verbose:
                print(f"  ✗ {table_name}: {exc}")

    return result


def _merge_into_delta(
    spark: "SparkSession",
    source_df: "SparkDataFrame",
    target_table: str,
    keys: List[str],
    *,
    create_if_missing: bool = True,
) -> None:
    """Upsert ``source_df`` into ``target_table`` via Delta ``MERGE INTO``.

    Matches on ``keys``; updates all columns on match, inserts on no-match.
    If the target table does not exist and ``create_if_missing`` is ``True``,
    it is created from the source (first write).
    """
    from delta.tables import DeltaTable

    if not _table_exists_uc(spark, target_table):
        if create_if_missing:
            source_df.write.format("delta").mode("overwrite") \
                     .option("overwriteSchema", "true").saveAsTable(target_table)
            return
        raise ValueError(f"Target table '{target_table}' does not exist for merge.")

    import re as _re
    _invalid = [k for k in keys if not _re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', k)]
    if _invalid:
        raise ValueError(
            f"merge_keys contains invalid column name(s): {_invalid}. "
            "Keys must be plain identifiers (letters, digits, underscores)."
        )
    target = DeltaTable.forName(spark, target_table)
    cond = " AND ".join([f"t.`{k}` = s.`{k}`" for k in keys])
    (
        target.alias("t")
        .merge(source_df.alias("s"), cond)
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )


# ---------------------------------------------------------------------------
# Incremental append
# ---------------------------------------------------------------------------

def append_to_delta(
    schema_config: "SchemaConfig",
    spark: "SparkSession",
    n_rows: Dict[str, int],
    *,
    catalog: Optional[str] = None,
    database: Optional[str] = None,
    schema: Optional[str] = None,
    seed: Optional[int] = None,
    verbose: bool = True,
) -> DeltaWriteResult:
    """Generate additional rows and append them to existing Delta tables.

    Reads the current maximum ID from each Delta table to compute offsets,
    generates new rows with non-colliding IDs, and appends them. FK integrity
    is maintained within the new batch (new child rows only reference new
    parent rows — they do not cross-reference existing data).

    Args:
        schema_config: The :class:`~misata.schema.SchemaConfig` used to generate
                       the original dataset.
        spark:         Active ``SparkSession``.
        n_rows:        Per-table row counts for the new batch, e.g.
                       ``{"customers": 200, "orders": 800}``. Tables omitted here
                       use their original ``row_count`` from the schema.
        catalog:       Unity Catalog catalog name (optional).
        database:      Target database / schema name.
        schema:        Alias for ``database``.
        seed:          Seed for the new batch (defaults to ``schema.seed + 10``).
        verbose:       Print progress. Default ``True``.

    Returns:
        :class:`DeltaWriteResult` — new-batch paths and row counts.

    Example::

        # Day 1: generate initial dataset
        result = generate_to_delta(schema, spark, database="bronze")

        # Day 2: add 200 more customers and 800 orders
        append_to_delta(
            schema, spark,
            n_rows={"customers": 200, "orders": 800},
            database="bronze",
        )
    """
    _require_pyspark("append_to_delta()")

    import copy
    import misata as _misata

    db = database or schema
    new_schema = copy.deepcopy(schema_config)
    new_schema.seed = seed if seed is not None else ((schema_config.seed or 0) + 10)

    # Apply requested row counts
    for t in new_schema.tables:
        if t.name in n_rows:
            t.row_count = n_rows[t.name]

    # Read existing max IDs from Delta to compute per-table offsets
    pk_offsets: Dict[str, int] = {}
    for t in new_schema.tables:
        full_name = _full_table_name(t.name, catalog, db)
        try:
            rows = spark.sql(
                f"SELECT COALESCE(MAX(id), 0) AS max_id FROM {_sql_quote(full_name)}"
            ).limit(1).collect()
            pk_offsets[t.name] = int(rows[0]["max_id"]) + 1 if rows else 0
        except Exception:
            pk_offsets[t.name] = 0

    # Generate new batch
    new_tables = _misata.generate_from_schema(new_schema)

    # First pass: offset PKs so they don't collide with existing rows.
    for name, df in new_tables.items():
        offset = pk_offsets.get(name, 0)
        if offset and "id" in df.columns:
            try:
                df = df.copy()
                df["id"] = df["id"] + offset
                new_tables[name] = df
            except Exception:
                pass

    # Second pass: shift FK columns so child rows still reference the shifted parent PKs.
    for rel in new_schema.relationships:
        parent_offset = pk_offsets.get(rel.parent_table, 0)
        if not parent_offset:
            continue
        child_df = new_tables.get(rel.child_table)
        if child_df is None:
            continue
        if rel.child_key in child_df.columns:
            try:
                child_df = child_df.copy()
                child_df[rel.child_key] = child_df[rel.child_key] + parent_offset
                new_tables[rel.child_table] = child_df
            except Exception:
                pass

    # Conform date typing to whatever the EXISTING table already uses, so the
    # append never conflicts with a base table written under different date
    # semantics (e.g. base written without schema_config → dates as Timestamp).
    # The target table's schema is authoritative for an append.
    target_dates = {
        t.name: _date_columns_from_delta(spark, _full_table_name(t.name, catalog, db))
        for t in new_schema.tables
    }
    target_dates = {k: v for k, v in target_dates.items() if v}

    return write_delta(
        new_tables,
        spark,
        catalog=catalog,
        database=db,
        mode="append",
        date_columns=target_dates or None,
        verbose=verbose,
    )


# ---------------------------------------------------------------------------
# Streaming write (100M+ rows without memory buffer)
# ---------------------------------------------------------------------------

def write_delta_stream(
    schema_config: "SchemaConfig",
    spark: "SparkSession",
    *,
    catalog: Optional[str] = None,
    database: Optional[str] = None,
    schema: Optional[str] = None,
    batch_size: int = 100_000,
    partition_by: Optional[Dict[str, List[str]]] = None,
    table_properties: Optional[Dict[str, str]] = None,
    optimize_after_write: bool = False,
    create_schema_if_not_exists: bool = True,
    verbose: bool = True,
) -> DeltaWriteResult:
    """Write a very large Misata dataset to Delta in streaming batches.

    Uses :func:`misata.generate_stream` to yield batches without buffering
    the full dataset in memory. Suitable for datasets with tens or hundreds of
    millions of rows.

    Args:
        schema_config:             Schema to generate from.
        spark:                     Active ``SparkSession``.
        catalog:                   Unity Catalog catalog name (optional).
        database:                  Target database / schema name.
        schema:                    Alias for ``database``.
        batch_size:                Rows per generation batch (default 100,000).
        partition_by:              Per-table partition columns.
        table_properties:          Delta table properties.
        optimize_after_write:      Run ``OPTIMIZE`` after all batches.
        create_schema_if_not_exists: Create schema if missing.
        verbose:                   Print per-batch progress.

    Returns:
        :class:`DeltaWriteResult` with cumulative row counts.

    Example::

        schema.tables[0].row_count = 5_000_000  # 5M orders
        result = write_delta_stream(schema, spark, database="bronze", batch_size=200_000)
    """
    _require_pyspark("write_delta_stream()")

    from misata.simulator import DataSimulator

    db = database or schema
    result = DeltaWriteResult()
    date_map = _date_columns_from_schema(schema_config)

    if create_schema_if_not_exists and db:
        db_full = f"{catalog}.{db}" if catalog else db
        try:
            spark.sql(f"CREATE SCHEMA IF NOT EXISTS {_sql_quote(db_full)}")
        except Exception as exc:
            warnings.warn(f"Could not create schema '{db_full}': {exc}")

    # Track whether we've written the first batch per table (overwrite first, append rest)
    first_batch: Dict[str, bool] = {}
    schemas_cache: Dict[str, Any] = {}

    sim = DataSimulator(schema_config, batch_size=batch_size)
    batch_num: Dict[str, int] = {}

    for table_name, batch_df in sim.generate_all():
        full_name = _full_table_name(table_name, catalog, db)
        is_first = first_batch.get(table_name, True)
        write_mode = "overwrite" if is_first else "append"
        dcols = date_map.get(table_name, set())

        try:
            clean = _normalize_for_spark(batch_df, date_columns=dcols)

            # Build the schema from the first batch and reuse it.
            # Must be derived from `clean` (post-normalization) so date columns
            # read as python date objects and map to DateType, not TimestampType.
            if is_first:
                schemas_cache[table_name] = _build_spark_schema(clean, date_columns=dcols)

            spark_df = spark.createDataFrame(clean, schema=schemas_cache[table_name])

            writer = spark_df.write.format("delta").mode(write_mode)
            # First batch replaces the schema; later batches append to it.
            if is_first:
                writer = writer.option("overwriteSchema", "true")
            else:
                writer = writer.option("mergeSchema", "true")

            if is_first and partition_by and table_name in partition_by:
                writer = writer.partitionBy(*partition_by[table_name])

            if table_properties and is_first:
                for k, v in table_properties.items():
                    writer = writer.option(k, v)

            writer.saveAsTable(full_name)

            result.table_paths[table_name] = full_name
            result.rows_written[table_name] = (
                result.rows_written.get(table_name, 0) + len(batch_df)
            )
            batch_num[table_name] = batch_num.get(table_name, 0) + 1

            if verbose:
                total = result.rows_written[table_name]
                print(f"  ↑ {table_name} batch #{batch_num[table_name]} "
                      f"(+{len(batch_df):,} rows, {total:,} total) → {full_name}")

            first_batch[table_name] = False

        except Exception as exc:
            result.errors[table_name] = str(exc)
            if verbose:
                print(f"  ✗ {table_name}: {exc}")

    if optimize_after_write:
        for table_name, full_name in result.table_paths.items():
            try:
                spark.sql(f"OPTIMIZE {_sql_quote(full_name)}")
            except Exception:
                pass

    return result


# ---------------------------------------------------------------------------
# Schema import: Spark → Misata
# ---------------------------------------------------------------------------

def from_spark_schema(
    source: Union["StructType", "SparkDataFrame", str],
    spark: Optional["SparkSession"] = None,
    *,
    table_name: str = "table",
    row_count: int = 1_000,
    foreign_keys: Optional[Dict[str, str]] = None,
    seed: Optional[int] = 42,
) -> "SchemaConfig":
    """Convert a single Spark schema to a Misata :class:`~misata.schema.SchemaConfig`.

    Accepts three source types:

    - ``StructType``  — a Spark schema object
    - ``DataFrame``   — schema is read from ``.schema``
    - ``str``         — interpreted as a fully-qualified table name; requires ``spark``

    Args:
        source:       A ``StructType``, ``DataFrame``, or fully-qualified table name.
        spark:        Active ``SparkSession`` (required when ``source`` is a string).
        table_name:   Name to give the generated table when ``source`` is a
                      ``StructType``. Ignored for DataFrame/string inputs.
        row_count:    Number of rows to generate. Default 1,000.
        foreign_keys: Explicit FK mappings for this table, e.g.::

                          {"customer_id": {"table": "customers", "column": "id"}}

        seed:         Random seed. Default 42.

    Returns:
        :class:`~misata.schema.SchemaConfig` ready for
        :func:`~misata.generate_from_schema`.

    Example::

        # From an existing DataFrame
        schema = from_spark_schema(spark.table("prod.bronze.orders"), row_count=2000,
                                   foreign_keys={"customer_id": {"table": "customers", "column": "id"}})

        # From a StructType
        from pyspark.sql.types import StructType, StructField, StringType, LongType
        struct = StructType([
            StructField("id", LongType(), nullable=False),
            StructField("email", StringType(), nullable=True),
        ])
        schema = from_spark_schema(struct, table_name="users", row_count=500)
    """
    _require_pyspark("from_spark_schema()")

    from pyspark.sql.types import StructType

    if isinstance(source, str):
        if spark is None:
            raise ValueError("A SparkSession is required when source is a table name string.")
        df_schema = spark.table(source).schema
        table_name = source.split(".")[-1]
    elif isinstance(source, StructType):
        df_schema = source
    else:
        # A DataFrame (classic or Spark Connect) — read .schema only. Avoid the
        # private _jdf JVM bridge, which does not exist on Spark Connect sessions.
        df_schema = source.schema
        # Caller-provided table_name is used as-is; DataFrames have no stable name.

    col_dict: Dict[str, Any] = {
        "__rows__": row_count,
    }

    has_id = any(f.name.lower() == "id" for f in df_schema.fields)

    for f in df_schema.fields:
        col_def = _spark_field_to_col_def(f)

        # Mark likely PK
        if f.name.lower() == "id":
            col_def["primary_key"] = True

        # Apply explicit FK mappings
        if foreign_keys and f.name in foreign_keys:
            fk = foreign_keys[f.name]
            col_def["foreign_key"] = fk if isinstance(fk, dict) else {"table": fk, "column": "id"}

        col_dict[f.name] = col_def

    from misata.compat import from_dict_schema

    return from_dict_schema(
        {table_name: col_dict},
        row_count=row_count,
        seed=seed,
    )


def from_catalog_table(
    table_name: str,
    spark: "SparkSession",
    *,
    row_count: int = 1_000,
    foreign_keys: Optional[Dict[str, str]] = None,
    seed: Optional[int] = 42,
) -> "SchemaConfig":
    """Import a single Unity Catalog / Hive table schema into Misata.

    Args:
        table_name:   Fully-qualified table name, e.g. ``"prod.bronze.orders"``
                      or ``"bronze.orders"`` or just ``"orders"``.
        spark:        Active ``SparkSession``.
        row_count:    Number of rows to generate. Default 1,000.
        foreign_keys: FK declarations for this table (column → FK target)::

                          {"customer_id": {"table": "customers", "column": "id"}}

        seed:         Random seed. Default 42.

    Returns:
        :class:`~misata.schema.SchemaConfig`.

    Example::

        schema = from_catalog_table("dev_catalog.bronze.orders", spark,
                                    row_count=5000,
                                    foreign_keys={"customer_id": {"table": "customers", "column": "id"}})
        tables = misata.generate_from_schema(schema)
    """
    _require_pyspark("from_catalog_table()")

    short_name = table_name.split(".")[-1]
    return from_spark_schema(
        table_name,
        spark,
        table_name=short_name,
        row_count=row_count,
        foreign_keys=foreign_keys,
        seed=seed,
    )


def from_catalog_schema(
    spark: "SparkSession",
    database: str,
    *,
    catalog: Optional[str] = None,
    row_counts: Optional[Dict[str, int]] = None,
    foreign_keys: Optional[Dict[str, Dict[str, Any]]] = None,
    infer_foreign_keys: bool = True,
    seed: Optional[int] = 42,
) -> "SchemaConfig":
    """Import all tables in a Spark database / Unity Catalog schema into Misata.

    Reads the schema of every table in ``database`` and assembles them into a
    single multi-table :class:`~misata.schema.SchemaConfig`. FK relationships
    are inferred automatically from column naming conventions (``{parent}_id``
    columns) or provided explicitly.

    Args:
        spark:             Active ``SparkSession``.
        database:          Database / schema name, e.g. ``"bronze"``.
        catalog:           Unity Catalog catalog, e.g. ``"prod_catalog"`` (optional).
        row_counts:        Override row count per table, e.g. ``{"orders": 5000}``.
                           Tables not listed use 1,000 rows.
        foreign_keys:      Explicit FK declarations keyed by *child table name*::

                               {
                                 "orders": {
                                   "customer_id": {"table": "customers", "column": "id"}
                                 },
                                 "order_items": {
                                   "order_id": {"table": "orders", "column": "id"}
                                 },
                               }

        infer_foreign_keys: Automatically infer FKs from ``{parent}_id`` column
                            naming conventions. Applied in addition to any
                            explicit ``foreign_keys``. Default ``True``.
        seed:              Random seed. Default 42.

    Returns:
        Multi-table :class:`~misata.schema.SchemaConfig`.

    Example::

        # Mirror the entire bronze layer of a production catalog
        schema = from_catalog_schema(
            spark,
            database="bronze",
            catalog="prod_catalog",
            row_counts={"customers": 500, "orders": 2000, "order_items": 6000},
        )
        tables = misata.generate_from_schema(schema)
        write_delta(tables, spark, catalog="dev_catalog", database="bronze")
    """
    _require_pyspark("from_catalog_schema()")

    db_full = f"{catalog}.{database}" if catalog else database

    # Discover all tables in the database
    try:
        rows = spark.sql(f"SHOW TABLES IN {_sql_quote(db_full)}").collect()
        table_names = [r.tableName for r in rows]
    except Exception:
        # Fallback: Spark catalog API (works on Hive metastore, may fail on UC 3-part names)
        try:
            table_names = [t.name for t in spark.catalog.listTables(db_full)]
        except Exception as exc:
            raise RuntimeError(
                f"Could not list tables in '{db_full}'. "
                f"Check that the catalog/database exists and you have READ permission.\n"
                f"Original error: {exc}"
            ) from exc

    if not table_names:
        warnings.warn(f"No tables found in '{db_full}'.")

    row_counts = row_counts or {}
    foreign_keys = foreign_keys or {}

    # Build a raw dict-schema for from_dict_schema
    raw_schema: Dict[str, Any] = {}

    for tname in table_names:
        full_name = _full_table_name(tname, catalog, database)
        try:
            struct = spark.table(full_name).schema
        except Exception as exc:
            warnings.warn(f"Skipping table '{tname}': could not read schema — {exc}")
            continue

        col_dict: Dict[str, Any] = {
            "__rows__": row_counts.get(tname, 1_000),
        }

        explicit_fks = foreign_keys.get(tname, {})

        for f in struct.fields:
            col_def = _spark_field_to_col_def(f)

            if f.name.lower() == "id":
                col_def["primary_key"] = True

            if f.name in explicit_fks:
                fk = explicit_fks[f.name]
                col_def["foreign_key"] = fk if isinstance(fk, dict) else {
                    "table": fk, "column": "id"
                }

            col_dict[f.name] = col_def

        raw_schema[tname] = col_dict

    # Prefer formally declared UC FK constraints from INFORMATION_SCHEMA (UC only).
    # Fall back to column-name heuristics when constraints are absent or on Hive.
    if catalog and infer_foreign_keys:
        uc_fks = _uc_foreign_keys(spark, catalog, database)
        for tname, cols in uc_fks.items():
            for col_name, fk_def in cols.items():
                if tname in raw_schema and col_name in raw_schema[tname]:
                    if "foreign_key" not in raw_schema[tname][col_name]:
                        raw_schema[tname][col_name]["foreign_key"] = fk_def

    # Heuristic name-based inference (applied after UC constraints so it never
    # overwrites formally declared relationships).
    if infer_foreign_keys:
        inferred = _infer_fk_relationships(table_names, raw_schema)
        for tname, cols in inferred.items():
            for col_name, fk_def in cols.items():
                # Don't overwrite explicit or UC-declared FKs
                if col_name not in raw_schema.get(tname, {}):
                    continue
                existing = raw_schema[tname][col_name]
                if "foreign_key" not in existing:
                    existing["foreign_key"] = fk_def

    from misata.compat import from_dict_schema

    return from_dict_schema(raw_schema, row_count=1_000, seed=seed)


# ---------------------------------------------------------------------------
# Referential integrity verification on Delta
# ---------------------------------------------------------------------------

@dataclass
class SparkIntegrityViolation:
    """A single FK violation found in Delta tables."""

    child_table: str
    child_column: str
    parent_table: str
    parent_column: str
    orphan_count: int
    sample_orphan_values: List[Any] = field(default_factory=list)

    @property
    def relationship(self) -> str:
        return f"{self.child_table}.{self.child_column} → {self.parent_table}.{self.parent_column}"

    def __str__(self) -> str:
        sample = f"  sample: {self.sample_orphan_values}" if self.sample_orphan_values else ""
        return f"{self.relationship}: {self.orphan_count:,} orphan rows{sample}"


@dataclass
class SparkIntegrityReport:
    """Result of :func:`verify_delta_integrity`.

    Attributes:
        violations: List of :class:`SparkIntegrityViolation` objects.
        ok:         ``True`` iff no violations were found.
    """

    violations: List[SparkIntegrityViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.violations) == 0

    def summary(self) -> str:
        if self.ok:
            return "✅ Referential integrity OK — 0 violations."
        lines = [f"✗ {len(self.violations)} FK violation(s) found:"]
        for v in self.violations:
            lines.append(f"  • {v}")
        return "\n".join(lines)

    def raise_if_invalid(self) -> "SparkIntegrityReport":
        """Raise ``ValueError`` listing all violations."""
        if not self.ok:
            raise ValueError(self.summary())
        return self


def verify_delta_integrity(
    spark: "SparkSession",
    relationships: List[Dict[str, str]],
    *,
    catalog: Optional[str] = None,
    database: Optional[str] = None,
    schema: Optional[str] = None,
    sample_size: int = 5,
) -> SparkIntegrityReport:
    """Verify referential integrity across Delta tables using Spark SQL anti-joins.

    Runs a ``LEFT ANTI JOIN`` for every declared FK relationship and counts
    orphan rows (child rows whose FK value has no matching parent PK).

    Args:
        spark:          Active ``SparkSession``.
        relationships:  List of FK relationship dicts. Each dict must contain
                        at least ``"from_table"``, ``"from_column"``,
                        ``"to_table"``, ``"to_column"``::

                            [
                              {"from_table": "orders",      "from_column": "customer_id",
                               "to_table":   "customers",   "to_column":   "id"},
                              {"from_table": "order_items", "from_column": "order_id",
                               "to_table":   "orders",      "to_column":   "id"},
                            ]

                        Alternatively, use shorthand ``"from"``/``"to"`` keys with
                        dot notation::

                            [{"from": "orders.customer_id", "to": "customers.id"}]

        catalog:        Unity Catalog catalog name (optional — used to qualify table
                        names if they are unqualified single-word names).
        database:       Database / schema name (optional — same as above).
        schema:         Alias for ``database``.
        sample_size:    Number of sample orphan values to include in the report
                        for each violation (default 5).

    Returns:
        :class:`SparkIntegrityReport`.

    Raises:
        ImportError: If PySpark is not installed.

    Example::

        report = verify_delta_integrity(
            spark,
            relationships=[
                {"from_table": "orders",      "from_column": "customer_id",
                 "to_table":   "customers",   "to_column":   "id"},
                {"from_table": "order_items", "from_column": "order_id",
                 "to_table":   "orders",      "to_column":   "id"},
            ],
            database="bronze",
        )
        print(report.summary())
        report.raise_if_invalid()  # raises ValueError if any FK is broken
    """
    _require_pyspark("verify_delta_integrity()")

    db = database or schema
    violations: List[SparkIntegrityViolation] = []

    def _qualify(table: str) -> str:
        if "." in table:
            return table
        return _full_table_name(table, catalog, db)

    def _parse_rel(rel: Dict[str, str]) -> Tuple[str, str, str, str]:
        if "from" in rel and "to" in rel:
            from_parts = rel["from"].rsplit(".", 1)
            to_parts = rel["to"].rsplit(".", 1)
            return from_parts[0], from_parts[1], to_parts[0], to_parts[1]
        return (
            rel["from_table"], rel["from_column"],
            rel["to_table"],   rel["to_column"],
        )

    for rel in relationships:
        child_table, child_col, parent_table, parent_col = _parse_rel(rel)
        child_fqn  = _qualify(child_table)
        parent_fqn = _qualify(parent_table)

        try:
            orphan_df = spark.sql(f"""
                SELECT c.`{child_col}`
                FROM   {_sql_quote(child_fqn)}  c
                LEFT ANTI JOIN {_sql_quote(parent_fqn)} p ON c.`{child_col}` = p.`{parent_col}`
                WHERE  c.`{child_col}` IS NOT NULL
            """)
            orphan_count = orphan_df.count()

            if orphan_count > 0:
                samples = [
                    row[child_col]
                    for row in orphan_df.limit(sample_size).collect()
                ]
                violations.append(SparkIntegrityViolation(
                    child_table=child_table,
                    child_column=child_col,
                    parent_table=parent_table,
                    parent_column=parent_col,
                    orphan_count=orphan_count,
                    sample_orphan_values=samples,
                ))
        except Exception as exc:
            # Treat SQL errors as integrity unknown — add as warning violation
            violations.append(SparkIntegrityViolation(
                child_table=child_table,
                child_column=child_col,
                parent_table=parent_table,
                parent_column=parent_col,
                orphan_count=-1,
                sample_orphan_values=[str(exc)],
            ))

    return SparkIntegrityReport(violations=violations)


# ---------------------------------------------------------------------------
# One-liner convenience functions
# ---------------------------------------------------------------------------

def generate_to_spark(
    schema_or_story: Union["SchemaConfig", str],
    spark: "SparkSession",
    *,
    rows: int = 10_000,
    seed: Optional[int] = None,
    smart_correlations: bool = False,
) -> Dict[str, "SparkDataFrame"]:
    """Generate synthetic data and return it as Spark DataFrames.

    A one-liner that combines :func:`misata.generate_from_schema` (or
    :func:`misata.generate`) with :func:`to_spark`.

    Args:
        schema_or_story: A :class:`~misata.schema.SchemaConfig` built with
                         :func:`~misata.from_dict_schema`, or a plain-English
                         story string (no API key required).
        spark:           Active ``SparkSession``.
        rows:            Default row count (used only when a story string is
                         passed). Default 10,000.
        seed:            Random seed for reproducibility.
        smart_correlations: Auto-infer Pearson correlations between numeric
                            columns with semantically related names.

    Returns:
        Dict mapping table name → ``pyspark.sql.DataFrame``.

    Example::

        from misata.spark import generate_to_spark
        from misata import from_dict_schema

        schema = from_dict_schema({
            "customers": {
                "__rows__": 500,
                "id":    {"type": "integer", "primary_key": True},
                "email": {"type": "email"},
                "country": {"type": "string"},
            },
            "orders": {
                "__rows__": 2000,
                "id":          {"type": "integer", "primary_key": True},
                "customer_id": {"type": "integer",
                                "foreign_key": {"table": "customers", "column": "id"}},
                "total":       {"type": "float", "distribution": "lognormal",
                                "mu": 4.5, "sigma": 0.9, "min": 4.99},
            },
        })

        spark_tables = generate_to_spark(schema, spark)
        spark_tables["orders"].show(5)
    """
    _require_pyspark("generate_to_spark()")

    import misata as _misata

    if isinstance(schema_or_story, str):
        sc = _misata.parse(schema_or_story, rows=rows)
        if seed is not None:
            sc.seed = seed
        tables = _misata.generate_from_schema(sc, smart_correlations=smart_correlations)
    else:
        sc = schema_or_story
        if seed is not None:
            import copy
            sc = copy.deepcopy(sc)
            sc.seed = seed
        tables = _misata.generate_from_schema(sc, smart_correlations=smart_correlations)

    return to_spark(tables, spark, schema_config=sc)


def generate_to_delta(
    schema_or_story: Union["SchemaConfig", str],
    spark: "SparkSession",
    *,
    catalog: Optional[str] = None,
    database: Optional[str] = None,
    schema: Optional[str] = None,
    rows: int = 10_000,
    seed: Optional[int] = None,
    mode: str = "overwrite",
    partition_by: Optional[Dict[str, List[str]]] = None,
    cluster_by: Optional[Dict[str, List[str]]] = None,
    merge_keys: Optional[Dict[str, List[str]]] = None,
    table_properties: Optional[Dict[str, str]] = None,
    optimize_after_write: bool = False,
    create_schema_if_not_exists: bool = True,
    location: Optional[Union[str, Dict[str, str]]] = None,
    smart_correlations: bool = False,
    verbose: bool = True,
) -> DeltaWriteResult:
    """Generate synthetic data and write it to Delta Lake in one call.

    The highest-level convenience function in the Spark module — combines
    generation and writing. Ideal for notebooks and pipelines where you want
    realistic relational test data in Delta with a single expression.

    Args:
        schema_or_story:  A :class:`~misata.schema.SchemaConfig` or a
                          plain-English story string.
        spark:            Active ``SparkSession``.
        catalog:          Unity Catalog catalog name (optional).
        database:         Target database / schema name.
        schema:           Alias for ``database``.
        rows:             Default row count (story string only). Default 10,000.
        seed:             Random seed.
        mode:             Write mode — ``"overwrite"`` (default) or ``"append"``.
        partition_by:     Per-table partition columns.
        table_properties: Delta table properties.
        optimize_after_write: Run ``OPTIMIZE`` after writing.
        create_schema_if_not_exists: Create database if missing. Default ``True``.
        smart_correlations: Auto-infer numeric correlations.
        verbose:          Print per-table progress. Default ``True``.

    Returns:
        :class:`DeltaWriteResult`.

    Example (Databricks notebook)::

        from misata.spark import generate_to_delta
        from misata import from_dict_schema

        schema = from_dict_schema({
            "customers":   {"__rows__": 500,  "id": {"type": "integer", "primary_key": True},
                            "email": {"type": "email"}, "country": {"type": "string"}},
            "orders":      {"__rows__": 2000, "id": {"type": "integer", "primary_key": True},
                            "customer_id": {"type": "integer",
                                            "foreign_key": {"table": "customers", "column": "id"}},
                            "total": {"type": "float", "distribution": "lognormal",
                                      "mu": 4.5, "sigma": 0.9, "min": 4.99}},
            "order_items": {"__rows__": 6000, "id": {"type": "integer", "primary_key": True},
                            "order_id": {"type": "integer",
                                         "foreign_key": {"table": "orders", "column": "id"}},
                            "quantity": {"type": "integer", "min": 1, "max": 5},
                            "unit_price": {"type": "float", "distribution": "lognormal",
                                           "mu": 3.5, "sigma": 0.6, "min": 0.99}},
        })

        result = generate_to_delta(
            schema, spark,
            catalog="dev_catalog",
            database="bronze",
            mode="overwrite",
        )
        print(result.summary())
        result.raise_on_error()
    """
    _require_pyspark("generate_to_delta()")

    import misata as _misata

    db = database or schema

    if isinstance(schema_or_story, str):
        sc = _misata.parse(schema_or_story, rows=rows)
        if seed is not None:
            sc.seed = seed
        tables = _misata.generate_from_schema(sc, smart_correlations=smart_correlations)
    else:
        sc = schema_or_story
        if seed is not None:
            import copy
            sc = copy.deepcopy(sc)
            sc.seed = seed
        tables = _misata.generate_from_schema(sc, smart_correlations=smart_correlations)

    return write_delta(
        tables,
        spark,
        catalog=catalog,
        database=db,
        mode=mode,
        partition_by=partition_by,
        cluster_by=cluster_by,
        merge_keys=merge_keys,
        table_properties=table_properties,
        optimize_after_write=optimize_after_write,
        create_schema_if_not_exists=create_schema_if_not_exists,
        location=location,
        schema_config=sc,
        verbose=verbose,
    )


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------

__all__ = [
    # Core conversion
    "to_spark",
    # Delta write
    "write_delta",
    "DeltaWriteResult",
    # Incremental / streaming
    "append_to_delta",
    "write_delta_stream",
    # Schema import
    "from_spark_schema",
    "from_catalog_table",
    "from_catalog_schema",
    # Integrity
    "verify_delta_integrity",
    "SparkIntegrityReport",
    "SparkIntegrityViolation",
    # One-liners
    "generate_to_spark",
    "generate_to_delta",
]
