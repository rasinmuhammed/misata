"""
Schema Inference Module - Reverse-engineer schemas from sample data.

This module analyzes uploaded CSV/JSON data and infers:
- Column types (int, float, categorical, date, text, email, uuid, etc.)
- Distribution parameters (min, max, mean, std, choices, etc.)
- Correlations between columns
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import numpy as np
import pandas as pd

from misata.schema import Column, SchemaConfig, Table


# ============ Type Detection Patterns ============

EMAIL_PATTERN = re.compile(r'^[\w\.-]+@[\w\.-]+\.\w+$')
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
PHONE_PATTERN = re.compile(r'^[\d\s\-\+\(\)]{7,20}$')
URL_PATTERN = re.compile(r'^https?://')


def detect_column_type(series: pd.Series) -> Tuple[str, Dict[str, Any]]:
    """Detect the type and distribution parameters of a column.
    
    Args:
        series: Pandas Series to analyze
        
    Returns:
        Tuple of (type_name, distribution_params)
    """
    # Drop nulls for analysis
    clean = series.dropna()
    if len(clean) == 0:
        return "text", {"text_type": "sentence"}
    
    # Check for boolean
    unique_vals = set(clean.unique())
    if unique_vals <= {True, False, 0, 1, "true", "false", "True", "False", "yes", "no", "Yes", "No"}:
        # Calculate probability of True
        bool_vals = clean.map(lambda x: str(x).lower() in ('true', '1', 'yes'))
        prob = bool_vals.mean()
        return "boolean", {"probability": round(prob, 2)}
    
    # Check for UUID
    if clean.dtype == object:
        sample = str(clean.iloc[0])
        if UUID_PATTERN.match(sample):
            return "text", {"text_type": "uuid"}
        
        # Check for email
        if EMAIL_PATTERN.match(sample):
            return "text", {"text_type": "email"}
        
        # Check for URL
        if URL_PATTERN.match(sample):
            return "text", {"text_type": "url"}
        
        # Check for phone
        if PHONE_PATTERN.match(sample):
            return "text", {"text_type": "phone"}
    
    # Check for date
    if clean.dtype == 'datetime64[ns]' or pd.api.types.is_datetime64_any_dtype(clean):
        return "date", {
            "start": str(clean.min().date()),
            "end": str(clean.max().date())
        }
    
    # Try parsing as date
    if clean.dtype == object:
        try:
            parsed = pd.to_datetime(clean, errors='coerce')
            if parsed.notna().mean() > 0.9:  # 90%+ parse as dates
                return "date", {
                    "start": str(parsed.min().date()),
                    "end": str(parsed.max().date())
                }
        except:
            pass
    
    # Check for categorical (limited unique values)
    n_unique = clean.nunique()
    if n_unique <= min(20, len(clean) * 0.2):  # <=20 or <=20% unique
        value_counts = clean.value_counts(normalize=True)
        choices = value_counts.index.tolist()
        probabilities = [round(p, 3) for p in value_counts.values.tolist()]
        return "categorical", {
            "choices": choices,
            "probabilities": probabilities
        }
    
    # Check for numeric
    if pd.api.types.is_integer_dtype(clean):
        return "int", {
            "min": int(clean.min()),
            "max": int(clean.max()),
            "distribution": "uniform"
        }
    
    if pd.api.types.is_float_dtype(clean):
        # Check if it looks like currency (2 decimal places)
        decimals = clean.apply(lambda x: len(str(x).split('.')[-1]) if '.' in str(x) else 0)
        if decimals.mode().iloc[0] == 2:
            return "float", {
                "min": round(float(clean.min()), 2),
                "max": round(float(clean.max()), 2),
                "distribution": "lognormal",
                "decimals": 2
            }
        return "float", {
            "min": float(clean.min()),
            "max": float(clean.max()),
            "distribution": "normal",
            "mean": float(clean.mean()),
            "std": float(clean.std())
        }
    
    # Try converting to numeric
    try:
        numeric = pd.to_numeric(clean, errors='coerce')
        if numeric.notna().mean() > 0.9:  # 90%+ are numeric
            if numeric.apply(float.is_integer).all():
                return "int", {
                    "min": int(numeric.min()),
                    "max": int(numeric.max())
                }
            return "float", {
                "min": float(numeric.min()),
                "max": float(numeric.max()),
                "mean": float(numeric.mean()),
                "std": float(numeric.std())
            }
    except:
        pass
    
    # Default to text
    # Try to detect text type from column name
    col_name = series.name.lower() if series.name else ""
    
    if "name" in col_name:
        return "text", {"text_type": "name"}
    elif "email" in col_name:
        return "text", {"text_type": "email"}
    elif "address" in col_name:
        return "text", {"text_type": "address"}
    elif "company" in col_name or "org" in col_name:
        return "text", {"text_type": "company"}
    elif "phone" in col_name:
        return "text", {"text_type": "phone"}
    elif "url" in col_name or "website" in col_name:
        return "text", {"text_type": "url"}
    
    return "text", {"text_type": "sentence"}


def fit_distribution(series: pd.Series) -> Dict[str, Any]:
    """Fit a statistical distribution to numeric data.
    
    Args:
        series: Numeric pandas Series
        
    Returns:
        Distribution parameters including type and fitted params
    """
    clean = pd.to_numeric(series.dropna(), errors='coerce').dropna()
    if len(clean) < 5:
        return {"distribution": "uniform", "min": 0, "max": 100}
    
    mean = float(clean.mean())
    std = float(clean.std())
    min_val = float(clean.min())
    max_val = float(clean.max())
    skew = float(clean.skew())
    
    # Determine best distribution based on characteristics
    if abs(skew) < 0.5:
        # Roughly symmetric → Normal
        return {
            "distribution": "normal",
            "mean": mean,
            "std": std,
            "min": min_val,
            "max": max_val
        }
    elif skew > 1.0 and min_val >= 0:
        # Right-skewed, positive → Lognormal
        return {
            "distribution": "lognormal",
            "mean": np.log(mean) if mean > 0 else 0,
            "sigma": std / mean if mean > 0 else 1,
            "min": min_val,
            "max": max_val
        }
    else:
        # Use empirical (histogram-based)
        hist, bins = np.histogram(clean, bins=20, density=True)
        control_points = []
        for i in range(len(hist)):
            x = (bins[i] + bins[i+1]) / 2
            y = float(hist[i])
            control_points.append({"x": x, "y": y})
        
        return {
            "distribution": "custom",
            "control_points": control_points,
            "min": min_val,
            "max": max_val
        }


def infer_schema(
    data: pd.DataFrame,
    table_name: str = "data",
    row_count: Optional[int] = None
) -> SchemaConfig:
    """Infer a complete schema from sample data.
    
    Args:
        data: Sample DataFrame to analyze
        table_name: Name for the inferred table
        row_count: Target row count (default: 100x input)
        
    Returns:
        SchemaConfig ready for generation
    """
    if row_count is None:
        row_count = max(len(data) * 100, 1000)
    
    columns = []
    for col_name in data.columns:
        col_type, params = detect_column_type(data[col_name])
        
        # Check for unique constraint
        is_unique = data[col_name].nunique() == len(data)
        
        column = Column(
            name=str(col_name),
            table_name=table_name,
            type=col_type,
            distribution_params=params,
            nullable=data[col_name].isna().any(),
            unique=is_unique
        )
        columns.append(column)
    
    return SchemaConfig(
        name=f"Inferred: {table_name}",
        tables=[Table(
            name=table_name,
            row_count=row_count,
            columns=[c.name for c in columns]
        )],
        columns={table_name: columns},
        relationships=[]
    )


def detect_correlations(data: pd.DataFrame) -> List[Dict[str, Any]]:
    """Detect correlations between numeric columns.
    
    Args:
        data: DataFrame to analyze
        
    Returns:
        List of correlation dicts with column pairs and strength
    """
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) < 2:
        return []
    
    correlations = []
    corr_matrix = data[numeric_cols].corr()
    
    for i, col1 in enumerate(numeric_cols):
        for col2 in numeric_cols[i+1:]:
            corr = corr_matrix.loc[col1, col2]
            if abs(corr) > 0.5:  # Only report strong correlations
                correlations.append({
                    "column1": col1,
                    "column2": col2,
                    "correlation": round(corr, 3),
                    "strength": "strong" if abs(corr) > 0.7 else "moderate"
                })
    
    return correlations


def schema_to_dict(schema: SchemaConfig) -> Dict[str, Any]:
    """Convert schema to a JSON-serializable dict for the UI."""
    return {
        "name": schema.name,
        "tables": [
            {
                "name": t.name,
                "row_count": t.row_count,
                "columns": t.columns
            }
            for t in schema.tables
        ],
        "columns": {
            table_name: [
                {
                    "name": c.name,
                    "type": c.type,
                    "params": c.distribution_params,
                    "nullable": c.nullable,
                    "unique": c.unique
                }
                for c in cols
            ]
            for table_name, cols in schema.columns.items()
        }
    }
