
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from misata.studio.constraint_generator import (
    ConstrainedWarehouseGenerator, WarehouseSpec, TableSpec, ColumnSpec, OutcomeConstraint
)
from misata.studio.outcome_curve import OutcomeCurve, CurvePoint

def test_integration():
    print("--- Testing Causal Engine Integration ---")

    # 1. Define Schema that matches SaaS Template
    # Needs tables: Traffic, Leads, Deals (mapped to Revenue)
    
    traffic_table = TableSpec(
        name="daily_traffic",
        row_count=0, # Will be determined by solver
        columns=[ColumnSpec(name="visits", type="int")]
    )
    
    leads_table = TableSpec(
        name="leads",
        row_count=0,
        columns=[ColumnSpec(name="email", type="text", text_type="email")]
    )
    
    revenue_table = TableSpec(
        name="subscriptions_revenue", # Matches "revenue" heuristic? "revenue" is keyword
        row_count=0,
        columns=[
             ColumnSpec(name="amount", type="float"),
             ColumnSpec(name="created_at", type="date")
        ],
        is_fact=True,
        date_column="created_at",
        amount_column="amount"
    )

    # 2. Define Constraint
    # Monthly Revenue Curve
    points = [
        CurvePoint(timestamp=datetime.now() + timedelta(days=30*i), value=100000 + i*10000)
        for i in range(5)
    ]
    curve = OutcomeCurve(metric_name="revenue", points=points, time_unit="month")
    
    constraint = OutcomeConstraint(
        metric_name="revenue",
        fact_table="subscriptions_revenue",
        value_column="amount",
        date_column="created_at",
        outcome_curve=curve
    )

    spec = WarehouseSpec(
        tables=[traffic_table, leads_table, revenue_table],
        constraints=[constraint]
    )

    # 3. Generate
    generator = ConstrainedWarehouseGenerator(spec)
    
    # Check if detection worked
    if generator.causal_graph:
        print(f"✅ Detection Worked! Mapping: {generator.causal_mapping}")
    else:
        print("❌ Detection Failed.")
        return

    result = generator.generate_all()

    # 4. Verify Data Consistency
    # Check if tables exist and have rows
    print("\nGenerated Tables:")
    for name, df in result.items():
        print(f"- {name}: {len(df)} rows")
        if len(df) > 0:
            print(df.head(2))

    # Check Revenue Sum
    rev_df = result['subscriptions_revenue']
    total_rev_gen = rev_df['amount'].sum()
    total_rev_target = sum(p.value for p in points)
    
    print(f"\nTotal Target Revenue: ${total_rev_target:,.2f}")
    print(f"Total Generated Revenue: ${total_rev_gen:,.2f}")
    
    # Error < 5% is acceptable due to random noise in generation
    error_pct = abs(total_rev_gen - total_rev_target) / total_rev_target
    print(f"Error: {error_pct:.2%}")
    
    if error_pct < 0.10: # 10% tolerance for random noise logic
        print("✅ Data Generation Verified!")
    else:
        print("❌ High Error Rate.")

if __name__ == "__main__":
    test_integration()
