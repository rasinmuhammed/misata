---
title: A Sandbox an AI Agent Can Act In
description: Give a SQL or data agent a seeded SQLite database through MCP or the CLI, with declared facts it must recover, and grade the SQL it writes on three rotated copies of the same world.
---

# A sandbox an agent can act in

An agent that writes SQL needs a database to practise on, and you need to
know whether what it wrote is right. A copy of production gives you the
first and not the second. Here the database is generated from declared
facts, so every question you ask the agent has an answer you wrote down
before the data existed.

**Who:** builders of SQL agents, data agents and coding agents.
**Time:** about a second for the sandbox, three for the grader.

## The world

A help desk: 600 accounts, 9,000 invoices, 12,000 tickets. The facts are
declared, not sampled:

```yaml
# misata.yaml
name: helpdesk_sandbox
seed: 42
tables:
  accounts:
    rows: 600
    columns:
      account_id: {type: int, unique: true, min: 1, max: 600}
      plan: {type: categorical, choices: [starter, growth, scale], probabilities: [0.55, 0.3, 0.15]}
      region: {type: categorical, choices: [amer, emea, apac]}
  invoices:
    rows: 9000
    columns:
      invoice_id: {type: int, unique: true, min: 1, max: 1000000}
      account_id: {type: foreign_key}
      product: {type: categorical, choices: [seats, usage, support]}
      amount: {type: float, min: 20, max: 4000}
      issued_at: {type: date, start: "2025-01-01", end: "2025-04-30"}
  tickets:
    rows: 12000
    columns:
      ticket_id: {type: int, unique: true, min: 1, max: 1000000}
      account_id: {type: foreign_key}
      priority: {type: categorical, choices: [low, normal, urgent], probabilities: [0.3, 0.55, 0.15]}
      escalated: {type: boolean}
      opened_at: {type: date, start: "2025-01-01", end: "2025-04-30"}
relationships:
  - accounts.account_id -> invoices.account_id
  - accounts.account_id -> tickets.account_id
outcome_curves:
  - table: invoices
    column: amount
    time_column: issued_at
    value_mode: absolute
    start_date: "2025-01-01"
    curve_points:
      - {month: 1, target_value: 182340.55}
      - {month: 2, target_value: 190118.02}
      - {month: 3, target_value: 204977.61}
      - {month: 4, target_value: 211503.89}
group_shares:
  - table: invoices
    measure: amount
    group_column: product
    shares: {seats: 0.6, usage: 0.3, support: 0.1}
rate_curves:
  - table: tickets
    column: escalated
    time_column: opened_at
    rate_points:
      - {period: "2025-01", rate: 0.12}
      - {period: "2025-04", rate: 0.07}
```

Invoice revenue is 182,340.55 in January, 190,118.02 in February, 204,977.61
in March and 211,503.89 in April. In every month, seats bring exactly 60% of
it, usage 30% and support 10%. Escalations fall from 12% of tickets to 7%.

## Give the agent its sandbox

```bash
pip install "misata[evalpack]"
misata sandbox -c misata.yaml --db sandbox.db
```

`sandbox.db` is a SQLite file with every foreign key checked. Dates are
stored as `YYYY-MM-DD` text, so the agent's date filters behave as they
would on DuckDB or Postgres. Misata marks the file as its own and refuses to
overwrite any database it did not create.

To let an agent create and query it on its own, register the MCP server
once:

<!-- stranger: skip, registers a server with a local agent -->
```bash
pip install "misata[mcp]"
claude mcp add misata misata-mcp
```

The agent then has `explain_schema` (what a schema will produce, before
any rows exist), `create_sandbox` (pass this schema as a dict) and
`query_sandbox`, which runs on a connection SQLite itself keeps read-only.
From a shell, the same query looks like this:

```bash
misata sandbox -c misata.yaml --db sandbox.db --sql "SELECT product, ROUND(SUM(amount), 2) AS revenue FROM invoices GROUP BY product ORDER BY revenue DESC"
```

## Build the grader

The grader is an evalpack of the same schema: the questions the agent
should answer, with their declared answers, and three databases that hold
the same facts in different rows.

```bash
misata evalpack -c misata.yaml -o pack --rotations 3
```

Give the agent the `question` field of each line in `pack/questions.jsonl`.
Collect its SQL as one JSON line per answer, `{"id": ..., "sql": ...}`.

## Grade it

`agent.jsonl` holds four answers an agent wrote against the sandbox:

<!-- stranger: skip, one sample answer is wrong on purpose -->
```bash
python pack/verify.py --candidates agent.jsonl
```

```text
OK   q003: 204977.61
OK   q013: 0
OK   q021: 122986.57
FAIL q027: expected 473364.04; seed-42: 467644.51; seed-43: 468479.53; seed-44: 469368.97

3/4 match on all 3 database(s)
```

`q027` asks for seats revenue from January through April. The agent wrote
`issued_at < '2025-04-30'` and lost the last day. The sandbox gave it
467,644.51 too: nothing in the data says that number is wrong. Only the
declared answer does.

The sandbox and the `seed-42` rotation are the same rows, so a query that
returns one number in the sandbox returns the same number in the grader.
A query passes only when it matches on all three rotations.

## The check

The answer key is checked before anyone grades against it:

```bash
python pack/verify.py
```

```text
27/27 match on all 3 database(s)
```
