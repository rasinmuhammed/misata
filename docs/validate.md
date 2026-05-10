---
title: Validate & Preview — Data Quality Profiling and Story Inspection with Misata
description: Profile CSV files for quality issues, inspect story detection results before generating, and validate misata.yaml schemas against the built-in JSON Schema. All three are zero-generation operations.
---

# Validate & Preview

Misata provides three separate inspection tools — all of which produce no synthetic data:

| Tool | Purpose |
|:--|:--|
| `preview()` | Inspect what a plain-English story would generate before committing |
| `validate_csv()` | Profile a CSV for quality issues and null rates |
| `validate_schema()` | Check a `misata.yaml` against the JSON Schema |

---

## preview() — Inspect story detection

`preview()` parses a plain-English story and returns everything Misata understood: domain, scale, locale, and the table layout — without generating a single row. Use it before any large `generate()` call to catch ambiguity or misconfiguration early.

```python
import misata

report = misata.preview(
    "A SaaS company with 5k users, MRR from $50k in Jan to $200k in Dec"
)

print(report.domain)             # "saas"
print(report.domain_confidence)  # "high"
print(report.matched_keywords)   # ["saas", "mrr"]
print(report.scale_params)       # {"users": 5000}
print(report.locale)             # None

print(report.table_preview)
# [{"name": "users",         "rows": 5000,  "columns": 12},
#  {"name": "subscriptions", "rows": 5000,  "columns": 8},
#  {"name": "invoices",      "rows": 20000, "columns": 6}]

print(report.temporal_events)    # [{"type": "growth", "value": null}]
print(report.warnings)           # []

print(report.summary())
# ✓ Domain: saas  [high]  matched: saas, mrr
# ✓ Scale: users=5,000
# ✓ Events: 2 detected
#
#   Will generate 3 table(s), 30,000 total rows:
#     users          5,000 rows  (12 columns)
#     subscriptions  5,000 rows  (8 columns)
#     invoices      20,000 rows  (6 columns)
```

### DetectionReport reference

| Field | Type | Description |
|:--|:--|:--|
| `domain` | `str \| None` | Detected domain code (`"saas"`, `"fintech"`, …) or `None` if no domain matched |
| `domain_confidence` | `str` | `"high"` if ≥2 keywords matched, `"low"` if 1 keyword, `"none"` if nothing matched |
| `matched_keywords` | `list[str]` | The specific keywords that fired for the winning domain |
| `near_misses` | `dict[str, list[str]]` | Other domains whose keywords also appeared — useful for diagnosing ambiguity |
| `scale_params` | `dict[str, int]` | Parsed numeric scale signals (e.g. `{"users": 5000}`) |
| `temporal_events` | `list[dict]` | Growth, churn, crash events detected (used to build outcome curves) |
| `locale` | `str \| None` | Auto-detected locale code (`"de_DE"`, `"pt_BR"`, …), or `None` |
| `table_preview` | `list[dict]` | `[{name, rows, columns}]` for each table that would be generated |
| `total_rows` | `int` | Sum of row counts across all tables |
| `warnings` | `list[str]` | Fallback and ambiguity warnings |

### Interpreting confidence levels

```python
report = misata.preview("A platform with crypto wallets and subscription payments")

print(report.domain_confidence)  # "low" — ambiguous
print(report.near_misses)        # {"crypto": ["crypto", "wallet"], "saas": ["subscription"]}
print(report.warnings)
# ["Domain 'fintech' matched on 1 keyword — consider naming the domain explicitly"]

# Fix: name the domain so it earns the +5 literal bonus
report2 = misata.preview("A fintech platform with crypto wallets and subscription payments")
print(report2.domain_confidence)  # "high"
print(report2.domain)             # "fintech"
```

**Detection scoring:**
- **+5** if the literal domain name appears in the story
- **+1** per matched keyword

The highest-scoring domain wins. Naming the domain explicitly (`"fintech"`, `"saas"`, etc.) always produces a `"high"` confidence result.

### Workflow: preview then generate

```python
import misata

story = "A fintech with 5k customers, Black Friday spike"

# Step 1 — inspect for free
report = misata.preview(story, rows=5000)
if report.domain_confidence == "none":
    print("No domain detected:", report.warnings)
    exit()

# Step 2 — optional: inspect full schema (tables, columns, FK relationships)
schema = misata.parse(story, rows=5000)
print(schema.summary())

# Step 3 — generate
tables = misata.generate_from_schema(schema, seed=42)
```

### CLI

```bash
misata preview --story "A SaaS company with 5k users, Q4 spike"
```

---

## validate_csv() — CSV quality profiling

Profile any CSV file for null rates, type inference, range statistics, and uniqueness violations. Returns a `ValidationReport` with a 0–100 quality score.

### CLI

```bash
# Profile a CSV — type inference, null rates, range stats
misata validate customers.csv

# Check against a YAML schema
misata validate orders.csv --schema misata.yaml

# Parse a story and validate the CSV against it
misata validate orders.csv --story "A SaaS company with an orders table"
```

Example output:

```
Validating 'customers' — 5,000 rows × 8 columns
──────────────────────────────────────────────────────────────────────────
  Column                 Type          Nulls  Range / Values               Notes
  ──────────────────────────────────────────────────────────────────────────
  customer_id            int            0.0%  1 → 5000                     unique · schema ✓
  email                  text           0.2%  4,989 unique                 0.2% nulls · schema ✓
  plan                   categorical    0.0%  free, pro, enterprise        schema ✓
  mrr                    float          0.0%  0.0 → 2,399.8               schema ✓
  signup_date            date           0.0%  2022-01-03 → 2024-12-29     unique
  credit_score           int            1.1%  582 → 848                    1.1% nulls
  is_active              boolean        0.0%
  country                text           0.0%  94 unique
  ──────────────────────────────────────────────────────────────────────────

  Quality score: 94/100
  1 issue(s) found:
    · credit_score: 1.1% nulls — column may be mostly empty
```

### Python API

```python
import misata

# Profile only
report = misata.validate_csv("customers.csv")
print(report.score)         # 0–100
print(report.issues)        # list of strings
print(report)               # formatted table

# With a YAML schema — checks types, required columns, value constraints
schema = misata.load_yaml_schema("misata.yaml")
report = misata.validate_csv("customers.csv", schema=schema, table_name="customers")

# From a DataFrame directly
import pandas as pd
df = pd.read_csv("customers.csv")
report = misata.validate_csv(df, table_name="customers")
```

### ValidationReport attributes

| Attribute | Type | Description |
|:--|:--|:--|
| `score` | `int` | Quality score 0–100. Deductions for nulls >50%, type mismatches, uniqueness violations |
| `rows` | `int` | Number of rows profiled |
| `columns` | `list[dict]` | Per-column stats: name, inferred type, null rate, range, notes |
| `issues` | `list[str]` | Human-readable list of detected problems |

---

## validate_schema() — YAML schema validation

Misata ships a JSON Schema (`misata/_schemas/misata_schema.json`) that describes the full `misata.yaml` format. Running `validate_schema()` runs two layers of validation:

1. **Structural** — JSON Schema checks (required fields, types, allowed values)
2. **Semantic** — domain-aware checks (FK targets exist, distribution params are in range, formula columns reference existing columns)

### CLI

```bash
# Validate a misata.yaml file
misata validate-schema misata.yaml
```

### Python API

```python
import misata

result = misata.validate_schema("misata.yaml")

if result.valid:
    print("Schema is valid")
else:
    for error in result.errors:
        print(error)
# Example errors:
# tables[0].columns[2]: 'distribution' must be one of: uniform, normal, lognormal, ...
# tables[1].columns[0]: formula references column 'gross_pay' which is not defined
```

### Editor auto-complete

Add the `$schema` pointer to your `misata.yaml` to get in-editor validation and auto-complete in VS Code, PyCharm, and any editor that supports JSON Schema:

```yaml
# misata.yaml
$schema: "https://rasinmuhammed.github.io/misata/schema/misata_schema.json"

tables:
  - name: users
    rows: 5000
    columns:
      - name: user_id
        type: int
        unique: true
      - name: email
        type: email
      - name: plan
        type: categorical
        values: [free, pro, enterprise]
```

VS Code will highlight unknown keys, warn on invalid distribution names, and auto-complete column type names as you type.

### What the schema checks

| Check | Example error |
|:--|:--|
| Required fields present | `tables[0]: 'name' is required` |
| Column types valid | `type must be one of: int, float, text, email, …` |
| Distribution names valid | `distribution must be one of: uniform, normal, lognormal, …` |
| FK targets exist | `foreign_key 'orders.customer_id' references unknown table 'users'` |
| Formula columns reference existing columns | `formula 'gross_pay * rate' references undefined column 'rate'` |
| Distribution params in range | `normal mean must be a number` |

---

## Inspecting narrative curves

When a story contains growth patterns, `parse()` returns `OutcomeCurve` objects that show the exact monthly targets that will shape generated data:

```python
import misata

schema = misata.parse(
    "SaaS mrr from $50k in Jan to $200k in Dec, Q3 slump, Black Friday spike",
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
  Month 11: $163,636   ← Black Friday (×1.55 on interpolated value)
  Month 12: $200,000
```

This lets you verify the curve before generating 100k rows. [Full narrative patterns guide →](guides/narrative-patterns.md)
