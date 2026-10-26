---
title: An Eval Database With a Correct Answer Key
description: Build a text-to-SQL evaluation database whose answers are declared before the data exists, verified on three rotated databases, and designed so plausible wrong SQL fails instead of passing by coincidence.
---

# An eval database with a correct answer key

Text-to-SQL benchmarks annotate answers onto an existing database, and the
annotations are often wrong. An evalpack works the other way round: the
answers are the spec, the database is generated to satisfy them, and each
answer is then confirmed by running its gold SQL with DuckDB against the
files that ship.

**Who:** teams evaluating SQL agents, data agents and text-to-SQL models.
**Time:** about 3 seconds for three databases of 43,040 rows each.

## The declaration

```yaml
# misata.yaml
name: retail_answer_key
seed: 42
tables:
  stores:
    rows: 40
    columns:
      store_id: {type: int, unique: true, min: 1, max: 40}
      region: {type: categorical, choices: [north, south, east, west]}
      opened_on: {type: date, start: "2018-01-01", end: "2023-12-31"}
  customers:
    rows: 3000
    columns:
      customer_id: {type: int, unique: true, min: 1, max: 3000}
      loyalty_tier: {type: categorical, choices: [none, silver, gold], probabilities: [0.6, 0.3, 0.1]}
  sales:
    rows: 40000
    columns:
      sale_id: {type: int, unique: true, min: 1, max: 10000000}
      store_id: {type: foreign_key}
      customer_id: {type: foreign_key}
      category: {type: categorical, choices: [grocery, apparel, electronics, home]}
      amount: {type: float, min: 2, max: 1500}
      is_return: {type: boolean}
      sold_at: {type: date, start: "2025-01-01", end: "2025-06-30"}
relationships:
  - stores.store_id -> sales.store_id
  - customers.customer_id -> sales.customer_id
outcome_curves:
  - table: sales
    column: amount
    time_column: sold_at
    value_mode: absolute
    start_date: "2025-01-01"
    curve_points:
      - {month: 1, target_value: 410000.37}
      - {month: 2, target_value: 385112.84}
      - {month: 3, target_value: 432519.06}
      - {month: 4, target_value: 451002.91}
      - {month: 5, target_value: 478236.45}
      - {month: 6, target_value: 502081.18}
group_shares:
  - table: sales
    measure: amount
    group_column: category
    shares: {grocery: 0.4, apparel: 0.25, electronics: 0.2, home: 0.15}
rate_curves:
  - table: sales
    column: is_return
    time_column: sold_at
    rate_points:
      - {period: "2025-01", rate: 0.06}
      - {period: "2025-06", rate: 0.04}
```

Monthly revenue targets carry cents on purpose. With round targets, a query
that rounds money to whole units gets the same answer as the correct one and
cannot be told apart from it.

## Build the pack

```bash
pip install "misata[evalpack]"
misata evalpack -c misata.yaml -o pack --rotations 3
python pack/verify.py
```

```text
46/46 match on all 3 database(s)
```

`pack/` holds `questions.jsonl` (46 questions with gold SQL and expected
answers), three databases under `rotations/seed-42/`, `seed-43/` and
`seed-44/`, a certificate per database, and the standalone `verify.py`.
The databases share every declared answer and differ in every row.

## Score a model

Each line of `answers.jsonl` is a model's SQL for one question:

<!-- stranger: skip, the sample answers include two wrong ones on purpose -->
```bash
python pack/verify.py --candidates answers.jsonl
```

```text
OK   q001: 410000.37
FAIL q002: expected 385112.84; seed-42: 397191.82; seed-43: 399406.21; seed-44: 399894.45
OK   q008: 6168
FAIL q015: expected 0.06; seed-42: 5.9987; seed-43: 5.9987; seed-44: 5.9987

2/4 match on all 3 database(s)
```

`q001` and `q008` are correct queries written differently from the gold SQL.
`q002` uses `BETWEEN`, which includes the first of March. `q015` returns a
percentage where the question asks for a fraction. A query counts as
correct only when it matches on every database, so one that happens to fit
a single database's rows still fails.

## How hard it is to pass by accident

`pack/manifest.json` records a near-miss study: each gold query with one
plausible mistake, run against every database.

| Mistake | Queries | Pass anyway |
|---|---:|---:|
| exclusive start of the window | 43 | 0% |
| inclusive end of the window | 43 | 27.9% |
| inner join instead of the declared one | 2 | 100% |
| money rounded to whole units | 35 | 0% (88.6% with round targets) |
| all near misses | 123 | 11.4% |

```chart
type: bar
title: Plausible wrong SQL that passes anyway, by mistake
suffix: "%"
max: 100
source: the near-miss study in this pack's manifest.json

| Mistake | Pass anyway |
|---|---:|
| exclusive start of the window | 0 |
| inclusive end of the window | 27.9 |
| inner join instead of the declared one | 100 |
| money rounded to whole units | 0 |
| all near misses | 11.4 |
```

```chart
type: bar
title: Money rounded to whole units, passing anyway
suffix: "%"
max: 100
source: the near-miss study, with the targets above and with the same targets rounded

| Revenue targets | Pass anyway |
|---|---:|
| declared with cents | 0 |
| round targets | 88.6 |
```

A mistake that passes on every database is equivalent on this data, so no
execution check can catch it: an inner join changes nothing when no key is
orphaned, and an inclusive end changes nothing for the last month. Those
rates are a property of the questions, not of the rotation, and they are
the number to look at when you design a pack.

## The check

Every rotation also carries an attestation of its tables:

```bash
python pack/rotations/seed-42/verify_attestation.py
```

## Related

- [Build an evalpack](../guides/evalpack.md): where questions come from, rotations, boundary rows
- [A sandbox an agent can act in](agent-sandbox.md): the same pack used to grade a live agent
- [Publish to Hugging Face](../guides/publish.md): one split per rotation, with the near-miss numbers on the card
- [When Misata refuses](../failure-modes.md): why a question is dropped

## Files

The recipe folder runs as it is. Its files on GitHub:

- [`answers.jsonl`](https://github.com/rasinmuhammed/misata/blob/main/examples/usecases/eval-database/answers.jsonl)
- [`misata.yaml`](https://github.com/rasinmuhammed/misata/blob/main/examples/usecases/eval-database/misata.yaml)
