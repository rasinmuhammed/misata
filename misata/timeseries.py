"""
Time-series generation for Misata.

Generates realistic temporal sequences with trend, seasonality, noise,
and anomaly injection — useful for metrics, sensor data, KPIs, and any
dataset where rows represent observations over time.

Quick start::

    import misata

    # Story-driven
    ts = misata.generate_timeseries(
        "Daily active users for a social app over 2 years, "
        "growing 15% monthly with weekly seasonality and a viral spike in June"
    )

    # Config-driven
    from misata.timeseries import TimeSeriesConfig, Trend, Seasonality, Anomaly

    cfg = TimeSeriesConfig(
        metric="revenue",
        periods=365,
        freq="D",
        start_value=10_000,
        trend=Trend(type="exponential", rate=0.003),
        seasonality=[
            Seasonality(type="weekly",  amplitude=0.25, peak_offset=4),
            Seasonality(type="yearly",  amplitude=0.40, peak_offset=180),
        ],
        noise_std=0.05,
        anomalies=[Anomaly(at_period=170, magnitude=4.0, duration=3)],
    )
    ts = misata.generate_timeseries(config=cfg)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Literal, Optional

import numpy as np
import pandas as pd


# ── Config dataclasses ────────────────────────────────────────────────────────

@dataclass
class Trend:
    """Describes the long-run direction of the series.

    Args:
        type:       "linear" | "exponential" | "stepwise" | "none"
        rate:       Per-period growth rate.
                    Linear: absolute units/period (e.g. 50 → +50/day).
                    Exponential: fractional rate (e.g. 0.003 → +0.3%/day).
        steps:      For stepwise — list of (period_index, new_value) breakpoints.
    """
    type: Literal["linear", "exponential", "stepwise", "none"] = "linear"
    rate: float = 0.0
    steps: List[tuple] = field(default_factory=list)


@dataclass
class Seasonality:
    """A single periodic seasonal component.

    Args:
        type:        "daily" | "weekly" | "monthly" | "yearly"
        amplitude:   Fraction of the local trend value (0.3 → ±30%).
        peak_offset: Period offset where the sine wave peaks.
                     weekly: 0=Mon … 6=Sun. yearly: day-of-year (0–364).
    """
    type: Literal["daily", "weekly", "monthly", "yearly"] = "weekly"
    amplitude: float = 0.20
    peak_offset: int = 0


@dataclass
class Anomaly:
    """A single anomalous event injected into the series.

    Args:
        at_period:  Zero-based period index where the anomaly starts.
        magnitude:  Multiplier applied to the base value (3.0 → 3× spike;
                    -0.5 → drop to 50% of normal).
        duration:   Number of periods the anomaly lasts.
        shape:      "spike" decays exponentially; "flat" stays constant.
    """
    at_period: int = 0
    magnitude: float = 2.0
    duration: int = 1
    shape: Literal["spike", "flat"] = "spike"


@dataclass
class TimeSeriesConfig:
    """Full configuration for a time-series generation run.

    Args:
        metric:      Column name for the generated values.
        periods:     Number of time steps to generate.
        freq:        Pandas frequency alias: "D" daily, "H" hourly,
                     "W" weekly, "ME" month-end, "h" hourly.
        start_date:  ISO date string for the first period.
        start_value: Baseline value at period 0 (before trend/seasonality).
        trend:       Trend configuration (or None for flat).
        seasonality: List of seasonal components to stack.
        noise_std:   Gaussian noise std as a fraction of the local value.
        noise_type:  "gaussian" or "poisson" (integer-count series).
        anomalies:   List of anomaly injections.
        min_value:   Floor the series at this value (useful for counts ≥ 0).
        seed:        Random seed for reproducibility.
    """
    metric: str = "value"
    periods: int = 365
    freq: str = "D"
    start_date: str = "2023-01-01"
    start_value: float = 1000.0
    trend: Optional[Trend] = None
    seasonality: List[Seasonality] = field(default_factory=list)
    noise_std: float = 0.05
    noise_type: Literal["gaussian", "poisson"] = "gaussian"
    anomalies: List[Anomaly] = field(default_factory=list)
    min_value: Optional[float] = 0.0
    seed: Optional[int] = None


# ── Generator ─────────────────────────────────────────────────────────────────

class TimeSeriesGenerator:
    """Generates a time-series DataFrame from a TimeSeriesConfig."""

    def generate(self, config: TimeSeriesConfig) -> pd.DataFrame:
        rng = np.random.default_rng(config.seed)
        n = config.periods
        t = np.arange(n, dtype=float)

        # ── Trend component ──────────────────────────────────────────────────
        trend = np.full(n, config.start_value, dtype=float)
        tr = config.trend or Trend(type="none")

        if tr.type == "linear":
            trend += t * tr.rate

        elif tr.type == "exponential":
            trend = config.start_value * np.exp(tr.rate * t)

        elif tr.type == "stepwise":
            # steps = [(period_idx, new_value), ...]
            sorted_steps = sorted(tr.steps, key=lambda s: s[0])
            level = config.start_value
            for i in range(n):
                for step_t, step_val in sorted_steps:
                    if i == step_t:
                        level = step_val
                trend[i] = level

        # ── Seasonal components ───────────────────────────────────────────────
        seasonal = np.zeros(n)
        dates = pd.date_range(config.start_date, periods=n, freq=config.freq)

        for s in config.seasonality:
            amp = s.amplitude
            if s.type == "weekly":
                period = 7
                phase = (dates.dayofweek - s.peak_offset) * (2 * np.pi / period)
            elif s.type == "daily":
                period = 24
                phase = (dates.hour - s.peak_offset) * (2 * np.pi / period)
            elif s.type == "monthly":
                period = 30
                phase = (dates.day - s.peak_offset) * (2 * np.pi / period)
            elif s.type == "yearly":
                period = 365
                phase = (dates.dayofyear - s.peak_offset) * (2 * np.pi / period)
            else:
                continue
            seasonal += amp * np.sin(phase)

        base = trend * (1 + seasonal)

        # ── Noise ─────────────────────────────────────────────────────────────
        if config.noise_type == "poisson":
            noisy = rng.poisson(np.maximum(base, 1e-9)).astype(float)
        else:
            noise = rng.normal(0, config.noise_std, n) * base
            noisy = base + noise

        # ── Anomalies ────────────────────────────────────────────────────────
        is_anomaly = np.zeros(n, dtype=bool)
        for a in config.anomalies:
            start = max(0, a.at_period)
            end   = min(n, start + a.duration)
            is_anomaly[start:end] = True
            if a.shape == "spike":
                # Exponential decay from peak magnitude
                for j, idx in enumerate(range(start, end)):
                    decay = np.exp(-j * 1.2)
                    noisy[idx] *= 1 + (a.magnitude - 1) * decay
            else:
                noisy[start:end] *= a.magnitude

        # ── Floor ─────────────────────────────────────────────────────────────
        if config.min_value is not None:
            noisy = np.maximum(noisy, config.min_value)

        return pd.DataFrame({
            "date":       dates,
            config.metric: np.round(noisy, 2),
            "trend":      np.round(trend, 2),
            "seasonal":   np.round(trend * seasonal, 2),
            "is_anomaly": is_anomaly,
        })


# ── Story parser ──────────────────────────────────────────────────────────────

def _parse_timeseries_story(story: str) -> TimeSeriesConfig:
    """Extract TimeSeriesConfig fields from a plain-English story."""
    s = story.lower()

    # Metric name
    metric_map = {
        r"daily active users?|dau": "daily_active_users",
        r"monthly active users?|mau": "monthly_active_users",
        r"revenue|mrr|arr": "revenue",
        r"orders?": "orders",
        r"sessions?": "sessions",
        r"signups?|registrations?": "signups",
        r"page views?|pageviews?": "page_views",
        r"sensor|temperature|humidity|pressure": "sensor_value",
        r"stock|price|close": "price",
        r"downloads?": "downloads",
    }
    metric = "value"
    for pattern, name in metric_map.items():
        if re.search(pattern, s):
            metric = name
            break

    # Periods / horizon
    periods = 365
    m = re.search(r"(\d+)\s*(year|yr)", s)
    if m:
        periods = int(m.group(1)) * 365
    m = re.search(r"(\d+)\s*month", s)
    if m:
        periods = int(m.group(1)) * 30
    m = re.search(r"(\d+)\s*(week|wk)", s)
    if m:
        periods = int(m.group(1)) * 7
    m = re.search(r"(\d+)\s*day", s)
    if m:
        periods = int(m.group(1))

    # Frequency — match explicit cadence phrases, not seasonality adjectives
    freq = "D"
    if re.search(r"hourly|per hour|every hour|each hour", s):
        freq = "h"
    elif re.search(r"per week|every week|each week|weekly data|weekly readings", s):
        freq = "W"
    elif re.search(r"per month|every month|each month|monthly data|monthly readings", s):
        freq = "ME"

    # Start value
    start_value = 1000.0
    m = re.search(r"starting (?:at |from |with )?[\$£€]?([\d,]+\.?\d*)[kKmM]?", s)
    if m:
        raw = float(m.group(1).replace(",", ""))
        if re.search(r"[kK]", s[m.end():m.end()+1]):
            raw *= 1000
        elif re.search(r"[mM]", s[m.end():m.end()+1]):
            raw *= 1_000_000
        start_value = raw

    # Trend
    trend: Optional[Trend] = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:monthly|daily|weekly|annual|yearly)?\s*(?:growth|growing|increase|rising)", s)
    if m:
        rate_pct = float(m.group(1)) / 100
        if "daily" in s[max(0, m.start()-5):m.end()+5]:
            trend = Trend(type="exponential", rate=rate_pct)
        elif "weekly" in s[max(0, m.start()-5):m.end()+5]:
            trend = Trend(type="exponential", rate=rate_pct / 7)
        else:
            trend = Trend(type="exponential", rate=rate_pct / 30)
    elif re.search(r"growing|growth|rising|increasing|upward", s):
        trend = Trend(type="exponential", rate=0.002)
    elif re.search(r"declining|falling|decreasing|downward", s):
        trend = Trend(type="exponential", rate=-0.001)
    else:
        trend = Trend(type="linear", rate=0.0)

    # Seasonality
    seasonality: List[Seasonality] = []
    if re.search(r"weekly seasonality|day.of.week|weekday|weekend", s):
        seasonality.append(Seasonality(type="weekly", amplitude=0.30, peak_offset=1))
    if re.search(r"yearly|annual|seasonal|summer|winter|holiday", s):
        seasonality.append(Seasonality(type="yearly", amplitude=0.40, peak_offset=180))
    if re.search(r"monthly|end.of.month|month.end", s):
        seasonality.append(Seasonality(type="monthly", amplitude=0.20, peak_offset=28))
    if re.search(r"hourly|intraday|rush.hour|morning.peak", s):
        seasonality.append(Seasonality(type="daily", amplitude=0.50, peak_offset=9))

    # Anomalies
    anomalies: List[Anomaly] = []
    if re.search(r"viral|spike|launch|surge|breakout", s):
        at = int(periods * 0.4)
        anomalies.append(Anomaly(at_period=at, magnitude=4.0, duration=3, shape="spike"))
    if re.search(r"crash|outage|dip|drop|incident", s):
        at = int(periods * 0.7)
        anomalies.append(Anomaly(at_period=at, magnitude=0.1, duration=2, shape="flat"))

    return TimeSeriesConfig(
        metric=metric,
        periods=periods,
        freq=freq,
        start_value=start_value,
        trend=trend,
        seasonality=seasonality,
        noise_std=0.05,
        anomalies=anomalies,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def generate_timeseries(
    story: Optional[str] = None,
    *,
    config: Optional[TimeSeriesConfig] = None,
    metric: str = "value",
    periods: int = 365,
    freq: str = "D",
    start_date: str = "2023-01-01",
    start_value: float = 1000.0,
    trend: Optional[Trend] = None,
    seasonality: Optional[List[Seasonality]] = None,
    noise_std: float = 0.05,
    anomalies: Optional[List[Anomaly]] = None,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """Generate a time-series DataFrame.

    Can be driven by a plain-English story, a ``TimeSeriesConfig`` object,
    or keyword arguments.  Story and kwargs are merged — explicit kwargs
    override story inference.

    Args:
        story:       Plain-English description of the time series.
        config:      Pre-built ``TimeSeriesConfig`` (takes full precedence).
        metric:      Column name for the generated metric values.
        periods:     Number of time steps.
        freq:        Pandas frequency alias ("D" daily, "h" hourly, "W" weekly, "ME" monthly).
        start_date:  ISO date string for period 0.
        start_value: Baseline value before trend/seasonality.
        trend:       ``Trend`` object (linear, exponential, stepwise).
        seasonality: List of ``Seasonality`` components to stack.
        noise_std:   Gaussian noise as a fraction of the local value.
        anomalies:   List of ``Anomaly`` events to inject.
        seed:        Random seed.

    Returns:
        DataFrame with columns: ``date``, ``<metric>``, ``trend``,
        ``seasonal``, ``is_anomaly``.

    Example::

        ts = misata.generate_timeseries(
            "Daily active users over 1 year, growing 10% monthly "
            "with weekly seasonality and a viral spike",
            start_value=5000,
            seed=42,
        )
        ts.plot(x="date", y="daily_active_users")
    """
    if config is not None:
        return TimeSeriesGenerator().generate(config)

    # Start from story inference if provided
    if story:
        cfg = _parse_timeseries_story(story)
    else:
        cfg = TimeSeriesConfig()

    # Explicit kwargs override story inference
    if metric != "value":
        cfg.metric = metric
    if periods != 365:
        cfg.periods = periods
    if freq != "D":
        cfg.freq = freq
    if start_date != "2023-01-01":
        cfg.start_date = start_date
    if start_value != 1000.0:
        cfg.start_value = start_value
    if trend is not None:
        cfg.trend = trend
    if seasonality is not None:
        cfg.seasonality = seasonality
    if noise_std != 0.05:
        cfg.noise_std = noise_std
    if anomalies is not None:
        cfg.anomalies = anomalies
    if seed is not None:
        cfg.seed = seed

    return TimeSeriesGenerator().generate(cfg)
