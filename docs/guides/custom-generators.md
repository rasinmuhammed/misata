# Custom generators

Declarations cover the common shapes of business data. When a column needs
logic of your own (a tier computed from a parent's spend, an ID format from an
internal spec, a value from a lookup service you mock), write a function and
register it. The alternative is post-processing the DataFrame after
generation, which is the hand-written script Misata exists to replace, and
which runs after the integrity and audit passes rather than inside them.

```python
import numpy as np
import misata

@misata.generator("loyalty_tier")
def loyalty_tier(ctx):
    spend = ctx.parent("customers")["lifetime_value"].to_numpy()
    tier = np.where(spend > 1000, "gold", np.where(spend > 200, "silver", "bronze"))
    upgrade = ctx.rng.random(ctx.size) < 0.05     # seeded: same seed, same rows
    return np.where(upgrade, "gold", tier)
```

Name it on the column, the same way from Python, YAML or a dict schema:

<!-- stranger: skip (needs the loyalty_tier generator registered above) -->
```yaml
tables:
  customers:
    rows: 300
    columns:
      customer_id: {type: int, primary_key: true}
      lifetime_value: {type: float, distribution: lognormal, mu: 5.5, sigma: 1.0}
  orders:
    rows: 2000
    columns:
      order_id: {type: int, primary_key: true}
      customer_id: {type: foreign_key, references: customers.customer_id}
      tier: {type: text, generator: loyalty_tier}
```

From the CLI, load the module that registers it:

<!-- stranger: skip (needs your own my_generators module) -->
```bash
misata --plugin my_generators generate --config misata.yaml
# or: MISATA_PLUGINS="my_generators other_module" misata generate ...
```

## What the function receives

`ctx` is a `misata.GenContext`:

| | |
|---|---|
| `ctx.size` | rows to return for this batch |
| `ctx.rows` | the batch's columns generated so far |
| `ctx.parent("customers")` | the parent row of every row in the batch, all columns, in order (by table name or foreign-key column) |
| `ctx.rng` | a numpy `Generator` seeded from the schema seed, table, column and batch |
| `ctx.table`, `ctx.column`, `ctx.params` | where it is running, and the column's declared parameters |
| `ctx.tables` | every parent table generated so far |

Return an array, list or Series of `ctx.size` values. Anything else raises,
naming the column.

## Rules that keep it reproducible and safe

- **Use `ctx.rng`, not `np.random` or `random`.** It is what makes the same
  seed give the same rows.
- **Declare the column after what it reads.** `ctx.parent()` needs the
  foreign key generated first, and says so if it is not.
- **A schema only names a generator, it never imports one.** Code runs only if
  you registered it, so a schema from someone else, or from an agent through
  the MCP server, cannot execute anything.
- **Leave declared columns to their declarations.** A column a curve,
  roll-up or identity owns is written by that declaration; put the generator
  on a different column.

## Older forms

`generate_from_schema(schema, custom_generators={"orders": {"tier": fn}})`
still works, with `fn(partial_df, tables)` (vectorised) or
`fn(row, column_name, tables)` (per row). A one-parameter `fn(ctx)` gets the
context above.
