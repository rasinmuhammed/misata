# Synthetic Data Evaluation Metrics and Benchmarks (for a credible Misata public benchmark)

Research note, 2026-10-04. Network caveat: arxiv.org, openreview.net, alphaxiv.org and docs.sdv.dev were blocked by the egress proxy during this research, so many findings come from search-result abstracts/snippets of those primary sources rather than full-text reads. Claims are cited to the primary URL the snippet came from. Numbers not seen in a source are moved to Gaps.

## Fidelity metrics: marginal, pairwise, joint — which are most robust?

### Takeaway
Marginal (KS/TVD) and pairwise (correlation/contingency) scores are cheap, interpretable and standard (SDMetrics Quality Report), but they saturate: generators that score near-perfectly on them are still trivially detectable. Classifier-based detection (C2ST / discriminator AUC, ideal 0.5) is the most discriminating joint test in recent benchmarks; sample-level precision/recall-style metrics (alpha-precision/beta-recall, density/coverage) are popular but a 2025 ICML position paper shows all of them fail basic sanity checks, so they should be reported as secondary, never as headline numbers.

### Cited Findings
- SDMetrics' CardinalityShapeSimilarity returns a KSComplement score (1 - KS statistic) on the per-parent child-count distribution; scores are bounded 1.0 (best) to 0.0 (worst). This shows SDMetrics' convention: marginal fidelity = KSComplement for numeric, TVComplement for categorical, all mapped to [0,1]. — [SDMetrics CardinalityShapeSimilarity](https://docs.sdv.dev/sdmetrics/metrics/metrics-glossary/cardinalityshapesimilarity)
- SDMetrics separates a "Quality Report" (column shapes, column-pair trends, and for multi-table, cardinality and intertable trends) from a "Diagnostic Report" (validity: e.g., referential integrity, boundary adherence). — [SDMetrics Quality Report](https://docs.sdv.dev/sdmetrics/data-metrics/quality/quality-report); [SDMetrics Diagnostic](https://docs.sdv.dev/sdmetrics/data-metrics/diagnostic); [Multi Table API](https://docs.sdv.dev/sdmetrics/reports/quality-report/multi-table-api)
- Alpha-precision, beta-recall and authenticity are "three-dimensional, domain- and model-agnostic" sample-level measures of fidelity, diversity and generalization; alpha-precision = how well synthetic samples fall in the dense support of real data, beta-recall = how much of the real distribution is covered, authenticity = share of genuinely new (non-copied) samples. Shipped in Synthcity. — [Synthcity NeurIPS 2023 D&B paper](https://papers.neurips.cc/paper_files/paper/2023/file/09723c9f291f6056fd1885081859c186-Paper-Datasets_and_Benchmarks.pdf); [synthcity docs](https://synthcity.readthedocs.io/)
- Observed robustness problem: authenticity and beta-recall are strongly negatively correlated ("their sum is nearly constant"), so they should not be used simultaneously as independent axes. — [TabStruct (arXiv 2509.11950)](https://arxiv.org/html/2509.11950v2) (as summarized by search snippet)
- Räisä, van Breugel & van der Schaar (ICML 2025 position paper) designed a suite of sanity checks (Gaussian shifts, outliers, heavy tails, Gaussian-mixture mode collapse, hypercube size/convergence) and found "all of the fidelity and diversity metrics fail a large number of sanity checks, in many cases failing to measure even the basic property they are supposed to measure." Metrics covered include precision/recall, density/coverage, alpha-precision/beta-recall family. — [arXiv 2505.22450](https://arxiv.org/abs/2505.22450); [ICML 2025 poster](https://icml.cc/virtual/2025/poster/40164)
- Follow-up proposes "Clipped Density and Coverage" to fix some failure modes of density/coverage. — [arXiv 2507.01761](https://arxiv.org/pdf/2507.01761)
- Hudovernik et al. (2024) relational benchmark: "No method is able to synthesize a dataset that is indistinguishable from original data" under their robust detection approach — i.e., classifier detection retains discriminative power where statistical scores saturate. — [arXiv 2410.03411](https://arxiv.org/abs/2410.03411)
- NIST SDNist uses a k-marginal edit-distance similarity score (many random 3-way marginal snapshots, averaged density differences), scaled to a maximum of 1000 for identical data, plus pairwise PCA scatterplots and a propensity (real-vs-deidentified classifier) metric. — [Diverse Community Data paper, arXiv 2306.13216](https://arxiv.org/pdf/2306.13216); [example SDNist report](https://pages.nist.gov/privacy_collaborative_research_cycle/select_results/20230314/SynCity/GeneticSD/national2019_genetic_sd_national_03-15-2023/report.html)
- TabSynDex (2022) aggregates basic statistics (mean/median/std), log-transformed correlation, propensity score (logistic regression real-vs-synthetic) and ML utility into one bounded [0,1] score. — [TabSynDex arXiv 2207.05295](https://arxiv.org/pdf/2207.05295)
- SynthEval (2024) provides configurable utility+privacy evaluation of tabular synthetic data (metrics include distribution distances, correlation differences, propensity/detection, DCR/NNDR, MIA-style risk). — [SynthEval arXiv 2404.15821](https://arxiv.org/pdf/2404.15821)

### Inferences
- Recommended headline fidelity stack for a Misata benchmark: (1) per-column KSComplement/TVComplement (SDMetrics-compatible so numbers are comparable to the SDV ecosystem); (2) pairwise correlation/contingency similarity; (3) 3-way k-marginal (NIST-style) for categorical joints; (4) C2ST with a gradient-boosted classifier (report AUC, ideal 0.5, with cross-validation and CIs). Report alpha/beta/density/coverage only as diagnostics, citing the ICML 2025 caveat.
- Single aggregated scores (TabSynDex, SDMetrics overall score) hide failure modes; publish the per-property breakdown.

### Gaps
- No authoritative published threshold for "good enough" KSComplement or C2ST AUC was found; 0.5 AUC is the definitional ideal, and any pass/fail cutoff (e.g., AUC < 0.6) would be a Misata design choice, not literature-provenanced.
- Could not read the full TabStruct or ICML 2025 papers (arXiv blocked) to list exactly which metrics failed which checks.

## Utility: TSTR/TRTS, ML efficacy, query/aggregate error

### Takeaway
TSTR (train on synthetic, test on real) and ML-efficacy are the dominant utility measures in tabular papers, but relational benchmarks find utility and fidelity rank methods differently, so both must be reported. For BI-style workloads, query/aggregate error and NIST-style k-marginal/propensity metrics are the closest standard analogues. For Misata (no real training data), TSTR is only meaningful against a public reference dataset of the same schema.

### Cited Findings
- Hudovernik et al.: utility shows "moderate correlation between real and synthetic data for both model predictive performance and feature importance," and "methods with lower performance on data fidelity sometimes outperform stronger methods on utility" — fidelity and utility are distinct axes. — [arXiv 2410.03411](https://arxiv.org/abs/2410.03411)
- SyntheRela introduces "relational deep learning utility" (training RDL/GNN models over the synthetic database and evaluating on real tasks) as its multi-table utility measure. — [SyntheRela OpenReview](https://openreview.net/forum?id=ZfQofWYn6n)
- SDNist includes two ML task-based metrics (including the propensity metric) alongside k-marginal; the CRC archive publishes each contributed deidentified dataset with its full metrics report in human- and machine-readable form. — [arXiv 2306.13216](https://arxiv.org/pdf/2306.13216); [NIST CRC Data and Metrics Archive](https://catalog.data.gov/dataset/nist-collaborative-research-cycle-data-and-metrics-archive)
- Synthcity covers multiple use cases beyond classification utility (e.g., fairness, augmentation, survival and time-series), framing utility as task-dependent. — [Synthcity NeurIPS 2023](https://papers.neurips.cc/paper_files/paper/2023/file/09723c9f291f6056fd1885081859c186-Paper-Datasets_and_Benchmarks.pdf)

### Inferences
- Misata's main audience (demo/test/load/BI data) cares more about aggregate-query fidelity than classifier accuracy. A credible benchmark should include a fixed SQL query workload (group-by counts, sums, top-k, joins across FK paths, time-bucketed aggregates) with relative error per query, alongside TSTR on one or two standard tasks for comparability with academic tables.
- Feature-importance rank correlation (real vs synthetic-trained model) is a cheap secondary utility measure supported by the Hudovernik findings.

### Gaps
- Found no standardized, widely adopted public "BI query workload" benchmark for synthetic data; this would be a Misata contribution.

## Privacy: DCR, NNDR, MIA, attribute inference, Anonymeter, DP — and DCR pitfalls

### Takeaway
DCR/NNDR are popular but discredited as standalone privacy evidence (2025 "DCR Delusion"); membership inference attacks are the accepted gold standard, and Anonymeter's GDPR-aligned singling-out/linkability/inference attacks are the de-facto practical suite. For Misata, which never sees real data, privacy is trivially satisfied by construction (no training records) — the benchmark should state this and demonstrate it (e.g., zero exact matches with reference data, DCR-holdout share ≈50%), rather than run MIAs that have no member set.

### Cited Findings
- Anonymeter (Giomi et al., PETS 2023) quantifies singling out, linkability and inference risk — "the three key indicators of factual anonymization according to GDPR" — via attack-based evaluation; first to directly model singling-out and linkability attacks. — [arXiv 2211.10459](https://arxiv.org/abs/2211.10459); [anonymeter PyPI](https://pypi.org/project/anonymeter/)
- Anonymeter has been applied at scale to NIST CRC submissions. — [AnonosDev/anonymeter-sdnist](https://github.com/AnonosDev/anonymeter-sdnist)
- Platzer & Reutterer holdout method: for each synthetic record compute distance to closest training record and to an equally sized holdout set; the share of synthetic records closer to training than holdout should be close to 50% — the only DCR-family threshold with clear provenance; ~50% gives "plausible deniability." Most synthesizers studied achieved this; perturbation techniques did not without losing fidelity. — [arXiv 2104.00635](https://arxiv.org/pdf/2104.00635); [Frontiers in Big Data 2021](https://www.frontiersin.org/journals/big-data/articles/10.3389/fdata.2021.679939/full)
- "The DCR Delusion" (2025): DCR and other distance-based metrics fail to identify privacy leakage; datasets deemed private by proxy metrics are highly vulnerable to MIAs across multiple datasets and generators (BayNet, CTGAN, diffusion models). MIAs are "widely considered the gold standard." — [arXiv 2505.01524](https://arxiv.org/abs/2505.01524); [Springer chapter](https://link.springer.com/chapter/10.1007/978-3-032-07884-1_24)
- Distance metrics "by design do not learn and need to make assumptions about what causes privacy leakage"; they miss uniquely-identifying feature values and complex feature combinations. — [arXiv 2505.01524](https://arxiv.org/pdf/2505.01524) (search snippet)
- Survey of synthetic data privacy metrics (2025) catalogues DCR, NNDR, MIA, attribute inference etc. — [arXiv 2501.03941](https://arxiv.org/pdf/2501.03941)
- SDNist Unique Exact Match (UEM): percent of singleton records in the target that appear in the deidentified data. — [arXiv 2306.13216](https://arxiv.org/pdf/2306.13216)
- MIAs are now being extended to multi-table synthetic data. — [arXiv 2602.07126](https://arxiv.org/pdf/2602.07126)

### Inferences
- Misata benchmark privacy section: (a) state the threat model — no real data is ingested, so membership inference has no member set; (b) still report UEM/exact-match rate and holdout-DCR share against any public reference dataset used for comparison, to rebut "it memorized a public dataset" claims (e.g., name/address pools); (c) for any future "fit-to-data" mode, run Anonymeter + an MIA rather than DCR alone.

### Gaps
- Anonymeter's recommended risk thresholds were not verified (paper text unavailable). DP accounting guidance not researched in depth; it is irrelevant to Misata's no-data mode.

## Multi-table and temporal realism metrics

### Takeaway
The multi-table literature converges on: referential integrity (validity), cardinality/fan-out distribution similarity, cross-table (k-hop) correlation, and aggregation-enriched detection (C2ST-Agg/DDA). Temporal benchmarks (Seq2Synth, 2026) show static fidelity does not imply temporal fidelity and add timestamp-validity, per-step and trajectory metrics.

### Cited Findings
- SDMetrics ReferentialIntegrity: proportion of FK values found in the parent PK; 1.0 = no orphans. — [SDMetrics ReferentialIntegrity](https://docs.sdv.dev/sdmetrics/metrics/metrics-glossary/referentialintegrity)
- SDMetrics CardinalityShapeSimilarity: KSComplement of the child-count-per-parent distribution; CardinalityBoundaryAdherence checks child counts fall in real min/max. — [CardinalityShapeSimilarity](https://docs.sdv.dev/sdmetrics/metrics/metrics-glossary/cardinalityshapesimilarity); [CardinalityBoundaryAdherence](https://docs.sdv.dev/sdmetrics/metrics/metrics-glossary/cardinalityboundaryadherence)
- ClavaDDPM (NeurIPS 2024) metrics: (1) cardinality (FK group-size distribution); (2) 1-way column density for all tables; (3) k-hop pairwise column correlation between columns in tables at distance k; (4) "average 2-way" across all k-hop pairs — framed as a "long-range dependency" metric. Reported e.g. +58.29% over best baseline on 2-hop correlations (Instacart 05), +20.24% on 3-hop (Berka). — [ClavaDDPM NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/983876577ec81db17ecfae1521df9208-Paper-Conference.pdf); [arXiv 2405.17724](https://arxiv.org/html/2405.17724v1)
- SyntheRela: single-column (e.g., ChiSquare), single-table (e.g., MMD) and multi-table (Cardinality Shape Similarity, Aggregation Detection) metrics. Its DDA/C2ST-Agg metric enriches parent rows with child aggregates (child count, mean of numeric fields, count of unique categorical values) before training a discriminator. Benchmarks 6 open-source methods on 8 real databases (39 tables); ICLR 2025 workshop; pip install syntherela; public Hugging Face leaderboard with maintainer-run evaluation on fixed hardware (H100, 48h per dataset), one submission per 30 days. — [SyntheRela GitHub](https://github.com/martinjurkovic/syntherela); [OpenReview](https://openreview.net/forum?id=ZfQofWYn6n)
- Seq2Synth (2026): maps time representation, sampling regularity, trajectory dependence and schema structure to four fidelity dimensions — timestamp (temporal violations), cross-sectional (per-time-step distributions), longitudinal (step-level and global trajectory differences), structural (table relationships). Over 13 datasets and 8 generators, "strong static-distribution fidelity does not reliably translate to temporal fidelity", rankings change, and near-perfect static models still produce duplicate timestamps, irregular intervals and incomplete observation grids. — [arXiv 2607.15606](https://arxiv.org/abs/2607.15606)
- A 2026 fraud benchmark reports tabular generators fail to preserve temporal, velocity and multi-account signals. — [arXiv 2604.13125](https://arxiv.org/html/2604.13125v1)
- Temporal-preservation metrics for longitudinal patient data are an active 2026 topic. — [arXiv 2602.10643](https://arxiv.org/pdf/2602.10643)

### Inferences
- Misata's benchmark should be strongest exactly here, since schema-first generation can guarantee constraint validity: report referential integrity, PK uniqueness, boundary/check-constraint adherence and temporal ordering (child timestamp ≥ parent created_at) as hard 100%-or-fail validity checks, then fan-out shape (KS on child counts, plus tail/power-law fit), k-hop correlations, inter-event time distributions, and seasonality (hour-of-day / day-of-week / month spectra) as fidelity scores versus a public reference DB.
- Aggregation-enriched C2ST (SyntheRela DDA) is the toughest published multi-table test; adopting it via the syntherela package would make results directly comparable to the SyntheRela leaderboard.

### Gaps
- Exact list of SyntheRela's 8 databases not confirmed from accessible text (README mentions Rossmann; the literature commonly uses Rossmann, Berka, AirBnB, Walmart, Biodegradability, CORA, IMDB, MovieLens, Instacart — unverified for SyntheRela specifically).

## Text realism metrics (robust and offline-computable)

### Takeaway
MAUVE is the standard reference-based distributional metric but needs an embedding model and reference corpus; for offline, reference-free checks, compression ratio (gzip) is a fast, validated proxy for n-gram homogeneity, alongside distinct-n and self-BLEU. Separate quality from diversity (precision/recall-style) rather than one combined score.

### Cited Findings
- MAUVE measures distributional gap between generated and human text via divergence frontiers in an embedding space; theory and practice expanded in JMLR 2023. — [MAUVE arXiv 2102.01454](https://arxiv.org/pdf/2102.01454); [JMLR 2023](https://www.jmlr.org/papers/volume24/23-0023/23-0023.pdf)
- Distinct-n = fraction of distinct n-grams across all generations; Self-BLEU = BLEU of each generation against all others (lower = more diverse). — [arXiv 2410.06097](https://arxiv.org/pdf/2410.06097) (search snippet)
- Shaib et al. (2024) "Standardizing the Measurement of Text Diversity": gzip compression ratio of concatenated outputs captures information similar to slow n-gram homogenization scores; released a diversity-score package. — [arXiv 2403.00553](https://arxiv.org/abs/2403.00553); [OpenReview](https://openreview.net/forum?id=jvRCirB0Oq)
- ACL 2024 precision/recall for LLMs: recall correlates with Self-BLEU and Distinct-4 (word-level diversity); precision does not, but correlates with MAUVE — two measures distinguish lack of quality vs lack of diversity. — [ACL 2024](https://aclanthology.org/2024.acl-long.616.pdf)
- Machine-generated-text detectors are used as quality/detectability signals. — [arXiv 2502.15654](https://arxiv.org/pdf/2502.15654)
- 2026 work proposes fidelity-diversity metrics specific to text and coherence-aware distributional evaluation. — [arXiv 2607.04563](https://arxiv.org/pdf/2607.04563); [arXiv 2609.34240](https://arxiv.org/html/2609.34240)

### Inferences
- For Misata (template/grammar-generated short fields), reference-free offline set: compression ratio, distinct-1/2/3, self-BLEU on a sample, duplicate rate, length distribution, and Zipf slope of the vocabulary; optional MAUVE against a public corpus (e.g., Amazon reviews) when a GPU/embedding model is available. Classifier detectability (TF-IDF+logistic regression real-vs-synthetic AUC) is offline and cheap.

### Gaps
- No published thresholds for compression ratio or distinct-n that indicate "human-like"; these must be calibrated against a human reference corpus in the benchmark itself.

## Existing benchmark suites, datasets and reporting

### Takeaway
SDMetrics (SDV), Synthcity, SynthEval, SyntheRela and NIST CRC/SDNist are the reference points; NIST CRC is the model for community trust (fixed public data, standardized metrics report per submission, open archive), and SyntheRela is the model for multi-table leaderboards (maintainer-run, fixed compute, rate-limited submissions).

### Cited Findings
- NIST Diverse Communities Data Excerpts: small curated geography and feature set from 2019 ACS PUMS, built as benchmark data for deidentification (NeurIPS 2023 D&B). — [arXiv 2306.13216](https://arxiv.org/pdf/2306.13216); [NeurIPS supplement](https://proceedings.neurips.cc/paper_files/paper/2023/file/a15032f8199511ced4d7a8e2bbb487a5-Supplemental-Datasets_and_Benchmarks.pdf)
- NIST CRC has collected over 350 deidentified instances of the Excerpts since Feb 2023; each is evaluated with a standardized SDNist battery of fidelity, utility and privacy metrics; the Data and Metrics Archive publishes data plus metrics. — [NIST CRC](https://pages.nist.gov/privacy_collaborative_research_cycle/pages/citing.html); [data.gov archive](https://catalog.data.gov/dataset/nist-collaborative-research-cycle-data-and-metrics-archive); [sdnist PyPI](https://pypi.org/project/sdnist/)
- Synthcity: NeurIPS 2023 D&B benchmark framework with fidelity, privacy, utility metrics and multiple modalities. — [Synthcity paper](https://papers.neurips.cc/paper_files/paper/2023/file/09723c9f291f6056fd1885081859c186-Paper-Datasets_and_Benchmarks.pdf)
- 2025 multi-dimensional tabular evaluation framework paper. — [arXiv 2504.01908](https://arxiv.org/html/2504.01908)
- SyntheRela leaderboard and reporting protocol (see multi-table section). — [SyntheRela GitHub](https://github.com/martinjurkovic/syntherela)
- SynDiffix multi- vs single-table comparison uses CRC-style evaluation. — [arXiv 2403.08463](https://arxiv.org/pdf/2403.08463)

### Inferences
- A trusted Misata benchmark should copy: pinned public datasets + checksums, a pip-installable harness, per-run machine-readable JSON + human HTML report (like SDNist), fixed seeds, recorded compute/time, and inclusion of baselines (SDV HMA, ClavaDDPM, Faker/Mimesis-style random) so readers see where a no-data generator sits.

### Gaps
- SDV's own published benchmark ("SDGym") numbers and datasets were not verified in this session.

## Benchmarking a no-real-data generator fairly against fit-to-data models

### Takeaway
No published benchmark specifically addresses "realism without data." The fairest design evaluates Misata on public schemas with public reference data held out entirely (Misata never sees it; fitted models train on a train split), reports validity and detectability on the held-out split, and adds reference-free tells, human Turing tests, and downstream app/BI tests where fitted models have no inherent advantage.

### Cited Findings
- Holdout-based assessment (synthetic vs train vs holdout) is an established framework for fidelity and privacy. — [Platzer & Reutterer](https://www.frontiersin.org/journals/big-data/articles/10.3389/fdata.2021.679939/full)
- Static fidelity rankings differ from temporal-aware rankings, and fidelity and utility rankings diverge — so a single leaderboard axis misleads. — [Seq2Synth](https://arxiv.org/abs/2607.15606); [Hudovernik et al.](https://arxiv.org/abs/2410.03411)
- Even fitted SOTA relational generators remain detectable by robust classifiers. — [arXiv 2410.03411](https://arxiv.org/abs/2410.03411)

### Inferences
- Proposed tracks: (1) Validity track (constraints, RI, temporal order) — reference-free, where schema-first should hit 100%; (2) Reference-free realism track (Misata's 14 tells, text diversity) applied to all generators and to real data as a calibration ceiling; (3) Held-out fidelity track (KS/TV, pairs, k-hop, cardinality, C2ST-Agg) vs real holdout, with Misata in a "zero-shot/prior-only" category and optionally "prior + published aggregate stats" category; (4) Workload track (fixed SQL/BI queries, app integration tests); (5) Human detectability study (blind real-vs-synthetic rows judged by practitioners, report accuracy vs 50%).
- Always report real-vs-real (train vs holdout) as the ceiling for every metric, so scores are interpretable.

### Gaps
- Found no peer-reviewed protocol for human Turing tests on tabular synthetic data with recommended sample sizes; this needs further research or a pre-registered design.
