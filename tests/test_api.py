"""
Integration tests for FastAPI endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from misata.api import app


class TestAPIEndpoints:
    """Tests for API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns welcome."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "Misata" in data["name"]
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_validate_schema(self, client):
        """Test schema validation endpoint."""
        valid_schema = {
            "name": "Test",
            "tables": [{"name": "users", "row_count": 10}],
            "columns": {
                "users": [
                    {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 10}}
                ]
            },
            "relationships": [],
            "events": []
        }
        
        response = client.post("/api/validate-schema", json=valid_schema)
        
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data
        assert data["valid"] is True
    
    def test_validate_invalid_schema(self, client):
        """Test validation of invalid schema."""
        invalid_schema = {
            "name": "Test"
            # Missing required fields
        }
        
        response = client.post("/api/validate-schema", json=invalid_schema)
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "error" in data
    
    def test_preview_distribution_int(self, client):
        """Test distribution preview for integers."""
        response = client.post("/api/preview-distribution", params={
            "column_type": "int",
            "sample_size": 100
        }, json={
            "distribution": "uniform",
            "min": 0,
            "max": 100
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "histogram" in data
        assert "stats" in data
    
    def test_preview_distribution_categorical(self, client):
        """Test distribution preview for categorical."""
        response = client.post("/api/preview-distribution", params={
            "column_type": "categorical",
            "sample_size": 100
        }, json={
            "choices": ["A", "B", "C"],
            "probabilities": [0.5, 0.3, 0.2]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "distribution" in data
    
    def test_generate_data(self, client):
        """Test data generation endpoint."""
        request_body = {
            "schema_config": {
                "name": "Test",
                "tables": [{"name": "data", "row_count": 5}],
                "columns": {
                    "data": [
                        {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 5}},
                        {"name": "value", "type": "float", "distribution_params": {"distribution": "uniform", "min": 0, "max": 100}}
                    ]
                },
                "relationships": [],
                "events": []
            }
        }
        
        response = client.post("/api/generate-data", json=request_body)
        
        assert response.status_code == 200
        data = response.json()
        assert "tables" in data
        assert "data" in data["tables"]
        assert "download_id" in data


class TestAPIStoryGeneration:
    """Tests for LLM-based story generation (may fail without API key)."""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_story_endpoint_requires_body(self, client):
        """Test story endpoint validates input."""
        response = client.post("/api/generate-schema")
        
        # Should fail without body - 422 validation error
        assert response.status_code == 422
    
    def test_graph_endpoint_requires_body(self, client):
        """Test graph endpoint validates input."""
        response = client.post("/api/generate-from-graph")
        
        assert response.status_code == 422
