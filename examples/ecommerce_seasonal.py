"""
E-Commerce Seasonal Sales
=========================
Generates a 3-table relational dataset: products, customers, orders.
Revenue follows a seasonal curve with Black Friday and December peaks.
Price distributions match real e-commerce (heavily right-skewed).

Run:
    python examples/ecommerce_seasonal.py
"""

import warnings
warnings.filterwarnings("ignore")

import misata
import pandas as pd
import numpy as np

# ── Generate ──────────────────────────────────────────────────────────────────

schema = misata.parse(
    "An ecommerce store with 5000 customers and orders. "
    "Revenue grows from $100k in January to $300k in November (Black Friday) "
    "then $350k in December.",
    rows=5000,
)

schema.seed = 42
tables = misata.generate_from_schema(schema)

customers = tables["customers"]
orders    = tables["orders"]

print()
print("━" * 64)
print("  Misata — E-Commerce Seasonal Sales Demo")
print("━" * 64)
print(f"  Customers: {len(customers):>7,}")
print(f"  Orders:    {len(orders):>7,}")
print(f"  AOV:       ${orders['amount'].mean():>7,.2f}")
print()

# ── Referential integrity ─────────────────────────────────────────────────────

cust_ids = set(customers["customer_id"])
orphan_orders = (~orders["customer_id"].isin(cust_ids)).sum()

print("  Referential integrity")
print(f"  {'customers → orders':<30} {'✓ 0 orphans' if orphan_orders == 0 else f'✗ {orphan_orders} orphans':>18}")
print()

# ── Seasonal revenue curve ────────────────────────────────────────────────────

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

orders_df = orders.copy()
orders_df["month"] = pd.to_datetime(orders_df["order_date"]).dt.month
monthly_rev = orders_df.groupby("month")["amount"].sum()

print("  Monthly revenue  (seasonal: grows through year, peak Dec)")
max_rev = monthly_rev.max()
print(f"  {'Month':<5}  {'Revenue':>12}  {'Trend'}")
print(f"  {'─'*4}  {'─'*12}  {'─'*28}")
for m in range(1, 13):
    rev = monthly_rev.get(m, 0.0)
    bar_len = int(rev / max_rev * 28)
    bar = "█" * bar_len
    peak_flag = "  ← Black Friday" if m == 11 else ("  ← Holiday peak" if m == 12 else "")
    print(f"  {MONTH_NAMES[m-1]:<5}  ${rev:>11,.0f}  {bar}{peak_flag}")
print()

# ── Price distribution — power law ───────────────────────────────────────────

prices = orders_df["amount"].dropna()
p25    = np.percentile(prices, 25)
p50    = np.percentile(prices, 50)
p75    = np.percentile(prices, 75)
p90    = np.percentile(prices, 90)
p99    = np.percentile(prices, 99)

print("  Order amount distribution  (right-skewed, power-law tail)")
print(f"  {'Percentile':<12}  {'Amount':>10}")
print(f"  {'─'*12}  {'─'*10}")
for label, val in [("p25", p25), ("p50 (median)", p50), ("p75", p75),
                   ("p90", p90), ("p99", p99), ("max", prices.max())]:
    print(f"  {label:<12}  ${val:>9,.2f}")
print()
print(f"  Mean / Std:   ${prices.mean():,.2f} / ${prices.std():,.2f}")
print()

# ── Order volume by day of week ───────────────────────────────────────────────

DOW = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
orders_df["dow"] = pd.to_datetime(orders_df["order_date"]).dt.dayofweek
dow_counts = orders_df.groupby("dow").size()

print("  Orders by day of week  (weekend lift is a real e-comm pattern)")
max_dow = dow_counts.max()
for d in range(7):
    n   = dow_counts.get(d, 0)
    pct = n / len(orders_df) * 100
    bar = "█" * int(n / max_dow * 28)
    print(f"  {DOW[d]}  {bar:<28}  {pct:>5.1f}%")

print()
print("━" * 64)
print()
