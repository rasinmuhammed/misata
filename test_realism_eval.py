import os
import json
import logging
from pprint import pprint
import pandas as pd

logger = logging.getLogger("misata.test")
logging.basicConfig(level=logging.ERROR)

from misata.llm_parser import LLMSchemaGenerator
from misata.simulator import DataSimulator
from misata.schema import NoiseConfig

def test_complex_realism():
    print("=== Testing Misata Enterprise Realism ===\n")
    
    parser = LLMSchemaGenerator(
        enable_feedback=True,
        feedback_min_occurrences=1
    )

    story = """
    We need an e-commerce dataset for Q4 2023.
    Create:
    - users: profiles with signup dates.
    - orders: transactions tied to users.
    
    Business constraints:
    - Orders peak around Black Friday in November.
    - Weekend sales are very heavy.
    - Noise profile should be messy tracking data with 5% null values and 2% typos.
    """

    print("1. Generating Schema via LLM...")
    schema = parser.generate_from_story(story, default_rows=500)
    
    print("\n[Generated Tables]")
    for table in schema.tables:
        print(f" - {table.name} ({table.row_count} rows)")
        
    print("\n[Noise Configuration Applied]")
    if schema.noise_config:
        print(schema.noise_config.model_dump_json(indent=2))
    else:
        print("None detected from prompt. Falling back.")

    print("\n[Outcome Curves Detected]")
    if schema.outcome_curves:
        for curve in schema.outcome_curves:
            print(f" - {curve.table}.{getattr(curve, 'column', getattr(curve, 'time_column', ''))} ({curve.pattern_type}) points: {len(curve.curve_points)} intra-period: {getattr(curve, 'intra_period_pattern', 'N/A')}")
    else:
        print("No outcome curves generated.")

    print("\n2. Executing Data Simulator...")
    os.makedirs("./test_outputs", exist_ok=True)
    simulator = DataSimulator(schema, batch_size=1000)
    simulator.export_to_csv("./test_outputs")
    
    print("\n3. Analyzing Final CSVs...")
    
    # Analyze users table
    if os.path.exists("./test_outputs/users.csv"):
        users_df = pd.read_csv("./test_outputs/users.csv")
        null_count = users_df.isnull().sum().sum()
        total_cells = users_df.size
        print(f"\n[Users Table Profile]")
        print(f"  Rows: {len(users_df)}")
        print(f"  Null Values: {null_count} / {total_cells} ({(null_count/total_cells * 100) if total_cells > 0 else 0:.2f}%)")
        print("\n  Sample Data:")
        print(users_df.head(2).to_string())
        
    # Check orders table
    if os.path.exists("./test_outputs/orders.csv"):
        orders_df = pd.read_csv("./test_outputs/orders.csv")
        print(f"\n[Orders Table Profile]")
        print(f"  Rows: {len(orders_df)}")
        null_count = orders_df.isnull().sum().sum()
        total_cells = orders_df.size
        print(f"  Null Values: {null_count} / {total_cells} ({(null_count/total_cells * 100) if total_cells > 0 else 0:.2f}%)")
        
        # Look for dates
        date_cols = [c for c in orders_df.columns if "date" in c.lower() or "created" in c.lower() or "time" in c.lower()]
        if date_cols:
            date_col = date_cols[0]
            orders_df[date_col] = pd.to_datetime(orders_df[date_col], errors='coerce')
            
            non_null_dates = orders_df[orders_df[date_col].notnull()]
            if not non_null_dates.empty:
                monthly = non_null_dates.groupby(non_null_dates[date_col].dt.month).size()
                print("\n  [Seasonality] Sales by Month:")
                for m, count in monthly.items():
                    print(f"    Month {m}: {count} orders")
                    
                weekly = non_null_dates.groupby(non_null_dates[date_col].dt.dayofweek).size()
                print("\n  [Seasonality] Sales by Day of Week (0=Mon, 6=Sun):")
                for d, count in weekly.items():
                    print(f"    Day {d}: {count} orders")

if __name__ == "__main__":
    test_complex_realism()
