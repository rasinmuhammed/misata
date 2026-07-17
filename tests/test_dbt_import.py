"""Tests for the dbt → Misata importer (misata/dbt_import.py).

Covers properties-file parsing (both `tests:` and `data_tests:` syntaxes,
inline and `arguments:`-nested generic-test args), translation into a
SchemaConfig, and a full generation pass asserting the generated data
satisfies the dbt project's declared contract.
"""

from pathlib import Path

import pandas as pd
import pytest

from misata.dbt import detect_dbt_project
from misata.dbt_import import (
    apply_date_only_columns,
    build_schema_from_dbt,
    build_schema_from_dbt_project,
    parse_dbt_properties,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DBT_PROJECT_YML = """
name: demo
version: "1.0.0"
profile: demo
model-paths: ["models"]
seed-paths: ["seeds"]
"""

# Deliberately mixes dbt syntax generations:
#   raw_orders uses `data_tests:` with `arguments:` nesting (dbt 1.9+)
#   raw_payments uses legacy `tests:` with inline args
SEEDS_PROPERTIES = """
version: 2

seeds:
  - name: raw_customers
    description: One row per customer
    columns:
      - name: id
        data_tests: [unique, not_null]
      - name: email
        data_tests: [unique, not_null]
      - name: signup_date
  - name: raw_orders
    columns:
      - name: id
        data_tests: [unique, not_null]
      - name: customer_id
        data_tests:
          - not_null
          - relationships:
              arguments:
                to: ref('raw_customers')
                field: id
      - name: order_date
        data_type: date
      - name: status
        data_tests:
          - accepted_values:
              arguments:
                values: ['placed', 'shipped', 'completed']
  - name: raw_payments
    columns:
      - name: id
        tests: [unique, not_null]
      - name: order_id
        tests:
          - relationships:
              to: ref('raw_orders')
              field: id
      - name: payment_method
        tests:
          - accepted_values:
              values: ['credit_card', 'coupon']
          - dbt_utils.not_empty_string
"""

MODELS_PROPERTIES = """
version: 2

models:
  - name: stg_orders
    columns:
      - name: order_id
        data_tests: [unique, not_null]
"""

DBT_UTILS_PROPERTIES = """
version: 2

seeds:
  - name: line_items
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          arguments:
            combination_of_columns: [order_id, line_number]
      - dbt_utils.expression_is_true:
          expression: "sale_price <= list_price"
      - dbt_utils.expression_is_true:
          expression: "quantity >= 1"
      - dbt_utils.some_future_test
    columns:
      - name: order_id
      - name: line_number
        data_type: integer
      - name: quantity
        data_type: integer
      - name: list_price
        data_tests:
          - dbt_utils.accepted_range:
              arguments:
                min_value: 1
                max_value: 500
      - name: sale_price
        data_type: float
        tests:
          - dbt_utils.expression_is_true:
              expression: ">= 0"
      - name: sku
        tests:
          - dbt_utils.not_empty_string
      - name: warehouse_id
        tests:
          - dbt_utils.relationships_where:
              to: ref('warehouses')
              field: id
  - name: warehouses
    columns:
      - name: id
        data_tests: [unique, not_null]
"""


@pytest.fixture
def dbt_project(tmp_path: Path) -> Path:
    (tmp_path / "dbt_project.yml").write_text(DBT_PROJECT_YML)
    (tmp_path / "seeds").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "seeds" / "properties.yml").write_text(SEEDS_PROPERTIES)
    (tmp_path / "models" / "staging.yml").write_text(MODELS_PROPERTIES)
    return tmp_path


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_collects_seeds_and_models(dbt_project: Path):
    info = detect_dbt_project(dbt_project)
    entities, files_read = parse_dbt_properties(info)

    assert files_read == 2
    names = {e.name: e for e in entities}
    assert set(names) == {"raw_customers", "raw_orders", "raw_payments", "stg_orders"}
    assert names["raw_customers"].resource_type == "seed"
    assert names["stg_orders"].resource_type == "model"


def test_parse_both_test_syntaxes(dbt_project: Path):
    info = detect_dbt_project(dbt_project)
    entities, _ = parse_dbt_properties(info)
    cols = {
        (e.name, c.name): c for e in entities for c in e.columns
    }

    # data_tests with arguments: nesting (dbt 1.9+)
    fk = cols[("raw_orders", "customer_id")]
    assert fk.relationship == ("raw_customers", "id")
    assert fk.not_null

    status = cols[("raw_orders", "status")]
    assert status.accepted_values == ["placed", "shipped", "completed"]

    # legacy tests: with inline args
    fk_legacy = cols[("raw_payments", "order_id")]
    assert fk_legacy.relationship == ("raw_orders", "id")

    method = cols[("raw_payments", "payment_method")]
    assert method.accepted_values == ["credit_card", "coupon"]
    # dbt_utils.not_empty_string is now translated, not skipped
    assert method.non_empty
    assert method.skipped_tests == []

    # unique/not_null in both syntaxes
    assert cols[("raw_customers", "id")].unique
    assert cols[("raw_payments", "id")].unique

    # declared data_type survives
    assert cols[("raw_orders", "order_date")].data_type == "date"


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def test_build_schema_targets_seeds_by_default(dbt_project: Path):
    info = detect_dbt_project(dbt_project)
    entities, _ = parse_dbt_properties(info)
    schema, report = build_schema_from_dbt(entities, rows=50)

    assert sorted(t.name for t in schema.tables) == [
        "raw_customers", "raw_orders", "raw_payments",
    ]
    assert "stg_orders" not in {t.name for t in schema.tables}
    assert report.relationships_translated == 2
    assert report.accepted_values_translated == 2


def test_build_schema_models_fallback_when_no_seeds(dbt_project: Path):
    info = detect_dbt_project(dbt_project)
    entities, _ = parse_dbt_properties(info)
    models_only = [e for e in entities if e.resource_type == "model"]
    schema, _ = build_schema_from_dbt(models_only, rows=50)
    assert [t.name for t in schema.tables] == ["stg_orders"]


def test_translation_details(dbt_project: Path):
    info = detect_dbt_project(dbt_project)
    entities, _ = parse_dbt_properties(info)
    schema, report = build_schema_from_dbt(entities, rows=50)

    orders_cols = {c.name: c for c in schema.columns["raw_orders"]}
    assert orders_cols["customer_id"].type == "foreign_key"
    assert orders_cols["status"].type == "categorical"
    assert orders_cols["status"].distribution_params["choices"] == [
        "placed", "shipped", "completed",
    ]
    assert orders_cols["id"].unique

    rels = {(r.parent_table, r.child_table, r.parent_key, r.child_key)
            for r in schema.relationships}
    assert ("raw_customers", "raw_orders", "id", "customer_id") in rels
    assert ("raw_orders", "raw_payments", "id", "order_id") in rels

    # order_date was declared data_type: date → flagged date-only
    assert ("raw_orders", "order_date") in report.date_only_columns


def test_relationship_to_missing_table_degrades_gracefully():
    from misata.dbt_import import DbtColumnSpec, DbtEntitySpec

    entities = [DbtEntitySpec(
        name="orders", resource_type="seed", source_file=Path("x.yml"),
        columns=[
            DbtColumnSpec(name="id", unique=True, not_null=True),
            DbtColumnSpec(name="warehouse_id",
                          relationship=("warehouses", "id")),
        ],
    )]
    schema, report = build_schema_from_dbt(entities, rows=10)
    assert schema.relationships == []
    assert any("warehouses" in w for w in report.warnings)
    # column still generated as a plain id
    cols = {c.name: c for c in schema.columns["orders"]}
    assert cols["warehouse_id"].type == "int"


def test_missing_parent_key_column_is_injected():
    from misata.dbt_import import DbtColumnSpec, DbtEntitySpec

    entities = [
        DbtEntitySpec(
            name="customers", resource_type="seed", source_file=Path("x.yml"),
            # note: no `id` column declared
            columns=[DbtColumnSpec(name="email", unique=True)],
        ),
        DbtEntitySpec(
            name="orders", resource_type="seed", source_file=Path("x.yml"),
            columns=[
                DbtColumnSpec(name="id", unique=True),
                DbtColumnSpec(name="customer_id",
                              relationship=("customers", "id")),
            ],
        ),
    ]
    schema, _ = build_schema_from_dbt(entities, rows=10)
    customer_cols = {c.name for c in schema.columns["customers"]}
    assert "id" in customer_cols


def test_project_without_dbt_yml_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        build_schema_from_dbt_project(tmp_path)


def test_project_without_columns_raises(tmp_path: Path):
    (tmp_path / "dbt_project.yml").write_text(DBT_PROJECT_YML)
    (tmp_path / "seeds").mkdir()
    with pytest.raises(ValueError):
        build_schema_from_dbt_project(tmp_path)


# ---------------------------------------------------------------------------
# dbt_utils tests
# ---------------------------------------------------------------------------

@pytest.fixture
def dbt_utils_project(tmp_path: Path) -> Path:
    (tmp_path / "dbt_project.yml").write_text(DBT_PROJECT_YML)
    (tmp_path / "seeds").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "seeds" / "properties.yml").write_text(DBT_UTILS_PROPERTIES)
    return tmp_path


def test_dbt_utils_parsing(dbt_utils_project: Path):
    info = detect_dbt_project(dbt_utils_project)
    entities, _ = parse_dbt_properties(info)
    items = next(e for e in entities if e.name == "line_items")
    cols = {c.name: c for c in items.columns}

    assert cols["list_price"].accepted_range == (1.0, 500.0)
    assert cols["sale_price"].expression == (">=", 0.0)
    assert cols["sku"].non_empty
    assert cols["warehouse_id"].relationship == ("warehouses", "id")

    kinds = {(t.kind, str(t.payload)) for t in items.entity_tests}
    assert ("unique_combination", "['order_id', 'line_number']") in kinds
    assert ("inequality", "('sale_price', '<=', 'list_price')") in kinds
    assert ("inequality", "('quantity', '>=', 1.0)") in kinds
    # unknown dbt_utils tests are reported, not crashed on
    assert "dbt_utils.some_future_test" in items.skipped_tests


def test_dbt_utils_translation(dbt_utils_project: Path):
    schema, report = build_schema_from_dbt_project(dbt_utils_project, rows=50)

    cols = {c.name: c for c in schema.columns["line_items"]}
    # accepted_range → numeric bounds
    assert cols["list_price"].type in ("int", "float")
    assert cols["list_price"].distribution_params["min"] == 1.0
    assert cols["list_price"].distribution_params["max"] == 500.0
    # column-level ">= 0" → min bound
    assert cols["sale_price"].distribution_params["min"] == 0.0
    # entity-level "quantity >= 1" → min bound on quantity
    assert cols["quantity"].distribution_params["min"] == 1.0
    # relationships_where → plain FK
    assert cols["warehouse_id"].type == "foreign_key"

    items_table = next(t for t in schema.tables if t.name == "line_items")
    ctypes = {(c.type, tuple(c.group_by) if c.group_by else
               (c.column_a, c.operator, c.column_b)) for c in items_table.constraints}
    assert ("unique_combination", ("order_id", "line_number")) in ctypes
    assert ("inequality", ("sale_price", "<=", "list_price")) in ctypes
    assert report.dbt_utils_translated >= 6


def test_dbt_utils_generation_satisfies_contract(dbt_utils_project: Path):
    from misata.simulator import DataSimulator

    schema, report = build_schema_from_dbt_project(dbt_utils_project, rows=200, seed=3)
    sim = DataSimulator(schema)
    tables: dict = {}
    for name, batch in sim.generate_all():
        tables[name] = pd.concat([tables[name], batch], ignore_index=True) \
            if name in tables else batch

    items = tables["line_items"]
    assert (items["list_price"] >= 1).all() and (items["list_price"] <= 500).all()
    assert (items["sale_price"] >= 0).all()
    assert (items["sale_price"] <= items["list_price"]).all()
    assert (items["quantity"] >= 1).all()
    assert not items.duplicated(["order_id", "line_number"]).any()
    assert set(items["warehouse_id"]).issubset(set(tables["warehouses"]["id"]))
    assert items["sku"].astype(str).str.len().gt(0).all()


# ---------------------------------------------------------------------------
# Generation satisfies the dbt contract
# ---------------------------------------------------------------------------

def test_generated_data_satisfies_dbt_contract(dbt_project: Path):
    from misata.simulator import DataSimulator

    schema, report = build_schema_from_dbt_project(dbt_project, rows=100, seed=7)

    sim = DataSimulator(schema)
    tables: dict = {}
    for name, batch in sim.generate_all():
        tables[name] = pd.concat([tables[name], batch], ignore_index=True) \
            if name in tables else batch
    apply_date_only_columns(tables, report)

    customers, orders, payments = (
        tables["raw_customers"], tables["raw_orders"], tables["raw_payments"],
    )

    # unique tests
    assert customers["id"].is_unique
    assert customers["email"].is_unique
    assert orders["id"].is_unique

    # not_null tests
    assert orders["customer_id"].notna().all()

    # relationships tests (FK integrity)
    assert set(orders["customer_id"]).issubset(set(customers["id"]))
    assert set(payments["order_id"]).issubset(set(orders["id"]))

    # accepted_values tests
    assert set(orders["status"]).issubset({"placed", "shipped", "completed"})
    assert set(payments["payment_method"]).issubset({"credit_card", "coupon"})

    # declared data_type: date → date-only strings
    assert orders["order_date"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$").all()
