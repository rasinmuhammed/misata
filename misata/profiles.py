"""
Distribution Profiles for Realistic Data Generation.

Pre-configured distribution parameters that match real-world patterns
for common data types like age, salary, prices, etc.
"""

from typing import Any, Dict, List, Optional, Union
import numpy as np


class DistributionProfile:
    """A named distribution configuration for realistic generation.
    
    Example:
        profile = DistributionProfile(
            name="age",
            distribution="mixture",
            params={
                "components": [
                    {"mean": 35, "std": 12, "weight": 0.6},  # Working age
                    {"mean": 70, "std": 8, "weight": 0.2},   # Retirees
                    {"mean": 12, "std": 4, "weight": 0.2},   # Children
                ]
            }
        )
        values = profile.generate(1000)
    """
    
    def __init__(
        self,
        name: str,
        distribution: str,
        params: Dict[str, Any],
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        decimals: Optional[int] = None,
    ):
        self.name = name
        self.distribution = distribution
        self.params = params
        self.min_value = min_value
        self.max_value = max_value
        self.decimals = decimals
    
    def generate(
        self, 
        size: int, 
        rng: Optional[np.random.Generator] = None
    ) -> np.ndarray:
        """Generate values according to this profile."""
        if rng is None:
            rng = np.random.default_rng()
        
        if self.distribution == "normal":
            mean = self.params.get("mean", 50)
            std = self.params.get("std", 10)
            values = rng.normal(mean, std, size)
        
        elif self.distribution == "lognormal":
            mean = self.params.get("mean", 0)
            sigma = self.params.get("sigma", 1)
            values = rng.lognormal(mean, sigma, size)
        
        elif self.distribution == "exponential":
            scale = self.params.get("scale", 1.0)
            values = rng.exponential(scale, size)
        
        elif self.distribution == "pareto":
            alpha = self.params.get("alpha", 2.0)
            min_val = self.params.get("min", 1.0)
            values = (rng.pareto(alpha, size) + 1) * min_val
        
        elif self.distribution == "beta":
            a = self.params.get("a", 2)
            b = self.params.get("b", 5)
            scale = self.params.get("scale", 1.0)
            values = rng.beta(a, b, size) * scale
        
        elif self.distribution == "mixture":
            # Gaussian mixture model
            components = self.params.get("components", [])
            if not components:
                values = rng.normal(0, 1, size)
            else:
                weights = np.array([c.get("weight", 1) for c in components])
                weights = weights / weights.sum()
                
                # Sample component indices
                component_indices = rng.choice(
                    len(components), size=size, p=weights
                )
                
                values = np.zeros(size)
                for i, comp in enumerate(components):
                    mask = component_indices == i
                    n = mask.sum()
                    if n > 0:
                        values[mask] = rng.normal(
                            comp.get("mean", 0),
                            comp.get("std", 1),
                            n
                        )
        
        elif self.distribution == "zipf":
            # Zipf distribution for long-tail data
            a = self.params.get("alpha", 2.0)
            values = rng.zipf(a, size).astype(float)
        
        elif self.distribution == "uniform":
            low = self.params.get("min", 0)
            high = self.params.get("max", 100)
            values = rng.uniform(low, high, size)
        
        else:
            # Default to uniform
            values = rng.uniform(0, 100, size)
        
        # Apply constraints
        if self.min_value is not None:
            values = np.maximum(values, self.min_value)
        if self.max_value is not None:
            values = np.minimum(values, self.max_value)
        if self.decimals is not None:
            values = np.round(values, self.decimals)
        
        return values


# ============ Pre-built Profiles ============

PROFILES: Dict[str, DistributionProfile] = {}


def _register_profile(profile: DistributionProfile) -> None:
    """Register a profile by name."""
    PROFILES[profile.name] = profile


# Age distributions
_register_profile(DistributionProfile(
    name="age_adult",
    distribution="mixture",
    params={
        "components": [
            {"mean": 28, "std": 6, "weight": 0.3},   # Young adults
            {"mean": 42, "std": 10, "weight": 0.45}, # Middle age
            {"mean": 62, "std": 8, "weight": 0.25},  # Older adults
        ]
    },
    min_value=18,
    max_value=100,
    decimals=0,
))

_register_profile(DistributionProfile(
    name="age_population",
    distribution="mixture",
    params={
        "components": [
            {"mean": 8, "std": 4, "weight": 0.15},   # Children
            {"mean": 25, "std": 8, "weight": 0.25},  # Young adults
            {"mean": 42, "std": 12, "weight": 0.35}, # Middle age
            {"mean": 68, "std": 10, "weight": 0.25}, # Seniors
        ]
    },
    min_value=0,
    max_value=105,
    decimals=0,
))

# Salary distributions
_register_profile(DistributionProfile(
    name="salary_usd",
    distribution="lognormal",
    params={"mean": 11.0, "sigma": 0.5},  # Log of ~$60k median
    min_value=25000,
    max_value=500000,
    decimals=0,
))

_register_profile(DistributionProfile(
    name="salary_tech",
    distribution="mixture",
    params={
        "components": [
            {"mean": 75000, "std": 15000, "weight": 0.2},   # Junior
            {"mean": 120000, "std": 25000, "weight": 0.4},  # Mid
            {"mean": 180000, "std": 40000, "weight": 0.3},  # Senior
            {"mean": 280000, "std": 60000, "weight": 0.1},  # Staff+
        ]
    },
    min_value=50000,
    max_value=600000,
    decimals=0,
))

# Price distributions
_register_profile(DistributionProfile(
    name="price_retail",
    distribution="lognormal",
    params={"mean": 3.5, "sigma": 1.2},  # ~$30 median
    min_value=0.99,
    max_value=10000,
    decimals=2,
))

_register_profile(DistributionProfile(
    name="price_saas",
    distribution="mixture",
    params={
        "components": [
            {"mean": 15, "std": 5, "weight": 0.3},     # Basic tier
            {"mean": 49, "std": 15, "weight": 0.4},    # Pro tier
            {"mean": 199, "std": 50, "weight": 0.25},  # Enterprise
            {"mean": 999, "std": 200, "weight": 0.05}, # Custom
        ]
    },
    min_value=0,
    max_value=5000,
    decimals=0,
))

# Transaction amounts
_register_profile(DistributionProfile(
    name="transaction_amount",
    distribution="pareto",
    params={"alpha": 2.5, "min": 10},
    min_value=1,
    max_value=100000,
    decimals=2,
))

# Counts / quantities
_register_profile(DistributionProfile(
    name="order_quantity",
    distribution="zipf",
    params={"alpha": 2.0},
    min_value=1,
    max_value=100,
    decimals=0,
))

# Time-related
_register_profile(DistributionProfile(
    name="session_duration_seconds",
    distribution="lognormal",
    params={"mean": 5.5, "sigma": 1.5},  # ~4 min median
    min_value=1,
    max_value=7200,  # 2 hours max
    decimals=0,
))

# Ratings and scores
_register_profile(DistributionProfile(
    name="rating_5star",
    distribution="beta",
    params={"a": 5, "b": 2, "scale": 5},  # Skewed towards higher ratings
    min_value=1,
    max_value=5,
    decimals=1,
))

_register_profile(DistributionProfile(
    name="nps_score",
    distribution="mixture",
    params={
        "components": [
            {"mean": 3, "std": 2, "weight": 0.15},   # Detractors
            {"mean": 7, "std": 1, "weight": 0.25},   # Passives
            {"mean": 9, "std": 0.8, "weight": 0.6},  # Promoters
        ]
    },
    min_value=0,
    max_value=10,
    decimals=0,
))

# Percentages
_register_profile(DistributionProfile(
    name="conversion_rate",
    distribution="beta",
    params={"a": 2, "b": 50, "scale": 100},  # Low conversion (1-5%)
    min_value=0,
    max_value=100,
    decimals=2,
))

_register_profile(DistributionProfile(
    name="churn_rate",
    distribution="beta",
    params={"a": 1.5, "b": 30, "scale": 100},  # ~5% typical
    min_value=0,
    max_value=100,
    decimals=2,
))


def get_profile(name: str) -> Optional[DistributionProfile]:
    """Get a profile by name."""
    return PROFILES.get(name)


def list_profiles() -> List[str]:
    """List all available profile names."""
    return list(PROFILES.keys())


def generate_with_profile(
    profile_name: str,
    size: int,
    rng: Optional[np.random.Generator] = None
) -> np.ndarray:
    """Generate values using a named profile.
    
    Args:
        profile_name: Name of the profile (e.g., "salary_tech")
        size: Number of values to generate
        rng: Random number generator
        
    Returns:
        Array of generated values
        
    Raises:
        ValueError: If profile not found
    """
    profile = get_profile(profile_name)
    if profile is None:
        available = ", ".join(list_profiles())
        raise ValueError(f"Unknown profile: {profile_name}. Available: {available}")
    
    return profile.generate(size, rng)
