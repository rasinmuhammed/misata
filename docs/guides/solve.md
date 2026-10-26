---
title: Solve for a Pipeline's Output
description: Make a dbt model, a SQL query or a Python function produce the numbers you declare, by moving Misata's outcome curves until the pipeline's metrics hit their targets.
---

# Solve for a pipeline's output

An outcome curve fixes what Misata generates: the total of `orders.amount`
in each month, exactly. The number people look at is usually computed later,
by a pipeline Misata does not own: net revenue after a fee and refunds, in a
dbt model. `misata solve` closes that gap. It generates, runs your pipeline,
compares each metric with its target, adjusts the curves you name as levers,
and repeats until every period is within tolerance.

The result is a dataset that, run through your real pipeline, produces the
numbers you asked for, plus a solved schema that regenerates it exactly.

## A first solve

The schema needs an outcome curve with exact values on each lever:

```yaml
# misata.yaml
name: shop
seed: 11
tables:
  orders:
    rows: 3000
    columns:
      order_id: {type: int, unique: true}
      amount: {type: float, min: 5, max: 500}
      ordered_at: {type: datetime, start: "2025-01-01", end: "2025-03-31"}
outcome_curves:
  - table: orders
    column: amount
    time_column: ordered_at
    value_mode: absolute
    curve_points:
      - {month: 1, target_value: 50000}
      - {month: 2, target_value: 52000}
      - {month: 3, target_value: 55000}
```

The solve config names the schema, the pipeline and the targets:

```yaml
# solve.yaml
schema: misata.yaml
tolerance: 0.5%
pipeline:
  sql:
    net_revenue: |
      SELECT date_trunc('month', ordered_at), SUM(amount) * 0.97
      FROM orders GROUP BY 1
targets:
  - metric: net_revenue
    lever: orders.amount
    values: {2025-01: 70000, 2025-02: 65000, 2025-03: 72000}
```

```bash
misata solve -c solve.yaml -o solved --format parquet
```

```text
solve: converged after 4 iteration(s) in 0.3s (tolerance 0.5%)
  net_revenue: worst period off by 0.1205% (iteration 4)
wrote solved (PASSED)
```

`solved/` holds the tables, `schema.solved.json`, `misata.solved.yaml` (your
schema with only the lever's curve points replaced), `solve.json` with every
iteration, and an attestation. Generating from either solved schema
reproduces the solved tables exactly.

## Pipelines

Each metric returns two columns, the period and the value, one row per
period. A period matches a curve period when it falls inside it, so a
`date_trunc('month', ...)` timestamp, a `2025-03` label and the 15th of
March all name March on a monthly curve.

**SQL.** DuckDB queries over the generated tables, one per metric. They run
in a sandbox: the tables are readable, and files, extensions, `ATTACH` and
configuration changes are refused.

**dbt.** A dbt project run on a temporary DuckDB warehouse:

```yaml
pipeline:
  dbt:
    project_dir: analytics          # relative to solve.yaml
    select: +fct_revenue            # optional
    source_schema: main             # where your sources read the raw tables
    seeds: true                     # optional: dbt seed first (true, a name, or a list)
    metrics:
      net_revenue: SELECT month, net_revenue FROM fct_revenue
```

The generated tables are loaded into `source_schema`, `dbt seed` loads the
seeds you name (a package's lookup tables, a fee schedule), `dbt run` builds
the selected models with a generated profile (your project's profile name,
adapter `duckdb`), and the metric queries read the built models. Nothing is
written into the project folder. Needs `pip install dbt-duckdb`, and
`dbt deps` first if the project uses packages.

**Python.** From the library, any function of the tables:

```python
import misata

def net_revenue(tables):
    orders = tables["orders"]
    month = orders["ordered_at"].dt.to_period("M")
    return {"net_revenue": orders.groupby(month)["amount"].sum() * 0.97}

result = misata.solve(
    schema,
    net_revenue,
    [misata.Target("net_revenue", "orders.amount", {"2025-01": 70000, "2025-02": 65000})],
    tolerance="0.5%",
)
print(result.summary())
result.write("solved")
result.attest("solved")
```

## Direction

A lever is `direct` when more of it raises the metric. Refunds lower net
revenue, so a refund curve moving net revenue is `inverse`:

```yaml
targets:
  - metric: net_revenue
    lever: refunds.amount
    direction: inverse
    values: {2025-01: 45000, 2025-02: 49000}
```

Declaring the wrong direction makes the gap widen, and the run stops as
`diverging` and says so.

## How it steps

Each lever takes the first of these steps that applies:

1. **Coupled least squares.** Pipelines often move rows across a period
   boundary (a time-zone shift, a fiscal calendar), so feeding more into
   March also raises April. Once a lever has one more observation than it
   has periods, the solver fits how every period's output depends on every
   period's input and solves for the inputs that hit all targets at once.
   The fit is used only when it is well conditioned and does not reach far
   past the values it was fitted on.
2. **Secant.** For a period whose last two observations slope the way its
   direction says, the step goes to where that line meets the target.
   Pipelines that add or subtract the lever (net = gross - refunds) are
   lines, and this solves them in two or three iterations.
3. **Damped ratio.** Otherwise, the value is multiplied by
   `(target / measured) ** 0.85`.

No step grows a value more than twentyfold, crosses zero, or exceeds 1e12.
Every iteration uses the schema's seed and generates from a complete
schema, so the feasibility gate checks every candidate before it runs.

## When it stops

| Reason | Meaning | Exit |
|---|---|---|
| `converged` | every period is within tolerance | 0 |
| `max_iterations` | the budget ran out; the closest iteration is kept | 1 |
| `max_seconds` | the time budget ran out | 1 |
| `diverging` | the gap widened three times in a row, past where it began | 1 |
| `unresponsive` | the lever moved and the metric did not change at all | 1 |
| `pipeline_error` | the pipeline failed or returned something unreadable | 1 |
| `infeasible` | the schema, or values the solver chose, cannot generate | 3 |

A config Misata cannot use (an unknown field, a lever with no curve, a
period outside the curve) exits 2 before anything runs.

Generation is random within each period. A pipeline that reads rows across
period boundaries therefore sees some noise between iterations, about a
percent for a few thousand rows a month. A tolerance below that noise is
reached by luck rather than by steering. Raise the tolerance, or add rows.

## The certificate

With a SQL pipeline, every solved period becomes an attestation invariant
with `comparator: within_tolerance`. `verify.py` reruns your metric query
against the written files and checks it is within the tolerance of the
target, in exact decimals. A solved dataset can therefore prove, without
Misata, that your query over it gives the numbers you declared.

The solver decides convergence with the same comparison the verifier uses,
so a run that reports `converged` writes a certificate that passes.

dbt and Python pipelines need more than the written files to rerun, so their
solved periods are recorded in `solve.json`, with the pipeline's identity (a
digest of the dbt project's files, or of the function's source), rather
than as invariants.

## Proven on pipelines Misata did not write

Two external engines, run unmodified, each turning generated rows into a
number Misata never computes itself (measured 26 October 2026, M1 laptop):

| Pipeline | What is declared | Lever | Result |
|---|---|---|---|
| [PSLmodels Tax-Calculator](https://github.com/PSLmodels/Tax-Calculator) 6.8, the U.S. federal income tax code | 300 households owe $2,450,000 in 2024 | total wages | converged in 5 iterations within 0.5%, 4.7 s |
| [snowplow_web](https://github.com/snowplow/dbt-snowplow-web) 1.0.1 on dbt-duckdb, from 5 generated tables (a 129-column `atomic.events`) | 150, 210 and 300 page views in Jan to Mar 2025 | events per month | converged in 4 iterations within 1%, 80 s |

Tax is not linear in wages: brackets, the EITC phase-out and the Child Tax
Credit make doubling wages more than double the tax, which is why the secant
step does the work here. The Tax-Calculator proof runs in the test suite
when `taxcalc` is installed (`tests/test_pipeline_proofs.py`).

## From an agent

The MCP tool `solve_outcome` takes a schema dict, SQL queries and targets,
and returns the solved curve points per lever. It writes nothing, and it
runs SQL pipelines only: each query in the sandbox above, limited to 30
seconds and 2 GB.
