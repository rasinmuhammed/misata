<div align="center">

<img src="https://raw.githubusercontent.com/rasinmuhammed/misata/main/public/logo.png" width="160" alt="Misata" />

# Misata

### Declare what must be true. Get data that makes it true. Prove it.

Misata is a declarative synthetic data generator for Python. You write down the
facts a dataset has to satisfy, from a monthly revenue curve to a balanced
ledger to a foreign key that must never dangle, and the engine builds
multi-table data that satisfies all of them at once. Then DuckDB checks the
files on disk and writes a certificate anyone can re-run.

[![PyPI](https://img.shields.io/pypi/v/misata.svg?style=flat-square&color=E89030)](https://pypi.org/project/misata/)
[![Python](https://img.shields.io/pypi/pyversions/misata.svg?style=flat-square)](https://pypi.org/project/misata/)
[![Tests](https://img.shields.io/github/actions/workflow/status/rasinmuhammed/misata/ci.yml?branch=main&style=flat-square&label=tests)](https://github.com/rasinmuhammed/misata/actions)
[![License](https://img.shields.io/github/license/rasinmuhammed/misata.svg?style=flat-square)](https://github.com/rasinmuhammed/misata/blob/main/LICENSE)
[![arXiv](https://img.shields.io/badge/arXiv-2606.08736-b31b1b?style=flat-square)](https://arxiv.org/abs/2606.08736)
[![Open in Colab](https://img.shields.io/badge/Open%20in-Colab-F9AB00?style=flat-square&logo=googlecolab&logoColor=white)](https://colab.research.google.com/github/rasinmuhammed/misata/blob/main/notebooks/quickstart.ipynb)
[![smithery badge](https://smithery.ai/badge/misata/misata)](https://smithery.ai/servers/misata/misata)

[Docs](https://misata.studio/docs) · [Use cases](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/) · [The language](https://github.com/rasinmuhammed/misata/blob/main/LANGUAGE.md) · [Limitations](https://github.com/rasinmuhammed/misata/blob/main/LIMITATIONS.md) · [Studio](https://misata.studio) · [Changelog](https://github.com/rasinmuhammed/misata/blob/main/CHANGELOG.md)

</div>

<!-- mcp-name: io.github.rasinmuhammed/misata -->

---

## Sixty seconds

```bash
pip install "misata[duckdb]"
```

```yaml
# misata.yaml
seed: 7
tables:
  customers:
    rows: 2000
    columns:
      customer_id: {type: int, unique: true, min: 1, max: 2000}
      name: {type: text, text_type: name}
      signed_up: {type: date, start: "2024-01-01", end: "2024-12-31"}
  orders:
    rows: 40000
    columns:
      order_id: {type: int, unique: true, min: 1, max: 1000000}
      customer_id: {type: foreign_key}
      channel: {type: categorical, choices: [web, app, store]}
      amount: {type: float, min: 5, max: 900}
      ordered_at: {type: date, start: "2025-01-01", end: "2025-12-31"}
relationships:
  - customers.customer_id -> orders.customer_id
outcome_curves:
  - table: orders
    column: amount
    time_column: ordered_at
    start_date: "2025-01-01"
    curve_points:
      - {month: 1, target_value: 180000}
      - {month: 6, target_value: 240000}
      - {month: 12, target_value: 310000}
group_shares:
  - table: orders
    measure: amount
    group_column: channel
    shares: {web: 0.5, app: 0.3, store: 0.2}
```

```bash
misata generate -c misata.yaml -o data --attest
python data/verify.py
```

```text
Attestation: data
  result: PASSED
  files pinned: 2
  invariants held: 69 of 69

ok    2 file(s) match their attested sha256
ok    69 of 69 invariant(s) hold
```

The 69 are derived from the YAML before a row exists: twelve monthly revenue
totals (180,000.00 in January, 240,000.00 in June, 310,000.00 in December,
straight lines between), the channel split inside every one of those months,
the planned row count per month, zero orphaned `customer_id`s and unique keys.
`verify.py` needs only the standard library and `duckdb`, and it shares no
code with the generator. Change one cent in one row and it says so:

```text
FAIL  orders.csv: sha256 301165f9dc4e does not match the attested 670f89195826
FAIL  orders.amount.month:1.outcome_curve_period: expected 180000.00, observed 180000.01
FAIL  orders.amount.outcome_curve_total: expected 2945000.00, observed 2945000.01
FAIL  orders.amount.web.2025-01.group_share_period: expected 90000.00, observed 90000.01
FAIL  orders.amount.web.group_share_total: expected 1472500.00, observed 1472500.01
FAIL  65 of 69 invariant(s) hold
```

---

## Why declare instead of generate

Every test fixture has an oracle problem. To check a dbt model, a Spark job,
a dashboard tile or a data agent you need input data **and** an answer you
know independently of the code under test. Copying production gives you data
without an answer. Hand-written fixtures give you an answer that rots. Random
generators give you data whose answer you have to compute with the code you
are testing.

Misata turns it around. The specification is the ground truth and the rows are
derived from it. "January revenue is 180,000" is true before a single row
exists, so your pipeline either returns 180,000.00 or it has a bug.

Three properties make this different from a generator with options:

- **A declaration is honoured or refused, never quietly replaced.**
  Declarations that cannot all hold stop generation with an error that names
  each one, shows the arithmetic and suggests the change.
- **The certificate is checked by code that did not write the data.** A bug
  in Misata's arithmetic shows up as a failed invariant, not a
  self-consistent wrong answer.
- **The same spec, seed and version give the same bytes** on Linux, macOS and
  Windows, so a fixture can live in git with its fingerprint.

---

## The evidence

<div align="center">
<img src="https://raw.githubusercontent.com/rasinmuhammed/misata/main/docs/assets/readme/gauntlet-light.svg" width="680" alt="The Gauntlet, assertions held per section. Misata holds 136 of 136. A Faker script with the same columns holds 78 of 136: it ties on keys, value domains, diamond joins, arithmetic and distributions, and loses on time ordering, status-implied fields, cross-table totals, geography, lifecycles, missingness, late arrivals and grids.">

<sub>The Gauntlet: 13 tables and 136 SQL assertions run by DuckDB. The Faker script ties wherever a fact is about one column at a time and loses wherever columns, rows or tables have to agree. <a href="https://github.com/rasinmuhammed/misata/blob/main/benchmarks/gauntlet.py">Source</a>, rerun with <code>python -m benchmarks.gauntlet</code>.</sub>
</div>

<br/>

<div align="center">
<img src="https://raw.githubusercontent.com/rasinmuhammed/misata/main/docs/assets/readme/detection-light.svg" width="680" alt="Detection AUC, lower is better, 0.5 means a classifier cannot tell generated rows from real ones. Olist orders: Misata from a declared schema 0.63, Misata from a sentence 0.73, Faker script 0.78, SDV fitted to the real data 0.71, Misata mimic 0.54. NYC taxi trips: 0.75, 0.80, 0.79, 0.68 and 0.54.">

<sub>A gradient-boosted classifier tries to tell generated rows from real ones; mean of five seeds. Without seeing a real row, a declared schema beats SDV trained on the real orders. On taxi trips SDV wins: blind fares are a miss. <a href="https://github.com/rasinmuhammed/misata/blob/main/benchmarks/realism_bench.py">Source</a>, numbers in <a href="https://github.com/rasinmuhammed/misata/blob/main/benchmarks/results/summary.json">summary.json</a>.</sub>
</div>

<br/>

| Claim | Measured | Reproduce |
|---|---|---|
| Valid by construction | 0 violations of keys, CHECK, UNIQUE, NOT NULL and self-reference trees on five DDL schemas. A per-column Faker script: 15,014 to 50,416 per schema. SDV's multi-table model trained on valid data: 3,055 to 5,557, and it refuses two of the five | `python -m benchmarks.validity_bench` |
| Conformance | 294 SQL assertions in three suites, all held: the Gauntlet 136, the Warren 110, the Ledger 48 | `python -m benchmarks.gauntlet` |
| Reproducible | identical fingerprints on Linux, macOS and Windows | `python -m benchmarks.golden` |
| Scale | 10,000,000 rows across 14 tables in 36.3 s at 0.78 GB peak on an Apple M1, every foreign key checked afterwards | `python benchmarks/bench_r3_volume.py --scale 10 --stream out/` |

---

## What you can declare

Each declaration has a guarantee stated so you could test it, a list of the
columns it owns, a cost and a refusal. [LANGUAGE.md](https://github.com/rasinmuhammed/misata/blob/main/LANGUAGE.md) is the
reference. All 25 declaration kinds are checked for feasibility before a row
exists and re-checked on the rows afterwards; the ones marked ✓ are also in
the DuckDB certificate.

| Declare | What holds | Certificate |
|---|---|:---:|
| `outcome_curves` | a measure's total per period, to the cent | ✓ |
| `rate_curves` | the share of rows flagged per period, to the nearest row | ✓ |
| `group_shares` | each group's share of a measure inside every period | ✓ |
| `balanced_ledger` | debits equal credits per entry, and the trial balance is zero | ✓ |
| `waterfalls` | opening plus movements equals closing, per component | ✓ |
| relationships, `min_children`, `partition_by` | no orphans, no childless parent, no key crossing a tenant | ✓ |
| `unique`, `inequality`, `col_range`, choices, NOT NULL, DDL `CHECK` | no row breaks the rule | ✓ |
| `lifecycles` | a status implies its whole history: the right timestamps set, in order, and the rest null | ✓ |
| `dag_edges`, `graph_motifs` | no cycle outside a planted case; each ring, fan and chain at its exact count | ✓ |
| roll-ups, `stock_flows`, `scd2`, `bitemporal`, `when_then`, `lte_parent` | parents equal their children, inventory balances, versions tile a timeline | |
| `outliers`, `typos`, `duplicates`, `missingness`, `late_arrivals` | dirt at exact counts, with an answer key | |
| `retention`, `joint_distributions`, `time_grids`, `event_logs`, `processes` | cohort curves, joint margins, a declared clock, logs that agree with status | |

Underneath any declaration, foreign keys resolve by construction (parents are
built before children), text agrees with its row, money is skewed, timestamps
have a daily rhythm and a few customers place most of the orders, so the data
looks like a business before you declare anything. A sentence picks one of 18
story domains, from SaaS and fintech to healthcare, logistics and streaming,
each with its tables, keys and calibrated distributions.

---

## Pick your entry point

| You have | Call | Notes |
|---|---|---|
| A sentence | `misata.generate("A SaaS company with 1,000 customers", seed=42)` | fastest start; print the tables or `misata explain` to see what it built |
| YAML or a dict | `misata.generate_from_schema(schema)` | every declaration holds, or it refuses |
| SQL DDL | `misata.from_ddl(ddl)` or `misata generate -c schema.sql` | NOT NULL, UNIQUE, composite keys, CHECK ranges and enums, self-references |
| A live database | `misata seed postgresql://...` | introspects, inserts in one transaction, never truncates unless you pass `--truncate` |
| A dbt project | `misata dbt-unit-test --select my_model` | fixtures from `manifest.json` whose keys agree |
| Prisma or Django | `misata prisma-seed`, `misata.from_django(app_labels=[...])` | |
| More rows than memory | `misata.generate_stream(schema)` | yields `(table, batch)`; partitioned Parquet, one file per partition |
| A pipeline whose output must hit a number | `misata solve -c solve.yaml` | drives inputs through your real dbt or Python pipeline to a declared outcome, within a stated tolerance |
| A dataset to share | `misata publish data --hf you/name` | re-verifies, then uploads the data with its spec, certificate and verifier |
| Real rows to imitate | `misata.mimic(df)` | fitted to real rows; **not** anonymous |

Pass a seed every time. The same seed is the same data.

---

## Twelve recipes

Each is a folder with the schema, the commands, and the check that proves the
declaration held. `tools/stranger.py --clean` runs every command on every page
from a freshly built wheel in a clean virtualenv before each release, so the
numbers on the pages are what you will see.

| Recipe | For | Proof |
|---|---|---|
| [Seed a dev database](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/seed-a-dev-database/) | app developers, coding agents | 22 invariants from three `CREATE TABLE` statements |
| [Known-answer tests for dbt](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/dbt-known-answer-tests/) | analytics engineers | a dbt test that catches the last-day-of-month bug |
| [A warehouse before users](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/warehouse-before-users/) | founders, data leads | 291,000 rows of partitioned Parquet, 80 invariants |
| [A demo tenant](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/demo-tenant/) | sales engineers, PMs | churned and healthy accounts, a few whales; realism 0.96 |
| [An eval database](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/eval-database/) | AI labs, eval teams | text-to-SQL answers verified on three rotated databases |
| [An agent sandbox](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/agent-sandbox/) | agent builders | the sandbox and the grader agree row for row |
| [Load testing](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/load-testing/) | platform engineers | hot keys and a daily curve, keys checked before replay |
| [Fraud and AML](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/fraud-aml/) | risk and ML teams | an acyclic background and every ring at its declared count |
| [Ledgers that reconcile](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/ledgers-that-reconcile/) | finance engineering, audit | two fiscal years, 52 invariants, trial balance zero |
| [Take-home exercises](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/take-home-exercises/) | hiring teams, course authors | a different answer key per candidate, each verified |
| [PII-free environments](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/pii-free-environments/) | regulated teams | staging data from production DDL, never production rows |
| [Example data for docs](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/example-data-for-docs/) | DX, API and SDK teams | nested JSONL whose ids resolve across files |

---

## A status that implies its history

Declare the state machine once and every row's timestamps follow from its
status. From the [demo tenant](https://github.com/rasinmuhammed/misata/tree/main/examples/usecases/demo-tenant/):

```yaml
lifecycles:
  - name: subscription
    table: subscriptions
    state_column: status
    start_column: started_at
    initial: trialing
    states:
      - {name: trialing}
      - {name: active, timestamp: activated_at}
      - {name: past_due, timestamp: past_due_at}
      - {name: churned, timestamp: churned_at, terminal: true}
    transitions:
      - [trialing, active]
      - [trialing, churned]
      - [active, past_due]
      - [active, churned]
      - [past_due, churned]
    weights: {trialing: 0.07, active: 0.6, past_due: 0.07, churned: 0.26}
```

Of 1,200 subscriptions, exactly 720 are active, 312 churned, 84 past due and
84 still trialing: weights are counts, allocated by largest remainder, not
probabilities. Every past-due row has an activation date and a past-due date,
in that order and after it started; no active row has a churn date. The
certificate checks both, row by row. A state reachable several ways splits its
rows across every route: of the 312 churned, 156 left during the trial, 78
after being active and 78 after falling past due.

---

## When it says no

```text
$ misata explain bad.yaml
Generation would refuse: 1 conflict(s).
1 declaration cannot be satisfied together:
  1. [orders.channel] group_shares on amount
      declared shares sum to 1.500 (web=0.6, app=0.6, store=0.3); a share of a whole cannot exceed 1.0
      → Suggestion: scale the shares so they sum to 1.0, or drop a group. Misata will not renormalise them for you, because the result would be a specification you did not write
Nothing was generated. Change the declarations each conflict names; its remedy says how.
```

`misata explain` prints the planned rows, what each declaration will write,
how many invariants the certificate will carry and every conflict, without
generating anything. Every command takes `--json` and prints one envelope;
exit code 3 means the declarations cannot all hold and nothing was written.

---

## With a coding agent

The agent designs the schema, Misata does the arithmetic, and DuckDB checks
it. An agent cannot certify its own output; this is how it gets an answer it
did not write.

[![Install in Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=misata&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJtaXNhdGFbbWNwXSIsIm1pc2F0YS1tY3AiXX0=)

```bash
claude mcp add misata -- uvx --from "misata[mcp]" misata-mcp   # Claude Code
misata mcp install --client all                                  # Cursor, Windsurf, Claude Desktop
```

Fifteen tools: `generate_from_schema`, `generate_dataset`, `explain_schema`,
`validate_yaml`, `inspect_schema`, `preview_story`, `list_domains`,
`validate_domain`, `seed_database`, `create_sandbox`, `query_sandbox`,
`solve_outcome`, `attest_dataset`, `audit_dataset` and `check_realism`.
[AGENTS.md](https://github.com/rasinmuhammed/misata/blob/main/AGENTS.md) tells an agent which entry point fits which job and
which claims the evidence supports.

---

## What it is not

Misata **imitates nothing** unless you ask it to. It does not learn a joint
distribution from your data. If you need a statistical twin of a specific
private table, use a differentially private synthesizer with a stated
epsilon. `mimic` fits to real rows and is not anonymous.

It is **exact for what can be declared** (sums, rates, shares, roll-ups,
ledgers, keys, lifecycles) and **not for arbitrary SQL**. A model built on a
window function or business logic Misata cannot invert still gets coherent,
key-valid inputs, and you write the expected output. `misata solve` closes
part of that gap by driving inputs through your real pipeline to a declared
outcome within a stated tolerance, and the certificate says which tolerance.

Priors are English-first and US-leaning on money, and rates round to whole
rows. [LIMITATIONS.md](https://github.com/rasinmuhammed/misata/blob/main/LIMITATIONS.md) has the full list and wins any
argument with the rest of the docs.

| | Imperative | Inferential | Declarative |
|---|---|---|---|
| You give it | code that emits values | real data to fit | facts that must hold |
| It guarantees | nothing after the fact | resemblance, approximately | the facts exactly, or a refusal |
| Foreign keys | your problem | per table fine, across tables fragile | by construction |
| Needs real data | no | yes | no |
| Examples | Faker, Mockaroo, LLM seed scripts | SDV, learned synthesizers | Misata |

---

## Cite

```bibtex
@article{rasin2026declarative,
  title  = {Declarative Outcome-Conformant Synthesis: Exact, Closed-Form
            Specification Satisfaction and a Conformance Benchmark},
  author = {Rasin, Muhammed},
  year   = {2026},
  url    = {https://arxiv.org/abs/2606.08736}
}
```

## Contribute

```bash
git clone https://github.com/rasinmuhammed/misata && cd misata
uv sync --all-extras && uv run pytest -q
python tools/stranger.py --clean    # every documented command, from the built wheel
```

A capability earns a place only if it can be declared and verified. The
conformance suites in `benchmarks/` are the contract: write the assertion
first, watch it fail, then make it pass. MIT licensed.
