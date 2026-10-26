---
title: "Research Benchmark Harness: Misata Against a Faker Baseline"
description: "Run Misata's offline benchmark harness to compare a declared, verified Misata workflow with a hand-written Faker baseline on the same tasks."
---

# Research Benchmarks

Misata includes an offline benchmark harness for comparing a proof-backed Misata workflow with a hand-written Faker baseline.

```bash
python benchmarks/bench_research_moat.py
```

The harness reports:

- rows per second
- foreign-key orphan count
- reproducibility with a fixed seed
- scenario-control support
- Oracle report availability
- a simple setup-effort proxy

The point is not to claim that one library is always faster. The point is to make Misata's research claim measurable: it generates relational data and a proof report from one high-level description, while manual baselines need custom glue code for schema, relationships, scenario logic, and checks.
