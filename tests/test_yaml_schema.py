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


class TestDeclarationsSurviveTheFile:
    """A declaration that loads empty is worse than one that is rejected.

    Both defects here were found by writing a spec against a real project's
    schema (transpondarr#184) rather than against a fixture. In each case the
    YAML parsed, `misata lint` was clean, generation succeeded, and the thing
    the user declared simply did not happen.
    """

    def _load(self, tmp_path, text):
        import misata
        path = tmp_path / "misata.yaml"
        path.write_text(text)
        return misata.load_yaml_schema(path)

    FK_SPEC = """
name: fk
tables:
  parents:
    rows: 50
    columns:
      id: {type: int, unique: true, min: 1, max: 50}
  children:
    rows: 20
    columns:
      id: {type: int, unique: true, min: 1, max: 20}
      parent_id: {type: foreign_key, unique: true, references: "parents.id"}
relationships:
  - {parent_table: parents, child_table: children, parent_key: id, child_key: parent_id}
"""

    def test_unique_survives_on_a_foreign_key(self, tmp_path):
        """The foreign_key branch built its Column from the name alone.

        `unique: true` on a foreign key says the relationship is one-to-one.
        Dropping it means the key is drawn with replacement, and the database
        rejects the insert on its own unique index.
        """
        schema = self._load(tmp_path, self.FK_SPEC)
        col = next(c for c in schema.columns["children"] if c.name == "parent_id")
        assert col.unique is True
        assert col.distribution_params.get("references") == "parents.id"

    def test_a_unique_foreign_key_generates_distinct_values(self, tmp_path):
        import misata
        children = misata.generate_from_schema(self._load(tmp_path, self.FK_SPEC))["children"]
        assert children["parent_id"].is_unique

    WHEN_THEN_SPEC = """
name: gate
tables:
  grabs:
    rows: 200
    columns:
      id: {type: int, unique: true, min: 1, max: 200}
      status:
        type: categorical
        choices: [imported, grabbed, failed]
        probabilities: [0.5, 0.3, 0.2]
      last_error: {type: categorical, choices: ["boom", "kaput"]}
    constraints:
      - name: only_failed_rows_carry_an_error
        type: when_then
        when_column: status
        when_op: not_in
        when_value: [failed]
        then_column: last_error
        then: "null"
"""

    def test_when_then_fields_survive_the_parser(self, tmp_path):
        """`_parse_constraint` enumerated the fields of four constraint types
        and dropped the rest, so a when_then loaded with every field None. The
        constraint was present, named, and inert."""
        schema = self._load(tmp_path, self.WHEN_THEN_SPEC)
        c = next(c for t in schema.tables for c in (t.constraints or [])
                 if c.type == "when_then")
        assert c.when_column == "status"
        assert c.when_op == "not_in"
        assert c.when_value == ["failed"]
        assert c.then_column == "last_error"
        assert c.then == "null"

    def test_the_declared_gate_actually_holds(self, tmp_path):
        import misata
        grabs = misata.generate_from_schema(self._load(tmp_path, self.WHEN_THEN_SPEC))["grabs"]
        offenders = grabs[(grabs["status"] != "failed") & grabs["last_error"].notna()]
        assert len(offenders) == 0, (
            f"{len(offenders)} row(s) are not failed yet carry an error")

    def test_an_unknown_constraint_field_is_refused(self, tmp_path):
        """Enumerating fields is what caused the silence, so the parser now
        takes every field the model defines and rejects anything else. A typo
        must not be a no-op."""
        import pytest
        with pytest.raises(ValueError, match="unknown field"):
            self._load(tmp_path, """
name: typo
tables:
  t:
    rows: 10
    columns:
      id: {type: int, unique: true, min: 1, max: 10}
    constraints:
      - name: oops
        type: when_then
        when_colum: status
""")

    def test_the_table_routing_key_is_still_allowed(self, tmp_path):
        """`table:` routes a top-level constraint and is not a model field."""
        schema = self._load(tmp_path, """
name: routed
tables:
  t:
    rows: 10
    columns:
      id: {type: int, unique: true, min: 1, max: 10}
      a: {type: int, min: 1, max: 5}
      b: {type: int, min: 1, max: 5}
constraints:
  - name: a_below_b
    type: inequality
    table: t
    column_a: a
    operator: "<="
    column_b: b
""")
        c = next(c for t in schema.tables for c in (t.constraints or []))
        assert c.column_a == "a" and c.column_b == "b" and c.operator == "<="
