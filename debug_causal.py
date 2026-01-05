
import numpy as np
import networkx as nx
from misata.causal.graph import get_saas_template
from misata.causal.solver import CausalSolver

def test_causal_solver():
    print("--- Testing Causal Solver ---")

    # 1. Setup Graph
    graph = get_saas_template()
    solver = CausalSolver(graph)

    # 2. Define Time Series (12 Months)
    months = np.arange(12)
    
    # Target Revenue: Linear Trend + Seasonality
    # E.g. Start at 100k, end at 200k, with a peak in month 6
    trend = np.linspace(100000, 200000, 12)
    seasonality = 20000 * np.sin(months * (2 * np.pi / 12))
    target_revenue = trend + seasonality

    print("Target Revenue (First 5):", target_revenue[:5])

    # 3. Solve for 'Traffic'
    # assumption: Conversion Rates and AOV are constant (Fact Injection would provide these)
    # But wait, the solver defaults exogenous to 1.0. 
    # If AOV=1, Traffic will need to be HUGE (equal to Revenue).
    # That's fine for testing the math.
    
    results = solver.solve(
        target_constraints={"Revenue": target_revenue},
        adjustable_nodes=["Traffic"]
    )

    # 4. Verify
    # Run a forward pass with the solved inputs
    
    # Needs to match solver internals for defaults:
    # We solved for Traffic. We need to provide defaults for others (LeadConversion, SalesConversion, AOV)
    # The solver assumed 1.0 for these defaults during optimization.
    
    verification_inputs = results.copy()
    verification_inputs["LeadConversion"] = np.ones(12)
    verification_inputs["SalesConversion"] = np.ones(12)
    verification_inputs["AOV"] = np.ones(12)

    final_pass = graph.forward_pass(verification_inputs)
    generated_revenue = final_pass["Revenue"]

    print("\nGenerated Revenue (First 5):", generated_revenue[:5])
    
    # Check Error
    error = np.mean((generated_revenue - target_revenue) ** 2)
    print(f"\nMean Squared Error: {error:.4f}")
    
    if error < 1.0:
        print("✅ Solver Successfully Back-Propagated Constraints!")
    else:
        print("❌ Solver Failed to Converge.")

    # Check the "Why": Why did Revenue follow that curve?
    # Because Traffic followed it (since conversions are 1.0)
    traffic = results["Traffic"]
    print("\nSolved Traffic (First 5):", traffic[:5])
    
    # Traffic should match Revenue exactly if all multipliers are 1.0
    diff = np.abs(traffic - target_revenue).sum()
    if diff < 1.0:
         print("✅ Logic Check: Traffic == Revenue (since conversion=1)")

if __name__ == "__main__":
    test_causal_solver()
