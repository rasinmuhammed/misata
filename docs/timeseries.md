# Time Series

Generate realistic temporal sequences with trend, seasonality, noise, and anomaly injection — metrics, sensor data, KPIs, DAU curves, revenue forecasts.

## Quick start

```python
import misata

# Story-driven — Misata infers everything from plain English
ts = misata.generate_timeseries(
    "Daily active users over 1 year, growing 10% monthly "
    "with weekly seasonality and a viral spike",
    start_value=5_000,
    seed=42,
)

print(ts.head())
#         date  daily_active_users    trend  seasonal  is_anomaly
# 2023-01-01             4812.3   5000.0    -187.7       False
# 2023-01-02             5231.4   5010.0     221.4       False
# ...

ts.plot(x="date", y="daily_active_users")
```

## Config-driven

```python
from misata.timeseries import TimeSeriesConfig, Trend, Seasonality, Anomaly

config = TimeSeriesConfig(
    metric="revenue",
    periods=365,
    freq="D",                        # "D" daily | "h" hourly | "W" weekly | "ME" monthly
    start_date="2024-01-01",
    start_value=10_000,
    trend=Trend(type="exponential", rate=0.003),   # ~0.3%/day compound growth
    seasonality=[
        Seasonality(type="weekly",  amplitude=0.25, peak_offset=4),   # Fri peak
        Seasonality(type="yearly",  amplitude=0.40, peak_offset=355), # Dec peak
    ],
    noise_std=0.05,
    noise_type="gaussian",           # "gaussian" or "poisson" (for count data)
    anomalies=[
        Anomaly(at_period=170, magnitude=4.0, duration=3, shape="spike"),  # viral moment
        Anomaly(at_period=290, magnitude=0.2, duration=1, shape="flat"),   # outage
    ],
    min_value=0.0,
    seed=42,
)

ts = misata.generate_timeseries(config=config)
```

## Output columns

| Column | Description |
|:--|:--|
| `date` | Timestamp at the chosen frequency |
| `<metric>` | The generated value (trend + seasonal + noise + anomalies) |
| `trend` | Pure trend component (no seasonality or noise) |
| `seasonal` | Seasonal contribution added to trend |
| `is_anomaly` | `True` for periods covered by an `Anomaly` |

## Story inference

The story parser extracts:

- **Metric name** — "daily active users" → `daily_active_users`, "revenue" → `revenue`
- **Periods** — "over 2 years" → 730 days; "for 6 months" → 180 days
- **Trend** — "growing 15% monthly" → exponential rate=0.005; "declining" → negative rate
- **Seasonality** — "weekly seasonality" → weekly component; "summer peak" → yearly component
- **Anomalies** — "viral spike" → 4× magnitude spike; "outage" or "crash" → 0.1× drop

## Trend types

| `type` | Description | Key param |
|:--|:--|:--|
| `linear` | Constant absolute growth per period | `rate` (units/period) |
| `exponential` | Compounding percentage growth | `rate` (fraction/period, e.g. 0.003) |
| `stepwise` | Step-function changes at specified periods | `steps` list of `(period, value)` |
| `none` | Flat baseline | — |

## Seasonality types

| `type` | Period | `peak_offset` unit |
|:--|:--|:--|
| `daily` | 24 hours | Hour of day (0–23) |
| `weekly` | 7 days | Day of week (0=Mon … 6=Sun) |
| `monthly` | 30 days | Day of month (1–28) |
| `yearly` | 365 days | Day of year (0–364) |

## Multiple series

```python
# Generate correlated series manually
import pandas as pd

dau = misata.generate_timeseries("Daily active users, growing 8% monthly", start_value=10_000, seed=1)
rev = misata.generate_timeseries("Revenue, growing 12% monthly with weekly seasonality", start_value=5_000, seed=2)

combined = dau[["date", "daily_active_users"]].merge(rev[["date", "revenue"]], on="date")
combined["arpu"] = combined["revenue"] / combined["daily_active_users"]
```
