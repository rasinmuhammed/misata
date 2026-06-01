# The Exact-Aggregate Engine: Correct Mathematical Identity, Honest Lineage

**Status:** brick 1, rewritten after literature reconnaissance (see `02_literature_and_verdict.md`).
**Purpose:** state *exactly* what `misata/engines/fact_engine.py` does, in the correct
mathematical language, with full citation of the fields that own each idea. Every
proposition is checked numerically by `research/measure.py`.

> **Posture.** Nothing here is claimed as novel. The value of this document is
> *correctness and lineage-awareness*: describing the engine the way someone who
> knows official statistics, compositional data analysis, and constrained sampling
> would describe it. That is the anti-slop signal. Where a genuine open seam may
> exist, it is flagged as *open*, not claimed as solved.

---

## 1. What the engine computes

Given, for a metric column `Y` over `P` time periods: targets `T_1,…,T_P ≥ 0`, a
mean transaction value `μ`, a concentration `α`, row bounds `[r_min,r_max]`, and
decimal precision `d` (`m=10^d`). For each period `p` independently it returns a row
count `n_p` and nonnegative values `v_{p,1..n_p}` on the `1/m` grid with
`Σ_i v_{p,i} = round(T_p,d)` exactly.

- **Stage 1, counts:** `n_p = clip(round(T_p/μ), r_min, r_max)` (then capped by
  `⌊T_p m⌋`).
- **Stage 2, values:** `w ~ Dirichlet(α·1_{n_p})`, scale by `U_p = round(T_p m)`,
  then **largest-remainder (Hamilton) apportionment** to make the integer units sum
  to `U_p` exactly; divide by `m`.

---

## 2. The correct identity: this is conditional-sum sampling of a Gamma population

The engine is **not** an ad-hoc rescale. It is the *exact* solution to a classical
problem for one specific family.

**Fact (Lukacs 1955 characterization; standard).** If
`X_1,…,X_n ~ iid Gamma(α, θ)`, then the normalized vector
`(X_1,…,X_n)/Σ_j X_j ~ Dirichlet(α,…,α)` and is **independent** of the sum `Σ_j X_j`.

**Proposition 0 (what Stage 2 really is).** Drawing `w ~ Dirichlet(α·1_n)` and
setting `v_i = T·w_i` produces a sample distributed *exactly* as
`(X_1,…,X_n) | Σ_j X_j = T` for `X_j ~ iid Gamma(α,θ)` — i.e. **exact sampling from
a Gamma population conditioned on a fixed total.**

*Proof.* By the Fact, conditioning iid Gammas on their sum yields a Dirichlet
composition scaled by that sum, with no residual dependence on `θ`. The construction
reproduces this law verbatim; controlled rounding (§3) projects onto the `1/m` grid
without changing the sum. ∎

This is the right frame and it is *clarifying*, not deflating:

- The marginal realism we observe is not luck. Conditioning a Gamma population on its
  total is genuinely realistic — heavier-tailed than Gaussian, strictly positive,
  unimodal — and the engine samples it *exactly and in closed form*.
- It immediately tells us the method's reach: **exactness for free holds precisely
  for the Gamma/exponential/χ² family.** For other target marginals, the
  corresponding conditional-sum sampling is generally *not* closed-form (§6, open).

---

## 3. Aggregate exactness (controlled rounding)

**Proposition 1 (Exactness).** For every `p`, `Σ_i v_{p,i} = U_p/m = round(T_p,d)`
deterministically, for any draw and any `n_p ≥ 1`.

*Proof.* `Σ_i w_i = 1 ⇒ Σ_i T̃_i = U_p` with `T̃_i = w_i U_p`. The residual
`R = U_p − Σ_i⌊T̃_i⌋ = Σ_i frac(T̃_i) ∈ {0,…,n_p−1}`. Largest-remainder adds one unit
to the `R` largest fractional parts (well defined as `R < n_p`), giving `Σ_i u_i=U_p`.
Divide by `m`. ∎

**Lineage.** Integer apportionment to a fixed total under proportional weights is the
**Hamilton/largest-remainder method** (apportionment theory, 1792) and, in tabular
form, **controlled rounding / controlled tabular adjustment** in statistical
disclosure control (Cox 1987; Willenborg & de Waal 2001). The exactness is a known
guarantee of that family; we use it, we do not claim it.

**Corollary 1.1.** Error vs the rounded curve is 0 per period; vs the unrounded curve
≤ `1/(2m)` (half a cent), independent of `n_p,α`, and the shape.

---

## 4. Marginal law in closed form (compositional data analysis)

**Proposition 2.** Ignoring the `O(1/U_p)` rounding term, with `w~Dirichlet(α1_n)`
each `w_i ~ Beta(α,(n−1)α)`, so `v_i = T w_i`:

$$
\mathbb E[v_i]=\frac{T}{n},\qquad
\mathrm{CV}(v_i)=\sqrt{\frac{n-1}{\,n\alpha+1\,}}\xrightarrow[n\to\infty]{}\frac1{\sqrt\alpha}.
$$

*Proof.* Symmetric-Dirichlet marginals are Beta with these parameters; substitute
into mean and CV. ∎

**Lineage.** Dirichlet/Beta marginals on the simplex are textbook **compositional
data analysis** (Aitchison 1986); `Dirichlet` as the max-entropy law on the simplex
for fixed log-moments is standard. `α` as a closed-form CV knob is a property of that
family, not an invention.

---

## 5. Distortion under saturation (the precise, honest failure mode)

**Proposition 3.** Let `ρ_p = E[v_{p,i}]/μ = T_p/(n_p μ)`. With
`n_p = clip(round(T_p/μ),r_min,r_max)`:

$$
\rho_p=\begin{cases}
1+O(\mu/T_p) & r_{\min}\le T_p/\mu\le r_{\max}\\
T_p/(r_{\max}\mu)>1 & T_p/\mu>r_{\max}\\
T_p/(r_{\min}\mu)<1 & T_p/\mu<r_{\min}
\end{cases}
$$

*Proof.* Three branches of `clip` in `ρ_p=T_p/(n_pμ)`; unsaturated branch uses
`round(x)=x(1+O(1/x))`. ∎

**Reading.** The curve is carried by **row counts**, not by inflating values; per-row
marginals are undistorted **iff** `T_p/μ ∈ [r_min,r_max]`. Outside, distortion is the
**closed-form clamp ratio**, giving an exact recipe to guarantee `ρ_p≡1`
(`r_max ≥ max_p T_p/μ`, `r_min ≤ min_p T_p/μ`). Numerically confirmed to 0.00% in all
three regimes (`research/measure.py`).

---

## 6. What is genuinely open (the only place worth digging)

Proposition 0 localizes the boundary precisely. Exact, closed-form, training-free
conditional-sum sampling is **free for the Gamma family** (our engine) and **for the
Gaussian family** (affine projection onto the sum hyperplane — classical). The open
problem:

> **P★ (specified-marginal exact-aggregate sampling).** Given an arbitrary target
> marginal `F` (e.g. real lognormal/Pareto/empirical) and a total `T`, draw
> `n` values approximately `~ F` with `Σ = T` *exactly*, efficiently, with a
> *provable bound* on the divergence from `F` induced by the sum constraint.

For non-Gamma/Gaussian `F` there is no closed-form conditional; one needs exponential
tilting, sequential Monte Carlo, or MCMC, trading exactness against fidelity to `F`.
**Caveat (honest):** constrained / fixed-sum sampling is itself a studied area
(tilting, SMC with constraints). Before claiming P★ as a contribution we must verify
it is not already solved in that literature — see `02_literature_and_verdict.md`.
The plausibly-fresh angle is only the *wrapper*: P★ inside relational, temporal,
zero-data synthetic generation with a benchmark.

Secondary open items: **G2** distortion-minimizing count allocation when clamps must
bind (small integer program; our `clip` is the naive baseline); **G3** joint targets
across correlated metrics / across FK joins (current exactness is per-column,
per-period, independent).

---

## 7. One-line honest summary

The exact-aggregate engine is **exact Gamma-population conditional-sum sampling
(Dirichlet) + controlled rounding (Hamilton apportionment)**, with closed-form
marginal CV (compositional data analysis) and a closed-form clamp-distortion bound.
Every component is classical and correctly cited. The only candidate open seam is
P★ — exact-aggregate sampling for an *arbitrary specified* marginal — and even that
must survive a constrained-sampling literature check before any claim.
