# Outcome-Conformant Relational Synthesis: Exact Specification Satisfaction, Its Achievable Frontier, and a Conformance Benchmark

> **Draft status.** Publication-ready skeleton for a *data-management / benchmark*
> paper (target: VLDB/SIGMOD; secondary: NeurIPS Datasets & Benchmarks framed as a
> new evaluation paradigm; JOSS for the tool). This is **not** a novel-theory paper —
> every mechanism is attributed to its classical owner (§3). The contribution is
> (C1) a unifying formal characterization of *outcome-conformant* synthesis, including
> a precise achievable frontier; (C2) **SpecBench**, the first benchmark for
> *conformance* (not fidelity); (C3) a closed-form, deterministic reference system.
> Math → `01_formalization.md`; lineage → `02_*`/`05_literature_review.md`; scope lock
> → `00_moat_and_scope.md`; numbers → `research/measure.py` + `specbench/`.
>
> **Spine (do not lose this again).** The paper's backbone is the *mathematics*: the
> conditional-sum identity (Prop. 0) that makes outcome conformance exact and
> closed-form, and the condensation frontier (Prop. 5) that says exactly when it must
> trade against marginal fidelity. SpecBench is the *measurement arm* of these
> propositions — every metric operationalizes a specific claim (§4.1). The axis is
> **conformance, not fidelity**; we concede fidelity-to-real to imitation methods.
>
> **Author note.** Rewrite in the author's own voice before submission. `[CITE: ...]`
> markers resolve to entries in `05_literature_review.md`.

---

## Abstract

Synthetic tabular data research is dominated by the *imitation* paradigm: learn a
real distribution and sample from it, judged on *fidelity to real data*. A large
class of practical needs — software testing, database seeding, demos, teaching,
query-engine stress — is structurally outside this paradigm: there is no source data
("cold start"), and success means *reproducing a declared analytical outcome* (a
revenue curve, a churn rate, a group-wise distribution) across a relational schema,
not resembling some real dataset. We call this **outcome-conformant relational
synthesis** and argue its evaluation axis is **conformance**, not fidelity. Our
contributions are threefold. **(C1) A formal characterization.** We show that a
widely-used family of exact-aggregate generators is, precisely, *exact sampling from
a Gamma population conditioned on a fixed total* (via Lukacs' proportion–sum
independence `[CITE: Lukacs 1955]`), giving closed-form aggregate exactness
(controlled rounding `[CITE: Cox 1987]`), a closed-form marginal coefficient of
variation, and an *exact* distortion bound under resource limits. We then establish
the **achievable frontier**: using condensation theory for conditioned sums
`[CITE: Armendáriz–Loulakis 2011; Szavits-Nossan et al. 2014]`, exact-aggregate
conformance preserves an arbitrary target marginal *only* in the light-tailed (fluid)
regime; for heavy-tailed targets under tight totals a condensate forms (single big
jump) and fidelity loss is unavoidable — a known impossibility, not an open problem.
**(C2) SpecBench**, the first benchmark for conformance: it scores generators on
aggregate-match error, rate/group-distribution conformance, controllability response,
FK-integrity, temporal coherence, and determinism — axes that fidelity benchmarks
(SDGym/SDMetrics) cannot express because they presuppose real data. Each metric
operationalizes a proposition from C1. **(C3) A reference implementation** that maps a
natural-language or declarative specification to a relational dataset with exact,
deterministic, closed-form conformance and zero source data. We show imitation methods
(SDV, CTGAN, RelDiff) cannot ingest outcome targets and score zero on cold-start
tasks, and that LLM-driven cold-start generators (NeMo Data Designer) approximate but
cannot *guarantee* conformance or determinism — while honestly conceding that
imitation methods lead on fidelity-to-real where real data exists.

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
valid foreign keys. We call this **outcome-conformant relational synthesis**: the
input is a *specification of analytical outcomes*; success is *conformance* to it.

### 1.2 Why imitation cannot serve it; why prior specification work is partial

The two paradigms answer different questions. Imitation requires source data
(violating cold-start), satisfies outcome targets only in expectation if at all (most
learned models cannot ingest "this sum/rate/share must equal X"), and is judged on
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

**C1 — Formal characterization with an achievable frontier (§2–§3).** We define
outcome-conformant synthesis and analyze its exactly-solvable core.
- **Identity (Prop. 0).** The exact-aggregate engine *is* exact sampling from a Gamma
  population conditioned on a fixed total (Lukacs proportion–sum independence
  `[CITE: Lukacs 1955]`) — not an ad-hoc rescale. This is the mathematical spine.
- **Exactness & marginal law (Props. 1–2).** Closed-form aggregate exactness via
  controlled rounding `[CITE: Cox 1987]`; closed-form marginal `CV = √((n−1)/(nα+1))`
  `[CITE: Aitchison 1986]`.
- **Distortion bound (Prop. 3).** Exact closed-form distortion under resource clamps.
- **Frontier (Prop. 5).** Via condensation theory `[CITE: Armendáriz–Loulakis 2011;
  Szavits-Nossan et al. 2014]`: exact conformance preserves an arbitrary target
  marginal *only* in the light-tailed fluid regime; heavy tails under tight totals
  force a condensate (single big jump) and unavoidable fidelity loss. This both
  *justifies* the Gamma design and *bounds* what any such method can achieve.

**C2 — SpecBench (§4): the first conformance benchmark.** Metrics for the regime —
aggregate-match error, rate- and group-distribution conformance, controllability
response, FK-integrity, temporal coherence, determinism — none expressible in
fidelity suites (SDGym/SDMetrics) that presuppose real data. Crucially, **each metric
operationalizes a proposition from C1** (mapping in §4.1), so the benchmark is the
measurement arm of the theory, not a detached scoreboard.

**C3 — Reference implementation (§5).** An open-source system mapping a
natural-language/declarative spec to a relational dataset with exact, deterministic,
closed-form conformance and guaranteed FK integrity, from zero source data — no
iterative fitting, no training, no LLM call at generation time.

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

### 4.1 SpecBench is the measurement arm of C1 (the weld)

Existing benchmarks (SDMetrics, SDGym `[CITE]`) score *fidelity to a reference
dataset* and therefore presuppose real data. The conformance regime has none and a
different success criterion. SpecBench is not a detached scoreboard: **every metric
operationalizes a proposition from §3.** This is the explicit link between the theory
(C1) and the evaluation (C2).

| Proposition (C1) | What it claims | SpecBench metric that measures it |
|---|---|---|
| Prop. 1 (exactness) | aggregate hits target exactly | **AME** → 0 for exact generators |
| Prop. 2 (marginal law) | per-row `CV=√((n−1)/(nα+1))` | marginal-plausibility check vs predicted CV |
| Prop. 3 (clamp distortion) | distortion = closed-form clamp ratio | conformance vs declared row-bounds |
| Prop. 5 (frontier) | fidelity preserved only in fluid regime | **MD trade-off curve** across tail-heaviness |
| §2 integrity desiderata | FK + temporal correctness | **FIVR**, **TCV** → 0 |
| determinism (system) | same seed ⇒ identical output | **DET** → 1 |
| controllability | tracks a changed spec | **CR** → 0 under target change |

The single most important plot in the paper is the **Prop. 5 MD trade-off curve**:
as the declared marginal grows heavier-tailed under a fixed aggregate, measured
marginal distortion rises, and the *onset* matches the condensation transition
predicted in §3. That figure turns the theory's frontier into an empirical,
falsifiable curve — the core scientific result, not a leaderboard cell.

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
- **MD** Marginal Distortion (normalized 1-Wasserstein) — used for the Prop. 5 curve
  and to *concede* fidelity to imitation methods, per the scope lock. TSTR,
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
the cross-paradigm SpecBench leaderboard and E6 the Prop. 5 frontier figure (both via
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

**E5 — Cross-paradigm conformance (SpecBench leaderboard).** Real runs; AME = relative
aggregate-match error against declared anchors, FIVR = FK-violation rate, DET =
determinism (same-seed bitwise identity), CSC = cold-start capability. SDV trained for
real (GaussianCopula and CTGAN, the latter 100 epochs).

*Spec-mode (cold-start) task — SaaS MRR curve:*

| Generator | CSC | AME | FIVR | DET |
|---|---|---|---|---|
| **Misata (ours)** | 1 | **0.000** | 0.000 | 1.000 |
| Faker + hand-wired FK | 1 | 0.735 | 0.000 | 1.000 |
| SDV GaussianCopula | 0 | — (cannot run: no source data) | | |
| SDV CTGAN | 0 | — (cannot run: no source data) | | |

*Reference-mode task — revenue curve, real source table supplied so learned methods
train on data whose monthly sums already match the targets:*

| Generator | CSC | AME | FIVR | DET | fit+sample (s) |
|---|---|---|---|---|---|
| **Misata (ours)** | 1 | **0.000** | 0.000 | 1.000 | 0.04 |
| SDV GaussianCopula | 0 | 0.213 | 0.000 | 1.000 | 0.80 |
| SDV CTGAN | 0 | 0.698 | 0.000 | **0.000** | 52.0 |
| Faker + hand-wired FK | 1 | 1.823 | 0.000 | 1.000 | 0.00 |

The reference-mode row is the paper's central empirical point: **even when an
imitation model is trained on data whose monthly totals already equal the targets, it
reproduces the point cloud, not the declared outcome** (AME 0.21–0.70), and the deep
model is **non-deterministic** (DET 0) — it cannot reproduce its own output under a
fixed seed. Conformance is a property of *taking the specification as input*, which
imitation structurally does not. We concede, as predicted, that learned methods lead
on fidelity-to-real context metrics (reported in the appendix, not as a success axis).

**E6 — The conformance/fidelity frontier (Prop. 5).** Holding the aggregate exact, we
sweep the *demanded* target marginal from light- to heavy-tailed (lognormal log-σ from
0.1 to 2.0) and measure marginal distortion MD (normalized 1-Wasserstein to an
unconstrained draw from the same target). Distortion rises monotonically from
**MD ≈ 0.058** (light tail, σ≤0.4: the *fluid* regime where the exact-sum constraint
is essentially free) to **MD ≈ 1.25** (heavy tail, σ≥1.6: the *condensation* regime) —
a **21.7×** increase with a visible knee near σ≈1.4, while the aggregate stays exact
(max sum-error 0.00 across the sweep). This is the empirical signature of the
condensation transition (§3.4): exact aggregate conformance and arbitrary
heavy-tailed marginal fidelity are jointly unachievable, and the boundary is the one
condensation theory predicts. *(Figure: MD vs σ; data in
`research/specbench/prop5_curve.csv`.)*

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
**(vi) The frontier** — condensation of conditioned sums
`[CITE: Armendáriz–Loulakis 2011; Szavits-Nossan et al. 2014]`; constrained sampling
`[CITE: Golchi–Campbell 2014]`. We unify the *specification* thread, supply the missing
*conformance* benchmark, and reuse — and cite — the rest.

---

## 8. Limitations

Exact aggregate satisfaction is per-column and per-period independent; *joint*
targets across correlated metrics or across FK joins are future work. Marginal
control is exact only in the fluid regime (Prop. 5). Domain priors are curated, not
learned, so realism outside the 18 domains relies on user specification. We do not
compete with learned methods on fidelity-to-real when real data exists.

## 9. Conclusion

Outcome-conformant relational synthesis is a real, practically important problem that
the imitation paradigm structurally cannot serve. We formalized it (Prop. 0 reveals
the exact-aggregate engine as conditional-sum sampling of a Gamma population), mapped
its achievable frontier honestly (the condensation impossibility, Prop. 5, confirmed
empirically as a 21.7× distortion rise in E6), built the first conformance benchmark
(SpecBench), and released a closed-form, zero-data, integrity-preserving reference
system that attains AME = 0 where learned methods — even trained on
target-consistent data — reach only 0.21–0.70 and may be non-deterministic. The
contribution is unification, measurement, and honesty — not a new theorem — and that
is precisely what the area needed.

---

## Appendix A — Reproducibility
- **E1–E4** (proposition validation): `research/measure.py` against the released
  engine; no extra dependencies.
- **E5** (cross-paradigm leaderboard): `python -m research.specbench.runner` in the
  isolated env (`requirements-specbench.txt`, SDV 1.37.0); writes
  `research/specbench/results_e5.csv`. Each baseline run twice per task for DET.
- **E6** (Prop. 5 frontier): `python -m research.specbench.prop5_curve`; writes
  `research/specbench/prop5_curve.csv`. Seeds and library versions pinned.
- All oracles are frozen in the task definitions (the spec *is* the ground truth);
  no metric reads any generator's internals.

## Appendix B — Proofs
Full proofs of Propositions 1–5 (Prop. 0 identity; 1 exactness; 2 marginal law;
3 distortion; 5 condensation frontier) in `research/01_formalization.md`.
