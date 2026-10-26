---
title: SQL Take-Home Exercises With a Different Answer Key per Candidate
description: Give every candidate or student the same SQL questions on their own generated bookshop database, with their own numbers, an answer key verified before it ships, and grading that runs their SQL on two databases.
---

# Take-home exercises and coursework

A take-home with one dataset has one answer key, and after the first round
it is on the internet. Writing a new dataset by hand each time means
writing a new answer key, and the key is where the mistakes hide. Here every
candidate gets the same questions on a database of their own, every answer
is declared before the data exists, and every key is checked before it
ships.

**Who:** hiring teams, bootcamps and course authors teaching SQL or
analytics.
**Time:** about a second per candidate.

## The course

```yaml
# course.yaml
name: bookshop_takehome
seed: 100
tables:
  customers:
    rows: 1500
    columns:
      customer_id: {type: int, unique: true, min: 1, max: 1500}
      city: {type: categorical, choices: [Leeds, Bristol, Glasgow, Cardiff, Belfast]}
  orders:
    rows: 12000
    columns:
      order_id: {type: int, unique: true, min: 1, max: 1000000}
      customer_id: {type: foreign_key}
      genre: {type: categorical, choices: [fiction, nonfiction, children, comics]}
      amount: {type: float, min: 3, max: 220}
      ordered_on: {type: date, start: "2025-01-01", end: "2025-04-30"}
relationships:
  - customers.customer_id -> orders.customer_id
outcome_curves:
  - table: orders
    column: amount
    time_column: ordered_on
    value_mode: absolute
    start_date: "2025-01-01"
    curve_points:
      - {month: 1, target_value: 61250.40}
      - {month: 2, target_value: 58410.15}
      - {month: 3, target_value: 66980.72}
      - {month: 4, target_value: 70115.09}
group_shares:
  - table: orders
    measure: amount
    group_column: genre
    shares: {fiction: 0.45, nonfiction: 0.25, children: 0.2, comics: 0.1}
```

`takehomes.py` (in this folder) turns that into one exercise per candidate.
From a hash of the candidate's name it scales the revenue targets by 0.8 to
1.25, moves the order count by up to a tenth and picks a seed, so the build
is reproducible and every candidate's numbers are their own.

## Build them

```bash
pip install "misata[evalpack]"
python takehomes.py ada grace linus
```

```text
candidate     seed questions  q001 answer
ada         486789        31  56724.0
grace       627988        31  50519.33
linus       799284        31  54439.36
```

For each candidate you get two folders:

| Folder | Who gets it | Contents |
|---|---|---|
| `handouts/<name>/` | the candidate | `tables/customers.csv`, `tables/orders.csv`, `questions.md` |
| `packs/<name>/` | you | the answer key, the gold SQL, a second database, `verify.py` |

Of the 31 questions, 29 have a different answer for each of the three
candidates. The two that match are the busiest month (April for everyone,
because the course's curve peaks there) and the count of orders without a
customer, which is always 0.

## Grade a submission

Ask for SQL, one JSON line per answer. `grace.jsonl` holds three of Grace's:

<!-- stranger: skip, one sample answer is wrong on purpose -->
```bash
python packs/grace/verify.py --candidates grace.jsonl
```

```text
OK   q001: 50519.33
FAIL q005: expected 211772.65; seed-627988: 237782.06; seed-627989: 237782.06
OK   q006: 3088

2/3 match on all 2 database(s)
```

Her `q005` is `SELECT 237782.06`: Ada's total, pasted in. It fails because
Grace's books are not Ada's. The SQL also has to hold on a second database
she never saw, so a query that fits one set of rows by accident fails too.

Per-candidate numbers stop shared answers, not shared queries: two
candidates who swap SQL both pass. Grade the SQL as well as the result if
that matters to you.

## The check

Each key is verified before it is handed to anyone:

```bash
python packs/ada/verify.py
```

```text
31/31 match on all 2 database(s)
```
