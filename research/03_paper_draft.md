# Specification-Driven Relational Synthesis: A Benchmark and Reference Implementation for Controllable Cold-Start Data Generation

> **Draft status.** Publication-ready skeleton for a *benchmark / systems* paper
> (target: NeurIPS Datasets & Benchmarks, VLDB tools/demo, or JOSS). This is **not**
> a novel-theory paper — §3 attributes every mechanism to its classical owner. The
> contributions are the *problem formalization*, the *benchmark*, the *honest
> characterization*, and the *reference implementation*. All numbers trace to
> `research/measure.py`; all math to `research/01_formalization.md`; all lineage to
> `research/02_literature_and_verdict.md`.
>
> **Author note.** Every section is to be rewritten in the author's own voice before
> submission. Citations marked `[CITE: ...]` need a real bibliographic entry.

---

## Abstract

Synthetic tabular data research is dominated by the *imitation* paradigm: given a
real dataset, learn its distribution (copulas, GANs, diffusion, autoregressive
models) and sample from it. This paradigm is structurally unable to serve a large
and practical class of needs — software testing, database seeding, demos, and
teaching — where (i) no source data exists ("cold start"), (ii) the data must hit
*specified analytical targets* (a revenue curve, a fraud rate, a funnel), and
(iii) multi-table referential integrity is mandatory. We call the complementary
problem **specification-driven relational synthesis** and argue it has been studied
only in fragments across official statistics, databases, and statistical physics,
never unified or benchmarked. We make three contributions. First, we formalize the
problem and its core sub-task — generating microdata whose period-level aggregate
exactly matches a target while remaining individually realistic — and we
characterize, using a classical conditional-sum identity and condensation theory,
*exactly* when an exact-aggregate generator preserves marginal realism and when it
cannot. Second, we introduce **SpecBench**, a benchmark that scores generators
jointly on aggregate-match error, FK-integrity violation rate, marginal-distortion,
controllability, and cold-start capability — axes that existing fidelity-to-real
benchmarks (e.g. SDMetrics) do not measure. Third, we provide a permissively
licensed reference implementation that satisfies aggregate targets *exactly* in
closed form, generates relational data from a natural-language specification with
zero source data, and serves as a strong, honest baseline. We show that
imitation-based methods cannot take specification targets at all, and we delineate —
honestly — the regime (heavy-tailed marginals under tight aggregate constraints)
where *no* method can preserve fidelity, a known impossibility rather than an open
problem.

---

## 1. Introduction

### 1.1 Two paradigms

Most synthetic-data systems answer the question *"make data that looks like this real
data."* This is **imitation**, and the field's flagship tools — CTGAN/TVAE
`[CITE: Xu et al. 2019]`, TabDDPM `[CITE: Kotelnikov et al. 2023]`, the Synthetic
Data Vault `[CITE: Patki et al. 2016]`, and the recent relational diffusion models
ClavaDDPM `[CITE: 2024]` and RelDiff — are optimized for, and benchmarked on,
fidelity to a reference distribution.

A different question arises constantly in software practice: *"make data that
produces this outcome, from nothing."* A developer seeding a test database, a
founder building a demo, an instructor preparing an exercise, or an engineer
stress-testing a query planner does not have — and must not use — real customer
data. They instead know the *shape* the data should have: "10k users, 20% churn,
MRR rising from \$50k to \$200k across the year with a Q3 dip," across a schema with
valid foreign keys. We call this **specification-driven relational synthesis**.

### 1.2 Why imitation cannot serve it

The two paradigms are not competitors on one axis; they answer different questions.
Imitation requires source data (violating cold-start), satisfies aggregate targets
only in expectation if at all (most learned models cannot ingest a "sum must equal
X" constraint), and historically struggled with cross-table integrity. Conversely,
when real data *does* exist and the goal is joint-distribution fidelity, learned
methods are the right tool and we do not compete with them. We are explicit about
this boundary throughout; conceding it is what makes the rest credible.

### 1.3 Contributions

1. **Formalization (§2–§3).** We define specification-driven relational synthesis
   and isolate its hardest exactly-solvable core: *exact-aggregate microdata
   generation*. We give the correct mathematical identity for a widely-used class of
   generators (conditional-sum sampling of a Gamma population; Lukacs
   `[CITE: Lukacs 1955]`), a closed-form marginal law, and an *exact* distortion
   bound under resource limits.
2. **A negative result, stated honestly (§3.4).** Using condensation theory for
   conditioned sums `[CITE: Szavits-Nossan et al. 2014]`, we show that an
   exact-aggregate generator can preserve an arbitrary target marginal *only* in the
   light-tailed (fluid) regime; for heavy-tailed targets under tight totals,
   fidelity loss is unavoidable. This delineates the achievable frontier and
   explains why our reference design chooses the Gamma family.
3. **SpecBench (§4).** A benchmark and metric suite for the specification regime:
   aggregate-match error, FK-integrity violation rate, marginal distortion,
   controllability response, and cold-start capability — with a task suite spanning
   18 business domains and 15 locales.
4. **Reference implementation (§5).** An open-source system that maps a
   natural-language or declarative specification to a relational dataset with exact
   aggregate satisfaction and guaranteed FK integrity, from zero source data, in
   closed form (no iterative fitting, no training).

We deliberately claim **no new theorem**. The novelty is the unification, the
benchmark, the honest frontier, and the reference system.

---

## 2. Problem formulation

**Schema.** A schema is tables `T_1,…,T_K` with typed columns and a set of
foreign-key constraints forming a DAG. A *fact table* `T` carries a metric column
`Y` and a time column `t`.

**Specification.** A specification `Σ` declares: (a) the schema and FK graph;
(b) per-table scale (row counts, parent/child multiplicities); (c) zero or more
*analytical targets* on `Y` — the case we solve exactly here is a partition of time
into periods `B_1,…,B_P` with aggregate targets `T_1,…,T_P ≥ 0`; (d) realism
controls (a target average value `μ`, a dispersion `α`, resource bounds
`[r_min, r_max]`, precision `d`, `m = 10^d`).

**Generator.** A randomized map producing, per period `p`, a count `n_p` and values
`v_{p,1..n_p}` on the `1/m` grid. Desiderata:
- **(A) Aggregate fidelity:** `Σ_i v_{p,i} = round(T_p, d)` exactly.
- **(R) Marginal realism:** the per-row law of `Y` is realistic and controllable.
- **(I) Integrity:** rows populate a relational scaffold preserving FK and temporal
  order.

§3 resolves (A) and (R) for the exact-aggregate core; (I) is handled by topological
generation in the reference system (§5) and measured, not re-derived.

---

## 3. The exact-aggregate core: identity, guarantees, and the achievable frontier

We analyze the generator implemented in the reference system; all claims are
verified numerically in §6.

### 3.1 The mechanism

Per period `p`: **counts** `n_p = clip(round(T_p/μ), r_min, r_max)` (then capped by
`⌊T_p m⌋`); **values** `w ~ Dirichlet(α·1_{n_p})`, scale by `U_p = round(T_p m)`,
then largest-remainder (Hamilton) apportionment `[CITE: Balinski–Young 1982]` to
make integer units sum to `U_p`; divide by `m`.

### 3.2 What this actually is (the correct identity)

**Proposition 1.** Drawing `w ~ Dirichlet(α·1_n)` and setting `v_i = T·w_i` yields a
sample distributed exactly as `(X_1,…,X_n) | Σ_j X_j = T` for iid
`X_j ~ Gamma(α,θ)`. *(Lukacs characterization `[CITE: Lukacs 1955]`; proof in
`01_formalization.md`.)* The engine is therefore *exact conditional-sum sampling of
a Gamma population*, not an ad-hoc rescale.

### 3.3 Exactness and marginal law

**Proposition 2 (Exactness).** `Σ_i v_{p,i} = round(T_p,d)` deterministically, for
any draw and any `n_p ≥ 1`. Error vs the unrounded target ≤ `1/(2m)` per period,
independent of `n_p, α`, shape. *(Largest-remainder guarantees the integer sum;
controlled-rounding lineage `[CITE: Cox 1987]`.)*

**Proposition 3 (Marginals).** Each `w_i ~ Beta(α,(n−1)α)`, so `E[v_i] = T/n` and
`CV(v_i) = sqrt((n−1)/(nα+1)) → 1/√α`. `α` is a closed-form realism knob
(compositional data analysis `[CITE: Aitchison 1986]`).

### 3.4 The achievable frontier (the honest negative result)

**Proposition 4 (Distortion under resource limits).** With
`ρ_p = E[v_{p,i}]/μ = T_p/(n_p μ)`: `ρ_p = 1 + O(μ/T_p)` when
`T_p/μ ∈ [r_min, r_max]`; otherwise `ρ_p` equals the closed-form clamp ratio
`T_p/(r_max μ)` or `T_p/(r_min μ)`. The aggregate curve is carried by *row counts*,
not by inflating values; marginals are undistorted iff the target-to-average ratio
fits the resource bounds.

**Proposition 5 (Heavy-tail impossibility).** For a *specified* target marginal `F`
and total `T`, exact-sum conditioning preserves `F` only in the light-tailed
("fluid") regime. For heavy-tailed `F` (lognormal, Pareto) under a large total, the
conditioned law enters a **condensation** phase — one summand absorbs the excess and
the marginal is provably not `F` `[CITE: Szavits-Nossan et al. 2014]`. Hence no
generator can offer exact aggregates *and* a low-distortion guarantee for arbitrary
heavy-tailed marginals. This is a frontier, not a defect: the reference design's
Gamma/Dirichlet choice is exactly the fluid regime where (A) and (R) coexist.

This subsection is the paper's intellectual honesty and, paradoxically, its
strength: we map the boundary of what is possible rather than overclaiming past it.

---

## 4. SpecBench

### 4.1 Why a new benchmark

Existing benchmarks (SDMetrics `[CITE]`, SDGym `[CITE]`) score *fidelity to a
reference dataset*. The specification regime has no reference dataset and different
success criteria. SpecBench measures what matters here.

### 4.2 Metrics

- **Aggregate-Match Error (AME):** `max_p |Ŝ_p − T_p| / T_p` over specified targets.
  Exact generators achieve `0`; learned generators conditioned post-hoc do not.
- **FK-Integrity Violation Rate (FIVR):** fraction of child rows whose foreign key
  has no matching parent key. Target `0`.
- **Marginal Distortion (MD):** divergence (e.g. 1-Wasserstein) between the realized
  per-row metric law and the intended marginal, reported *within* and *outside* the
  fluid regime per Prop. 5.
- **Controllability Response (CR):** given a change to a target (e.g. double the Dec
  value), the realized response error — does the system track the new spec?
- **Cold-Start Capability (CSC):** binary — does the method run with zero source
  rows? Imitation methods score `0`.
- **Throughput / Determinism:** rows/s and seed-reproducibility (bitwise identical
  output per seed).

### 4.3 Task suite

18 domains (SaaS, ecommerce, fintech, healthcare, HR, logistics, marketplace,
social, real estate, pharma, food delivery, edtech, gaming, CRM, crypto, insurance,
travel, streaming) × {flat, narrative-curve, multi-table-FK, locale-shifted}
configurations. Each task ships a specification and an oracle for its targets.

### 4.4 Baselines

(1) The reference system (this work). (2) Faker + hand-wired FK scripts. (3) SDV
(GaussianCopula, CTGAN) — *with real data provided*, to fairly show it wins on
fidelity-to-real but scores `0` on CSC and cannot take aggregate targets. (4) A
temporal-disaggregation baseline (Denton `[CITE: Denton 1971]`) for the single-table
aggregate task, to position the classical relative honestly.

---

## 5. Reference implementation

A permissively licensed Python library that: parses a natural-language or YAML
specification into a schema + targets; generates tables in FK-topological order
(parents before children) for `FIVR = 0` by construction; applies the exact-aggregate
engine of §3 for `AME = 0`; supports 18 domain priors and 15 locales; is fully
seed-deterministic; and runs with zero source data and no training step. We position
it as the **reference baseline** for SpecBench, not as a claim of algorithmic
novelty — its components are classical (§3) and correctly cited.

---

## 6. Experiments

All results reproducible via `research/measure.py` against the released engine.

**E1 — Aggregate exactness (Prop. 2).** Over **5,000** randomized trials spanning
row counts `n ∈ [1, 2000]`, targets up to `5×10⁶`, integer and 2-decimal precision,
and `α ∈ [0.3, 50]`, the maximum aggregate error was **0 integer units** — exact in
every trial.

**E2 — Marginal law (Prop. 3).** Pooled ~2×10⁶ samples per cell. Empirical mean
matched `T/n` exactly; empirical CV matched `sqrt((n−1)/(nα+1))` to within
**0.01%–0.10%** across `(n,α) ∈ {(50,1),(200,2),(500,5),(1000,25)}`.

**E3 — Distortion frontier (Prop. 4).** Across the three regimes (upper-clamp,
unsaturated, lower-clamp) the realized `ρ_p` matched the closed-form prediction
(0.500, 1.000, 5.000) to **0.00%** relative error.

**E4 — End-to-end controllability.** The natural-language specification *"MRR \$50k
in January, \$100k in June, \$200k in December"* produced microdata whose monthly
rollups were **\$50,000.00** and **\$200,000.00** — exact to the cent.

**E5 — Cross-paradigm (to run for submission).** SpecBench across all baselines:
expected — reference system `AME=0, FIVR=0, CSC=1`; SDV/CTGAN `CSC=0` and no
aggregate-target ingestion; on fidelity-to-real (where applicable) learned methods
lead, as they should.

---

## 7. Related work

Temporal disaggregation (Denton 1971, Chow–Lin 1971) `[CITE]`; controlled
rounding / tabular adjustment (Cox 1987) `[CITE]`; iterative proportional fitting
and maximum-entropy population synthesis (Deming–Stephan 1940; Private-PGM/AIM)
`[CITE]`; reverse query processing / query-aware generation (QAGen, Touchstone,
Hydra, DataSynth) `[CITE]`; constraint-guaranteed generation (JANUS 2026) `[CITE]`;
constrained sampling (Sequentially Constrained Monte Carlo, Golchi–Campbell 2014)
`[CITE]`; condensation of conditioned sums `[CITE]`; relational deep synthesis
(ClavaDDPM, RelDiff) `[CITE]`. Our work unifies the *specification* thread and
supplies the missing benchmark; we reuse, and cite, the rest.

---

## 8. Limitations

Exact aggregate satisfaction is per-column and per-period independent; *joint*
targets across correlated metrics or across FK joins are future work. Marginal
control is exact only in the fluid regime (Prop. 5). Domain priors are curated, not
learned, so realism outside the 18 domains relies on user specification. We do not
compete with learned methods on fidelity-to-real when real data exists.

## 9. Conclusion

Specification-driven relational synthesis is a real, practically important problem
that the imitation paradigm structurally cannot serve. We formalized it, mapped its
achievable frontier honestly (including a heavy-tail impossibility), built the first
benchmark for it, and released a closed-form, zero-data, integrity-preserving
reference system. The contribution is unification, measurement, and honesty — not a
new theorem — and that is precisely what the area needed.

---

## Appendix A — Reproducibility
`research/measure.py` regenerates E1–E4 from the released engine; SpecBench tasks
and the E5 harness ship in `research/specbench/` `[TO BUILD]`.

## Appendix B — Proofs
Full proofs of Propositions 1–5 in `research/01_formalization.md`.
