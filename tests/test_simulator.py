"""
Unit tests for data simulator.
"""

import pandas as pd
import pytest

from misata.schema import Column, NoiseConfig, OutcomeCurve, RealismConfig, Relationship, SchemaConfig, Table
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

    def test_exact_outcome_curve_generation(self):
        """Exact outcome curves should generate bucket sums that match targets."""
        schema = SchemaConfig(
            name="Revenue Story",
            seed=42,
            tables=[
                Table(name="customers", row_count=25),
                Table(name="orders", row_count=150),
            ],
            columns={
                "customers": [
                    Column(
                        name="id",
                        type="int",
                        distribution_params={"distribution": "uniform", "min": 1, "max": 25},
                        unique=True,
                    ),
                    Column(name="name", type="text", distribution_params={"text_type": "name"}),
                ],
                "orders": [
                    Column(
                        name="id",
                        type="int",
                        distribution_params={"distribution": "uniform", "min": 1, "max": 150},
                        unique=True,
                    ),
                    Column(
                        name="customer_id",
                        type="foreign_key",
                        distribution_params={"sampling": "pareto", "alpha": 1.2},
                    ),
                    Column(
                        name="order_date",
                        type="date",
                        distribution_params={"start": "2024-01-01", "end": "2024-03-31"},
                    ),
                    Column(
                        name="amount",
                        type="float",
                        distribution_params={"distribution": "uniform", "min": 10.0, "max": 100.0, "decimals": 2},
                    ),
                ],
            },
            relationships=[
                Relationship(
                    parent_table="customers",
                    child_table="orders",
                    parent_key="id",
                    child_key="customer_id",
                )
            ],
            outcome_curves=[
                OutcomeCurve(
                    table="orders",
                    column="amount",
                    time_column="order_date",
                    time_unit="month",
                    value_mode="absolute",
                    avg_transaction_value=20.0,
                    start_date="2024-01-01",
                    curve_points=[
                        {"month": 1, "target_value": 1000.0},
                        {"month": 2, "target_value": 1500.0},
                        {"month": 3, "target_value": 500.0},
                    ],
                )
            ],
        )

        simulator = DataSimulator(schema)
        data = self.generate_and_collect(simulator)

        orders = data["orders"].copy()
        monthly_amount = (
            pd.to_datetime(orders["order_date"])
            .dt.month.to_frame(name="month")
            .assign(amount=orders["amount"].values)
            .groupby("month")["amount"]
            .sum()
        )

        assert monthly_amount.loc[1] == pytest.approx(1000.0, abs=0.01)
        assert monthly_amount.loc[2] == pytest.approx(1500.0, abs=0.01)
        assert monthly_amount.loc[3] == pytest.approx(500.0, abs=0.01)
        assert set(orders["customer_id"]).issubset(set(data["customers"]["id"]))

    def test_analytics_safe_noise_preserves_exact_targets(self):
        """Analytics-safe noise should avoid breaking constrained metrics and keys."""
        schema = SchemaConfig(
            name="Revenue Story With Safe Noise",
            seed=42,
            tables=[
                Table(name="customers", row_count=20),
                Table(name="orders", row_count=100),
            ],
            columns={
                "customers": [
                    Column(
                        name="id",
                        type="int",
                        distribution_params={"distribution": "uniform", "min": 1, "max": 20},
                        unique=True,
                    ),
                    Column(name="name", type="text", distribution_params={"text_type": "name"}),
                ],
                "orders": [
                    Column(
                        name="id",
                        type="int",
                        distribution_params={"distribution": "uniform", "min": 1, "max": 100},
                        unique=True,
                    ),
                    Column(name="customer_id", type="foreign_key", distribution_params={}),
                    Column(
                        name="order_date",
                        type="date",
                        distribution_params={"start": "2024-01-01", "end": "2024-02-29"},
                    ),
                    Column(
                        name="amount",
                        type="float",
                        distribution_params={"distribution": "uniform", "min": 10.0, "max": 100.0, "decimals": 2},
                    ),
                    Column(name="description", type="text", distribution_params={"text_type": "sentence"}),
                ],
            },
            relationships=[
                Relationship(parent_table="customers", child_table="orders", parent_key="id", child_key="customer_id")
            ],
            outcome_curves=[
                OutcomeCurve(
                    table="orders",
                    column="amount",
                    time_column="order_date",
                    time_unit="month",
                    value_mode="absolute",
                    avg_transaction_value=20.0,
                    start_date="2024-01-01",
                    curve_points=[
                        {"month": 1, "target_value": 1000.0},
                        {"month": 2, "target_value": 500.0},
                    ],
                )
            ],
            noise_config=NoiseConfig(
                mode="analytics_safe",
                null_rate=0.5,
                typo_rate=0.5,
            ),
        )

        simulator = DataSimulator(schema)
        data = self.generate_and_collect(simulator)
        orders = data["orders"]

        monthly_amount = (
            pd.to_datetime(orders["order_date"])
            .dt.month.to_frame(name="month")
            .assign(amount=orders["amount"].values)
            .groupby("month")["amount"]
            .sum()
        )

        assert monthly_amount.loc[1] == pytest.approx(1000.0, abs=0.01)
        assert monthly_amount.loc[2] == pytest.approx(500.0, abs=0.01)
        assert orders["id"].isna().sum() == 0
        assert orders["customer_id"].isna().sum() == 0
        assert orders["amount"].isna().sum() == 0
        assert orders["description"].isna().sum() > 0

    def test_row_planning_heuristic_adjusts_child_counts(self):
        """Heuristic row planning should break flat parent/child counts deterministically."""
        schema = SchemaConfig(
            name="Row Planning",
            seed=42,
            tables=[
                Table(name="customers", row_count=100),
                Table(name="orders", row_count=100),
                Table(name="order_items", row_count=100),
            ],
            columns={
                "customers": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 100}, unique=True),
                ],
                "orders": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 1000}, unique=True),
                    Column(name="customer_id", type="foreign_key", distribution_params={}),
                ],
                "order_items": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 5000}, unique=True),
                    Column(name="order_id", type="foreign_key", distribution_params={}),
                ],
            },
            relationships=[
                Relationship(parent_table="customers", child_table="orders", parent_key="id", child_key="customer_id"),
                Relationship(parent_table="orders", child_table="order_items", parent_key="id", child_key="order_id"),
            ],
            realism=RealismConfig(row_planning="heuristic"),
        )

        simulator = DataSimulator(schema)
        data = self.generate_and_collect(simulator)

        assert len(data["customers"]) == 100
        assert len(data["orders"]) > len(data["customers"])
        assert len(data["order_items"]) > len(data["orders"])

    def test_realistic_text_and_coherence_generate_consistent_identity_fields(self):
        """Realistic text + coherence should derive email and username from the same name."""
        schema = SchemaConfig(
            name="Identity Coherence",
            seed=42,
            tables=[Table(name="users", row_count=50)],
            columns={
                "users": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 50}, unique=True),
                    Column(name="first_name", type="text", distribution_params={}),
                    Column(name="last_name", type="text", distribution_params={}),
                    Column(name="email", type="text", distribution_params={}),
                    Column(name="username", type="text", distribution_params={}),
                ]
            },
            realism=RealismConfig(text_mode="realistic_catalog", coherence="standard"),
        )

        simulator = DataSimulator(schema)
        users = self.generate_and_collect(simulator)["users"]

        first = users.loc[0, "first_name"].lower()
        last = users.loc[0, "last_name"].lower()
        assert first[:3] in users.loc[0, "email"].lower()
        assert users.loc[0, "username"].lower().startswith(first[:3])
        assert last[:3] in users.loc[0, "username"].lower()

    def test_configured_workflow_fixes_terminal_timestamps(self):
        """Configured workflow presets should keep terminal timestamps coherent."""
        schema = SchemaConfig(
            name="Workflow Orders",
            seed=42,
            tables=[Table(name="orders", row_count=40, workflow_preset="order")],
            columns={
                "orders": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 40}, unique=True),
                    Column(name="status", type="categorical", distribution_params={"choices": ["pending", "delivered", "cancelled"]}),
                    Column(name="created_at", type="datetime", distribution_params={"start": "2024-01-01", "end": "2024-01-10"}),
                    Column(name="delivered_at", type="datetime", distribution_params={"start": "2024-01-01", "end": "2024-02-01"}),
                    Column(name="cancelled_at", type="datetime", distribution_params={"start": "2024-01-01", "end": "2024-02-01"}),
                ]
            },
            realism=RealismConfig(workflow_mode="preset"),
        )

        simulator = DataSimulator(schema)
        orders = self.generate_and_collect(simulator)["orders"]

        delivered_mask = orders["status"].str.lower() == "delivered"
        cancelled_mask = orders["status"].str.lower() == "cancelled"
        pending_mask = orders["status"].str.lower() == "pending"

        assert orders.loc[pending_mask, "delivered_at"].isna().all()
        assert orders.loc[pending_mask, "cancelled_at"].isna().all()
        assert orders.loc[delivered_mask, "delivered_at"].notna().all()
        assert orders.loc[cancelled_mask, "cancelled_at"].notna().all()

    def test_generate_with_reports_returns_requested_advisory_reports(self):
        """The report API should return validation plus selected advisory reports."""
        schema = SchemaConfig(
            name="Reports",
            seed=42,
            tables=[Table(name="users", row_count=25)],
            columns={
                "users": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 25}, unique=True),
                    Column(name="age", type="int", distribution_params={"distribution": "uniform", "min": 18, "max": 65}),
                    Column(name="country", type="text", distribution_params={}),
                ]
            },
            realism=RealismConfig(text_mode="realistic_catalog", reports=["privacy", "fidelity", "data_card"]),
        )

        simulator = DataSimulator(schema)
        result = simulator.generate_with_reports()

        assert "users" in result.tables
        assert result.validation_report is not None
        assert set(result.reports.keys()) == {"privacy", "fidelity", "data_card"}
        assert result.tables_are_samples is True
        assert result.table_row_counts["users"] == 25
        assert len(result.tables["users"]) <= 25

    def test_generate_with_reports_can_still_return_full_tables(self):
        """Full-table collection should remain available as an explicit opt-in."""
        schema = SchemaConfig(
            name="Reports Full Tables",
            seed=42,
            tables=[Table(name="users", row_count=30)],
            columns={
                "users": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 30}, unique=True),
                    Column(name="age", type="int", distribution_params={"distribution": "uniform", "min": 18, "max": 65}),
                ]
            },
            realism=RealismConfig(reports=["data_card"]),
        )

        simulator = DataSimulator(schema)
        result = simulator.generate_with_reports(include_tables=True)

        assert result.tables_are_samples is False
        assert len(result.tables["users"]) == 30
        assert result.table_row_counts["users"] == 30

    def test_time_density_curve_biases_datetime_columns(self):
        """Relative curves on datetime columns should reshape date density instead of multiplying dates."""
        schema = SchemaConfig(
            name="Ticket Seasonality",
            seed=42,
            tables=[Table(name="tickets", row_count=1000)],
            columns={
                "tickets": [
                    Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 1000}, unique=True),
                    Column(name="created_at", type="date", distribution_params={"start": "2024-01-01", "end": "2024-02-29"}),
                    Column(name="status", type="categorical", distribution_params={"choices": ["open", "closed"]}),
                ]
            },
            outcome_curves=[
                OutcomeCurve(
                    table="tickets",
                    column="created_at",
                    time_column="created_at",
                    time_unit="month",
                    value_mode="relative",
                    pattern_type="seasonal",
                    curve_points=[
                        {"month": 1, "relative_value": 0.9},
                        {"month": 2, "relative_value": 0.1},
                    ],
                )
            ],
        )

        simulator = DataSimulator(schema)
        tickets = self.generate_and_collect(simulator)["tickets"]
        months = pd.to_datetime(tickets["created_at"]).dt.month.value_counts()

        assert months[1] > months[2]


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
