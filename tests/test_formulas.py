"""
Unit tests for formula engine.
"""

import numpy as np
import pandas as pd
import pytest

from misata.formulas import FormulaEngine, FormulaColumn, apply_formula_columns


class TestFormulaEngine:
    """Tests for FormulaEngine."""
    
    @pytest.fixture
    def sample_tables(self):
        """Sample tables for testing."""
        return {
            "exercises": pd.DataFrame({
                "id": [1, 2, 3],
                "name": ["Running", "Cycling", "Yoga"],
                "calories_per_minute": [10, 8, 3]
            }),
            "workouts": pd.DataFrame({
                "id": [1, 2, 3, 4],
                "exercise_id": [1, 2, 3, 1],
                "duration_minutes": [30, 45, 60, 20]
            })
        }
    
    def test_simple_arithmetic(self, sample_tables):
        """Test simple arithmetic formula."""
        engine = FormulaEngine(sample_tables)
        df = sample_tables["workouts"]
        
        result = engine.evaluate_with_lookups(df, "duration_minutes * 2")
        
        expected = np.array([60, 90, 120, 40])
        np.testing.assert_array_equal(result, expected)
    
    def test_cross_table_lookup(self, sample_tables):
        """Test @table.column cross-table lookup."""
        engine = FormulaEngine(sample_tables)
        df = sample_tables["workouts"]
        
        result = engine.evaluate_with_lookups(
            df, 
            "duration_minutes * @exercises.calories_per_minute",
            fk_mappings={"exercises": "exercise_id"}
        )
        
        # workout 1: 30 min * 10 cal/min = 300
        # workout 2: 45 min * 8 cal/min = 360
        # workout 3: 60 min * 3 cal/min = 180
        # workout 4: 20 min * 10 cal/min = 200
        expected = np.array([300, 360, 180, 200])
        np.testing.assert_array_equal(result, expected)
    
    def test_multiple_cross_table_refs(self, sample_tables):
        """Test formula with multiple cross-table references."""
        # Add products table
        sample_tables["products"] = pd.DataFrame({
            "id": [1, 2],
            "price": [10.0, 20.0],
            "discount": [0.1, 0.2]
        })
        
        sample_tables["order_items"] = pd.DataFrame({
            "id": [1, 2, 3],
            "product_id": [1, 2, 1],
            "quantity": [2, 1, 3]
        })
        
        engine = FormulaEngine(sample_tables)
        df = sample_tables["order_items"]
        
        # Calculate total price: quantity * price
        result = engine.evaluate_with_lookups(
            df,
            "quantity * @products.price",
            fk_mappings={"products": "product_id"}
        )
        
        expected = np.array([20.0, 20.0, 30.0])
        np.testing.assert_array_almost_equal(result, expected)


class TestFormulaColumn:
    """Tests for FormulaColumn class."""
    
    def test_formula_column_int_result(self):
        """Test FormulaColumn with int result type."""
        tables = {
            "data": pd.DataFrame({"value": [1.5, 2.7, 3.9]})
        }
        
        col = FormulaColumn(
            name="doubled",
            formula="value * 2",
            result_type="int"
        )
        
        result = col.evaluate(tables["data"], tables)
        
        assert result.dtype == int
        np.testing.assert_array_equal(result, [3, 5, 7])
    
    def test_formula_column_float_result(self):
        """Test FormulaColumn with float result type."""
        tables = {
            "data": pd.DataFrame({"value": [10, 20, 30]})
        }
        
        col = FormulaColumn(
            name="percent",
            formula="value / 100",
            result_type="float"
        )
        
        result = col.evaluate(tables["data"], tables)
        
        assert result.dtype == float
        np.testing.assert_array_almost_equal(result, [0.1, 0.2, 0.3])


class TestApplyFormulaColumns:
    """Tests for apply_formula_columns function."""
    
    def test_applies_multiple_formulas(self):
        """Test applying multiple formula columns."""
        tables = {
            "sales": pd.DataFrame({
                "quantity": [10, 20, 30],
                "unit_price": [5.0, 10.0, 15.0]
            })
        }
        
        formulas = [
            FormulaColumn("total", "quantity * unit_price", "float"),
            FormulaColumn("tax", "quantity * unit_price * 0.1", "float"),
        ]
        
        result = apply_formula_columns(tables["sales"], formulas, tables)
        
        assert "total" in result.columns
        assert "tax" in result.columns
        np.testing.assert_array_almost_equal(result["total"], [50, 200, 450])
        np.testing.assert_array_almost_equal(result["tax"], [5, 20, 45])


class TestFormulaEdgeCases:
    """Tests for edge cases in formula evaluation."""
    
    def test_empty_dataframe(self):
        """Test formula on empty dataframe."""
        tables = {
            "empty": pd.DataFrame({"value": []})
        }
        
        engine = FormulaEngine(tables)
        result = engine.evaluate_with_lookups(tables["empty"], "value * 2")
        
        assert len(result) == 0
    
    def test_missing_table_raises(self):
        """Test that referencing missing table raises error."""
        tables = {
            "data": pd.DataFrame({"id": [1, 2, 3]})
        }
        
        engine = FormulaEngine(tables)
        
        with pytest.raises(ValueError, match="not found"):
            engine.evaluate_with_lookups(tables["data"], "@nonexistent.value")

