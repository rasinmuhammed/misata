# Evaluating realism of synthetic free text in tabular data, and of whole synthetic datasets

Scope: metrics that can extend Misata's reference-free realism report (`misata/tells.py`, today 12 tells; the text check `_check_text_templates` fires only on columns with >=200 rows, mean length >=40 chars, all values containing a space, and warns when exact-duplicate share >0.20 or the top three-word opener share >0.10).

Method note: arxiv.org, aclanthology.org and ncbi.nlm.nih.gov were blocked for full-text fetch in this environment, so paper findings come from search-result snippets and project READMEs. To make up for that, I ran a **local calibration** (pure Python + numpy/pandas, no GPU) on real open corpora fetched from GitHub, and compared them with Faker text, a 4-template slot filler, and Misata's own `misata.enrich_text` output. Calibration corpora:
- Women's Clothing E-Commerce Reviews (23k reviews with Title, Review Text, Rating, Department/Class) — [GitHub mirror](https://raw.githubusercontent.com/AFAgarap/ecommerce-reviews-analysis/master/Womens%20Clothing%20E-Commerce%20Reviews.csv)
- AG News test set descriptions (news blurbs, similar in length to product descriptions) — [GitHub mirror](https://raw.githubusercontent.com/mhjabreel/CharCnn_Keras/master/data/ag_news_csv/test.csv)
- TweetEval sentiment test tweets — [cardiffnlp/tweeteval](https://raw.githubusercontent.com/cardiffnlp/tweeteval/main/datasets/sentiment/test_text.txt)
- StackOverflow posts (title + body, used as a stand-in for support tickets) — [kavgan/nlp-in-practice](https://raw.githubusercontent.com/kavgan/nlp-in-practice/master/tf-idf/data/stackoverflow-data-idf.json)
- Goodbooks-10k book titles (short-name column) — [zygmuntz/goodbooks-10k](https://raw.githubusercontent.com/zygmuntz/goodbooks-10k/master/books.csv)

Each corpus was sampled to a fixed n=2000 non-empty values (the metrics depend on sample size, see below). Scripts: `calib.py` and `calib2.py` in the session scratchpad (`/tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/`). Cells labelled "local calibration" below are my own measurements, not published numbers.

## Lexical diversity and template detection (distinct-n, TTR/MTLD, self-BLEU, gzip ratio, skeleton repetition, length shape, Zipf)

### Takeaway
On a fixed sample size, **gzip compression ratio**, **distinct-2/3**, **masked-skeleton duplicate share**, **MinHash near-duplicate share** and **length coefficient of variation** separate real corpora from template text by one to two orders of magnitude. Every real corpus I measured fell inside a narrow band (gzip CR 2.2-2.9, distinct-3 >= 0.72, near-dup <= 0.2% for texts of 8+ tokens). Template and Misata text sat far outside it (gzip CR 15-103, distinct-3 <= 0.015). Faker lorem text is the odd case: it passes every n-gram diversity metric but fails the **Zipf slope** and **vocabulary size** checks, so a Zipf/vocab check is needed to catch "random word salad". Self-BLEU and MTLD add little beyond gzip and distinct-n and cost more.

### Cited Findings
- Shaib et al. ("Standardizing the Measurement of Text Diversity", ACL Anthology 2025 IJCNLP demo, arXiv 2403.00553) recommend **compression ratio** as a fast score that "is sufficient to capture the information in all token/type ratio related alternatives". It is strongly correlated with other diversity scores. **Compression ratio over part-of-speech sequences** is the score that best separates human from model text — [ACL Anthology](https://aclanthology.org/2025.ijcnlp-demo.5/); [arXiv HTML](https://arxiv.org/html/2403.00553v1)
- Reported values (CNN/DM summaries): human reference CR 2.189 / POS-CR 5.179; Llama-2 CR 2.96 / POS-CR 5.627; GPT-4 CR 2.287 / POS-CR 5.376. Higher means more redundant. Compression ratio and Self-BLEU both show model text as less diverse than human text — [arXiv 2403.00553](https://arxiv.org/pdf/2403.00553) (via search snippet)
- The companion `diversity` toolkit implements compression ratio (gzip/xz), homogenization (ROUGE-L/BLEU/BERTScore), n-gram diversity, self-repetition, POS-pattern "template rate" and "templates per token", and embedding "remote clique" (average pairwise cosine distance) and Chamfer distance (sensitive to near-duplicates). Core deps are numpy, nltk and scikit-learn; embeddings need sentence-transformers and torch — [cshaib/diversity on GitHub](https://github.com/cshaib/diversity)
- **Local calibration, n=2000 values per corpus** (d-n = distinct n-grams / total n-grams over the concatenated sample; gzip CR = raw bytes / gzip-9 bytes of newline-joined sample; skel_dup = share of rows whose skeleton duplicates an earlier row, after masking numbers to `#`, emails to `@E`, and every non-stopword to `W`; near_dup = share of rows with a MinHash-LSH partner at word-5-shingle Jaccard >= 0.8; zipf = slope of log-frequency vs log-rank over the top 1000 words):

| corpus | mean tokens | len CV | d1 | d2 | d3 | gzip CR | MTLD | exact dup | top 3-word opener | top-10 openers | skel dup | near dup | Zipf slope | vocab |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| real: clothing reviews | 61.2 | 0.47 | .041 | .347 | .718 | 2.92 | 86 | 0.000 | .038 | .202 | 0.000 | .001 | -1.15 | 5052 |
| real: clothing review titles | 3.4 | 0.54 | .179 | .654 | .899 | 2.72 | 113 | 0.136 | .009 | .043 | 0.635 | .176 | -1.13 | 1221 |
| real: AG News descriptions | 32.3 | 0.34 | .164 | .680 | .914 | 2.38 | 298 | 0.000 | .018 | .061 | 0.000 | .002 | -0.85 | 10562 |
| real: tweets | 15.0 | 0.37 | .237 | .783 | .958 | 2.16 | 355 | 0.000 | .042 | .064 | 0.002 | .002 | -0.88 | 7115 |
| real: StackOverflow bodies | 82.9 | 0.29 | .087 | .527 | .830 | 2.55 | 57 | 0.000 | .074 | .274 | 0.000 | .000 | -1.00 | 14367 |
| real: StackOverflow titles | 8.8 | 0.42 | .222 | .782 | .957 | 2.33 | 258 | 0.000 | .016 | .078 | 0.160 | .000 | -0.90 | 3913 |
| real: book titles | 5.6 | 0.60 | .316 | .789 | .932 | 2.29 | 112 | 0.002 | .002 | .016 | 0.521 | .008 | -0.78 | 3541 |
| synth: Faker paragraph | 19.3 | 0.32 | .025 | .981 | 1.000 | 2.76 | 665 | 0.000 | .000 | .005 | 0.224 | .000 | **-0.14** | **971** |
| synth: 4 templates x slots | 11.2 | 0.12 | .002 | .007 | .015 | 14.98 | 27 | 0.530 | .260 | .652 | 0.996 | .530 | -0.60 | 39 |
| Misata `enrich_text` customer_feedback | 15.2 | 0.09 | .005 | .006 | .006 | 52.4 | 81 | 0.994 | .098 | .848 | 0.994 | .994 | -0.38 | 144 |
| Misata product_description | 14.3 | 0.08 | .002 | .002 | .002 | 103.4 | 39 | 0.998 | .274 | 1.000 | 0.998 | .998 | -0.30 | 49 |
| Misata resolution_notes | 16.1 | 0.15 | .006 | .007 | .008 | 49.8 | 95 | 0.992 | .076 | .694 | 0.992 | .993 | -0.40 | 187 |
| Misata ticket_subject | 7.8 | 0.11 | .011 | .012 | .012 | 24.7 | 96 | 0.988 | .049 | .439 | 0.988 | .988 | -0.31 | 165 |
| Misata clinical_notes | 27.3 | 0.11 | .003 | .004 | .004 | 82.7 | 112 | 0.996 | .138 | 1.000 | 0.996 | .993 | -0.36 | 175 |

  — local calibration on the corpora listed above
- In the same run, `misata.enrich_text(pd.Series([""]*2000), text_type=..., seed=1)` returned only **12 distinct strings** for `customer_feedback` and **4** for `product_description`; the top product description filled 547 of 2000 rows. Input of `None` behaved the same way — local calibration
- **Sample-size dependence** (clothing reviews): distinct-2 was 0.620 / 0.507 / 0.432 / 0.354 at n = 200 / 500 / 1000 / 2000, while gzip CR was 2.71 / 2.84 / 2.87 / 2.90. Distinct-n must be computed on a fixed-size sample, or a fixed token budget, to have stable thresholds. gzip CR is nearly size-invariant above about 500 rows — local calibration
- **MinHash LSH cost:** 64 permutations, 16 bands, word-5-shingles, on 2000 rows took 0.1-0.3 s per column in numpy/pure Python — local calibration

### Inferences
- **The current `text_templates` gate is too narrow.** Mean length >=40 chars and "every value contains a space" excludes short columns such as ticket subjects (Misata's are about 7.8 tokens). It also excludes any column with one single-word value. The opener test (top opener >0.10) missed Misata `customer_feedback` (0.098) and `ticket_subject` (0.049), even though 99% of their rows are exact duplicates. Those columns are caught only by the duplicate rule.
- **Real-data bands for texts of 8+ tokens** (all five real long-text corpora): gzip CR <= 2.95; distinct-3 >= 0.71 at n=2000; skeleton-dup <= 0.16 (StackOverflow titles reach 0.16, long texts are about 0); near-dup <= 0.002; length CV >= 0.29; top-10 opener share <= 0.28; Zipf slope between -0.78 and -1.15. Synthetic template text lies 5x to 50x outside these bands, so thresholds can sit well inside the gap: for example WARN at gzip CR > 4, d3 < 0.5, near-dup > 0.05, skeleton-dup > 0.30 for texts of 8+ tokens, and length CV < 0.15.
- **Short name-like columns (titles, 3-6 tokens) must be gated out of skeleton and opener checks.** Real review titles have 13.6% exact duplicates and 63% skeleton duplicates, because "Love it!" and "Great dress" really do repeat. Book titles have 52% skeleton duplicates. Use a median-token gate of at least 8 for skeleton and near-dup checks, and keep the exact-dup threshold at 0.2 or above for short columns.
- **Faker/lorem detection** needs a lexical-naturalness check. A Zipf slope flatter than -0.5, or a vocabulary below about 1500 types over 2000 rows of 15+ tokens, flags it. A stopword-share check (real English text is about 40-50% function words) would likely work too, but I did not calibrate it.
- MTLD did not separate cleanly. Misata `clinical_notes` scored 112, inside the real range of 57-355, because MTLD measures within-text diversity and misses cross-row repetition. Self-BLEU is O(n²) and correlated with gzip CR, per Shaib et al. Both are low-value additions.
- POS-sequence compression (the best human-vs-LLM separator in Shaib et al.) needs a POS tagger, so it requires an extra (nltk or spaCy). It suits a later "LLM text" tier, because simple templates are already caught by word-level gzip.

### Gaps
- I could not generate LLM-written synthetic rows (for example GPT- or Claude-written reviews) to calibrate. LLM text likely passes the gzip and distinct-n bands. The only numbers I have for it are Shaib et al.'s summarization numbers (GPT-4 CR 2.287 vs human 2.189), which show a small gap. Template detection and LLM-text detection are different problems.
- I found no published per-domain thresholds for distinct-n or gzip CR on support tickets or product descriptions. The bands above come from my own five-corpus run.
- I did not calibrate POS-template rate or stopword ratio.

## Semantic checks (embedding diversity, near-duplicates, cross-column consistency, sentiment vs rating)

### Takeaway
The highest-value semantic checks are **cross-column agreement tests**, and they run on CPU with no heavy dependencies: sentiment vs rating, title vs body word overlap, and whether text predicts category. They catch the most common tell of template generators: text drawn independently of the row it sits in. Measured against a within-column shuffle baseline, real data shows strong agreement on all three. Embedding diversity and NLI are optional extras.

### Cited Findings
- **Sentiment vs rating, real reviews (n=3000):** VADER compound score vs star rating gives Spearman 0.436. The AUC for separating 4-5 star from 1-2 star reviews is 0.838. Mean compound by rating is 1★ 0.24, 2★ 0.39, 3★ 0.54, 4★ 0.77, 5★ 0.87, so it rises monotonically. VADER is a pure-Python, lexicon-based package (`vaderSentiment`, about 1 MB, no model download) — local calibration; [vaderSentiment on PyPI](https://pypi.org/project/vaderSentiment/)
- **Title vs body overlap, real reviews:** mean share of title content words (3+ letters) that also appear in the body is 0.403 for real pairs vs 0.097 after shuffling bodies, with AUC 0.744 — local calibration
- **Category vs text, real reviews:** the singular class word (for example "dress", "sweater") appears in 22.8% of real review texts vs 5.1% after shuffling. A naive Bayes classifier trained in-sample on 2000 rows and tested on 1000 predicted Department Name with 0.761 accuracy against a 0.438 majority baseline. After shuffling the labels, accuracy dropped to 0.398, below the majority baseline — local calibration
- SDMetrics "mostly focuses on unimodal data types and evaluates univariate column shapes and selected pairwise trends among structured variables". Text metrics such as BERTScore and MAUVE "evaluate text without conditioning on tabular attributes in the same record, so they do not test row-level cross-modal consistency" — [arXiv 2609.22149, "Beyond the Stitching Assumption"](https://arxiv.org/html/2609.22149)
- The `diversity` toolkit's embedding metrics, remote clique (mean pairwise cosine distance) and Chamfer distance (mean nearest-neighbour distance, sensitive to near-duplicates), need sentence-transformers and torch — [cshaib/diversity](https://github.com/cshaib/diversity)

### Inferences
- **Recommended reference-free cross-column check, `text_context_agreement`:** for a text column T and a categorical column C in the same table, compute a self-supervised score: the naive Bayes or TF-IDF nearest-centroid accuracy of predicting C from T on a held-out split, divided by the majority baseline, minus the same ratio after shuffling. If text carries no information about its row's category (lift ≈ 0), WARN, provided C plausibly relates to T. Real data gave a lift of about 1.74x vs about 0.92x when shuffled. This is about 40 lines of numpy plus Counter, with no dependencies. To limit false positives, run it only on (text, category) pairs whose names suggest a link (product/category, ticket subject/queue, review/rating), or report it as INFO.
- **`sentiment_rating`:** when a table has a review-like text column and an ordinal rating column (1-5 or 1-10), compute Spearman(VADER, rating). Real data gave 0.44. WARN if rho < 0.10, or if the mean sentiment by rating is non-monotonic. This needs `vaderSentiment` as an optional extra, or a small vendored positive/negative word list (a vendored list would be weaker; not calibrated).
- **`subject_body_overlap`:** for subject/title + body/description pairs, compare mean overlap with a within-table shuffle. Real data gave a 4x ratio (0.40 vs 0.10). WARN if the ratio is < 1.5. No dependencies.
- **Near-duplicates:** MinHash LSH in numpy, or the `datasketch` package as an optional extra, at 0.1-0.3 s per 2000 rows. SimHash is an alternative with a similar cost. I did not benchmark it separately.
- **Embedding diversity and NLI** (for example, does the description entail the category, using a small MNLI model) need torch plus a model download of hundreds of MB. They should be an opt-in `misata[text-eval]` extra, not part of the default report.

### Gaps
- No published source gives typical sentiment-rating correlations across review datasets. 0.44 is from one dataset and one lexicon.
- I did not benchmark small NLI models or embedding pairwise-cosine values on real vs template text, so no CPU timing or threshold for those.
- A bug in the shuffled-rating Spearman baseline (index misalignment in my script) made that one number unreliable. The shuffled baselines for title overlap and category prediction were computed correctly.

## Reference-based metrics when real data exists (MAUVE, Fréchet embedding distance, classifier two-sample tests, LLM-as-judge)

### Takeaway
With real data available, MAUVE (an embedding-quantized divergence) and classifier two-sample tests are the established distributional measures, but both need an embedding model or a trained classifier. The cheapest useful version is a **TF-IDF + logistic-regression real-vs-synthetic classifier AUC** (scikit-learn only). LLM-as-judge realism scoring is biased toward familiar, low-perplexity text, so it is unreliable for judging LLM-generated data and should never be the sole gate.

### Cited Findings
- MAUVE compares a model's text distribution with human text using divergence frontiers, computed "in a quantized embedding space" (k-means over embeddings, then KL-based frontier) — [MAUVE, arXiv 2102.01454](https://arxiv.org/abs/2102.01454)
- MAUVE's correlations with human judgments are 0.857 for human-like, 0.714 for interesting and 0.762 for sensible. Generation perplexity scores 0.810 / 0.643 / 0.738 — [MAUVE paper (HTML)](https://arxiv.org/html/2102.01454v3)
- A follow-up JMLR paper covers MAUVE's theory and practical estimation choices (quantization, embedding model) — [MAUVE Scores for Generative Models: Theory and Practice](https://arxiv.org/pdf/2212.14578)
- LLM judges show **self-preference bias**: GPT-4 shows the highest among the models studied. LLMs give significantly higher scores to lower-perplexity texts than human evaluators do, whether or not the text is self-generated, which suggests familiarity is the root cause — [Wataoka et al., arXiv 2410.21819](https://arxiv.org/pdf/2410.21819)
- A 2026 paper finds that labels saying who wrote a text ("self" vs "other") cause bias in both directions in LLM judges — [arXiv 2608.18091](https://arxiv.org/abs/2608.18091)
- "LLM-as-a-Discriminator: When Synthetic Tables Still Look Real" (2026) studies LLMs as discriminators of synthetic tabular releases, with the table alone and with the table plus distributional metadata. It notes that existing metrics "do not capture whether a human or AI observer can directly distinguish a synthetic table from a real one" — [arXiv 2606.09865](https://arxiv.org/html/2606.09865v1) (search snippet only; full text blocked, so I have no accuracy figures)
- Cross-table synthetic-data detection (training detectors that generalize across tables) is an active area — [arXiv 2412.13227](https://arxiv.org/pdf/2412.13227)

### Inferences
- **A dependency-light reference-based tier for Misata:** (1) a classifier two-sample test, using TF-IDF word 1-2-grams + logistic regression with 5-fold cross-validation, reporting AUC (0.5 = indistinguishable; above about 0.8 = easily told apart). This needs scikit-learn, CPU only, seconds per column. (2) A "band match": compute the reference-free metrics above on both real and synthetic data and report the ratio, for example gzip CR synthetic/real and d3 synthetic/real. (3) MAUVE or Fréchet distance on sentence embeddings, only behind an optional `[text-eval]` extra (needs `mauve-text` plus torch and an embedding model).
- **LLM-as-judge** should only be an opt-in, advisory signal: use blinded pairs with randomized order, and use a judge from a different model family than the generator, given the self-preference and perplexity bias findings.

### Gaps
- I could not retrieve accuracy numbers from the LLM-as-a-Discriminator paper, or Fréchet-distance-on-text benchmarks, because full text was blocked.
- I did not measure classifier two-sample AUC values for template vs real text in this run.

## Whole-dataset realism practices beyond Misata (cross-table, temporal, human evaluation, how SDMetrics/Synthcity/benchmarks handle text)

### Takeaway
Mainstream tabular benchmarks (SDMetrics, Synthcity, SynthEval) do not evaluate free-text columns in any meaningful way. Text is treated as a categorical column or ignored, and row-level text-to-attribute consistency is untested. For whole datasets, the established practices are statistical similarity reports (SDMetrics Quality and Diagnostic reports, which work across tables), detection metrics (a classifier distinguishes real from synthetic), domain validity measures (Synthea was checked against clinical quality measures), and expert Turing-style blinded reviews.

### Cited Findings
- SDMetrics is model-agnostic and compares real vs synthetic data for quality and privacy. Its Quality Report measures statistical similarity — [SDMetrics GitHub](https://github.com/sdv-dev/SDMetrics); [Quality Report docs](https://docs.sdv.dev/sdmetrics/data-metrics/quality/quality-report)
- SDV's multi-table data quality covers column shapes, column-pair trends, cardinality and inter-table trends — [SDV multi-table data quality](https://docs.sdv.dev/sdv/multi-table-data/evaluation/data-quality)
- SDMetrics is described as the only package that supports multi-table evaluation, with a focus on structural metrics. Synthcity offers 25+ statistical, privacy and detection metrics but nothing text-specific — [Benchmarking the Fidelity and Utility of Synthetic Relational Data, arXiv 2410.03411](https://arxiv.org/pdf/2410.03411); [Synthcity GitHub](https://github.com/vanderschaarlab/synthcity)
- SynthEval is a framework for utility and privacy evaluation of tabular synthetic data — [arXiv 2404.15821](https://arxiv.org/pdf/2404.15821)
- Text-specific synthetic-data evaluation is emerging separately: SynthTextEval targets high-stakes domains — [arXiv 2507.07229](https://arxiv.org/pdf/2507.07229). Work on reference-free evaluation of multi-system business data is also appearing — [arXiv 2609.11286](https://arxiv.org/pdf/2609.11286)
- Synthea was validated using clinical quality measures. Separately, interviews with medical doctors found individual Synthea records "somewhat realistic". Turing tests, in which a field expert tries to tell simulation output from real data, have been part of Synthea validation work — [BMC Med Inform Decis Mak 2019](https://bmcmedinformdecismak.biomedcentral.com/articles/10.1186/s12911-019-0793-0); [WPI "Validation of Synthea"](https://digital.wpi.edu/downloads/4f16c426t?locale=en)
- "Synthetic Hospital" (2026) describes itself as an open, verifiable, physician-validated longitudinal EHR benchmark — [arXiv 2609.30027](https://arxiv.org/html/2609.30027v1) (title and snippet only; protocol details not retrieved)

### Inferences
- **Dataset-level checks Misata could add without reference data:** (a) cross-table temporal ordering (a child's timestamps fall after the parent's created_at, for example order after signup, ticket resolution after open), reported as the share of violations; (b) cross-table text-to-attribute agreement (does a ticket body mention the product the FK points to); (c) joint plausibility across a join (for example, the correlation between order value and customer tier carries through the join); (d) text "staleness" (the same text across many parent entities, using near-dup clusters across FK groups).
- **A human-evaluation protocol, adapted from the Turing-style practice used for Synthea:** mix k real and k synthetic rows (for example 20+20) with identical columns, have 3+ domain raters label each as real or synthetic, and report accuracy with a binomial CI and inter-rater kappa. Accuracy near 50% means the data is indistinguishable. This is cheap to document as a recipe even without automation.

### Gaps
- I could not retrieve the quantitative Synthea results (which measures matched or missed and by how much) or the Synthetic Hospital physician-validation protocol, because the PMC and arXiv full texts were blocked.
- I found no evidence on how TabArena handles text columns. It appears to be a predictive benchmark rather than a synthetic-data benchmark, but I could not verify this.

## Recommendation: which 4-6 text checks to add first, with calibrated thresholds

### Takeaway
Replace the single `text_templates` check with five cheap, dependency-free checks plus one optional-extra check. Every threshold below sits well outside all seven real corpora measured. Misata's own `enrich_text` output (4-12 distinct strings per 2000 rows) and a 4-template slot filler would fail four or more of them.

### Cited Findings
- Shaib et al. recommend compression ratio as the first-line diversity score, cheap and correlated with the rest — [ACL Anthology](https://aclanthology.org/2025.ijcnlp-demo.5/)
- Calibration bands are from the local measurements in the first section; real-data AUC and correlation values are from the second section — local calibration

### Inferences
Proposed checks. Gate all of them with "≥200 non-null rows and median length ≥3 tokens". Sample a fixed 2000 rows, or all rows if fewer, with a fixed seed. If fewer than 2000 rows are available, loosen the d3 thresholds, because d-n rises at small n.

1. **`text_compressibility`** (gzip CR of the newline-joined sample; uses stdlib `gzip`, O(n), milliseconds). Real range 2.2-2.9. WARN > 4.0. Template text scored 15-103.
2. **`text_ngram_diversity`** (distinct-3 over the sample; stdlib, O(tokens)). Real range ≥ 0.72 for long texts, ≥ 0.90 for short ones. WARN < 0.40. Template text scored ≤ 0.015. Report distinct-1 and distinct-2 as evidence.
3. **`text_skeleton_repetition`** (mask numbers, emails and non-stopwords, then take the share of duplicate skeletons; stdlib regex). Gate: median ≥ 8 tokens. Real range ≤ 0.16. WARN > 0.35. Template text scored 0.99. This catches "same sentence, different noun" generators that pass exact-dup checks.
4. **`text_near_duplicates`** (MinHash LSH, word 5-shingles, Jaccard ≥ 0.8; numpy, about 0.2 s). Gate: median ≥ 8 tokens. Real range ≤ 0.002. WARN > 0.05. Keep the existing exact-dup rule (> 0.2) for all lengths.
5. **`text_length_shape`** (CV of token length). Real range 0.29-0.60. WARN < 0.15. Template text scored 0.08-0.15. Optionally add the Zipf slope: WARN if flatter than -0.5 for columns of median ≥ 10 tokens, which catches Faker lorem (-0.14).
6. **`text_context_agreement`** (cross-column; zero dependencies for the NB/overlap variants, `vaderSentiment` optional for sentiment). (a) Rating column present: Spearman(sentiment, rating), real 0.44, WARN < 0.10. (b) Title/body pair: overlap ratio vs shuffle, real 4x, WARN < 1.5x. (c) Category column: NB accuracy lift over the majority baseline, real 1.74x vs 0.92x shuffled, WARN when below the shuffle baseline + 0.1. Start (c) as INFO until it has been tested on more schemas.
- Keep the three-word opener metric as evidence, but switch from the top-1 to a **top-10 opener share** with WARN > 0.5. Real values ranged up to 0.27 (StackOverflow bodies), and top-1 missed Misata output at 0.049-0.098.
- **Product implication:** the calibration shows Misata's own rule-based text generator (`enrich_text`) would fail these checks badly: 4-12 unique strings across 2000 rows. Shipping stricter checks will flag Misata's own default output. Either improve the generator alongside the checks (slot filling plus combinatorial clause assembly, aiming for distinct-3 > 0.5 and gzip CR < 4), or document this as expected.
- Optional extras tier (`misata[text-eval]`): POS-sequence compression ratio (nltk), embedding remote-clique diversity and NLI consistency (sentence-transformers/torch), MAUVE (`mauve-text`), and a TF-IDF classifier two-sample AUC when reference data is supplied (scikit-learn).

### Gaps
- Thresholds come from seven real English corpora and simple synthetic baselines. They are not yet validated on non-English text, on very domain-specific codes or notes (for example clinical shorthand, which can be legitimately repetitive), or against LLM-generated rows.
- False-positive rates on real columns such as "status notes" or "error messages" (legitimately templated system logs) are unknown. These need a name-based exemption or an INFO level.
