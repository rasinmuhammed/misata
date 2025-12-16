"""
Unit tests for schema validation.
"""

import pytest
from pydantic import ValidationError

from misata.schema import Column, Table, Relationship, SchemaConfig, ScenarioEvent


class TestColumn:
    """Tests for Column model."""
    
    def test_basic_int_column(self):
        """Test creating a basic integer column."""
        col = Column(
            name="age",
            type="int",
            distribution_params={"distribution": "uniform", "min": 18, "max": 65}
        )
        assert col.name == "age"
        assert col.type == "int"
        assert col.distribution_params["min"] == 18
    
    def test_categorical_requires_choices(self):
        """Categorical columns must have choices."""
        with pytest.raises(ValidationError):
            Column(name="status", type="categorical", distribution_params={})
    
    def test_date_requires_start_end(self):
        """Date columns must have start and end."""
        with pytest.raises(ValidationError):
            Column(name="created_at", type="date", distribution_params={})
    
    def test_valid_date_column(self):
        """Test valid date column with start/end."""
        col = Column(
            name="created_at",
            type="date",
            distribution_params={"start": "2023-01-01", "end": "2024-12-31"}
        )
        assert col.distribution_params["start"] == "2023-01-01"
    
    def test_text_column(self):
        """Test text column with text_type."""
        col = Column(
            name="email",
            type="text",
            distribution_params={"text_type": "email"}
        )
        assert col.distribution_params["text_type"] == "email"


class TestTable:
    """Tests for Table model."""
    
    def test_basic_table(self):
        """Test creating a basic table."""
        table = Table(name="users", row_count=1000)
        assert table.name == "users"
        assert table.row_count == 1000
        assert table.is_reference is False
    
    def test_reference_table_with_inline_data(self):
        """Test reference table with inline data."""
        table = Table(
            name="plans",
            is_reference=True,
            inline_data=[
                {"id": 1, "name": "Free", "price": 0.0},
                {"id": 2, "name": "Premium", "price": 9.99},
            ]
        )
        assert table.is_reference is True
        assert len(table.inline_data) == 2
        assert table.inline_data[0]["price"] == 0.0


class TestRelationship:
    """Tests for Relationship model."""
    
    def test_basic_relationship(self):
        """Test creating a relationship."""
        rel = Relationship(
            parent_table="users",
            child_table="orders",
            parent_key="id",
            child_key="user_id"
        )
        assert rel.parent_table == "users"
        assert rel.child_table == "orders"


class TestSchemaConfig:
    """Tests for complete schema configuration."""
    
    def test_minimal_schema(self):
        """Test minimal valid schema."""
        schema = SchemaConfig(
            name="Test",
            tables=[Table(name="users", row_count=100)],
            columns={
                "users": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 100}),
                    Column(name="email", type="text", distribution_params={"text_type": "email"}),
                ]
            }
        )
        assert schema.name == "Test"
        assert len(schema.tables) == 1
    
    def test_schema_with_relationships(self):
        """Test schema with parent-child relationships."""
        schema = SchemaConfig(
            name="Test",
            tables=[
                Table(name="users", row_count=100),
                Table(name="orders", row_count=500),
            ],
            columns={
                "users": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 100}),
                ],
                "orders": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 500}),
                    Column(name="user_id", type="foreign_key", distribution_params={}),
                ],
            },
            relationships=[
                Relationship(parent_table="users", child_table="orders", parent_key="id", child_key="user_id")
            ]
        )
        assert len(schema.relationships) == 1
    
    def test_missing_table_columns_fails(self):
        """Schema should fail if table has no columns."""
        with pytest.raises(ValidationError):
            SchemaConfig(
                name="Test",
                tables=[Table(name="users", row_count=100)],
                columns={}  # No columns for users!
            )
    
    def test_invalid_relationship_table(self):
        """Schema should fail if relationship references non-existent table."""
        with pytest.raises(ValidationError):
            SchemaConfig(
                name="Test",
                tables=[Table(name="users", row_count=100)],
                columns={
                    "users": [Column(name="id", type="int", distribution_params={"distribution": "uniform"})]
                },
                relationships=[
                    Relationship(parent_table="users", child_table="orders", parent_key="id", child_key="user_id")
                ]
            )
