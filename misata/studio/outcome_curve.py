"""
Outcome Curve Designer - Reverse Time-Series Generation

The killer feature: Users draw the aggregated outcome they want,
and Misata generates individual transactions that produce that exact curve.

Example:
    User draws: Revenue = [$100K, $150K, $200K, $180K, ...] over 12 months
    Misata generates: 50,000 individual orders with dates/amounts
    When aggregated: SUM(amount) GROUP BY month = exactly the drawn curve

Algorithm:
    1. Parse curve control points into time buckets
    2. For each bucket, calculate target aggregate
    3. Distribute transactions across bucket:
       - Determine transaction count (based on avg ticket or specified)
       - Generate individual amounts that sum to target
    4. Add variance/noise for realism
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class CurvePoint:
    """A single point on the outcome curve."""
    timestamp: datetime
    value: float


@dataclass
class OutcomeCurve:
    """Represents the target outcome curve drawn by user."""
    metric_name: str  # e.g., "revenue", "signups", "orders"
    time_unit: str    # "day", "week", "month"
    points: List[CurvePoint]
    
    # Optional constraints
    avg_transaction_value: Optional[float] = None  # For revenue curves
    min_transactions_per_period: int = 10
    max_transactions_per_period: int = 10000


def interpolate_curve(curve: OutcomeCurve, num_buckets: int) -> List[float]:
    """Interpolate curve to get values for each time bucket."""
    if len(curve.points) < 2:
        return [curve.points[0].value] * num_buckets
    
    # Extract x (time indices) and y (values)
    x = np.array([i for i in range(len(curve.points))])
    y = np.array([p.value for p in curve.points])
    
    # Interpolate to num_buckets
    x_new = np.linspace(0, len(curve.points) - 1, num_buckets)
    
    from scipy.interpolate import interp1d
    f = interp1d(x, y, kind='cubic', fill_value='extrapolate')
    return list(np.maximum(f(x_new), 0))  # Ensure non-negative


def generate_transactions_for_bucket(
    target_value: float,
    bucket_start: datetime,
    bucket_end: datetime,
    avg_transaction: Optional[float] = None,
    min_transactions: int = 10,
    max_transactions: int = 1000,
    rng: Optional[np.random.Generator] = None
) -> pd.DataFrame:
    """Generate individual transactions that sum to target_value for a time bucket.
    
    Returns DataFrame with columns: [timestamp, amount]
    """
    if rng is None:
        rng = np.random.default_rng()
    
    if target_value <= 0:
        return pd.DataFrame(columns=['timestamp', 'amount'])
    
    # Determine number of transactions
    if avg_transaction:
        n_transactions = int(target_value / avg_transaction)
        n_transactions = max(min_transactions, min(n_transactions, max_transactions))
    else:
        # Estimate based on target value
        n_transactions = max(min_transactions, min(int(target_value / 50), max_transactions))
    
    # Generate amounts that sum to target using Dirichlet distribution
    # This ensures realistic variation while hitting exact target
    proportions = rng.dirichlet(np.ones(n_transactions) * 2)  # alpha=2 for moderate variance
    amounts = proportions * target_value
    
    # Add some variance to make it more realistic
    # Small noise that doesn't change the sum significantly
    noise = rng.normal(0, abs(target_value) * 0.001, n_transactions)
    amounts = amounts + noise
    
    # Adjust to hit exact target (compensate for noise)
    amounts = amounts * (target_value / amounts.sum())
    
    # Ensure all positive
    amounts = np.maximum(amounts, 0.01)
    amounts = amounts * (target_value / amounts.sum())  # Re-normalize
    
    # Generate timestamps uniformly distributed within bucket
    bucket_duration = (bucket_end - bucket_start).total_seconds()
    random_seconds = rng.uniform(0, bucket_duration, n_transactions)
    timestamps = [bucket_start + timedelta(seconds=s) for s in random_seconds]
    
    # Sort by timestamp
    df = pd.DataFrame({
        'timestamp': timestamps,
        'amount': amounts.round(2)
    }).sort_values('timestamp').reset_index(drop=True)
    
    return df


def generate_from_outcome_curve(
    curve: OutcomeCurve,
    start_date: Optional[datetime] = None,
    seed: int = 42
) -> pd.DataFrame:
    """Generate a full transaction dataset from an outcome curve.
    
    Args:
        curve: The target outcome curve
        start_date: Start date (defaults to today minus curve duration)
        seed: Random seed for reproducibility
        
    Returns:
        DataFrame with columns: [id, timestamp, amount] where
        SUM(amount) GROUP BY period = the drawn curve
    """
    rng = np.random.default_rng(seed)
    
    n_periods = len(curve.points)
    
    # Determine bucket duration
    if curve.time_unit == "day":
        bucket_delta = timedelta(days=1)
    elif curve.time_unit == "week":
        bucket_delta = timedelta(weeks=1)
    elif curve.time_unit == "month":
        bucket_delta = timedelta(days=30)  # Approximate
    else:
        bucket_delta = timedelta(days=1)
    
    # Set start date
    if start_date is None:
        start_date = datetime.now() - (bucket_delta * n_periods)
    
    all_transactions = []
    
    for i, point in enumerate(curve.points):
        bucket_start = start_date + (bucket_delta * i)
        bucket_end = bucket_start + bucket_delta
        
        transactions = generate_transactions_for_bucket(
            target_value=point.value,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
            avg_transaction=curve.avg_transaction_value,
            min_transactions=curve.min_transactions_per_period,
            max_transactions=curve.max_transactions_per_period,
            rng=rng
        )
        
        all_transactions.append(transactions)
    
    # Combine all transactions
    df = pd.concat(all_transactions, ignore_index=True)
    df.insert(0, 'id', range(1, len(df) + 1))
    
    return df


def verify_curve_match(
    transactions: pd.DataFrame,
    curve: OutcomeCurve,
    start_date: datetime
) -> Dict[str, Any]:
    """Verify that generated transactions aggregate to match the target curve.
    
    Returns:
        Dict with 'match_score', 'expected', 'actual', 'error_pct'
    """
    n_periods = len(curve.points)
    expected = np.array([p.value for p in curve.points])
    
    # Determine bucket duration
    if curve.time_unit == "day":
        bucket_delta = timedelta(days=1)
    elif curve.time_unit == "week":
        bucket_delta = timedelta(weeks=1)
    else:  # month
        bucket_delta = timedelta(days=30)
    
    # Assign each transaction to a bucket index based on time offset from start
    def get_bucket_index(ts):
        offset = (ts - start_date).total_seconds()
        bucket_seconds = bucket_delta.total_seconds()
        return min(int(offset / bucket_seconds), n_periods - 1)
    
    transactions = transactions.copy()
    transactions['bucket_idx'] = transactions['timestamp'].apply(get_bucket_index)
    
    # Aggregate by bucket index
    actual_by_bucket = transactions.groupby('bucket_idx')['amount'].sum()
    
    # Build actual array matching expected length
    actual = np.zeros(n_periods)
    for idx, val in actual_by_bucket.items():
        if 0 <= idx < n_periods:
            actual[idx] = val
    
    # Calculate match score
    error_pct = np.abs(actual - expected) / np.maximum(expected, 1) * 100
    avg_error = error_pct.mean()
    match_score = max(0, 100 - avg_error)
    
    return {
        'match_score': round(match_score, 2),
        'expected': expected.tolist(),
        'actual': actual.tolist(),
        'error_pct': error_pct.tolist(),
        'avg_error_pct': round(avg_error, 2)
    }


# ============ Preset Curve Shapes ============

def get_curve_presets() -> Dict[str, List[float]]:
    """Get preset curve shapes for common business patterns."""
    return {
        "Linear Growth": [100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 320],
        "Exponential Growth": [100, 115, 132, 152, 175, 201, 231, 266, 306, 352, 405, 466],
        "Hockey Stick": [100, 102, 105, 108, 112, 118, 140, 180, 250, 350, 500, 700],
        "Seasonal (Retail)": [100, 80, 70, 90, 100, 120, 110, 100, 130, 160, 200, 300],
        "SaaS Growth": [10, 18, 30, 50, 80, 120, 170, 230, 300, 380, 470, 570],
        "Churn Decline": [1000, 920, 850, 790, 740, 700, 665, 635, 610, 590, 575, 560],
        "V-shaped Recovery": [100, 80, 60, 50, 45, 50, 65, 85, 110, 140, 170, 200],
        "Plateau": [100, 150, 200, 240, 270, 290, 300, 305, 308, 310, 311, 312],
    }


def create_curve_from_preset(
    preset_name: str,
    metric_name: str = "revenue",
    time_unit: str = "month",
    start_date: datetime = None,
    scale: float = 1000  # Multiply preset values by this
) -> OutcomeCurve:
    """Create an OutcomeCurve from a preset shape."""
    presets = get_curve_presets()
    values = presets.get(preset_name, presets["Linear Growth"])
    
    if start_date is None:
        start_date = datetime.now() - timedelta(days=30 * len(values))
    
    if time_unit == "day":
        delta = timedelta(days=1)
    elif time_unit == "week":
        delta = timedelta(weeks=1)
    else:
        delta = timedelta(days=30)
    
    points = [
        CurvePoint(
            timestamp=start_date + delta * i,
            value=v * scale
        )
        for i, v in enumerate(values)
    ]
    
    return OutcomeCurve(
        metric_name=metric_name,
        time_unit=time_unit,
        points=points
    )
