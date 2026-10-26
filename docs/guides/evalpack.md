# Build an evalpack

An evalpack is a database with questions whose answers were fixed before a
row existed. Misata derives each answer from the schema's declarations,
generates the data, then runs every gold SQL against the written files with
DuckDB and ships only the questions that match exactly. It is built for
scoring text-to-SQL systems and data agents.

```bash
pip install "misata[evalpack]"
misata evalpack -c misata.yaml -o pack --seed 42 --rotations 3
```

```python
from misata.evalpack import build_evalpack

result = build_evalpack(schema, "pack", rotations=3)
assert result.all_verified, result.summary()
```

## Where the questions come from

| Declaration | Questions |
|---|---|
| `outcome_curves` | each period's total, the grand total, the peak period, rows per period |
| `rate_curves` | the rate at each anchor, when the rounded row count makes it exact |
| `group_shares` | each group's total per period and over the whole table |
| `balanced_ledger` | every entry and the trial balance net to zero |
| `waterfalls` | opening plus movements equals closing |
| relationships | no child row points at a missing parent |

A schema with none of these ships no questions, and the command exits 1.

## What a pack holds

| Path | Contents |
|---|---|
| `questions.jsonl` | one question per line: `id`, `question`, `gold_sql`, `expected_answer`, `answer_type`, `round_decimals` |
| `tables/` or `rotations/seed-N/tables/` | the database, one CSV per table |
| `certificate.json` | the verification run: DuckDB version, observed value per question |
| `manifest.json` | seed, Misata version, spec hash, every dropped question and why, the near-miss study |
| `verify.py` | reruns every gold SQL, or scores yours, with only `duckdb` |
| `attestation.intoto.json` | each table pinned by SHA-256; see [Attest a dataset](attest.md) |

## Score a model

```bash
python pack/verify.py                                # every gold SQL, every database
python pack/verify.py --candidates answers.jsonl    # your SQL
```

Candidates are JSON Lines of `{"id": "q001", "sql": "..."}`, a JSON list of
them, or one object mapping id to SQL. Numbers are compared at the
question's `round_decimals` and strings exactly. A query that errors is a
wrong answer. The script exits 0 when every candidate matches.

## Rotations

`--rotations N` writes N databases from seeds `SEED` to `SEED+N-1`. They
share every declared answer and differ in every row. A question ships only
when its answer holds on all of them, and a candidate counts as correct
only when it matches on all of them.

That catches queries that depend on particular rows rather than on the
question: a hard-coded key, a `LIMIT` without `ORDER BY`, a filter that
happens to select the same rows in one database. It does not catch a model
that memorised the answers, because the answers are the same in every
rotation by design.

Every rotated pack measures what rotation bought on its own data.
`manifest.json` → `near_miss_study` applies one plausible mistake at a time
to each gold SQL and records how often the result still matches:

| Mistake | Change to the gold SQL |
|---|---|
| `inclusive_end` | `< TIMESTAMP` becomes `<= TIMESTAMP` |
| `exclusive_start` | `>= TIMESTAMP` becomes `> TIMESTAMP` |
| `inner_join` | `LEFT JOIN` becomes `JOIN` |
| `whole_units` | a money total rounded to whole units |

A mistake that matches every database returns the right answer on this
data, so no execution check can catch it. Matching one database is what
single-database execution accuracy accepts.

## Put rows on the boundaries

A window closed at the wrong end changes the answer only when a row sits
exactly on the boundary. Timestamps drawn to the nanosecond never do, so
those mistakes pass on any number of databases. Declare the curve's time
column as a `date` and every row sits at midnight, so each period boundary
carries rows:

| Time column | `exclusive_start` passes | `inclusive_end` passes |
|---|---|---|
| `datetime` | 100% | 100% |
| `date` | 0% | 12% |

Measured on the 12-month, three-rotation pack in
`tests/test_evalpack_rotations.py`. The `inclusive_end` mistakes that still
pass close the last period, where no row exists past the end of the curve.
A `time_grids` declaration can put the dates in business hours: on a `date`
column the grid never changes the day. On a `datetime` curve column a grid
is refused, because rows late on a period's last day would roll into the
next period.

## Limits

- Questions come only from declarations, so they test aggregation over
  time windows, groups and joins, not arbitrary SQL.
- Gold SQL is DuckDB dialect.
- A pack is reproducible from `manifest.json`'s schema and seed with the
  same Misata version.
- Why a candidate question was dropped is listed in
  [failure modes](../failure-modes.md#evalpack-question-gates).
