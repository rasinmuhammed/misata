"""
Unit tests for data validation.
"""

import pandas as pd
import pytest

from misata.validation import DataValidator, ValidationReport, Severity, validate_data


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
