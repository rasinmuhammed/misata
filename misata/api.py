"""
Misata API - FastAPI backend for the web UI.

Provides REST endpoints for:
- Story-to-schema generation (LLM-powered)
- Graph-to-data reverse engineering
- Data generation and preview
- Schema validation and export
"""

import io
import os
import tempfile
import zipfile
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from misata import DataSimulator, SchemaConfig
from misata.llm_parser import LLMSchemaGenerator


# ============================================================================
# Request/Response Models
# ============================================================================

class StoryRequest(BaseModel):
    """Request to generate schema from story."""
    story: str
    default_rows: int = 10000


class GraphRequest(BaseModel):
    """Request to generate schema from graph description."""
    description: str
    chart_type: str = "line"


class GenerateRequest(BaseModel):
    """Request to generate data from schema."""
    schema_config: Dict[str, Any]
    seed: Optional[int] = None


class EnhanceRequest(BaseModel):
    """Request to enhance existing schema."""
    schema_config: Dict[str, Any]
    enhancement: str


class IndustrySuggestionsRequest(BaseModel):
    """Request for industry-specific improvements."""
    schema_config: Dict[str, Any]
    industry: str


class SchemaResponse(BaseModel):
    """Response containing generated schema."""
    schema_config: Dict[str, Any]
    tables_count: int
    total_rows: int


class DataPreviewResponse(BaseModel):
    """Response containing data preview."""
    tables: Dict[str, List[Dict[str, Any]]]
    stats: Dict[str, Dict[str, Any]]
    download_id: str


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Misata API",
    description="AI-Powered Synthetic Data Engine",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for generated data (in production, use Redis or file storage)
_generated_data: Dict[str, Dict] = {}


# ============================================================================
# Health Check
# ============================================================================

@app.get("/")
async def root():
    """Health check and API info."""
    return {
        "name": "Misata API",
        "version": "2.0.0",
        "status": "healthy",
        "docs": "/docs"
    }


@app.get("/api/health")
async def health_check():
    """Detailed health check."""
    groq_key_set = bool(os.environ.get("GROQ_API_KEY"))
    return {
        "status": "healthy",
        "groq_configured": groq_key_set,
        "message": "Ready to generate synthetic data!" if groq_key_set else "Set GROQ_API_KEY for LLM features"
    }


# ============================================================================
# Schema Generation Endpoints
# ============================================================================

@app.post("/api/generate-schema", response_model=SchemaResponse)
async def generate_schema_from_story(request: StoryRequest):
    """
    Generate schema from natural language story using LLM.
    
    This is the core AI feature - describe your data needs in plain English.
    """
    try:
        llm = LLMSchemaGenerator()
        schema = llm.generate_from_story(
            request.story,
            default_rows=request.default_rows
        )
        
        return SchemaResponse(
            schema_config=schema.model_dump(),
            tables_count=len(schema.tables),
            total_rows=sum(t.row_count for t in schema.tables)
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schema generation failed: {str(e)}")


@app.post("/api/generate-from-graph", response_model=SchemaResponse)
async def generate_schema_from_graph(request: GraphRequest):
    """
    REVERSE ENGINEERING: Generate schema that produces desired chart patterns.
    
    Describe your chart, get data that matches it exactly.
    """
    try:
        llm = LLMSchemaGenerator()
        schema = llm.generate_from_graph(request.description)
        
        return SchemaResponse(
            schema_config=schema.model_dump(),
            tables_count=len(schema.tables),
            total_rows=sum(t.row_count for t in schema.tables)
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph schema generation failed: {str(e)}")


@app.post("/api/enhance-schema", response_model=SchemaResponse)
async def enhance_schema(request: EnhanceRequest):
    """
    Enhance an existing schema with additional requirements.
    """
    try:
        llm = LLMSchemaGenerator()
        existing = SchemaConfig(**request.schema_config)
        enhanced = llm.enhance_schema(existing, request.enhancement)
        
        return SchemaResponse(
            schema_config=enhanced.model_dump(),
            tables_count=len(enhanced.tables),
            total_rows=sum(t.row_count for t in enhanced.tables)
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schema enhancement failed: {str(e)}")


@app.post("/api/industry-suggestions")
async def get_industry_suggestions(request: IndustrySuggestionsRequest):
    """
    Get AI suggestions for making data more industry-realistic.
    """
    try:
        llm = LLMSchemaGenerator()
        schema = SchemaConfig(**request.schema_config)
        suggestions = llm.suggest_industry_improvements(schema, request.industry)
        
        return suggestions
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Suggestions failed: {str(e)}")


# ============================================================================
# Data Generation Endpoints
# ============================================================================

@app.post("/api/generate-data", response_model=DataPreviewResponse)
async def generate_data(request: GenerateRequest, background_tasks: BackgroundTasks):
    """
    Generate synthetic data from schema configuration.
    
    Returns a preview (first 100 rows per table) and a download ID for full data.
    """
    try:
        schema = SchemaConfig(**request.schema_config)
        
        if request.seed is not None:
            schema.seed = request.seed
        
        simulator = DataSimulator(schema)
        data = simulator.generate_all()
        
        # Generate unique download ID
        import uuid
        download_id = str(uuid.uuid4())
        
        # Store data for download (in production, use proper storage)
        _generated_data[download_id] = data
        
        # Build preview (first 100 rows)
        preview = {}
        stats = {}
        
        for table_name, df in data.items():
            preview[table_name] = df.head(100).to_dict(orient="records")
            
            # Calculate stats
            stats[table_name] = {
                "row_count": len(df),
                "columns": list(df.columns),
                "memory_mb": df.memory_usage(deep=True).sum() / 1024**2,
                "numeric_stats": {}
            }
            
            for col in df.select_dtypes(include=["number"]).columns:
                stats[table_name]["numeric_stats"][col] = {
                    "mean": float(df[col].mean()),
                    "std": float(df[col].std()),
                    "min": float(df[col].min()),
                    "max": float(df[col].max())
                }
        
        # Clean up old data after 1 hour (in background)
        background_tasks.add_task(cleanup_old_data, download_id, 3600)
        
        return DataPreviewResponse(
            tables=preview,
            stats=stats,
            download_id=download_id
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data generation failed: {str(e)}")


@app.get("/api/download/{download_id}")
async def download_data(download_id: str, format: str = "csv"):
    """
    Download generated data as CSV or JSON.
    """
    if download_id not in _generated_data:
        raise HTTPException(status_code=404, detail="Data not found. It may have expired.")
    
    data = _generated_data[download_id]
    
    if format == "csv":
        # Create ZIP with all CSVs
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for table_name, df in data.items():
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False)
                zf.writestr(f"{table_name}.csv", csv_buffer.getvalue())
        
        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=misata_data_{download_id[:8]}.zip"}
        )
    
    elif format == "json":
        json_data = {name: df.to_dict(orient="records") for name, df in data.items()}
        return json_data
    
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


async def cleanup_old_data(download_id: str, delay_seconds: int):
    """Clean up generated data after delay."""
    import asyncio
    await asyncio.sleep(delay_seconds)
    if download_id in _generated_data:
        del _generated_data[download_id]


# ============================================================================
# Validation Endpoints
# ============================================================================

@app.post("/api/validate-schema")
async def validate_schema(schema_config: Dict[str, Any]):
    """
    Validate a schema configuration.
    """
    try:
        schema = SchemaConfig(**schema_config)
        return {
            "valid": True,
            "tables": len(schema.tables),
            "columns": sum(len(cols) for cols in schema.columns.values()),
            "relationships": len(schema.relationships),
            "events": len(schema.events)
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }


@app.post("/api/preview-distribution")
async def preview_distribution(
    column_type: str,
    distribution_params: Dict[str, Any],
    sample_size: int = 1000
):
    """
    Preview what a distribution will look like before generating.
    """
    import numpy as np
    
    rng = np.random.default_rng(42)
    
    if column_type in ["int", "float"]:
        dist = distribution_params.get("distribution", "normal")
        
        if dist == "normal":
            values = rng.normal(
                distribution_params.get("mean", 100),
                distribution_params.get("std", 20),
                sample_size
            )
        elif dist == "uniform":
            values = rng.uniform(
                distribution_params.get("min", 0),
                distribution_params.get("max", 100),
                sample_size
            )
        elif dist == "exponential":
            values = rng.exponential(
                distribution_params.get("scale", 1.0),
                sample_size
            )
        else:
            values = rng.normal(100, 20, sample_size)
        
        # Apply constraints
        if "min" in distribution_params:
            values = np.maximum(values, distribution_params["min"])
        if "max" in distribution_params:
            values = np.minimum(values, distribution_params["max"])
        
        if column_type == "int":
            values = values.astype(int)
        
        # Return histogram data
        hist, bin_edges = np.histogram(values, bins=50)
        
        return {
            "histogram": {
                "counts": hist.tolist(),
                "bin_edges": bin_edges.tolist()
            },
            "stats": {
                "mean": float(values.mean()),
                "std": float(values.std()),
                "min": float(values.min()),
                "max": float(values.max())
            },
            "sample": values[:20].tolist()
        }
    
    elif column_type == "categorical":
        choices = distribution_params.get("choices", ["A", "B", "C"])
        probs = distribution_params.get("probabilities")
        
        if probs:
            probs = np.array(probs)
            probs = probs / probs.sum()
        
        values = rng.choice(choices, size=sample_size, p=probs)
        unique, counts = np.unique(values, return_counts=True)
        
        return {
            "distribution": {choice: int(count) for choice, count in zip(unique, counts)},
            "sample": values[:20].tolist()
        }
    
    else:
        return {"error": f"Preview not supported for type: {column_type}"}


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
