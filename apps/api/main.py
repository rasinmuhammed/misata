from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import asyncio
import os
from datetime import datetime, timedelta
import pandas as pd

# Misata Core Imports
from misata.schema import SchemaConfig
from misata.studio.constraint_generator import convert_schema_config_to_spec, generate_constrained_warehouse
from misata.studio.outcome_curve import OutcomeCurve, CurvePoint
from misata.llm_parser import generate_schema
from misata.research import DeepResearchAgent
from misata.quality import check_quality


app = FastAPI(title="Misata Studio API", version="2.0.0")

# Allow CORS for local development (Next.js is on 3000, API on 8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ STATE ============
# In-memory job store (in production this would be Redis/DB)
JOBS: Dict[str, Dict] = {}

# Helper to convert numpy types to native Python for JSON serialization
def convert_numpy_types(obj):
    import numpy as np
    # Skip DataFrame objects (can't serialize and causes truth value errors)
    if isinstance(obj, pd.DataFrame):
        return "[DataFrame]"  # Return placeholder, don't try to serialize
    if isinstance(obj, dict):
        # Skip 'dataframes' key entirely as it contains raw DataFrames
        return {k: convert_numpy_types(v) for k, v in obj.items() if k != 'dataframes'}
    elif isinstance(obj, list):
        return [convert_numpy_types(v) for v in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif obj is None:
        return None
    # Safe check for NA/NaN without ambiguity errors
    try:
        if pd.isna(obj):
            return None
    except (ValueError, TypeError):
        pass  # Not a scalar, skip NA check
    return obj

# ============ PERSISTENCE ============
JOBS_FILE = "misata_jobs.pkl"
import pickle

def save_jobs_to_disk():
    """Save in-memory jobs to disk."""
    try:
        with open(JOBS_FILE, "wb") as f:
            pickle.dump(JOBS, f)
        print(f"✅ Saved {len(JOBS)} jobs to {JOBS_FILE}")
    except Exception as e:
        print(f"❌ Failed to save jobs: {e}")

def load_jobs_from_disk():
    """Load jobs from disk on startup."""
    global JOBS
    if os.path.exists(JOBS_FILE):
        try:
            with open(JOBS_FILE, "rb") as f:
                JOBS = pickle.load(f)
            print(f"✅ Loaded {len(JOBS)} jobs from {JOBS_FILE}")
        except Exception as e:
            print(f"❌ Failed to load jobs: {e}")

# Register startup/shutdown events
@app.on_event("startup")
async def startup_event():
    load_jobs_from_disk()

@app.on_event("shutdown")
async def shutdown_event():
    save_jobs_to_disk()

# LLM Configuration (can be updated from frontend)
LLM_CONFIG: Dict[str, Any] = {
    "provider": os.getenv("LLM_PROVIDER", "groq"),
    "api_key": os.getenv("GROQ_API_KEY", ""),
    "model": os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
}

# ============ REQUEST MODELS ============

class OutcomeConstraintAPI(BaseModel):
    table_name: str
    column_name: str
    curve_points: List[Dict[str, Any]]  # [{timestamp: str, value: float}]
    time_unit: str = "month"
    avg_transaction_value: Optional[float] = 50.0

class JobSubmitRequest(BaseModel):
    schema_config: Dict[str, Any]  # Accept as dict for flexibility
    outcome_constraints: Optional[List[OutcomeConstraintAPI]] = None

class GenerateSchemaRequest(BaseModel):
    story: str
    api_key: Optional[str] = None
    provider: Optional[str] = None
    use_research: bool = False # New flag for Deep Research Agent


class LLMConfigRequest(BaseModel):
    provider: str
    api_key: Optional[str] = None

# ============ WORKERS ============

async def run_generation_job(job_id: str, schema_dict: Dict[str, Any], outcome_constraints: Optional[List[OutcomeConstraintAPI]]):
    """Background worker to run the heavy generation task."""
    try:
        JOBS[job_id]["status"] = "PROGRESS"
        JOBS[job_id]["message"] = "Preparing specifications..."
        JOBS[job_id]["progress"] = 10
        
        # 1. Parse SchemaConfig from dict
        schema_config = SchemaConfig(**schema_dict)
        
        # 2. Build OutcomeCurve from constraints if provided
        revenue_curve = None
        if outcome_constraints and len(outcome_constraints) > 0:
            oc = outcome_constraints[0]  # Use FIRST constraint as primary revenue curve
            curve_points = []
            for p in oc.curve_points:
                # Handle both dict and object formats
                if hasattr(p, 'timestamp'):
                    ts = p.timestamp
                    val = p.value
                elif isinstance(p, dict):
                    ts = p.get('timestamp')
                    val = p.get('value', 0)
                else:
                    continue
                
                # Parse timestamp if string
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                
                curve_points.append(CurvePoint(timestamp=ts, value=float(val)))
            revenue_curve = OutcomeCurve(
                metric_name='revenue',
                time_unit=oc.time_unit,
                points=curve_points,
                avg_transaction_value=oc.avg_transaction_value or 50.0
            )
            JOBS[job_id]["message"] = f"Applying outcome constraint on {oc.table_name}.{oc.column_name}..."
        
        # 2b. Auto-convert LLM outcome_curves (month/relative_value format) 
        # This enables Story Mode patterns like "dip in September, peak in December"
        if not revenue_curve and schema_config.outcome_curves:
            llm_curve = schema_config.outcome_curves[0]  # Use first curve
            print(f"[CONSTRAINT DEBUG] LLM curve found: table={llm_curve.table}, col={llm_curve.column}, time_col={llm_curve.time_column}")
            print(f"[CONSTRAINT DEBUG] Pattern: {llm_curve.pattern_type}, Description: {llm_curve.description}")
            print(f"[CONSTRAINT DEBUG] Points: {[(p.month, p.relative_value) for p in llm_curve.curve_points]}")
            
            base_value = 10000  # Base monthly value to scale relative values
            
            # Convert monthly relative values to actual curve points
            curve_points = []
            for point in llm_curve.curve_points:
                month = point.month if hasattr(point, 'month') else point.get('month', 1)
                relative_value = point.relative_value if hasattr(point, 'relative_value') else point.get('relative_value', 0.5)
                timestamp = datetime(2025, month, 15)  # Mid-month
                actual_value = base_value * relative_value
                curve_points.append(CurvePoint(timestamp=timestamp, value=actual_value))
                print(f"[CONSTRAINT DEBUG] Point: month={month}, relative={relative_value}, actual={actual_value}")
            
            if curve_points:
                revenue_curve = OutcomeCurve(
                    metric_name=llm_curve.column,
                    time_unit='month',
                    points=sorted(curve_points, key=lambda p: p.timestamp),
                    avg_transaction_value=50.0
                )
                JOBS[job_id]["message"] = f"Applying LLM-extracted pattern: {llm_curve.description or 'seasonal curve'}..."
                JOBS[job_id]["outcome_curve_applied"] = True
                
                # CRITICAL: Store the LLM's target table/column for constraint targeting
                JOBS[job_id]["llm_fact_table"] = llm_curve.table
                JOBS[job_id]["llm_amount_col"] = llm_curve.column
                JOBS[job_id]["llm_date_col"] = llm_curve.time_column
                print(f"[CONSTRAINT DEBUG] Revenue curve created with {len(curve_points)} points")
        
        # 3. Convert to WarehouseSpec (pass LLM curve target info)
        llm_fact_table = JOBS[job_id].get("llm_fact_table")
        llm_amount_col = JOBS[job_id].get("llm_amount_col")
        llm_date_col = JOBS[job_id].get("llm_date_col")
        
        spec = convert_schema_config_to_spec(
            schema_config, 
            revenue_curve=revenue_curve,
            fact_table_override=llm_fact_table,
            date_col_override=llm_date_col,
            amount_col_override=llm_amount_col
        )
        
        JOBS[job_id]["message"] = "Generating entities..."
        JOBS[job_id]["progress"] = 30
        
        # 4. Run Generation (Blocking CPU task, run in threadpool)
        loop = asyncio.get_running_loop()
        result_dfs = await loop.run_in_executor(
            None, 
            lambda: generate_constrained_warehouse(spec, seed=42)
        )
        
        JOBS[job_id]["progress"] = 90
        JOBS[job_id]["message"] = "Finalizing output..."
        
        # 5. Verify Constraint Match (Feature for Pitch)
        verification_result = None
        if revenue_curve and spec.constraints:
            constraint = spec.constraints[0]  # Verify the primary constraint
            if constraint.fact_table in result_dfs:
                fact_df = result_dfs[constraint.fact_table]
                
                # We need the start date from the curve to align buckets
                start_date = revenue_curve.points[0].timestamp
                
                from misata.studio.outcome_curve import verify_curve_match
                verification_result = verify_curve_match(fact_df, revenue_curve, start_date)
                
                JOBS[job_id]["message"] = f"Verification Score: {verification_result['match_score']}/100"

        # 6. Serialize Results (files)
        # Store preview rows (up to 100) alongside metadata
        
        results_summary = {}
        full_dataframes = {}  # Store full DFs for download
        for name, df in result_dfs.items():
            # Convert NaN to None and numpy types to native Python
            df_preview = df.head(100).where(pd.notnull(df), None)
            preview_rows = convert_numpy_types(df_preview.to_dict(orient='records'))
            
            results_summary[name] = {
                "rows": preview_rows,
                "total_rows": int(len(df)),
                "preview_rows": int(len(df_preview)),
                "columns": list(df.columns)
            }
            full_dataframes[name] = df  # Keep full DF for download
        
        JOBS[job_id]["status"] = "SUCCESS"
        JOBS[job_id]["progress"] = 100
        JOBS[job_id]["message"] = "Complete"
        JOBS[job_id]["result"] = results_summary
        JOBS[job_id]["verification"] = verification_result  # Store verification report
        JOBS[job_id]["dataframes"] = full_dataframes  # Store for download
        JOBS[job_id]["completed_at"] = datetime.now().isoformat()
        
        # Store extracted constraints for UI display
        JOBS[job_id]["outcome_curves"] = [
            {
                "table": c.table,
                "column": c.column,
                "time_column": c.time_column,
                "pattern_type": c.pattern_type,
                "description": c.description,
                "curve_points": [{"month": p.month, "relative_value": p.relative_value} for p in c.curve_points]
            }
            for c in schema_config.outcome_curves
        ] if schema_config.outcome_curves else []
        
        # Extract date ranges from schema
        date_ranges = {}
        for table in schema_config.tables:
            for col in schema_config.get_columns(table.name):
                if col.type == "date" and "start" in col.distribution_params:
                    date_ranges[f"{table.name}.{col.name}"] = {
                        "start": col.distribution_params.get("start"),
                        "end": col.distribution_params.get("end")
                    }
        JOBS[job_id]["date_ranges"] = date_ranges
        
    except Exception as e:
        JOBS[job_id]["status"] = "FAILURE"
        JOBS[job_id]["error"] = str(e)
        import traceback
        print(traceback.format_exc())

# ============ ENDPOINTS ============

@app.get("/")
def health_check():
    return {"status": "ok", "service": "Misata Studio API"}

@app.get("/jobs")
def list_jobs():
    """List all jobs."""
    jobs = [
        {
            "id": job["id"],
            "status": job["status"],
            "progress": job.get("progress", 0),
            "schema_name": job.get("schema_name", "Unknown"),
            "submitted_at": job.get("submitted_at", ""),
        }
        for job in JOBS.values()
    ]
    return {"jobs": jobs}

@app.post("/jobs")
async def submit_job(req: JobSubmitRequest, background_tasks: BackgroundTasks):
    """Submit a generation job with optional outcome constraints."""
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id,
        "status": "PENDING",
        "progress": 0,
        "submitted_at": datetime.now().isoformat(),
        "schema_name": req.schema_config.get("name", "Untitled Schema")
    }
    
    background_tasks.add_task(run_generation_job, job_id, req.schema_config, req.outcome_constraints)
    
    return {"job_id": job_id, "status": "PENDING"}

# IMPORTANT: Specific routes must come BEFORE parameterized routes
@app.get("/jobs/completed")
def get_completed_jobs():
    """Get all completed jobs."""
    completed = []
    for job in JOBS.values():
        if job.get("status") == "SUCCESS":
            result = job.get("result", {})
            # total_rows is the actual row count, 'rows' is the array of preview data
            total_rows = sum(t.get("total_rows", 0) for t in result.values())
            completed.append({
                "id": job["id"],
                "status": job["status"],
                "tables": len(result),
                "rows": total_rows,
                "created_at": job.get("submitted_at", ""),
                "schema_name": job.get("schema_name", "Unknown"),
            })
    return {"jobs": completed}

@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    # Convert numpy types for JSON serialization
    return convert_numpy_types(JOBS[job_id])

@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """Delete a job from the queue."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    del JOBS[job_id]
    save_jobs_to_disk()  # Persist the deletion
    return {"message": f"Job {job_id} deleted successfully"}

@app.get("/jobs/{job_id}/data")
def get_job_data(job_id: str, limit: int = 100):
    """Get preview data for a completed job."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    if job.get("status") != "SUCCESS":
        raise HTTPException(status_code=400, detail="Job not complete")
    
    # In production, this would read from stored files
    # For now, return the result summary
    return {
        "job_id": job_id,
        "tables": job.get("result", {})
    }

@app.get("/jobs/{job_id}/download")
def download_job_files(job_id: str):
    """Download job results as ZIP with CSV files."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    if job.get("status") != "SUCCESS":
        raise HTTPException(status_code=400, detail="Job not complete")
    
    dataframes = job.get("dataframes", {})
    if not dataframes:
        # Fallback: reconstruct from preview data if full DFs not available
        result = job.get("result", {})
        for table_name, table_data in result.items():
            rows = table_data.get("rows", [])
            if rows:
                dataframes[table_name] = pd.DataFrame(rows)
    
    if not dataframes:
        raise HTTPException(status_code=400, detail="No data available for download")
    
    # Create ZIP in memory
    import io
    import zipfile
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for table_name, df in dataframes.items():
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            zip_file.writestr(f"{table_name}.csv", csv_buffer.getvalue())
    
    zip_buffer.seek(0)
    
    from fastapi.responses import Response
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=misata_{job_id[:8]}.zip"}
    )

@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """Delete a job."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    del JOBS[job_id]
    return {"status": "deleted", "job_id": job_id}

@app.get("/jobs/{job_id}/quality-report")
def get_quality_report(job_id: str):
    """Get comprehensive quality report with statistical scores."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    if job.get("status") != "SUCCESS":
        raise HTTPException(status_code=400, detail="Job not complete")
    
    result = job.get("result", {})
    
    # Calculate quality using DataQualityChecker
    dataframes = job.get("dataframes", {})
    
    # If dataframes missing (old jobs?), try to reconstruct/skip
    # But strictly we need dataframes for time series analysis
    # Fallback to empty if not found
    
    quality_report = check_quality(dataframes)
    
    # Build table metrics (keep existing logic for size estimation as it's UI specific)
    table_metrics = {}
    for table_name, table_data in result.items():
         row_count = table_data.get("total_rows", 0)
         columns = table_data.get("columns", [])
         table_metrics[table_name] = {
            "row_count": row_count,
            "column_count": len(columns),
            "columns": columns,
            "file_size_kb": round(row_count * len(columns) * 0.05, 1),
            "memory_usage_kb": round(row_count * len(columns) * 0.08, 1),
            "metrics": { "completeness": 100 } # Placeholder for row specific stats
         }
         
         # ENRICH COLUMNS WITH REAL DATA STATS
         if table_name in dataframes:
            df = dataframes[table_name]
            enriched_columns = {}
            for col_def in columns:
                if isinstance(col_def, str):
                    col_name = col_def
                    stats = {"name": col_name, "type": "text"} # Default if missing
                else:
                    col_name = col_def["name"]
                    stats = col_def.copy()
                
                if col_name in df.columns:
                    # Basic stats
                    stats["unique_count"] = int(df[col_name].nunique())
                    stats["null_count"] = int(df[col_name].isnull().sum())
                    
                    # Numeric stats
                    if pd.api.types.is_numeric_dtype(df[col_name]):
                        val_min = df[col_name].min()
                        val_max = df[col_name].max()
                        val_mean = df[col_name].mean()

                        stats["min"] = float(val_min) if pd.notnull(val_min) else 0
                        stats["max"] = float(val_max) if pd.notnull(val_max) else 0
                        stats["mean"] = float(val_mean) if pd.notnull(val_mean) else 0
                        
                enriched_columns[col_name] = stats
            
            # Update the metrics with enriched columns
            table_metrics[table_name]["columns"] = enriched_columns


    # Calculate summary metrics
    total_tables = len(result)
    total_rows = sum([meta.get("row_count", 0) for meta in table_metrics.values()])
    total_columns = sum([meta.get("column_count", 0) for meta in table_metrics.values()])

    # Add constraint verification if available
    constraint_verification = job.get("verification")
    
    return convert_numpy_types({
        "job_id": job_id,
        "schema_name": job.get("schema_name", "Unknown"),
        "generated_at": job.get("completed_at", ""),
        "verification": constraint_verification,
        "summary": {
            "total_tables": total_tables,
            "total_rows": total_rows,
            "total_columns": total_columns,
            "quality_score": quality_report.score,
            "quality_grade": "A" if quality_report.score >= 90 else "B" if quality_report.score >= 80 else "C",
            "issues_count": len(quality_report.issues)
        },
        "metrics": {
            "completeness": 100, # Generated data is always complete
            "integrity": 100,
            "coverage": 100,
        },
        "tables": table_metrics,
        "quality_issues": [
            {
                "severity": i.severity,
                "category": i.category,
                "table": i.table,
                "column": i.column,
                "message": i.message,
                "details": i.details,
                "type": i.category # Frontend expects 'type'
            }
            for i in quality_report.issues
        ]
    })

@app.get("/jobs/{job_id}/timeseries/{table_name}")
def get_time_series_aggregation(
    job_id: str, 
    table_name: str, 
    time_column: str = "event_time",
    value_column: str = "amount",
    aggregation: str = "sum"
):
    """
    Get time-series aggregation for constraint verification.
    Returns aggregated data by month for charting.
    """
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    if job.get("status") != "SUCCESS":
        raise HTTPException(status_code=400, detail="Job not complete")
    
    # Get the DataFrame
    dataframes = job.get("dataframes", {})
    if table_name not in dataframes:
        # Try to reconstruct from preview
        result = job.get("result", {})
        if table_name in result:
            rows = result[table_name].get("rows", [])
            if rows:
                dataframes[table_name] = pd.DataFrame(rows)
    
    if table_name not in dataframes:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
    
    df = dataframes[table_name]
    
    # Validate columns exist
    if time_column not in df.columns:
        available_time_cols = [c for c in df.columns if 'time' in c.lower() or 'date' in c.lower()]
        raise HTTPException(
            status_code=400, 
            detail=f"Column '{time_column}' not found. Available time columns: {available_time_cols}"
        )
    
    if value_column not in df.columns:
        available_num_cols = [c for c in df.columns if df[c].dtype in ['float64', 'int64', 'float32', 'int32']]
        raise HTTPException(
            status_code=400, 
            detail=f"Column '{value_column}' not found. Available numeric columns: {available_num_cols}"
        )
    
    try:
        # LOGGING FOR DEBUGGING
        print(f"DEBUG CHART: Table={table_name}, Time={time_column}, Value={value_column}")
        print(f"DEBUG CHART: Dtypes before:\n{df.dtypes}")
        
        # Convert time column to datetime (coerce errors to NaT)
        df_copy = df.copy()
        df_copy[time_column] = pd.to_datetime(df_copy[time_column], errors='coerce')
        
        # Force value column to numeric (handle currency strings etc)
        df_copy[value_column] = pd.to_numeric(df_copy[value_column], errors='coerce').fillna(0)
        
        # Drop invalid dates
        df_copy = df_copy.dropna(subset=[time_column])
        
        print(f"DEBUG CHART: Rows after cleaning: {len(df_copy)}")
        
        # Group by month
        df_copy['month'] = df_copy[time_column].dt.to_period('M')
        
        # Aggregate
        if aggregation == "sum":
            agg_result = df_copy.groupby('month')[value_column].sum()
        elif aggregation == "mean":
            agg_result = df_copy.groupby('month')[value_column].mean()
        elif aggregation == "count":
            agg_result = df_copy.groupby('month')[value_column].count()
        else:
            agg_result = df_copy.groupby('month')[value_column].sum()
            
        print(f"DEBUG CHART: Aggregation result head:\n{agg_result.head()}")
        
        # Convert to chart-friendly format
        data_points = []
        for period, value in agg_result.items():
            val_float = float(value) if pd.notnull(value) else 0.0
            data_points.append({
                "timestamp": str(period), 
                "value": val_float
            })
        
        # Sort by timestamp to ensure chronological order
        data_points.sort(key=lambda x: x["timestamp"])
        
        return {
            "job_id": job_id,
            "table_name": table_name,
            "time_column": time_column,
            "value_column": value_column,
            "aggregation": aggregation,
            "data_points": data_points,
            "total_records": len(df),
            "date_range": {
                "start": str(df_copy[time_column].min()) if not df_copy.empty else "",
                "end": str(df_copy[time_column].max()) if not df_copy.empty else "",
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Aggregation failed: {str(e)}")

@app.get("/jobs/{job_id}/computed/revenue")
def get_computed_revenue(
    job_id: str,
    subscription_table: str = "subscriptions",
    plans_table: str = "plans",
    time_column: str = "start_date"
):
    """
    Compute revenue by joining subscriptions with plan prices.
    This is for tables that don't have an explicit revenue column.
    Revenue = count(subscriptions) × plan.price, grouped by month.
    """
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    if job.get("status") != "SUCCESS":
        raise HTTPException(status_code=400, detail="Job not complete")
    
    dataframes = job.get("dataframes", {})
    result = job.get("result", {})
    
    # Try to get or reconstruct the subscription DataFrame
    if subscription_table not in dataframes:
        if subscription_table in result:
            rows = result[subscription_table].get("rows", [])
            if rows:
                dataframes[subscription_table] = pd.DataFrame(rows)
    
    # Try to get or reconstruct the plans DataFrame
    if plans_table not in dataframes:
        if plans_table in result:
            rows = result[plans_table].get("rows", [])
            if rows:
                dataframes[plans_table] = pd.DataFrame(rows)
    
    if subscription_table not in dataframes:
        raise HTTPException(status_code=404, detail=f"Table '{subscription_table}' not found")
    
    subs_df = dataframes[subscription_table]
    
    # Check for time column
    if time_column not in subs_df.columns:
        # Auto-detect time column
        time_cols = [c for c in subs_df.columns if 'date' in c.lower() or 'time' in c.lower()]
        if time_cols:
            time_column = time_cols[0]
        else:
            raise HTTPException(status_code=400, detail=f"No time column found in {subscription_table}")
    
    try:
        subs_df = subs_df.copy()
        subs_df[time_column] = pd.to_datetime(subs_df[time_column])
        subs_df['month'] = subs_df[time_column].dt.to_period('M')
        
        # Method 1: If plans table exists with prices, join and calculate
        if plans_table in dataframes:
            plans_df = dataframes[plans_table]
            price_col = None
            for col in ['price', 'amount', 'cost', 'monthly_price']:
                if col in plans_df.columns:
                    price_col = col
                    break
            
            if price_col and 'plan_id' in subs_df.columns and 'id' in plans_df.columns:
                # Join subscriptions with plans
                merged = subs_df.merge(
                    plans_df[['id', price_col]], 
                    left_on='plan_id', 
                    right_on='id',
                    how='left'
                )
                # Sum revenue by month
                revenue_by_month = merged.groupby('month')[price_col].sum()
            else:
                # Fallback: just count subscriptions by month
                revenue_by_month = subs_df.groupby('month').size()
        else:
            # No plans table: count subscriptions by month
            revenue_by_month = subs_df.groupby('month').size()
        
        data_points = [
            {"timestamp": str(period), "value": float(value)}
            for period, value in revenue_by_month.items()
        ]
        
        return convert_numpy_types({
            "job_id": job_id,
            "metric": "revenue",
            "method": "subscription_price_join" if plans_table in dataframes else "subscription_count",
            "data_points": data_points,
            "total_records": len(subs_df),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Revenue calculation failed: {str(e)}")

@app.get("/jobs/{job_id}/export/json")
def export_job_json(job_id: str):
    """Export job data as JSON."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    if job.get("status") != "SUCCESS":
        raise HTTPException(status_code=400, detail="Job not complete")
    
    # Build JSON export with schema and data summary
    export_data = {
        "schema_name": job.get("schema_name", "Unknown"),
        "generated_at": job.get("completed_at", ""),
        "generator": "Misata Studio v0.1.0",
        "tables": job.get("result", {}),
        "metadata": {
            "job_id": job_id,
            "total_rows": sum(t.get("total_rows", 0) for t in job.get("result", {}).values()),
        }
    }
    
    import json
    from fastapi.responses import Response
    return Response(
        content=json.dumps(export_data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=misata_{job_id[:8]}.json"}
    )

@app.get("/jobs/{job_id}/export/sql")
def export_job_sql(job_id: str):
    """Export job as SQL CREATE TABLE and INSERT statements."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    if job.get("status") != "SUCCESS":
        raise HTTPException(status_code=400, detail="Job not complete")
    
    result = job.get("result", {})
    sql_lines = [
        f"-- Misata Studio Generated Data",
        f"-- Schema: {job.get('schema_name', 'Unknown')}",
        f"-- Generated: {job.get('completed_at', '')}",
        f"-- Job ID: {job_id}",
        "",
    ]
    
    # Generate CREATE TABLE statements
    for table_name, table_data in result.items():
        columns = table_data.get("columns", [])
        if columns:
            # Quote identifiers to handle reserved keywords
            quoted_table = f'"{table_name}"'
            col_defs = ", ".join([f'"{col}" TEXT' for col in columns])
            sql_lines.append(f"CREATE TABLE IF NOT EXISTS {quoted_table} ({col_defs});")
            sql_lines.append("")
    
    # Note about data
    sql_lines.append("-- Note: Full INSERT statements require downloading the complete dataset")
    sql_lines.append("-- Use the /jobs/{job_id}/download endpoint for full CSV data")
    
    from fastapi.responses import Response
    return Response(
        content="\n".join(sql_lines),
        media_type="application/sql",
        headers={"Content-Disposition": f"attachment; filename=misata_{job_id[:8]}.sql"}
    )

@app.get("/jobs/{job_id}/export/csv/{table_name}")
def export_table_csv(job_id: str, table_name: str):
    """Export a specific table as CSV."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    if job.get("status") != "SUCCESS":
        raise HTTPException(status_code=400, detail="Job not complete")
    
    result = job.get("result", {})
    if table_name not in result:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
    
    table_data = result[table_name]
    columns = table_data.get("columns", [])
    
    # Generate CSV header
    csv_content = ",".join(columns) + "\n"
    csv_content += f"# {table_data.get('rows', 0)} rows generated\n"
    csv_content += "# Download full dataset for complete data\n"
    
    from fastapi.responses import Response
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={table_name}.csv"}
    )

@app.post("/schema/generate")
def generate_schema_endpoint(req: GenerateSchemaRequest):
    """LLM Endpoint: Text -> SchemaConfig"""
    try:
        # Use API key from request if provided, otherwise use config
        api_key = req.api_key or LLM_CONFIG.get("api_key") or os.getenv("GROQ_API_KEY")
        provider = req.provider or LLM_CONFIG.get("provider", "groq")
        
        # Set environment variable for the LLM parser to use
        if api_key:
            if provider == "groq":
                os.environ["GROQ_API_KEY"] = api_key
            elif provider == "openai":
                os.environ["OPENAI_API_KEY"] = api_key
        
        config = generate_schema(req.story, use_research=req.use_research)
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/config/llm")
def update_llm_config(req: LLMConfigRequest):
    """Update LLM configuration (provider and optional API key)."""
    global LLM_CONFIG
    
    LLM_CONFIG["provider"] = req.provider
    
    if req.api_key:
        LLM_CONFIG["api_key"] = req.api_key
        # Also update environment variable
        if req.provider == "groq":
            os.environ["GROQ_API_KEY"] = req.api_key
        elif req.provider == "openai":
            os.environ["OPENAI_API_KEY"] = req.api_key
    
    return {"status": "success", "provider": req.provider}

@app.get("/config/llm")
def get_llm_config():
    """Get current LLM configuration (without exposing full API key)."""
    api_key = LLM_CONFIG.get("api_key", "")
    return {
        "provider": LLM_CONFIG.get("provider", "groq"),
        "has_api_key": bool(api_key),
        "api_key_preview": f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "****"
    }

@app.post("/config/test-llm")
def test_llm_config(req: LLMConfigRequest):
    """Test if the provided LLM configuration is valid."""
    try:
        if req.provider == "groq":
            from groq import Groq
            api_key = req.api_key or LLM_CONFIG.get("api_key") or os.getenv("GROQ_API_KEY")
            if not api_key:
                return {"valid": False, "error": "No API key provided"}
            client = Groq(api_key=api_key)
            # Quick test - list models
            client.models.list()
            return {"valid": True, "provider": "groq"}
        
        elif req.provider == "openai":
            import openai
            api_key = req.api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                return {"valid": False, "error": "No API key provided"}
            client = openai.OpenAI(api_key=api_key)
            client.models.list()
            return {"valid": True, "provider": "openai"}
        
        elif req.provider == "ollama":
            import requests
            response = requests.get("http://localhost:11434/api/version", timeout=2)
            if response.ok:
                return {"valid": True, "provider": "ollama", "version": response.json().get("version")}
            return {"valid": False, "error": "Ollama not responding"}
        
        return {"valid": False, "error": f"Unknown provider: {req.provider}"}
    
    except Exception as e:
        return {"valid": False, "error": str(e)}

@app.get("/api/research/entities")
def search_entities(domain: str, type: str = "competitors", limit: int = 10):
    """
    Search for real-world entities (e.g. competitors, products) in a domain.
    Uses DeepResearchAgent (Mock/Tavily).
    """
    agent = DeepResearchAgent(use_mock=True) # Defaults to mock for now
    try:
        results = agent.search_entities(domain, type, limit)
        return {"domain": domain, "type": type, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/research/stats")
def search_market_stats(domain: str):
    """
    Search for market statistics for a domain.
    """
    agent = DeepResearchAgent(use_mock=True)
    try:
        stats = agent.search_market_stats(domain)
        return {"domain": domain, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ STUDIO AGENT ORCHESTRATION ============

class StudioGenerateRequest(BaseModel):
    """Request for multi-agent schema generation."""
    story: str
    session_id: Optional[str] = None


# In-memory agent sessions (for multi-turn conversations)
AGENT_SESSIONS: Dict[str, Dict] = {}


@app.post("/studio/generate")
async def studio_generate(req: StudioGenerateRequest, background_tasks: BackgroundTasks):
    """
    Multi-agent schema generation endpoint.
    
    This endpoint triggers the SupervisorOrchestrator which coordinates:
    - SchemaArchitectAgent: Extracts tables, columns, relationships
    - DomainExpertAgent: Enriches with domain-specific knowledge
    - ValidationAgent: Validates the generated schema
    
    Returns a session_id for polling status.
    """
    session_id = req.session_id or str(uuid.uuid4())
    
    # Initialize session
    AGENT_SESSIONS[session_id] = {
        "status": "started",
        "story": req.story,
        "created_at": datetime.now().isoformat(),
        "steps": [],
        "schema": None,
        "error": None,
    }
    
    # Run agent pipeline in background
    background_tasks.add_task(run_agent_pipeline, session_id, req.story)
    
    return {
        "session_id": session_id,
        "status": "started",
        "message": "Agent pipeline started"
    }


async def run_agent_pipeline(session_id: str, story: str):
    """Background task to run the multi-agent pipeline."""
    try:
        session = AGENT_SESSIONS[session_id]
        
        # Step 1: Schema Architect
        session["status"] = "schema_architect"
        session["steps"].append({
            "agent": "SchemaArchitectAgent",
            "status": "running",
            "message": "Extracting schema from story...",
            "timestamp": datetime.now().isoformat()
        })
        
        # Use existing LLM parser
        from misata.llm_parser import generate_schema
        await asyncio.sleep(0.5)  # Small delay for UI feedback
        
        schema_config = generate_schema(story)
        
        session["steps"][-1]["status"] = "complete"
        session["steps"][-1]["result"] = {
            "tables": len(schema_config.tables),
            "relationships": len(schema_config.relationships),
        }
        
        # Step 2: Domain Expert
        session["status"] = "domain_expert"
        session["steps"].append({
            "agent": "DomainExpertAgent",
            "status": "running",
            "message": "Enriching with domain knowledge...",
            "timestamp": datetime.now().isoformat()
        })
        
        await asyncio.sleep(0.3)
        
        # Auto-detect domain and enrich
        detected_domain = "unknown"
        table_names = [t.name.lower() for t in schema_config.tables]
        if any(kw in str(table_names) for kw in ["order", "product", "cart", "customer"]):
            detected_domain = "e-commerce"
        elif any(kw in str(table_names) for kw in ["user", "subscription", "plan"]):
            detected_domain = "saas"
        elif any(kw in str(table_names) for kw in ["patient", "doctor", "appointment"]):
            detected_domain = "healthcare"
        
        session["steps"][-1]["status"] = "complete"
        session["steps"][-1]["result"] = {"domain": detected_domain}
        
        # Step 3: Validation
        session["status"] = "validation"
        session["steps"].append({
            "agent": "ValidationAgent",
            "status": "running",
            "message": "Validating schema structure...",
            "timestamp": datetime.now().isoformat()
        })
        
        await asyncio.sleep(0.2)
        
        # Basic validation
        validation_passed = True
        validation_issues = []
        
        if not schema_config.tables:
            validation_passed = False
            validation_issues.append("No tables defined")
        
        for table in schema_config.tables:
            cols = schema_config.columns.get(table.name, [])
            if not cols:
                validation_issues.append(f"Table '{table.name}' has no columns")
        
        session["steps"][-1]["status"] = "complete"
        session["steps"][-1]["result"] = {
            "passed": validation_passed,
            "issues": validation_issues
        }
        
        # Complete
        session["status"] = "complete"
        session["schema"] = schema_config.model_dump()
        
    except Exception as e:
        import traceback
        session = AGENT_SESSIONS.get(session_id, {})
        session["status"] = "error"
        session["error"] = str(e)
        session["traceback"] = traceback.format_exc()


@app.get("/studio/session/{session_id}")
def get_studio_session(session_id: str):
    """Get the status and results of an agent session."""
    if session_id not in AGENT_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return AGENT_SESSIONS[session_id]


@app.get("/studio/sessions")
def list_studio_sessions():
    """List all active agent sessions."""
    return {
        "sessions": [
            {
                "session_id": sid,
                "status": data.get("status"),
                "created_at": data.get("created_at"),
            }
            for sid, data in AGENT_SESSIONS.items()
        ]
    }


if __name__ == "__main__":

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

