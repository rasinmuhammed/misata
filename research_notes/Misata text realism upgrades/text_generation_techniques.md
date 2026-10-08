# Techniques for realistic, diverse, coherent free text in synthetic tabular data

Scope note: arxiv.org, aclanthology.org and krishnap25.github.io were blocked by the egress proxy during this research, so paper claims come from search-result abstracts, GitHub READMEs and secondary summaries, not full-text reads. Claims marked "(from memory, unverified)" are things I believe are in the cited work but could not confirm in this session. The report writer should treat them as leads, not facts.

Local context, read from the repo: `misata/microtext.py` (722 lines) holds a `Grammar` class (recursive symbol expansion with `{slot}` filling and sentence capitalisation) and a `MicrotextGenerator` seeded by `np.random.Generator`. Its methods include reviews (conditioned on rating, with the J-shaped star prior p=[.06,.07,.12,.25,.50]), ticket subjects and bodies, resolution notes, error messages, clinical notes, product descriptions and others. Its docstring already notes that a fixed morpheme pool "never mints a new word, so the Heaps exponent stays at zero", and that per-row context slots (e.g. the product name) are the only open vocabulary. I could not measure a baseline for distinct-n or compression ratio because numpy is not installed in this sandbox.

## 1. Template grammars / PCFGs (Tracery-style): how far they go, and how to break the rhythm

### Takeaway
Weighted grammars stay the best fit for a deterministic, vectorized, MIT-licensed core. Readers spot them through repeated openers, a fixed sentence count and repeated POS skeletons. The fixes are structural (sample the discourse plan, then realize it) and statistical (match length and opener distributions to real text). Adding more synonyms does little.

### Cited Findings
- Tracery grammars are JSON objects that are expanded recursively, replacing tokens until none remain. It ships modifiers for capitalization, pluralization, a/an and conjugation, which it calls "common hassles of generative text". — [Compton, Kybartas, Mateas 2015, Tracery paper](http://www.galaxykate.com/pdfs/ComptonKybartasMateas15-Tracery%20An%20Author-Focused%20Generative%20Text%20Tool.pdf); [pytracery (Python port)](https://github.com/aparrish/pytracery)
- Template rhythm can be measured. Shaib et al. (EMNLP 2024) define "syntactic templates" as repeated POS n-gram sequences. On Rotten Tomatoes, 95% of model outputs contained a length-6 template versus 38% of human references. Open-generation template rates were 74.4% ± 2.1, and summarization 96.8% ± 0.6. — [Detection and Measurement of Syntactic Templates in Generated Text (ACL Anthology)](https://aclanthology.org/2024.emnlp-main.368/); [arXiv 2407.00211](https://arxiv.org/abs/2407.00211)
- 76% of templates in model text appear in pre-training data, against 35% for human-authored text. — [same paper](https://aclanthology.org/2024.emnlp-main.368/)
- The `diversity` package (Apache-2.0) implements `extract_patterns()`, `match_patterns()`, `template_rate()` ("fraction of documents in the corpus that contain at least one template") and `templates_per_token()`. Misata could use these as an offline test harness, but should not take them as a runtime dependency. — [cshaib/diversity](https://github.com/cshaib/diversity)

### Inferences (design proposals, not sourced facts)
- **Two-stage generation: plan, then realize.** First sample a discourse plan per row, for example `[complaint_core, context?, attempted_fix?, ask]`, with optional moves included with probability p and the order permuted under constraints. Then expand each move from its own sub-grammar. A sentence count drawn from a fitted distribution, such as a truncated geometric or a negative binomial over 1–6 sentences, removes the most visible tell: every review having three sentences.
- **Opener quotas.** Hash or count the first 2–3 tokens of each output. Cap any opener at a share comparable to real data, for example ≤3–5% (an inferred heuristic, not a sourced number). Do this with weighted sampling without replacement over opener productions within a batch, which works well vectorized (per-batch draws with `rng.choice(..., p=w)` and then reweighting).
- **Length matching.** Fit length (tokens or characters) per column type to a log-normal. Real user text is heavy-tailed, with many 1–5 word reviews and a few long ones. Generate the plan to a target length instead of letting length fall out of the grammar.
- **Register and noise layer.** A post-pass with seeded probabilities: lowercase starts, missing final punctuation, doubled "!!", emoji or ":)" for high ratings, keyboard-adjacent typos (rate ~0.5–2% of tokens), contractions on or off, ALL-CAPS words for angry rows. Keep this per-entity so one persona keeps one register (see section 5).
- **Discourse markers and clause reordering.** Add optional connectives ("Honestly,", "That said,", "Update:") and subordinate clauses that can go before or after the main clause ("Since the update, X" / "X since the update").
- **Open vocabulary.** As the repo docstring notes, fixed pools keep the Heaps exponent at zero. Pull nouns from row entities (product names, cities, features) and from large shipped lexicons such as feature and part nouns per category, so vocabulary grows with N.
- **Agreement.** Tracery-style modifiers (`.a`, `.s`, `.capitalize`, `.ed`) handle English morphology cheaply. For multilingual output, a small inflection table is cheaper than a dependency.

### Gaps
- I found no published study that measures how many productions or how much nesting depth a human needs before template rhythm stops being noticeable.
- I found no sourced "real-data opener share" threshold. Misata should measure it on licensed reference corpora.

## 2. Markov chains / n-gram models on licensed corpora

### Takeaway
Order-2 word chains are cheap, seedable and MIT-friendly (markovify). Their cost is near-verbatim copying, which is both a privacy risk and a licence risk. A novelty filter and corpora that are licensed and PII-free are therefore mandatory. Global coherence is poor, so chains work better as a phrase-level filler inside grammar slots than as a whole-document generator.

### Cited Findings
- markovify (MIT): default `state_size=2`. `make_sentence()` rejects outputs that overlap the source by 15 words or 70% of the sentence (`max_overlap_total`, `max_overlap_ratio`) and makes 10 attempts by default (`tries`). `combine(models, weights)` blends corpora. `.compile()` speeds up generation but blocks further combining. `make_short_sentence(max_chars)` exists. The README says nothing about seeding. — [jsvine/markovify](https://github.com/jsvine/markovify)
- At high order or on small corpora, generation becomes "copy the training text". With a 10,000-token corpus at order 5, most 5-grams occur once, so the chain is effectively deterministic memorization. Lower orders produce verbatim runs with small changes at the joins. — [DEV Community, Markov chain in 200 lines](https://dev.to/sendotltd/text-generation-before-transformers-building-a-markov-chain-in-200-lines-of-python-475o) (secondary/blog source)

### Inferences
- **Seedable and vectorized design.** Compile the chain into CSR arrays: state id → (successor ids, cumulative probabilities). Sampling is then `np.searchsorted(cum[state_ptr], rng.random(batch))`, done for all rows in lockstep. This is deterministic under a `np.random.Generator` and avoids markovify's use of the global `random` module.
- **Privacy controls.** (a) Use only licensed, PII-scrubbed corpora (CC0/CC-BY and public-domain text). (b) Run a novelty check with a rolling hash of every source k-gram (k≈8–12) and reject outputs that contain any of them, similar to markovify's overlap test but quicker. (c) Back off or prune states with fewer than m≥3 distinct successors so that singleton continuations cannot copy text.
- **Size.** An order-2 model over a ~1–5M token domain corpus is plausibly tens of MB uncompressed. Pruning rare states shrinks it. This is an estimate, not measured.

### Gaps
- I found no rigorous paper quantifying the membership-inference or PII-leak rate of n-gram generators against corpus size and order. The privacy argument above is mechanistic, not empirical.

## 3. Small local language models (CPU, offline) vs "generate once, ship a phrase bank"

### Takeaway
Per-row generation with a small LM is too slow and too hard to make deterministic for a vectorized library. Even a 135M model at roughly 20–100 tok/s caps out at a few rows per second. llama.cpp only guarantees bitwise determinism in narrow conditions. The practical pattern is to generate offline once, deduplicate, and ship phrase or sentence banks as data, then recombine them deterministically at runtime. A local LM can stay as an opt-in extra.

### Cited Findings
- SmolLM2-135M-Instruct is about 720 MB at default precision and runs on CPU. One source estimates 10–50 ms per token on CPU, about 20–100 tok/s depending on hardware. This comes from secondary aggregator pages, not a benchmark. — [atomic.chat model page](https://atomic.chat/models/smollm2-135m-instruct); [45Squared CPU LLM overview](https://45squared.com/llms-that-run-on-cpu-only-hardware/); model: [HuggingFaceTB/SmolLM2-135M](https://huggingface.co/HuggingFaceTB/SmolLM2-135M); GGUF quantized builds: [bartowski/SmolLM2-135M-Instruct-GGUF](https://huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF)
- SmolLM2-1.7B reportedly runs at 15–30 tok/s on ARM SBCs or Intel NUCs with 8 GB RAM. — [45Squared](https://45squared.com/llms-that-run-on-cpu-only-hardware/) (secondary)
- llama.cpp determinism: the maintainers do not guarantee bit-identical results when batch size varies. Logits are not reproducible when other sequences share the KV cache or prefill chunking differs. An opt-in deterministic mode (`-DGGML_DETERMINISTIC=ON`, `--deterministic`) makes **CUDA** inference batch-invariant. — [llama.cpp PR #16016](https://github.com/ggml-org/llama.cpp/pull/16016); [drama_llama issue #126](https://github.com/mdegans/drama_llama/issues/126)
- On the CPU backend, the token-input path is bitwise deterministic for identical inputs, but the embedding-input path is not. — [llama.cpp issue #28963](https://github.com/ggml-org/llama.cpp/issues/28963)
- For reproducibility, llama-cpp-python users recommend temperature=0, top_k=1, top_p=1, which kills diversity. — [llama-cpp-python issue #972](https://github.com/abetlen/llama-cpp-python/issues/972)
- ONNX Runtime's transformer optimizer supports GPT-2 and DistilGPT2 export. Its published benchmarks are GPU-focused. I found no CPU tok/s numbers. — [onnxruntime transformers README](https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/python/tools/transformers/README.md)

### Inferences
- **Throughput math.** A 60-token review at ~50 tok/s is about 1.2 s per row, so 1M rows take about 14 days on one core. Grammar generation in pure Python is typically 10^4–10^5 rows/s (estimate; Misata should benchmark). That is a gap of 4–5 orders of magnitude.
- **Determinism.** Seeded sampling with single-sequence, fixed-batch, CPU token-path decoding is reproducible on one machine and build. It is not guaranteed across llama.cpp versions, CPU ISAs (AVX2 vs AVX-512 vs NEON) or thread counts. That breaks the cross-platform reproducibility Misata promises, so LM output should never sit in the default data path.
- **Recommended "vocabulary pack" pipeline (offline, at build time):** (1) For each (domain, column, sentiment or severity bucket, persona facet), prompt a strong model many times with persona or attribute conditioning (sections 5 and 7) and verbalized-sampling-style prompts. (2) Segment the output into sentences or clauses and tag each with slots, for example replacing product mentions with `{subject}`. (3) Deduplicate with exact hashes, MinHash near-dup removal (Jaccard ≥ ~0.8 on word 3-shingles) and an embedding cosine cut (≥ ~0.9). These thresholds are conventional, not sourced. (4) Drop items with names or PII, check the licence of the generating model's terms, and ship the result as compressed JSON or Parquet (a few MB per domain). (5) At runtime, sample deterministically and recombine clauses under the plan grammar from section 1.
- **Optional extra.** `pip install misata[llm]` with llama-cpp-python and a user-downloaded GGUF, used only to grow packs locally. Flag it as a large download (hundreds of MB to GBs) that gets no determinism guarantee.

### Gaps
- I found no first-party, reproducible CPU benchmark of SmolLM2-135M, Qwen2.5-0.5B or DistilGPT2 tok/s. Misata should measure this itself before quoting numbers.
- I did not research the licence terms for shipping LLM-generated text, for example model-output clauses in the Llama, Qwen or Gemma licences.

## 4. Retrieval and recombination from open corpora, with dedup control

### Takeaway
Sentence banks recombined under a discourse plan give real human texture at grammar-level speed. The risks are verbatim reuse of identifiable text and repeated sentences across rows. Both are handled by per-dataset without-replacement sampling plus near-duplicate filtering at build time.

### Cited Findings
- The `diversity` package's `homogenization_score` (ROUGE-L, BLEU or BERTScore), `remote_clique` (mean pairwise cosine distance) and `chamfer_dist` (minimum pairwise distance) can audit a bank or an output batch for redundancy. — [cshaib/diversity](https://github.com/cshaib/diversity)
- PersonaHub's data is CC BY-NC-SA 4.0 and its code is MIT. Its 200k persona preview and 370M "elite personas" (Feb 2025) therefore **cannot** be shipped in an MIT package for commercial users. The README describes no dedup method. — [tencent-ailab/persona-hub](https://github.com/tencent-ailab/persona-hub)
- (From memory, unverified, because arxiv was blocked) The PersonaHub paper deduplicates personas with MinHash (1-gram, signature size 128, threshold 0.9) and then with embedding similarity (text-embedding-3-small, cosine 0.9). — [arXiv 2406.20094 summary on EmergentMind](https://www.emergentmind.com/papers/2406.20094)

### Inferences
- **Runtime dedup for recombined banks.** Keep a per-column "used" bitset and sample without replacement until the bank is exhausted, then reshuffle with a seeded permutation, which is vectorized as `rng.permutation(len(bank))[:n]`. Because the combinatorics of clause recombination (k slots × m variants) are large, exact-duplicate rows stay rare at 10^6 scale.
- **Source choice.** Corpora must be redistributable under MIT-compatible terms (CC0, public domain, CC-BY with attribution in NOTICE). Avoid scraped review datasets with unclear licences (e.g. Amazon or Yelp academic datasets) as shipped data. Use them, at most, as an offline calibration reference for metric targets.

### Gaps
- I did not identify specific CC0 sentence corpora suitable for reviews, tickets or clinical notes. Clinical text in particular is almost never openly licensed.

## 5. Coherence across columns and rows: latent scenarios and personas

### Takeaway
The most effective coherence technique is to sample a latent "scenario" object per row and a "persona" object per entity before generating any column. Every text, categorical and numeric column is then rendered from those latents. That is the persona-conditioning idea from PersonaHub, applied without an LLM.

### Cited Findings
- PersonaHub's core claim is that injecting a persona into a synthesis prompt steers generation toward different perspectives, raising diversity at scale. It builds personas Text-to-Persona (inferred from web text) and Persona-to-Persona (related personas). — [PersonaHub repo](https://github.com/tencent-ailab/persona-hub); [MarkTechPost summary](https://www.marktechpost.com/2024/07/03/this-ai-paper-by-tencent-ai-lab-researchers-introduces-persona-hub-a-collection-of-one-billion-diverse-personas-for-scaling-synthetic-data/)
- Fine-grained persona prompting has been studied for its effect on lexical diversity. — [Measuring Lexical Diversity of Synthetic Data Generated through Fine-Grained Persona Prompting (arXiv 2505.17390)](https://arxiv.org/pdf/2505.17390) (title and abstract only; I could not read the findings)
- Misata already conditions review sentiment on a rating column and injects per-row `subject`, `when` and `agent` slots. — local file `/home/user/misata/misata/microtext.py` (`MicrotextGenerator.reviews`, `_slot_series`)

### Inferences (concrete scheme)
- **Scenario object (per row).** For a support ticket: `issue_type ~ Cat(domain prior)` → `component`, `symptom`, `trigger`, `severity ~ f(issue_type)` → `priority = g(severity, customer_tier)`, `first_response_delay ~ LogNormal(μ(priority))`, `resolution_kind ~ Cat(issue_type)`, `resolved_at = created + Gamma(k, θ(severity))`. Subject, body, category and resolution note are all rendered from the same symptom and component slots, so the text agrees with the structured columns by construction. Vectorize by sampling every latent as a numpy column and grouping rows by `issue_type` for batched grammar expansion.
- **Persona object (per entity, e.g. customer).** Facets include register (formal, casual, terse), verbosity multiplier (scales the length distribution), typo rate, emoji propensity, locale spelling (colour/color), expertise (jargon level), recurring pet product or issue, and sentiment bias (an offset on rating). Derive the persona RNG from `hash(seed, entity_id)` so a customer's bio, reviews and tickets share traits regardless of row order. That gives order-independent determinism.
- **Numeric conditioning.** Map continuous columns onto buckets that select sub-grammars. Rating sets valence. Price bucket sets value-for-money claims ("pricey but", "for the price"). Severity sets urgency markers and caps. Delivery delay sets lateness complaints. Add bucket-boundary jitter, for example a 4-star review that mentions a minor flaw with probability ~0.4, so the mapping is not perfectly separable. Real ratings and text disagree some of the time.
- **Cross-row coherence.** Entity-level memory, such as the last product mentioned or the open ticket's issue, lets follow-up rows refer back ("still seeing the sync error from last week").

### Gaps
- I found no benchmark that scores cross-column text–structure consistency in synthetic relational data. Misata would need its own checks, for example a classifier that predicts the category from text and has to agree with the column.

## 6. Diversity metrics and template-tell detection; what real data shows

### Takeaway
Use a small, low-correlation metric set: gzip compression ratio, POS-template rate, self-repetition of long n-grams, and Self-BLEU (sampled). Add distinct-n and opener concentration as cheap CI gates. Calibrate targets against a licensed human reference of the same genre, because no universal thresholds are published. MAUVE is a heavyweight distributional check (it needs embedding features from a large LM) and belongs in offline evaluation only.

### Cited Findings
- Shaib et al. (2024/2025): compression ratio (output size / gzip size, where higher means more repetitive), self-repetition, n-gram diversity, Self-BLEU and homogenization (BERTScore/ROUGE). They recommend reporting compression ratio, self-repetition of long n-grams and Self-BLEU because these have low mutual correlation. CR correlates moderately to highly with the other n-gram scores, weakly with Self-BLEU and BERT-homogenization, and is fast. — [Standardizing the Measurement of Text Diversity (arXiv 2403.00553)](https://arxiv.org/html/2403.00553v1); [IJCNLP 2025 demo](https://aclanthology.org/2025.ijcnlp-demo.5.pdf)
- Implementations: `pip install diversity` (Apache-2.0) with `compression_ratio`, `ngram_diversity_score`, `self_repetition_score`, `homogenization_score`, `template_rate`, `remote_clique`, `chamfer_dist` and `compute_all_metrics()`. It gives no threshold guidance. — [cshaib/diversity](https://github.com/cshaib/diversity)
- Distinct-n is the number of unique n-grams divided by total n-grams (typically n=2,3). Self-BLEU is the BLEU of each sample against the others, where higher means less diverse. — [Training Language Models on Synthetic Text (NAACL Findings 2024)](https://aclanthology.org/2024.findings-naacl.228.pdf); [arXiv 2311.09807](https://arxiv.org/pdf/2311.09807)
- Template rate for human text is about 38% versus 95% for models (Rotten Tomatoes, n=6 POS templates). This is the most concrete human-vs-generated reference number I found. — [Shaib et al. EMNLP 2024](https://aclanthology.org/2024.emnlp-main.368/)
- MAUVE (Pillutla et al., NeurIPS 2021) compares model and human text distributions through divergence frontiers in a quantized embedding space. It separates Type I errors (text humans would not write) from Type II errors (text humans write that the model misses), and it correlates with human judgments. — [Semantic Scholar entry](https://www.semanticscholar.org/paper/MAUVE:-Measuring-the-Gap-Between-Neural-Text-and-Pillutla-Swayamdipta/8484fdb56e4690927dc0191ede11c2d24bc5e2ef); [Wikipedia: MAUVE](https://en.wikipedia.org/wiki/MAUVE_(metric))
- (From memory, unverified) The `mauve-text` package defaults to GPT-2-large features with k-means quantization, and the authors suggest thousands of samples per side. That makes it a GPU-friendly, large-download dependency. — [arXiv 2102.01454](https://arxiv.org/pdf/2102.01454)

### Inferences
- **Proposed CI gate (pure stdlib plus numpy, deterministic):** for each text generator at N=5,000 rows, check (a) unique-row ratio, (b) gzip CR over the joined batch, (c) distinct-1, 2 and 3, (d) top 3-token opener share and number of openers covering 50% of rows, (e) length mean, SD and skew compared with the target log-normal, (f) the largest repeated 6+-gram share, a self-repetition proxy. Set pass bands from a licensed human reference of the same genre. Sampled Self-BLEU and POS-template rate (which needs a tagger such as spaCy) go in an optional dev-only eval.
- Embedding-based diversity (`remote_clique`) and MAUVE need sentence-transformer or GPT-2 features. Keep them in a dev extra, never a runtime dependency.

### Gaps
- I found no published "real data" values for CR or distinct-n in review or ticket corpora that I could verify. Full papers were blocked. Misata should compute its own reference values.

## 7. Recent research (2023–2026) on diversity collapse in LLM-generated synthetic data, and fixes

### Takeaway
Aligned LLMs collapse onto a few names, settings and phrasings (for example "Elias", "Elara", lighthouses, "Kenji Nakamura"). The research points to typicality bias from preference tuning. Proposed fixes are persona or attribute conditioning, verbalized sampling, and mixing diverse sources. For Misata this argues for building packs offline with explicit attribute grids and never taking names from LLMs. Names should come from frequency-weighted name tables.

### Cited Findings
- Hamilton & Mimno (2026) sampled 20,000 stories from four current models with five prompts. Eleven words appear in 88.3% of stories. "Elias" appears in 26.5%, "Mara" in 16.7% and "Elara" in 13.1%. A lighthouse/Elias/keeper combination appears in 66.6%. The tokens are rare in pre-training data but common in preference data, which implicates alignment. — [arXiv 2605.26492](https://arxiv.org/html/2605.26492); [HF papers page](https://huggingface.co/papers/2605.26492)
- In one persona-generation study, "Kenji Nakamura" made up 40.30% of samples, and LLMs fall back on default demographics and occupations when not explicitly conditioned. — [All too perfect: bias and aspiration in persona generation with LLMs (Springer AIR 2026)](https://link.springer.com/article/10.1007/s10462-026-11641-3)
- Verbalized Sampling (Zhang et al., Oct 2025): typicality bias in preference data drives mode collapse. Asking the model to verbalize a probability distribution over k responses recovers base-model diversity, giving 1.6–2.1× diversity in creative writing, with gains on synthetic data generation and no loss of factuality or safety. Larger models benefit more. — [arXiv 2510.01171](https://arxiv.org/html/2510.01171v3); [CHATS-lab/verbalized-sampling](https://github.com/CHATS-lab/verbalized-sampling)
- Fine-tuning on synthetic data from diverse sources mitigates distribution collapse. — [Synthetic Eggs in Many Baskets (arXiv 2511.01490)](https://arxiv.org/abs/2511.01490)
- Linguistic diversity declines when models are trained recursively on synthetic text. — [The Curious Decline of Linguistic Diversity (arXiv 2311.09807)](https://arxiv.org/pdf/2311.09807)
- LLM name diversity experiments find heavy reuse of a few names. — [HF blog: Name Diversity in LLMs](https://huggingface.co/blog/ChuckMcSneed/name-diversity-in-llms-experiment); [glaforge: The Sci-Fi naming problem](https://glaforge.dev/posts/2025/07/22/the-sci-fi-naming-problem-are-llms-less-creative-than-we-think/) (blogs, secondary)
- LLM-as-a-discriminator work (2026) shows synthetic tables can still be told apart from real ones, and that results depend on the discriminator. — [arXiv 2606.09865](https://arxiv.org/pdf/2606.09865) (abstract-level only)

### Inferences
- **For pack building:** (1) Enumerate an explicit attribute grid (domain × issue × sentiment × persona facets × length bucket) and fill each cell, so the LLM never chooses the topic. (2) Use verbalized-sampling prompts ("give 5 variants with probabilities") and sample by the stated probabilities. (3) Mix 2–3 model families. (4) Strip any proper names the LLM produced and replace them with `{name}` slots filled at runtime from census or frequency name tables. Misata or Faker or Mimesis name data can provide these.
- **Pack lint:** use the 11-word "attractor" check idea from Hamilton & Mimno. Flag any content word whose document frequency in a pack is far above its frequency in a reference corpus.

### Gaps
- I could not read the full text of the persona-prompting lexical-diversity paper (2505.17390) or the Synthetic Eggs paper to extract numbers.
- I did not cover Faker or Mimesis text providers in depth. From general knowledge, Faker's `text`/`sentence` providers use lorem or word-list sampling and do not model coherence, but I did not verify that this session.
