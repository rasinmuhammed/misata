# Outcome Curve-Driven Synthesis

Misata's outcome-curve engine lets you declare **what your data should aggregate to** rather than how individual rows are distributed. The engine then generates rows that hit your declared targets **exactly**: not approximately.

This capability is formalised in the published paper:

> **Declarative Outcome-Conformant Synthesis: Exact, Closed-Form Specification Satisfaction and a Conformance Benchmark**  
> Muhammed Rasin, arXiv:2606.08736v1 (2026)

The paper proves the mechanism is exactly conditional-sum sampling of a Gamma population via Lukacs' characterisation. The Aggregate Mean Error (AME) is exactly 0 for the closed-form engine, versus 74–86% miss for off-the-shelf learned synthesisers.

---

## Core Concept

You declare targets; Misata generates individual rows whose aggregate (sum per period) matches:

```
Declared:   Jan=$10k   Jun=$45k   Dec=$120k
Generated:  36,200 individual order rows
Verified:   sum(Jan orders) = $10,000.00 ✓  AME = 0
            sum(Dec orders) = $120,000.00 ✓  AME = 0
```

---

## Three Authoring Paths

### 1. Natural Language (NL)

The simplest path, describe your curve in plain English. The `StoryParser` extracts anchors and modifiers automatically:

```python
import misata

tables = misata.generate(
    "An ecommerce store with 10k orders — revenue from $10k in January "
    "to $120k in December, with a Black Friday spike and an August dip"
)
```

Supported NL patterns include:
- **Anchors**: `"$50k in January"`, `"$200k in Q4"`
- **Multipliers**: `"doubled"`, `"10x growth"`, `"grew 300%"`
- **Named events**: `"Black Friday"`, `"Christmas"`, `"summer slump"`, `"New Year"`
- **Quarter modifiers**: `"Q4 spike"`, `"dip in Q3"`, `"strong Q4"`

### 2. SDK Builder (Programmatic)

Use `OutcomeCurveBuilder` when you need precise control, the primary target for the no-code UI backend:

```python
from misata import OutcomeCurveBuilder, parse, generate_from_schema

# Sparse anchors — the builder interpolates between them
curve = (
    OutcomeCurveBuilder("orders", column="amount", time_column="order_date")
    .start("2024-01-01")
    .anchor("2024-01", 10_000)    # January: $10k
    .anchor("2024-06", 45_000)    # June: $45k (mid-year push)
    .anchor("2024-12", 120_000)   # December: $120k
    .dip("2024-08", factor=0.7)   # August slowdown (-30%)
    .spike("2024-11", factor=1.3) # November push (+30%)
    .avg_value(75.0)              # drives row-count planning (paper §3.1)
    .concentration(2.0)           # Dirichlet α — per-row dispersion (paper §3.2)
    .build()
)

schema = parse("An ecommerce store with 10k orders")
schema = OutcomeCurveBuilder.attach(schema, curve)
tables = generate_from_schema(schema)
```

**Builder API reference:**

| Method | Description |
|--------|-------------|
| `.start("YYYY-MM-DD")` | Start date of the curve timeline |
| `.anchor(period, value)` | Pin an exact aggregate target for one period |
| `.dip(period, factor=0.7)` | Multiply a period downward (`factor < 1`) |
| `.spike(period, factor=1.3)` | Multiply a period upward (`factor > 1`) |
| `.quarter_pattern(q1, q2, q3, q4)` | Set relative multipliers for all four quarters |
| `.seasonal(black_friday=True, ...)` | Apply named seasonal event multipliers |
| `.avg_value(mu)` | Average transaction value: drives row count (§3.1) |
| `.concentration(alpha)` | Dirichlet α: controls dispersion (§3.2) |
| `.row_bounds(min_tx, max_tx)` | Row-count bounds per period (Prop. 3 guard) |
| `.intra_period(pattern)` | Within-period timestamp distribution |
| `.build()` | Returns an `OutcomeCurve` |

`OutcomeCurveBuilder.attach(schema, *curves)`, non-mutating attach (returns a deep copy).

**Period formats accepted by `.anchor()`, `.dip()`, `.spike()`:**

| Format | Example | Meaning |
|--------|---------|---------|
| `"YYYY-MM"` | `"2024-01"` | January 2024 |
| `"YYYY-Q1"` | `"2024-Q4"` | Q4 2024 (months 10–12) |
| integer | `6` | Month 6 |

### 3. YAML Schema

Declare outcome curves in `misata.yaml` and generate from the CLI:

```yaml
# misata.yaml
name: Ecommerce Dataset
tables:
  orders:
    rows: 10000
    columns:
      order_id:
        type: int
        unique: true
      amount:
        type: float
        min: 5.0
        decimals: 2
      order_date:
        type: date
        start: "2024-01-01"
        end: "2024-12-31"

outcome_curves:
  - table: orders
    column: amount
    time_column: order_date
    time_unit: month
    pattern_type: growth
    avg_transaction_value: 75        # drives row-count planning (paper §3.1)
    concentration: 2.0               # Dirichlet α (paper §3.2)
    start_date: "2024-01-01"
    intra_period_pattern: weekday_heavy
    curve_points:
      - {period: "2024-01", value: 10000}
      - {period: "2024-06", value: 45000}
      - {period: "2024-12", value: 120000}
```

```bash
misata generate   # → data/orders.csv with exact monthly sums
```

---

## Rate Curves (RCE Axis)

`OutcomeCurve` targets aggregate sums (AME axis). **`RateCurve`** targets the rate of a boolean or categorical column per period, the rate-conformance (RCE) axis introduced in SpecBench.

### SDK

```python
from misata import OutcomeCurveBuilder

# Fraud rate rising from 2% → 5% through the year
fraud_curve = (
    OutcomeCurveBuilder.rate(
        "transactions",
        column="is_fraud",
        time_column="transaction_date",
    )
    .anchor("2024-01", 0.02)
    .anchor("2024-06", 0.035)
    .anchor("2024-12", 0.05)
    .interpolate(True)              # rates between anchors are interpolated
    .build()                        # → RateCurve
)

schema = OutcomeCurveBuilder.attach(schema, fraud_curve)
```

### YAML

```yaml
rate_curves:
  - table: transactions
    column: is_fraud
    time_column: transaction_date
    time_unit: month
    true_value: true         # value counted as the positive class
    interpolate: true
    rate_points:
      - {period: "2024-01", rate: 0.02}
      - {period: "2024-06", rate: 0.035}
      - {period: "2024-12", rate: 0.05}
```

### Verification

```python
monthly_fraud = (
    tables["transactions"]
    .groupby(tables["transactions"]["transaction_date"].dt.to_period("M"))["is_fraud"]
    .mean()
)
# January: ≈ 0.020  ✓
# December: ≈ 0.050  ✓
```

---

## Conformance Preview

Before generating rows, call `conformance_preview()` to see what the engine will produce, period targets, estimated row counts, and clamping warnings. This is what a no-code UI renders to the user before generation:

```python
from misata import conformance_preview, OutcomeCurveBuilder, parse

curve = (
    OutcomeCurveBuilder("orders", column="amount", time_column="order_date")
    .anchor("2024-01", 10_000)
    .anchor("2024-12", 120_000)
    .avg_value(75.0)
    .build()
)
schema = parse("An ecommerce store with 5k orders")
schema = OutcomeCurveBuilder.attach(schema, curve)

preview = conformance_preview(schema)
print(preview.summary())
# Conformance preview: E-commerce Dataset
# Outcome curves: 1
# AME achievable: Yes ✓
#   orders.amount over order_date (month)
#     Total target: 785,000.00  |  Est. rows: 10,467
#     month:1    target=   10,000.00  rows≈  133
#     month:2    target=   20,182.00  rows≈  269
#     ...

# Serialise for the no-code UI chart renderer
chart_data = preview.to_dict()
```

**`ConformancePreview` fields:**

| Field | Description |
|-------|-------------|
| `ame_achievable` | `True` if all curves can reach AME = 0 |
| `bounds_respected` | `True` if no curve needs to violate a declared column min/max |
| `curves` | List of `CurvePreview` per outcome curve |
| `warnings` | Merged list of all warnings |
| `.summary()` | Human-readable multi-line string |
| `.to_dict()` | JSON-serialisable dict for UI rendering |

**`CurvePreview` fields:**

| Field | Description |
|-------|-------------|
| `periods` | List of `PeriodPreview` (period, target, est_rows) |
| `total_target` | Sum of all period targets |
| `total_rows` | Estimated total rows across all periods |
| `ame_achievable` | `True` for this specific curve |
| `bounds_respected` | `False` when a period target forces per-row values past the declared min/max |
| `warnings` | Prop. 3 clamping and bound-conflict warnings for this curve |

### Precedence: aggregate targets win over column bounds

A period with `n` rows and target `T` can keep every row inside the column's declared `[min, max]` only when `min * n <= T <= max * n`. When a target breaks that condition (say `target_value: 100` for a month that gets 900 rows on a column with `min: 50`), the engine still hits the aggregate exactly. The exact target takes precedence, and per-row values in that period will violate the declared bound.

This never happens silently. Three surfaces report the sacrifice:

1. Generation emits a `UserWarning` naming the table, column, period, and the bound that was sacrificed.
2. `conformance_preview()` sets `bounds_respected=False` on the affected curve and adds a per-period warning, before any rows exist.
3. The Oracle report flags it under `guarantees.kpi_conformance`: `bounds_passed=False`, with per-period `bound_violation` details (rows below min, rows above max, observed extremes). The AME check itself still passes, since the aggregate was met.

To resolve the conflict, widen the bound, adjust the target, or constrain the row count with `min/max_transactions_per_period` so the per-row mean lands inside the declared range.

---

## No-Code UI Integration

The SDK is designed so the no-code UI backend never touches the NL parser. The expected flow:

```
User drags anchors on chart
        ↓
UI POSTs JSON { "table": ..., "anchors": {...}, "modifiers": {...} }
        ↓
Backend: OutcomeCurveBuilder.from_dict(payload).build()
        ↓
Backend: conformance_preview(schema) → render chart to user
        ↓
User clicks "Generate"
        ↓
Backend: generate_from_schema(schema) → download CSV / seed DB
```

```python
# Backend handler (FastAPI / Flask / etc.)
from misata import OutcomeCurveBuilder, conformance_preview, generate_from_schema

def handle_preview(payload: dict, schema):
    curve = OutcomeCurveBuilder.from_dict(payload["curve"]).build()
    schema = OutcomeCurveBuilder.attach(schema, curve)
    preview = conformance_preview(schema)
    return preview.to_dict()          # sent to UI chart

def handle_generate(payload: dict, schema):
    curve = OutcomeCurveBuilder.from_dict(payload["curve"]).build()
    schema = OutcomeCurveBuilder.attach(schema, curve)
    return generate_from_schema(schema)
```

---

## Mathematical Background

The engine implements **Proposition 2** from the paper:

> Given a total `T_p` and `n_p` rows, sample proportions `w` from a symmetric Dirichlet(α). Then `x_i = ⌊w_i · T_p · 10^d⌋ / 10^d` with remainder correction gives `Σ x_i = T_p` exactly.

Key parameters:
- `concentration` (Dirichlet α), higher = tighter per-row distribution
- `avg_transaction_value` (`μ`), sets `n_p = round(T_p / μ)` (Prop. 3)
- `min/max_transactions_per_period`, guards against distortion when `n_p` is clamped

See the full paper at [arXiv:2606.08736v1](https://arxiv.org/abs/2606.08736v1) for proofs and SpecBench benchmark results.
