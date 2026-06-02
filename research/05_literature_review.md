# Literature Review & Annotated Bibliography

**Status:** brick 4. The scholarly backbone. Every entry is a real, verified work
with author/venue/year; annotations say *what it does* and *how our work differs*.
Organized into the six threads that together bound our contribution. This is the
material the paper's Related Work compresses, and the source of every `[CITE]`.

> **Positioning thesis (one paragraph).** Synthetic data research splits into
> *imitation* (learn a real distribution, sample from it; judged on fidelity) and
> *specification* (declare what the data must satisfy; judged on conformance). Our
> work is squarely in the specification camp. Within it, the database community built
> *query-aware* generators (match query-output cardinalities) and the official-
> statistics community built *aggregate-consistent* methods (match marginal/temporal
> totals). Neither targets **analytical outcomes** (revenue curves, rates, group
> distributions) declared in **natural language**, across a **relational** schema,
> from **zero data**, with **exact, closed-form, deterministic** guarantees. That
> specific intersection is the gap. The mathematics that makes it exact is classical
> (Lukacs proportion–sum independence; controlled rounding) and we cite it as such;
> the contribution is the unification, the conformance evaluation paradigm
> (SpecBench), the honest impossibility frontier (condensation), and the reference
> system.

---

## Thread 1 — Imitation / learned tabular & relational synthesis (what we are NOT)

These learn `P(D)` from real data and are evaluated on fidelity-to-real. We concede
this axis and do not compete on it; we cite them to draw the paradigm boundary.

- **Patki, Wedge, Veeramachaneni (2016), "The Synthetic Data Vault," IEEE DSAA.**
  Origin of SDV; copula-based multi-table synthesis with the HMA (Hierarchical
  Modeling Algorithm). The reference toolkit/baseline of the field. *Diff:* requires
  real data; cannot ingest analytical-outcome targets; non-deterministic.
- **Xu, Skoularidou, Cuesta-Infante, Veeramachaneni (2019), "Modeling Tabular Data
  using Conditional GAN," NeurIPS.** CTGAN/TVAE; mode-specific normalization +
  conditional GAN for mixed-type tables. *Diff:* imitation; no exact constraints;
  training-based.
- **Kotelnikov et al. (2023), "TabDDPM: Modelling Tabular Data with Diffusion
  Models," ICML.** Diffusion for tabular fidelity. *Diff:* imitation; fidelity-axis.
- **Patki/DataCebo HMA; "Hierarchical Conditional Tabular GAN" (HCTGAN, arXiv
  2411.07009, 2024).** Multi-table GAN that *guarantees referential integrity* while
  sampling. *Diff:* learned/fidelity; integrity is a side-guarantee, not conformance
  to declared outcomes; needs source data.
- **RelDiff (arXiv 2506.00710, 2025), "Relational Data Generative Modeling with
  Graph-Based Diffusion."** Graph-decomposed diffusion; strict referential integrity;
  SOTA fidelity on 11 relational benchmarks. *Diff:* the current fidelity SOTA for
  relational data — the strongest imitation comparator — but still requires real data
  and targets fidelity, not outcome conformance.
- **IRG (arXiv 2312.15187, SIGKDD 2026), "Modular Synthetic Relational Database
  Generation with Complex Relational Schemas."** DFS traversal preserving complex key
  constraints across 10 real schemas. *Diff:* learned; integrity-preserving but
  fidelity-judged; not spec/outcome-driven.
- **DP-relational synthesis (arXiv 2405.18670, 2024).** Differential privacy for
  multi-table generation. *Diff:* privacy-by-noise on real data; we are
  privacy-by-construction (no real data) and conformance-judged.

**Takeaway:** the imitation thread is mature and converging on relational fidelity
(RelDiff, IRG). We position *orthogonally*: different input (a spec, not data),
different success criterion (conformance, not fidelity). RelDiff/IRG are the
reference-mode comparators that, by construction, score zero on cold-start tasks.

---

## Thread 2 — Query-aware / constraint-based DB test-data generation (our closest kin)

The database community's specification tradition: generate a database so that
*queries* produce controlled results. This is the lineage we extend.

- **Binnig, Kossmann, Lo, Özsu (2007), "QAGen: Generating Query-Aware Test
  Databases," SIGMOD, pp. 341–352.** Seminal. Takes schema + query + constraints on
  query operators; symbolic query processing produces a DB where each operator yields
  target intermediate cardinalities. Supports 13/22 TPC-H queries; ~1GB in ~17h.
  *Diff:* targets **query-output cardinalities** for optimizer testing, not
  **analytical outcomes** (curves/rates/distributions) on metric columns; not NL;
  CSP/symbolic, not closed-form sampling; single-DB-per-query.
- **Lo, Binnig, Kossmann, Özsu, Fan — "A framework for testing DBMS features,"
  VLDB Journal (2010).** Extends QAGen toward DBMS feature testing. *Diff:* same
  cardinality/operator focus.
- **DataSynth — Arasu, Kaushik, Li (2011), "Data Generation using Declarative
  Constraints," SIGMOD; PVLDB 4(12).** Declarative *cardinality* constraints →
  database instances via constraint solving. The cleanest "declarative spec → data"
  precedent. *Diff:* cardinality constraints, not distributional/temporal analytical
  outcomes; not NL; not zero-data narrative synthesis.
- **Projection-compliant database generation (PVLDB 2022, 10.14778/3510397.3510398).**
  Extends cardinality control to projection/DISTINCT/GROUP-BY operators. *Diff:* still
  query-cardinality, optimizer-testing oriented.
- **XData — Chandra et al. (data generation for testing/grading SQL, VLDB J 2015).**
  Generates datasets to kill SQL query mutants for testing/grading. *Diff:*
  query-correctness testing, not analytical-outcome conformance.
- **TPC-H / TPC-DS data generators (dbgen/dsdgen); tpchgen-rs (2025).** Industry-
  standard fixed-schema generators with controlled skew for engine benchmarking.
  *Diff:* fixed schema and distribution; the generator is a means to benchmark
  *engines*, not itself measured for conformance to an arbitrary declared spec.

**Takeaway:** QAGen/DataSynth are our true ancestors. We differ on the *target type*
(analytical outcomes vs query cardinalities), the *interface* (natural language /
declarative outcome curves), the *method* (closed-form conditional-sum sampling vs
CSP/symbolic), and the *evaluation* (we introduce conformance metrics; they reported
cardinality match + runtime).

---

## Thread 3 — LLM / cold-start "from-scratch" generation (the live competitor)

- **NeMo Data Designer (NVIDIA, ex-Gretel, 2025; Apache-2.0).** Post-acquisition
  successor to Gretel's developer tooling. Generates from scratch or seed via
  statistical samplers + LLMs; dependency-aware; Python/SQL/custom validators;
  LLM-as-judge quality scoring. *Diff (the crux):* **LLM-stochastic and approximate**
  — validators *check* and *retry*, they do not *guarantee*; no exactness, no
  determinism, no closed-form conformance. We provide provable exact conformance and
  bitwise determinism, which an LLM pipeline structurally cannot.
- **LLM-for-synthetic-data surveys (arXiv 2503.14023, 2025) and Text-to-SQL data
  synthesis (SING-SQL 2509.25672; TailorSQL; SelectCraft, 2025).** Synthesize
  *training data for NL→SQL models*. *Diff:* different task (model training data), not
  outcome-conformant relational test databases.

**Takeaway:** NeMo Data Designer is the competitor to name explicitly. Our wedge is
the formal-guarantee axis (exact + deterministic + closed-form), which we *measure*
in SpecBench and they cannot meet.

---

## Thread 4 — Aggregate-consistent synthesis in official statistics (our math's home)

The methods our exact-aggregate engine is mathematically a member of. We cite to
establish lineage and to *avoid claiming their results as new*.

- **Deming & Stephan (1940), "On a Least Squares Adjustment…," Ann. Math. Stat.**
  Iterative Proportional Fitting (IPF/RAS): adjust a table to match known margins.
  Foundational aggregate-consistency. *Diff:* categorical contingency tables,
  in-expectation/iterative; we do continuous, exact, closed-form.
- **Denton (1971), "Adjustment of Monthly or Quarterly Series to Annual Totals,"
  JASA; Chow & Lin (1971), Rev. Econ. Stat.** Temporal disaggregation: high-frequency
  series preserving the low-frequency total (movement preservation). **Our single-
  series aggregate task is mathematically a disaggregation.** *Diff:* series→series
  (one value per sub-period); we generate a *population of transaction rows per
  period* with a controlled marginal — aggregate→population, not series→series.
  Comparator baseline in SpecBench.
- **`tempdisagg` (R Journal 2013); Sparse Temporal Disaggregation (JRSS-A 2022).**
  Modern implementations; we use one as the Denton baseline.
- **Population synthesis / spatial microsimulation (Müller & Axhausen 2010 state of
  the art; Lovelace & Dumont, *Spatial Microsimulation with R*).** IPF-based synthetic
  populations matching zonal margins. *Diff:* discrete attributes, margin-matching,
  single-table populations; no relational FK, no temporal outcome curves, needs real
  margins.

**Takeaway:** our engine's *exactness* belongs to this family. We say so plainly.
What is not in this family: the relational + NL + analytical-outcome + zero-data
wrapper, and the conformance benchmark.

---

## Thread 5 — The exact mathematics (cited precisely, claimed as classical)

- **Lukacs (1955), "A Characterization of the Gamma Distribution," Ann. Math. Stat.
  26(2):319–324.** Proportion–sum independence: for independent positive `X,Y`,
  `X/(X+Y) ⟂ X+Y` iff both are Gamma with common scale; generalizes to the Dirichlet.
  **This is Proposition 0's foundation:** our Stage-2 Dirichlet partition *is* exact
  sampling from a Gamma population conditioned on its sum. Primary math citation.
- **Aitchison (1986), *The Statistical Analysis of Compositional Data*.** Dirichlet/
  Beta marginals on the simplex; basis for our closed-form CV (Prop. 2).
- **Cox (1987), "A Constructive Procedure for Unbiased Controlled Rounding," JASA.**
  Round table entries to integer multiples preserving additivity along margins. **Our
  integer-unit exactness is controlled rounding;** largest-remainder is its hand-
  computable case. Cited for Prop. 1's exactness lineage.
- **Balinski & Young (1982), *Fair Representation*; Balinski–Young impossibility
  (1983).** Apportionment theory; the largest-remainder (Hamilton) method we use for
  exact integer sums, and its known paradoxes (context for why we choose it).
- **Willenborg & de Waal (2001), *Elements of Statistical Disclosure Control.***
  Textbook home of controlled rounding / CTA; situates Prop. 1 in SDC.

---

## Thread 6 — The impossibility frontier: condensation of conditioned sums

The honest negative result (Prop. 5): why exact aggregate + arbitrary heavy-tailed
marginal cannot coexist. **Nuance to state carefully** (the search corrected a naive
version): under a large-deviation sum constraint, subexponential variables exhibit a
*single big jump* — one summand absorbs the excess while the **rest become
independent with (modified) `O(1)` marginals**. So the conditional marginal departs
from `F` via a condensate, not via uniform inflation.

- **Armendáriz & Loulakis (2011), "Conditional distribution of heavy-tailed random
  variables on large deviations of their sum," Stoch. Proc. Appl. 121(5):1138–1147
  (arXiv 0912.1516).** The precise statement of the conditioned-sum limit law for
  subexponential variables. Core citation for Prop. 5.
- **Szavits-Nossan, Evans, Majumdar (2014), "Condensation transition in joint large
  deviations of linear statistics" (arXiv 1406.3573); and "Condensation for random
  variables conditioned by the value of their sum" (arXiv 1812.02513).** Condensation
  transition: the regime boundary where a condensate forms. Establishes that the
  fluid (no-condensate) phase — where marginals are preserved — is exactly the
  light-tailed/moderate-sum regime our Gamma engine occupies. This is *why* our design
  works and *where* it must break.
- **Nagaev; Denisov, Dieker, Shneer — big-jump / subexponential large deviations
  (foundational).** Classical basis of the single-big-jump principle.

**Takeaway:** Prop. 5 is not our theorem; it is an application of established
condensation theory that *delimits the achievable frontier*. Stating it correctly
(single big jump, fluid vs condensed phases) is the depth signal; claiming it as new
would be the slop signal.

---

## Thread 7 — Evaluation methodology (for SpecBench's design & contrast)

- **SDGym (DataCebo) & SDMetrics.** Standard benchmark/metric suites for tabular
  synthesis: fidelity (column/pair shapes, detection), ML-efficacy, privacy, runtime.
  *Diff:* presuppose real data; measure fidelity-to-real. SpecBench measures
  conformance-to-spec — orthogonal axes; we reuse SDMetrics shape/correlation only as
  *secondary context* on reference-mode tasks.
- **TSTR — train-synthetic-test-real (Esteban et al. 2017; widely used).** ML-utility
  protocol. *Diff:* utility axis; reported once as context, never headline.
- **The "DCR Delusion" (arXiv 2505.01524, 2025).** Shows distance-to-closest-record
  is *uninformative* of membership-inference risk; DCR-private data still leaks.
  *Use:* justification for **not** adopting DCR as a privacy claim; our privacy is
  by-construction (zero real data), optionally checked via MIA = chance.
- **NeurIPS Datasets & Benchmarks Track CFP (2021–2026).** Acceptance criteria —
  accessibility, documentation, reproducibility (Croissant metadata), and impact via
  challenging a dominant evaluation paradigm. SpecBench is designed to these.

---

## Master citation list (to convert to .bib)

1. Lukacs 1955, Ann. Math. Stat. 26(2):319–324.
2. Aitchison 1986, *Statistical Analysis of Compositional Data*, Chapman & Hall.
3. Cox 1987, JASA 82(398):520–524.
4. Balinski & Young 1982, *Fair Representation*, Yale Univ. Press.
5. Willenborg & de Waal 2001, *Elements of Statistical Disclosure Control*, Springer.
6. Deming & Stephan 1940, Ann. Math. Stat. 11(4):427–444.
7. Denton 1971, JASA 66(333):99–102.
8. Chow & Lin 1971, Rev. Econ. Stat. 53(4):372–375.
9. Sax & Steiner 2013, "Temporal Disaggregation of Time Series," R Journal 5(2).
10. Müller & Axhausen 2010, "Population synthesis…state of the art," STRC.
11. Armendáriz & Loulakis 2011, Stoch. Proc. Appl. 121(5):1138–1147 (arXiv 0912.1516).
12. Szavits-Nossan, Evans, Majumdar 2014, arXiv 1406.3573 (PRL).
13. Evans, Majumdar et al. 2018, "Condensation…sum," arXiv 1812.02513.
14. Binnig, Kossmann, Lo, Özsu 2007, "QAGen," SIGMOD pp. 341–352.
15. Lo, Binnig, Kossmann, Özsu, Fan 2010, "Testing DBMS features," VLDB J 19.
16. Arasu, Kaushik, Li 2011, "DataSynth / Data Generation using Declarative
    Constraints," SIGMOD; PVLDB 4(12).
17. Projection-compliant database generation 2022, PVLDB (10.14778/3510397.3510398).
18. Chandra et al. 2015, "Data generation for testing/grading SQL queries," VLDB J 24.
19. Patki, Wedge, Veeramachaneni 2016, "The Synthetic Data Vault," IEEE DSAA.
20. Xu, Skoularidou, Cuesta-Infante, Veeramachaneni 2019, "CTGAN," NeurIPS.
21. Kotelnikov et al. 2023, "TabDDPM," ICML.
22. HCTGAN 2024, arXiv 2411.07009.
23. RelDiff 2025, arXiv 2506.00710.
24. IRG 2026 (SIGKDD), arXiv 2312.15187.
25. DP relational synthesis 2024, arXiv 2405.18670.
26. NeMo Data Designer (NVIDIA) 2025, Apache-2.0 (software + docs).
27. LLM synthetic data survey 2025, arXiv 2503.14023.
28. SING-SQL 2025, arXiv 2509.25672.
29. "The DCR Delusion" 2025, arXiv 2505.01524.
30. Esteban, Hyland, Rätsch 2017, "Real-valued (medical) time series GANs / TSTR,"
    arXiv 1706.02633.
31. SDGym / SDMetrics (DataCebo, software).
32. TPC-H, TPC-DS specifications (TPC); tpchgen-rs 2025 (software).
33. NeurIPS Datasets & Benchmarks Track CFP 2021–2026.

> **Verification note.** Authors/venues/years/pages above were taken from search
> results during reconnaissance. Before submission, each must be confirmed against the
> primary source (DOI/DBLP) and converted to BibTeX. Items marked from software (NeMo,
> SDGym, TPC) cite the tool + docs, not a paper, and should be labeled as such.
