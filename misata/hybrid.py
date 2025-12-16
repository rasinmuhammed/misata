"""
Hybrid Learning Module for Misata.

This module provides:
- Learn distributions from sample real data
- Combine LLM schema generation with statistical learning
- Detect and replicate correlation patterns

This addresses the critic's concern: "If user HAS data, learn from it"
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class LearnedDistribution:
    """A distribution learned from real data."""
    column_name: str
    dtype: str
    distribution_type: str
    parameters: Dict[str, Any]
    sample_stats: Dict[str, float]

    def to_schema_params(self) -> Dict[str, Any]:
        """Convert to Misata schema distribution_params."""
        return {
            "distribution": self.distribution_type,
            **self.parameters
        }


@dataclass
class LearnedCorrelation:
    """A correlation learned between columns."""
    column1: str
    column2: str
    correlation: float
    relationship_type: str  # linear, monotonic, categorical
    strength: str  # weak, moderate, strong


class DistributionLearner:
    """
    Learn distributions from sample data.

    Analyzes real data to:
    1. Detect best-fit distributions
    2. Extract parameters
    3. Identify correlations
    """

    def __init__(self):
        self.distributions: Dict[str, LearnedDistribution] = {}
        self.correlations: List[LearnedCorrelation] = []

    def fit(self, df: pd.DataFrame, table_name: str = "data") -> Dict[str, Any]:
        """
        Learn from a DataFrame.

        Args:
            df: Sample data to learn from
            table_name: Name for the learned table

        Returns:
            Schema configuration matching the learned patterns
        """
        columns = []

        for col_name in df.columns:
            col_data = df[col_name]
            learned = self._learn_column(col_name, col_data)

            if learned:
                self.distributions[f"{table_name}.{col_name}"] = learned
                columns.append({
                    "name": col_name,
                    "type": learned.dtype,
                    "distribution_params": learned.to_schema_params()
                })

        # Learn correlations
        self._learn_correlations(df, table_name)

        return {
            "tables": [{"name": table_name, "row_count": len(df)}],
            "columns": {table_name: columns},
            "relationships": [],
            "events": []
        }

    def _learn_column(self, name: str, data: pd.Series) -> Optional[LearnedDistribution]:
        """Learn distribution for a single column."""
        # Skip if mostly null
        if data.isna().mean() > 0.5:
            return None

        data = data.dropna()

        if len(data) < 10:
            return None

        # Detect dtype and appropriate distribution
        if pd.api.types.is_numeric_dtype(data):
            return self._learn_numeric(name, data)
        elif pd.api.types.is_datetime64_any_dtype(data):
            return self._learn_datetime(name, data)
        else:
            return self._learn_categorical(name, data)

    def _learn_numeric(self, name: str, data: pd.Series) -> LearnedDistribution:
        """Learn distribution for numeric column."""
        values = data.values.astype(float)

        # Calculate basic stats
        mean = float(np.mean(values))
        std = float(np.std(values))
        min_val = float(np.min(values))
        max_val = float(np.max(values))
        skewness = float(stats.skew(values))

        # Test for different distributions
        distributions_to_test = [
            ('normal', lambda: stats.kstest(values, 'norm', args=(mean, std))),
            ('uniform', lambda: stats.kstest(values, 'uniform', args=(min_val, max_val - min_val))),
            ('exponential', lambda: stats.kstest(values[values > 0], 'expon') if (values > 0).all() else (1.0, 0.0)),
        ]

        best_dist = 'normal'
        best_p = 0

        for dist_name, test_func in distributions_to_test:
            try:
                stat, p = test_func()
                if p > best_p:
                    best_p = p
                    best_dist = dist_name
            except Exception:
                continue

        # Build parameters based on best distribution
        if best_dist == 'normal':
            params = {"mean": round(mean, 2), "std": round(std, 2)}
        elif best_dist == 'uniform':
            params = {"min": round(min_val, 2), "max": round(max_val, 2)}
        elif best_dist == 'exponential':
            scale = float(np.mean(values))
            params = {"scale": round(scale, 2)}
        else:
            params = {"mean": round(mean, 2), "std": round(std, 2)}

        # Determine if int or float
        is_int = np.allclose(values, np.round(values))
        dtype = "int" if is_int else "float"

        return LearnedDistribution(
            column_name=name,
            dtype=dtype,
            distribution_type=best_dist,
            parameters=params,
            sample_stats={
                "mean": mean,
                "std": std,
                "min": min_val,
                "max": max_val,
                "skewness": skewness
            }
        )

    def _learn_datetime(self, name: str, data: pd.Series) -> LearnedDistribution:
        """Learn distribution for datetime column."""
        min_date = data.min()
        max_date = data.max()

        return LearnedDistribution(
            column_name=name,
            dtype="date",
            distribution_type="uniform",
            parameters={
                "start": str(min_date.date()) if hasattr(min_date, 'date') else str(min_date),
                "end": str(max_date.date()) if hasattr(max_date, 'date') else str(max_date)
            },
            sample_stats={
                "count": len(data),
                "range_days": (max_date - min_date).days if hasattr(max_date - min_date, 'days') else 0
            }
        )

    def _learn_categorical(self, name: str, data: pd.Series) -> LearnedDistribution:
        """Learn distribution for categorical column."""
        value_counts = data.value_counts(normalize=True)

        # If too many unique values, might be text
        if len(value_counts) > 50:
            # Detect if it's an email, name, etc.
            sample = str(data.iloc[0]).lower()
            if '@' in sample:
                return LearnedDistribution(
                    column_name=name,
                    dtype="text",
                    distribution_type="pattern",
                    parameters={"text_type": "email"},
                    sample_stats={"unique_count": len(value_counts)}
                )
            else:
                return LearnedDistribution(
                    column_name=name,
                    dtype="text",
                    distribution_type="pattern",
                    parameters={"text_type": "word"},
                    sample_stats={"unique_count": len(value_counts)}
                )

        choices = list(value_counts.index[:20])  # Top 20
        probs = list(value_counts.values[:20])

        # Normalize probabilities
        total = sum(probs)
        probs = [p / total for p in probs]

        return LearnedDistribution(
            column_name=name,
            dtype="categorical",
            distribution_type="categorical",
            parameters={
                "choices": choices,
                "probabilities": [round(p, 3) for p in probs]
            },
            sample_stats={
                "unique_count": len(value_counts),
                "top_value": choices[0] if choices else None,
                "entropy": float(stats.entropy(probs))
            }
        )

    def _learn_correlations(self, df: pd.DataFrame, table_name: str):
        """Learn correlations between numeric columns."""
        numeric_cols = df.select_dtypes(include=[np.number]).columns

        if len(numeric_cols) < 2:
            return

        for i, col1 in enumerate(numeric_cols):
            for col2 in numeric_cols[i+1:]:
                try:
                    corr, p_value = stats.pearsonr(
                        df[col1].dropna(),
                        df[col2].dropna()
                    )

                    if abs(corr) > 0.3:  # Non-trivial correlation
                        strength = (
                            "strong" if abs(corr) > 0.7 else
                            "moderate" if abs(corr) > 0.5 else
                            "weak"
                        )

                        self.correlations.append(LearnedCorrelation(
                            column1=col1,
                            column2=col2,
                            correlation=round(corr, 3),
                            relationship_type="linear",
                            strength=strength
                        ))
                except Exception:
                    continue

    def get_correlation_report(self) -> str:
        """Get human-readable correlation report."""
        if not self.correlations:
            return "No significant correlations detected."

        lines = ["Detected Correlations:", "-" * 40]

        for corr in sorted(self.correlations, key=lambda x: abs(x.correlation), reverse=True):
            direction = "positive" if corr.correlation > 0 else "negative"
            lines.append(
                f"  {corr.column1} ↔ {corr.column2}: "
                f"{corr.correlation:+.3f} ({corr.strength} {direction})"
            )

        return "\n".join(lines)


class HybridSchemaGenerator:
    """
    Combines LLM generation with statistical learning.

    If user provides sample data:
    1. Learn distributions from sample
    2. Use LLM for schema structure
    3. Override LLM params with learned params
    """

    def __init__(self):
        self.learner = DistributionLearner()
        self.learned_schema: Optional[Dict] = None

    def learn_from_sample(self, sample_data: Dict[str, pd.DataFrame]):
        """
        Learn from sample data.

        Args:
            sample_data: Dict of table_name -> DataFrame
        """
        combined_schema = {
            "tables": [],
            "columns": {},
            "relationships": [],
            "events": []
        }

        for table_name, df in sample_data.items():
            learned = self.learner.fit(df, table_name)
            combined_schema["tables"].extend(learned["tables"])
            combined_schema["columns"].update(learned["columns"])

        self.learned_schema = combined_schema

    def enhance_llm_schema(self, llm_schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance LLM-generated schema with learned patterns.

        Args:
            llm_schema: Schema from LLM

        Returns:
            Enhanced schema with learned distributions
        """
        if not self.learned_schema:
            return llm_schema

        enhanced = json.loads(json.dumps(llm_schema))  # Deep copy

        # Override columns with learned distributions
        for table_name, learned_cols in self.learned_schema["columns"].items():
            if table_name in enhanced.get("columns", {}):
                for learned_col in learned_cols:
                    col_name = learned_col["name"]

                    # Find matching column in LLM schema
                    for i, llm_col in enumerate(enhanced["columns"][table_name]):
                        if llm_col["name"] == col_name:
                            # Keep LLM structure, use learned params
                            enhanced["columns"][table_name][i]["distribution_params"] = \
                                learned_col["distribution_params"]
                            break

        return enhanced

    def generate_schema_from_csv(self, csv_path: str) -> Dict[str, Any]:
        """
        Generate schema from a CSV file.

        Args:
            csv_path: Path to CSV file

        Returns:
            Complete schema configuration
        """
        df = pd.read_csv(csv_path)
        table_name = csv_path.split("/")[-1].replace(".csv", "")

        return self.learner.fit(df, table_name)


# Convenience function for CLI
def learn_from_csv(csv_path: str) -> str:
    """Learn and return schema from CSV file."""
    generator = HybridSchemaGenerator()
    schema = generator.generate_schema_from_csv(csv_path)

    report = [
        "=" * 50,
        "MISATA HYBRID LEARNING REPORT",
        "=" * 50,
        f"Source: {csv_path}",
        f"Tables: {len(schema['tables'])}",
        "",
        "Learned Columns:"
    ]

    for table, cols in schema["columns"].items():
        report.append(f"\n{table}:")
        for col in cols:
            params = col["distribution_params"]
            report.append(f"  - {col['name']}: {col['type']} ({params.get('distribution', 'n/a')})")

    report.append("")
    report.append(generator.learner.get_correlation_report())
    report.append("=" * 50)

    return "\n".join(report)
