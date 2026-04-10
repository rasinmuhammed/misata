"""
Unit tests for data validation.
"""

import pandas as pd
import pytest

from misata.schema import Column, Relationship, SchemaConfig, Table
from misata.validation import DataValidator, SchemaValidationError, ValidationReport, validate_data, validate_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_schema(**kwargs) -> SchemaConfig:
    """Build the simplest valid SchemaConfig with one table and one column."""
    base = dict(
        name="test",
        tables=[Table(name="users", row_count=10)],
        columns={
            "users": [
                Column(name="user_id", type="int", unique=True, distribution_params={"min": 1, "max": 10}),
            ]
        },
        relationships=[],
        events=[],
        outcome_curves=[],
    )
    base.update(kwargs)
    return SchemaConfig(**base)


# ---------------------------------------------------------------------------
# validate_schema — pre-generation checks
# ---------------------------------------------------------------------------

class TestValidateSchema:
    def test_valid_schema_passes(self):
        schema = _minimal_schema()
        validate_schema(schema)  # must not raise

    def test_duplicate_table_name_raises(self):
        schema = SchemaConfig(
            name="test",
            tables=[Table(name="x", row_count=5), Table(name="x", row_count=5)],
            columns={
                "x": [Column(name="id", type="int", unique=True, distribution_params={"min": 1, "max": 5})],
            },
        )
        with pytest.raises(SchemaValidationError, match="Duplicate table name"):
            validate_schema(schema)

    def test_outcome_curve_unknown_time_column_raises(self):
        from misata.schema import OutcomeCurve
        schema = _minimal_schema(
            outcome_curves=[OutcomeCurve(table="users", column="user_id", time_column="no_such_date")]
        )
        with pytest.raises(SchemaValidationError, match="unknown time_column"):
            validate_schema(schema)

    def test_foreign_key_without_relationship_raises(self):
        schema = SchemaConfig(
            name="test",
            tables=[
                Table(name="users", row_count=10),
                Table(name="orders", row_count=20),
            ],
            columns={
                "users": [Column(name="user_id", type="int", unique=True, distribution_params={"min": 1, "max": 10})],
                "orders": [
                    Column(name="order_id", type="int", unique=True, distribution_params={"min": 1, "max": 20}),
                    Column(name="user_id", type="foreign_key", distribution_params={}),
                ],
            },
            # No relationship defined for the FK column
            relationships=[],
        )
        with pytest.raises(SchemaValidationError, match="foreign_key.*no matching Relationship"):
            validate_schema(schema)

    def test_categorical_probs_not_summing_to_one_raises(self):
        schema = SchemaConfig(
            name="test",
            tables=[Table(name="t", row_count=10)],
            columns={
                "t": [
                    Column(name="status", type="categorical", distribution_params={
                        "choices": ["a", "b", "c"],
                        "probabilities": [0.5, 0.5, 0.5],  # sums to 1.5
                    }),
                ]
            },
        )
        with pytest.raises(SchemaValidationError, match="probabilities sum to"):
            validate_schema(schema)

    def test_mismatched_choices_and_probs_raises(self):
        schema = SchemaConfig(
            name="test",
            tables=[Table(name="t", row_count=10)],
            columns={
                "t": [
                    Column(name="status", type="categorical", distribution_params={
                        "choices": ["a", "b"],
                        "probabilities": [0.6, 0.3, 0.1],  # 3 probs, 2 choices
                    }),
                ]
            },
        )
        with pytest.raises(SchemaValidationError, match="lengths must match"):
            validate_schema(schema)

    def test_outcome_curve_unknown_table_raises(self):
        from misata.schema import OutcomeCurve
        schema = _minimal_schema(
            outcome_curves=[OutcomeCurve(table="nonexistent", column="amount", time_column="date")]
        )
        with pytest.raises(SchemaValidationError, match="unknown table 'nonexistent'"):
            validate_schema(schema)

    def test_outcome_curve_unknown_column_raises(self):
        from misata.schema import OutcomeCurve
        schema = _minimal_schema(
            outcome_curves=[OutcomeCurve(table="users", column="no_such_col", time_column="user_id")]
        )
        with pytest.raises(SchemaValidationError, match="unknown column 'users.no_such_col'"):
            validate_schema(schema)

    def test_all_issues_reported_at_once(self):
        """SchemaValidationError should list ALL problems, not just the first one."""
        from misata.schema import OutcomeCurve
        # Two independent errors: bad probabilities + outcome curve on unknown table
        schema = SchemaConfig(
            name="test",
            tables=[Table(name="t", row_count=10)],
            columns={
                "t": [
                    Column(name="status", type="categorical", distribution_params={
                        "choices": ["a", "b"],
                        "probabilities": [0.9, 0.9],  # sums to 1.8
                    }),
                ]
            },
            outcome_curves=[OutcomeCurve(table="no_table", column="x", time_column="y")],
        )
        exc = pytest.raises(SchemaValidationError, validate_schema, schema)
        assert len(exc.value.issues) >= 2  # bad probs AND unknown curve table

    def test_simulator_raises_schema_validation_error_on_bad_config(self):
        """DataSimulator.__init__ must surface SchemaValidationError, not a cryptic crash."""
        from misata.simulator import DataSimulator
        # FK column with no matching Relationship is a valid SchemaConfig (Pydantic accepts it)
        # but validate_schema should catch it
        schema = SchemaConfig(
            name="test",
            tables=[
                Table(name="users", row_count=10),
                Table(name="orders", row_count=20),
            ],
            columns={
                "users": [Column(name="user_id", type="int", unique=True, distribution_params={"min": 1, "max": 10})],
                "orders": [
                    Column(name="order_id", type="int", unique=True, distribution_params={"min": 1, "max": 20}),
                    Column(name="user_id", type="foreign_key", distribution_params={}),
                ],
            },
            relationships=[],  # FK column exists but no relationship
        )
        with pytest.raises(SchemaValidationError):
            DataSimulator(schema)


class TestValidationReport:
    """Tests for validation report."""
    
    def test_empty_report_is_clean(self):
        """Empty report should be clean."""
        report = ValidationReport()
        assert report.is_clean
        assert not report.has_errors
        assert not report.has_warnings


class TestDataValidator:
    """Tests for data validator."""
    
    def test_validates_positive_prices(self):
        """Should detect negative prices."""
        tables = {
            "products": pd.DataFrame({
                "id": [1, 2, 3],
                "price": [10.0, -5.0, 20.0],  # -5 is invalid!
            })
        }
        
        report = validate_data(tables)
        
        # Should have an error about negative price
        assert report.has_errors
        price_issues = [i for i in report.issues if i.column == "price"]
        assert len(price_issues) > 0
    
    def test_validates_positive_ages(self):
        """Should detect invalid ages."""
        tables = {
            "users": pd.DataFrame({
                "id": [1, 2, 3],
                "age": [25, -5, 300],  # -5 and 300 are invalid!
            })
        }
        
        report = validate_data(tables)
        
        # Should have warnings about age
        assert report.has_warnings or report.has_errors
    
    def test_validates_email_format(self):
        """Should detect invalid emails."""
        tables = {
            "users": pd.DataFrame({
                "id": [1, 2, 3],
                "email": ["valid@example.com", "invalid-no-at", "another@test.org"],
            })
        }
        
        report = validate_data(tables)
        
        # Should have error about invalid email
        assert report.has_errors
        email_issues = [i for i in report.issues if i.column == "email"]
        assert len(email_issues) > 0
    
    def test_clean_data_passes(self):
        """Valid data should pass all checks."""
        tables = {
            "products": pd.DataFrame({
                "id": [1, 2, 3],
                "name": ["Apple", "Orange", "Banana"],
                "price": [1.99, 2.49, 0.99],
            }),
            "users": pd.DataFrame({
                "id": [1, 2],
                "email": ["user1@test.com", "user2@test.com"],
                "age": [25, 35],
            })
        }
        
        report = validate_data(tables)
        
        # Might have info messages but no errors
        assert not report.has_errors
    
    def test_report_summary(self):
        """Report should generate readable summary."""
        tables = {
            "data": pd.DataFrame({"id": [1, 2, 3]})
        }
        
        report = validate_data(tables)
        summary = report.summary()
        
        assert "DATA VALIDATION REPORT" in summary
        assert "Tables checked:" in summary


class TestReferentialIntegrity:
    """Tests for foreign key validation."""
    
    def test_detects_orphan_fks(self):
        """Should detect FK values not in parent."""
        from misata.schema import SchemaConfig, Table, Column, Relationship
        
        # Create schema with relationship
        schema = SchemaConfig(
            name="Test",
            tables=[
                Table(name="users", row_count=3),
                Table(name="orders", row_count=3),
            ],
            columns={
                "users": [Column(name="id", type="int", distribution_params={"distribution": "uniform"})],
                "orders": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform"}),
                    Column(name="user_id", type="foreign_key", distribution_params={}),
                ],
            },
            relationships=[
                Relationship(parent_table="users", child_table="orders", parent_key="id", child_key="user_id")
            ]
        )
        
        # Create data with orphan FK
        tables = {
            "users": pd.DataFrame({"id": [1, 2, 3]}),
            "orders": pd.DataFrame({
                "id": [1, 2, 3],
                "user_id": [1, 2, 999],  # 999 doesn't exist in users!
            })
        }
        
        validator = DataValidator(tables, schema)
        report = validator.validate_all()
        
        # Should detect orphan
        assert report.has_errors
        orphan_issues = [i for i in report.issues if "orphan" in i.message.lower()]
        assert len(orphan_issues) > 0


class TestOutcomeCurveValidation:
    """Tests for exact outcome curve validation."""

    def test_detects_outcome_curve_mismatch(self):
        """Should detect aggregates that do not match exact targets."""
        from misata.schema import Column, OutcomeCurve, SchemaConfig, Table

        schema = SchemaConfig(
            name="Curve Validation",
            tables=[Table(name="orders", row_count=4)],
            columns={
                "orders": [
                    Column(name="order_date", type="date", distribution_params={"start": "2024-01-01", "end": "2024-02-29"}),
                    Column(name="amount", type="float", distribution_params={"distribution": "uniform", "min": 1.0, "max": 100.0}),
                ]
            },
            outcome_curves=[
                OutcomeCurve(
                    table="orders",
                    column="amount",
                    time_column="order_date",
                    time_unit="month",
                    value_mode="absolute",
                    start_date="2024-01-01",
                    curve_points=[
                        {"month": 1, "target_value": 100.0},
                        {"month": 2, "target_value": 200.0},
                    ],
                )
            ],
        )

        tables = {
            "orders": pd.DataFrame(
                {
                    "order_date": pd.to_datetime(
                        ["2024-01-05", "2024-01-20", "2024-02-03", "2024-02-18"]
                    ),
                    "amount": [40.0, 50.0, 100.0, 90.0],
                }
            )
        }

        report = validate_data(tables, schema)

        assert report.has_errors
        mismatch_issues = [issue for issue in report.issues if "Outcome curve aggregate mismatch" in issue.message]
        assert len(mismatch_issues) == 1
