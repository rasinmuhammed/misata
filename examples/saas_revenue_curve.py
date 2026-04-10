"""
SaaS Revenue Curve
==================
Misata can pin exact monthly aggregate targets to generated rows.
"Revenue rises from $50k in January to $200k in December with a dip in September"
is not a visual effect — the rows actually sum to those numbers.

Run:
    python examples/saas_revenue_curve.py
"""

import warnings
warnings.filterwarnings("ignore")

import misata
import pandas as pd
import numpy as np

# ── 1. Generate ──────────────────────────────────────────────────────────────

schema = misata.parse(
    "A SaaS company with 1000 users. "
    "MRR rises from $50k in January to $200k in December with a dip in September.",
    rows=1000,
)

tables = misata.generate_from_schema(schema)
users         = tables["users"]
subscriptions = tables["subscriptions"]

# ── 2. Monthly MRR: target vs actual ─────────────────────────────────────────

curve        = schema.outcome_curves[0]
targets      = {pt["month"]: pt["target_value"] for pt in curve.curve_points}
MONTH_NAMES  = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

subs = subscriptions.copy()
subs["month"] = pd.to_datetime(subs["start_date"]).dt.month
monthly_actual = subs.groupby("month")["mrr"].sum()

print()
print("━" * 62)
print("  Misata — SaaS Revenue Curve Demo")
print("━" * 62)
print(f"  Users generated:         {len(users):>6,}")
print(f"  Subscriptions generated: {len(subscriptions):>6,}")
print()
print(f"  {'Month':<6}  {'Target MRR':>12}  {'Actual MRR':>12}  {'Match':>6}")
print(f"  {'─'*5:<6}  {'─'*12}  {'─'*12}  {'─'*5}")

all_match = True
for m in range(1, 13):
    target = targets.get(m, 0)
    actual = monthly_actual.get(m, 0)
    diff   = abs(target - actual)
    match  = "✓" if diff < 0.02 else f"Δ{diff:.2f}"
    if diff >= 0.02:
        all_match = False
    print(f"  {MONTH_NAMES[m-1]:<6}  ${target:>11,.0f}  ${actual:>11,.0f}  {match:>6}")

print()
if all_match:
    print("  ✓ All 12 monthly targets hit exactly.")
print()

# ── 3. MRR distribution — log-normal proof ───────────────────────────────────

mrr = subscriptions["mrr"].dropna().astype(float)
print(f"  MRR distribution (real SaaS is right-skewed, not uniform)")
print(f"  {'Median':>10}  {'Mean':>10}  {'p90':>10}  {'Max':>10}")
print(f"  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*10}")
print(f"  ${np.median(mrr):>9,.0f}  ${mrr.mean():>9,.0f}  "
      f"${np.percentile(mrr,90):>9,.0f}  ${mrr.max():>9,.0f}")
print()
print("  A few big customers. Many small ones. Log-normal.")
print()

# ── 4. Plan breakdown ─────────────────────────────────────────────────────────

plan_counts = subscriptions["status"].value_counts()
print(f"  Subscription status breakdown")
for status, count in plan_counts.items():
    bar = "█" * int(count / len(subscriptions) * 30)
    pct = count / len(subscriptions) * 100
    print(f"  {status:<12} {bar:<30} {pct:>5.1f}%")

print()
print("━" * 62)
print()
