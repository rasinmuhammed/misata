
"""
Tests for Business Rule Constraints.
"""

import pandas as pd
import pytest

from misata.schema import Column, Constraint, SchemaConfig, Table
from misata.simulator import DataSimulator


class TestConstraints:
    """Tests for business rule constraint enforcement."""
    
    def generate_and_collect(self, simulator):
        """Helper to consume generator and collect all data."""
        data = {}
        for table_name, batch_df in simulator.generate_all():
            if table_name in data:
                data[table_name] = pd.concat([data[table_name], batch_df], ignore_index=True)
            else:
                data[table_name] = batch_df
        return data

    @pytest.fixture
    def max_hours_schema(self):
        """Schema with max hours per employee per day constraint."""
        return SchemaConfig(
            name="TimesheetConstraintTest",
            seed=42,
            tables=[
                Table(
                    name="timesheets", 
                    row_count=100,
                    constraints=[
                        Constraint(
                            name="max_daily_hours",
                            type="max_per_group",
                            group_by=["employee_id", "date"],
                            column="hours",
                            value=8.0,
                            action="cap"
                        )
                    ]
                ),
            ],
            columns={
                "timesheets": [
                    Column(name="id", type="int", distribution_params={"min": 1, "max": 1000}),
                    Column(name="employee_id", type="int", distribution_params={"min": 1, "max": 10}),
                    Column(name="date", type="date", distribution_params={"start": "2024-01-01", "end": "2024-01-10"}),
                    Column(name="hours", type="float", distribution_params={"min": 1.0, "max": 12.0}),  # Intentionally can exceed 8
                ]
            },
            relationships=[]
        )

    @pytest.fixture
    def sum_limit_schema(self):
        """Schema with sum limit constraint (total hours per day)."""
        return SchemaConfig(
            name="SumLimitTest",
            seed=42,
            tables=[
                Table(
                    name="timesheets", 
                    row_count=50,
                    constraints=[
                        Constraint(
                            name="max_total_daily_hours",
                            type="sum_limit",
                            group_by=["employee_id", "date"],
                            column="hours",
                            value=8.0,
                            action="cap"
                        )
                    ]
                ),
            ],
            columns={
                "timesheets": [
                    Column(name="id", type="int", distribution_params={"min": 1, "max": 1000}),
                    Column(name="employee_id", type="int", distribution_params={"min": 1, "max": 5}),
                    Column(name="date", type="date", distribution_params={"start": "2024-01-01", "end": "2024-01-05"}),
                    Column(name="hours", type="float", distribution_params={"min": 1.0, "max": 6.0}),
                ]
            },
            relationships=[]
        )

    def test_max_per_group_constraint(self, max_hours_schema):
        """
        Verify that hours are capped at 8 per employee per day.
        """
        simulator = DataSimulator(max_hours_schema)
        data = self.generate_and_collect(simulator)
        
        timesheets = data["timesheets"]
        
        # Check max value per group
        max_hours = timesheets.groupby(["employee_id", "date"])["hours"].max()
        
        print(f"Max hours per group:\n{max_hours.head(10)}")
        
        # All should be <= 8
        assert max_hours.max() <= 8.0

    def test_sum_limit_constraint(self, sum_limit_schema):
        """
        Verify that total hours per employee per day <= 8.
        """
        simulator = DataSimulator(sum_limit_schema)
        data = self.generate_and_collect(simulator)
        
        timesheets = data["timesheets"]
        
        # Check sum per group
        total_hours = timesheets.groupby(["employee_id", "date"])["hours"].sum()
        
        print(f"Total hours per group:\n{total_hours.head(10)}")
        
        # All should be <= 8
        assert total_hours.max() <= 8.0


class TestInequalityConstraint:
    """Tests for InequalityConstraint."""

    def _df(self):
        return pd.DataFrame({
            "price": [10.0, 5.0, 20.0, 3.0],
            "cost":  [15.0, 2.0, 18.0, 4.0],   # rows 0 and 3 violate price > cost
        })

    def test_apply_fixes_violations(self):
        from misata.constraints import InequalityConstraint
        df = self._df()
        c = InequalityConstraint("price", ">", "cost")
        result = c.apply(df)
        assert (result["price"] > result["cost"]).all()

    def test_validate_passes_after_apply(self):
        from misata.constraints import InequalityConstraint
        df = self._df()
        c = InequalityConstraint("price", ">", "cost")
        assert c.validate(c.apply(df))

    def test_validate_fails_on_violations(self):
        from misata.constraints import InequalityConstraint
        df = self._df()
        c = InequalityConstraint("price", ">", "cost")
        assert not c.validate(df)

    def test_missing_column_is_noop(self):
        from misata.constraints import InequalityConstraint
        df = pd.DataFrame({"price": [1.0, 2.0]})
        c = InequalityConstraint("price", ">", "missing_col")
        result = c.apply(df)
        assert result.equals(df)

    def test_less_than_operator(self):
        from misata.constraints import InequalityConstraint
        df = pd.DataFrame({"discount": [0.5, 0.1, 0.9], "max_discount": [0.3, 0.2, 0.8]})
        c = InequalityConstraint("discount", "<", "max_discount")
        result = c.apply(df)
        assert (result["discount"] < result["max_discount"]).all()

    def test_from_schema_constraint_inequality(self):
        from misata.constraints import ConstraintEngine
        from misata.schema import Constraint
        sc = Constraint(
            name="p_gt_c", type="inequality",
            column_a="price", operator=">", column_b="cost"
        )
        c = ConstraintEngine.from_schema_constraint(sc)
        from misata.constraints import InequalityConstraint
        assert isinstance(c, InequalityConstraint)


class TestColumnRangeConstraint:
    """Tests for ColumnRangeConstraint."""

    def _df(self):
        return pd.DataFrame({
            "min_price": [5.0,  10.0, 20.0],
            "max_price": [50.0, 80.0, 60.0],
            "price":     [3.0,  55.0, 40.0],   # row 0 below min, row 1 above max
        })

    def test_apply_clips_below_min(self):
        from misata.constraints import ColumnRangeConstraint
        df = self._df()
        c = ColumnRangeConstraint("price", "min_price", "max_price")
        result = c.apply(df)
        assert (result["price"] >= result["min_price"]).all()

    def test_apply_clips_above_max(self):
        from misata.constraints import ColumnRangeConstraint
        df = self._df()
        c = ColumnRangeConstraint("price", "min_price", "max_price")
        result = c.apply(df)
        assert (result["price"] <= result["max_price"]).all()

    def test_validate_passes_after_apply(self):
        from misata.constraints import ColumnRangeConstraint
        df = self._df()
        c = ColumnRangeConstraint("price", "min_price", "max_price")
        assert c.validate(c.apply(df))

    def test_validate_fails_on_violations(self):
        from misata.constraints import ColumnRangeConstraint
        df = self._df()
        c = ColumnRangeConstraint("price", "min_price", "max_price")
        assert not c.validate(df)

    def test_missing_column_is_noop(self):
        from misata.constraints import ColumnRangeConstraint
        df = pd.DataFrame({"price": [10.0], "min_price": [5.0]})
        c = ColumnRangeConstraint("price", "min_price", "max_price")  # max_price missing
        result = c.apply(df)
        assert result.equals(df)

    def test_from_schema_constraint_col_range(self):
        from misata.constraints import ConstraintEngine, ColumnRangeConstraint
        from misata.schema import Constraint
        sc = Constraint(
            name="price_range", type="col_range",
            column="price", low_column="min_price", high_column="max_price"
        )
        c = ConstraintEngine.from_schema_constraint(sc)
        assert isinstance(c, ColumnRangeConstraint)
