# SpecBench: Design & Methodology

**Status:** brick 3. The rigorous backbone that makes this a benchmark a reviewer
trusts. Grounded in the established evaluation literature so we neither reinvent
standard metrics nor miss the ones reviewers expect.

> **Posture.** A credible benchmark (i) reuses the field's accepted metrics where they
> apply, with correct citations; (ii) adds new metrics *only* for axes the regime
> needs that existing suites do not cover; (iii) is brutally honest about validity
> threats; (iv) is fully reproducible. We design to NeurIPS D&B / VLDB standards.

---

## 1. Design principles (from the D&B review criteria)

NeurIPS Datasets & Benchmarks holds submissions to **main-track rigor** and weights:
**accessibility** (open code/data, no gated access), **documentation** (how built,
biases, intended use), **reproducibility** (persistent hosting, machine-readable
metadata), and **impact** (challenges a dominant evaluation paradigm or surfaces an
underexplored problem). `[CITE: NeurIPS D&B CFP]`

SpecBench is designed to score on all four: it is open and pip-runnable; every task
ships a spec + oracle; results regenerate from one command; and it *explicitly
challenges the fidelity-to-real paradigm* by measuring axes that paradigm ignores.

---

## 2. The evaluation gap we fill — stated precisely

The standard tabular-synthesis stack — **SDGym** `[CITE]` over **SDMetrics** `[CITE]`
— evaluates **fidelity to a reference dataset**, **ML utility (TSTR)**, and
**privacy**. Every one of these *presupposes a real dataset exists*. They answer
"how close is synthetic to real?"

The specification regime has **no real dataset** and a different success criterion:
"does the data satisfy the declared targets with integrity, from nothing?" None of
AME, FIVR, or CR is expressible in SDGym, because there is no real reference to
compare against. That is the gap. We do **not** replace SDGym; we add the orthogonal
axes and *reuse* SDGym-style metrics wherever a reference happens to exist (§4).

---

## 3. Metric taxonomy

> **Scope lock (see `00_moat_and_scope.md`).** The evaluation axis is **CONFORMANCE,
> not FIDELITY.** Families A–B are the **core** of the paper — they measure how
> exactly a generator obeys a declared specification. Family C is **secondary
> context only**, reported on reference-mode tasks purely to demonstrate the honest
> trade-off (Prop. 5); it is never a headline axis. TSTR-as-success-axis,
> detection-AUC-as-success-axis, and DCR-as-privacy are **deliberately cut** — they
> would mis-file us in the imitation/fidelity paradigm we do not compete in.

### Family A — Specification / outcome conformance (NEW; the core contribution)

| Metric | Definition | Ideal |
|---|---|---|
| **AME** Aggregate-Match Error | `max_p |Ŝ_p − T_p| / |T_p|` over declared period targets | 0 |
| **RCE** Rate-Conformance Error | |declared rate − realized rate| for fraction targets (churn %, fraud %) | 0 |
| **GDC** Group-Distribution Conformance | total-variation distance between declared and realized group shares | 0 |
| **CR** Controllability Response | AME/RCE against a *changed* spec (e.g. ×2 a target), after regeneration | 0 |
| **CSAT** Constraint Satisfaction | fraction of declared hard constraints (ranges, inequalities) met | 1 |

Rationale: these measure whether the generator *obeys the specification* — the
defining question of cold-start specification-driven synthesis. Learned imitators
cannot ingest such targets at all (AME/RCE undefined or large; CR meaningless);
LLM-stochastic cold-start generators (NeMo Data Designer) can *approximate* but not
*exactly satisfy* them and are non-deterministic. That asymmetry is the paper's
central empirical point. AME/RCE/GDC generalize "outcome conformance" from temporal
aggregates to rates and group distributions — the analytical outcomes practitioners
actually specify.

### Family B — Structural & reproducibility integrity (NEW for this regime)

| Metric | Definition | Ideal |
|---|---|---|
| **FIVR** FK-Integrity Violation Rate | child-weighted fraction of dangling FKs | 0 |
| **TCV** Temporal Coherence Violations | fraction of rows breaking declared order (e.g. `shipped ≥ ordered`) | 0 |
| **DET** Determinism | bitwise-identical output under fixed seed | 1 |

Rationale: relational + temporal correctness is mandatory for test-data/seeding use
and is *not* a standard fidelity axis. DET matters for CI/test fixtures and is a
property both learned samplers and LLM-driven generators rarely guarantee — a clean,
categorical separation from every competitor.

### Family C — Marginal plausibility (SECONDARY CONTEXT ONLY; the honest trade)

Reported *only* on reference-mode tasks, and *only* to quantify the trade-off our own
theory predicts (Prop. 5: heavy-tail condensation). NOT a headline result; we
explicitly expect imitation methods to lead here and we concede it in the abstract.

| Metric | What | Source |
|---|---|---|
| **MD** Marginal Distortion | normalized 1-Wasserstein per metric column | `[CITE: Ramdas et al.]` |
| **Corr-Δ** Correlation difference | |corr_real − corr_syn| (pairwise) | SDMetrics `[CITE]` |

We report a single detection-style number at most, framed as context, never as a
success axis. (Cut entirely from the core: TSTR, detection-AUC-as-goal, DCR-privacy.)

We *expect and will report* that learned methods win here. Conceding this is the
credibility of the paper (cf. §3.4 / Prop. 5 of the formalization: heavy-tail
condensation makes exact-aggregate generators trade fidelity for control).

### Privacy — by construction, stated categorically (NOT a fidelity-style axis)

We do **not** adopt DCR as a privacy metric. The "DCR Delusion" result
`[CITE: Ganev et al. 2025]` shows DCR-private data can still leak under membership
inference, so DCR claims would be a *liability*, not a strength. For cold-start
specification-driven generation our privacy argument is **categorical**: no real
record is ever read, so there is nothing to leak. We state this as a property and,
if a reviewer wants empirical backing, verify a membership-inference attack returns
chance-level (AUC ≈ 0.5). Knowing *not* to lean on DCR is itself the
literature-awareness that signals depth.

We also deliberately **do not centre TSTR** (train-synthetic-test-real). TSTR is the
ML-ready/utility axis; centring it would mis-file us in the imitation paradigm
(`00_moat_and_scope.md`). It may appear once, as reference-mode context, never as a
headline.

---

## 4. Fair-comparison protocol (the part reviewers attack)

The hardest reviewer objection to a "our tool wins" benchmark is *unfair framing*.
We preempt it:

1. **Two task modes.**
   - **Spec-mode tasks** (cold start): only a specification is given; no real data.
     Learned methods get an empty training set → CSC = 0. Scored on Families A–B.
   - **Reference-mode tasks:** a real (or held-out synthetic-ground-truth) dataset is
     supplied. Learned methods train on it; Misata is given only the *spec derived
     from* it. Scored on Families A–B (core) plus Family C (secondary context only).
   This lets each paradigm compete where it is designed to win and exposes where it
   structurally cannot play.

2. **No metric reads generator internals.** Every metric is a pure function of output
   tables + spec, identical across baselines.

3. **Identical compute budget & seeds** reported; throughput and peak memory logged
   (SDGym convention) `[CITE]`.

4. **Baselines at their best:** SDV synthesizers tuned per their own defaults/docs;
   we do not handicap them. If SDV wins an axis, we say so in the abstract.

5. **Ground-truth oracles** for spec-mode targets are computed independently of any
   generator (the spec *is* the oracle), removing circularity.

---

## 5. Baselines

| Baseline | Paradigm | Expected profile |
|---|---|---|
| **Misata** (this work) | specification, cold-start, closed-form | AME=0, FIVR=0, CSC=1; concedes Family C |
| **Faker + hand-wired FK** | manual templating | FIVR>0 unless hand-fixed; AME large; CSC=1 |
| **SDV GaussianCopula** | imitation (statistical) | strong Family C; CSC=0; AME n/a |
| **SDV CTGAN** | imitation (deep) | strong Family C on complex marginals; CSC=0; slow |
| **SDV HMA** (multi-table) | imitation, relational | FK-aware; CSC=0; the fair relational comparator |
| **Denton temporal disaggregation** | classical, single-series | exact aggregate on 1 series; no relational/marginal-population |

SDV is **mandatory** and run for real (isolated env). Any baseline that cannot be run
is *omitted with a stated reason*, never stubbed with invented numbers.

---

## 6. Task suite

18 domains × 4 configurations = 72 base tasks, each with a frozen spec + oracle:

- **flat** — single fact table, no curve (sanity / FIVR / marginals)
- **narrative-curve** — period aggregate targets on the metric (AME / CR core)
- **multi-table-FK** — full relational schema (FIVR / TCV / HMA comparison)
- **locale-shifted** — same spec under a non-default locale (robustness)

Plus **reference-mode** variants for a subset, pairing each with a real public
dataset (e.g. from the UCI/OpenML tabular collections) so Families C–D are scored on
genuine data. `[CITE: dataset sources, with licenses]`

Every task is versioned and hashed; the suite ships as data + code with Croissant
metadata for D&B compliance. `[CITE]`

---

## 7. Threats to validity (we write this section, reviewers respect it)

- **Construct validity:** AME rewards exactness, which our method achieves by design —
  is the metric "rigged"? Mitigation: AME measures a *user-declared* requirement that
  is real and that no baseline is prevented from meeting; we show learned methods
  *could* be post-hoc rescaled and quantify the marginal damage that causes (ties to
  Prop. 5). The point is not "we hit a number we chose" but "the regime demands this
  and imitation cannot meet it without breaking fidelity."
- **External validity:** curated domain priors may not generalize beyond 18 domains;
  we report locale-shift robustness and document the limit.
- **Privacy validity:** DCR is unreliable (`[CITE: DCR Delusion]`) → we use MIA.
- **Benchmark gaming:** all specs/oracles frozen and hashed; held-out reference data
  for Family C/D to prevent overfitting the suite.

---

## 8. Reproducibility package

- `research/specbench/` — metrics, baselines (pluggable adapters), tasks, runner.
- One command regenerates every number; seeds and versions pinned.
- Results emitted as a machine-readable leaderboard (CSV/JSON) + a rendered table.
- SDV pinned to a known-good version in `requirements-specbench.txt`.

---

## 9. What "a year of depth" concretely means here, mapped to artifacts

1. Correct math identity + honest frontier (Prop. 0–5) — `01_formalization.md` ✓
2. Full literature reconnaissance closing the novelty question — `02_*.md` ✓
3. Metric design reusing SDGym/SDMetrics + new regime axes, with the DCR-Delusion and
   TSTR nuances baked in — this doc ✓
4. Real multi-baseline runs incl. SDV (no stubs) — `specbench/` + E5 [in progress]
5. Threats-to-validity + fair-comparison protocol — §4, §7 ✓
6. Reproducibility package to D&B standard — §8 [to finish]

The depth is the *combination*: correct theory framing, exhaustive lineage, accepted
+ novel metrics, honest concessions, and a runnable suite. That is what a careful
reviewer reads as "this person lived in the problem," not "this was generated."
