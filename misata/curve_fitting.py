
"""
Mathematical Graph Solver for Misata.

This module uses scipy.optimize to find the best distribution parameters
that match a set of control points provided by the LLM or user.
This allows users/LLMs to "draw" a distribution shape rather than
guessing abstract parameters like alpha/beta/gamma.
"""

from typing import Dict, List

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm, lognorm, expon, beta, gamma, uniform

class CurveFitter:
    """
    Fits statistical distributions to control points using optimization.
    """

    def __init__(self):
        """Initialize the curve fitter."""
        self.distributions = {
            "normal": norm,
            "lognormal": lognorm,
            "exponential": expon,
            "beta": beta,
            "gamma": gamma,
            "uniform": uniform
        }

    def fit_distribution(
        self,
        targets: List[Dict[str, float]],
        distribution_type: str = "normal"
    ) -> Dict[str, float]:
        """
        Find best parameters for a distribution to match target points.

        Args:
            targets: List of points dicts [{"x": 10, "y": 0.1}, ...]
                     where x is the value and y is the desired PDF probability density.
            distribution_type: Name of distribution to fit.

        Returns:
            Dictionary of best-fit parameters (e.g., {"mean": 10, "std": 5})
        """
        if distribution_type not in self.distributions:
            raise ValueError(f"Unsupported distribution: {distribution_type}")

        dist_func = self.distributions[distribution_type]
        points = np.array([(p["x"], p["y"]) for p in targets])
        x_vals = points[:, 0]
        y_targets = points[:, 1]

        # Define objective function (MSE)
        def objective(params):
            try:
                # Scipy stats distributions take args/scale/loc differently
                # We need to map generic params array to specific distribution args
                # This is tricky. Simplified approach:
                if distribution_type == "normal":
                    # params[0] = mean (loc), params[1] = std (scale)
                    y_pred = dist_func.pdf(x_vals, loc=params[0], scale=abs(params[1]))
                elif distribution_type == "exponential":
                     # params[0] = scale (1/lambda)
                     y_pred = dist_func.pdf(x_vals, scale=abs(params[0]))
                elif distribution_type == "uniform":
                    # params[0] = min (loc), params[1] = range (scale)
                    y_pred = dist_func.pdf(x_vals, loc=params[0], scale=abs(params[1]))
                elif distribution_type == "lognormal":
                     # s=shape, scale=exp(mean), loc=0 usually
                     y_pred = dist_func.pdf(x_vals, s=abs(params[0]), scale=abs(params[1]))
                else:
                     # General fallback?
                     return 1e9

                # Mean Squared Error
                mse = np.mean((y_pred - y_targets) ** 2)
                return mse
            except Exception:
                return 1e9

        # Initial guesses
        initial_guess = [np.mean(x_vals), np.std(x_vals)]
        if distribution_type == "exponential":
            initial_guess = [np.mean(x_vals)]
        elif distribution_type == "lognormal":
            initial_guess = [1.0, np.mean(x_vals)]

        # Optimize
        result = minimize(objective, initial_guess, method='Nelder-Mead')
        best_params = result.x

        # Map back to named parameters
        if distribution_type == "normal":
            return {"mean": float(best_params[0]), "std": float(abs(best_params[1]))}
        elif distribution_type == "exponential":
            return {"scale": float(abs(best_params[0]))}
        elif distribution_type == "uniform":
             return {"min": float(best_params[0]), "max": float(best_params[0] + abs(best_params[1]))}
        elif distribution_type == "lognormal":
            return {"shape": float(abs(best_params[0])), "scale": float(abs(best_params[1]))}

        return {}
