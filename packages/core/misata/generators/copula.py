"""
SDV Copula-based Synthetic Data Generator

Uses SDV's GaussianCopulaSynthesizer for high-quality correlation preservation.
This is a key upgrade from our basic generator to beat Gretel on data quality.
"""

from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

try:
    from sdv.single_table import GaussianCopulaSynthesizer
    from sdv.metadata import SingleTableMetadata
    SDV_AVAILABLE = True
except ImportError:
    SDV_AVAILABLE = False
    print("[WARNING] SDV not installed. Run: pip install sdv")


class CopulaGenerator:
    """
    SDV-based generator using Gaussian Copulas for correlation preservation.
    
    Key advantages over basic generation:
    - Preserves pairwise correlations between columns
    - Learns marginal distributions accurately
    - Handles mixed data types (numeric, categorical, datetime)
    """
    
    def __init__(self):
        self.synthesizer = None
        self.metadata = None
        self._is_fitted = False
    
    def fit(self, df: pd.DataFrame, metadata: Optional[Dict] = None) -> None:
        """
        Fit the copula model to real data.
        
        Args:
            df: Real data to learn from
            metadata: Optional SDV metadata dict, auto-detected if not provided
        """
        if not SDV_AVAILABLE:
            raise ImportError("SDV not installed. Run: pip install sdv")
        
        # Auto-detect metadata if not provided
        self.metadata = SingleTableMetadata()
        self.metadata.detect_from_dataframe(df)
        
        # Apply custom metadata if provided
        if metadata:
            for col, col_meta in metadata.items():
                if 'sdtype' in col_meta:
                    self.metadata.update_column(col, sdtype=col_meta['sdtype'])
        
        # Create and fit synthesizer
        self.synthesizer = GaussianCopulaSynthesizer(self.metadata)
        self.synthesizer.fit(df)
        self._is_fitted = True
        
        print(f"[COPULA] Fitted on {len(df)} rows, {len(df.columns)} columns")
    
    def sample(self, n: int) -> pd.DataFrame:
        """
        Generate synthetic data preserving correlations.
        
        Args:
            n: Number of rows to generate
            
        Returns:
            Synthetic DataFrame with same schema as training data
        """
        if not self._is_fitted:
            raise ValueError("Must call fit() before sample()")
        
        synthetic = self.synthesizer.sample(n)
        print(f"[COPULA] Generated {len(synthetic)} rows")
        return synthetic
    
    def get_quality_report(self, real: pd.DataFrame, synthetic: pd.DataFrame) -> Dict[str, Any]:
        """
        Evaluate quality of synthetic data vs real data.
        
        Returns:
            Dict with quality metrics (no fake validations!)
        """
        try:
            from sdv.evaluation.single_table import evaluate_quality
            
            report = evaluate_quality(
                real_data=real,
                synthetic_data=synthetic,
                metadata=self.metadata
            )
            
            return {
                "overall_score": report.get_score(),
                "column_shapes": report.get_details("Column Shapes"),
                "column_pair_trends": report.get_details("Column Pair Trends"),
            }
        except Exception as e:
            print(f"[COPULA] Quality evaluation failed: {e}")
            return {"error": str(e)}


class ConstraintAwareCopulaGenerator(CopulaGenerator):
    """
    Extended Copula generator that applies outcome constraints.
    """
    
    def sample_with_constraints(
        self, 
        n: int, 
        outcome_curves: Optional[List[Dict]] = None,
        date_column: Optional[str] = None,
        value_column: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Generate data that matches outcome curve targets.
        
        Args:
            n: Number of rows
            outcome_curves: List of curve specs with monthly targets
            date_column: Column containing dates
            value_column: Column to adjust for targets
            
        Returns:
            Synthetic data adjusted to match targets
        """
        # Generate base synthetic data
        df = self.sample(n)
        
        if not outcome_curves or not date_column or not value_column:
            return df
        
        if date_column not in df.columns or value_column not in df.columns:
            print(f"[COPULA] Columns not found: {date_column}, {value_column}")
            return df
        
        # Apply outcome curve adjustments
        for curve in outcome_curves:
            df = self._apply_curve(df, curve, date_column, value_column)
        
        return df
    
    def _apply_curve(
        self, 
        df: pd.DataFrame, 
        curve: Dict, 
        date_column: str, 
        value_column: str
    ) -> pd.DataFrame:
        """Apply a single outcome curve to the data."""
        
        points = curve.get('curve_points', [])
        if not points:
            return df
        
        # Ensure date column is datetime
        if not pd.api.types.is_datetime64_any_dtype(df[date_column]):
            df[date_column] = pd.to_datetime(df[date_column], errors='coerce')
        
        # Build month -> target mapping
        month_targets = {}
        for p in points:
            month = p.get('month') if isinstance(p, dict) else getattr(p, 'month', None)
            value = p.get('relative_value') if isinstance(p, dict) else getattr(p, 'relative_value', None)
            if month and value:
                month_targets[month] = value
        
        if not month_targets:
            return df
        
        # Calculate base mean for scaling
        base_mean = df[value_column].mean()
        
        # Apply scaling per month
        for month, relative_value in month_targets.items():
            mask = df[date_column].dt.month == month
            if mask.sum() > 0:
                # Scale values to match relative target
                # relative_value=1.0 means average, 2.0 means double, etc.
                current_mean = df.loc[mask, value_column].mean()
                if current_mean > 0:
                    scale_factor = relative_value
                    df.loc[mask, value_column] = df.loc[mask, value_column] * scale_factor
        
        print(f"[COPULA] Applied outcome curve: {len(month_targets)} monthly adjustments")
        return df


# Factory function for easy access
def create_copula_generator(with_constraints: bool = True) -> CopulaGenerator:
    """Create a copula generator instance."""
    if with_constraints:
        return ConstraintAwareCopulaGenerator()
    return CopulaGenerator()
