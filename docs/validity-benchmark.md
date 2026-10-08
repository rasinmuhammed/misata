# Validity benchmark

The realism benchmark asks whether generated data *looks* real. This one asks
something more basic: does it obey its own schema? A seed that breaks a CHECK
constraint, a composite key or a foreign key fails on `INSERT`, and test data
that cannot be loaded is not test data.

Five SQL schemas, written the way production databases declare their rules:

| Schema | What makes it hard |
|---|---|
| `saas_billing` | UNIQUE emails, CHECK enums, `CHECK (seats > 0 AND seats <= 500)`, `CHECK (end_date > start_date)` |
| `org_chart` | a self-referencing `manager_id` that must form a tree, `CHECK (salary BETWEEN ...)` |
| `marketplace_m2m` | a junction table with a composite PRIMARY KEY, `UNIQUE (order_id, line_no)`, `CHECK (price >= cost)` |
| `hotel_bookings` | `CHECK (check_out > check_in)`, ranges on capacity and guests, a status enum |
| `retail_chain_6_levels` | a six-level foreign-key chain from regions to payments |

Each schema is generated two ways:

- **`misata_from_ddl`**: `misata.from_ddl(ddl)` then `generate_from_schema`,
  with the row counts set and nothing else configured.
- **`faker_script`**: the script people usually write instead. One Faker or
  NumPy call per column, foreign keys drawn uniformly from the parent ids,
  CHECK clauses not read.

The checker restates every rule in plain pandas and shares no code with
Misata, so a pass is not Misata grading itself. It counts duplicate primary
keys, orphaned foreign keys, NULLs in NOT NULL columns, duplicate UNIQUE
values (single and composite), values outside CHECK enums and ranges,
violated column-to-column CHECKs, and rows that sit on a cycle of a
self-reference.

## Results

Misata 0.9.7, seed 7. Reproduce with

```bash
python benchmarks/validity_bench.py
```

| Schema | Generator | Rows | pk duplicates | fk orphans | nulls | unique duplicates | enum violations | range violations | check violations | cycles | Total | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| saas_billing | misata_from_ddl | 35,000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** | 1.1 |
| saas_billing | faker_script | 35,000 | 0 | 0 | 0 | 211 | 32,957 | 1,495 | 1,487 | 0 | **36,150** | 1.79 |
| org_chart | misata_from_ddl | 5,040 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** | 0.05 |
| org_chart | faker_script | 5,040 | 0 | 0 | 0 | 52 | 0 | 9,962 | 0 | 5,000 | **15,014** | 0.58 |
| marketplace_m2m | misata_from_ddl | 35,785 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** | 0.12 |
| marketplace_m2m | faker_script | 37,060 | 97 | 0 | 0 | 2,115 | 0 | 38,622 | 1,553 | 0 | **42,387** | 0.04 |
| hotel_bookings | misata_from_ddl | 32,300 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** | 0.28 |
| hotel_bookings | faker_script | 32,300 | 0 | 0 | 0 | 324 | 20,000 | 20,207 | 9,885 | 0 | **50,416** | 1.92 |
| retail_chain_6_levels | misata_from_ddl | 45,836 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** | 0.23 |
| retail_chain_6_levels | faker_script | 45,836 | 0 | 0 | 0 | 0 | 23,975 | 50 | 0 | 0 | **24,025** | 0.36 |

Misata reports zero violations on every schema. Two things it costs, stated
plainly:

- **Composite keys can shorten a table.** Where a composite key cannot be
  made unique by renumbering (a junction table of two foreign keys), repeated
  pairs are dropped, so `product_tags` delivers 5,045 of the 6,000 rows asked
  for. A sequence column in a composite key (`line_no`) is renumbered within
  its group instead, and only rows past the CHECK maximum are dropped.
- **Durations come from the column names, not your data.** A date pair
  ordered by a CHECK is generated as the earlier date plus a duration that
  fits the names: stays (`check_out > check_in`) skew short with a median of
  three nights, shipping takes one to ten days, a contract's `end_date` runs
  one month to two years. Other pairs repaired by the constraint move by a
  gap drawn from the rows that already satisfied it.

## What fixing this found

This benchmark was written for 0.9.7 and failed on its first run. The fixes
it forced are in the release:

- `from_ddl` dropped every self-referencing foreign key, so `manager_id` was
  random integers that looped back on themselves. It now keeps them, and the
  generator builds the hierarchy as a forest.
- Table-level `CHECK (a > b)` between two columns was ignored; it is now an
  inequality constraint.
- Composite `PRIMARY KEY (a, b)` and `UNIQUE (a, b)` were ignored, and once
  declared they were enforced per batch, which the union of batches broke.
  They now hold over the whole table.
- An inequality repair set the violating value equal to the other column,
  which breaks a strict `>` and piles rows up at a zero gap.
- UNIQUE text columns skipped semantic generation, so a UNIQUE `sku` was
  filled with sentences and a `regions.name` with people's names.
