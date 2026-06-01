# Literature Reconnaissance & The Honest Verdict on a Paper

**Status:** brick 2. Purpose: map every field that already owns part of what Misata
does, and decide — without sycophancy — whether a research paper is defensible.

---

## 1. The map (who owns what)

| Idea in Misata | Real owner | Maturity | Overlap |
|---|---|---|---|
| Microdata summing exactly to period/temporal targets | **Temporal disaggregation** — Denton 1971, Chow–Lin 1971; `tempdisagg` | 50+ yrs | series→series; see §2 |
| Integer/decimal exact-sum apportionment | **Controlled rounding / CTA**, Hamilton apportionment (Cox 1987) | 40+ yrs / 1792 | direct — we use it |
| Dirichlet partition, CV knob | **Compositional data analysis** (Aitchison 1986) | 40 yrs | direct — we use it |
| Aggregate→microdata, max-entropy | **IPF** (Deming–Stephan 1940); **Private-PGM/MST/AIM** (NIST) | 1940→now | categorical, in-exp, needs data |
| Multi-way cardinality, maxent | [arXiv 2603.22558](https://arxiv.org/abs/2603.22558) (2026) | new | **confirmed disjoint**, §3 |
| Reverse-generate data from query outputs | **QAGen** (Binnig 2007), **Touchstone**, **Hydra**, **DataSynth** | 18 yrs | cardinalities, not measure-sums |
| Guaranteed per-row *logical* constraints | **JANUS** [2603.03748](https://arxiv.org/abs/2603.03748) (2026) | new | **cleared, disjoint**, §4 |
| Relational/FK deep synthesis | ClavaDDPM (NeurIPS'24), RelDiff, GraphCFM | 2024–25 | learned, needs data |
| Same summary stats, different data | Matejka–Fitzmaurice 2017 | 8 yrs | single-table viz |

---

## 2. Temporal disaggregation — the closest classical relative, and the one real distinction

Denton/Chow–Lin convert a **low-frequency series into a high-frequency series**
preserving the aggregate (one value per sub-period). Our engine instead emits a
**population of many transaction rows per period** whose *sum* hits the target and
whose *per-row marginal* is a controlled Gamma-conditional law. So: disaggregation is
**series → series**; ours is **aggregate → population of rows with distributional
realism**. That distinction is real but *small*, and almost certainly folklore once
combined with controlled rounding. Not a paper on its own.

---

## 3. Maxent multi-way cardinality (2603.22558) — CONFIRMED disjoint

Clean extraction, consistent across reads: **marginal-total constraints on
categorical contingency tables**, satisfied **in expectation**, via **iterative**
maxent (IPF-family), needing **real marginals**, **single-table**, **no temporal**.
Ours is **continuous**, **exact**, **closed-form**, **zero-data**, **temporal**,
**relational**. No overlap. (But it shares our intellectual neighborhood, which is
itself the warning: this space is actively worked in 2026.)

---

## 4. JANUS (2603.03748) — CLEARED via verbatim abstract: adjacent but disjoint

"JANUS: Joint Ancestral Network for Uncertainty and Synthesis" (2026). Verbatim
abstract obtained. What it actually is:

- **Constraints = inter-column *logical* relations** (e.g. `Salary_offered >=
  Salary_requested`), propagated backward through a **DAG of Bayesian Decision Trees**
  ("Reverse-Topological Back-filling"), **100% satisfaction on feasible sets without
  rejection sampling** — exact, but for *per-row logical* constraints.
- **Distribution-modeling, not zero-data:** explicitly competes with CTGAN/TabDDPM on
  *Fidelity to the original distribution*; it needs a distribution to model.
- **No continuous aggregate-sum-over-period targets.** That is our territory; JANUS
  does not address it.
- **Notable convergence:** their *Analytical Uncertainty Decomposition* is "derived
  from **Dirichlet priors**." We arrived at the Dirichlet independently as the *exact
  conditional-sum law* (Prop 0). Two 2026 works reaching for the same simplex object
  from opposite directions = strong evidence this is a live, real neighborhood, and
  that our specific corner (exact continuous aggregates, zero-data, temporal,
  relational) is unoccupied by them.

**Verdict: disjoint mechanism and disjoint problem.** No blocking overlap. JANUS is
the right *related work* to cite, not a competitor to our aggregate engine.

---

## 5. The verdict

**Theory paper: NO.** Every mathematical component is classical and correctly
attributable (Lukacs/Dirichlet conditioning, Hamilton apportionment, Aitchison,
Denton, IPF). Proposition 0 *reduces* our engine to a known special case. Writing it
as new theory would be the precise reputational self-harm we are avoiding.

**Systems/tool paper: CONDITIONAL, plausibly alive.** JANUS and 2603.22558 are both
**cleared as disjoint** (§3, §4) — the 2026 neighborhood is active but nobody occupies
*exact continuous aggregate targets, zero-data, temporal, relational*. Viability now
hinges on two things only: (a) build something measurably *better* than a documented
baseline — the natural candidate is **P★** (exact-aggregate sampling for an *arbitrary
specified* marginal, with a proven distortion bound) — and (b) prove it on an honest
benchmark vs SDV/CTGAN/temporal-disaggregation. Gate: confirm P★ is not already solved
in constrained/fixed-sum sampling (SMC, exponential tilting). Venue if it survives:
VLDB/SIGMOD tool track or NeurIPS D&B — never a main-track theory claim.

**Where the name actually comes from (unsentimental):** not a paper. From a tool that
is *provably correct, honestly documented with its real lineage, and the default
choice for zero-data relational test data* — a niche academia does not serve. The
rigor here (harness + correct citations) is what makes the tool credible; it is the
means, not the headline.

---

## 6. P★ gate — RESOLVED: closed as theory, but yields a real applied principle

Literature check done. P★ (exact-sum sampling for an arbitrary specified marginal) is
**not open as a theory contribution**:

- **Sampling machinery exists.** Exponential tilting (closed-form for the exponential
  family) and **Sequentially Constrained Monte Carlo** (Golchi & Campbell 2014/16,
  [1410.8209](https://arxiv.org/abs/1410.8209)) already sample from an arbitrary `F`
  under a hard sum constraint. The "how to sample" half is solved, generically.
- **Distortion is already characterized.** The statistical-physics literature on
  **condensation** of sums ([1812.02513](https://arxiv.org/pdf/1812.02513)) gives the
  exact behavior: conditioning *light-tailed* `F` (exponential/Gamma) on a sum is the
  "fluid phase" — the excess spreads evenly, marginal ≈ `F`. Conditioning
  *heavy-tailed* `F` (lognormal/Pareto) on a large sum enters a **condensation phase**
  — one summand absorbs the excess; the conditional marginal is provably NOT `F`. So a
  "provable low-distortion bound for arbitrary `F`" cannot exist for heavy tails — it
  is a known impossibility, not our discovery.

**The genuine applied insight (docs/blog, not a paper):** our engine's choice of the
Gamma-conditional (Dirichlet) law is *exactly the fluid-phase regime* — the unique
classical family where exact-sum conditioning leaves the marginal essentially
undistorted. That is *why* Proposition 2 holds and why empirical means stay flat. It
is a correct, citable engineering rationale (Lukacs + condensation theory), and a
good story — but it is assembling known results, not new theory.

## 7. Final verdict

- **Novel-theory paper: CLOSED.** Every door checked; each component is classical and
  P★ is impossible/solved. Pursuing it = the slop trap.
- **Benchmark / systems paper: OPEN and achievable.** No standardized benchmark
  exists for the *specification regime* — controllable, cold-start, relational
  synthesis measured jointly on aggregate-match error, FK integrity, marginal
  realism, and controllability (SDMetrics measures fidelity-to-real, a different
  axis). Building that benchmark + Misata as reference implementation is a real,
  landable contribution that needs rigor and honesty, not novel math. Venue:
  **NeurIPS Datasets & Benchmarks**, **VLDB tool/demo**, or **JOSS**.
- **The name comes from the adopted tool**, with the benchmark as its credibility
  anchor. Not from theory.
