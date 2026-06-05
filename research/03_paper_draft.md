# Declarative Outcome-Conformant Synthesis: Exact, Closed-Form Specification Satisfaction and a Conformance Benchmark

<!-- SCOPE NOTE (review B6/R4): re-scoped declarative-first. The contribution is the
closed-form exact-conformance engine + the conformance benchmark. Natural-language
input is a *bounded convenience layer over curated domains*, NOT a general capability:
on an arbitrary non-curated schema (D8, California Housing) the NL path does not apply
and the engine is driven by an explicit declarative spec instead. Title and claims are
deliberately kept to what the evidence supports. -->


> **Draft status.** Publication-ready skeleton for a *data-management / benchmark*
> paper (target: VLDB/SIGMOD; secondary: NeurIPS Datasets & Benchmarks framed as a
> new evaluation paradigm; JOSS for the tool). This is **not** a novel-theory paper —
> every mechanism is attributed to its classical owner (§3). The contribution is
> (C1) correct attribution + analysis of the exact-aggregate engine for *outcome-conformant* synthesis, including
> a precise achievable frontier; (C2) **SpecBench**, the first benchmark for
> *conformance* (not fidelity); (C3) a closed-form, deterministic reference system.
> Math → `01_formalization.md`; lineage → `02_*`/`05_literature_review.md`; scope lock
> → `00_moat_and_scope.md`; numbers → `research/measure.py` + `specbench/`.
>
> **Spine.** The paper's backbone is the *mathematics*: the conditional-sum identity
> (Prop. 0) that makes outcome conformance exact and closed-form, and scale-invariance
> (Prop. 4) showing the engine preserves the marginal by fixing shape and letting scale
> absorb the constraint — which is *why* it sidesteps the condensation obstruction that
> bounds the fixed-marginal problem. SpecBench is the *measurement arm* — every metric
> operationalizes a specific claim (§4.1). The axis is **conformance, not fidelity**; we
> concede fidelity-to-real to imitation methods, and we concede that exact aggregation
> *alone* is trivial (a rescale ties it given a hand-built schema) — the contribution is
> exact conformance from a **declarative spec**, zero data, with closed-form marginals
> and integrity preserved (NL input is a bounded convenience over curated domains).
>
> **Author note.** Rewrite in the author's own voice before submission. `[CITE: ...]`
> markers resolve to entries in `05_literature_review.md`.

---

## Abstract

We study a capability the dominant paradigm in synthetic tabular data does not provide:
**exact** satisfaction of a declared analytical outcome with no source data. Imitation
methods — copulas, GANs, diffusion, the Synthetic Data Vault — learn a real distribution
and sample from it; they are judged on *fidelity to real data*. A large, practical class
of needs is different: generating data with **no source data** ("cold start") that
*reproduces a declared outcome* (a revenue curve, a churn rate, a group-wise
distribution) across a relational schema. Off-the-shelf imitation tools provide no
interface for such targets; and — the structural point — **no sampler can hit an exact
aggregate**, because sampling has variance. We make this precise: on a real public
dataset, off-the-shelf learned synthesizers trained *on that very data* miss the declared
monthly aggregate by **74–87%**; the strongest steelman (a GaussianCopula trained
*per period*, the fix a reviewer would demand) cuts the miss to **~19%** but still cannot
reach **0** — exactness is unattainable by sampling. A closed-form generator attains
**exactly 0** (to the half-cent, deterministically). We name this task
**outcome-conformant synthesis**, argue its evaluation axis is **conformance** (does the
output *exactly* obey the specification?) rather than **fidelity** (does it resemble real
data?), and show the two axes are orthogonal. Our
contributions are threefold. **(C1) A formal characterization.** We show that a
widely-used family of exact-aggregate generators is, precisely, *exact sampling from
a Gamma population conditioned on a fixed total* (via Lukacs' proportion–sum
independence `[CITE: Lukacs 1955]`), giving closed-form aggregate exactness
(controlled rounding `[CITE: Cox 1987]`), a closed-form marginal coefficient of
variation, and an *exact* distortion bound under resource limits. We further prove a
**scale-invariance** property: the engine fixes the per-row *shape* (a Gamma family at
fixed concentration) and lets the *scale* absorb the aggregate constraint, so the
marginal is preserved regardless of the target — empirically, the distortion vs an
unconstrained control is ≈ 0 across all tail weights. We connect this to condensation
theory for conditioned sums `[CITE: Armendáriz–Loulakis 2011; Szavits-Nossan et al.
2014]`: condensation (single-big-jump marginal collapse) is the obstruction for the
*fixed-external-marginal* exact-aggregate problem (which we do **not** claim to solve),
and scale-invariance is precisely how our shape-fixing engine *sidesteps* it.
**(C2) SpecBench**, the first benchmark for conformance: it scores generators on
aggregate-match error, rate/group-distribution conformance, controllability response,
FK-integrity, temporal coherence, and determinism — axes that fidelity benchmarks
(SDGym/SDMetrics) cannot express because they presuppose real data. Each metric
operationalizes a proposition from C1. **(C3) A reference implementation** that maps a
**declarative** specification (schema + outcome targets) to a relational dataset with
exact, deterministic, closed-form conformance and zero source data; a natural-language
front-end provides the same over a curated set of domains. We show imitation methods
(SDV, CTGAN, RelDiff) provide no off-the-shelf interface for outcome targets and score zero on cold-start tasks; even per-period conditioning (§6) approximates but never hits them exactly.
**Scope, stated up front:** exact *aggregate* satisfaction alone is trivial (a rescale
script ties it given a hand-built schema); our contribution is exact conformance
*jointly* with closed-form per-row marginals, FK/temporal integrity, determinism, and
zero source data — and a benchmark that measures these together. The natural-language
capability is **bounded to curated domains**: on an arbitrary real schema the engine is
driven by an explicit declarative spec, not parsed from a sentence (Section 6, D8). We
concede imitation methods lead on fidelity-to-real where real data exists.

---

## 1. Introduction

### 1.1 Two orthogonal axes: fidelity vs exact conformance

Synthetic tabular data is evaluated along what the literature treats as a single quality
axis but is really **two orthogonal axes**:

| | **Data available** | **Cold start (no source data)** |
|---|---|---|
| **Fidelity** (resemble real data) | imitation: SDV, CTGAN, TabDDPM, RelDiff — the field's focus | n/a (no reference to resemble) |
| **Exact conformance** (obey a declared outcome to 0 error) | only approximable by conditioning (sampling variance ⇒ AME>0) | **the task of this paper** (closed-form, AME=0) |

Most systems answer *"make data that looks like this real data"* — **imitation**, the
flagship tools `[CITE: Xu et al. 2019; Kotelnikov et al. 2023; Patki et al. 2016]` and
recent relational diffusion (ClavaDDPM `[CITE: 2024]`, RelDiff), all optimized for and
benchmarked on *fidelity*. But a different question arises constantly in software
practice: *"make data that produces this outcome, from nothing."* A developer seeding a
test database, a founder building a demo, an instructor preparing an exercise, or an
engineer stress-testing a query planner has no real data — and must not use it — yet
knows the *shape* the data must have: "10k users, 20% churn, MRR rising from \$50k to
\$200k with a Q3 dip," over a schema with valid foreign keys. This is the bottom-right
cell: **outcome-conformant synthesis** — input is a *specification of analytical
outcomes*; success is *exact conformance*. Imitation struggles here on two counts:
off-the-shelf tools provide no interface to accept a target (cold-start = 0 capability),
and — even when *conditioned* per period (the obvious fix) — a sampler cannot produce an
*exact* aggregate, only an approximation with variance. §6 shows this concretely:
off-the-shelf learned methods miss real-data outcomes by 74–87%; a per-period-conditioned
steelman still misses by ~19% and never reaches 0; closed-form generation reaches exactly
0. The structural statement is about *exactness*, not about whether imitation can be
coaxed to approximate.

### 1.2 Why imitation cannot serve it; why prior specification work is partial

The two paradigms answer different questions. Imitation requires source data
(violating cold-start), satisfies outcome targets only in expectation if at all (most
off-the-shelf learned models provide no interface for "this sum/rate/share must equal X", and even conditioned they approximate rather than hit it exactly), and are judged on
fidelity. When real data exists and fidelity is the goal, imitation is the right tool
and we do not compete; conceding this is what makes the rest credible.

The *specification* tradition is real but partial. In databases, **QAGen**
`[CITE: Binnig et al. 2007]` and **DataSynth** `[CITE: Arasu et al. 2011]` generate
data to satisfy declared **query-output cardinalities** for optimizer testing — not
analytical outcomes (curves, rates, distributions) on metric columns, and not from
natural language. In official statistics, **temporal disaggregation**
`[CITE: Denton 1971]` and **IPF** `[CITE: Deming–Stephan 1940]` produce
aggregate-consistent *series* or *contingency tables* — not relational populations
with per-row realism. LLM cold-start tools (**NeMo Data Designer**, 2025) target
outcomes but *approximate* them stochastically with no exactness or determinism. The
specific intersection — exact, deterministic, closed-form conformance to analytical
outcomes, relational, from natural language, zero data — is unoccupied (§7).

### 1.3 Contributions

**C1 — Correct attribution and analysis of the exact-aggregate engine (§2–§3).** We do
not claim new theorems; the value is *clarity and honesty* — naming exactly what a
widely-used generation mechanism is, in classical terms, and identifying the one
non-obvious consequence (condensation explains why the shape-fixing design choice is what
makes exactness free). We define outcome-conformant synthesis and analyze its
exactly-solvable core.
- **Identity (Prop. 0).** The exact-aggregate engine *is* exact sampling from a Gamma
  population conditioned on a fixed total (Lukacs proportion–sum independence
  `[CITE: Lukacs 1955]`) — not an ad-hoc rescale. This is the mathematical spine.
- **Exactness & marginal law (Props. 1–2).** Closed-form aggregate exactness via
  controlled rounding `[CITE: Cox 1987]`; closed-form marginal `CV = √((n−1)/(nα+1))`
  `[CITE: Aitchison 1986]`.
- **Distortion bound (Prop. 3).** Exact closed-form distortion under resource clamps.
- **Scale-invariance, and why condensation is avoided (Prop. 4).** The engine fixes the
  per-row *shape* and lets the *scale* meet the target, so the marginal is invariant to
  the demanded aggregate (verified: distortion vs an unconstrained control ≈ 0 across
  tail weights, E6). Condensation theory `[CITE: Armendáriz–Loulakis 2011;
  Szavits-Nossan et al. 2014]` says single-big-jump collapse is the obstruction for the
  *fixed-external-marginal* exact-aggregate problem; Prop. 4 shows our shape-fixing
  design sidesteps that obstruction by construction. We do **not** claim to solve the
  fixed-marginal problem (that remains open, §6, P★) — we delimit where it bites.

**C2 — SpecBench (§4): the first conformance benchmark.** Metrics for the regime —
aggregate-match error, rate- and group-distribution conformance, controllability
response, FK-integrity, temporal coherence, determinism — none expressible in
fidelity suites (SDGym/SDMetrics) that presuppose real data. Crucially, **each metric
operationalizes a proposition from C1** (mapping in §4.1), so the benchmark is the
measurement arm of the theory, not a detached scoreboard.

**C3 — Reference implementation (§5).** An open-source system mapping a **declarative
spec** (schema + outcome targets) to a relational dataset with exact, deterministic,
closed-form conformance and guaranteed FK integrity, from zero source data — no
iterative fitting, no training, no LLM call at generation time. A natural-language
front-end offers the same over a curated domain set; we bound that claim explicitly
(§6, D8) — on non-curated schemas the system is driven declaratively, not from a
sentence.

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

**The key insight.** Generating values that hit an exact total while staying realistic
*looks* like a hard constrained-sampling problem — and for an *arbitrary fixed marginal*
it genuinely is, blocked by a condensation impossibility (§3.4). Our engine sidesteps
this entirely by a single design choice: **parameterize the per-row *shape*, not the
marginal, and let the *scale* absorb the constraint.** Under that choice the hard problem
collapses to an exact, closed-form, training-free draw (Prop. 0) — and the impossibility
that blocks the obvious formulation simply does not apply (Prop. 4). The rest of this
section makes that precise. We analyze the generator in the reference system; all claims
are verified numerically in §6.

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

### 3.4 Distortion under resource limits, scale-invariance, and the boundary

**Proposition 3b (Distortion under resource limits).** With
`ρ_p = E[v_{p,i}]/μ = T_p/(n_p μ)`: `ρ_p = 1 + O(μ/T_p)` when
`T_p/μ ∈ [r_min, r_max]`; otherwise `ρ_p` equals the closed-form clamp ratio
`T_p/(r_max μ)` or `T_p/(r_min μ)`. The aggregate curve is carried by *row counts*,
not by inflating values; marginals are undistorted iff the target-to-average ratio
fits the resource bounds.

**Proposition 4 (Scale-invariance).** Fix concentration `α`. For totals `T, T'`, the
engine's output for `T'` equals `(T'/T)·` its output for `T` in distribution (up to the
`O(1/U)` rounding term): the *normalized* law `v_i/\bar v` is independent of the target.
The target sets the scale; the shape is invariant. *(Proof: Stage-2 `w∼Dirichlet(α𝟙)`
is independent of `T`; `v_i(T')=T'w_i=(T'/T)v_i(T)`.)*

**Where condensation does — and does not — apply (the honest boundary).** Condensation
theory `[CITE: Armendáriz–Loulakis 2011; Szavits-Nossan et al. 2014]` shows that
conditioning a sum of variables with a *fixed marginal* `F` on a large-deviation total
forces a single-big-jump collapse: the conditional marginal is provably not `F` for
heavy-tailed `F`. This is the obstruction for the **fixed-external-marginal**
exact-aggregate problem (P★, §6) — which we do **not** claim to solve. Our engine
**avoids** the obstruction rather than defeating it: by Prop. 4 it holds the *shape*
fixed and lets the *scale* absorb the constraint, so there is no fixed `F` to collapse.
E6 confirms this empirically — with the proper unconstrained control, the marginal
distortion gap is ≈ 0 across all tail weights.

> **Retraction (intellectual-honesty note).** An earlier draft asserted a "heavy-tail
> impossibility frontier" *for our engine* and reported a 21.7× distortion rise with
> tail-heaviness. Adding the unconstrained control revealed that rise to be a
> Beta-vs-lognormal family-mismatch plus finite-sample 1-Wasserstein bias — an artifact,
> not a constraint effect. The corrected result (Prop. 4 + E6) is that the engine's
> marginal is *invariant* to the target. We keep this note because mapping the boundary
> honestly — and catching our own confound — is part of the contribution.

---

## 4. SpecBench

### 4.1 SpecBench is the measurement arm of C1 (the weld)

Existing benchmarks (SDMetrics, SDGym `[CITE]`) score *fidelity to a reference
dataset* and therefore presuppose real data. The conformance regime has none and a
different success criterion. SpecBench is not a detached scoreboard: **every metric
operationalizes a proposition from §3.** This is the explicit link between the theory
(C1) and the evaluation (C2).

| Proposition (C1) | What it claims | SpecBench metric that measures it |
|---|---|---|
| Prop. 1 (exactness) | aggregate hits target exactly | **AME** → 0 for exact generators |
| Prop. 2 (marginal law) | per-row `CV=√((n−1)/(nα+1))` | CV check vs predicted (E2: ≤0.1%) |
| Prop. 3 (clamp distortion) | distortion = closed-form clamp ratio | ρ vs declared row-bounds (E3) |
| Prop. 4 (scale-invariance) | marginal preserved; condensation avoided | **MD vs unconstrained control** ≈ 0 (E6) |
| §2 integrity desiderata | FK + temporal correctness | **FIVR**, **TCV** → 0 |
| determinism (system) | same seed ⇒ identical output | **DET** → 1 |
| capability (input) | conformant data from an NL spec, zero data | **input axis** (nl vs schema vs data) |
| controllability | tracks a changed spec | **CR** → 0 under target change |

The key figure (E6) is the **Prop. 4 scale-invariance plot**: across tail-heaviness,
the engine's constrained marginal coincides with an *unconstrained* same-family control
(distortion gap ≈ 0) while the aggregate stays exact. It turns the theory into a
falsifiable curve and — crucially — includes the control that distinguishes a genuine
effect from the family-mismatch artifact an uncontrolled version would show (see the
retraction note in §6/E6). That methodological care is itself part of the contribution.

### 4.2 Metrics (grouped by family; see `00_moat_and_scope.md`)

**Core — Family A (outcome conformance):**
- **AME** Aggregate-Match Error: `max_p |Ŝ_p − T_p| / |T_p|`. Exact generators → 0.
- **RCE** Rate-Conformance Error: `|declared − realized|` for fraction targets
  (churn %, fraud %).
- **GDC** Group-Distribution Conformance: total-variation distance between declared
  and realized group shares.
- **CR** Controllability Response: AME/RCE against a *changed* spec after regen.
- **CSAT** Constraint Satisfaction: fraction of declared hard constraints met.

**Core — Family B (integrity & reproducibility):**
- **FIVR** FK-Integrity Violation Rate (child-weighted dangling FKs) → 0.
- **TCV** Temporal Coherence Violations (declared order breaks) → 0.
- **DET** Determinism (bitwise identical under fixed seed) → 1.

**Capability gate:**
- **CSC** Cold-Start Capability: binary — runs with zero source rows? Imitation → 0.
- **Throughput / peak memory** (SDGym convention `[CITE]`).

**Secondary context only (reference-mode tasks; never headline):**
- **MD** Marginal Distortion (normalized 1-Wasserstein) — used for the Prop. 4
  scale-invariance experiment (E6, vs an unconstrained control) and to *concede*
  fidelity to imitation methods, per the scope lock. TSTR,
  detection-as-goal, and DCR-as-privacy are deliberately excluded (§ rationale in
  `00_moat_and_scope.md`); privacy is argued by construction (zero real data).

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

E1–E4 validate the propositions of §3 (reproducible via `research/measure.py`); E5 is
the cross-paradigm SpecBench leaderboard and E6 the Prop. 4 scale-invariance figure (both via
`research/specbench/`, isolated env `requirements-specbench.txt`, SDV 1.37.0).

**E1 — Aggregate exactness (Prop. 1).** Over **5,000** randomized trials spanning
row counts `n ∈ [1, 2000]`, targets up to `5×10⁶`, integer and 2-decimal precision,
and `α ∈ [0.3, 50]`, the maximum aggregate error was **0 integer units** — exact in
every trial.

**E2 — Marginal law (Prop. 2).** Pooled ~2×10⁶ samples per cell. Empirical mean
matched `T/n` exactly; empirical CV matched `√((n−1)/(nα+1))` to within
**0.01%–0.10%** across `(n,α) ∈ {(50,1),(200,2),(500,5),(1000,25)}`.

**E3 — Distortion bound (Prop. 3).** Across the three regimes (upper-clamp,
unsaturated, lower-clamp) the realized `ρ_p` matched the closed-form prediction
(0.500, 1.000, 5.000) to **0.00%** relative error.

**E4 — End-to-end controllability.** The natural-language specification *"MRR \$50k
in January … \$200k in December"* produced microdata whose monthly rollups were
**\$50,000.00** and **\$200,000.00** — exact to the cent.

**E5 — Cross-paradigm conformance (SpecBench leaderboard).** Real runs, **10 seeds,
mean ± std**. AME = relative aggregate-match error against declared anchors; FIVR =
FK-violation rate; DET = determinism over ≥3 same-seed regenerations; CSC = cold-start
capability; **input** = what the generator consumes (`nl` = natural-language spec;
`schema` = a hand-built schema enumerating columns/FKs/periods; `data` = a real source
table). SDV is properly seeded (torch+numpy); CTGAN 100 epochs.

*Spec-mode (cold-start) tasks — three curated domains (SaaS non-monotone, fintech,
ecommerce). Misata's NL front-end applies here (`input=nl`):*

| Generator | input | CSC | AME | FIVR | DET |
|---|---|---|---|---|---|
| **Misata (ours)** | **nl** | 1 | **0 (≤1/2m)** | 0 | 1 |
| NaiveRescale (Faker + per-period ×T/Σ) | schema | 1 | 1.5e-16 | 0 | 1 |
| Faker (independent draws) | schema | 1 | 0.82–0.90 | 0 | 1 |
| SDV (GC / CTGAN / HMA) | data | 0 | — *(cannot run: no source data)* | — | — |

**Honest reading.** Hitting the aggregate exactly is *trivial*: NaiveRescale also
reaches AME ≈ 0. The distinction E5 makes visible is the **input axis** — NaiveRescale
and Faker reach the table only because *a human hand-built their schema, columns, FKs,
and period structure*; on these curated domains the engine produces the same conformant
relational dataset from a natural-language sentence with zero source data. The
contribution on spec-mode is not AME = 0 (conceded trivial) but AME = 0 with closed-form
realistic marginals and FK/temporal integrity, and — on curated domains — from an NL
spec (the only `input=nl` row). Imitation methods (SDV) cannot run cold-start (CSC = 0).
**Scope:** the `input=nl` advantage is bounded to the curated domains; on an arbitrary
real schema the engine runs declaratively (`input=schema`), shown next.

*Reference-mode, PRIMARY result — a **real public dataset** (California Housing, 20,640
records; metric = real `MedHouseVal`, monthly targets = the data's own per-month sums).
Learned methods train on the real table; the engine receives only the targets (`input=
schema`, since "housing" is outside the curated domains — the honest D8 finding):*

| Generator | input | CSC | AME (3 seeds) | FIVR | DET | fit+sample (s) |
|---|---|---|---|---|---|---|
| **Misata (ours)** | schema | 1 | **0** (exact) | 0 | 1 | ~0.1 |
| NaiveRescale | schema | 1 | **0** (exact) | 0 | 1 | ~0.1 |
| Faker | schema | 1 | 0.493 | 0 | 1 | 0.0 |
| SDV GaussianCopula (off-the-shelf) | data | 0 | 0.739 (det.) | 0 | 1 | ~1 |
| SDV HMA | data | 0 | 0.739 (det.) | 0 | 1 | ~2 |
| SDV CTGAN | data | 0 | 0.857 ± 0.354 | 0 | 1 | 77/seed |
| **SDV GaussianCopula, per-period conditioned** (steelman) | data | 0 | **0.189** | 0 | 1 | ~2 |

The last row is the key fairness control (review F1): we *give imitation the best shot* by
training a separate GaussianCopula per declared period — the obvious way to make it
"target" the aggregate. It improves dramatically (0.739 → 0.189) but **cannot reach 0**:
per-period sums still vary by 0.1–0.8% even on the best months, because sampling has
variance. Closed-form generation reaches exactly 0. *Exactness is the structural divide.*

**Reading (primary) — exactness, not "we beat SDV."** Three honest points. (1) *Fairness:*
off-the-shelf SDV has no API for aggregate targets; the conditioned steelman shows that
*even when we engineer imitation to target*, it lands at AME≈0.19, not 0. The divide is
**exact vs in-expectation**, which is structural to sampling, not a tuning artifact.
(2) *On the metric's validity (review F2):* the monthly targets here have CV≈0.30
(one bin is ~2× the others; the `HouseAge mod 12` binning is ~uncorrelated with value,
r=−0.03), so the targets are *not* near-uniform — the miss is a genuine failure to match
real per-bin structure, verified per-month (e.g. month 05 target 7103 vs SDV 3810), not
an artifact of a degenerate target. (3) Any generator that ingests the target exactly
(Misata declarative, or NaiveRescale) attains AME=0. The point is the orthogonality
of the two axes (§1.1), demonstrated on real data — not a performance ranking on a shared
objective. **Honest caveat (review M11):** on this non-curated schema the engine has no
domain prior, so it hits the aggregate exactly but its *per-row marginal* is a supplied
default — here Misata and NaiveRescale are both "right aggregate, generic marginal," and
we claim *no* marginal-realism advantage over a rescale on non-curated data. The
defensible real-data claim is precisely the conformance capability gap vs imitation.

*Multi-table reference-mode (review M13) — real parent `customers` + child `orders`,
an outcome target on `orders.amount`, and a customer→order FK. Tests the relational
claim directly against SDV's relational synthesizer, HMA:*

Two relational depths are tested: a **2-table** parent→child (customers→orders) and a
**3-table** hierarchy (regions→stores→sales, two FK edges), each with an outcome target.

| Task | Generator | input | AME | FIVR | DET |
|---|---|---|---|---|---|
| 2-table | **Misata (ours)** | schema | **0** | **0** | 1 |
| 2-table | SDV HMA (relational) | data | 0.783 | **0** | 1 |
| 3-table | **Misata (ours)** | schema | **0** | **0** (2 edges) | 1 |
| 3-table | SDV HMA (relational) | data | 0.640 | **0** (2 edges) | 1 |

**Reading (the honest relational result).** HMA **preserves every FK by construction**
(FIVR = 0, including both edges of the 3-level hierarchy) — so referential integrity does
*not* separate the methods; both achieve it. The separation is **conformance**: HMA,
trained on the real child table, still misses the declared monthly aggregate by **64–78%**
because it has no mechanism to ingest an outcome target. The engine attains **AME = 0
*and* FIVR = 0 together** at both depths (via the declarative path — "retail"/"ecommerce"
schemas drive `input=schema`). The relational contribution is therefore *integrity
jointly with outcome conformance*, not a claim of superior integrity over a purpose-built
relational synthesizer (we tie there at 0).

*Reference-mode, controlled check — a synthetic source table with a clean ramp (10
seeds), to isolate behavior on a known-smooth curve:*

| Generator | input | CSC | AME (10 seeds) | DET | fit+sample (s) |
|---|---|---|---|---|---|
| **Misata (ours)** | schema | 1 | **0** | 1 | 0.04 |
| SDV GaussianCopula | data | 0 | 0.213 ± 0.000 | 1 | 0.82 |
| SDV HMA | data | 0 | 0.213 ± 0.000 | 1 | 1.54 |
| SDV CTGAN | data | 0 | 0.569 ± 0.436 | 1 | 48.8 |
| Faker | schema | 1 | 0.895 ± 0.005 | 1 | 0.00 |

CTGAN's **0.569 ± 0.436** confirms imitation conformance is *uncontrolled* (variance so
wide it sometimes nearly hits, sometimes badly misses — no targeting mechanism).
*Correction note:* an earlier single-seed draft reported CTGAN "non-deterministic
(DET 0)"; once SDV is properly seeded **all SDV synthesizers are deterministic (DET = 1)**
— that claim was a un-seeded-run artifact and is retracted. We concede learned methods
lead on fidelity-to-real where real data exists (a different objective).

**E6 — Exact aggregate costs ~no shape distortion (Prop. 4; condensation avoided).**
*Correction note:* an earlier draft claimed a "condensation frontier" (a 21.7× rise in
marginal distortion with tail-heaviness). With the proper **unconstrained control
added**, that rise proved to be a Beta-vs-lognormal family-mismatch and finite-sample
1-Wasserstein artifact, **not** a constraint effect; it is **retracted**. The corrected,
controlled experiment (10 seeds) holds the aggregate exact and compares the engine's
constrained sample to an unconstrained i.i.d. draw from the *same* family across
tail-heaviness CV ∈ [0.35, 2.9]. The two coincide — distortion **gap ≈ 0** throughout
(−0.012 light-tail to −0.051 heavy-tail; the constrained sample is, if anything,
slightly *closer* to the target) — while the aggregate stays exact (max sum-error 0).
This empirically confirms **Prop. 4**: the engine fixes the *shape* (Dirichlet/Gamma
at concentration α) and lets the *scale* absorb the constraint, so condensation — which
afflicts *fixed-marginal* conditional sampling — is **avoided by construction**, not
merely deferred. *(Figure: `research/specbench/scale_invariance.png`; data in
`scale_invariance_curve.csv` / `scale_invariance_summary.csv`.)*

**E7 — Conformance generalizes beyond temporal sums (rates and group shares).** Outcome
conformance is not limited to aggregate curves. We declare (i) a **churn rate** target
and (ii) a **plan-distribution** (group-share) target, and measure Rate-Conformance
Error (RCE = |declared − realized|) and Group-Distribution Conformance (GDC = total-
variation distance). The engine attains **RCE ≤ 0.008** across declared rates
{0.05, 0.10, 0.20, 0.35} and **GDC = 0.005** for a declared 0.60/0.30/0.10 split, versus
**RCE = 0.30** for an uncontrolled draw with no target channel. A natural-language
front-end bug previously mapped "20% churn" to ~55% churned; we fixed it so the NL path
now also yields the declared rate (0.10→0.101, 0.20→0.195, 0.35→0.343). This shows the
contribution is *outcome conformance* generally, not a single curve-fitting trick.
*(Demo: `research/specbench/demo_rate_group.py`.)*

**E8 — End-to-end usability (case study).** Intrinsic metrics aside, can a developer
*use* the output? From the one-line spec *"an ecommerce store with 2000 customers and
8000 orders, revenue \$50k in January rising to \$200k in December"* we generate, load
into a real **SQLite** database, and run the SQL a BI tool or test suite would run:
(a) a `LEFT JOIN` orphan check returns **0** dangling foreign keys; (b) the in-database
monthly revenue rollup returns **\$50,000 in January and \$200,000 in December** — the
declared outcome holds *in SQL*, not just in the generator; (c) a `WHERE amount <= 0`
assertion returns **0** rows. One sentence to a queryable, outcome-correct test database.
*(Script: `research/specbench/case_study.py`.)*

**E9 — Throughput and the absence of an infeasible regime.** *(a) Cost:* closed-form
generation is training-free and scales near-linearly — 0.06 s (1k rows) to 0.34 s (50k
rows) — versus SDV GaussianCopula's fit+sample at 0.56–2.40 s, a **7–11× speedup** on a
comparable single-table workload (and off-the-shelf SDV has no target interface). *(b)
Robustness:* the aggregate-conformance problem has **no infeasible regime** — by Prop. 1
the exact sum is achievable for any row count `n ≥ 1`; pushing targets to extremes (a
\$1M month over 10 rows, or a \$0.02 month over 10 rows) still yields the exact sum, the
latter simply leaving some rows at 0. There is no silent-miss failure mode to detect,
because there is no miss. *(Scripts: `throughput.py`; verified edge cases in text.)*

**E10 — A task the reference method does NOT ace (so the benchmark can be failed).**
A benchmark its author always wins is worthless. We include **P★**: hit an exact monthly
sum *and* match a **specified external heavy-tailed marginal** (a Pareto target). The
engine hits the sum exactly (err 5e-4) but **fails the marginal-match axis**
(normalized 1-Wasserstein = 0.78) — because by Prop. 4 it fixes a Gamma-family shape and
*cannot* reproduce an arbitrary external marginal. This is the P★ / condensation regime
(§3.4): exact aggregate + arbitrary fixed marginal is the open, condensation-bounded
problem we explicitly do **not** solve. SpecBench reports this as a Misata **failure**,
which is the point — the suite contains tasks the proposing method loses, and the
boundary of the contribution is measured, not hidden.

---

## 7. Related work

Full annotated bibliography in `research/05_literature_review.md`; we summarize the
six threads that bound our contribution. **(i) Imitation / learned synthesis** — SDV
`[CITE: Patki 2016]`, CTGAN `[CITE: Xu 2019]`, TabDDPM `[CITE: Kotelnikov 2023]`, and
relational deep models RelDiff `[CITE: 2025]`, IRG `[CITE: SIGKDD 2026]`, HCTGAN
`[CITE: 2024]` learn `P(D)` from real data and are judged on fidelity; we are
orthogonal (conformance, cold-start). **(ii) Query-aware DB test-data** — QAGen
`[CITE: Binnig 2007]`, DataSynth `[CITE: Arasu 2011]`, projection-compliant generation
`[CITE: PVLDB 2022]`, XData `[CITE: 2015]` target *query-output cardinalities*, not
analytical outcomes, and not from natural language. **(iii) LLM cold-start** — NeMo
Data Designer `[CITE: NVIDIA 2025]` approximates outcomes stochastically without
exactness or determinism. **(iv) Aggregate-consistent official statistics** — temporal
disaggregation (Denton `[CITE: 1971]`, Chow–Lin `[CITE: 1971]`), IPF
`[CITE: Deming–Stephan 1940]`, population synthesis — series/contingency tables, not
relational populations. **(v) The exact mathematics** — Lukacs proportion–sum
independence `[CITE: 1955]`, compositional data analysis `[CITE: Aitchison 1986]`,
controlled rounding `[CITE: Cox 1987]`, apportionment `[CITE: Balinski–Young 1982]`.
**(vi) The boundary** — condensation of conditioned sums
`[CITE: Armendáriz–Loulakis 2011; Szavits-Nossan et al. 2014]` (the obstruction for the
fixed-marginal problem our engine sidesteps); constrained sampling
`[CITE: Golchi–Campbell 2014]`. We unify the *specification* thread, supply the missing
*conformance* benchmark, and reuse — and cite — the rest.

---

## 8. Limitations

Exact aggregate satisfaction is per-column and per-period independent; *joint* targets
across correlated metrics or across FK joins are future work. The engine fixes a
Gamma-family shape (Prop. 4); hitting an *arbitrary externally specified* marginal under
an exact aggregate (P★, §6) is open and condensation-bounded. On cold-start spec-mode,
exact aggregation *alone* is trivial — a rescale ties it given a hand-built schema; the
contribution there is conformance from an NL spec with zero data. Domain priors are
curated, not learned, so realism outside the curated domains relies on user
specification. Reference-mode currently uses controlled synthetic source data; a real
public dataset is the priority external-validity addition. We do not compete with
learned methods on fidelity-to-real when real data exists.

## 9. Conclusion

Outcome-conformant relational synthesis is a real, practically important problem that
the imitation paradigm does not serve — off-the-shelf it cannot take the target, and no
sampler can hit an aggregate *exactly*. We analyzed it (Prop. 0 reveals the
exact-aggregate engine as conditional-sum sampling of a Gamma population; Prop. 4 shows
it preserves the marginal by fixing shape and letting scale absorb the constraint,
sidestepping the condensation obstruction that bounds the fixed-marginal problem), built
the first conformance benchmark (SpecBench), and released a closed-form, zero-data,
integrity-preserving reference system. On reference-mode it attains AME = 0 from the spec
where learned methods — even trained on target-consistent data — reach only 0.21
(GaussianCopula/HMA) to 0.57 ± 0.44 (CTGAN, effectively uncontrolled). On cold-start
spec-mode it is the only method producing a conformant relational dataset from a natural
-language sentence with no source data and no hand-built schema. The contribution is
unification, measurement, and honesty — including the retraction of two claims that did
not survive proper controls — not a new theorem, and that is precisely what the area
needed.

---

## Appendix A — Reproducibility
- **E1–E4** (proposition validation): `research/measure.py` against the released
  engine; no extra dependencies.
- **E5** (cross-paradigm leaderboard): `python -m research.specbench.runner` in the
  isolated env (`requirements-specbench.txt`, SDV 1.37.0); writes
  `research/specbench/results_e5.csv`. 10 seeds; SDV seeded (torch+numpy); DET measured
  over ≥3 same-seed regenerations.
- **E6** (Prop. 4 scale-invariance, with control): `python -m research.specbench.scale_invariance`
  then `plot_scale_invariance`; writes `scale_invariance_curve.csv`, `scale_invariance_summary.csv`,
  `scale_invariance.png`. Seeds and library versions pinned.
- All oracles are frozen in the task definitions (the spec *is* the ground truth);
  no metric reads any generator's internals.

## Appendix B — Proofs
Full proofs in `research/01_formalization.md`: Prop. 0 (Gamma-conditional identity),
Prop. 1 (aggregate exactness), Prop. 2 (closed-form marginal CV), Prop. 3 (clamp
distortion), Prop. 4 (scale-invariance / condensation avoided). The retracted
"condensation frontier" conjecture and its confound are documented in
`06_adversarial_review.md` (B1) and the §3.4 retraction note.
