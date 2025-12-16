"""
Unit tests for data simulator.
"""

import numpy as np
import pandas as pd
import pytest

from misata.schema import Column, Table, Relationship, SchemaConfig
from misata.simulator import DataSimulator


class TestDataSimulator:
    """Tests for DataSimulator class."""
    
    @pytest.fixture
    def simple_schema(self):
        """Simple schema with one table."""
        return SchemaConfig(
            name="Test",
            seed=42,
            tables=[Table(name="users", row_count=100)],
            columns={
                "users": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 100}),
                    Column(name="age", type="int", distribution_params={"distribution": "uniform", "min": 18, "max": 65}),
                    Column(name="email", type="text", distribution_params={"text_type": "email"}),
                    Column(name="active", type="boolean", distribution_params={"probability": 0.7}),
                ]
            }
        )
    
    @pytest.fixture
    def schema_with_fk(self):
        """Schema with foreign key relationship."""
        return SchemaConfig(
            name="Test",
            seed=42,
            tables=[
                Table(name="users", row_count=50),
                Table(name="orders", row_count=200),
            ],
            columns={
                "users": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 50}, unique=True),
                    Column(name="name", type="text", distribution_params={"text_type": "name"}),
                ],
                "orders": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 200}),
                    Column(name="user_id", type="foreign_key", distribution_params={}),
                    Column(name="amount", type="float", distribution_params={"distribution": "uniform", "min": 10, "max": 500}),
                ],
            },
            relationships=[
                Relationship(parent_table="users", child_table="orders", parent_key="id", child_key="user_id")
            ]
        )
    
    @pytest.fixture
    def reference_table_schema(self):
        """Schema with reference table."""
        return SchemaConfig(
            name="Test",
            seed=42,
            tables=[
                Table(
                    name="plans",
                    is_reference=True,
                    inline_data=[
                        {"id": 1, "name": "Free", "price": 0.0},
                        {"id": 2, "name": "Basic", "price": 9.99},
                        {"id": 3, "name": "Premium", "price": 29.99},
                    ]
                ),
                Table(name="subscriptions", row_count=100),
            ],
            columns={
                "plans": [
                    Column(name="id", type="int", distribution_params={}),
                    Column(name="name", type="text", distribution_params={}),
                    Column(name="price", type="float", distribution_params={}),
                ],
                "subscriptions": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 100}),
                    Column(name="plan_id", type="foreign_key", distribution_params={}),
                ],
            },
            relationships=[
                Relationship(parent_table="plans", child_table="subscriptions", parent_key="id", child_key="plan_id")
            ]
        )
    

    def generate_and_collect(self, simulator):
        """Helper to consume generator and collect all data."""
        data = {}
        for table_name, batch_df in simulator.generate_all():
            if table_name in data:
                data[table_name] = pd.concat([data[table_name], batch_df], ignore_index=True)
            else:
                data[table_name] = batch_df
        return data

    def test_simple_generation(self, simple_schema):
        """Test basic data generation."""
        simulator = DataSimulator(simple_schema)
        data = self.generate_and_collect(simulator)
        
        assert "users" in data
        assert len(data["users"]) == 100
        assert set(data["users"].columns) == {"id", "age", "email", "active"}
    
    def test_age_bounds(self, simple_schema):
        """Test that age values respect bounds."""
        simulator = DataSimulator(simple_schema)
        data = self.generate_and_collect(simulator)
        
        ages = data["users"]["age"]
        assert ages.min() >= 18
        assert ages.max() <= 65
    
    def test_email_format(self, simple_schema):
        """Test that emails contain @."""
        simulator = DataSimulator(simple_schema)
        data = self.generate_and_collect(simulator)
        
        emails = data["users"]["email"]
        assert all("@" in str(email) for email in emails)
    
    def test_boolean_distribution(self, simple_schema):
        """Test boolean probability is approximately correct."""
        simulator = DataSimulator(simple_schema)
        data = self.generate_and_collect(simulator)
        
        active_rate = data["users"]["active"].mean()
        # With probability 0.7, expect between 0.5 and 0.9
        assert 0.5 < active_rate < 0.9
    
    def test_foreign_key_integrity(self, schema_with_fk):
        """Test that all foreign keys reference valid parent IDs."""
        simulator = DataSimulator(schema_with_fk)
        data = self.generate_and_collect(simulator)
        
        user_ids = set(data["users"]["id"])
        order_user_ids = set(data["orders"]["user_id"])
        
        # All order user_ids should exist in users
        assert order_user_ids.issubset(user_ids)
    
    def test_reference_table_uses_inline_data(self, reference_table_schema):
        """Test that reference tables use inline data."""
        simulator = DataSimulator(reference_table_schema)
        data = self.generate_and_collect(simulator)
        
        # Plans should have exactly 3 rows from inline_data
        assert len(data["plans"]) == 3
        assert list(data["plans"]["name"]) == ["Free", "Basic", "Premium"]
        assert list(data["plans"]["price"]) == [0.0, 9.99, 29.99]
    
    def test_fk_to_reference_table(self, reference_table_schema):
        """Test FK references to reference table."""
        simulator = DataSimulator(reference_table_schema)
        data = self.generate_and_collect(simulator)
        
        plan_ids = set(data["plans"]["id"])
        sub_plan_ids = set(data["subscriptions"]["plan_id"])
        
        assert sub_plan_ids.issubset(plan_ids)
    
    def test_reproducibility(self, simple_schema):
        """Test that same seed produces same NUMERIC data."""
        sim1 = DataSimulator(simple_schema)
        sim2 = DataSimulator(simple_schema)
        
        data1 = self.generate_and_collect(sim1)
        data2 = self.generate_and_collect(sim2)
        
        # Numeric columns should be identical (mimesis text isn't fully seedable)
        pd.testing.assert_series_equal(data1["users"]["id"], data2["users"]["id"])
        pd.testing.assert_series_equal(data1["users"]["age"], data2["users"]["age"])
        pd.testing.assert_series_equal(data1["users"]["active"], data2["users"]["active"])

    
    def test_topological_sort(self, schema_with_fk):
        """Test tables are generated in correct order."""
        simulator = DataSimulator(schema_with_fk)
        order = simulator.topological_sort()
        
        # Users must come before orders
        assert order.index("users") < order.index("orders")


class TestDistributions:
    """Tests for distribution accuracy."""
    
    def generate_and_collect(self, simulator):
        """Helper to consume generator and collect all data."""
        data = {}
        for table_name, batch_df in simulator.generate_all():
            if table_name in data:
                data[table_name] = pd.concat([data[table_name], batch_df], ignore_index=True)
            else:
                data[table_name] = batch_df
        return data

    def test_normal_distribution_mean(self):
        """Test normal distribution generates correct mean."""
        schema = SchemaConfig(
            name="Test",
            seed=42,
            tables=[Table(name="data", row_count=10000)],
            columns={
                "data": [
                    Column(name="value", type="float", distribution_params={
                        "distribution": "normal", "mean": 100, "std": 10
                    })
                ]
            }
        )
        simulator = DataSimulator(schema)
        data = self.generate_and_collect(simulator)
        
        mean = data["data"]["value"].mean()
        # Mean should be close to 100
        assert 95 < mean < 105
    
    def test_categorical_probabilities(self):
        """Test categorical distribution respects probabilities."""
        schema = SchemaConfig(
            name="Test",
            seed=42,
            tables=[Table(name="data", row_count=10000)],
            columns={
                "data": [
                    Column(name="status", type="categorical", distribution_params={
                        "choices": ["A", "B", "C"],
                        "probabilities": [0.5, 0.3, 0.2]
                    })
                ]
            }
        )
        simulator = DataSimulator(schema)
        data = self.generate_and_collect(simulator)
        
        counts = data["data"]["status"].value_counts(normalize=True)
        
        # A should be ~50%, B ~30%, C ~20%
        assert 0.45 < counts.get("A", 0) < 0.55
        assert 0.25 < counts.get("B", 0) < 0.35
        assert 0.15 < counts.get("C", 0) < 0.25

