v0.8.0.2: Relational realism

This is a realism and correctness release. The headline change is that generated data now
reconciles the way real data does: a parent summary column like `customers.total_spent`
actually equals the sum of that customer's orders, so the data holds up under a real
`GROUP BY ... JOIN` instead of falling apart on the first query. We also closed a
correctness gap in how relative curves behave on large, multi-batch runs. 633 tests pass,
0 failures.

## Added

**Cross-table aggregate roll-ups.** Parent summary columns are now computed from the real
child rows, so they reconcile exactly. Declare a roll-up on the column:

```python
"total_spent": {"type": "float", "rollup": {
    "from_table": "orders", "fk": "customer_id", "agg": "sum", "column": "amount"}}
```

Supported aggregations are `sum`, `count`, `mean`, `max`, and `min`. You can add an
optional `where` filter to aggregate only matching child rows, for example
`"where": {"status": "completed"}` (a single value or a list). Reconciliation is exact,
foreign keys stay intact, and results are deterministic under a fixed seed.

**Zero-config roll-up inference.** When a parent column name clearly names a child table,
such as `num_orders` or `total_orders`, the roll-up is inferred automatically with no
declaration. This is deliberately conservative. On ambiguous names like `total_sales` or
`stock_count` it declines rather than guess, so it produces no false positives on the
built-in domains.

**Zero-inflated distributions.** A new `zero_inflate` parameter adds a spike of structural
zeros on top of any base distribution, for columns like free-tier MRR or no-spend months:

```python
"spend": {"type": "float", "distribution": "lognormal", "mu": 4, "sigma": 0.5,
          "zero_inflate": 0.3}
```

The zeros are applied after the `min` clamp, so a structural zero is not lifted to the
minimum. It is opt-in, and it is not auto-applied to domains that already model zeros
through their own logic.

## Fixed

**Relative-curve cross-batch convergence.** Relative outcome curves now hold their shape
exactly regardless of `batch_size`. Before this fix, a table larger than the batch size
generated in several batches would drift. For example, a curve meant to make December
four times January would land closer to three and a half times at small batch sizes. The
correction now interpolates a factor for every month and tracks the actual accumulated row
counts across batches, so single-batch and multi-batch runs match.

**YAML round-trip for generation features.** The `rollup`, `zero_inflate`, `depends_on`,
`mapping`, `formula`, and `inherits_curve_from` settings now survive a
`save_yaml_schema` then `load_yaml_schema` cycle. They were previously dropped on load,
which silently disabled these features for any schema committed to a `misata.yaml` file.

## Changed

**Positioning.** The library is now framed around outcome-conformant generation: you
declare the outcome you want, such as a revenue curve, a fraud rate, or a set of
multi-table aggregates, and Misata generates data that hits those targets exactly while
keeping referential integrity. This framing is now consistent across the README, the
package metadata, and the MCP server, which ships usage instructions so AI agents know
what Misata does and when to reach for it.

## Notes

This release extends the exact-aggregate engine described in the arXiv preprint
(2606.08736, https://arxiv.org/abs/2606.08736v1) from temporal aggregate conformance
toward relational aggregate coherence across parent and child tables.

Full changelog: https://github.com/rasinmuhammed/misata/blob/main/CHANGELOG.md
