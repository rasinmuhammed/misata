Title: Known-answer testing for dbt: synthetic seeds where you decide the metric before the model runs

---

I want to share a testing pattern that has changed how I trust my dbt models, plus a small tool I built to make it practical. I am genuinely curious whether other people here already do a version of this, because I went looking and did not find much.

## The thing that bothered me

Here is the situation that started it. I had a `monthly_mrr` model. `dbt build` was green. Every test passed. And I still did not trust the number.

Look at what dbt tests actually check on a model like that. `unique` and `not_null` confirm the grain and the missingness. `relationships` confirms the foreign keys resolve. A `dbt_utils` expression test confirms a column is non-negative. All useful. But none of them answer the question the business actually asks, which is: **is the 142,800 in `total_mrr` for March the correct number?**

It cannot answer that, because the test data has no known true value. I seeded some rows, the model summed them, and it produced a number. The test confirms the query ran and the shape is sane. It does not confirm the aggregation logic is right. A join that quietly fans out, a filter that drops a status I forgot about, a date cast that smears rows across a month boundary, none of those fail a test that has nothing to compare against.

So I had a green pipeline and an unfalsifiable number. That is a strange place to ship from.

## The reframe: decide the answer first

The fix turned out to be simple to state. Instead of seeding some data and hoping, generate seed data where you decide the aggregate in advance, then assert the model reproduces it.

If I declare that monthly MRR should climb from 50k in January to 200k in December, and I generate subscription rows whose `amount` actually sums to those targets month by month, then `monthly_mrr` has a right answer. If the model returns it, the joins held and the group-by counted what it was supposed to. If it does not, I have a real failure, on a branch, before any production data existed.

I could not get a normal mock-data generator to do this, because a random generator has no opinion about what the monthly total should be. So I wrote a small Python tool, [Misata](https://github.com/rasinmuhammed/misata), to do it. Full disclosure up front: I am the author.

Misata is a synthetic data generator. Its defining trait is that you declare an outcome (an aggregate total, a rate, a monthly curve) and it produces individual rows that conform to it exactly, with referential integrity across tables. Pipeline testing is one job it does. The same engine handles dev-environment seeding, demos, and larger multi-table datasets. The pattern matters more than the tool, but the tool is what makes it a five-minute job instead of a spreadsheet exercise.

## The workflow

It sits in front of `dbt seed`. You declare the schema and the answer, generate, then run dbt normally.

Declare the answer (this is the source of truth, version it in git):

```yaml
# misata.yaml
tables:
  subscriptions:
    columns:
      subscription_id: { type: int, unique: true }
      user_id:         { type: foreign_key }
      amount:          { type: float, min: 5, max: 2000 }
      start_date:      { type: date }

outcome_curves:
  - table: subscriptions
    column: amount
    time_column: start_date
    time_unit: month
    avg_transaction_value: 250
    start_date: "2024-01-01"
    curve_points:
      - {month: 1,  value: 50000}
      - {month: 6,  value: 110000}
      - {month: 12, value: 200000}
```

Generate the seeds into your dbt project:

```bash
pip install misata
misata dbt-seed --config misata.yaml
```

That writes `seeds/subscriptions.csv`, `seeds/users.csv`, and a `_misata_seeds.yml` with the `unique`, `not_null`, and `relationships` tests it can infer from the schema. The per-row `amount` values are different every time, but `sum(amount)` per calendar month equals the curve you declared, to the cent.

Then the part that does the actual work, a singular test that compares the model against the declared answer key:

```sql
-- tests/assert_mrr_curve.sql
-- Returns any month where the model deviates from the declared target.
-- A singular test passes on zero rows, so this fails the build if the math is wrong.
with actual as (
    select subscription_month, total_mrr from {{ ref('monthly_mrr') }}
),
expected as (
    select subscription_month, expected_mrr from {{ ref('expected_mrr') }}
)
select e.subscription_month, e.expected_mrr, a.total_mrr,
       abs(coalesce(a.total_mrr, 0) - e.expected_mrr) as abs_error
from expected e
left join actual a using (subscription_month)
where abs(coalesce(a.total_mrr, 0) - e.expected_mrr) > 0.01
```

Run it like any dbt project:

```
$ dbt seed && dbt run && dbt test
...
1 of 5 PASS assert_mrr_curve ........................................ [PASS in 0.05s]
Done. PASS=5 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=5
```

When I deliberately broke the model (changed the group-by grain), `assert_mrr_curve` went red and printed the exact months and the dollar gap. That is the test I actually wanted the whole time.

There is a complete, runnable version here, verified end to end on dbt 1.11 with dbt-duckdb, no warehouse needed: [examples/dbt](https://github.com/rasinmuhammed/misata/tree/main/examples/dbt). Clone it, `pip install dbt-duckdb`, and `dbt seed && dbt run && dbt test` goes green.

## Where it fits, and where it does not

A few honest notes, because I would rather you find the edges from me than from a failed run.

- **Seeds are for small fixtures.** dbt seeds get unhappy past a few thousand rows. The example keeps subscriptions under 6k. For bigger datasets, generate straight to the warehouse (`misata generate --db-url ...`) and declare a dbt source instead of a seed. Same pattern, the answer key is still yours.
- **It does not find a bug you did not model.** If your real source encodes a status or a timezone quirk you never put in the schema, the generated data is innocent of it, and your model meets it for the first time in production. This proves your logic against known inputs. It is not a substitute for testing against the real sources eventually.
- **Unit tests:** there is also a `misata dbt-fixture` for dbt unit test fixtures. It generates realistic `given` inputs. You still write the `expect`, because that depends on your SQL, and I am not going to pretend a generator can infer your transformation.
- **dbt Core for the seed flow.** dbt Cloud will not let you `pip install` in the run, so the seed companion is a Core or CI thing. The warehouse-load variant works anywhere.

## Why I am posting

Two reasons. First, I think known-answer testing is underused in analytics engineering and I would like more people doing it, with whatever tool. Second, I want to know where this breaks for real projects. If you already do this with a homegrown script or hand-built golden tables, I would love to hear how it holds up at scale, especially once the rollups get deep. And if the approach is wrong-headed in some way I am not seeing, tell me that too.

Happy to answer anything about the mechanism. The exact-aggregate part is a closed-form construction if anyone wants the math, but the dbt-facing story is just: declare the number, generate the data, assert the model gives it back.
