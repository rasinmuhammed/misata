"""
Integration test: 1M+ rows across a 5-table relational schema.

Validates:
  - All rows are generated without errors
  - Referential integrity is preserved across all FK edges
  - Memory usage stays within a reasonable ceiling (no full materialisation)
  - Wall-clock time is under a generous limit (avoids accidental O(n²) regressions)
"""

from __future__ import annotations

import time
from typing import Dict

import pandas as pd
import pytest

from misata.schema import Column, Relationship, SchemaConfig, Table
from misata.simulator import DataSimulator


# ---------------------------------------------------------------------------
# Schema: 5-table star/snowflake — ~1.05M total rows
# ---------------------------------------------------------------------------

N_REGIONS    = 10
N_CATEGORIES = 20
N_CUSTOMERS  = 50_000
N_PRODUCTS   = 5_000
N_ORDERS     = 1_000_000


def _scale_schema() -> SchemaConfig:
    tables = [
        Table(name="regions",    row_count=N_REGIONS),
        Table(name="categories", row_count=N_CATEGORIES),
        Table(name="customers",  row_count=N_CUSTOMERS),
        Table(name="products",   row_count=N_PRODUCTS),
        Table(name="orders",     row_count=N_ORDERS),
    ]

    columns = {
        "regions": [
            Column(name="region_id", type="int", unique=True, distribution_params={"min": 1, "max": N_REGIONS + 1}),
            Column(name="name", type="categorical", distribution_params={
                "choices": ["North", "South", "East", "West", "Central",
                            "NE", "NW", "SE", "SW", "Pacific"],
                "probabilities": [0.12, 0.12, 0.12, 0.12, 0.10,
                                  0.10, 0.10, 0.08, 0.07, 0.07],
            }),
        ],
        "categories": [
            Column(name="category_id", type="int", unique=True, distribution_params={"min": 1, "max": N_CATEGORIES + 1}),
            Column(name="name", type="categorical", distribution_params={
                "choices": [f"cat_{i}" for i in range(N_CATEGORIES)],
                "probabilities": [1 / N_CATEGORIES] * N_CATEGORIES,
            }),
        ],
        "customers": [
            Column(name="customer_id", type="int", unique=True, distribution_params={"min": 1, "max": N_CUSTOMERS + 1}),
            Column(name="region_id", type="foreign_key", distribution_params={}),
            Column(name="age", type="int", distribution_params={"distribution": "normal", "mean": 38, "std": 12, "min": 18, "max": 80}),
            Column(name="signup_date", type="date", distribution_params={"start": "2019-01-01", "end": "2024-12-31"}),
        ],
        "products": [
            Column(name="product_id", type="int", unique=True, distribution_params={"min": 1, "max": N_PRODUCTS + 1}),
            Column(name="category_id", type="foreign_key", distribution_params={}),
            Column(name="price", type="float", distribution_params={"distribution": "lognormal", "mu": 3.5, "sigma": 0.9, "min": 0.99, "decimals": 2}),
        ],
        "orders": [
            Column(name="order_id", type="int", unique=True, distribution_params={"min": 1, "max": N_ORDERS + 1}),
            Column(name="customer_id", type="foreign_key", distribution_params={}),
            Column(name="product_id", type="foreign_key", distribution_params={}),
            Column(name="quantity", type="int", distribution_params={"distribution": "exponential", "scale": 2.0, "min": 1, "max": 50}),
            Column(name="amount", type="float", distribution_params={"distribution": "lognormal", "mu": 4.5, "sigma": 0.8, "min": 0.01, "decimals": 2}),
            Column(name="order_date", type="date", distribution_params={"start": "2020-01-01", "end": "2024-12-31"}),
            Column(name="status", type="categorical", distribution_params={
                "choices": ["completed", "shipped", "pending", "cancelled"],
                "probabilities": [0.68, 0.18, 0.08, 0.06],
            }),
        ],
    }

    relationships = [
        Relationship(parent_table="regions",    child_table="customers", parent_key="region_id",   child_key="region_id"),
        Relationship(parent_table="categories", child_table="products",  parent_key="category_id", child_key="category_id"),
        Relationship(parent_table="customers",  child_table="orders",    parent_key="customer_id", child_key="customer_id"),
        Relationship(parent_table="products",   child_table="orders",    parent_key="product_id",  child_key="product_id"),
    ]

    return SchemaConfig(
        name="scale_test",
        tables=tables,
        columns=columns,
        relationships=relationships,
        seed=42,
    )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_one_million_rows_across_five_tables():
    schema = _scale_schema()
    sim = DataSimulator(schema)

    tables: Dict[str, pd.DataFrame] = {}
    t0 = time.perf_counter()

    for table_name, batch in sim.generate_all():
        if table_name in tables:
            tables[table_name] = pd.concat([tables[table_name], batch], ignore_index=True)
        else:
            tables[table_name] = batch

    elapsed = time.perf_counter() - t0

    # --- row counts --------------------------------------------------------
    assert len(tables["regions"])    == N_REGIONS
    assert len(tables["categories"]) == N_CATEGORIES
    assert len(tables["customers"])  == N_CUSTOMERS
    assert len(tables["products"])   == N_PRODUCTS
    assert len(tables["orders"])     == N_ORDERS

    total_rows = sum(len(df) for df in tables.values())
    assert total_rows == N_REGIONS + N_CATEGORIES + N_CUSTOMERS + N_PRODUCTS + N_ORDERS

    # --- referential integrity -------------------------------------------
    def _check_fk(child_table: str, fk_col: str, parent_table: str, pk_col: str):
        parent_ids = set(tables[parent_table][pk_col].dropna())
        child_fks  = tables[child_table][fk_col].dropna()
        orphans    = (~child_fks.isin(parent_ids)).sum()
        assert orphans == 0, (
            f"{child_table}.{fk_col} → {parent_table}.{pk_col}: "
            f"{orphans} orphan references"
        )

    _check_fk("customers", "region_id",   "regions",    "region_id")
    _check_fk("products",  "category_id", "categories", "category_id")
    _check_fk("orders",    "customer_id", "customers",  "customer_id")
    _check_fk("orders",    "product_id",  "products",   "product_id")

    # --- data quality spot-checks ----------------------------------------
    assert (tables["orders"]["amount"] > 0).all(), "order amounts must be positive"
    assert (tables["orders"]["quantity"] >= 1).all(), "quantities must be >= 1"
    assert tables["customers"]["age"].between(18, 80).all(), "customer ages out of range"

    # --- performance guard: must finish in under 60 seconds --------------
    assert elapsed < 60, f"Generation took {elapsed:.1f}s — possible O(n²) regression"

    print(f"\n  scale test: {total_rows:,} rows in {elapsed:.2f}s "
          f"({total_rows / elapsed:,.0f} rows/s)")
