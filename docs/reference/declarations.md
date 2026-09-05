---
title: "Declaration reference: every property Misata can guarantee"
description: "Complete reference for all 29 Misata schema declarations, from exact revenue curves and balancing ledgers to state machines, graph motifs and conditional missingness. Every example runs."
---

# Declaration reference

Misata is declarative. You state what must be true of a dataset and the engine
solves for rows satisfying it, deterministically. This page lists every property
you can state.

The rule that decides what belongs here: **a capability earns a place only if it
can be declared and verified.** If you cannot state it in the schema it is not
part of the language, and if the audit cannot check it afterwards it is not a
guarantee.

```diagram
# What a declaration is worth: it is checked after generation, not assumed

    your schema                  the engine                 the audit
  ┌────────────────┐        ┌──────────────────┐      ┌──────────────────┐
  │ tables         │        │ feasibility      │      │ recompute every  │
  │ relationships  │──────▶ │   refuse early   │────▶ │ declared value   │
  │ declarations   │        │ solve            │      │ from the rows    │
  └────────────────┘        │ emit rows        │      │ report mismatch  │
         ▲                  └──────────────────┘      └────────┬─────────┘
         │                                                     │
         └─────────  contradictory? named, with arithmetic ◀───┘
```

Two things follow from that shape. Contradictory declarations are refused
**before** any data exists, with both declarations and the arithmetic named,
rather than one quietly winning. And a declaration that did hold can be
re-checked by anyone, from the emitted files, with no access to the generator.

Every example below was executed against the engine before publishing.

Prefer to click rather than type? The same declarations are editable on the
canvas at [misata.studio/try](https://misata.studio/try), no sign-up.

---

## How to declare

Three surfaces, one language. Pick whichever suits you.

```python
import misata

schema = misata.from_dict_schema({
    "customers": {"__rows__": 500, "id": {"type": "integer", "primary_key": True}},
    "orders": {
        "__rows__": 5000,
        "customer_id": {"type": "foreign_key",
                        "foreign_key": {"table": "customers", "column": "id"}},
        "revenue": {"type": "float", "min": 10, "max": 900},
    },
}, seed=42)
tables = misata.generate_from_schema(schema)
```

Schema-level declarations use a `__dunder__` key at the top level, alongside
your tables. The same document in YAML uses the bare name:

```yaml
tables:
  orders:
    rows: 5000
    columns:
      order_date: {type: date}
      category: {type: string, enum: [Electronics, Home, Apparel]}
      revenue: {type: float, min: 10, max: 900}

outcome_curves:
  - table: orders
    column: revenue
    time_column: order_date
    time_unit: month
    value_mode: absolute
    curve_points:
      - {date: "2026-01-01", target_value: 50000}
      - {date: "2026-06-01", target_value: 120000}

group_shares:
  - table: orders
    measure: revenue
    group_column: category
    shares: {Electronics: 0.5, Home: 0.3, Apparel: 0.2}
```

Run `misata lint schema.yaml` to have feasibility checked in CI without
generating anything.

---

## Structure

What rows exist, and how they point at each other.

### `relationships`, foreign keys that resolve

Declared per column. Parents are generated before children and every child key
points at a real parent row, so a join never drops rows and an orphan count is
zero by construction rather than by luck.

```python
"orders": {
    "__rows__": 5000,
    "customer_id": {"type": "foreign_key",
                    "foreign_key": {"table": "customers", "column": "id"}},
}
```

### `constraints`, row-level rules

Bounds, inequalities between columns, composite uniqueness, and expressions.
See [Constraints](../constraints.md).

### `dag_edges`, an edge table with no cycles

Guarantees the edge table is a directed acyclic graph. Required before a
closure table can mean anything.

```python
"__dag_edges__": [{
    "name": "org_tree", "table": "edges",
    "node_table": "nodes", "node_key": "id",
    "from_column": "parent", "to_column": "child",
}]
```

### `closures`, a closure table that equals its closure

A closure (or "ancestor") table is the classic place where hand-made test data
lies: it looks plausible and does not actually equal the transitive closure of
the edges beside it. Here it does, at every depth.

```python
"__closures__": [{
    "name": "org_closure", "table": "tree_closure",
    "edge_table": "edges", "edge_from": "parent", "edge_to": "child",
    "ancestor_column": "ancestor", "descendant_column": "descendant",
    "depth_column": "depth",
}]
```

Verified by recomputing the closure independently from the edge table and
comparing triple for triple.

### `graph_motifs`, the patterns worth detecting, on purpose

A DAG is the right default and the wrong dataset for anyone building a
detector, because the shapes worth finding are the ones a DAG forbids. This
rewrites a declared fraction of the edges into rings, fan-in, fan-out,
scatter-gather and chains at an exact mix, each labelled with a case id.

```diagram
# A declared 2% of edges become motifs; the rest stay acyclic

  background (98%)          declared motifs (2%)
   a → b → c → d       ring:  p → q → r → p        case M000044
   e → f → g                  ▲___________|
   h → i                fan-in: s ┐
   (no cycles,                  t ┼→ w              case M000208
    ever)                       u ┘
```

The property is exact rather than statistical: **the subgraph of edges carrying
no case id is acyclic**, so every cycle in the output belongs to a case somebody
declared and an accidental pattern cannot exist. `benign_shares` declares hard
negatives, real motifs labelled legitimate, so a detector is measured on telling
a ring from an innocent loop rather than on finding loops.

Full guide: [Lexicons, motifs and joint margins](../guides/declared-vocabulary-and-structure.md).
Worked example: [the AML case study](https://misata.studio/case-studies).

---

## Exact aggregates

Declare the number the data must add up to. The engine solves for rows that hit
it, rather than generating rows and hoping.

### `outcome_curves`, an aggregate over time, hit exactly

"Revenue grows from 50k to 200k over twelve months" becomes rows whose monthly
sums equal those targets to the cent. Closed-form conditional sampling, not
rejection sampling and not approximation.

```python
"__outcome_curves__": [{
    "table": "orders", "column": "revenue",
    "time_column": "order_date", "time_unit": "month",
    "value_mode": "absolute",
    "curve_points": [{"date": "2026-01-01", "target_value": 50000},
                     {"date": "2026-12-01", "target_value": 200000}],
}]
```

Full guide: [Outcome curves](../guides/outcome_curves.md).

### `rate_curves`, a rate over time, hit exactly

The same mechanism for proportions: a fraud rate, a churn rate, a pass rate,
declared per period and true per period.

Full guide: [Rate curves](../guides/rate_curves.md).

### `group_shares`, exact shares of a measure

"Electronics is 50% of revenue, Home 30%, Apparel 20%", true on the emitted
rows, and composing with any curve above it.

```python
"__group_shares__": [{
    "table": "sales", "measure": "revenue", "group_column": "category",
    "shares": {"Electronics": 0.5, "Home": 0.3, "Apparel": 0.2},
}]
```

Measured on 900 rows: `{Electronics: 0.5, Home: 0.3, Apparel: 0.2}` exactly.

### `joint_distributions`, several margins at once

Two margins used to be satisfiable one at a time and silently inconsistent
together. This solves for the unique maximum-entropy table consistent with every
declared margin, by iterative proportional fitting, and refuses up front when
they cannot all hold.

```python
"__joint_distributions__": [{
    "name": "region_by_tier", "table": "accounts",
    "margins": {
        "region": {"emea": 0.42, "apac": 0.31, "amer": 0.27},
        "tier": {"free": 0.70, "pro": 0.22, "enterprise": 0.08},
    },
}]
```

### `waterfalls`, movements that reconcile to a balance

A movements table whose signed rows per period equal that period's declared
delta, so the running balance recomputed from raw rows hits every declared
ending value.

```python
"__waterfalls__": [{
    "table": "mrr_movements", "starting_value": 100000,
    "points": [{"period": "2026-01", "ending_value": 106000},
               {"period": "2026-02", "ending_value": 112000},
               {"period": "2026-03", "ending_value": 118000}],
    "inflow_shares": {"new": 0.7, "expansion": 0.3},
    "outflow_shares": {"churn": 1.0},
}]
```

```diagram
# The running balance is recomputed from the rows, not stored

  100,000  ├─ new +8,200 ─ expansion +1,900 ─ churn -4,100 ──▶  106,000  ✓ declared
  106,000  ├─ new +7,400 ─ expansion +2,300 ─ churn -3,700 ──▶  112,000  ✓ declared
  112,000  ├─ new +6,900 ─ expansion +2,600 ─ churn -3,500 ──▶  118,000  ✓ declared
```

Measured over six periods: every recomputed balance matched its declared value
with a delta of 0.0000.

Note the key is `ending_value`, not `value`. `period_column`, `type_column` and
`amount_column` default to `period`, `movement_type` and `amount`.

### `stock_flows`, an inventory ledger that reconciles per unit

`closing = opening + received - shipped`, chained across periods per SKU, so the
closing balance of one period is the opening balance of the next.

```python
"__stock_flows__": [{
    "table": "inventory", "sku_column": "sku", "period_column": "period",
    "open_column": "opening", "received_column": "received",
    "shipped_column": "shipped", "close_column": "closing",
    "periods": ["2026-01", "2026-02", "2026-03"],
    "starting_min": 50, "starting_max": 500,
}]
```

Measured on 300 rows: maximum residual of `opening + received - shipped -
closing` was 0.0000000000. Note `periods` is a list of period labels, not a
count.

---

## Time and state

### `time_grids`, timestamps that land where real ones do

Appointments at 09:00, 09:15, 09:30, inside business hours. Real systems do not
scatter timestamps uniformly across the clock, and uniform ones are a tell.

```python
"__time_grids__": [{
    "table": "appointments", "column": "slot",
    "minute_grid": 15, "hours": [9, 17],
}]
```

Measured on 400 rows: 0 off-grid, 0 outside hours.

### `lifecycles`, a state machine that held

An entity's status column is only as trustworthy as the path it took to get
there. Declare the states and the legal transitions, and every row's state is
reachable, with the timestamps of the states on its path populated and the rest
null.

```python
"__lifecycles__": [{
    "name": "order_flow", "table": "orders",
    "state_column": "status", "start_column": "placed_at",
    "states": [{"name": "placed"}, {"name": "paid"}, {"name": "shipped"},
               {"name": "delivered"}, {"name": "refunded", "terminal": True}],
    "transitions": [["placed", "paid"], ["paid", "shipped"],
                    ["shipped", "delivered"], ["delivered", "refunded"]],
    "initial": "placed",
}]
```

`states` takes objects, not bare strings. Give a state a `timestamp` column to
have entry times recorded and null-correct.

### `event_logs`, a log that agrees with the status column

The same guarantee projected onto an event-sourced child table. In one audited
corpus this class of defect produced 602 done tasks with no completion event and
667 completions that happened before the work started.

```python
"__event_logs__": [{
    "name": "case_trail", "table": "case_events",
    "entity_table": "cases", "entity_key": "case_id",
    "event_type_column": "event", "event_time_column": "at",
    "state_events": {"submitted": "case_submitted",
                     "reviewed": "case_reviewed",
                     "approved": "case_approved"},
}]
```

`state_events` maps state name to event type name, and pairs with a
`lifecycles` declaration on the parent table.

### `retention`, a cohort curve the cohort table actually shows

```python
"__retention__": [{
    "table": "sessions", "event_time": "occurred_at",
    "cohort_key": "user_id", "cohort_table": "users",
    "cohort_time": "signed_up", "unit": "month",
    "curve": {0: 1.0, 1: 0.55, 2: 0.40, 3: 0.32, 4: 0.28, 5: 0.25},
}]
```

`curve` is a mapping of period offset to retained fraction. `unit` is `day`,
`week` or `month`.

### `bitemporal`, two independent time axes

When a fact was true, and when you knew it. The shape every slowly-changing
dimension and every audited price history really has, and the one hand-made
fixtures almost never get right.

```python
"__bitemporal__": [{
    "name": "price_history", "table": "prices",
    "entity_columns": ["sku"],
    "valid_from": "valid_from", "valid_to": "valid_to",
    "recorded_at": "recorded_at", "superseded_at": "superseded_at",
    "avg_versions": 3,
}]
```

```diagram
# Two axes, so "what did we believe on 3 March about 1 January?" has an answer

  valid time  ──▶   Jan          Feb          Mar
                    ├────────────┤
  recorded    Feb 2 │  price 40  │                    superseded Mar 9
                    ├────────────┼────────────┐
  recorded    Mar 9 │  price 42 (correction)  │       current
```

### `late_arrivals`, events that land after the fact

A declared fraction of events arrive with an ingest time later than their event
time, which is what breaks naive incremental pipelines.

```python
"__late_arrivals__": [{
    "table": "events", "event_time": "occurred_at",
    "ingest_time": "ingested_at",
    "late_fraction": 0.05, "max_delay_days": 3,
}]
```

### `events`, `degradations`

`events` declares occurrences over a time axis. `degradations` declares that
units wear out and when, producing remaining-useful-life and damage columns,
optional bearing physics, and a maintenance policy. See
[Predictive maintenance](../domains/predictive-maintenance.md) and the
[public RUL dataset](https://huggingface.co/datasets/rasinmuhammed/predictive-maintenance-remaining-useful-life).

---

## Realism and imperfection

Real data is not clean. Declaring the mess is what separates a dataset that
exercises a pipeline from one that only exercises the happy path.

### `missingness`, why values are missing, not just how often

Missing-at-random is the easy case and the rare one. Declare the condition.

```python
"__missingness__": [{
    "table": "patients", "column": "discharge_note",
    "rate": 0.9, "else_rate": 0.05,
    "when_column": "admitted", "when_op": "==", "when_value": True,
}]
```

Measured on 2,000 rows: 0.9 missing where admitted, 0.05 elsewhere.

### `typos`, exactly this many corrupted values

```python
"__typos__": [{"table": "contacts", "column": "city", "count": 25}]
```

Exactly 25 of the values become corrupted versions of a legal value, so a
dedupe or cleaning step has a known number of things to find. Use `fraction`
instead of `count` for a proportion.

### `duplicates`, exactly this many duplicate rows

```python
"__duplicates__": [{"table": "contacts", "count": 10}]
```

Pass `subset` or `keys` to duplicate on a partial match, which is the harder
and more realistic case for a matching algorithm.

### `noise`, `outliers`

Measurement noise and declared outliers, with counts you can assert against.

### `realism`, `vocabularies`, `locale`

The realism core: joint name, gender and culture identities, real geographic
facts, Zipf-shaped categorical frequencies, and rating-conformant review text.
`locale` makes names, addresses and formats region-correct, and it wins over a
generic lexicon: `locale: "ja_JP"` returns 鈴木 くみ子.

Column-level `semantic:` resolves a column to a generative lexicon whose
vocabulary keeps growing with the table instead of cycling a fixed pool. See
[Lexicons, motifs and joint margins](../guides/declared-vocabulary-and-structure.md).

---

## Control

| Key | What it does |
|---|---|
| `seed` | Same seed, identical bytes, on any machine. No model, no tokens, nothing leaves the machine. |
| `generation_mode` | `anchored` makes schema edits produce minimal data diffs: adding a column leaves the rest byte-identical. |
| `domain` | Picks a built-in domain's vocabulary and shape. Unknown domains are composed structurally rather than guessed. |
| `rows` | Default row count, overridden per table by `__rows__`. |
| `name`, `description` | Prose for the reader. Changes no data. |

---

## When a declaration cannot hold

Misata refuses rather than picking one. A generator picks and carries on; a
declarative engine names both declarations and shows the arithmetic:

```
Infeasible: orders.revenue
  outcome_curves  declares  January total = 50,000.00
  group_shares    declares  Electronics = 50% of revenue
  constraints     declares  revenue <= 900 per row
  arithmetic      50,000.00 x 0.5 = 25,000.00 needs >= 28 rows at the cap,
                  January has 20
  remedy          raise the cap, lower the share, or add rows
```

See [When Misata refuses](../failure-modes.md) and
[Known limitations](https://misata.studio/limitations).

---

## Next

- [Ready-to-paste prompts](../prompts.md) for the plain-English and agent paths
- [Quick start](../quickstart.md)
- [Try the canvas, no sign-up](https://misata.studio/try)
- [Ready-made datasets](https://misata.studio/datasets)
- [Case studies](https://misata.studio/case-studies)
