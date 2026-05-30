# Outcome-Driven Relational Synthesis: A Formalization

**Status:** working draft, brick 1 of the research program.
**Scope:** formalize the *exact-aggregate* generation mechanism implemented in
`misata/engines/fact_engine.py`, state precisely what it guarantees, and bound its
failure mode. Every claim below is grounded in the actual implementation
(`_allocate_row_counts`, `_generate_exact_values`, `generate`) and is empirically
checked by `research/measure.py`.

---

## 1. The problem

The dominant paradigm in synthetic tabular data is **imitation**: given a real
dataset `D`, learn `P(D)` (copulas, GANs, diffusion, autoregressive LLMs) and
sample. We study the **inverse / specification** problem:

> Given a desired *analytical outcome* and **no source data**, generate microdata
> that *provably reproduces that outcome* while remaining individually realistic and
> referentially consistent.

This document formalizes the first solved instance of that problem: a metric whose
**period-level aggregate** must follow a user-specified curve (e.g. "monthly revenue
rises \$50k → \$200k with a Q3 dip").

### 1.1 Relation to prior work (must be cited; we do not claim the category)

The general idea of "generate microdata consistent with given aggregates" is
established under other names, and a credible paper must engage them:

- **Population synthesis / spatial microsimulation** — synthesize individuals
  matching known marginal totals.
- **Iterative Proportional Fitting (IPF)** and **synthetic reconstruction** — the
  classical algorithms for matching contingency-table margins.
- **Apportionment theory** — the largest-remainder (Hamilton) method we use to keep
  integer sums exact is a 19th-century result.

Our contribution is **not** the bare concept. It is the specific, unclaimed
combination: *relational, multi-table transactional* microdata, specified by a
*business-narrative* curve, targeting a *BI-level analytical outcome*, with
*zero source data*, FK integrity, temporal coherence, and a closed-form realism
guarantee. §6 states the contribution precisely and honestly.

---

## 2. Notation and objects

A **schema** is a set of tables `T₁,…,T_K` with columns and a set of foreign-key
constraints `F` (a directed acyclic graph over tables). We focus on a single
**fact table** `T` carrying a **metric column** `Y` (e.g. `mrr`, `amount`) and a
**time column** `t`.

An **outcome curve** for `(T, Y, t)` is a partition of the time axis into
`P` consecutive **periods** (buckets) `B₁,…,B_P` with **targets**

$$
T_1,\dots,T_P \ \in\ \mathbb{R}_{\ge 0},
$$

where `T_p` is the required value of the aggregate of `Y` over the rows whose
timestamp falls in `B_p`. (Targets between user-specified anchors are produced by
interpolation upstream in the parser; here they are given.)

Two further user parameters shape the within-period microdata:

- `μ > 0` — a target **average transaction value** (`avg_transaction_value`);
- `α > 0` — a **concentration** parameter controlling per-row dispersion;
- `[r_min, r_max]` — bounds on the number of rows generated per period;
- `d ∈ ℕ` — decimal precision of `Y` (money: `d = 2`), with `m := 10^d`.

A **generator** `G` is a randomized map producing, for each period `p`, a row count
`n_p` and values `v_{p,1},…,v_{p,n_p} ∈ (1/m)·ℤ_{≥0}`. The realized period
aggregate is `Ŝ_p := Σ_i v_{p,i}`.

We require three things of `G`, formalized in §4–§5:

1. **(A) Aggregate fidelity:** `Ŝ_p = round(T_p, d)` exactly, for all `p`.
2. **(R) Marginal realism:** the per-row law of `Y` has mean ≈ `μ` and a
   controllable, well-characterized spread.
3. **(I) Integrity:** rows are emitted into a relational scaffold that preserves FK
   and temporal constraints (handled by the simulator around the engine; not
   re-derived here).

---

## 3. The mechanism (exactly as implemented)

For each period `p` independently:

**Stage 1 — row allocation** (`_allocate_row_counts`, absolute mode). With `μ` given,

$$
n_p \;=\; \operatorname{clip}\!\Big(\operatorname{round}(T_p/\mu),\; r_{\min},\; r_{\max}\Big),
\qquad\text{then } n_p \leftarrow \min\!\big(n_p,\ \lfloor T_p\, m\rfloor\big).
$$

The last cap (`_clip_to_target_units`) forbids more rows than indivisible currency
units; it is inactive whenever `T_p m ≥ n_p`, i.e. essentially always for nontrivial
targets.

**Stage 2 — exact value partition** (`_generate_exact_values`). Let
`U_p := round(T_p · m) ∈ ℤ_{≥0}` be the target in integer units. Draw a composition

$$
w \;\sim\; \mathrm{Dirichlet}(\alpha\mathbf{1}_{n_p}),
\qquad \tilde u_i = w_i\, U_p,
\qquad u_i = \lfloor \tilde u_i\rfloor,
$$

then apply **largest-remainder apportionment**: with residual
`R = U_p − Σ_i u_i`, add one unit to each of the `R` rows with the largest
fractional parts `tilde u_i − u_i`. (A final safety line forces
`Σ u_i = U_p` unconditionally.) Output `v_{p,i} = u_i / m`.

The optional `intra_period_pattern` rescales the Dirichlet concentration per row
(`weekday_heavy`, `start_heavy`, …) to shape *where within the period* the mass
lands; it does not affect the totals.

> **Relative mode (no `μ`).** When `μ` is absent, Stage 1 instead distributes a row
> budget `N` by `n_p = round( (T_p / Σ_q T_q)·N )`. Stage 2 is unchanged. We treat
> absolute mode as primary; the relative variant is analyzed in Remark 5.3.

---

## 4. Aggregate fidelity is exact and unconditional

**Proposition 1 (Exactness).** For every period `p`,
`Ŝ_p = Σ_{i=1}^{n_p} v_{p,i} = U_p/m = round(T_p, d)`, deterministically, for any
draw of `w` and any `n_p ≥ 1`.

*Proof.* The Dirichlet weights satisfy `Σ_i w_i = 1`, so `Σ_i \tilde u_i = U_p`,
an integer. Hence

$$
R \;=\; U_p - \textstyle\sum_i u_i \;=\; \sum_i (\tilde u_i - \lfloor \tilde u_i\rfloor)
\;=\; \sum_i \mathrm{frac}(\tilde u_i).
$$

Each `frac(·) ∈ [0,1)`, so `R ∈ [0, n_p)`, and because the left side is an integer,
`R ∈ {0,1,…,n_p−1}`. Largest-remainder adds exactly `R` units among distinct rows
(well-defined since `R < n_p`), giving `Σ_i u_i = U_p`. The safety line is therefore
a no-op but guarantees the identity even under floating-point pathologies. Dividing
by `m` gives `Ŝ_p = U_p/m`. ∎

**Corollary 1.1.** The total aggregate error against the *rounded* curve is zero in
every period; against the *unrounded* curve it is at most `1/(2m)` per period
(half a currency unit), independent of `n_p`, `α`, and the distribution shape.

This is the property the field's imitation methods structurally lack: a conditional
GAN/diffusion model conditioned on a target sum matches it only in expectation and
approximately. Here it is an identity.

---

## 5. Marginal realism: closed form, and an exact distortion bound

Exactness alone is trivial (any rescaling hits a sum). The substance is that the
**per-row law stays realistic** — and we can say exactly when it does and doesn't.

**Proposition 2 (Marginal law).** Ignore integer rounding (an `O(1/U_p)`
perturbation). Under `w ∼ Dirichlet(α𝟏_{n_p})`, each normalized weight is
`w_i ∼ Beta(α, (n_p−1)α)`, so the per-row value `v_{p,i} = U_p w_i / m` satisfies

$$
\mathbb{E}[v_{p,i}] = \frac{T_p}{n_p},
\qquad
\mathrm{CV}(v_{p,i}) \;=\; \sqrt{\frac{n_p-1}{\,n_p\alpha+1\,}}
\;\xrightarrow[n_p\to\infty]{}\; \frac{1}{\sqrt{\alpha}}.
$$

*Proof.* Marginals of a symmetric Dirichlet are Beta with the stated parameters;
`E[w_i] = 1/n_p` and `Var(w_i) = (n_p−1)/(n_p²(n_pα+1))`. Then
`E[v] = (U_p/m)E[w] = T_p/n_p` and
`CV² = Var(w)/E[w]² = (n_p−1)/(n_pα+1)`; take `n_p→∞`. ∎

**Interpretation.** `α` is a principled, closed-form realism knob: in the
large-period limit the per-row coefficient of variation is `1/√α`
(e.g. `α=1`⇒CV≈1, heavy spread; `α=25`⇒CV≈0.2, tight). This is *designed*
dispersion, not an artifact.

**Proposition 3 (Exact realism-distortion bound).** Define the **distortion**
`ρ_p := E[v_{p,i}] / μ = T_p/(n_p μ)`, the ratio of realized mean to intended
average. With `n_p = clip(round(T_p/μ), r_min, r_max)`:

$$
\rho_p =
\begin{cases}
1 + O\!\big(\mu/T_p\big), & r_{\min} \le T_p/\mu \le r_{\max}\ \text{(unsaturated)},\\[4pt]
\dfrac{T_p}{r_{\max}\,\mu} \;>\; 1, & T_p/\mu > r_{\max}\ \text{(lower-clamp saturated)},\\[6pt]
\dfrac{T_p}{r_{\min}\,\mu} \;<\; 1, & T_p/\mu < r_{\min}\ \text{(upper-clamp saturated)}.
\end{cases}
$$

*Proof.* Immediate from `ρ_p = T_p/(n_p μ)` and the three branches of `clip`. In the
unsaturated branch `n_p = round(T_p/μ) = (T_p/μ)(1+O(μ/T_p))`, so `ρ_p → 1`. ∎

**Reading of Proposition 3 (the honest failure mode).** Per-row marginals are
undistorted **iff** the target-to-average ratio lies within the row bounds. This is
exactly why, empirically, a 100× target swing left the per-row mean flat at ≈\$150
across all periods (the ratio never hit a clamp): **the curve is carried by row
*counts*, not by inflating values.** Distortion appears only at saturation, and then
its magnitude is the *closed-form clamp ratio* above — giving the user a precise
recipe (`set r_max ≥ max_p T_p/μ`, `r_min ≤ min_p T_p/μ`) to guarantee `ρ_p ≡ 1`.

**Remark 5.3 (Relative mode).** Without `μ`, `n_p ∝ T_p`, hence
`E[v_{p,i}] = T_p/n_p = (Σ_q T_q)/N`, **constant across periods**: the entire curve
shape is carried by density and the value marginal is homogeneous. Both modes
preserve realism; they differ in *what* is held fixed (per-row mean vs. row budget).

---

## 6. What is, and is not, the contribution

**Not novel (state plainly):** proportional partition to hit a sum is trivial;
largest-remainder apportionment is classical; matching aggregates with microdata is
the population-synthesis problem.

**The genuine kernel:**

1. **Problem framing** — *outcome-driven relational synthesis from zero data*: a
   metric's BI-level aggregate curve is satisfied *exactly* (Prop. 1) while the
   per-row law is realistic *with a closed-form CV* (Prop. 2), across a relational
   scaffold with FK/temporal integrity.
2. **A clean separation of concerns** — *counts carry shape, a Dirichlet carries
   spread* — yielding the **exact distortion characterization** of Prop. 3, i.e. a
   provable condition for zero realism loss. We have not found this stated for the
   relational, narrative-specified, zero-data regime.
3. **A measurement methodology** (`research/measure.py`, brick 2) that quantifies
   *outcome-match error* and *marginal distortion* and shows imitation baselines
   cannot take aggregate targets at all.

**Conceded, in writing:** when real data exists and the goal is fidelity to its
joint distribution, learned methods (CTGAN, diffusion) win. We address a different
objective; honesty about this boundary is the credibility of the paper.

---

## 7. Open problems (the deeper trench)

- **G1 — Generalize the target class.** From period aggregates to arbitrary
  analytical outcomes: cohort-retention curves, funnel conversion vectors, a target
  regression coefficient, a full correlation matrix. Each is an inverse problem;
  some are ill-posed (many or no solutions). Characterize solvability.
- **G2 — Joint multi-metric / cross-table targets.** Current exactness is
  per-column, per-period and independent across periods. Simultaneous targets on
  correlated metrics, or on aggregates that span FK joins, require a constrained
  *joint* solve. Formulate as optimization:
  minimize marginal distortion `Σ_p D(law_p ‖ realistic_p)` subject to exact
  aggregate + integer-row + FK constraints; relate the current heuristic to its
  optimum.
- **G3 — Distortion-minimizing allocation under hard row bounds.** When clamps must
  bind, choose `n_p` (and possibly redistribute across periods) to minimize total
  distortion subject to Σ constraints — a small integer program with, plausibly, a
  greedy optimum.
- **G4 — Statistical indistinguishability.** Beyond mean/CV, bound the divergence
  between the Dirichlet-partition law and a target marginal (e.g. lognormal) and
  state when they are indistinguishable at sample size `n_p`.

Brick 2 builds the measurement harness that turns Propositions 1–3 into reproducible
numbers and stress-tests the saturation boundary of Proposition 3.
