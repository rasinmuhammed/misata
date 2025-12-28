from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import uuid
import os
import io
import shutil
import zipfile
from celery.result import AsyncResult

# Import worker and LLM
from worker import celery_app, generate_dataset_task

# Add misata core to path
import sys
sys.path.insert(0, os.path.abspath('../../packages/core'))

from misata.llm_parser import LLMSchemaGenerator

app = FastAPI(
    title="Misata Cloud API",
    description="Enterprise API for Synthetic Data Generation",
    version="0.1.0-alpha"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ Request/Response Models ============

class JobRequest(BaseModel):
    schema_config: Dict[str, Any]
    project_id: Optional[str] = "default"

class JobResponse(BaseModel):
    job_id: str
    status: str

class StoryRequest(BaseModel):
    story: str
    provider: Optional[str] = "groq"

class SchemaGenerationResponse(BaseModel):
    schema: Dict[str, Any]
    explanation: str

# ============ Health Check ============

@app.get("/")
def health_check():
    return {
        "status": "healthy",
        "service": "misata-api",
        "version": app.version,
        "worker_connected": True
    }

# ============ Job Management ============

@app.get("/jobs/completed")
def list_completed_jobs():
    """List all jobs with output files in storage (completed jobs)."""
    import pandas as pd
    from datetime import datetime
    
    storage_base = os.path.abspath("storage")
    
    if not os.path.exists(storage_base):
        return {"jobs": []}
    
    completed_jobs = []
    
    for job_id in os.listdir(storage_base):
        job_path = os.path.join(storage_base, job_id)
        if not os.path.isdir(job_path):
            continue
        
        csv_files = [f for f in os.listdir(job_path) if f.endswith('.csv')]
        if not csv_files:
            continue
        
        # Get job metadata
        total_rows = 0
        for csv_file in csv_files:
            try:
                df = pd.read_csv(os.path.join(job_path, csv_file))
                total_rows += len(df)
            except:
                pass
        
        # Get creation time from directory
        created = datetime.fromtimestamp(os.path.getctime(job_path)).isoformat()
        
        completed_jobs.append({
            "id": job_id,
            "status": "SUCCESS",
            "tables": len(csv_files),
            "rows": total_rows,
            "created_at": created,
            "schema_name": f"Dataset ({len(csv_files)} tables)"
        })
    
    # Sort by creation time (newest first)
    completed_jobs.sort(key=lambda x: x["created_at"], reverse=True)
    
    return {"jobs": completed_jobs}

@app.post("/jobs", response_model=JobResponse, status_code=202)
def create_job(request: JobRequest):
    """Submit a new data generation job."""
    job_id = str(uuid.uuid4())
    
    task = generate_dataset_task.apply_async(
        args=[request.schema_config, job_id],
        task_id=job_id
    )
    
    return {"job_id": job_id, "status": "queued"}

@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Check the status of a job."""
    task_result = AsyncResult(job_id, app=celery_app)
    
    response = {
        "job_id": job_id,
        "status": task_result.state,
        "result": task_result.result,
    }
    
    if task_result.state == 'PROGRESS':
        response["progress"] = task_result.info.get("progress", 0)
        response["message"] = task_result.info.get("status", "")
    elif task_result.state == 'SUCCESS':
        response["progress"] = 100
        if isinstance(task_result.result, dict):
            response.update(task_result.result)
    elif task_result.state == 'FAILURE':
        response["progress"] = 100
        response["error"] = str(task_result.result)
        response["traceback"] = task_result.traceback
              
    return response

@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """Delete a job and its associated files."""
    storage_dir = os.path.abspath(f"storage/{job_id}")
    
    if not os.path.exists(storage_dir):
        raise HTTPException(status_code=404, detail="Job not found")
    
    try:
        shutil.rmtree(storage_dir)
        return {"status": "deleted", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")

@app.get("/jobs/{job_id}/download")
def download_job_files(job_id: str):
    """Download all generated files as a ZIP."""
    storage_dir = os.path.abspath(f"storage/{job_id}")
    
    if not os.path.exists(storage_dir):
        raise HTTPException(status_code=404, detail="Job output not found")
    
    # Get all CSV files
    files = [f for f in os.listdir(storage_dir) if f.endswith('.csv')]
    
    if not files:
        raise HTTPException(status_code=404, detail="No files generated")
    
    # If single file, return directly
    if len(files) == 1:
        return FileResponse(
            path=os.path.join(storage_dir, files[0]),
            filename=files[0],
            media_type="text/csv"
        )
    
    # Multiple files: create ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_name in files:
            file_path = os.path.join(storage_dir, file_name)
            zip_file.write(file_path, file_name)
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=misata_{job_id[:8]}.zip"}
    )

@app.get("/jobs/{job_id}/data")
def get_job_data(job_id: str, limit: int = 100):
    """Get parsed CSV data as JSON for in-app viewing."""
    import pandas as pd
    
    storage_dir = os.path.abspath(f"storage/{job_id}")
    
    if not os.path.exists(storage_dir):
        raise HTTPException(status_code=404, detail="Job output not found")
    
    # Get all CSV files
    files = [f for f in os.listdir(storage_dir) if f.endswith('.csv')]
    
    if not files:
        raise HTTPException(status_code=404, detail="No files generated")
    
    # Parse each CSV and return as JSON
    tables = {}
    for file_name in files:
        table_name = file_name.replace('.csv', '')
        file_path = os.path.join(storage_dir, file_name)
        try:
            df = pd.read_csv(file_path, nrows=limit)
            tables[table_name] = {
                "columns": df.columns.tolist(),
                "rows": df.head(limit).to_dict(orient='records'),
                "total_rows": len(pd.read_csv(file_path)),  # Get actual count
                "preview_rows": len(df)
            }
        except Exception as e:
            tables[table_name] = {"error": str(e)}
    
    return {
        "job_id": job_id,
        "tables": tables
    }

# ============ LLM Schema Generation ============

@app.post("/schema/generate", response_model=SchemaGenerationResponse)
async def generate_schema_from_story(request: StoryRequest):
    """Generate a schema from natural language story using LLM."""
    try:
        generator = LLMSchemaGenerator(provider=request.provider)
        
        # Generate schema from story
        schema = generator.generate_from_story(request.story)
        
        # Convert to dict format
        schema_dict = {
            "name": schema.name,
            "description": schema.description,
            "tables": [
                {"name": t.name, "row_count": t.row_count}
                for t in schema.tables
            ],
            "columns": {
                table_name: [
                    {
                        "name": col.name,
                        "type": col.type,
                        "distribution_params": col.distribution_params
                    }
                    for col in cols
                ]
                for table_name, cols in schema.columns.items()
            },
            "relationships": [
                {
                    "parent_table": r.parent_table,
                    "child_table": r.child_table,
                    "parent_key": r.parent_key,
                    "child_key": r.child_key
                }
                for r in schema.relationships
            ]
        }
        
        return {
            "schema": schema_dict,
            "explanation": f"Generated schema with {len(schema.tables)} tables based on your story."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ Templates ============

@app.get("/templates")
def list_templates():
    """Get list of available schema templates."""
    return {
        "templates": [
            {
                "id": "ecommerce",
                "name": "E-commerce Platform",
                "description": "Users, products, orders, reviews",
                "tables": 5,
                "preview_rows": 10000
            },
            {
                "id": "saas",
                "name": "SaaS Analytics",
                "description": "Companies, users, subscriptions, events",
                "tables": 4,
                "preview_rows": 25000
            },
            {
                "id": "healthcare",
                "name": "Healthcare System",
                "description": "Patients, doctors, appointments, prescriptions",
                "tables": 6,
                "preview_rows": 50000
            }
        ]
    }

# ============ Data Quality Report ============

@app.get("/jobs/{job_id}/quality-report")
def get_quality_report(job_id: str):
    """Generate an enhanced data quality report for completed job."""
    import pandas as pd
    import numpy as np
    import json
    
    storage_dir = os.path.abspath(f"storage/{job_id}")
    
    if not os.path.exists(storage_dir):
        raise HTTPException(status_code=404, detail="Job output not found")
    
    files = [f for f in os.listdir(storage_dir) if f.endswith('.csv')]
    
    if not files:
        raise HTTPException(status_code=404, detail="No files generated")
    
    report = {
        "job_id": job_id,
        "generated_at": pd.Timestamp.now().isoformat(),
        "tables": {}
    }
    
    quality_issues = []
    
    for file_name in files:
        table_name = file_name.replace('.csv', '')
        file_path = os.path.join(storage_dir, file_name)
        
        try:
            df = pd.read_csv(file_path)
            
            table_stats = {
                "row_count": len(df),
                "column_count": len(df.columns),
                "file_size_kb": round(os.path.getsize(file_path) / 1024, 2),
                "memory_usage_kb": round(df.memory_usage(deep=True).sum() / 1024, 2),
                "columns": {},
                "correlations": None,
                "numeric_summary": None,
            }
            
            # Get numeric columns for correlation analysis
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            
            # Correlation matrix for numeric columns (if 2+ numeric cols)
            if len(numeric_cols) >= 2:
                corr_matrix = df[numeric_cols].corr()
                # Convert to serializable format
                correlations = {}
                for col in corr_matrix.columns:
                    correlations[col] = {
                        c: round(float(corr_matrix.loc[col, c]), 3) 
                        for c in corr_matrix.columns
                    }
                table_stats["correlations"] = correlations
                
                # Find strong correlations (potential data quality issues or relationships)
                for i, col1 in enumerate(numeric_cols):
                    for col2 in numeric_cols[i+1:]:
                        corr_val = abs(corr_matrix.loc[col1, col2])
                        if corr_val > 0.9:
                            quality_issues.append({
                                "table": table_name,
                                "type": "high_correlation",
                                "columns": [col1, col2],
                                "value": round(float(corr_val), 3)
                            })
            
            # Numeric summary statistics
            if numeric_cols:
                numeric_summary = {}
                for col in numeric_cols:
                    series = df[col].dropna()
                    if len(series) > 0:
                        numeric_summary[col] = {
                            "mean": round(float(series.mean()), 2),
                            "std": round(float(series.std()), 2),
                            "min": float(series.min()),
                            "25%": float(series.quantile(0.25)),
                            "50%": float(series.quantile(0.50)),
                            "75%": float(series.quantile(0.75)),
                            "max": float(series.max()),
                            "skewness": round(float(series.skew()), 3) if len(series) > 2 else 0,
                            "kurtosis": round(float(series.kurtosis()), 3) if len(series) > 3 else 0,
                        }
                table_stats["numeric_summary"] = numeric_summary
            
            for col in df.columns:
                col_stats = {
                    "dtype": str(df[col].dtype),
                    "null_count": int(df[col].isnull().sum()),
                    "null_pct": round(df[col].isnull().sum() / len(df) * 100, 2),
                    "unique_count": int(df[col].nunique()),
                    "cardinality_pct": round(df[col].nunique() / len(df) * 100, 2),
                }
                
                # Add numeric stats with histogram data
                if pd.api.types.is_numeric_dtype(df[col]):
                    series = df[col].dropna()
                    
                    col_stats.update({
                        "min": float(series.min()) if len(series) > 0 else None,
                        "max": float(series.max()) if len(series) > 0 else None,
                        "mean": round(float(series.mean()), 2) if len(series) > 0 else None,
                        "std": round(float(series.std()), 2) if len(series) > 0 else None,
                        "median": float(series.median()) if len(series) > 0 else None,
                    })
                    
                    # Generate histogram data (10 bins)
                    if len(series) > 0:
                        try:
                            counts, bin_edges = np.histogram(series, bins=10)
                            col_stats["histogram"] = {
                                "counts": [int(c) for c in counts],
                                "bin_edges": [round(float(e), 2) for e in bin_edges],
                            }
                        except Exception:
                            pass
                    
                    # Outlier detection using IQR method
                    if len(series) > 4:
                        q1, q3 = series.quantile([0.25, 0.75])
                        iqr = q3 - q1
                        lower_bound = q1 - 1.5 * iqr
                        upper_bound = q3 + 1.5 * iqr
                        outliers = series[(series < lower_bound) | (series > upper_bound)]
                        outlier_count = len(outliers)
                        outlier_pct = round(outlier_count / len(series) * 100, 2)
                        
                        col_stats["outliers"] = {
                            "count": outlier_count,
                            "percentage": outlier_pct,
                            "lower_bound": round(float(lower_bound), 2),
                            "upper_bound": round(float(upper_bound), 2),
                        }
                        
                        if outlier_pct > 5:
                            quality_issues.append({
                                "table": table_name,
                                "type": "high_outliers",
                                "column": col,
                                "percentage": outlier_pct
                            })
                
                # Add categorical stats with value distribution
                elif df[col].nunique() <= 20:
                    value_counts = df[col].value_counts()
                    col_stats["value_distribution"] = {
                        str(k): {
                            "count": int(v),
                            "percentage": round(v / len(df) * 100, 2)
                        } for k, v in value_counts.head(10).items()
                    }
                    col_stats["top_values"] = {str(k): int(v) for k, v in value_counts.head(10).items()}
                
                # Check for quality issues
                if col_stats["null_pct"] > 10:
                    quality_issues.append({
                        "table": table_name,
                        "type": "high_nulls",
                        "column": col,
                        "percentage": col_stats["null_pct"]
                    })
                
                if col_stats["cardinality_pct"] == 100 and col != 'id':
                    quality_issues.append({
                        "table": table_name,
                        "type": "all_unique",
                        "column": col,
                        "note": "All values unique - verify if expected"
                    })
                
                table_stats["columns"][col] = col_stats
            
            report["tables"][table_name] = table_stats
            
        except Exception as e:
            report["tables"][table_name] = {"error": str(e)}
    
    # Calculate overall stats and quality score
    total_rows = sum(t.get("row_count", 0) for t in report["tables"].values() if isinstance(t, dict))
    total_columns = sum(t.get("column_count", 0) for t in report["tables"].values() if isinstance(t, dict))
    
    # Calculate quality score (100 - penalty for each issue)
    base_score = 100
    penalty_per_issue = 5
    quality_score = max(0, base_score - len(quality_issues) * penalty_per_issue)
    
    report["summary"] = {
        "total_tables": len(files),
        "total_rows": total_rows,
        "total_columns": total_columns,
        "quality_score": quality_score,
        "issues_count": len(quality_issues),
    }
    
    report["quality_issues"] = quality_issues
    
    return report

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
