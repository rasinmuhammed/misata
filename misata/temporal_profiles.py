"""
Temporal realism profiles: every timestamp gets the granularity its
semantics demand.

Raw generation draws datetimes as uniform random nanosecond integers, which
produces values like ``2022-08-29 06:36:12.995319155`` for an appointment —
nanosecond precision, 6 AM, a Sunday. No real scheduling system emits that,
and it is one of the fastest "this data is fake" tells.

Real-world timestamps are quantised and rhythmic, by mechanism:

  - SCHEDULED events (appointments, meetings, interviews) snap to 15-minute
    grids inside business hours, almost never on weekends.
  - HUMAN actions (signups, orders, payments, logins) happen at second
    resolution following waking-hour rhythms.
  - MACHINE events (logs, clicks, telemetry) are the only timestamps that
    legitimately carry sub-second precision, around the clock.
  - VITAL dates (birth dates, expiry dates) are dates, not times.

Classification is by column-name stem (mechanism is encoded in how people
name columns), application is vectorised and seeded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemporalProfile:
    name: str
    hour_weights: Optional[list] = None   # 24 weights; None = use domain rhythm
    minute_grid: Optional[int] = None     # snap minutes to this grid (e.g. 15)
    seconds: str = "uniform"              # "zero" | "uniform" | "subsecond"
    weekend_factor: float = 1.0           # probability multiplier for keeping weekend days
    date_only: bool = False


BUSINESS_HOURS = [0, 0, 0, 0, 0, 0, 0, 2, 8, 14, 16, 15, 10, 13, 16, 15, 13, 9, 4, 1, 0, 0, 0, 0]

SCHEDULED = TemporalProfile(
    name="scheduled",
    hour_weights=BUSINESS_HOURS,
    minute_grid=15,
    seconds="zero",
    weekend_factor=0.08,
)
HUMAN_ACTION = TemporalProfile(name="human_action", seconds="uniform")
MACHINE_EVENT = TemporalProfile(name="machine_event", seconds="subsecond")
DATE_ONLY = TemporalProfile(name="date_only", date_only=True)

# Stem → profile. Checked in order; first match wins.
_PROFILE_PATTERNS = [
    (re.compile(
        r"appointment|meeting|booking|scheduled|reservation|interview|"
        r"visit|session|demo|call|consultation|checkup|class|lesson"
    ), SCHEDULED),
    (re.compile(r"birth|dob\b|date_of_birth|expir|due_date|valid_until|maturity"), DATE_ONLY),
    (re.compile(
        r"log|click|event_|_event|request|error|ping|trace|telemetry|"
        r"impression|pageview|heartbeat"
    ), MACHINE_EVENT),
]


def classify_temporal(column_name: str, table_name: str = "") -> TemporalProfile:
    """Pick the temporal profile for a datetime column from its name."""
    haystack = f"{table_name} {column_name}".lower()
    for pattern, profile in _PROFILE_PATTERNS:
        if pattern.search(haystack):
            return profile
    return HUMAN_ACTION


def apply_temporal_profile(
    dates: pd.DatetimeIndex,
    profile: TemporalProfile,
    rng: np.random.Generator,
    domain_hour_weights: Optional[list] = None,
) -> pd.DatetimeIndex:
    """Re-shape times-of-day (and weekend density) without moving the date
    distribution: the day each row lands on is preserved except for the
    weekend damping shift of ±1–2 days, so outcome curves and FK-relative
    ranges stay intact."""
    size = len(dates)
    if size == 0:
        return dates

    days = dates.normalize()

    if profile.date_only:
        return days

    # Weekend damping: most scheduled events move Sat→Fri, Sun→Mon.
    if profile.weekend_factor < 1.0:
        dow = days.dayofweek.values
        keep = rng.random(size) < profile.weekend_factor
        shift = np.zeros(size, dtype="int64")
        shift[(dow == 5) & ~keep] = -1   # Saturday → Friday
        shift[(dow == 6) & ~keep] = 1    # Sunday → Monday
        if shift.any():
            days = days + pd.to_timedelta(shift, unit="D")

    weights = profile.hour_weights or domain_hour_weights
    if weights is not None:
        hw = np.asarray(weights, dtype=float)
        hw = hw / hw.sum()
        hours = rng.choice(24, size=size, p=hw)
    else:
        hours = rng.integers(0, 24, size=size)

    if profile.minute_grid:
        slots = 60 // profile.minute_grid
        minutes = rng.integers(0, slots, size=size) * profile.minute_grid
    else:
        minutes = rng.integers(0, 60, size=size)

    if profile.seconds == "zero":
        seconds_ns = np.zeros(size, dtype="int64")
    elif profile.seconds == "subsecond":
        seconds_ns = rng.integers(0, 60, size=size) * 1_000_000_000 + rng.integers(0, 1000, size=size) * 1_000_000
    else:
        seconds_ns = rng.integers(0, 60, size=size) * 1_000_000_000

    offset_ns = (hours.astype("int64") * 3600 + minutes.astype("int64") * 60) * 1_000_000_000 + seconds_ns
    return days + pd.to_timedelta(offset_ns, unit="ns")
