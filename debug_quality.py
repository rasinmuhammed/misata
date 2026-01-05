
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from misata.quality import check_quality

def test_quality_checker():
    print("--- Testing Quality Checker (Time Series) ---")
    
    # 1. generated Trend Data
    dates = [datetime(2025, 1, 1) + timedelta(days=i) for i in range(100)]
    values = [100 + i*2 + np.random.normal(0, 5) for i in range(100)] # Strong positive trend
    
    df = pd.DataFrame({
        "date": dates,
        "revenue": values
    })
    
    tables = {"daily_metrics": df}
    
    # 2. Run Checker
    report = check_quality(tables)
    
    # 3. Analyze Results
    print(f"Report Score: {report.score}")
    
    ts_issues = [i for i in report.issues if i.category == "time_series"]
    
    if ts_issues:
        print(f"✅ Time Series Issues Found: {len(ts_issues)}")
        for issue in ts_issues:
            print(f" - [{issue.table}.{issue.column}] {issue.message}")
            if "Trend" in issue.message:
                print("   -> Trend Detection Verified!")
            if "Autocorrelation" in issue.message:
                print("   -> Autocorrelation Verified!")
    else:
        print("❌ No time series issues found (Expected info logs)")

if __name__ == "__main__":
    test_quality_checker()
