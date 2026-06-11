"""
Numeric quantization profiles: human-chosen quantities land on the values
humans actually choose.

Raw generation draws numbers straight from a distribution, which produces
appointment durations of 7, 19 and 35 minutes and prices like 43.2714 —
no scheduling system books a 19-minute slot and no shop charges $43.27.
After nanosecond timestamps, off-grid "chosen" numbers are the next
fastest "this data is fake" tell.

Real-world numeric columns are quantised by who picks the value:

  - SCHEDULED durations (appointment/meeting/booking minutes) snap to the
    slot grid a calendar UI offers: 15, 30, 45, 60 — with 5/10 for short
    visits and half-hour steps beyond two hours.
  - PRICES in retail-ish domains (price, fee, amount, cost) end the way
    merchants end them: .99, .95 or .00 — never uniform random cents.
  - AGES are integers; nobody is 34.7 years old.
  - PERCENTAGES carry sensible precision (one decimal on a 0–100 scale,
    three on a 0–1 fraction), not float64 noise.

Measured quantities (gaming session lengths, watch time, flight durations,
fintech transaction amounts) legitimately fall anywhere and are left alone:
classification requires both the right column-name stem and, for prices,
a retail-ish domain. Application is vectorised, seeded per column, and
opted out per column with ``distribution_params={"quantize": False}``.
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

DURATION_GRID_MINUTES = np.array(
    [5, 10, 15, 30, 45, 60, 75, 90, 105, 120], dtype=float
)

CHARM_ENDINGS = np.array([0.99, 0.95, 0.00])
CHARM_WEIGHTS = np.array([0.50, 0.15, 0.35])

# Domains where displayed prices are merchant-chosen (and therefore charm).
# Fintech transaction amounts or healthcare claim totals are sums/measurements
# and keep their arbitrary cents.
CHARM_DOMAINS = frozenset(
    {"ecommerce", "e-commerce", "ecom", "retail", "store", "shop",
     "marketplace", "saas", "subscription"}
)

# Scheduled-event context: only durations booked through a calendar UI snap
# to the slot grid. A gaming session or a movie runtime is measured, not chosen.
_SCHEDULED_CONTEXT = re.compile(
    r"appointment|appt|meeting|booking|reservation|interview|"
    r"consultation|checkup|visit|class|lesson|demo|slot"
)

# Unit tokens that mark a duration as NOT minutes-denominated.
_NON_MINUTE_UNITS = frozenset(
    {"second", "seconds", "sec", "secs", "ms", "hour", "hours", "hrs",
     "day", "days", "week", "weeks", "month", "months", "year", "years"}
)

_PRICE_TOKENS = frozenset({"price", "prices", "fee", "fees", "amount", "cost"})


def _tokens(name: str) -> list[str]:
    return re.split(r"[^a-z0-9]+", name.lower())


def classify_quantization(
    column_name: str,
    table_name: str = "",
    domain: Optional[str] = None,
) -> Optional[str]:
    """Pick the quantization profile for a numeric column from its name.

    Returns one of ``"duration_grid"``, ``"charm_price"``, ``"age"``,
    ``"percentage"`` or ``None`` (leave the raw draw untouched).
    """
    toks = _tokens(column_name)
    haystack = f"{table_name} {column_name}".lower()

    if "duration" in toks or "duration" in haystack:
        minutes_denominated = not any(t in _NON_MINUTE_UNITS for t in toks)
        if minutes_denominated and _SCHEDULED_CONTEXT.search(haystack):
            return "duration_grid"
        return None

    if any(t in _PRICE_TOKENS for t in toks):
        if domain and domain.lower() in CHARM_DOMAINS:
            return "charm_price"
        return None

    if "age" in toks:
        return "age"

    if any(t in ("percent", "percentage", "pct") for t in toks):
        return "percentage"

    return None


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


def _snap_duration_grid(values: np.ndarray) -> np.ndarray:
    """Snap minute durations to calendar slot sizes (15/30/45/60-style)."""
    v = values.astype(float)
    grid = DURATION_GRID_MINUTES
    idx = np.clip(np.searchsorted(grid, v), 1, len(grid) - 1)
    lower, upper = grid[idx - 1], grid[idx]
    snapped = np.where((v - lower) <= (upper - v), lower, upper)
    # Beyond the grid, real calendars step in half hours.
    long = v > grid[-1]
    if long.any():
        snapped[long] = np.round(v[long] / 30.0) * 30.0
    return snapped


def _charm_prices(values: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Replace random cents with merchant endings (.99/.95/.00).

    Zeros (structural, e.g. zero-inflated free tiers) and negatives are
    preserved untouched.
    """
    v = values.astype(float)
    out = v.copy()
    mask = np.isfinite(v) & (v > 0)
    if not mask.any():
        return out
    dollars = np.maximum(np.round(v[mask]), 1.0)
    endings = rng.choice(CHARM_ENDINGS, size=int(mask.sum()), p=CHARM_WEIGHTS)
    # 43.27 → 42.99 / 42.95 / 43.00
    out[mask] = np.where(endings > 0.0, dollars - 1.0 + endings, dollars)
    return out


def _round_percentage(values: np.ndarray) -> np.ndarray:
    v = values.astype(float)
    finite = v[np.isfinite(v)]
    # 0–100 scale gets one decimal; 0–1 fractions keep three.
    if finite.size and np.abs(finite).max() > 1.5:
        return np.round(v, 1)
    return np.round(v, 3)


def apply_quantization(
    values: np.ndarray,
    profile: str,
    rng: np.random.Generator,
) -> np.ndarray:
    """Apply ``profile`` to raw draws. Vectorised; deterministic under ``rng``."""
    values = np.asarray(values)
    if values.size == 0:
        return values

    if profile == "duration_grid":
        return _snap_duration_grid(values)
    if profile == "charm_price":
        return _charm_prices(values, rng)
    if profile == "age":
        return np.round(values.astype(float), 0)
    if profile == "percentage":
        return _round_percentage(values)
    return values
