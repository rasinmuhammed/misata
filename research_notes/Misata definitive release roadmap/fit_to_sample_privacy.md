# Fit-to-sample modes with privacy guarantees for a rule-based generator (Misata)

Research method note: arxiv.org, pages.nist.gov, docs.sdv.dev, docs.smartnoise.org, alphaxiv and drivendata were blocked by the session's egress proxy, so paper findings below come from search-result abstracts/snippets of the primary papers, from PyPI JSON metadata (fetched directly), and from GitHub READMEs (raw.githubusercontent.com was reachable). Numbers that could not be read from a primary source in this session are listed under Gaps rather than stated. Repo context checked locally: Misata is MIT-licensed (`/home/user/misata/LICENSE`) and already ships an optional `CopulaGenerator` in `misata/generators/copula.py` that wraps SDV's `GaussianCopulaSynthesizer` via the `[advanced]` extra (`sdv>=1.0.0` in `pyproject.toml` line 135). That matters for the licence findings below.

## 1. Which methods win on fidelity/utility under differential privacy (NIST 2018/2020, CRC, benchmarks)

### Takeaway
Across every independent benchmark found, marginal-based "select-measure-generate" methods built on Private-PGM (MST, AIM, and PrivMRF) beat DP-GANs and other deep models on tabular fidelity and utility. AIM is the best general choice when a query workload is known. MST is the simplest strong baseline, and it won NIST 2018. At epsilon about 1, PrivMRF and AIM lead. At epsilon of 5 or more, ML utility is close to training on the real data.

### Cited Findings
- **NIST 2018 DP Synthetic Data Challenge, Match #3:** 1st rmckenna (score 902,307), 2nd ninghui (870,097), 3rd privbayes (823,512), 4th gardn999 (768,802), 5th manisrivastava (541,494). The overall final ranking was RMcKenna, DPSyn, PrivBayes, Gardn999, UCLANESL. — [NIST 2018 challenge page](https://www.nist.gov/ctl/pscr/open-innovation-prize-challenges/past-prize-challenges/2018-differential-privacy-synthetic); [HeroX](https://www.herox.com/Differential-Privacy-Synthetic-Data-Challenge)
- **How the 2018 winner worked:** it privately detects correlations, then measures 3-way marginals over the correlated attributes. Its generalisation, MST, became "a scalable and general approach". — [NIST blog on DP synthetic data](https://www.nist.gov/blogs/cybersecurity-insights/differentially-private-synthetic-data); [McKenna et al., "Winning the NIST Contest" (arXiv 2108.04978)](https://arxiv.org/pdf/2108.04978)
- **A comparative study of the 2018 entrants exists:** [Bowen & Snoke, arXiv 1911.12704](https://arxiv.org/pdf/1911.12704). Its per-epsilon numbers were not readable in this session.
- **NIST 2020 Temporal Map Challenge** (Oct 2020 to Jun 2021, $129k in prizes, more than 70 algorithms): 1st N-CRiPT (NUS), 2nd Minutemen (UMass Amherst, McKenna's group), 3rd DPSyn (Purdue). N-CRiPT used Markov random fields. Final scoring ran at epsilon 10, and solutions also "competed very well on lower epsilons". — [NIST 2020 challenge page](https://www.nist.gov/ctl/pscr/open-innovation-prize-challenges/past-prize-challenges/2020-differential-privacy-temporal); [NUS news](https://www.comp.nus.edu.sg/news/2021-nistchallenge); [Commerce blog](https://www.commerce.gov/news/blog/2021/10/keeping-your-data-safe-differential-privacy-temporal-map-challenge)
- **Tao, McKenna, Hay, Machanavajjhala & Miklau (2021), "Benchmarking DP Synthetic Data Generation Algorithms":** utility was measured on 1-way and 2-way marginals, pairwise correlation and ML classification. The study names the top performers and the algorithms that "consistently fail to beat baseline approaches". Secondary summaries report that marginal-based methods rank highest, with MST first across all metrics (average rank 1.56). — [arXiv 2112.09238](https://arxiv.org/abs/2112.09238); rank figure via [search summary of the ResearchGate copy](https://www.researchgate.net/publication/357171756_Benchmarking_Differentially_Private_Synthetic_Data_Generation_Algorithms). Treat the 1.56 figure as secondary.
- **AIM (McKenna, Mullins, Sheldon & Miklau, PVLDB 15(11):2599-2612, 2022):** workload-adaptive select-measure-generate. It iteratively picks the marginals most useful for both the workload and the data, and it gives analytic high-probability per-query error bounds, which can be turned into confidence intervals. It "outperformed MST convincingly, especially for higher values of epsilon". — [arXiv 2201.12677](https://arxiv.org/pdf/2201.12677); [ACM DL](https://dl.acm.org/doi/abs/10.14778/3551793.3551817)
- **2025 benchmark (arXiv 2504.14061):** at total epsilon 1.0, PrivMRF and AIM achieve the best utility of all methods tested. — [Benchmarking DP Tabular Data Synthesis](https://arxiv.org/pdf/2504.14061)
- **A newer neural method can beat AIM:** on densely correlated datasets, MargNet and AIM are the top two. Utility is nearly identical on Gauss10, and MargNet beats AIM on Gauss30, Gauss50 and PAMAP2 when epsilon is 5 or more. Utility-oriented benchmarks "consistently show that marginal-based models outperform deep generative approaches such as DP-GANs". — [Beyond One-Size-Fits-All (arXiv 2511.13893)](https://arxiv.org/html/2511.13893)
- **ML utility at a given epsilon (PLOS ONE 2024):** at epsilon above 5.0, models trained on synthetic data reached AUC 0.683 (AIM), 0.684 (MWEM-PGM), 0.662 (MST) and 0.668 (PrivBayes), against 0.684 on real data. The authors conclude epsilon = 5 "preserve[s] adequate predictive utility while significantly mitigating privacy risks". — [PLOS ONE / PMC10843030](https://pmc.ncbi.nlm.nih.gov/articles/PMC10843030/)
- **AIM in a real release:** AIM was used for a public release of behavioural-health data with "high utility". — [Aim High, Stay Private (arXiv 2507.02971)](https://arxiv.org/pdf/2507.02971)
- **DP's disparate impact:** DP synthetic data harms minority subgroups ("Robin Hood and Matthew Effects"). — [arXiv 2109.11429](https://arxiv.org/pdf/2109.11429)
- **NIST CRC methods:** the CRC benchmarks MST and AIM (via SmartNoise) against non-DP CART (synthpop), ARF (synthcity), TVAE (SDV), and SDC methods (cell suppression and rank swapping via sdcMicro). It uses NIST ACS Data Excerpts (24 columns, three geographic partitions) and SBO excerpts (130 features, 161K records). — [CRC repo](https://github.com/usnistgov/privacy_collaborative_research_cycle); [Diverse Community Data, arXiv 2306.13216](https://arxiv.org/pdf/2306.13216)
- **CRC 2025 red team:** the attacker knows quasi-identifiers (for example age, city and marital status) of a person known to be in the release, and tries to recover sensitive features (job satisfaction, health, income). — [CRC red team page](https://pages.nist.gov/privacy_collaborative_research_cycle/pages/red_team.html) (page blocked; the description comes from the search snippet)

### Inferences
- For Misata, the default DP fit mode should be AIM, with MST as the fast fallback, both through Private-PGM. DP-GAN or DP-diffusion modes add heavy dependencies and, per every benchmark found, give no tabular-utility advantage at the same epsilon.
- Practical epsilon guidance: epsilon of 1 is the "strong" setting where AIM and PrivMRF lead; epsilon of 3 to 10 is where most published utility parity claims sit (NIST 2020 scored at 10; PLOS ONE found parity at 5 or more). Misata should expose epsilon explicitly with no "magic" default, or default to a documented value such as 1.0 and warn above 10.
- AIM's per-query error bounds are a differentiator. Misata can surface them as confidence intervals in its fidelity report.

### Gaps
- Exact epsilon values for NIST 2018 Match 3 and the per-epsilon scores could not be read (arxiv and NIST pages blocked). I believe Match 3 used several epsilons below 10, but this is unverified.
- Measured marginal-error numbers (for example, average total variation distance at epsilon = 1) from Tao et al. and 2504.14061 could not be extracted. Only rankings are available.
- CRC red-team results (reconstruction rates for MST/AIM versus CART/TVAE) were not accessible.

## 2. Practical libraries, licences, compute and ease of embedding

### Takeaway
The permissive, embeddable options are Private-PGM (`mbi`, Apache-2.0, needs JAX), SmartNoise Synth (MIT, wraps MST/AIM, but pins `mbi<2` and the old `opacus<0.15`), DataSynthesizer (MIT, pure numpy/pandas/sklearn), pgmpy (MIT) and synthcity (Apache-2.0, heavy torch stack). SDV and the `copulas` library are now BUSL-1.1, not open source. Misata's existing `[advanced]` copula path therefore depends on a source-available licence, and an MIT project should replace it with its own small Gaussian copula.

### Cited Findings (versions, licences and dependencies from the PyPI JSON API, fetched 2026-10-04)
| Package | Latest | Licence | Key deps / notes |
|---|---|---|---|
| `smartnoise-synth` | 1.0.8 (uploaded 2026-04-15) | MIT | `mbi<2,>=1.1.0`, `opacus<0.15,>=0.14`, `pac-synth<0.0.9`, `smartnoise-sql`, Faker — [PyPI](https://pypi.org/project/smartnoise-synth/) |
| `mbi` (Private-PGM) | 2.0.0 | Apache-2.0 | numpy, scipy, networkx, **jax/jaxlib >=0.9**, chex, optax — [PyPI](https://pypi.org/project/mbi/) |
| `synthcity` | 0.2.12 | Apache-2.0 | `torch<2.3,>=2.1`, `numpy<2.0`, opacus, nflows, optuna, shap, lifelines, decaf… — [PyPI](https://pypi.org/project/synthcity/) |
| `DataSynthesizer` | 0.1.13 | MIT | numpy, pandas, scikit-learn, matplotlib, seaborn, dateutil — [PyPI](https://pypi.org/project/DataSynthesizer/) |
| `copulas` (SDV) | 0.14.1 | **BUSL-1.1** | numpy, pandas, plotly… — [PyPI](https://pypi.org/project/copulas/) |
| `sdv` | 1.38.5 | **BUSL-1.1** | boto3, graphviz, cloudpickle, … — [PyPI](https://pypi.org/project/sdv/) |
| `sdmetrics` | 0.32.0 | MIT | — [PyPI](https://pypi.org/project/sdmetrics/) |
| `pgmpy` | 1.1.2 | MIT | networkx>=3, numpy>=2, scipy, sklearn, statsmodels, `huggingface_hub`… — [PyPI](https://pypi.org/project/pgmpy/) |
| `mostlyai` (SDK) | 6.1.5 | Apache-2.0 | duckdb, pyarrow, pydantic, … — [PyPI](https://pypi.org/project/mostlyai/) |
| `mostlyai-engine` | 2.7.1 (2026-09-23) | Apache-2.0 | accelerate, datasets, peft, `opacus>=1.6` — [PyPI](https://pypi.org/project/mostlyai-engine/) |
| `opacus` | 1.6.0 | Apache-2.0 | `torch>=2.6` — [PyPI](https://pypi.org/project/opacus/) |

- **SmartNoise Synth contents:** MWEM, MST, QUAIL, DP-CTGAN, PATE-CTGAN, PATE-GAN and AIM. MWEM and MST "require columns to be categorical"; continuous columns must be discretised in a way that "does not reveal information about the distribution of the data". — [SmartNoise synth README](https://github.com/opendp/smartnoise-sdk/blob/main/synth/README.md)
- **Private-PGM (`mbi`) API:** you define a `Domain` of discrete attribute sizes, pass noisy marginal measurements as `LinearMeasurement`s, and call `estimation.MirrorDescent().estimate(domain, measurements)` (the recommended estimator). Dual Averaging and Interior Gradient are alternatives. Extensions include `MixtureOfProductsEstimator` ("scalable, no graphical model") and `ReweightedDatasetEstimator(seed_data=...)`, which produces a weighted dataset. You can draw synthetic rows with `model.synthetic_data(rows=N)` or read back marginals with `model.project(...)`. — [Private-PGM README](https://github.com/ryan112358/private-pgm); [docs](https://private-pgm.readthedocs.io/en/latest/)
- **Dependency conflict:** SmartNoise 1.0.8 pins `mbi<2` while `mbi` 2.0.0 is current, and it pins `opacus<0.15` while opacus 1.6.0 needs `torch>=2.6`. Installing SmartNoise therefore pulls an old opacus/torch chain even if you only want MST or AIM. — [PyPI smartnoise-synth](https://pypi.org/project/smartnoise-synth/), [PyPI opacus](https://pypi.org/project/opacus/)
- **MOSTLY AI DP:** the SDK and the QA metrics library were open-sourced under Apache-2.0 in late 2024. Training can run with DP via DP-SGD; you can set an upper epsilon limit, and training stops automatically when the budget is reached. — [MOSTLY AI DP blog](https://mostly.ai/blog/differentially-private-synthetic-data-with-mostly-ai); [SDK paper, arXiv 2508.00718](https://arxiv.org/html/2508.00718v1)

### Inferences
- **Recommended embedding:** a `misata[dp]` extra that depends on `mbi` directly (Apache-2.0, compatible with MIT) and on a ~200-line in-house implementation of MST and AIM selection. SmartNoise's AIM/MST code is MIT and could be vendored with attribution. This avoids the SmartNoise to opacus 0.14 chain. The JAX dependency is the main cost, at hundreds of MB, so it must remain an optional extra.
- **Non-DP "fit-to-sample" mode:** write an in-house Gaussian copula (numpy/scipy: empirical CDF, normal scores, correlation matrix, sampling). It is about 150 lines and removes the BUSL-1.1 `sdv`/`copulas` dependency from `misata/generators/copula.py`. Under BUSL, production use may be restricted depending on the Additional Use Grant, so an MIT project should not push it on users silently.
- **DataSynthesizer** is the lightest DP Bayesian-network option (pure sklearn/pandas, MIT). The benchmarks above rank PrivBayes-family methods below MST and AIM, though.

### Gaps
- Compute cost measurements (wall-clock and memory for AIM/MST on, for example, Adult at epsilon = 1) were not retrievable. AIM is known to be slower than MST because it runs many PGM estimation rounds, but no measured number was obtained this session.
- The exact Additional Use Grant text of SDV's BUSL-1.1 was not read (docs.sdv.dev blocked).

## 3. Fitting from aggregates only (no row-level data)

### Takeaway
Private-PGM is directly usable with published aggregates: its input is just a list of (noisy) marginals, so published cross-tabs can be fed in as "measurements" with any noise scale, including zero. The model it returns is the maximum-entropy-style graphical model consistent with them. Classic IPF/raking does the same for a seed table and is the established population-synthesis method.

### Cited Findings
- **Private-PGM takes marginal tables, not rows:** `LinearMeasurement(noisy_marginal, ("age","sex"))`, then estimate, then `synthetic_data(rows=...)`. `ReweightedDatasetEstimator(seed_data=...)` reweights a seed dataset to match the measurements, which is effectively raking. — [Private-PGM README](https://github.com/ryan112358/private-pgm)
- **IPF:** IPF (Deming & Stephan, 1940) adjusts contingency tables to match known marginal totals. Given known marginals and a sample from the same population, it produces the constrained maximum-entropy estimate of the full multiway table. It is "the most widely used and mature deterministic method" for allocating individuals to zones in spatial microsimulation. — [Spatial Microsimulation with R, ch. 5](https://spatial-microsim-book.robinlovelace.net/smsimr); [JASSS 18(2):21, "Evaluating the Performance of IPF"](https://www.jasss.org/18/2/21.html); [ETH IVT report ab150](https://ethz.ch/content/dam/ethz/special-interest/baug/ivt/ivt-dam/vpl/reports/101-200/ab150.pdf)
- **Integerisation:** IPF gives fractional weights, and "Truncate, replicate, sample" (TRS) converts them to integer counts of individuals. — [arXiv 1303.5228](https://arxiv.org/pdf/1303.5228)
- **Maximum entropy with cardinality constraints:** a 2026 paper relaxes multi-way cardinality constraints via maximum entropy for synthetic population generation. — [arXiv 2603.22558](https://arxiv.org/pdf/2603.22558)
- **Maximum-entropy calibration of DP synthetic data:** a recent approach post-hoc calibrates DP synthetic data to a workload via maximum-entropy reweighting. — [arXiv 2607.08122](https://arxiv.org/html/2607.08122v2)
- **Latent class models** can produce synthetic data and posterior inferences from DP counts alone. — [arXiv 2201.10545](https://arxiv.org/pdf/2201.10545)

### Inferences
- **"Calibrate from aggregates" for Misata:** the user supplies published cross-tabs (for example a census table of age by region). Misata (a) treats them as zero-noise `LinearMeasurement`s in `mbi` to get a joint model over those columns, or (b) generates its rule-based rows and then rakes them, using IPF weights followed by TRS integerisation or weighted resampling, to match the tables. Option (b) keeps every row produced by Misata's rules, so constraints hold by construction.
- Moment matching for numeric columns (target means, variances and correlations) can be done with a Gaussian copula whose correlation matrix is set directly from the published correlations, so no data is needed.
- If the aggregates themselves are DP releases (for example US Census), the privacy guarantee carries through by post-processing. This should be documented.

### Gaps
- No head-to-head accuracy numbers were found for IPF versus a PGM fit on the same cross-tabs.

## 4. Multi-table: learning parent-child relationships and cardinality under DP

### Takeaway
DP multi-table synthesis is research-grade. The options are PrivLava (SIGMOD 2023, latent-variable graphical models), Alimohammadi et al. 2024 (a wrapper over any single-table DP mechanism that iteratively refines the join to match cross-table marginals while keeping referential integrity), PrivPetal (2025) and PrivBench (SPN-based, PVLDB 2024). ClavaDDPM (NeurIPS 2024) is the strongest non-DP multi-table model. None has a mature, packaged library. For Misata, the practical path is to keep its own FK/cardinality engine and only learn the fan-out distribution (children per parent) and child attributes conditioned on parent attributes, with DP noise added to those histograms.

### Cited Findings
- **PrivLava:** the first DP solution for relational data with foreign keys. Graphical models with latent variables capture inter-table correlation, and are refined by EM with Gaussian noise injected in the M-step. It supports arbitrary FK DAGs and mixed public/private relations, and beats prior DP methods on Census and TPC-H multi-relational aggregate queries. Utility rises with epsilon. — [arXiv 2304.04545](https://arxiv.org/abs/2304.04545); [ACM DOI 10.1145/3589287](https://dx.doi.org/10.1145/3589287)
- **Alimohammadi, Wang, Gulati, Srivastava & Azizan (2024):** works with any existing DP single-table mechanism. It iteratively refines the relationships between individual synthetic tables to minimise error on low-order marginals while maintaining referential integrity. It avoids flattening into a master table, scales to high dimensions, and comes with DP and theoretical utility guarantees. — [arXiv 2405.18670](https://arxiv.org/abs/2405.18670)
- **PrivPetal (2025):** synthesises a flattened relation and decomposes it into base relations, so no join keys need to be generated. It notes that naive flattening produces very high-dimensional tables that are hard to synthesise under DP. — [ACM DL 10.1145/3725341](https://dl.acm.org/doi/10.1145/3725341)
- **PrivBench:** a sum-product-network framework that ensures database-level DP for multi-relation databases with complex references, aimed at benchmark publishing. — [arXiv 2405.01312 / PVLDB](https://dl.acm.org/doi/10.14778/3705829.3705855)
- **ClavaDDPM (NeurIPS 2024, non-DP):** relationship-aware GMM clustering learns latent variables that mediate foreign-key relationships, and the latents propagate across tables into diffusion models. It "significantly outperforms" baselines on long-range dependencies and is competitive on single-table utility. — [NeurIPS 2024 paper](https://proceedings.neurips.cc/paper_files/paper/2024/file/983876577ec81db17ecfae1521df9208-Paper-Conference.pdf); [code](https://github.com/weipang142857/ClavaDDPM)
- **Relational fidelity benchmark:** there is a benchmark of the fidelity and utility of synthetic relational data. — [arXiv 2410.03411](https://arxiv.org/pdf/2410.03411)
- **R2T:** gives instance-optimal truncation for DP queries with foreign keys, which is the standard tool for bounding a single user's contribution via fan-out truncation. — [R2T](https://www.researchgate.net/publication/361247141_R2T_Instance-optimal_Truncation_for_Differentially_Private_Query_Evaluation_with_Foreign_Keys)

### Inferences
- **Proposed Misata design ("DP relational-lite"):**
  1. Choose the privacy unit, the root entity (for example customer).
  2. Clip each parent's child count to a cap K, which bounds sensitivity in the R2T spirit.
  3. Release a noisy histogram of children per parent, optionally conditioned on 1 or 2 parent attributes.
  4. Release noisy 2-way marginals between child attributes and the parent attributes they depend on.
  5. Sample parents from a PGM, sample fan-out from the noisy histogram, sample children from the conditional model, then let Misata's FK and rule engine assign keys.

  Referential integrity then holds by construction, and the total epsilon is the sum (or zCDP composition) of the steps.
- Budget accounting must be per root entity. Because one customer contributes many child rows, the per-row sensitivity used by single-table tools is wrong for child tables unless the fan-out is clipped.

### Gaps
- The quantitative results of PrivLava and Alimohammadi et al. (errors at specific epsilons) were not readable.
- No packaged, maintained DP multi-table library was found. ClavaDDPM's code is research code and is non-DP.

## 5. Hybrid designs: keeping declared constraints, FKs and business rules

### Takeaway
Commercial and open tools use three mechanisms:
- **Reversible transforms** that make a constraint impossible to violate, such as modelling `b - a` as non-negative.
- **Rejection sampling** on an `is_valid` check.
- **Conditional sampling** that fixes some columns first.

SDV tries the transform first and falls back to rejection. Strict inequalities can only be enforced by rejection. For Misata, the cleanest hybrid is "rules first, learned residual": rules and FKs define structure and hard constraints, and the learned model supplies only the joint distribution of the free columns, conditioned on rule-determined columns.

### Cited Findings
- **SDV's constraint strategy:** "transform" is attempted by default, with fallback to "reject_sampling". During rejection, rows are validated with `is_valid`, and invalid rows are re-sampled until the required count is reached. `strict` inequality and range constraints can only be guaranteed with reject sampling. Custom constraints subclass `Constraint` and implement `fit`, `transform`, `reverse_transform` and `is_valid`. Older names were renamed (GreaterThan became Inequality/ScalarInequality, and UniqueCombinations became FixedCombinations). — [SDV 0.18 constraints guide](https://sdv.dev/SDV/developer_guides/sdv/constraints.html); [SDV issue #820](https://github.com/sdv-dev/SDV/issues/820); [SDV 0.16 release notes](https://pypi.org/project/sdv/0.16.0/)
- **SDV conditional sampling and custom constraints:** these historically did not compose. Conditional sampling failed when a `CustomConstraint` was present. — [SDV issue #696](https://github.com/sdv-dev/SDV/issues/696)
- **MOSTLY AI:** its models "can be configured to respect deterministic constraints between features". — [SDK paper, arXiv 2508.00718](https://arxiv.org/html/2508.00718v1)
- **Constrained sampling in general:** sampling constrained continuous distributions (rejection, projection, transformation and constrained MCMC) has been reviewed. — [arXiv 2209.12403](https://arxiv.org/pdf/2209.12403)

### Inferences
- **Recommended Misata pipeline for `fit="sample"` or `fit="dp"`:**
  1. Misata's schema decides tables, keys, cardinalities, derived and formula columns, and hard rules.
  2. The learned model (copula, or PGM via AIM/MST) is fitted only over "free" columns, discretised by Misata's declared bins or domains. Because the domain comes from the schema, the bins are data-independent, which is exactly what SmartNoise requires for DP discretisation.
  3. At sampling time, Misata's rule-fixed columns are passed as evidence (conditional sampling in a PGM is exact by clique propagation).
  4. Remaining hard constraints use a transform where possible (for example `end = start + learned_duration`). Otherwise Misata rejects and resamples with a capped retry count and reports the rejection rate.
  5. Derived and formula columns are recomputed last, so they always hold.
- Rejection is post-processing, so it does not weaken DP. It can, however, distort the learned marginals when the rejection rate is high, so Misata should report a fidelity diff after enforcement.
- Using schema-declared domains, rather than data-derived min/max, is a privacy requirement. Data-derived bounds leak information and silently break DP.

### Gaps
- Gretel's specific constraint mechanism was not found in this session's sources.
- No published measurement was found of how much rejection-based constraint enforcement degrades DP synthetic data fidelity.

## 6. Privacy auditing of the output and pitfalls

### Takeaway
Distance-to-closest-record (DCR) and other similarity metrics give false assurance. Datasets they pass are still highly vulnerable to membership inference. Without DP, higher fidelity means more leakage. Even DP generators can fail audits when they are implemented incorrectly (PATE-GAN). Misata should frame DP (with the epsilon stated) as the guarantee, offer MIA-based auditing as a sanity check only, and never label non-DP fit-to-sample output as "anonymous".

### Cited Findings
- **"The DCR Delusion" (Imperial/UCL, 2025):** DCR and other distance-based metrics "fail to identify privacy leakage". Across datasets and models (BayNet, CTGAN, diffusion), datasets deemed private by proxy metrics are "highly vulnerable" to membership inference, and the metrics are "flawed by design". — [arXiv 2505.01524](https://arxiv.org/pdf/2505.01524)
- **Similarity metrics versus attacks:** the paper "The Inadequacy of Similarity-based Privacy Metrics" mounts attacks against "truly anonymous" synthetic datasets that pass similarity-based checks. — [arXiv 2312.05114](https://arxiv.org/pdf/2312.05114)
- **Synth-MIA (2025):** a testbed of 13 MIAs behind a scikit-learn-like API. Findings: higher synthetic data quality means greater leakage, similarity-based metrics correlate weakly with MIA success, and DP PATE-GAN can fail to preserve privacy under attack. — [arXiv 2509.18014](https://arxiv.org/pdf/2509.18014)
- **PATE-GAN reproduction:** reproducing PATE-GAN surfaced implementation bugs and privacy violations. — [arXiv 2406.13985](https://arxiv.org/pdf/2406.13985)
- **Gen-LRA (no-box MIA):** exploits local overfitting of tabular generators via a surrogate model's local likelihood ratio. — [arXiv 2508.21146](https://arxiv.org/pdf/2508.21146); [OpenReview](https://openreview.net/forum?id=3ya9al7egn)
- **Further attacks:** a MIA via overfitting detection (DOMIAS) — [arXiv 2302.12580](https://arxiv.org/pdf/2302.12580); MIAs without auxiliary data — [arXiv 2307.01701](https://arxiv.org/pdf/2307.01701); ensembled MIAs against tabular generators — [arXiv 2509.05350](https://arxiv.org/pdf/2509.05350)
- **Bugs in DP libraries:** grey-box auditing has found bugs in DP libraries ("Privacy in Theory, Bugs in Practice"). — [arXiv 2602.17454](https://arxiv.org/pdf/2602.17454)
- **Vendor view:** Gretel's own privacy-metrics paper surveys these metrics. — [Steier, arXiv 2501.03941](https://arxiv.org/pdf/2501.03941)
- **Methods, attacks and defences overview:** a KDD 2025 tutorial and survey covers the area. — [arXiv 2506.06108](https://arxiv.org/pdf/2506.06108); [DP tabular synthesis survey, arXiv 2411.03351](https://arxiv.org/pdf/2411.03351)

### Inferences
- **Misata's output and report should:**
  - state the mechanism, the epsilon (and delta) used, the composition across tables, and the privacy unit;
  - mark non-DP copula fits as "not privacy-protecting: may memorise rare records";
  - optionally run a cheap MIA, such as a DOMIAS-style density ratio or one Synth-MIA attack, with a holdout split, and report AUC instead of DCR. Where DCR is reported at all, it should be labelled a necessary-but-not-sufficient memorisation check.
- **Pitfalls to guard in code:**
  - data-derived bounds or bins (leak information and break DP);
  - category vocabularies taken from the data (rare categories leak; take them from the schema or add noise to the counts);
  - child-table sensitivity without fan-out clipping;
  - refitting or tuning hyperparameters on the private data without accounting for it in the budget;
  - telling users that epsilon of 10 or more is "private" without caveat.

### Gaps
- Exact AUC/TPR figures from the DCR Delusion and Synth-MIA papers could not be extracted (arxiv blocked).
- The CRC red-team leaderboard numbers comparing MST/AIM with CART/TVAE were not accessible.
