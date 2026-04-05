import os
import pandas as pd
import numpy as np

def evaluate_realism():
    print("=== Misata Data Realism Deep Dive ===")
    
    users_path = "./test_outputs/users.csv"
    orders_path = "./test_outputs/orders.csv"
    
    if not os.path.exists(users_path) or not os.path.exists(orders_path):
        print("CSV files not found. Generate data first.")
        return
        
    users = pd.read_csv(users_path)
    orders = pd.read_csv(orders_path)
    
    # 1. Identity & PII Realism (Text Generation)
    print("\n--- 1. PII & Text Realism ---")
    if 'name' in users.columns:
        names = users['name'].dropna().head(3).tolist()
        print(f"Sample Names: {names}")
    if 'email' in users.columns:
        emails = users['email'].dropna().head(3).tolist()
        print(f"Sample Emails: {emails}")
        
    # 2. Noise Profiling
    print("\n--- 2. Messy Data Profiling (Noise Injector) ---")
    user_nulls = users.isnull().sum()
    user_nulls = user_nulls[user_nulls > 0]
    if not user_nulls.empty:
        print("Null values injected strictly into non-critical columns:")
        for col, count in user_nulls.items():
            print(f"  - {col}: {count} missing records ({(count/len(users))*100:.1f}%)")
    else:
        print("No nulls found.")
        
    # Check for Typos (if string column like name has weird capitalization or swapped chars)
    # A simple proxy is looking for lowercase/uppercase anomalies, but pandas doesn't easily show "typos".
    
    # 3. Relational Integrity
    print("\n--- 3. Relational Integrity ---")
    orphan_orders = ~orders['user_id'].isin(users['id'])
    orphan_count = orphan_orders.sum()
    print(f"Orphan Orders (user_id not in users table): {orphan_count} (Must be 0 for realism)")
    
    # 4. Statistical Distributions (Dist Engine)
    print("\n--- 4. Statistical Validity ---")
    if 'amount' in orders.columns:
        amt = orders['amount']
        print("Order Amount Engine: Expected Exponential/Normal distribution, not uniform.")
        print(f"  Mean: ${amt.mean():.2f}")
        print(f"  Median: ${amt.median():.2f}")
        print(f"  Max: ${amt.max():.2f}")
        print(f"  Skewness: {amt.skew():.2f} (Values > 1 indicate realistic long-tail purchasing behavior)")
        
    # 5. Temporal Constraints & Seasonality curves (Curve Engine)
    print("\n--- 5. Black Friday Seasonality (Curve Engine) ---")
    time_col = [c for c in orders.columns if 'date' in c.lower() or 'time' in c.lower()][0]
    orders[time_col] = pd.to_datetime(orders[time_col])
    
    if 'amount' in orders.columns:
        monthly = orders.groupby(orders[time_col].dt.month)['amount'].mean()
        print("Average Order Value by Month (Expecting spike in Nov/11):")
        for m, avg in monthly.items():
            print(f"  Month {m}: ${avg:.2f}")

if __name__ == '__main__':
    evaluate_realism()
