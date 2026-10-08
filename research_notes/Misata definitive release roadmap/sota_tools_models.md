# State of the art in synthetic tabular and relational data generation (2025-2026)

Research method note: arxiv.org, openreview.net, datacebo.com, hackernoon.com, news.ycombinator.com and datascience.codata.org were blocked by the egress proxy in this session, and the GitHub API was not enabled for most of these repos. Numbers below come from search-result extracts of those primary sources (paper PDFs, vendor pages), and the cited URL is the primary source the extract came from. Where I could not check a number against full text, I say so.

## Q1. Research models: reported results, datasets, failure modes

### Takeaway
Single-table SOTA moved from GANs/VAEs (CTGAN/TVAE, 2019) to diffusion (TabDDPM 2023, then TabSyn at ICLR 2024 and TabDiff at ICLR 2025) and fast autoregressive models (TabularARGN, 2025). Multi-table SOTA moved from SDV HMA to ClavaDDPM (NeurIPS 2024), then graph-based diffusion and flow models (RelDiff, RGCLD, graph-conditional flow matching, 2025). Every one of them needs real training data. The relational ones still have structural limits (linear schemas only, no more than one FK between a pair of tables) and real compute cost. Learned generators are also measurably bad at behavioural and temporal patterns, and they carry membership-inference risk.

### Cited Findings

**Single-table models**
- TabSyn (ICLR 2024; VAE latent space plus score-based diffusion): reports cutting error rates by **86% for column-wise distribution** and **67% for pair-wise column correlation** estimation compared with the most competitive baselines — [TabSyn paper, ICLR 2024](https://openreview.net/pdf?id=4Ay23yeuz0) / [Amazon Science PDF](https://cdn.amazon.science/a8/d6/054330464506b2b3bb2566db838f/mixed-type-tabular-data-synthesis-with-score-based-diffusion-in-latent-space.pdf)
- TabDiff (ICLR 2025; joint continuous-time diffusion over mixed types) on 7 standard benchmarks with 8 metrics:
  - Shape (marginals): beats TabSyn by an average of **13.3%** on 5 of 7 datasets.
  - Trend (pairwise correlations): beats TabSyn by **22.6%**.
  - MLE/TSTR: beats TabSyn by **15.0%** on average.
  - Imputation: wins on 5 of 7 datasets.
  - Headline claim: "up to 22.5%" improvement on pairwise correlation.
  - — [TabDiff, ICLR 2025 proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/file/5c882988ce5fac487974ee4f415b96a9-Paper-Conference.pdf)
- TabularARGN (MOSTLY AI, Jan 2025; autoregressive, any-order) on Adult:
  - TabularARGN: **97.9% accuracy**, **50.3% DCR share**, **138 s** training.
  - TabSyn: **98.2%**, **50.0%**, **2,316 s**.
  - That is roughly 16x faster at near-equal fidelity. All methods sit near the 50% DCR share, i.e. no measurable leakage relative to a holdout set.
  - — [TabularARGN paper](https://arxiv.org/pdf/2501.12012); [MOSTLY AI blog](https://mostly.ai/blog/introducing-tabularargn-a-flexible-and-efficient-auto-regressive-framework-for-generating-high-fidelity-synthetic-data)
- TabularARGN with differential privacy: accuracy **>90% on Adult at ε=2.8, δ=1e-5**; DP multiplies training time by about 2.6x on Adult — [Privacy-Preserving TabularARGN](https://arxiv.org/pdf/2508.06647)
- CTGAN scores well on privacy (DCR) but "struggled with column distributions and correlations" in 2024-2025 benchmark comparisons. In some evaluations TabDDPM and CTGAN do slightly worse than SMOTE on almost all metrics — [LLM-TabFlow / benchmark summaries](https://arxiv.org/html/2503.02161v1/); [HARMONIC, NeurIPS 2024 D&B](https://proceedings.neurips.cc/paper_files/paper/2024/file/b5aebe9a48398525a9da27a1df827d60-Paper-Datasets_and_Benchmarks_Track.pdf) (search-snippet level; which datasets were used was not confirmed)
- GReaT (LLM-based, text-serialised rows), in a 2025 benchmark on prosumer hardware: strong **R² 0.665**, but **3,714 s** runtime, the longest of the tools compared — [Data Science Journal 2025, "Benchmarking Tabular Data Synthesis ... on Prosumer Hardware"](https://datascience.codata.org/articles/10.5334/dsj-2025-037)
- Privacy risk of foundation-model / LLM generators: mean worst-case membership-inference AUCs of **0.587-0.667**, compared with **0.580-0.627** for CTGAN, TVAE and TabDiff. **LLaMA 3.3 70B was worst at AUC 0.667** — [Risk in Context, 2025](https://arxiv.org/html/2507.17066)
- LLM-based tabular generators can memorise and regurgitate training strings — [When Tables Leak: Attacking String Memorization in LLM-Based Tabular Data Generation](https://arxiv.org/pdf/2512.08875)
- Tabular foundation models (TabPFN v2 in Nature, Jan 2025; TabPFN-2.5 in Nov 2025, for up to 50k rows and 2k features; TabPFN-3 technical report in 2026) are mainly predictors pretrained on *synthetic priors* (structural-causal-model-generated tables). Generation is a secondary use — [TabPFN-2.5](https://arxiv.org/pdf/2511.08667); [TabPFN-3 report](https://arxiv.org/pdf/2605.13986); [State of TFMs 2026](https://mindfulmodeler.substack.com/p/the-state-of-tabular-foundation-models)
- Newer 2025-2026 single-table entrants found in passing: TabularMDLM (masked discrete diffusion; reported strong classification utility under imbalance) and FUSE (flow matching for mixed types, 2026) — [FUSE](https://arxiv.org/pdf/2608.07294); [summary listing TabularMDLM](https://arxiv.org/html/2503.02161v1/)

**Multi-table / relational models**
- ClavaDDPM (NeurIPS 2024; cluster-guided diffusion with classifier guidance across parent-child links):
  - Evaluated on 5 real multi-relational datasets: **California, Instacart 05, Berka, MovieLens, CCS**.
  - Introduced a "long-range (k-hop) dependency" metric.
  - Beats the best baseline by **58.29% on 2-hop correlations (Instacart 05)** and by **20.24% on 3-hop (Berka)**.
  - Only "competitive" (not better) on single-column densities and on cardinality.
  - — [ClavaDDPM, NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/983876577ec81db17ecfae1521df9208-Paper-Conference.pdf)
- Structural limits:
  - **REaLTabFormer can only generate databases with a linear (parent→child chain) structure.**
  - **ClavaDDPM cannot model datasets with two or more foreign keys between the same pair of tables.**
  - — [RelDiff, 2025](https://arxiv.org/html/2506.00710v1); [Benchmark for Synthetic Relational Database Generation](https://openreview.net/pdf/8277ba391d5b4398787bd90ef3e5bcd81f613c9e.pdf)
- Hudovernik et al., "Benchmarking the Fidelity and Utility of Synthetic Relational Data" (Oct 2024):
  - Compares SDV (HMA), RC-TGAN, REaLTabFormer and ClavaDDPM.
  - Fidelity metrics at single-column, single-table and multi-table level; ML-utility metrics; XGBoost-based detection with binomial testing.
  - On datasets the methods can synthesise at all, diffusion (ClavaDDPM, RGCLD) does best, followed by autoregressive TabularARGN.
  - — [arXiv 2410.03411](https://arxiv.org/html/2410.03411v1); [follow-up benchmark](https://openreview.net/pdf/8277ba391d5b4398787bd90ef3e5bcd81f613c9e.pdf)
- REaLTabFormer on the Hudovernik benchmark:
  - XGBoost discriminator accuracy **≈1.0 on AirBnB** and **0.92±0.01 on Rossmann**. Synthetic data is almost perfectly detectable, where 0.5 would mean indistinguishable.
  - ML utility is "near naive baseline" for the AirBnB classification and Rossmann regression tasks.
  - — [arXiv 2410.03411 v1](https://arxiv.org/html/2410.03411v1) (search-extract; I could not open the table)
- RelDiff (2025; graph-based diffusion): **best on all multi-table fidelity metrics**, with an average **25.3%** improvement in k-hop correlation preservation over methods including ClavaDDPM — [RelDiff](https://arxiv.org/html/2506.00710)
- Graph-Conditional Flow Matching for relational data (2025) is another newcomer — [arXiv 2505.15668](https://arxiv.org/pdf/2505.15668)
- "On the Gap Between Diffusion and Transformer Multi-Tabular Generation" (CIKM 2025) studies why autoregressive/transformer relational models trail diffusion models — [ACM DL](https://dl.acm.org/doi/10.1145/3746252.3761530)
- Multi-table synthetic data has its own membership-inference attack surface — [Finding Connections: MIAs for Multi-Table Synthetic Data, 2026](https://arxiv.org/html/2602.07126v1)
- Temporal and behavioural failure:
  - A 2026 benchmark finds that synthetic tabular generators **fail to preserve behavioural fraud patterns**: temporal, velocity and multi-account signals — [arXiv 2604.13125](https://arxiv.org/html/2604.13125v1)
  - Seq2Synth (2026) benchmarks temporal fidelity in sequential tables, framed as "Do Generative Models Keep Time?" — [Seq2Synth](https://arxiv.org/html/2607.15606)

### Inferences
- Learned-model benchmarks almost all use the same small public datasets: Adult, Default, Shoppers, Magic, Beijing, News (TabSyn/TabDiff suite), and California/Instacart/Berka/MovieLens/CCS/Rossmann/AirBnB on the relational side. Nobody benchmarks "no real data available", so Misata does not compete with them on their own benchmark. It competes on schemas that have no seed data.
- Learned relational models are strong at preserving correlations, but they have hard structural ceilings: linear-only (REaLTabFormer), no multiple FKs to the same parent (ClavaDDPM). Behavioural and temporal semantics such as velocity, sessions and per-entity sequences are a documented weak spot. Misata's rule-based simulation of fan-out and time-of-day patterns can be *definitively* better here: it satisfies these by construction.
- Detection accuracy near 1.0 (REaLTabFormer on AirBnB) shows that "learned" does not mean "realistic". A rule-based generator could publish its own detection / k-hop / cardinality scores using the Hudovernik metrics (SDMetrics-style) and borrow the benchmark protocol.
- Worth borrowing:
  - ClavaDDPM's k-hop correlation and cardinality metrics, as self-checks.
  - TabularARGN's any-order autoregressive conditioning, as the idea of conditional rules per column.
  - SDV CAG's taxonomy of predefined constraints (see Q2).

### Gaps
- Exact per-dataset tables (Shape/Trend/MLE/C2ST/DCR) for TabSyn, TabDiff, TabDDPM, CTGAN, TVAE, GReaT and TabuLa could not be extracted because the full texts were blocked. Only the aggregate percentages above are verified.
- RC-TGAN and TabuLa: no specific reported numbers found in this session.
- Training cost and wall-clock figures for ClavaDDPM, RelDiff and RC-TGAN were not retrieved.
- I found no confirmed published "TabPFN-as-generator" benchmark numbers for synthetic data generation (fidelity/DCR). The TabPFN line is documented as a predictor trained on synthetic priors.

## Q2. Commercial and open tools: strengths, licence and pricing, current status

### Takeaway
The market consolidated sharply in 2024-2026:
- Hazy was acquired by SAS (Nov 2024).
- Snaplet shut down (Aug 2024).
- Gretel was acquired by NVIDIA (Mar 2025); its product is gone and has been reborn as the open-source NeMo Data Designer plus Safe Synthesizer.
- Neosync was acqui-hired by Grow Therapy (Aug-Sep 2025, repo archived).
- The MOSTLY AI brand was acquired by Syntho (Jun 2026), after MOSTLY AI open-sourced its SDK under Apache-2.0.
- SDV remains source-available under BSL 1.1, with its best multi-table and constraint features paywalled in SDV Enterprise ($500/mo base). SDV 2.0 shipped in Sep 2026.

There is a clear vacuum for a permissively licensed, maintained, schema-first relational generator for developers.

### Cited Findings
- **SDV / DataCebo**
  - Licence: Business Source License 1.1 (introduced in 2023, per DataCebo). The change date is 4 years after each release, when the release converts to MIT. Production use for a "Synthetic Data Service", i.e. a commercial offering that gives third parties access to the synthesis functionality, is not allowed — [SDV LICENSE](https://github.com/sdv-dev/SDV/blob/main/LICENSE); [DataCebo blog, "Updating the SDV License"](https://datacebo.com/blog/sdv-bsl-license/)
  - Multi-table synthesizers in Enterprise:
    - **HMA** (2018): public.
    - **HSA** (segment-based, 2022): "fast performance for unlimited tables", 20+ tables. Enterprise only.
    - **IndependentSynthesizer**: learns no inter-table trends; tables are connected randomly by cardinality rules. Enterprise only.
    - — [DataCebo multi-table synthesizers](https://datacebo.com/blog/multi-table-synthesizers/); [HSASynthesizer docs](https://docs.sdv.dev/sdv/multi-table-data/modeling/synthesizers/hsasynthesizer); [IndependentSynthesizer docs](https://docs.sdv.dev/sdv/multi-table-data/modeling/synthesizers/independentsynthesizer)
  - Pricing: SDV Enterprise Base **from $500/month + usage per user**; each feature bundle costs **+$250/month/user** — [DataCebo pricing](https://datacebo.com/pricing/)
  - **Constraint-Augmented Generation (CAG)** is a paid bundle of predefined constraints applied across rows, columns or even multiple tables, marketed as "100% valid" output — [CAG announcement](https://datacebo.com/announcements/introducing-cag/); [Predefined constraints docs](https://docs.sdv.dev/sdv/concepts/constraint-augmented-generation-cag/predefined-constraints)
  - **SDV 2.0, released Sep 15, 2026**: "generative relational models" that learn the whole database from a representative subset, typically trained in "minutes to an hour" on a CPU, with more automated setup — [PR Newswire](https://www.prnewswire.com/news-releases/datacebo-releases-sdv-2-0-for-building-generative-relational-models-of-enterprise-data-302879009.html); [IT Brief](https://itbrief.ca/story/datacebo-launches-sdv-2-0-for-synthetic-enterprise-data)
- **Gretel → NVIDIA**
  - NVIDIA acquired Gretel in March 2025, around GTC, for more than Gretel's last $320M valuation; about 80 staff joined NVIDIA — [TechCrunch](https://techcrunch.com/2025/03/19/nvidia-reportedly-acquires-synthetic-data-startup-gretel)
  - Gretel's capabilities re-emerged as NeMo microservices: **Data Designer**, open-sourced under Apache-2.0 in Oct-Nov 2025 with 1,000-1,500+ stars, and **Safe Synthesizer**, under NVIDIA AI Enterprise. The gretelai GitHub org was archived on 2026-02-18, gretel.ai redirects to NVIDIA, and the self-serve platform is discontinued — [NVIDIA-NeMo/DataDesigner](https://github.com/NVIDIA-NeMo/DataDesigner); [Johnny Greco on X](https://x.com/johnnypgreco/status/2041118722715275418); [HN thread](https://news.ycombinator.com/item?id=46136055); [Seedfast, "Gretel alternative"](https://seedfa.st/compare/gretel-alternative) (a competitor's page; treat it as secondary)
  - Data Designer is LLM-centric: it generates "from scratch or from seed data" and was used to build the Nemotron training datasets — [NeMo Data Designer paper, 2026](https://arxiv.org/html/2609.17699v1)
- **MOSTLY AI**
  - Released its Synthetic Data SDK under **Apache-2.0** in 2025: TabularARGN-based; single-table, multi-table and sequential data; DP; fairness-aware generation; automated QA; claims "10x-100x faster" training — [mostly-ai/mostlyai](https://github.com/mostly-ai/mostlyai); [SDK paper, arXiv 2508.00718](https://arxiv.org/pdf/2508.00718)
  - **Syntho acquired the MOSTLY AI brand and related assets on June 9, 2026**; the product is now "MOSTLY AI, powered by Syntho" — [Syntho announcement](https://www.syntho.ai/syntho-acquires-mostly-ai-trademark-and-related-assets/)
- **Hazy**: SAS acquired Hazy's principal software assets; the deal closed Nov 12, 2024, terms undisclosed, and the technology is being folded into SAS Viya — [SAS PR](https://www.prnewswire.com/news-releases/sas-acquires-hazy-synthetic-data-software-to-boost-generative-ai-portfolio-302300944.html); [TechTarget](https://www.techtarget.com/searchbusinessanalytics/news/366615499/SAS-acquires-synthetic-data-generator-to-aid-AI-development)
- **Tonic.ai**: **Structural** de-identifies and subsets production databases while keeping primary and foreign key relationships across complex schemas. **Textual** redacts and synthesises unstructured text (support tickets, clinical notes, chat logs). Both start from real data; pricing is quote-based or via AWS and Azure marketplaces — [Tonic Structural](https://www.tonic.ai/products/tonic-structural); [Tonic Textual](https://www.tonic.ai/products/textual)
- **YData Fabric**: Community, Pay-as-you-go and Enterprise tiers; usage-based pricing that requires contacting sales for numbers — [YData pricing](https://ydata.ai/products/fabric-pricing)
- **Synthesized**: raised a **$20M Series A in Sep 2025** led by Redalpine and repositioned toward AI-powered QA and software testing. I found no evidence of an acquisition — [Fortune](https://fortune.com/2025/09/24/synthesized-series-a-20-million-for-ai-powered-software-testing-qa-redalpine/)
- **Neosync** (open-source test-data/anonymisation for Postgres/MySQL): acquired by Grow Therapy in **Sep 2025** as an acqui-hire; the repo nucleuscloud/neosync was **archived Aug 30, 2025** and the cloud service is offline — [Dealroom](https://app.dealroom.co/news/feed/grow-therapy-acquires-neosync-for-privacy); [Grow Therapy blog](https://growtherapy.com/blog/improving-privacy-in-mental-health/); [Seedfast migration guide](https://seedfa.st/blog/neosync-alternative) (competitor source)
- **Snaplet** (Postgres seed/snapshot): **shut down Aug 31, 2024**. The last meaningful @snaplet/seed release was v0.98.0 on Jul 30, 2024, and the community fork shows limited activity — [Seedfast compare](https://seedfa.st/compare) (competitor source)
- **Synth** (shuttle-hq, Rust, declarative JSON schema, database-agnostic, "millions of rows"): about 1.5k stars, latest release v0.6.9. One search summary described it as "actively maintained", but I could not verify recent commits — [shuttle-hq/synth](https://github.com/shuttle-hq/synth); [releases](https://github.com/shuttle-hq/synth/releases)
- **Mimesis vs Faker**: Mimesis is said to be about 12x faster. For 10k full names: Mimesis **0.137 s, 99.88% unique**; Faker **1.758 s, 93.63% unique**. Mimesis uses pre-computed locale data and no regex-based generation — [Mimesis docs, About](https://mimesis.name/latest/about.html)
- **Faker** is a column-level random value generator. It generates values independently, without relationships or distributions, and that "pass[es] CI and break[s] in staging" on mid-sized schemas — [HackerNoon, "Faker Is Not Synthetic Data"](https://hackernoon.com/faker-is-not-synthetic-data-where-mid-sized-schemas-break) (article body blocked; snippet only)

### Inferences
- Every surviving commercial leader needs real data, either for training (SDV, MOSTLY/Syntho, YData, Gretel/NVIDIA Safe Synthesizer) or for transformation (Tonic, Neosync). LLM-first Data Designer is the closest rival to "no real data", but it is LLM-cost-bound and row-oriented rather than relational-integrity-first.
- The developer seeding niche (Snaplet → Neosync → ?) has lost two products in 12 months. Competitors such as Seedfast are actively courting the stranded users. Misata could explicitly target this audience: Postgres/Django seeding, FK-correct and deterministic.
- Licensing is a real differentiator. SDV's BSL bans offering synthesis as a service and its scalable multi-table synthesizers (HSA) are Enterprise-only, while MOSTLY's SDK is Apache-2.0. A permissive (MIT/Apache) Misata with unlimited tables and FK-correct output by construction directly fills what SDV paywalls.
- Worth borrowing:
  - SDV CAG's predefined-constraint catalogue: inequality, fixed combinations, ranges, cross-table constraints.
  - Mimesis's pre-computed locale pools and published uniqueness/speed benchmark style.
  - Tonic's subsetting with referential integrity as a mental model.

### Gaps
- Tonic, Synthesized and YData list prices are not public.
- I could not verify current maintenance status (last commit dates) for Synth, Faker or Mimesis because the GitHub API was blocked for these repos.
- I found no information on "DataFactory-style" tools beyond the above.
- The exact date SDV moved to BSL is ambiguous. One snippet says "late 2022" for parts of the ecosystem and another says 2023. The full DataCebo blog text was blocked.

## Q3. User complaints

### Takeaway
The documented complaints are:
- broken or unknown foreign keys and cardinality mis-modelling in SDV HMA
- very slow multi-table training (days for about 1M rows with constraints)
- constraints that error out on multi-parent tables
- licence restrictions
- the need for real data
- privacy uncertainty, especially for LLM generators

### Cited Findings
- SDV `HMASynthesizer` **may sample foreign key values that were not present in the original data**, and fails to capture child-FK cardinality that is lower than the parent PK count — [SDV #1581](https://github.com/sdv-dev/SDV/issues/1581)
- HMA "always creates a child for every parent row", producing too much synthetic data — [SDV #1673](https://github.com/sdv-dev/SDV/issues/1673)
- Requests for a utility to **drop unknown references and enforce referential integrity**, because SDV requires full referential integrity in input data — [SDV #1792](https://github.com/sdv-dev/SDV/issues/1792)
- "Foreign key column contains unknown references" errors when a child references multiple parents — [SDV #2136](https://github.com/sdv-dev/SDV/issues/2136)
- The `FixedCombinations` constraint errors on a child table with multiple parents in HMA — [SDV #2087](https://github.com/sdv-dev/SDV/issues/2087)
- Constraints break re-fitting ("Cannot fit twice if I add constraints: ValueError: non-numerical values") — [SDV #1258](https://github.com/sdv-dev/SDV/issues/1258)
- Scalability and GPU-support requests for multi-table synthesis — [SDV #2110](https://github.com/sdv-dev/SDV/issues/2110)
- A user reported HMA took **about 3 days for 1M rows with constraints**, and SDV 1.6.0 added a warning when HMA is likely to be slow for a schema — [SDV on PyPI, 1.6.0 notes](https://pypi.org/project/sdv/1.6.0/); [#2110](https://github.com/sdv-dev/SDV/issues/2110)
- Misleading fit-time error messages for learned distributions in HMA — [SDV #1579](https://github.com/sdv-dev/SDV/issues/1579)
- Faker: independent per-column random values yield inconsistent records that "pass CI and break in staging" — [HackerNoon](https://hackernoon.com/faker-is-not-synthetic-data-where-mid-sized-schemas-break)
- LLM generators memorise strings, and their worst-case MIA AUC reaches 0.667 — [When Tables Leak](https://arxiv.org/pdf/2512.08875); [Risk in Context](https://arxiv.org/html/2507.17066)
- Licence: BSL forbids providing a commercial "Synthetic Data Service" — [SDV LICENSE](https://github.com/sdv-dev/SDV/blob/main/LICENSE)
- Product churn is itself a complaint: Snaplet users who migrated to Neosync "found themselves needing to migrate again" — [Seedfast, Neosync alternative](https://seedfa.st/blog/neosync-alternative) (competitor source)

### Inferences
- The top SDV complaints (FK integrity, cardinality, multi-parent constraints, speed) are exactly what a schema-first generator solves by construction, so Misata can claim "0 orphan FKs, exact cardinality control, multi-parent constraints, seconds not days" and back it with tests.
- Privacy uncertainty is structurally absent for no-real-data generation, since nothing is memorised. That is a definitive, explainable advantage over every learned model and LLM approach.

### Gaps
- Reddit and HN threads could not be opened (HN blocked), so I have no direct quotes on complaints about unrealistic text or schema setup effort.
- I have no quantitative survey of complaint frequency.

## Q4. Rule-based / schema-first vs learned models

### Takeaway
Learned models win when real data exists and the goal is to reproduce its joint distribution (TSTR, k-hop correlations). Rule-based, schema-first tools win on these:
- no data needed
- zero privacy risk
- guaranteed constraints and referential integrity
- arbitrary schemas (multiple FKs, non-linear graphs)
- speed and scale
- determinism
- controllable scenarios such as edge cases, temporal and behavioural patterns, and load sizes

The weak spots of rule-based tools are realistic cross-column correlations and text realism, unless they are explicitly modelled.

### Cited Findings
- Learned relational SOTA cannot handle some schema shapes at all: REaLTabFormer is linear-only, and ClavaDDPM cannot handle two or more FKs between the same pair of tables — [RelDiff](https://arxiv.org/html/2506.00710v1)
- Even SDV's own scalable option (IndependentSynthesizer) gives up inter-table learning and connects tables "randomly based on basic cardinality rules", which is effectively rule-based joining — [SDV docs](https://docs.sdv.dev/sdv/multi-table-data/modeling/synthesizers/independentsynthesizer)
- SDV markets CAG as producing data that conforms to business logic "100% of the time". Constraint satisfaction is something users explicitly pay for — [CAG](https://datacebo.com/announcements/introducing-cag/)
- Learned generators fail on behavioural and temporal fraud signals (velocity, multi-account) — [arXiv 2604.13125](https://arxiv.org/html/2604.13125v1)
- Training-cost gap: TabSyn takes 2,316 s on Adult (about 32k rows), GReaT 3,714 s in the DSJ benchmark, and HMA about 3 days at 1M rows with constraints — [TabularARGN](https://arxiv.org/pdf/2501.12012); [DSJ 2025](https://datascience.codata.org/articles/10.5334/dsj-2025-037); [SDV #2110](https://github.com/sdv-dev/SDV/issues/2110)
- Learned SOTA does well on fidelity:
  - TabDiff and TabSyn reach strong Shape, Trend and MLE scores — [TabDiff](https://proceedings.iclr.cc/paper_files/paper/2025/file/5c882988ce5fac487974ee4f415b96a9-Paper-Conference.pdf)
  - ClavaDDPM preserves 2-3-hop correlations — [ClavaDDPM](https://proceedings.neurips.cc/paper_files/paper/2024/file/983876577ec81db17ecfae1521df9208-Paper-Conference.pdf)
  - A purely independent generator like Faker has, by design, no such correlations — [HackerNoon](https://hackernoon.com/faker-is-not-synthetic-data-where-mid-sized-schemas-break)
- Mimesis-style pre-computed pools beat Faker on speed (12x) and uniqueness (99.88% vs 93.63%) — [Mimesis](https://mimesis.name/latest/about.html)
- The TabPFN family is pretrained entirely on *synthetic* tables drawn from hand-designed priors (structural causal models). Principled rule- and prior-based synthetic generation is valuable enough to train SOTA models — [TabPFN-2.5](https://arxiv.org/pdf/2511.08667); [TDS explainer](https://towardsdatascience.com/exploring-tabpfn-a-foundation-model-built-for-tabular-data/)

### Inferences
- Where Misata can be definitively better, and how to prove it:
  1. Referential integrity and cardinality exactness on arbitrary FK graphs (multi-FK, diamonds, self-references). Show orphan rate 0 and an exact fan-out distribution next to SDV HMA issue cases #1581, #1673 and #2136.
  2. Speed: million-row multi-table generation in seconds, against reported hours or days.
  3. Zero memorisation or MIA risk, since no real rows exist.
  4. Constraint guarantees comparable to SDV's paid CAG, but free.
  5. Behavioural and temporal scenarios (sessions, velocity, seasonality, night-heavy hours) that learned models measurably fail at.
  6. A permissive licence and stable maintenance, in a market where Snaplet, Neosync and Gretel's product all disappeared.
- What to borrow:
  - SCM-style priors from TabPFN, to inject plausible cross-column dependence without data.
  - ClavaDDPM/Hudovernik metrics (cardinality, k-hop correlation, C2ST detection) as internal "realism tells".
  - SDV CAG's constraint vocabulary.
  - TabularARGN's per-column conditional ordering.
  - An optional "fit marginals from a sample or from published stats" path, to close part of the fidelity gap without reproducing rows.
  - Data Designer's LLM-column pattern, used sparingly for text realism.
- Where learned models will keep winning: matching a specific real dataset's joint distribution for ML training or TSTR, and for analytics on that data. Misata should not claim parity there.

### Gaps
- I found no published head-to-head benchmark of a rule-based generator (Faker, Mimesis or Synth) against learned models on fidelity metrics. That would be novel territory for Misata to publish.
