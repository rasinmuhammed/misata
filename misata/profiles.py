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

        elif self.distribution == "spikes":
            # Discrete mass points with weights: real-world columns like
            # discount percentages sit on a handful of round values
            # (5/10/15/20/25/50), not on a smooth curve.
            points = np.array(self.params.get("values", [0.0]), dtype=float)
            weights = np.array(
                self.params.get("weights", [1.0] * len(points)), dtype=float)
            weights = weights / weights.sum()
            values = rng.choice(points, size=size, p=weights)
        
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


# Event timing: waits between independent events are exponential (the Poisson
# arrival assumption holds well for support tickets, purchases, log lines).
# Scale 600s puts the median wait near 7 minutes; declared bounds reshape it.
_register_profile(DistributionProfile(
    name="interarrival_seconds",
    distribution="exponential",
    params={"scale": 600.0},
    min_value=1,
    max_value=86400,
    decimals=0,
))

# Social counts are heavy-tailed: most accounts sit in the tens, a few in
# the millions. Pareto alpha 1.35 over a floor of 25 puts the median near
# 40 while the mean is dragged several times higher by the tail, the shape
# every real follower/view/like column shows under an audit.
_register_profile(DistributionProfile(
    name="social_count",
    distribution="pareto",
    params={"alpha": 1.35, "min": 25.0},
    min_value=0,
    max_value=50_000_000,
    decimals=0,
))

# Discounts sit on marketing's round numbers, not on a curve. Weights lean
# on the common 10/20/25; 50 is the clearance spike.
_register_profile(DistributionProfile(
    name="discount_percent",
    distribution="spikes",
    params={
        "values":  [5, 10, 15, 20, 25, 50],
        "weights": [15, 30, 15, 20, 12, 8],
    },
    min_value=0,
    max_value=100,
    decimals=0,
))

# Customer tenure: exponential survival, most customers are recent, a long
# tail has been around for years. The column-level face of cohort churn.
_register_profile(DistributionProfile(
    name="tenure_months",
    distribution="exponential",
    params={"scale": 14.0},
    min_value=0,
    max_value=120,
    decimals=0,
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


# ============ Semantic routing: the statistical priors knowledge base ============
#
# A column NAME carries distributional knowledge: a rating is J-shaped toward
# 5, an order quantity is mostly 1, a salary is lognormal, retail prices end
# in .99. The profiles above encode those shapes; this router applies them
# automatically whenever the user declared no shape of their own, so realism
# is the default instead of an opt-in. Explicit distribution/mean/std/mu/sigma
# always win; declared min/max bounds are respected by clipping.

# (predicate on lowercased name, profile name, treat_as)
# treat_as: "value" (use as-is), "price" (snap to retail endings),
#           "unit_rate" (normalise 0-100 output to 0-1 for *_rate columns)
def _r_rating(n):   return n in ("rating", "stars", "star_rating") or n.endswith("_rating")
def _r_age(n):      return n in ("age", "age_years", "customer_age", "user_age")
def _r_salary(n):   return "salary" in n or n in ("annual_income", "income")
def _r_price(n):    return n in ("price", "unit_price", "list_price", "item_price", "retail_price")
def _r_qty(n):      return n in ("quantity", "qty", "order_quantity", "items_per_order")
def _r_session(n):  return n in ("session_duration", "session_duration_seconds",
                                 "duration_seconds", "session_length_seconds")
def _r_txn(n):      return n == "transaction_amount"
def _r_conv(n):     return n in ("conversion_rate", "signup_rate", "click_through_rate", "ctr")
def _r_churn(n):    return n in ("churn_rate", "attrition_rate", "cancellation_rate")
def _r_nps(n):      return n in ("nps", "nps_score")
def _r_interarrival(n):
    return ("interarrival" in n or "inter_arrival" in n or "time_between" in n
            or n in ("seconds_since_last_event", "time_since_last_seconds",
                     "gap_seconds"))
def _r_social(n):
    return n in ("followers", "follower_count", "followers_count",
                 "following_count", "views", "view_count", "video_views",
                 "likes", "like_count", "likes_count", "shares",
                 "share_count", "subscribers", "subscriber_count",
                 "upvotes", "retweets", "reposts", "impressions",
                 "comment_count", "comments_count", "play_count")
def _r_discount(n):
    return n in ("discount", "discount_percent", "discount_pct",
                 "discount_percentage", "discount_rate", "promo_discount")
def _r_tenure(n):
    return n in ("tenure_months", "customer_tenure", "months_active",
                 "tenure", "subscription_months")

_SEMANTIC_ROUTES = [
    (_r_rating,      "rating_5star",             "value"),
    (_r_age,         "age_adult",                "value"),
    (_r_salary,      "salary_usd",               "value"),
    (_r_price,       "price_retail",             "price"),
    (_r_qty,         "order_quantity",           "value"),
    (_r_session,     "session_duration_seconds", "value"),
    (_r_txn,         "transaction_amount",       "money"),
    (_r_conv,        "conversion_rate",          "unit_rate"),
    (_r_churn,       "churn_rate",               "unit_rate"),
    (_r_nps,         "nps_score",                "value"),
    (_r_interarrival, "interarrival_seconds",    "value"),
    (_r_social,      "social_count",             "value"),
    (_r_discount,    "discount_percent",         "unit_rate"),
    (_r_tenure,      "tenure_months",            "value"),
]

# Retail price endings and how often each occurs; most real price tags end
# in .99, a chunk in .95/.49/.00. Applied to ~85% of price draws, the rest
# keep organic cents so the column is not suspiciously uniform.
_PRICE_ENDINGS = ([0.99] * 45 + [0.95] * 12 + [0.49] * 10 + [0.00] * 18)

# Locale-aware economics. The price/transaction profiles are calibrated in
# USD; a locale whose currency runs at a different magnitude gets its money
# columns scaled by a rough purchasing-magnitude factor (JPY prices in the
# thousands, INR in the hundreds-to-thousands). Charm pricing also varies:
# .99 dominance is an anglosphere habit; euro-zone tags lean on round and
# .50 endings, and zero-decimal currencies (JPY, KRW) carry no cents at all.
_CURRENCY_FX = {
    "USD": 1.0, "GBP": 0.8, "EUR": 0.95, "CAD": 1.35, "AUD": 1.5,
    "INR": 84.0, "JPY": 150.0, "KRW": 1350.0, "CNY": 7.2, "BRL": 5.4,
    "PLN": 4.0, "TRY": 34.0, "SAR": 3.75,
}
_ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW"}
_EURO_PRICE_ENDINGS = ([0.99] * 25 + [0.95] * 10 + [0.50] * 20 + [0.00] * 45)
_EURO_CURRENCIES = {"EUR"}


def _locale_currency(locale: Optional[str]) -> str:
    """Currency code for a locale, USD when unknown or unset.

    Falls back on the country suffix when the exact key misses (packs are
    keyed by one canonical language per country, so ``en_IN`` finds the
    ``hi_IN`` pack and its INR)."""
    if not locale or locale == "en_US":
        return "USD"
    try:
        from misata.locales.packs import LOCALE_PACKS
        pack = LOCALE_PACKS.get(locale)
        if pack is None and "_" in str(locale):
            suffix = "_" + str(locale).rsplit("_", 1)[1]
            pack = next(
                (p for k, p in LOCALE_PACKS.items() if k.endswith(suffix)),
                None,
            )
        return getattr(pack, "currency_code", None) or "USD"
    except Exception:
        return "USD"


def match_profile(column_name: str) -> Optional[str]:
    """Return the profile name the semantic router would apply, or None."""
    n = str(column_name).lower()
    for pred, profile, _mode in _SEMANTIC_ROUTES:
        if pred(n):
            return profile
    return None


def sample_semantic(
    column_name: str,
    params: Dict[str, Any],
    rng: np.random.Generator,
    size: int,
    locale: Optional[str] = None,
) -> Optional[np.ndarray]:
    """Draw from the priors knowledge base for a recognised column name.

    Returns None when no profile matches, so the caller falls through to its
    generic path. Declared ``min``/``max`` clip the draw; declared ``decimals``
    override the profile's rounding. When a ``locale`` is given, money columns
    (price and transaction amounts) scale to that locale's currency magnitude
    and adopt its price-ending habits.
    """
    n = str(column_name).lower()
    route = next(((prof, mode) for pred, prof, mode in _SEMANTIC_ROUTES if pred(n)), None)
    if route is None:
        return None
    profile_name, mode = route
    profile = PROFILES.get(profile_name)
    if profile is None:
        return None

    values = profile.generate(size, rng=rng)

    divided_to_unit = False
    if mode == "unit_rate" and n.endswith(("_rate", "_ratio", "_share", "_probability")):
        # The percent-scaled profile output becomes a 0-1 fraction, matching
        # the library-wide convention that *_rate columns live in 0-1.
        values = values / 100.0
        divided_to_unit = True

    currency = _locale_currency(locale) if mode in ("price", "money") else "USD"
    if mode in ("price", "money") and currency != "USD":
        values = values * _CURRENCY_FX.get(currency, 1.0)

    if mode == "price":
        if currency in _ZERO_DECIMAL_CURRENCIES:
            # No cents exist; round prices dominate, with a charm-digit tail.
            values = np.round(values, -1)
            charm = rng.random(size) < 0.3
            values = np.where(charm, np.maximum(values - 10, 0) + rng.choice([8.0, 9.0], size=size), values)
            values = np.maximum(values, 1)
        else:
            endings_pool = (_EURO_PRICE_ENDINGS if currency in _EURO_CURRENCIES
                            else _PRICE_ENDINGS)
            snap = rng.random(size) < 0.85
            endings = rng.choice(endings_pool, size=size)
            values = np.where(snap, np.floor(values) + endings, np.round(values, 2))
            values = np.maximum(values, 0.49)
    elif mode == "money" and currency in _ZERO_DECIMAL_CURRENCIES:
        values = np.round(values)

    lo, hi = params.get("min"), params.get("max")
    if isinstance(lo, (int, float)):
        values = np.maximum(values, float(lo))
    if isinstance(hi, (int, float)):
        values = np.minimum(values, float(hi))
    decimals = params.get("decimals", profile.decimals)
    if divided_to_unit and "decimals" not in params:
        # A whole-number percent profile (like the discount spikes) would
        # round its 0-1 form back to zero; a fraction needs 2 decimals.
        decimals = max(int(decimals or 0), 2)
    if mode in ("price", "money") and currency in _ZERO_DECIMAL_CURRENCIES:
        decimals = 0
    if decimals is not None:
        values = np.round(values, int(decimals))
    return values
