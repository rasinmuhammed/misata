---
title: "Synthetic Data Benchmarks: Validity, Realism and the Gauntlet"
description: "Every published Misata measurement in one place, with the command that reproduces it: rule violations on five DDL schemas, detection AUC on real orders and trips, and 136 SQL assertions over a 13-table schema."
---

# Benchmarks

Three benchmarks, three different questions. Each number on this page comes
from a file in the repository and has a command that reproduces it.

| Benchmark | Question | Reproduce |
|---|---|---|
| [Validity](validity-benchmark.md) | Does the data obey its own schema's keys and CHECK rules? | `python -m benchmarks.validity_bench` |
| [Realism](realism-benchmark.md) | How close does it get to real data of the same kind, without seeing any? | `python -m benchmarks.realism_bench --seed N` |
| The Gauntlet | Does it survive a reviewer running arbitrary joins and group-bys? | `python -m benchmarks.gauntlet` |

The validity and realism numbers are collected in
`benchmarks/results/summary.json`.

## Validity: zero violations, by construction

Five SQL schemas, each generated from its DDL with nothing else configured,
and checked by a pandas checker that shares no code with Misata.

```chart
type: bar
title: Rule violations per schema (lower is better)
unit: violations
source: benchmarks/results/summary.json, validity.totals; Misata 0.9.7, seed 7

| Schema | Misata from DDL | Faker script | SDV HMA |
|---|---:|---:|---:|
| saas_billing | 0 | 36150 | could not run |
| org_chart | 0 | 15014 | 4807 |
| marketplace_m2m | 0 | 42387 | 5557 |
| hotel_bookings | 0 | 50416 | 3055 |
| retail_chain_6_levels | 0 | 24025 | could not run |
```

SDV's open-source multi-table model refuses schemas with more than five
tables or foreign keys more than two levels deep, so it could not run two
of the five. [Full results and method](validity-benchmark.md).

## Realism: better than a script, behind a fitted model on taxis

A classifier tries to tell generated rows from held-out real rows; 0.5
means it cannot. Blind contestants never see a real row.

```chart
type: bar
title: Detection AUC, mean of five seeds (lower is better)
min: 0.5
max: 0.85
reference: 0.5
source: benchmarks/results/summary.json, realism.datasets.*.detect_auc.mean

| Generator | Olist | NYC taxis |
|---|---:|---:|
| misata_mimic (fitted) | 0.537 | 0.543 |
| misata_schema (blind) | 0.629 | 0.75 |
| sdv_copula (fitted) | 0.711 | 0.675 |
| faker_script (blind) | 0.783 | 0.788 |
```

On Olist orders, blind Misata is harder to detect than SDV fitted on the
real orders. On taxi trips it beats the Faker script but not SDV fitted on
the trips, because blind fares are drawn from a generic money shape.
`mimic` scores best and is fitted to the real rows, so it is not anonymous.
[Full results, every metric and the caveats](realism-benchmark.md).

## The Gauntlet: 136 SQL assertions

A 13-table relational schema and 136 independent SQL assertions,
each a query returning the number of violating rows, run by DuckDB against
the generated tables. The assertions cover keys, value domains, temporal
order, status gates, parent totals that equal their child facts (including
across several hops), denormalised copies, geography, arithmetic, degenerate
distributions, lifecycles, missingness and late arrivals. Aggregate checks
are exact to the cent, in SQL.

```chart
type: bar
title: Gauntlet assertions that hold, out of 136
max: 136
source: CHANGELOG.md, 0.9.8, "Declared values hold"

| Generator | Assertions held |
|---|---:|
| Misata | 136 |
| Faker script | 78 |
```

The Faker script is a careful one: foreign keys sampled from parent ids,
real formats, line totals computed as quantity times price. What it does not
do is build a constraint solver by hand, so aggregates, status gates,
temporal order and geography consistency fail. Reproduce with
`python -m benchmarks.gauntlet` and
`python -m benchmarks.gauntlet_compare --tool faker`. The harness can also
score SDV (`--tool sdv`), but no SDV score is published because it has not
been run.

## Reproducibility

`python -m benchmarks.golden` regenerates a set of story, dict and DDL
schemas and compares their `misata.fingerprint` hashes; CI requires the same
hashes on Linux, macOS and Windows.

## Related

- [Limitations](limitations.md): what none of these benchmarks covers
- [Research benchmarks](guides/research-benchmarks.md): the offline harness against a hand-written Faker baseline
- [Faker vs SDV vs Misata](guides/faker-vs-sdv-vs-misata.md): choosing between them
