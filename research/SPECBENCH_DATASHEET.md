# Datasheet for SpecBench

This datasheet follows the structure of Gebru et al., *Datasheets for Datasets*. SpecBench is
a benchmark for outcome-conformant relational synthesis: it measures whether a generator obeys
a declared analytical outcome (an aggregate curve, a rate, a group-wise distribution) across a
relational schema, rather than whether its output resembles a real dataset. SpecBench is
code-defined: a task is a frozen specification plus an oracle, and the "data" a user consumes
is the set of task definitions, the metric implementations, the baseline adapters, and the
result tables produced by running them.

## Motivation

**For what purpose was the benchmark created?** Existing tabular-synthesis benchmarks (SDGym
over SDMetrics, and recent multi-dimensional frameworks) score fidelity to a reference dataset
and therefore presuppose that real data exists. They cannot express conformance: whether a
generator, given only a specification and no source data, produces a relational dataset that
satisfies a declared analytical outcome. SpecBench fills that gap. It scores aggregate-match
error, rate and group-distribution conformance, controllability, foreign-key integrity,
temporal coherence, and determinism, and it pairs each metric with a proposition about the
reference engine so the benchmark is the measurement arm of an analysis rather than a detached
scoreboard.

**Who created it and who funded it?** The benchmark and the accompanying library (Misata) were
created by the project author (see the repository `LICENSE`). No external funding is recorded
in the repository.

## Composition

**What do the instances represent?** An instance is a *task*: a frozen specification (schema,
foreign-key graph, per-table scale, and zero or more analytical targets) together with an
oracle (the declared targets themselves, which are the ground truth). Tasks come in two modes.
Spec-mode tasks are cold-start: only a specification is given. Reference-mode tasks additionally
supply a real or synthetic source table from which the specification is derived, so that learned
baselines have something to train on.

**How many instances are there?** The released task suite registered in
`research/specbench/tasks.py` contains 8 core tasks spanning cold-start curve tasks (SaaS,
fintech, ecommerce), an integrity-only task, two relational reference-mode tasks (a 2-table and
a 3-table hierarchy), a controlled synthetic-ramp reference task, and one real public dataset
task (California Housing). The natural-language suite (`research/specbench/nl_suite.py`) adds 18
single-sentence curve tasks, one per domain, used to measure the natural-language path across
breadth. The design space described in the paper (18 domains crossed with flat, curve,
multi-table, and locale-shifted configurations) is larger than the currently implemented set;
library coverage and benchmark coverage are stated separately and should not be conflated.

**What data does each instance contain?** Specifications and oracles are declared in code
(typed Python structures). Generated tables are produced at run time and are not stored as part
of the benchmark. Result tables (CSV) record, per task and baseline and seed, the computed
metrics. Columns include: `AME` (aggregate-match error), `FIVR` (foreign-key violation rate),
`DET` (determinism), `CSC` (cold-start capability), `CSAT` (constraint satisfaction),
`input_type` (`nl` / `schema` / `data`), wall-clock seconds, and the random seed.

**Is any information missing?** Some baseline runs are intentionally recorded as not run with a
stated reason rather than a fabricated score: SDV cannot run cold-start tasks (no source data),
and NeMo Data Designer requires a hosted NVIDIA service behind an API key and was not run in the
isolated environment. These are marked explicitly.

**Does the benchmark contain personal or sensitive data?** No personal data is collected or
stored. Spec-mode tasks use zero source data by construction. The single real dataset used in
reference mode is California Housing (block-group housing aggregates) obtained from
scikit-learn; it contains no individual-level personal records. SpecBench therefore raises no
direct privacy concern; privacy of the reference engine is argued by construction (it never
reads a real record on cold-start tasks).

## Collection process

**How was the data associated with each instance acquired?** Specifications and oracles were
authored by hand and are versioned in the repository. The one real dataset (California Housing)
is fetched programmatically from scikit-learn at run time; its monthly targets are derived by a
fixed, documented mapping (`month = 1 + (HouseAge mod 12)`), which induces a real per-month
aggregate of real house values that serves as the oracle.

**Over what time frame was the data collected?** The benchmark and result tables were produced
during the development of the accompanying paper. Each result table is regenerated from a single
command, so the data are reproducible rather than collected once.

## Preprocessing, cleaning, labeling

Oracles are the declared targets and require no labeling. No metric reads any generator's
internals; every metric is a pure function of the output tables and the specification. Result
tables are emitted directly by the runner and the per-experiment scripts. Library-version
sensitivity applies to the learned baselines (SDV and its copula/rdt stack), so versions are
pinned in `requirements-specbench.txt`; the engine's exact quantities (AME, FIVR, DET) do not
depend on that stack.

## Uses

**What tasks could the benchmark be used for?** Evaluating any generator that claims to produce
relational data conforming to declared analytical outcomes; comparing cold-start
specification-driven generators against imitation methods on the orthogonal conformance axis;
and studying the reliability of natural-language and LLM front-ends for specification-to-data
pipelines.

**What should users be aware of?** AME = 0 and FIVR = 0 are achievable by construction for a
generator built to satisfy the spec and to generate in foreign-key topological order, so they
are not, on their own, evidence of a strong method; their value is in the comparison (imitation
methods miss the aggregate badly) and in the joint achievement with realistic marginals,
determinism, and cold-start operation. The suite deliberately includes a task the reference
method fails (P-star: exact aggregate plus an arbitrary external marginal), so the benchmark can
be failed.

**Are there tasks for which it should not be used?** SpecBench should not be used to claim
fidelity-to-real superiority; it does not measure fidelity except as secondary context, and it
concedes that axis to imitation methods.

## Distribution and licensing

The benchmark ships with the Misata repository under the MIT License (see `LICENSE`). It is
distributed as source: task definitions, metric implementations, baseline adapters, runner and
per-experiment scripts under `research/specbench/`, and the produced result tables (CSV). The
external dependency for reference mode (scikit-learn's California Housing) carries its own
license.

## Maintenance

The benchmark is maintained in the project repository. Result tables regenerate from the listed
commands (see the paper's reproducibility appendix and `research/specbench/`). Extensions
(additional domains, configurations, and baselines) are intended to be added through the same
task and baseline interfaces. Errata to the bibliography and any numeric corrections are tracked
in the adversarial-review logs (`research/06`–`11`) and the paper's retraction notes.
