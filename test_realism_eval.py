import os
import pandas as pd
import numpy as np

logger = __import__("logging").getLogger("misata.test")

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
    - users: profiles with name, email, and signup_dates.
    - products: inventory items with product_name, brand, and category.
    - orders: transactions tied to users and products.
    
    Business constraints:
    - Orders peak around Black Friday in November.
    - Weekend sales are very heavy.
    - Noise profile should be messy tracking data with 5% null values and 2% typos.
    """

    print("1. Generating Schema via LLM...")
    schema = parser.generate_from_story(story, default_rows=100)
    
    print("\n2. Executing Data Simulator with SMART MODE...")
    os.makedirs("./test_outputs", exist_ok=True)
    
    # TURNING ON SMART MODE FOR CONTEXT-AWARE TEXT GENERATION
    simulator = DataSimulator(schema, batch_size=1000, smart_mode=True)
    simulator.export_to_csv("./test_outputs")
    
    print("\n3. Analyzing Final CSVs...")
    
    # Check products table for smart values
    if os.path.exists("./test_outputs/products.csv"):
        products_df = pd.read_csv("./test_outputs/products.csv")
        print(f"\n[Products Table Text Realism]")
        print("  Sample Data:")
        # Find string columns
        str_cols = products_df.select_dtypes(include=['object']).columns.tolist()
        if str_cols:
            print(products_df[str_cols].head(5).to_string())
        else:
            print(products_df.head(2).to_string())
            
    # Check users table
    if os.path.exists("./test_outputs/users.csv"):
        users_df = pd.read_csv("./test_outputs/users.csv")
        print(f"\n[Users Table Text Realism]")
        print("  Sample Data:")
        str_cols = users_df.select_dtypes(include=['object']).columns.tolist()
        if str_cols:
            print(users_df[str_cols].head(4).to_string())

if __name__ == "__main__":
    test_complex_realism()
