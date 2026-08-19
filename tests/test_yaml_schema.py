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

    def test_templates_survive_the_file(self, tmp_path):
        """The passthrough was a list of sixteen names; the engine reads over
        fifty params. `templates` and `variables` were not on it, so a declared
        release-name template silently became generic semantic text: a column
        meant to hold `[SubsPlease] Show - 05 (1080p) [A1B2C3D4].mkv` came out
        as "VP of Marketing"."""
        import misata
        schema = self._load(tmp_path, """
name: releases
tables:
  grabs:
    rows: 40
    columns:
      id: {type: int, unique: true, min: 1, max: 40}
      release_title:
        type: text
        templates:
          - "[{group}] {show} - {ep} ({res}) [{crc}].mkv"
        variables:
          group: [SubsPlease, Erai-raws]
          show: [Some Show]
          ep: ["01", "05"]
          res: [1080p, 720p]
          crc: [A1B2C3D4]
""")
        col = next(c for c in schema.columns["grabs"] if c.name == "release_title")
        assert col.distribution_params.get("templates"), "templates dropped on load"
        assert col.distribution_params.get("variables"), "variables dropped on load"

        titles = misata.generate_from_schema(schema)["grabs"]["release_title"]
        assert all(t.endswith(".mkv") for t in titles), list(titles[:3])
        assert all(t.startswith("[") for t in titles)

    def test_every_param_the_engine_reads_can_be_written_in_yaml(self):
        """Three bugs this week were one enumerated list missing one key, so
        the loader no longer enumerates. This asserts the inversion holds: any
        key that is not structural must reach distribution_params."""
        from misata.yaml_schema import _parse_column, _STRUCTURAL_COLUMN_KEYS

        col = _parse_column("c", {
            "type": "text",
            "templates": ["x"], "variables": {"a": ["b"]},
            "null_when": "other", "exact_incidence": 5, "quantiles": [0.5],
            "zipf_exponent": 1.2, "start_hour": 9,
        })
        for key in ("templates", "variables", "null_when", "exact_incidence",
                    "quantiles", "zipf_exponent", "start_hour"):
            assert key in col.distribution_params, f"{key} did not survive the file"
        assert "type" in _STRUCTURAL_COLUMN_KEYS


class TestAPrimaryKeyIsUniqueOnEveryPath:
    """`primary_key: true` was honoured by the dict path and silently ignored
    by the YAML loader.

    `primary_key` was not in `_STRUCTURAL_COLUMN_KEYS`, so it fell through into
    `distribution_params`, the column kept the default normal distribution, and
    a declared key produced **142 distinct values across 2,000 rows**. Found by
    writing a demo schema for a video and checking it in DuckDB, not by the
    suite, because the suite speaks the dict dialect.

    Nothing downstream catches it: an orphan check asks whether a child's value
    exists in the parent, never whether the parent's key is unique. Integrity
    reported clean the whole time.
    """

    def _load(self, tmp_path, doc):
        import yaml
        import misata
        p = tmp_path / "s.yaml"
        p.write_text(yaml.safe_dump(doc))
        return misata.load_yaml_schema(str(p))

    DOC = {
        "name": "pk",
        "seed": 7,
        "tables": {
            "customers": {
                "rows": 2000,
                "columns": {
                    "customer_id": {"type": "integer", "primary_key": True},
                    "country": {"type": "categorical", "choices": ["US", "UK"]},
                },
            }
        },
    }

    def test_the_declaration_survives_the_yaml_loader(self, tmp_path):
        cfg = self._load(tmp_path, self.DOC)
        col = next(c for c in cfg.columns["customers"] if c.name == "customer_id")
        assert col.unique is True, "a primary key that is not unique is not a key"
        assert col.nullable is False
        assert "primary_key" not in col.distribution_params, (
            "the flag leaked into distribution params instead of being honoured")

    def test_the_generated_key_is_actually_unique(self, tmp_path):
        import misata
        df = misata.generate_from_schema(self._load(tmp_path, self.DOC))["customers"]
        assert df.customer_id.is_unique
        assert df.customer_id.nunique() == 2000

    def test_it_does_not_have_to_fight_the_range(self, tmp_path):
        """The default normal distribution over a narrow range made the engine
        widen it and warn on every single run."""
        import warnings
        import misata
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            misata.generate_from_schema(self._load(tmp_path, self.DOC))
        assert not [w for w in caught if "too small for unique" in str(w.message)]

    def test_an_explicit_distribution_still_wins(self, tmp_path):
        doc = {**self.DOC}
        doc["tables"]["customers"]["columns"]["customer_id"] = {
            "type": "integer", "primary_key": True,
            "distribution": "uniform", "min": 1, "max": 5000,
        }
        cfg = self._load(tmp_path, doc)
        col = next(c for c in cfg.columns["customers"] if c.name == "customer_id")
        assert col.distribution_params["max"] == 5000
        assert col.unique is True

    def test_both_entry_points_agree(self, tmp_path):
        """The same declaration, through either door, must mean the same thing."""
        import misata
        yaml_col = next(c for c in self._load(tmp_path, self.DOC).columns["customers"]
                        if c.name == "customer_id")
        dict_cfg = misata.from_dict_schema({
            "customers": {"__rows__": 2000,
                          "customer_id": {"type": "integer", "primary_key": True}}})
        dict_col = next(c for c in dict_cfg.columns["customers"]
                        if c.name == "customer_id")
        assert yaml_col.unique == dict_col.unique is True
