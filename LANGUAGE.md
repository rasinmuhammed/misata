# The Misata declaration language

Misata is a declarative synthetic data generator. You state what must be true of
the data; the engine solves for rows that satisfy it; an independent SQL engine
verifies the result.

This document is the reference for **what can be declared**. For every
declaration it answers four questions:

- **Guarantees** — exactly what holds afterwards, stated so you could test it.
- **Owns** — which columns the declaration writes. Anything it owns, you should
  not also govern another way.
- **Costs** — what it buffers, rewrites, or forces into memory.
- **Refuses** — when the engine will not generate at all, and what it says.

Two rules run through everything:

1. **Declared fractions are counts, not probabilities.** A declared 40% is 40%
   of rows, allocated by largest remainder, not 40% in expectation.
2. **Every guarantee is re-checked by `coherence_audit`**, which recomputes it
   from the emitted rows rather than trusting the pass that wrote them.

---

## How a declaration is verified

```python
import misata
from misata.coherence import coherence_audit

tables = misata.generate_from_schema(schema)      # refuses if infeasible
report = coherence_audit(tables, schema=schema)   # independent re-check
assert report.clean
```

`generate_from_schema` raises `InfeasibleSchema` **before generating anything**
when declarations cannot all hold. Pass `strict=False` for the older behaviour,
where the engine warns and then overrides one of your declarations. You almost
never want that.

---

## Aggregate declarations

### `outcome_curves` — exact per-period totals

```python
OutcomeCurve(
    table="orders", column="amount", time_column="order_date",
    time_unit="month", value_mode="absolute",
    curve_points=[{"date": "2025-01-01", "target_value": 120000.0}, ...],
)
```

**Guarantees.** Rows bucketed by `time_column` at `time_unit` sum to
`target_value` in every declared period, to the cent.

**Owns.** `column`, and the temporal density of `time_column`.

**Costs.** Buffers the table. Extends generated dates to cover the curve's span
even beyond the column's declared range; the curve wins.

**Refuses.** When `value_mode="absolute"` but the points carry `relative_value`
instead of `target_value`. That mismatch silently produced totals four orders of
magnitude off before it was a refusal, which is exactly why it is one now.

### `rate_curves` — exact per-period rates

As above, for a rate rather than a sum. Count-rounding limited: a rate that
cannot be hit exactly with whole rows is reported rather than approximated.

### `group_shares` — exact proportions across groups

```python
GroupShares(table="orders", measure="amount", group_column="segment",
            shares={"smb": 0.5, "mid": 0.3, "ent": 0.2})
```

**Guarantees.** Each group's share of `measure` is exactly as declared. **Paired
with an `OutcomeCurve` on the same measure, the shares hold exactly within every
declared period**, not merely over the table total. Both hold simultaneously;
this is verified in the Gauntlet.

**Owns.** `group_column` (labels are rewritten) and `measure`.

**Refuses.** Shares summing above 1.0. Shares naming a group absent from the
column's `choices`.

---

## Identity declarations

These are the ones no other generator has: facts that span rows and tables.

### `rollups` — a parent aggregate equals its child facts

```python
Column(name="lifetime_value", type="float", distribution_params={"rollup": {
    "from_table": "payments", "via": ["orders"],     # multi-hop
    "fk": "customer_id", "agg": "sum", "column": "amount"}})
```

**Guarantees.** The parent column equals `agg` over the child rows, to the cent,
including through a declared `via` chain of intermediate tables. Childless
parents get `fillna` (0 by default).

**Owns.** The target column.

**Costs.** Buffers parent, child, and every `via` table.

**Refuses.** A curve and a roll-up both claiming one column. An unresolvable
`via` chain warns loudly and leaves the column alone rather than aggregating a
guessed path.

### `waterfalls` / `stock_flows` / `balanced_ledger`

Period identities: opening + movements = closing; open + received − shipped =
close; sum(debit) = sum(credit) per journal entry. Each holds to the cent on
every row and every consecutive pair.

### `lifecycles` — a state implies a legal history

```python
Lifecycle(
    name="order_lifecycle", table="orders", state_column="status",
    start_column="order_date", initial="placed",
    states=[LifecycleState(name="placed", timestamp="placed_at"),
            LifecycleState(name="shipped", timestamp="shipped_at"),
            LifecycleState(name="cancelled", timestamp="cancelled_at",
                           terminal=True)],
    transitions=[("placed", "shipped"), ("placed", "cancelled")],
    weights={"placed": .2, "shipped": .7, "cancelled": .1},
)
```

**Guarantees.** For a row in state S with path P from `initial` to S: every state
in P has its timestamp populated, in path order; every state outside P has its
timestamp NULL; the whole chain postdates `start_column`. State shares match
`weights` exactly.

A returned order therefore carries the shipment and completion it necessarily
passed through, which is the thing a per-pair rule cannot express.

**Owns.** `state_column` and every declared state timestamp.

**Costs.** Buffers the table. Runs during that table's own generation, before
children, so a relationship filtering on the state sees final values.

**Refuses.** Two lifecycles on one state column. Weights on states no transition
reaches. A `when_then` rule contradicting the machine.

**Subsumes** `when_then` and status gating. Prefer a lifecycle when a status has
more than one dependent column.

### `when_then` — a status gates one column

```python
Constraint(type="when_then", when_column="status", when_op="in",
           when_value=["active"], then_column="cancelled_at", then="null")
```

`then` is `null`, `not_null` (filled from `then_value`, else by sampling the
column's own non-null values), or `set`.

### `lte_parent` / `sum_lte_parent` — child money bounded by its parent

Row-level clamp, and per-parent proportional rescale. The FK is resolved from the
declared relationship, never guessed.

### `min_children` — every parent covered

`Relationship(..., min_children=1)`. An order with zero line items does not
exist in real data, and a zero-item order poisons everything downstream of it.
**Refuses** when the child table cannot cover the parents.

### `scd2` — versions tile a timeline

No gaps, no overlaps, exactly one current version per entity.

---

## Dynamics declarations

### `retention` — a cohort curve that actually holds

```python
CohortRetention(
    table="orders", event_time="order_date", cohort_key="customer_id",
    cohort_table="customers", cohort_time="signup_date", unit="month",
    curve={0: 1.0, 1: 0.55, 2: 0.40, 3: 0.34},
)
```

**Guarantees.** For every cohort period and declared offset k, exactly
`round(fraction × cohort_size)` distinct entities have at least one event in
period `cohort + k`. Retention **nests** for a non-increasing curve: an entity
active at offset 2 was almost always active at offset 1, which is what real
curves look like.

Note the honest limit: the *count* per cohort is exact, so the realised *rate*
varies slightly between cohorts of different sizes. 50 of 90 is 55.6%, not 55%.

**Owns.** The event table's `cohort_key` and `event_time`. Every other column is
untouched.

**Costs.** Buffers both tables and rewrites two columns of the event table.

**Refuses.** When the curve needs more active entity-periods than the event
table has rows, with the arithmetic and the row count you would need.

### `missingness` — values absent for a reason (MNAR)

```python
Missingness(table="customers", column="income", rate=0.40, else_rate=0.05,
            when_column="age_band", when_op="in", when_value=["18-24"])
```

**Guarantees.** Exactly `rate` of matching rows are NULL, and exactly
`else_rate` of the rest. Integer columns are widened to float rather than
coerced. Omit the condition for a plain unconditional rate.

Why it matters: a flat null rate produces MCAR, the one pattern real data almost
never has. MNAR is what breaks models and pipelines in production.

**Owns.** `column`'s null pattern. Runs last, so nothing refills what it emptied.

### `late_arrivals` — some rows land in a later partition

```python
LateArrival(table="orders", event_time="order_date",
            ingest_time="ingested_at", late_fraction=0.05, max_delay_days=3)
```

**Guarantees.** `ingest_time` is always at or after `event_time`. Exactly
`late_fraction` of rows land in a **later calendar day** than the event; the rest
stay inside the event's own day. No delay exceeds `max_delay_days`.

"Late" means the partition boundary, not 24 hours, because the partition is what
an incremental model or a watermark actually keys on.

**Owns.** `ingest_time`, which must be declared on the table as a nullable
datetime. Never modifies `event_time`.

**Note.** An ingest timestamp is excluded from cross-table causality: it records
when a row was *recorded*, not when anything happened, so it must not define when
a parent came into existence.

---

## Value and structural guarantees

Not declarations, but always on:

| | |
|---|---|
| FK integrity | topological insert order, zero orphans, verified |
| Determinism | same spec, same seed, identical bytes |
| Anchored streams | edit one declaration and only it changes |
| Atomic geo | city, state and zip drawn as one consistent tuple |
| Temporal profiles | timestamps quantised to the granularity their semantics imply |

---

## What is not part of the language

Kept in the codebase, deliberately outside the contract, because they cannot be
both declared and verified: the LLM story parser, vocabulary and capsule
enrichment, PDF export, Spark output, fidelity/TSTR scoring.

They are conveniences. The rule that decides: **a capability earns a place in the
language only if it can be declared and verified.** If you cannot state it in the
schema it is not language; if the audit cannot check it, it is not a guarantee.

---

## Conformance

`benchmarks/gauntlet.py` is the conformance suite: 11 tables, an M:N junction, a
diamond dependency, and 119 SQL assertions executed by DuckDB, which shares no
code with the generator. It runs in CI on every push with a `KNOWN_RED` contract,
so it cannot quietly shrink to fit the product.

```bash
python -m benchmarks.gauntlet                        # 118/119
python -m benchmarks.gauntlet_compare --tool faker   # for comparison
```

The single known-red is FK sampling with temporal eligibility, and it stays
visible in every run until it is fixed.
