# The Moat & Scope Lock (read this before touching anything)

**Status:** brick 0 — the north star. Written after field reconnaissance (see §refs).
Every other research doc and every line of `specbench/` must serve this. If a metric,
baseline, or claim does not serve the moat below, it does not belong in the core.

---

## 1. The one-sentence moat

> **Exact, deterministic, closed-form conformance to declared *analytical outcomes*
> (aggregate curves, rates, group-wise distributions) across a *relational* schema,
> generated from a *natural-language/declarative specification* with *zero source
> data*.**

The evaluation axis is **CONFORMANCE, not FIDELITY**. We do not ask "how close is the
output to a real dataset?" (that is the ML-ready/imitation question). We ask "how
exactly does the output obey the declared specification?"

## 2. What we are NOT (and must never be benchmarked primarily as)

- **NOT an ML-ready / fidelity-to-real generator.** That is SDV, CTGAN, TabDDPM,
  RelDiff (2025), IRG (SIGKDD'26), DP-relational synthesis. They learn `P(D)` from
  real data and are judged on TSTR / detection / DCR. We concede that axis openly and
  do not compete on it. Including fidelity as a *core* metric mis-files us as a weak
  member of this club. Fidelity metrics may appear ONLY as secondary context on
  reference-mode tasks, never as headline axes.

## 3. The competitive landscape (honest, with the real threat named)

| System | Cold-start? | Spec/outcome targets? | Exact & deterministic? | Relational? | Judged on |
|---|---|---|---|---|---|
| **Misata (us)** | yes | **yes (analytical outcomes)** | **yes, closed-form** | yes | conformance |
| NeMo Data Designer (Gretel/NVIDIA, 2025) | yes | partial (LLM-guided, validators) | **no — LLM-stochastic, approximate** | partial | LLM-as-judge |
| SDV / CTGAN / RelDiff / IRG | no (needs data) | no | no | yes | fidelity-to-real |
| QAGen / XData / DataSynth (DB test-data) | yes | **query cardinalities only** | yes (CSP solve) | yes | query cardinality match |
| Faker + scripts | yes | no | no | manual | nothing standardized |

**The real competitor is NeMo Data Designer**, not SDV. Our wedge against it is the
property it structurally lacks: **provable exactness + determinism + closed-form** (no
LLM call, no sampling variance, bitwise-reproducible). Our wedge against the
QAGen-family is **analytical/distributional outcomes from NL specs**, not just query
output cardinalities. Our wedge against SDV is the entire **cold-start + spec** frame.

## 4. The benchmark gap (precise, citable)

No existing benchmark measures **analytical conformance of cold-start relational
synthesis**:

- **SDGym / SDMetrics** → fidelity-to-real (presupposes real data).
- **TPC-H / TPC-DS** → engine performance on *fixed* generated data; the generator's
  *conformance to a spec* is not the object of measurement.
- **QAGen-style evaluations** → match of *query output cardinalities* for optimizer
  testing; not analytical outcomes (curves/rates/group distributions) and not NL.

**SpecBench fills exactly this hole.** That is the contribution sentence.

## 5. Metric families — CORRECTED to serve conformance

- **CORE (this is the paper):**
  - **A. Specification adherence** — AME (aggregate-match error), CR (controllability
    response), CSAT (hard-constraint satisfaction), and **outcome-conformance**
    extensions: rate targets, group-wise distribution targets, funnel/ratio targets.
  - **B. Structural integrity** — FIVR (FK violations), TCV (temporal coherence), DET
    (determinism/reproducibility).
- **SECONDARY CONTEXT (reported, never headline; only on reference-mode tasks):**
  - marginal plausibility, and a *single* fidelity number purely to demonstrate the
    honest trade (cf. Prop. 5 heavy-tail condensation). NOT TSTR-centric. NOT DCR as a
    privacy claim.
- **CUT from core:** TSTR as a success axis, detection-AUC as a success axis,
  DCR-as-privacy. (Privacy for us is *by construction* — zero real data touched — and
  stated as a categorical property, optionally checked with one MIA = chance result.)

## 6. Target venue (matches the moat)

**Data-management / systems**, not the NeurIPS ML-fidelity community:
- **VLDB / SIGMOD** (test-data generation, QAGen lineage) — best fit.
- **NeurIPS Datasets & Benchmarks** — viable *iff* framed as a new evaluation paradigm
  (conformance), explicitly distinct from SDGym.
- **JOSS** — for the tool, in parallel.

## 7. The non-negotiables (anti-slop guarantees)

1. Real numbers only. SDV/NeMo baselines run for real or are omitted with a reason.
2. Every classical component cited to its owner (Lukacs, Hamilton/Cox, Aitchison,
   Denton, QAGen, condensation theory).
3. The honest frontier (Prop. 5) stays in — we map the boundary, not overclaim past it.
4. Conformance ≠ fidelity is stated in the abstract; we concede fidelity to imitation.
5. Fair two-mode protocol so every paradigm competes where it is designed to win.

## refs (to formalize with full citations)
RelDiff (2506.00710), IRG (2312.15187, SIGKDD'26), DP-relational (2405.18670),
NeMo Data Designer (Gretel/NVIDIA 2025), QAGen (SIGMOD 2007), XData (VLDB),
DataSynth (VLDB 2011), SDGym/SDMetrics, TPC-H/DS, condensation (1812.02513),
Lukacs 1955, Denton 1971, Cox 1987, Aitchison 1986, DCR Delusion (2505.01524).

Related internal docs: [[project_paper_kernel]] [[project_competitive_positioning]]
