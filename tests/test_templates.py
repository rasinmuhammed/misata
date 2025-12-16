"""
Unit tests for industry templates.
"""

import pytest

from misata.templates import (
    TEMPLATES,
    get_template,
    list_templates,
    template_to_schema,
    SAAS_TEMPLATE,
    ECOMMERCE_TEMPLATE,
    FITNESS_TEMPLATE,
    HEALTHCARE_TEMPLATE,
)


class TestTemplateRegistry:
    """Tests for template registry."""
    
    def test_list_templates(self):
        """Test listing available templates."""
        templates = list_templates()
        
        assert "saas" in templates
        assert "ecommerce" in templates
        assert "fitness" in templates
        assert "healthcare" in templates
        assert len(templates) == 4
    
    def test_get_valid_template(self):
        """Test getting a valid template."""
        template = get_template("saas")
        
        assert template["name"] == "SaaS Company Dataset"
        assert "tables" in template
        assert "columns" in template
    
    def test_get_invalid_template_raises(self):
        """Test that invalid template name raises error."""
        with pytest.raises(ValueError, match="not found"):
            get_template("nonexistent_template")


class TestSaaSTemplate:
    """Tests for SaaS template."""
    
    def test_has_required_tables(self):
        """Test SaaS has core tables."""
        tables = [t["name"] for t in SAAS_TEMPLATE["tables"]]
        
        assert "plans" in tables
        assert "users" in tables
        assert "subscriptions" in tables
        assert "payments" in tables
    
    def test_plans_is_reference_table(self):
        """Test plans table is reference with inline data."""
        plans = next(t for t in SAAS_TEMPLATE["tables"] if t["name"] == "plans")
        
        assert plans["is_reference"] is True
        assert plans["inline_data"] is not None
        assert len(plans["inline_data"]) == 4
    
    def test_plan_prices_are_valid(self):
        """Test plan prices are non-negative."""
        plans = next(t for t in SAAS_TEMPLATE["tables"] if t["name"] == "plans")
        
        for plan in plans["inline_data"]:
            assert plan["price"] >= 0
    
    def test_has_relationships(self):
        """Test SaaS has proper relationships."""
        relationships = SAAS_TEMPLATE["relationships"]
        
        # Should have users -> subscriptions
        user_to_sub = any(
            r["parent_table"] == "users" and r["child_table"] == "subscriptions"
            for r in relationships
        )
        assert user_to_sub


class TestEcommerceTemplate:
    """Tests for E-commerce template."""
    
    def test_has_products_table(self):
        """Test e-commerce has products."""
        tables = [t["name"] for t in ECOMMERCE_TEMPLATE["tables"]]
        
        assert "products" in tables
        assert "orders" in tables
        assert "customers" in tables
    
    def test_products_have_prices(self):
        """Test products have valid prices."""
        products = next(t for t in ECOMMERCE_TEMPLATE["tables"] if t["name"] == "products")
        
        for product in products["inline_data"]:
            assert "price" in product
            assert product["price"] > 0


class TestFitnessTemplate:
    """Tests for Fitness template."""
    
    def test_has_exercises_table(self):
        """Test fitness has exercises reference table."""
        tables = [t["name"] for t in FITNESS_TEMPLATE["tables"]]
        
        assert "exercises" in tables
        assert "workouts" in tables
    
    def test_exercises_have_calories(self):
        """Test exercises have calories_per_minute."""
        exercises = next(t for t in FITNESS_TEMPLATE["tables"] if t["name"] == "exercises")
        
        for exercise in exercises["inline_data"]:
            assert "calories_per_minute" in exercise
            assert exercise["calories_per_minute"] > 0


class TestHealthcareTemplate:
    """Tests for Healthcare template."""
    
    def test_has_required_tables(self):
        """Test healthcare has core tables."""
        tables = [t["name"] for t in HEALTHCARE_TEMPLATE["tables"]]
        
        assert "patients" in tables
        assert "doctors" in tables
        assert "appointments" in tables
        assert "diagnoses_catalog" in tables


class TestTemplateToSchema:
    """Tests for converting templates to SchemaConfig."""
    
    def test_converts_saas_template(self):
        """Test converting SaaS template to schema."""
        schema = template_to_schema("saas")
        
        assert schema.name == "SaaS Company Dataset"
        assert len(schema.tables) == 5
        assert len(schema.relationships) == 4
    
    def test_row_multiplier(self):
        """Test row count multiplier works."""
        schema_1x = template_to_schema("saas", row_multiplier=1.0)
        schema_half = template_to_schema("saas", row_multiplier=0.5)
        
        # Find users table in both
        users_1x = next(t for t in schema_1x.tables if t.name == "users")
        users_half = next(t for t in schema_half.tables if t.name == "users")
        
        assert users_half.row_count == users_1x.row_count * 0.5
    
    def test_reference_tables_preserved(self):
        """Test reference tables keep their inline data."""
        schema = template_to_schema("fitness")
        
        exercises = next(t for t in schema.tables if t.name == "exercises")
        
        assert exercises.is_reference is True
        assert exercises.inline_data is not None
        assert len(exercises.inline_data) == 10  # 10 exercises in template
    
    def test_relationships_preserved(self):
        """Test relationships are preserved in conversion."""
        schema = template_to_schema("ecommerce")
        
        # Check customer -> orders relationship exists
        rel = next(
            (r for r in schema.relationships if r.child_table == "orders"),
            None
        )
        assert rel is not None
        assert rel.parent_table == "customers"
