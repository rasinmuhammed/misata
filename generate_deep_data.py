import os
import json
import logging
import time

logger = logging.getLogger("misata.test")
logging.basicConfig(level=logging.INFO)

from misata.llm_parser import LLMSchemaGenerator
from misata.simulator import DataSimulator
from misata.schema import NoiseConfig

def run_deep_generation():
    print("=== Starting Deep B2B SaaS Data Generation ===")
    start = time.time()
    
    parser = LLMSchemaGenerator(
        enable_feedback=True,
        feedback_min_occurrences=1
    )

    story = """
    I need a B2B SaaS subscriptions dataset for the entire year of 2024.
    Tables:
    - tenants: The companies using our software (company name, industry, plan_type).
    - subscriptions: The actual MRR licenses tied to tenants (start_date, amount, status).
    - support_tickets: Customer service tickets tied to tenants (created_at, priority, resolution_time_hours).
    
    Business constraints:
    - Support tickets peak dramatically in January and February.
    - No support tickets happen on weekends.
    - MRR (amount) should be highly dependent on the plan_type (Enterprise should be $5000+, Startup $100+).
    - We want realistic analytics_safe noise: inject 8% null values into the support tickets to simulate bad agent data logging.
    """

    print("1. Generating Complex Schema via LLM...")
    schema = parser.generate_from_story(story, default_rows=25000)
    
    # Ensure massive rows for the transactional tables to test scaling
    for table in schema.tables:
        if not table.is_reference:
            table.row_count = 10000  # Cap at 10k per table for speed
            
    print("\n[Generated Tables]")
    for table in schema.tables:
        print(f" - {table.name} ({table.row_count} rows)")
        
    print("\n2. Executing Vectorized Data Simulator (Testing RAM & Speed)...")
    os.makedirs("./deep_outputs", exist_ok=True)
    
    simulator = DataSimulator(schema, batch_size=2500, smart_mode=True)
    simulator.export_to_csv("./deep_outputs")
    
    end = time.time()
    print(f"\n3. Generation Complete in {end - start:.2f} seconds!")
    print("Data available in ./deep_outputs/")
    
if __name__ == "__main__":
    run_deep_generation()
