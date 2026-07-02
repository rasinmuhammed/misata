"""Regression tests for from_dict_schema input formats and Oracle curve-awareness.

Covers the three 0.8.1.15 fixes:
  1. YAML-style envelope ({"name", "seed", "tables", "relationships"}) unwrap —
     previously parsed "tables" as a table named tables and generated garbage.
  2. references: "parent.key" string on foreign_key columns — previously never
     created a Relationship, so validation rejected the README's own example.
  3. Oracle row-count check is curve-aware — previously oracle["passed"] was
     False on perfectly curve-conformant datasets.
"""
import pandas as pd
import pytest

import misata


ENVELOPE_SCHEMA = {
    "name": "shop",
    "seed": 7,
    "tables": {
        "customers": {"rows": 300, "columns": {
            "customer_id": {"type": "int", "unique": True},
            "total_spent": {"type": "float", "rollup": {
                "from_table": "orders", "fk": "customer_id",
                "agg": "sum", "column": "amount"}},
        }},
        "orders": {"rows": 2000, "columns": {
            "order_id": {"type": "int", "unique": True},
            "customer_id": {"type": "foreign_key",
                            "references": "customers.customer_id"},
            "amount": {"type": "float", "min": 1, "max": 500},
        }},
    },
}


class TestEnvelopeFormat:
    def test_envelope_unwraps_to_real_tables(self):
        schema = misata.from_dict_schema(ENVELOPE_SCHEMA)
        assert sorted(t.name for t in schema.tables) == ["customers", "orders"]
        assert schema.name == "shop"
        assert schema.seed == 7

    def test_references_string_builds_relationship(self):
        schema = misata.from_dict_schema(ENVELOPE_SCHEMA)
        rels = [(r.parent_table, r.child_table, r.parent_key, r.child_key)
                for r in schema.relationships]
        assert ("customers", "orders", "customer_id", "customer_id") in rels

    def test_envelope_generates_with_fk_integrity_and_rollup(self):
        schema = misata.from_dict_schema(ENVELOPE_SCHEMA)
        tables = misata.generate_from_schema(schema)
        assert set(tables) == {"customers", "orders"}
        orders, cust = tables["orders"], tables["customers"]
        assert (~orders["customer_id"].isin(cust["customer_id"])).sum() == 0
        real = orders.groupby("customer_id")["amount"].sum()
        merged = cust.set_index("customer_id").join(real.rename("real"))
        merged["real"] = merged["real"].fillna(0)
        assert ((merged["total_spent"] - merged["real"]).abs() > 0.01).sum() == 0

    def test_envelope_relationships_arrow_string(self):
        schema = misata.from_dict_schema({
            "tables": {
                "users": {"rows": 50, "columns": {
                    "user_id": {"type": "int", "unique": True}}},
                "orders": {"rows": 200, "columns": {
                    "order_id": {"type": "int", "unique": True},
                    "user_id": {"type": "foreign_key"},
                    "amount": {"type": "float", "min": 5, "max": 50}}},
            },
            "relationships": ["users.user_id → orders.user_id"],
        })
        assert len(schema.relationships) == 1
        tables = misata.generate_from_schema(schema)
        orphans = (~tables["orders"]["user_id"]
                   .isin(tables["users"]["user_id"])).sum()
        assert orphans == 0

    def test_flat_format_unchanged(self):
        schema = misata.from_dict_schema({
            "users": {"id": {"type": "integer", "primary_key": True},
                      "email": {"type": "email"}},
            "posts": {"id": {"type": "integer", "primary_key": True},
                      "user_id": {"type": "integer",
                                  "foreign_key": {"table": "users", "column": "id"}}},
        }, row_count=100)
        tables = misata.generate_from_schema(schema)
        assert set(tables) == {"users", "posts"}

    def test_table_literally_named_tables_of_columns_stays_flat(self):
        # A real table named "tables" whose values are column defs must NOT
        # be mistaken for the envelope.
        schema = misata.from_dict_schema({
            "tables": {"id": {"type": "integer", "primary_key": True},
                       "label": {"type": "string"}},
        }, row_count=20)
        assert [t.name for t in schema.tables] == ["tables"]


class TestOracleCurveAwareRowCount:
    def test_oracle_passes_on_conformant_curve_dataset(self):
        schema = misata.from_dict_schema({
            "__outcome_curves__": [{
                "table": "orders", "column": "amount",
                "time_column": "order_date", "time_unit": "month",
                "value_mode": "absolute", "start_date": "2024-01-01",
                "avg_transaction_value": 120.0,
                "curve_points": [{"month": 1, "target_value": 50000.0},
                                 {"month": 12, "target_value": 200000.0}],
            }],
            "orders": {"__rows__": 5000,
                       "order_id": {"type": "integer", "primary_key": True},
                       "amount": {"type": "float", "min": 5, "max": 500},
                       "order_date": {"type": "date"}},
        }, seed=42)
        tables = misata.generate_from_schema(schema)
        oracle = misata.build_oracle_report(tables, schema, seed=42)
        assert oracle["passed"] is True
        check = oracle["guarantees"]["row_count_fulfillment"]["tables"]["orders"]
        assert check["row_count_derived_from_outcome_curve"] is True
        assert check["passed"] is True

    def test_non_curve_table_row_count_still_strict(self):
        schema = misata.from_dict_schema({
            "users": {"__rows__": 100,
                      "id": {"type": "integer", "primary_key": True}},
        }, seed=1)
        tables = misata.generate_from_schema(schema)
        # Drop rows to force a row-count failure.
        tables["users"] = tables["users"].head(50)
        oracle = misata.build_oracle_report(tables, schema, seed=1)
        check = oracle["guarantees"]["row_count_fulfillment"]["tables"]["users"]
        assert check["passed"] is False
        assert "row_count_derived_from_outcome_curve" not in check


class TestAnalyzeGenerationBundle:
    def test_default_runs_all_reports_with_attribute_access(self):
        schema = misata.from_dict_schema({
            "users": {"__rows__": 60,
                      "id": {"type": "integer", "primary_key": True},
                      "age": {"type": "integer", "min": 18, "max": 90}},
        }, seed=2)
        tables = misata.generate_from_schema(schema)
        bundle = misata.analyze_generation(tables, schema)
        assert set(bundle) == {"privacy", "fidelity", "data_card"}
        assert bundle.fidelity.overall_score >= 0
        assert bundle.privacy is bundle.privacy_report
        assert bundle.fidelity is bundle.fidelity_report
        with pytest.raises(AttributeError):
            _ = bundle.nonexistent_report

    def test_explicit_empty_list_runs_nothing(self):
        schema = misata.from_dict_schema({
            "users": {"__rows__": 10,
                      "id": {"type": "integer", "primary_key": True}},
        }, seed=2)
        tables = misata.generate_from_schema(schema)
        assert dict(misata.analyze_generation(tables, schema, reports=[])) == {}
