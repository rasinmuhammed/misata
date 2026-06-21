---
title: Narrative Growth Patterns, Shape Synthetic Data with Natural Language
description: Control exactly how your synthetic data rises, dips, and peaks. Misata understands quarterly patterns, named seasonal events (Black Friday, Christmas), and multipliers (doubled, 10x), turning plain English into precise monthly data shapes.
---

# Narrative Growth Patterns

Most synthetic data tools give you random noise. Misata gives you **data that tells a story**.

Describe a growth trajectory in plain English and Misata builds an exact per-month outcome curve, no manual data wrangling, no custom post-processing. The same sentence that describes your dataset also shapes its distribution.

```python
import misata

# These all produce precisely shaped data:
tables = misata.generate("SaaS company — MRR from $50k in Jan to $200k in Dec, Q3 slump")
tables = misata.generate("Ecommerce orders — Black Friday spike, Christmas peak, Q1 slump")
tables = misata.generate("SaaS startup — MRR 10x growth over the year")
tables = misata.generate("Fintech payments — strong Q4, flat Q2, dip in March")
```

---

## How it works

When Misata sees trigger words (see [full list below](#trigger-tokens)), it builds an **OutcomeCurve**: a set of 12 monthly target values. The data simulator then shapes row distributions to hit those targets, month by month.

The curve is built from three inputs, all of which can appear in the same story and stack together:

1. **Numeric anchors**: explicit values for specific months or quarters
2. **Qualitative modifiers**: relative factors applied to months or quarters
3. **Multipliers**: a single end-state factor (doubled, 10×, etc.)

---

## Monthly numeric anchors

Pin exact values for specific months using natural phrasing:

```python
# From–to
"SaaS mrr from $50k in January to $200k in December"

# Multiple control points — Misata interpolates between them
"SaaS mrr $50k in Jan, $90k in June, $200k in Dec"

# Single anchor + qualitative modifier
"SaaS mrr $50k in Jan, peak in November"

# value-then-month or month-then-value — both work
"$200k in December"
"December: $200k"
"December at $200k"
```

Numeric values support `$`, `k`, `M`, `B` prefixes and comma separators:

```
$50k       → 50,000
$1.5M      → 1,500,000
150,000    → 150,000
$200k      → 200,000
```

### From–to shorthand

```python
# Misata infers start=month 1, end=month 12
"SaaS mrr from $50k to $200k"
"SaaS mrr from $50k to $200k over 12 months"
```

---

## Quarterly patterns

Quarter keywords expand to all three constituent months in that quarter. This is the most concise way to shape seasonal data.

```python
# Qualitative quarter modifiers
"Ecommerce orders — Q4 spike"         # Oct, Nov, Dec each boosted by 1.3×
"SaaS mrr — Q1 slump"                 # Jan, Feb, Mar each reduced to 0.72×
"Fintech payments — strong Q4"        # Oct, Nov, Dec lifted by 1.15×
"SaaS mrr — Q3 dip, Q4 push"         # Jul–Sep down, Oct–Dec up
"Ecommerce — Q2 flat, Q4 boom"        # Apr–Jun stays flat, Oct–Dec surges

# Quarter numeric anchors — pin exact values for entire quarters
"SaaS mrr $100k in Q1, $150k in Q2, $200k in Q3, $250k in Q4"
"$80k in Q1, $200k in Q4"            # Misata interpolates Q2 and Q3
```

### Quarter factor reference

| Pattern | Months | Default factor |
|:--|:--|:--|
| `Q1 dip` / `Q1 slump` | Jan, Feb, Mar | 0.7–0.72× |
| `Q1 slow` / `Q1 low` | Jan, Feb, Mar | 0.8× |
| `Q2 flat` | Apr, May, Jun | 1.0× |
| `Q2 strong` | Apr, May, Jun | 1.15× |
| `Q3 dip` / `Q3 slump` | Jul, Aug, Sep | 0.7–0.72× |
| `Q3 peak` / `Q3 spike` | Jul, Aug, Sep | 1.25–1.3× |
| `Q4 push` / `strong Q4` | Oct, Nov, Dec | 1.15–1.2× |
| `Q4 spike` / `Q4 boom` | Oct, Nov, Dec | 1.3× |
| `Q4 surge` | Oct, Nov, Dec | 1.3× |

---

## Named seasonal events

Named commercial events map to specific months with calibrated boost factors. Add them anywhere in your story.

```python
"Ecommerce orders — Black Friday spike, Christmas peak"
"EdTech enrollments — back to school surge, New Year spike"
"SaaS signups — New Year spike, summer slump"
"Insurance payments — tax season boost"
```

### Event reference

| Event phrase | Month | Factor | Notes |
|:--|:--|:--|:--|
| `Black Friday` | November | 1.55× | Highest single-day boost |
| `Cyber Monday` | November | 1.45× | Stacks with Black Friday if both named |
| `Cyber Week` | November | 1.4× | |
| `Christmas` / `Xmas` | December | 1.4× | |
| `Holiday season` | December | 1.35× | |
| `Festive season` | December | 1.3× | |
| `New Year` | January | 1.25× | Gym, fitness, productivity SaaS |
| `Valentine` | February | 1.2× | |
| `Tax season` | April | 1.2× | Fintech, insurance, accounting |
| `Back to school` / `Back-to-school` | August | 1.2× | EdTech, ecommerce |
| `Summer slump` / `Slow summer` | July **+** August | 0.75× each | B2B SaaS, enterprise software |

### Combining events

Events stack with each other and with monthly anchors. In the example below, November gets the Black Friday boost on top of the interpolated value, and December gets the Christmas boost:

```python
tables = misata.generate(
    "Ecommerce store with 5k orders — revenue from $80k in Jan to $120k in Oct, "
    "Black Friday spike, Christmas peak",
    rows=5000, seed=42
)
# November will be the highest-revenue month (Black Friday ×1.55 on top of the curve)
# December will be the second highest (Christmas ×1.40)
```

---

## Relative multipliers

Use a multiplier when you know the end-state relative to the start but don't have absolute numbers.

```python
# Pure multiplier — Misata derives a sensible baseline
misata.generate("SaaS startup — MRR 10x growth over the year")
misata.generate("Fintech GMV doubled over the year")
misata.generate("Ecommerce sales tripled in one year")

# Multiplier + single anchor — anchor is the pivot point
# January is pinned at $50k; December is derived as $100k
misata.generate("SaaS mrr $50k in January, doubled by December")

# Multiplier + early anchor → start value known, end derived
misata.generate("SaaS mrr $20k in January, 5x growth")
# Month 1 = $20k, Month 12 = $100k, linear interpolation between

# Decline story
misata.generate("SaaS revenue halved after the pivot")
```

### Multiplier word reference

| Phrase | Factor |
|:--|:--|
| `halved` | 0.5× |
| `doubled` / `2x increase` | 2× |
| `tripled` / `3x growth` | 3× |
| `quadrupled` / `4x jump` | 4× |
| `5x` | 5× |
| `10x growth` | 10× |
| `grew 200%` | 3× (1 + 2.0) |
| `grew 300%` | 4× (1 + 3.0) |

!!! note "Percentage vs. multiplier"
    `"grew 200%"` means the value is **3×** the starting point (started at 1, added 2, ended at 3). This matches the business meaning of "200% growth."

---

## Combining all three

All three systems compose. Order in the story doesn't matter.

```python
# Monthly anchor + quarterly modifier + named event + multiplier
tables = misata.generate(
    "SaaS company with 5k users — "
    "MRR from $50k in January, "     # anchor: month 1 = $50k
    "doubled by December, "          # multiplier: month 12 = $100k
    "Q3 slump, "                     # quarter modifier: months 7–9 dipped
    "Black Friday spike",            # named event: November boosted
    rows=5000, seed=42
)
```

**Resolution order:**
1. Monthly anchors are interpolated into a baseline curve
2. Quarter modifiers apply as multipliers on the interpolated values
3. Named event modifiers apply on top of quarter-modified values
4. Numeric anchors are re-pinned exactly (overwriting any modifier effects on that specific month)

---

## Qualitative modifier reference

These work with month names, quarter labels, and standalone:

| Keyword | Factor |
|:--|:--|
| `crash` | 0.5× |
| `dip` | 0.7× |
| `drop` | 0.7× |
| `slump` | 0.72× |
| `decline` | 0.75× |
| `slow` | 0.8× |
| `low` | 0.8× |
| `flat` | 1.0× |
| `strong` | 1.15× |
| `push` | 1.2× |
| `high` | 1.2× |
| `peak` | 1.25× |
| `boom` | 1.3× |
| `spike` | 1.3× |
| `surge` | 1.3× |

---

## Trigger tokens

A curve is only built when the story contains at least one of these words. If you want narrative shaping but don't have a natural trigger, add `"revenue"` or `"growth"` to your story.

```
revenue    sales      mrr        arr        gmv        amount
orders     bookings   transactions  volume  churn      growth
peak       dip        spike      surge      drop       decline
slump      boom       doubled    tripled    halved
black friday  christmas  summer slump
q1  q2  q3  q4
```

---

## Accessing curve points programmatically

```python
import misata

schema = misata.parse(
    "SaaS mrr from $50k in Jan to $200k in Dec, Q3 slump",
    rows=5000
)

for oc in schema.outcome_curves:
    print(f"Curve: {oc.table}.{oc.column}")
    for pt in oc.curve_points:
        print(f"  Month {pt['month']:2d}: ${pt['target_value']:,.0f}")
```

Output:
```
Curve: subscriptions.mrr
  Month  1: $50,000
  Month  2: $63,636
  Month  3: $77,273
  Month  4: $90,909
  Month  5: $104,545
  Month  6: $118,182
  Month  7: $82,727    ← Q3 slump (×0.72)
  Month  8: $82,727    ← Q3 slump (×0.72)
  Month  9: $82,727    ← Q3 slump (×0.72)
  Month 10: $145,455
  Month 11: $159,091
  Month 12: $200,000
```

---

## Real-world story examples

### SaaS startup hockey-stick

```python
tables = misata.generate(
    "SaaS startup with 2k users — MRR $5k in January, 10x growth over the year, "
    "strong Q4 push, slow Q1 next year",
    rows=2000, seed=42
)
```

### Ecommerce with full seasonal story

```python
tables = misata.generate(
    "Ecommerce store with 10k customers — "
    "revenue from $200k in Jan to $350k in Sep, "
    "Black Friday spike, Christmas peak, Q1 slump after holidays",
    rows=10_000, seed=42
)
```

### Fintech payments with quarterly narrative

```python
tables = misata.generate(
    "Fintech with 5k customers — transaction volume strong Q4, "
    "flat Q2, tax season bump in April, Q1 slow start",
    rows=5000, seed=42
)
```

### B2B SaaS with summer slump

```python
tables = misata.generate(
    "B2B SaaS platform with 1k enterprise customers — "
    "ARR $500k in Jan, doubled by December, summer slump",
    rows=1000, seed=42
)
```

### Streaming service with content drops

```python
tables = misata.generate(
    "Netflix-like streaming with 20k subscribers — "
    "watch hours spike in Q4 holiday season, summer slump, "
    "watch volume from $1M in Jan to $2.5M in Dec",
    rows=20_000, seed=42
)
```

---

## Inspecting curve detection with preview()

Use `preview()` to verify the curve was detected before generating:

```python
report = misata.preview(
    "SaaS mrr from $50k in Jan to $200k in Dec, Q3 slump, Black Friday spike"
)
print(report.temporal_events)
# [{"type": "growth", "value": null}]

print(report.summary())
# ✓ Domain: saas  [high]
# ✓ Scale: users=1,000
# ✓ Events: 1 detected
#
#   Will generate 2 table(s), ...
```
