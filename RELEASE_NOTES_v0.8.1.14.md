# Misata 0.8.1.14

**Quality + resilience release.** Two goals: generation **never crashes**, and it
**never silently produces senseless values.**

## Highlights

### 1. Explicit numeric distributions are respected (the big fix)

Semantic inference runs by default and used to match columns named exactly
`price`/`cost`/`amount`/`salary`/etc., overwriting the declared distribution with a
generic `uniform(0, 1000)`. A house price declared `normal(mean=500000)` came out as
**$1–$999**. This was the root cause behind a lot of "bad numbers" across prompts.

Now: semantic inference only fills in **bare** columns (no distribution, e.g. from DB
introspection). Any explicitly-parameterised distribution is left untouched. Money and
measure columns additionally get a `min: 0` floor so a wide normal can't emit negative
values in its tail.

Before → after for "price rises with square footage":

| | Before | After |
|---|---|---|
| price mean | ~$500 | ~$492,000 |
| price min | $0.5 | $0 |
| price max | ~$999 | ~$977,000 |
| corr(price, sqft) | 0.75 ✓ | 0.76 ✓ |

### 2. Generation never crashes on bad LLM output

- **Impossible distribution params repaired:** negative `std`→abs, inverted
  `min`/`max`→swapped, non-positive `scale`/`lambda`→positive, `zipf`/`pareto` `a`≤1→1.1.
- **Circular FK chains broken:** cross-table cycles (a→b→a) previously raised
  `ValueError`; the closing edge is dropped with a warning and the orphan column
  demoted to int. Self-referential FKs (`employee.manager_id`) are preserved.
- **Empty reference tables handled:** a table marked `is_reference` with no
  `inline_data` is auto-filled from domain vocabulary or demoted to a normal table —
  never left to produce garbled output. Missing `id` columns are injected.

### 3. Deterministic domain vocabulary

Hallucinated categorical values (SaaS-tier words like "Premium"/"Standard"/"Basic"
used for property types, cities, statuses) are replaced with domain-correct values
from a built-in library — in both column `choices` and reference-table `inline_data`.
Domain detection uses word-boundary matching so "reorder"/"disorders" don't
false-match "order".

### 4. Prompt + FK improvements

- System prompt now carries a complete worked real-estate example (correct
  `inline_data`, `correlations` instead of `outcome_curves`, `foreign_key`-typed FKs).
- FK auto-detection no longer promotes a table's own unique primary-key `*_id` column.

## Verification

- **962 tests pass.**
- End-to-end torture test: a schema combining all failure modes at once (bad params,
  circular FKs, empty reference tables, blacklisted values) parses, validates, and
  generates rows with zero crashes.

## Companion (studio repo)

A **Refine Schema** chat bar in the Design view + `POST /engine/refine-schema` endpoint
for token-efficient natural-language schema edits (does not re-run full generation).

## Upgrade

```bash
pip install --upgrade misata
```

No API changes — this is a drop-in quality/resilience upgrade.
