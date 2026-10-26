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

When no row count in `[min_transactions_per_period, max_transactions_per_period]` satisfies it, generation refuses before writing a row:

```
SchemaValidationError: Outcome curve on 'orders.amount': target 50000 per period
is unreachable with the column bounds (min=5, max=500) and 1-20 rows per period:
no row count n satisfies 5·n ≤ 50000 ≤ 500·n.
  Fix: widen the bounds, adjust the target, or change min/max_transactions_per_period
```

When a row count would work but the one planned from `avg_transaction_value` does not, the aggregate target wins and rows leave their bounds, with a `ConformanceWarning` per period:

```
ConformanceWarning: Outcome curve on 'orders.amount', period 'month:1': exact target
50,000.00 across 1000 rows is infeasible under the declared max=40 (the target would
need to be at most 40,000.00). The aggregate target takes precedence: per-row values
will violate the declared max bound. Widen the bound, adjust the target, or tune
min/max_transactions_per_period.
```

The conformance preview (`misata preview`) shows these conflicts before any rows are generated.

## Row-count clamps (Prop. 3 saturation)

When a period target needs more rows than `max_transactions_per_period` allows, or fewer than `min_transactions_per_period`, the row count is held to the bound and each row grows or shrinks to keep the total exact. Every aggregate check still passes while the per-row mean leaves `avg_transaction_value`, so generation says so:

```
ConformanceWarning: amount: 3 of 3 periods (2024-01, 2024-02, 2024-03) need a row
count outside min/max_transactions_per_period [1, 20] at avg_transaction_value=50.
Their totals still hold, but rows in 2024-03 average 4,000.00 instead of 50. Widen
the min/max transactions per period, or change avg_transaction_value.
```

## Making warnings fatal in CI

Every warning Misata emits is a `misata.MisataWarning`, and every warning that means a declaration will not hold exactly as written is a `misata.ConformanceWarning`. Both subclass `UserWarning`, and each points at the line in your code that called Misata.

```python
import warnings
import misata

warnings.simplefilter("error", misata.ConformanceWarning)   # fail on any broken declaration
tables = misata.generate_from_schema(schema)
```

With pytest, the same rule goes in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
filterwarnings = ["error::misata.ConformanceWarning"]
```

## Evalpack question gates

Every question in an evalpack is re-executed against the shipped CSV files with DuckDB before shipping. Anything inexact is dropped and logged, never shipped. The drop reasons in `manifest.json`:

```
"drop_reason": "verification_mismatch"   the answer did not reproduce exactly
"drop_reason": "sql_error: ..."          the gold SQL failed to execute
"drop_reason": "answer_depends_on_seed"  the rotations disagree on the declared answer
```

A pack that ships 35 questions may have had 40 candidates. The dropped five are the honest ones.

## Group shares and small buckets

A `group_shares` declaration places at least one row in every positive-share group, so a curve period with fewer rows than groups cannot host the split:

```
ConformanceWarning: group_shares on orders: bucket with 2 rows cannot host
4 groups; skipping (infeasible)
```

The bucket keeps its generated values: the period total still holds, the shares inside that one period do not. Shares that do not sum to 1 are normalised, with a warning:

```
ConformanceWarning: group_shares on orders.revenue: shares sum to 0.970,
normalising to 1
```

## Reversed and degenerate date ranges

A single-date range (start equals end) means "within that day" and generates normally. A reversed range is swapped rather than crashed on, and tells you:

```
ConformanceWarning: date range start 2025-06-30 is after end 2025-01-01; swapping
```

If you meant the reversed order, the warning is your cue that the schema says otherwise.

## Capsule price bands and contradictory declarations

A capsule price band ("Laptops": 400 to 3500) draws every price inside the band of its row's category. Two precedence rules can make it stand down, silently by design:

- An explicit user distribution (`mean`, `std`, `mu`, `sigma`) on the price column ignores the band entirely. Your shape, your numbers.
- Declared `min`/`max` intersect the band. When the intersection is empty (declared max 300 against a 400 to 3500 band), the declaration wins outright and the band does not apply.

There is one loud backstop: `story_audit` re-checks the bands on the output, so a price outside its category's band always surfaces as a `price_band_violation` finding in the coherence report, whichever rule produced it.

## Time grids on a curve's time column

A time grid moves each timestamp forward to its next slot, and a value past the day's last slot moves to the next day. On the column an outcome or rate curve buckets its periods by, that would carry rows late on a period's last day into the next period, so the schema is refused before generation:

```
InfeasibleSchema: [orders.order_date] outcome_curve periods by orders.order_date vs time_grids on orders.order_date
  → Suggestion: declare order_date as type date, which keeps every row in its period, or drop the time grid on orders.order_date
```

A `date` column holds midnight, where the grid only sets the time of day, so the two compose.

## The general principle

Each of these behaviours follows one rule: an exact declaration is either satisfied exactly or refused visibly. Nothing in the engine silently produces "close enough" while claiming exactness. When you see one of these warnings, the declaration and the data genuinely disagree, and the message names which one gave way.
