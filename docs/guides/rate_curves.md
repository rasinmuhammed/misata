---
title: "Rate Curves, Make a Churn or Fraud Rate Rise Over Time"
description: "Declare the exact share of a boolean or categorical outcome per period — churn rising 2% to 9%, fraud climbing through the year — enforced with zero rate-conformance error."
---

# Rate Curves

An **outcome curve** controls *how much* of a numeric column accumulates per period (revenue, volume). A **rate curve** controls *what fraction* of a boolean or categorical outcome is positive per period: a churn rate rising from 2% to 9% over a year, a fraud rate climbing through the holidays, a conversion rate improving each quarter.

This is the Rate-Conformance (RCE) axis from the paper — orthogonal to the aggregate (AME) axis that outcome curves cover. The engine flips exactly `round(n_period × rate)` rows per period, so the realised rate matches your target with **RCE = 0**.

> Pick the right tool: a *magnitude over time* is an [outcome curve](outcome_curves.md); a *rate/proportion over time* is a rate curve; a *static split* with no time component is just categorical `probabilities`.

---

## Declare a rate curve

### Dict schema (`__rate_curves__`)

```python
import misata

schema = {
    "subscriptions": {
        "__rows__": 10000,
        "id":         {"type": "integer", "primary_key": True},
        "churn_date": {"type": "date", "start": "2024-01-01", "end": "2024-12-31"},
        "churned":    {"type": "boolean"},
    },
    "__rate_curves__": [
        {
            "table": "subscriptions",
            "column": "churned",          # the boolean/categorical column
            "time_column": "churn_date",  # buckets rows into periods
            "time_unit": "month",
            "true_value": True,           # the value counted as "positive"
            "interpolate": True,          # linearly fill between anchor points
            "rate_points": [
                {"period": 1,  "rate": 0.02},   # 2% churn in January
                {"period": 12, "rate": 0.09},   # rising to 9% by December
            ],
        }
    ],
}

tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=7))
```

### SchemaConfig (Python API)

```python
from misata.schema import RateCurve

RateCurve(
    table="subscriptions",
    column="churned",
    time_column="churn_date",
    time_unit="month",          # day | week | month | quarter
    true_value=True,
    interpolate=True,
    rate_points=[
        {"period": "2024-01", "rate": 0.02},
        {"period": "2024-12", "rate": 0.09},
    ],
)
```

Attach it via `SchemaConfig(rate_curves=[...])`.

---

## `rate_points`

Each point is `{"period": <p>, "rate": <0..1>}`:

- `period` accepts a `"YYYY-MM"` string, a `"YYYY-Qn"` quarter, or a bare 1-based month index.
- `rate` is the share of rows in that period whose `column` equals `true_value`.
- With `interpolate: True`, rates between anchors are filled linearly; with `False`, only the declared periods are constrained.

## Verify

```python
import pandas as pd
df = tables["subscriptions"]
df["m"] = pd.to_datetime(df["churn_date"]).dt.month
print(df.groupby("m")["churned"].mean())   # ≈ 0.02 … 0.09, monotonic
```

## Natural language & the studio

The LLM schema path extracts rate curves from prompts like *"monthly churn rises from 2% in January to 9% by December"*. In **Misata Studio**, the **Shape** tab has a *Rate curves* designer, and the **Explore** tab overlays the realised rate against your target.

## Common mistakes

- **A static split is not a rate curve.** "70% resolved, 20% pending, 10% escalated" has no time dimension — use categorical `probabilities` instead.
- **Curves belong on measure columns.** A rate curve targets a boolean/categorical column, never an `id`/foreign-key column (the engine drops those).
