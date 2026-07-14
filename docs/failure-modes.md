# When Misata refuses

Misata treats an impossible declaration as a bug in the declaration, not something to paper over. When your spec cannot be satisfied exactly, the engine either warns and tells you which property it sacrificed, or drops the affected artifact rather than shipping a wrong one. This page collects every such refusal, with the arithmetic that triggers it and the exact message you will see, so you can search this page by the warning text itself.

The companion page is [LIMITATIONS.md](https://github.com/rasinmuhammed/misata/blob/main/LIMITATIONS.md) in the repository: that file states what the engine cannot do; this one explains the messages it gives you when a specific run hits one of those walls.

## Rate targets and integer rounding

A rate over n rows can only be a multiple of 1/n. A declared 2% fraud rate over 4,824 rows is unreachable: 96 flagged rows gives 1.99%, 97 gives 2.01%.

What happens: plain generation flags the closest achievable count and moves on. An evalpack, whose questions must verify exactly, drops the question instead of shipping a wrong answer. The drop is recorded in `manifest.json`:

```
"drop_reason": "verification_mismatch"
```

If you need the rate to be a round number, choose row counts that divide it: 2% of 5,000 is exactly 100 rows.

## Declared bounds versus aggregate targets

A period target T over n rows with per-row bounds [lo, hi] is feasible only when:

```
lo * n <= T <= hi * n
```

When the declaration violates this, the aggregate target wins and rows leave their bounds, loudly:

```
UserWarning: Outcome curve on 'orders.amount' pushed values past the
column's declared bounds: 92 row(s) above declared max=100. The curve takes
precedence over the declared min/max. Widen the bounds or soften the curve
to avoid this.
```

The fix is in the message: widen the bounds or soften the curve. The conformance preview (`misata preview`) surfaces these conflicts before any rows are generated.

## Row-count clamps (Prop. 3 saturation)

When a period target needs more rows than `max_transactions_per_period` allows, the engine keeps the sum exact by inflating per-row values. Every aggregate check still passes while the row-level distribution shifts, so the warning is the only signal:

```
Period '2024-03': target=250,000.00 requires ≈2500 rows but
max_transactions_per_period=1000 — per-row values will be inflated
(Prop. 3 upper clamp). Raise max_transactions_per_period to avoid distortion.
```

The mirror case (target too small for `min_transactions_per_period`) deflates per-row values with the matching "Prop. 3 lower clamp" message.

## Evalpack question gates

Every question in an evalpack is re-executed against the shipped CSV files with DuckDB before shipping. Anything inexact is dropped and logged, never shipped. The two drop reasons in `manifest.json`:

```
"drop_reason": "verification_mismatch"   the answer did not reproduce exactly
"drop_reason": "sql_error: ..."          the gold SQL failed to execute
```

A pack that ships 35 questions may have had 40 candidates. The dropped five are the honest ones.

## Group shares and small buckets

A `group_shares` declaration places at least one row in every positive-share group, so a curve period with fewer rows than groups cannot host the split:

```
UserWarning: group_shares on orders: bucket with 2 rows cannot host
4 groups; skipping (infeasible)
```

The bucket keeps its generated values: the period total still holds, the shares inside that one period do not. Shares that do not sum to 1 are normalised, with a warning:

```
UserWarning: group_shares on orders.revenue: shares sum to 0.970,
normalising to 1
```

## Reversed and degenerate date ranges

A single-date range (start equals end) means "within that day" and generates normally. A reversed range is swapped rather than crashed on, and tells you:

```
UserWarning: date range start 2025-06-30 is after end 2025-01-01; swapping
```

If you meant the reversed order, the warning is your cue that the schema says otherwise.

## Capsule price bands and contradictory declarations

A capsule price band ("Laptops": 400 to 3500) draws every price inside the band of its row's category. Two precedence rules can make it stand down, silently by design:

- An explicit user distribution (`mean`, `std`, `mu`, `sigma`) on the price column ignores the band entirely. Your shape, your numbers.
- Declared `min`/`max` intersect the band. When the intersection is empty (declared max 300 against a 400 to 3500 band), the declaration wins outright and the band does not apply.

There is one loud backstop: `story_audit` re-checks the bands on the output, so a price outside its category's band always surfaces as a `price_band_violation` finding in the coherence report, whichever rule produced it.

## The general principle

Each of these behaviours follows one rule: an exact declaration is either satisfied exactly or refused visibly. Nothing in the engine silently produces "close enough" while claiming exactness. When you see one of these warnings, the declaration and the data genuinely disagree, and the message names which one gave way.
