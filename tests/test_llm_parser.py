"""
Unit tests for LLM parser (using mocks).
"""

import json
import pytest
from unittest.mock import MagicMock, patch

# Mock response from Groq
MOCK_LLM_RESPONSE = {
    "name": "Test Dataset",
    "description": "Test description",
    "seed": 42,
    "tables": [
        {"name": "plans", "is_reference": True, "inline_data": [
            {"id": 1, "name": "Free", "price": 0.0},
            {"id": 2, "name": "Premium", "price": 9.99}
        ]},
        {"name": "users", "row_count": 100, "is_reference": False}
    ],
    "columns": {
        "users": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 100}},
            {"name": "email", "type": "text", "distribution_params": {"text_type": "email"}},
            {"name": "plan_id", "type": "foreign_key", "distribution_params": {}}
        ]
    },
    "relationships": [
        {"parent_table": "plans", "child_table": "users", "parent_key": "id", "child_key": "plan_id"}
    ],
    "events": []
}


class TestLLMSchemaGenerator:
    """Tests for LLMSchemaGenerator with mocked Groq API."""
    
    @pytest.fixture
    def mock_groq_response(self):
        """Create mock Groq response."""
        mock_message = MagicMock()
        mock_message.content = json.dumps(MOCK_LLM_RESPONSE)
        
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        
        return mock_response
    
    @patch.dict('os.environ', {'GROQ_API_KEY': 'test_key'})
    @patch('misata.llm_parser.Groq')
    def test_generate_from_story(self, mock_groq_class, mock_groq_response):
        """Test schema generation from story."""
        from misata.llm_parser import LLMSchemaGenerator
        
        # Setup mock
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_groq_response
        mock_groq_class.return_value = mock_client
        
        # Test
        generator = LLMSchemaGenerator(api_key="test_key")
        schema = generator.generate_from_story("Test SaaS app")
        
        assert schema.name == "Test Dataset"
        assert len(schema.tables) == 2
        assert len(schema.relationships) == 1
    
    @patch.dict('os.environ', {'GROQ_API_KEY': 'test_key'})
    @patch('misata.llm_parser.Groq')
    def test_reference_table_parsing(self, mock_groq_class, mock_groq_response):
        """Test that reference tables with inline_data are parsed correctly."""
        from misata.llm_parser import LLMSchemaGenerator
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_groq_response
        mock_groq_class.return_value = mock_client
        
        generator = LLMSchemaGenerator(api_key="test_key")
        schema = generator.generate_from_story("Test")
        
        # Find plans table
        plans_table = next(t for t in schema.tables if t.name == "plans")
        
        assert plans_table.is_reference is True
        assert plans_table.inline_data is not None
        assert len(plans_table.inline_data) == 2
        assert plans_table.inline_data[0]["price"] == 0.0
    
    @patch.dict('os.environ', {'GROQ_API_KEY': 'test_key'})
    @patch('misata.llm_parser.Groq')
    def test_columns_parsed(self, mock_groq_class, mock_groq_response):
        """Test that columns are parsed correctly."""
        from misata.llm_parser import LLMSchemaGenerator
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_groq_response
        mock_groq_class.return_value = mock_client
        
        generator = LLMSchemaGenerator(api_key="test_key")
        schema = generator.generate_from_story("Test")
        
        user_columns = schema.columns["users"]
        assert len(user_columns) == 3
        
        email_col = next(c for c in user_columns if c.name == "email")
        assert email_col.type == "text"
        assert email_col.distribution_params["text_type"] == "email"
    
    def test_missing_api_key_raises(self):
        """Test that missing API key raises ValueError."""
        from misata.llm_parser import LLMSchemaGenerator
        
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="Groq API key required"):
                LLMSchemaGenerator()
    
    @patch.dict('os.environ', {'GROQ_API_KEY': 'test_key'})
    @patch('misata.llm_parser.Groq')
    def test_handles_missing_optional_fields(self, mock_groq_class):
        """Test handling of minimal LLM response."""
        from misata.llm_parser import LLMSchemaGenerator
        
        minimal_response = {
            "name": "Minimal",
            "tables": [{"name": "data", "row_count": 10}],
            "columns": {
                "data": [{"name": "id", "type": "int", "distribution_params": {"distribution": "uniform"}}]
            }
        }
        
        mock_message = MagicMock()
        mock_message.content = json.dumps(minimal_response)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq_class.return_value = mock_client
        
        generator = LLMSchemaGenerator(api_key="test_key")
        schema = generator.generate_from_story("Minimal test")
        
        assert schema.name == "Minimal"
        assert len(schema.tables) == 1
        assert schema.relationships == []
        assert schema.events == []


class TestLLMDateNormalization:
    """Test date parameter normalization."""
    
    @patch.dict('os.environ', {'GROQ_API_KEY': 'test_key'})
    @patch('misata.llm_parser.Groq')
    def test_normalizes_start_date_end_date(self, mock_groq_class):
        """Test that start_date/end_date are normalized to start/end."""
        from misata.llm_parser import LLMSchemaGenerator
        
        response_with_date_variants = {
            "name": "Test",
            "tables": [{"name": "events", "row_count": 10}],
            "columns": {
                "events": [
                    {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform"}},
                    {"name": "created_at", "type": "date", "distribution_params": {
                        "start_date": "2023-01-01",
                        "end_date": "2024-12-31"
                    }}
                ]
            }
        }
        
        mock_message = MagicMock()
        mock_message.content = json.dumps(response_with_date_variants)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq_class.return_value = mock_client
        
        generator = LLMSchemaGenerator(api_key="test_key")
        schema = generator.generate_from_story("Test")
        
        date_col = schema.columns["events"][1]
        assert "start" in date_col.distribution_params
        assert "end" in date_col.distribution_params
