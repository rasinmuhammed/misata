"""
Unit tests for semantic inference.
"""

import pytest

from misata.schema import Column
from misata.semantic import SemanticInference, apply_semantic_inference, SEMANTIC_PATTERNS


class TestSemanticInference:
    """Tests for semantic column inference."""
    
    def test_email_detection(self):
        """Test that email columns are detected."""
        inference = SemanticInference()
        result = inference.infer_column("email")
        
        assert result is not None
        assert result[0] == "text"
        assert result[1]["text_type"] == "email"
    
    def test_user_email_detection(self):
        """Test email detection with prefix."""
        inference = SemanticInference()
        result = inference.infer_column("user_email")
        
        assert result is not None
        assert result[1]["text_type"] == "email"
    
    def test_phone_detection(self):
        """Test phone number detection."""
        inference = SemanticInference()
        
        for name in ["phone", "phone_number", "mobile", "telephone"]:
            result = inference.infer_column(name)
            assert result is not None, f"Failed for {name}"
            assert result[1]["text_type"] == "phone"
    
    def test_price_detection(self):
        """Test price columns have min=0."""
        inference = SemanticInference()
        
        for name in ["price", "cost", "amount", "total"]:
            result = inference.infer_column(name)
            assert result is not None, f"Failed for {name}"
            assert result[1].get("min", -1) >= 0, f"Price {name} should have min >= 0"
    
    def test_age_detection(self):
        """Test age has reasonable bounds."""
        inference = SemanticInference()
        result = inference.infer_column("age")
        
        assert result is not None
        assert result[0] == "int"
        assert result[1]["min"] >= 0
        assert result[1]["max"] <= 150
    
    def test_boolean_pattern(self):
        """Test boolean patterns are detected."""
        inference = SemanticInference()
        
        for name in ["is_active", "has_subscription", "can_edit", "verified"]:
            result = inference.infer_column(name)
            assert result is not None, f"Failed for {name}"
            assert result[0] == "boolean"
    
    def test_status_detection(self):
        """Test status columns become categorical."""
        inference = SemanticInference()
        result = inference.infer_column("status")
        
        assert result is not None
        assert result[0] == "categorical"
        assert "active" in result[1]["choices"]
    
    def test_no_match(self):
        """Test that unknown names return None."""
        inference = SemanticInference()
        result = inference.infer_column("foobar_xyz_123")
        
        assert result is None
    
    def test_fix_column_email(self):
        """Test fixing a text column that should be email."""
        inference = SemanticInference(strict_mode=True)
        
        col = Column(
            name="email",
            type="text",
            distribution_params={"text_type": "sentence"}  # Wrong!
        )
        
        fixed = inference.fix_column(col)
        assert fixed.distribution_params["text_type"] == "email"
    
    def test_apply_to_schema(self):
        """Test applying semantic inference to schema columns."""
        columns = {
            "users": [
                Column(name="id", type="int", distribution_params={"distribution": "uniform"}),
                Column(name="email", type="text", distribution_params={"text_type": "sentence"}),
                Column(name="age", type="int", distribution_params={"distribution": "normal", "mean": 100}),
            ]
        }
        
        fixed = apply_semantic_inference(columns)
        
        # Email should be fixed
        email_col = fixed["users"][1]
        # Age should have min constraint
        age_col = fixed["users"][2]
        
        assert email_col.name == "email"
        assert age_col.name == "age"
