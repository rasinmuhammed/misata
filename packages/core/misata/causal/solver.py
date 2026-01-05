import numpy as np
from scipy.optimize import minimize # type: ignore
from typing import Dict, List, Optional, Tuple
from .graph import CausalGraph

class CausalSolver:
    """
    Solves for exogenous inputs given constraints on endogenous outputs.
    """
    def __init__(self, graph: CausalGraph):
        self.graph = graph

    def solve(
        self,
        target_constraints: Dict[str, np.ndarray],
        adjustable_nodes: List[str],
        initial_values: Optional[Dict[str, np.ndarray]] = None,
        bounds: Optional[Tuple[float, float]] = (0, None) # Non-negative by default
    ) -> Dict[str, np.ndarray]:
        """
        Back-solves the graph.
        
        Args:
            target_constraints: Dict mapping NodeName -> TargetArray (e.g., {'Revenue': [100, 200]})
            adjustable_nodes: List of Exogenous Node Names to adjust (e.g., ['Traffic'])
            initial_values: Starting guess for adjustable nodes. Defaults to 1.0.
            bounds: (min, max) for adjustable values.
            
        Returns:
            Dict of optimized inputs for the adjustable nodes.
        """
        
        # Validation
        sample_size = len(list(target_constraints.values())[0])
        num_vars = len(adjustable_nodes)
        
        # Flatten initial guess into 1D array for scipy
        # x0 = [node1_t0, node1_t1, ..., node2_t0, ...]
        x0 = []
        for node in adjustable_nodes:
            if initial_values and node in initial_values:
                x0.extend(initial_values[node])
            else:
                x0.extend(np.ones(sample_size)) # Default guess: 1.0
        
        x0 = np.array(x0)

        # Static inputs (non-adjustable exogenous nodes)
        # We need to provide values for ALL exogenous nodes for the forward pass.
        # If a node is exogenous but NOT in adjustable_nodes, we need a default.
        # For now, let's assume we pass a full `base_inputs` dict, or default to 1s.
        base_inputs = {}
        # TODO: Allow passing base inputs for non-optimized nodes

        def objective_function(x):
            """
            Input x: Flattened array of adjustable values.
            Returns: Error (MSE) between Generated and Target.
            """
            # 1. Unpack x back into Dict inputs
            current_inputs = base_inputs.copy()
            
            for i, node_name in enumerate(adjustable_nodes):
                start_idx = i * sample_size
                end_idx = (i + 1) * sample_size
                current_inputs[node_name] = x[start_idx:end_idx]

            # 2. Handle non-adjustable exogenous nodes (set to 1.0 if missing)
            # This is a simplification. Ideally, we fetch these from "Fact Injection".
            for node_name, node in self.graph.nodes.items():
                if node.node_type == 'exogenous' and node_name not in current_inputs:
                    current_inputs[node_name] = np.ones(sample_size)

            # 3. Forward Pass
            try:
                results = self.graph.forward_pass(current_inputs)
            except Exception as e:
                # If optimization goes wild (e.g. NaN), return high error
                return 1e9

            # 4. Calculate Error
            total_error = 0.0
            for target_node, target_arr in target_constraints.items():
                generated_arr = results[target_node]
                # Mean Squared Error
                mse = np.mean((generated_arr - target_arr) ** 2)
                total_error += mse
            
            return total_error

        # Run Optimization
        # L-BFGS-B handles bounds efficiently
        scipy_bounds = [bounds] * len(x0)
        
        res = minimize(
            objective_function, 
            x0, 
            method='L-BFGS-B', 
            bounds=scipy_bounds,
            options={'ftol': 1e-9, 'disp': False}
        )

        if not res.success:
            print(f"Warning: Optimization failed: {res.message}")

        # Unpack result
        final_inputs = {}
        optimized_x = res.x
        
        for i, node_name in enumerate(adjustable_nodes):
            start_idx = i * sample_size
            end_idx = (i + 1) * sample_size
            final_inputs[node_name] = optimized_x[start_idx:end_idx]
            
        return final_inputs
