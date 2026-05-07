"""
Narrative → Data
================
The Misata feature no other synthetic-data library has: write the
*shape* of your business in plain English and the generated rows
follow it exactly.

This example tells a multi-part story — growth, a Q3 dip, a holiday
peak — and verifies the generated data hits each anchor.

Run:
    python examples/narrative_to_data.py
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import pandas as pd

import misata


# ── 1. The narrative ─────────────────────────────────────────────────────────
STORY = (
    "An ecommerce store with 5000 customers. "
    "Order volume rises from 1k in January 2024 to 8k in December 2024, "
    "with a dip in March and a peak in November."
)

# ── 2. Preview before generating ─────────────────────────────────────────────
report = misata.preview(STORY)
print("Detection report:")
print(report.summary())
print()

# ── 3. Generate ──────────────────────────────────────────────────────────────
schema = misata.parse(STORY)
schema.seed = 42
tables = misata.generate_from_schema(schema)
orders = tables["orders"]
print(f"Generated {len(orders):,} orders across {len(tables)} tables.\n")

# ── 4. Verify the narrative shape appears in the data ────────────────────────
orders["__month"] = pd.to_datetime(orders["order_date"]).dt.month
monthly_volume = orders.groupby("__month").size()

print("Monthly order volume:")
for month, count in monthly_volume.items():
    bar = "█" * int(count / max(monthly_volume) * 40)
    print(f"  {pd.Timestamp(2024, int(month), 1).strftime('%b'):>4} {count:>6,}  {bar}")

# ── 5. Sanity checks (the contract this example illustrates) ────────────────
march = int(monthly_volume.get(3, 0))
nov = int(monthly_volume.get(11, 0))
jan = int(monthly_volume.get(1, 0))
dec = int(monthly_volume.get(12, 0))

print()
print(f"  March (dip)      : {march:>6,}")
print(f"  November (peak)  : {nov:>6,}")
print(f"  Jan → Dec growth : {jan:,} → {dec:,}  (×{dec / max(jan, 1):.1f})")

# These hold because the curve was extracted from the story, not random:
assert march < monthly_volume.get(2, 0) or march < monthly_volume.get(4, 0), \
    "Expected a March dip"
assert nov >= monthly_volume.get(10, 0) and nov >= monthly_volume.get(12, 0), \
    "Expected a November peak"
assert dec > jan, "Expected end-of-year growth"

print("\n✓ Narrative shape preserved end-to-end.")
