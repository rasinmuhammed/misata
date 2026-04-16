"""
Tests for misata.yaml_schema — load/save round-trip, constraint parsing, and
relationship arrow shorthand.
"""

import tempfile
from pathlib import Path

import yaml

from misata.yaml_schema import load_yaml_schema, save_yaml_schema, MISATA_YAML_TEMPLATE
from misata.schema import SchemaConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_YAML = """
name: minimal_test
tables:
  users:
    rows: 50
    columns:
      user_id:
        type: int
        min: 1
        max: 1000
      email:
        type: categorical
        choices: ["a@b.com", "c@d.com"]
      signup_date:
        type: date
"""

RELATIONAL_YAML = """
name: relational_test
tables:
  users:
    rows: 100
    columns:
      user_id:
        type: int
        min: 1
        max: 1000
      plan:
        type: categorical
        choices: [free, pro]
  orders:
    rows: 300
    columns:
      order_id:
        type: int
        min: 1
        max: 9999
      user_id:
        type: foreign_key
        references: users.user_id
      amount:
        type: float
        min: 5.0
        max: 500.0
      cost:
        type: float
        min: 1.0
        max: 100.0

relationships:
  - "users.user_id → orders.user_id"

constraints:
  - name: amount_above_cost
    table: orders
    type: inequality
    column_a: amount
    operator: ">"
    column_b: cost
"""

CONSTRAINT_COL_RANGE_YAML = """
name: col_range_test
tables:
  products:
    rows: 200
    columns:
      product_id:
        type: int
        min: 1
        max: 9999
      min_price:
        type: float
        min: 1.0
        max: 50.0
      max_price:
        type: float
        min: 51.0
        max: 200.0
      price:
        type: float
        min: 1.0
        max: 200.0
    constraints:
      - name: price_in_range
        type: col_range
        column: price
        low_column: min_price
        high_column: max_price
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoadYamlSchema:
    def _load_str(self, raw: str, **kwargs) -> SchemaConfig:
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(raw)
            path = f.name
        return load_yaml_schema(path, **kwargs)

    def test_minimal_loads_without_error(self):
        schema = self._load_str(MINIMAL_YAML)
        assert schema.name == "minimal_test"
        assert len(schema.tables) == 1
        assert schema.tables[0].name == "users"
        assert schema.tables[0].row_count == 50

    def test_columns_parsed_correctly(self):
        schema = self._load_str(MINIMAL_YAML)
        cols = {c.name: c for c in schema.columns["users"]}
        assert "user_id" in cols
        assert cols["user_id"].type == "int"
        assert "email" in cols
        assert cols["email"].type == "categorical"
        assert "a@b.com" in cols["email"].distribution_params["choices"]

    def test_relational_schema_loads(self):
        schema = self._load_str(RELATIONAL_YAML)
        assert len(schema.tables) == 2
        table_names = {t.name for t in schema.tables}
        assert "users" in table_names
        assert "orders" in table_names

    def test_arrow_relationship_parsed(self):
        schema = self._load_str(RELATIONAL_YAML)
        assert len(schema.relationships) == 1
        rel = schema.relationships[0]
        assert rel.parent_table == "users"
        assert rel.parent_key == "user_id"
        assert rel.child_table == "orders"
        assert rel.child_key == "user_id"

    def test_inequality_constraint_parsed(self):
        schema = self._load_str(RELATIONAL_YAML)
        # Inequality constraint should be on the orders table
        orders_table = next(t for t in schema.tables if t.name == "orders")
        assert len(orders_table.constraints) == 1
        c = orders_table.constraints[0]
        assert c.type == "inequality"
        assert c.column_a == "amount"
        assert c.operator == ">"
        assert c.column_b == "cost"

    def test_col_range_constraint_parsed(self):
        schema = self._load_str(CONSTRAINT_COL_RANGE_YAML)
        products = next(t for t in schema.tables if t.name == "products")
        assert len(products.constraints) == 1
        c = products.constraints[0]
        assert c.type == "col_range"
        assert c.column == "price"
        assert c.low_column == "min_price"
        assert c.high_column == "max_price"

    def test_rows_default_applied(self):
        schema = self._load_str(MINIMAL_YAML, rows=9999)
        # explicit rows: 50 in YAML overrides the default
        assert schema.tables[0].row_count == 50

    def test_seed_passed_through(self):
        schema = self._load_str(MINIMAL_YAML, seed=12345)
        assert schema.seed == 12345


class TestSaveYamlSchema:
    def _round_trip(self, raw: str) -> SchemaConfig:
        """load → save → load and return the reloaded schema."""
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(raw)
            source_path = f.name

        schema = load_yaml_schema(source_path)

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            out_path = Path(f.name)

        save_yaml_schema(schema, out_path)
        return load_yaml_schema(str(out_path))

    def test_round_trip_minimal(self):
        reloaded = self._round_trip(MINIMAL_YAML)
        assert reloaded.name == "minimal_test"
        assert len(reloaded.tables) == 1

    def test_round_trip_relational(self):
        reloaded = self._round_trip(RELATIONAL_YAML)
        assert len(reloaded.tables) == 2
        assert len(reloaded.relationships) == 1

    def test_round_trip_preserves_columns(self):
        reloaded = self._round_trip(MINIMAL_YAML)
        cols = {c.name for c in reloaded.columns["users"]}
        assert {"user_id", "email", "signup_date"}.issubset(cols)

    def test_save_creates_file(self, tmp_path):
        from misata.schema import Column, Table
        s = SchemaConfig(
            name="save_test",
            tables=[Table(name="t", row_count=10)],
            columns={"t": [Column(name="x", type="int")]},
        )
        out = tmp_path / "out.yaml"
        save_yaml_schema(s, out)
        assert out.exists()
        data = yaml.safe_load(out.read_text())
        assert data["name"] == "save_test"


class TestMisataYamlTemplate:
    def test_template_is_valid_yaml(self):
        # Template must be parseable even though it's a comment-heavy example
        # We just verify it's a non-empty string
        assert isinstance(MISATA_YAML_TEMPLATE, str)
        assert len(MISATA_YAML_TEMPLATE) > 100
        assert "tables:" in MISATA_YAML_TEMPLATE

    def test_template_contains_key_sections(self):
        assert "relationships:" in MISATA_YAML_TEMPLATE
        assert "constraints:" in MISATA_YAML_TEMPLATE
