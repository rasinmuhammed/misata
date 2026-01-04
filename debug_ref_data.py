
import sys
import os

# Add package root to path
sys.path.append("/Users/muhammedrasin/Misata/packages/core")

from misata.reference_data import detect_domain, get_reference_data, REFERENCE_DATA_LIBRARY

# Test Case 1: Detect Domain
match_tables = ["plans", "exercises", "categories", "products", "users", "subscriptions", "workouts", "orders"]
domain = detect_domain(match_tables)
print(f"Detected Domain: {domain}")

# Test Case 2: Get Reference Data
tables_to_test = ["plans", "exercises", "categories", "products"]
for t in tables_to_test:
    data = get_reference_data(domain, t)
    print(f"Table '{t}': {'FOUND' if data else 'MISSING'} ({len(data) if data else 0} rows)")
    if data:
        print(f"  Sample: {data[0]}")

# Test Case 3: Check Library Keys
print("\nLibrary structure:")
for d, tables in REFERENCE_DATA_LIBRARY.items():
    print(f"  {d}: {list(tables.keys())}")
