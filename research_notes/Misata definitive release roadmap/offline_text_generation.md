# Offline, deterministic, LLM-free text generation for a Python synthetic data library

Scope note: research ran under a ~15-tool-call budget. huggingface.co, yelpcdn.com and mattmahoney.net were blocked by the egress proxy, so some model-card and licence facts come from search-result snippets, not full-page reads. Those are flagged where it matters.

## 1. Compositional grammars and phrase banks: how large do they need to be?

### Takeaway
The data-to-text literature consistently finds that templates give perfect content fidelity but low lexical diversity. I found no published "N templates/phrases gives X diversity" scaling result. Size targets for phrase banks therefore have to be set empirically, using a compression-ratio or distinct-n target measured against real text.

### Cited Findings
- E2E NLG Challenge (restaurant descriptions from key-value meaning representations): Puzikov & Gurevych found a neural encoder-decoder produced fluent output, but "the task can be approached with a template-based model developed in just a few hours." — [ACL Anthology W18-6557](https://aclanthology.org/W18-6557/)
- The E2E dataset itself has "a fixed number of unique MR attributes and low diversity of the lexical instantiations of the MR attribute values," which explains why templates scored well there. — [Puzikov & Gurevych 2018, PDF](https://aclanthology.org/W18-6557.pdf)
- General finding in the data-to-text literature: template systems "can assure perfect content and linguistic quality" but "often suffer from low diversity," while neural models can generalise beyond their training templates. — [Jagfeld et al., Seq2seq word vs character & output diversity, arXiv 1810.04864](https://arxiv.org/pdf/1810.04864); [E2E challenge evaluation, arXiv 1901.07931](https://arxiv.org/pdf/1901.07931)
- A 2024 systematic review of data-to-text NLG covers the template-vs-neural trade-off. — [arXiv 2402.08496](https://arxiv.org/pdf/2402.08496)
- Reference point for real text: gzip typically reduces English text by 60-70% (about 2.5-3.3x), and by about 72% at level 9. — [GNU gzip manual](http://www.gnu.org/s/gzip/manual/gzip.html); [dev-toolbox gzip levels](https://www.dev-toolbox.tech/tools/gzip-size-calculator/examples/compression-levels-explained). Benchmark corpora: [enwik8/enwik9 description](https://mattmahoney.net/dc/textdata.html), [Large Text Compression Benchmark](https://mattmahoney.net/dc/text.html). The site was blocked, so exact gzip byte counts were not retrieved.

### Inferences
- gzip's window is 32 KB, so the compression ratio of a generated column mostly measures how often the same 3+ byte substrings repeat within about 32 KB. A grammar produces repeats in three ways: a fixed skeleton, a small closed-class connective set, and small slot pools. Going from 4-5x to under 3x means cutting long verbatim repeats (shared multi-word spans of 4 or more words) more than adding vocabulary.
- Practical levers, ranked by expected effect:
  1. Many skeletons with recursive optional clauses, so that no single skeleton dominates any 32 KB window.
  2. Paraphrase alternatives at the phrase level rather than the sentence level, which gives a multiplicative combinatorial space.
  3. Zipf-weighted slot pools (realistic repetition) instead of uniform pools.
  4. Morphological and orthographic noise: typos, casing, punctuation variance, contractions.
  5. Variable length, following a heavy-tailed distribution.
- Because gzip ratio is sensitive to length and to the ordering of rows, a regression test should fix the row count and the concatenation scheme before comparing against a real-text baseline.

### Gaps
- No primary source found for Tracery or SimpleNLG diversity measurements, or for quantitative "phrase-bank size vs distinct-n / compression" curves. Templates-vs-neural diversity comparisons are qualitative or use BLEU/distinct-n on E2E, not gzip ratio.
- Exact gzip ratios on enwik8/9 were not retrieved (site blocked). A local measurement on a licence-clean corpus would settle the "under 3x" target.

## 2. Statistical LMs: n-gram/Markov with Kneser-Ney, slot-conditioned; hybrid template + infill

### Takeaway
Modified Kneser-Ney n-gram models are mature and fast. However, the reference toolkit (KenLM) is LGPL-2.1, and n-gram sampling is locally fluent but drifts globally. The realistic design is a template skeleton plus short n-gram infill spans, with a pure-Python or NumPy sampler over a pruned, shipped count table.

### Cited Findings
- KenLM implements modified Kneser-Ney estimation (`lmplz`, which estimates unpruned models) and fast querying. Its TRIE structure uses less memory than the smallest lossless baseline and less CPU than the fastest baseline. — [KenLM paper (Heafield)](https://www.kheafield.com/papers/avenue/kenlm.pdf); [KenLM code page](https://kheafield.com/code/kenlm/)
- KenLM licence: code is LGPL (2.1), "but there are files from other sources too." — [kenlm forks' README e.g. CAMeL-Lab/camel-kenlm](https://github.com/CAMeL-Lab/camel-kenlm); [kheafield.com/code/kenlm](https://kheafield.com/code/kenlm/)
- Modified KN smoothing remains the baseline for n-gram generalisation work. — [Pickhardt et al., Generalized LM, arXiv 1404.3377](https://arxiv.org/pdf/1404.3377)

### Inferences
- An LGPL dependency at runtime is generally acceptable for an MIT/Apache Python package if it is dynamically linked and optional. A cleaner route is to use KenLM (or NLTK or a custom script) only at build time to estimate counts. You would then ship a pruned ARPA-like table as compressed JSON or NumPy arrays and sample with your own seeded code. Model files derived from data are not covered by KenLM's licence, but they are covered by the training corpus's licence (see section 5).
- Sampling a 3- to 4-gram model unconstrained gives text that is grammatical over about 4-word windows but incoherent beyond that. Constraining infill to 3-12 token spans between fixed template anchors, with a stop on a sentence-boundary token, keeps the realism of the skeleton while the n-gram supplies the lexical variety that lowers the gzip ratio.
- Conditioning on slots (product category, sentiment, severity): train one small model per condition, or interpolate a condition-specific model with a general one.
- Expected throughput: an n-gram sampler in pure Python is roughly tens of microseconds per token. That is consistent with thousands of rows/sec for short fields. This is an estimate, not a measured figure.

### Gaps
- No 2022-2026 paper found that directly evaluates template + n-gram infill or paraphrase lattices for synthetic tabular text. KenLM queries/sec were not retrieved.

## 3. Small on-device transformers (TinyStories, SmolLM, Qwen 0.5B) via llama.cpp/ONNX/CTranslate2

### Takeaway
Small models exist with permissive licences (TinyStories-33M MIT, SmolLM2-135M Apache-2.0, Qwen2.5-0.5B Apache-2.0) and are 100+ MB quantised. They give tens of tokens/sec per stream on a laptop CPU, which is too slow for thousands of rows/sec without batching. They are not bit-reproducible across hardware or builds. They fit as an optional extra, not as the default engine.

### Cited Findings
- TinyStories-33M: GPT-Neo architecture, 33M parameters, MIT licence. — [HF model card roneneldan/TinyStories-33M](https://huggingface.co/roneneldan/TinyStories-33M) (from a search snippet; the page was blocked); [TinyStories paper arXiv 2305.07759](https://arxiv.org/pdf/2305.07759)
- A 28.9M-parameter TinyStories-style model runs on an ESP32-S3 microcontroller at 9.88 tokens/s. — [slvDev/esp32-ai-tinystories](https://huggingface.co/slvDev/esp32-ai-tinystories)
- SmolLM2-135M: Apache 2.0. GGUF Q8_0 is about 0.14 GB and Q4_K_M about 0.11 GB. On an M2 MacBook Pro via llm/llama.cpp it generated about 74.8 tokens/s. — [llmapi SmolLM2-135M guide](https://llmapi.ai/models/huggingfacetb-smollm2-135m/); [Simon Willison on SmolLM](https://simonwillison.net/tags/smollm/)
- Qwen2.5-0.5B: 0.49B parameters (0.36B non-embedding), 24 layers, GQA 14 query / 2 KV heads, 32,768-token context, Apache 2.0. GGUF quantisations range from q2_K to q8_0. — [Qwen/Qwen2.5-0.5B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF); [ollama qwen2.5](https://ollama.com/library/qwen2.5)
- llama.cpp determinism:
  - The server with multiple slots gives non-deterministic output. With one slot the answer is repeatable, though logits vary slightly. — [llama.cpp issue #7052](https://github.com/ggml-org/llama.cpp/issues/7052)
  - Logits are not reproducible across KV-cache layouts, so seeded repros break under load. — [drama_llama issue #126](https://github.com/mdegans/drama_llama/issues/126)
  - Ollama users report inconsistent outputs despite a fixed seed and temperature. — [ollama #5321](https://github.com/ollama/ollama/issues/5321)
- Root cause: floating-point non-associativity. Greedy decoding can change with batch size, GPU count or GPU version. Quantised weights are still dequantised to floats, so quantisation does not remove this. — [arXiv 2506.09501 (numerical nondeterminism in LLM inference)](https://arxiv.org/html/2506.09501v2); [Ingonyama reproducibility write-up](https://www.ingonyama.com/post/solving-reproducibility-challenges-in-deep-learning-and-llms-our-journey)
- Guidance: for greedy decoding, use top-k=1 rather than temperature 0 alone, and pin binaries, drivers and quantisation, because different backends/builds still drift. — [KeywordsAI LLM consistency 2025](https://www.keywordsai.co/blog/llm_consistency_2025)
- The R package localLLM (llama.cpp-based) documents a reproducible-output mode. — [localLLM vignette](https://archive.linux.duke.edu/cran/web/packages/localLLM/vignettes/reproducible-output.html)

### Inferences
- At about 75 tok/s single-stream for a 135M model, a 30-token review takes about 0.4 s. That is about 2-3 rows/s per core, three orders of magnitude below the target. Batched ONNX or CTranslate2 inference could raise this a lot, but no benchmark was found.
- Determinism contract if offered: "same seed + same wheel/binary + same CPU ISA path gives the same text". It should not be "same text everywhere". This conflicts with a library-wide promise of cross-platform reproducibility, which argues for an opt-in `text_engine="local_llm"` extra.

### Gaps
- No primary docs retrieved on ONNX Runtime or CTranslate2 determinism flags, or on CPU batched throughput for 100M-500M models. Phi-mini sizes and licence were not verified in this pass.

## 4. Pre-generating a corpus with an LLM once and shipping phrase banks

### Takeaway
Major provider terms assign output ownership to the customer. They forbid using outputs to build or train competing models, but they do not forbid shipping text outputs as data. Distilling LLM output into a phrase bank shipped in an MIT/Apache package therefore looks permissible for Anthropic/OpenAI outputs if the package itself does not train a competing model. Pre-generation also keeps the runtime fully deterministic. This is not legal advice.

### Cited Findings
- OpenAI: "you ... own the Output" and OpenAI assigns its rights in Output to you. Use of Output "to develop models that compete with OpenAI" is prohibited. — [OpenAI Terms of Use (RoW)](https://openai.com/policies/row-terms-of-use/); [OpenAI Business terms May 2025](https://openai.com/policies/may-2025-business-terms/)
- Commentary: the competing-model restriction binds the party that generated the data, not downstream recipients. — [Eric Hartford, Demystifying OpenAI ToU and dataset licences](https://erichartford.com/demystifying-openais-terms-of-use-with-regards-to-dataset-licenses) (secondary opinion, not legal authority)
- Anthropic Commercial Terms:
  - The customer owns outputs, and Anthropic assigns its rights in outputs to the customer.
  - The customer may not use the services "to build a competing product or service, including to train competing AI models," except as expressly approved.
  - Anthropic publishes a help-centre article on training models with outputs.
  - Sources: [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms?facet2=pdf); [Claude support: Can I use my Outputs to train an AI model?](https://support.claude.com/en/articles/12326764-can-i-use-my-outputs-to-train-an-ai-model)

### Inferences
- A pre-generated phrase bank from an API LLM is a data asset owned by the generator. Licensing it as MIT/CC0 inside the package looks compatible with these terms. Two areas carry risk:
  - Downstream users who might use Misata text to train LLMs. The terms bind the original generator, per the commentary above, but this is unsettled.
  - Copyrightability of AI-generated text. It may be uncopyrightable, which actually reduces licence risk.
- Use an open-weight Apache-2.0 model (e.g. Qwen2.5, SmolLM2) as the offline generator to remove provider-terms questions entirely.
- QC pipeline for the pre-generated corpus:
  1. Exact dedup.
  2. Near-dedup with MinHash on 5-gram shingles.
  3. PII/entity scrub (real brand or person names).
  4. Length and sentiment balancing per slot.
  5. A gzip-ratio and distinct-n gate per field.
- Ship fragments (clauses or sentences keyed by slot), not whole rows, so that combinatorial recombination multiplies the diversity.

### Gaps
- Google Gemini and Meta Llama output/licence terms (e.g. the Llama licence's output-use clause) were not retrieved.

## 5. Licence status of candidate corpora for deriving phrase banks or n-gram models

### Takeaway
Of the commonly cited review sources, none is clean for redistributing derivatives in an MIT/Apache package. Yelp is restricted to academic/non-commercial use, Amazon Reviews 2023 has no licence the authors can grant, and MIMIC is credentialed. FineWeb (ODC-By plus Common Crawl ToU) and Synthea (Apache-2.0) are the cleanest options. Wikipedia-derived artifacts carry CC BY-SA share-alike obligations.

### Cited Findings
- **Yelp Open Dataset:** licensed "solely for academic or non-commercial purposes." Non-commercial means use by nonprofits, government, education or think tanks that is not for profit and not intended to produce works, services or data for commercial use. The licence is "royalty-free, non-exclusive, revocable, non-sublicensable, non-transferable." — [Yelp Dataset Terms of Use, July 7 2023](https://s3-media0.fl.yelpcdn.com/assets/srv0/engineering_pages/f64cb2d3efcc/assets/vendor/Dataset_User_Agreement.pdf) (from search snippet; PDF blocked); [Yelp Open Dataset page](https://business.yelp.com/data/resources/open-dataset/)
- **Amazon Reviews 2023 (McAuley Lab):** the lab says it is "not in a position to assign a license to this dataset or dictate the terms of its usage," and has made it available primarily for research. Some Kaggle mirrors label it CC0, which is unreliable. — [HF discussion #1](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/discussions/1); [UCSD Amazon data page](https://cseweb.ucsd.edu/~jmcauley/datasets/amazon/links.html); [Kaggle mirror listing CC0](https://www.kaggle.com/datasets/wajahat1064/amazon-reviews-data-2023)
- **FineWeb:** released under ODC-By v1.0 and "also subject to CommonCrawl's Terms of Use." — [HuggingFaceFW/fineweb](https://huggingface.co/datasets/HuggingFaceFW/fineweb); [FineWeb paper arXiv 2406.17557](https://arxiv.org/html/2406.17557v1); [Common Crawl ToU](https://commoncrawl.org/terms-of-use/)
- **Wikipedia-derived corpora:**
  - WikiText (100M+ tokens) is CC BY-SA. — [wikitext2 mirror](https://huggingface.co/datasets/mindchain/wikitext2)
  - Wiki-40B processed text inherits CC-BY-SA. — [Wiki-40B LREC 2020](https://aclanthology.org/2020.lrec-1.297.pdf)
  - Wikipedia's own guidance says the copyright status of LLM outputs and models relative to CC BY-SA is "not yet fully understood." — [Wikipedia:Large language models](https://en.wikipedia.org/wiki/Wikipedia:Large_language_models)
- **Synthea** (MITRE): Apache-2.0. The sibling project chatty-notes, which generates clinical notes from Synthea FHIR bundles, is also Apache-2.0. — [synthea LICENSE](https://github.com/synthetichealth/synthea/blob/master/LICENSE); [chatty-notes](https://github.com/synthetichealth/chatty-notes)
- **C4, OpenWebText, MIMIC, MTSamples:** licence pages not retrieved in this pass (see Gaps).

### Inferences
- **Safest path:** derive phrase banks and n-gram counts from FineWeb (ODC-By: attribution, ship a NOTICE) filtered to review- or support-like domains. Combine that with Synthea-derived clinical vocabulary (Apache-2.0) and self-authored or open-weight-LLM-generated fragments.
- **Avoid:** Yelp (commercial-use bar, non-sublicensable) and Amazon Reviews 2023 (no grantable licence). Do not even use them to tune statistics for a shipped asset.
- **Wikipedia:** an n-gram table derived from Wikipedia is arguably an adaptation under CC BY-SA. Ship it, if at all, as a separately licensed data file (CC BY-SA) in a separate optional package, not inside MIT/Apache code.
- **Data files and code licences:** data files can carry a different licence from the code (e.g. a `misata-textdata` wheel under ODC-By/CC BY). This needs clear NOTICE/attribution files.

### Gaps
- Not verified here: C4's licence (commonly stated as ODC-By), OpenWebText's licence, MIMIC-IV credentialed-access DUA terms (understood to be non-redistributable), the MTSamples licence, and Project Gutenberg's public-domain/trademark terms.

## 6. How other tools do it (Faker, Mimesis, Gretel/MOSTLY AI, SDV, DataDreamer/distilabel)

### Takeaway
Commodity generators (Faker) offer lorem or word-list text and guarantee seeded reproducibility only within a pinned version. Enterprise tools (MOSTLY AI, Gretel) fine-tune LLMs on the user's data. SDV treats free text as an unsupported or anonymised type. No mainstream open-source tool solves realistic, deterministic, offline free text, which is a gap Misata can fill.

### Cited Findings
- Faker: `seed()` seeds a shared RNG, and the same seed gives the same results "when the same methods with the same version of faker are called." Results "are not guaranteed to be consistent across patch versions," so users should pin to the patch level. — [joke2k/faker README](https://github.com/joke2k/faker); [Faker docs](https://faker.readthedocs.io/)
- No Faker locale overrides the Lorem provider, so text stays pseudo-Latin regardless of locale (per a third-party analysis). A PHP plugin bug showed decorations chosen via an unseeded `random_int()` breaking reproducibility, a common class of bug. — [awcodes/content-faker PR #8](https://github.com/awcodes/content-faker/pull/8)
- ONS guidance compares Faker and Mimesis for synthetic data. — [ONS Spark: Faker and Mimesis](https://best-practice-and-impact.github.io/ons-spark/ancillary-topics/synthetic_data_python.html)
- MOSTLY AI: free-text columns use the "Language/Text" encoding type. It fine-tunes Hugging Face text-generation models (e.g. Mistral-7B, Viking-7B) or its own non-pretrained LSTM, conditioned on the tabular columns of the same row. — [MOSTLY AI docs: fine-tuning LLMs](https://mostly.ai/docs/quick-start/fine-tuning-llms); [MOSTLY AI blog: synthetic text](https://mostly.ai/blog/synthetic-text-data)
- SDV: `{'sdtype': 'text'}` columns are filtered out by SDMetrics. `id` columns are generated from a `regex_format`. PII columns are anonymised by default. Free text is not modelled. — [SDMetrics issue #265](https://github.com/sdv-dev/SDMetrics/issues/265); [SDV sdtypes](https://docs.sdv.dev/sdv/concepts/metadata/sdtypes)

### Inferences
- Misata's differentiator: grammar/phrase-bank text that is (a) slot-conditioned on the row, (b) passes a compression/diversity check, and (c) has a documented stability contract stronger than Faker's patch-pinned one.

### Gaps
- Mimesis text provider internals, Gretel's current text offering, and how DataDreamer and distilabel handle seeding and caching were not retrieved. From general knowledge, distilabel and DataDreamer rely on caching LLM responses rather than on deterministic decoding, but no source was checked.

## 7. Seedability: cross-version and cross-platform determinism, per-row counter-based seeding

### Takeaway
Do not rely on stream stability across versions of NumPy `Generator` methods. Use a counter-based design: derive each row's state from (global_seed, column_id, row_index) through a stable hash or Philox key/counter. Then use only simple integer draws, with your own selection logic for choices and weights, so row N is independent of rows 0..N-1 and of library upgrades.

### Cited Findings
- NumPy NEP 19 (final): `Generator`/`default_rng` may break stream compatibility "to introduce new features or improve performance ... with caution". Legacy `RandomState` keeps the stricter guarantee. Calling `rng.random()` 5 times is not guaranteed to equal `rng.random(5)`. — [NEP 19](https://numpy.org/neps/nep-0019-rng-policy.html); [NumPy RNG compatibility policy](https://numpy.org/doc/stable/reference/random/compatibility.html)
- NumPy Philox:
  - Counter-based, period 2^256 − 1, supports jumping/advancing in increments of 2^128.
  - SeedSequence hashes user seeds, so "the usual user-provided seed" can be safely mixed "with simple incrementing counters" to get independent states.
  - `spawn()` creates independent child streams.
  - Sources: [Philox docs](https://numpy.org/doc/stable/reference/random/bit_generators/philox.html); [Parallel RNG](https://numpy.org/doc/stable/reference/random/parallel.html)
- Counter-based RNGs are the basis for portable, reproducible parallel RNG libraries. — [OpenRAND, arXiv 2310.19925](https://arxiv.org/pdf/2310.19925)
- Python stdlib `random.seed`: with version 2 (the default), str/bytes seeds are converted via SHA-512 to an int using all bits. Seeding with other objects uses `hash()`, which is randomised per process (e.g. tuples broke reproducibility). The docs promise that a backward-compatible seeder will be kept if seeding changes. — [Python random docs](https://docs.python.org/3/library/random.html); [bpo-32554 tuple seed](https://bugs.python.org/issue32554); [bpo-27706 str hash randomisation](https://bugs.python.org/issue27706)

### Inferences
- Recommended scheme:
  1. Compute `key = blake2b(f"{seed}|{table}|{column}".encode(), digest_size=16)`.
  2. Set `rng_row = Philox(key=key_int, counter=row_index)`, or hash `(key, row_index)` to a uint64 per row and run a small, self-implemented PRNG (e.g. SplitMix64/PCG in pure Python or NumPy uint64 arithmetic).
  3. Draw integers only. Implement weighted choice yourself via cumulative integer weights and bisect, rather than `Generator.choice`, whose algorithm may change under NEP 19.
- Vectorised path: generate a uint64 matrix of shape (n_rows, k_draws) from a counter-based hash in NumPy. Each row's draws then depend only on its index, which enables parallel/chunked generation and `generate(rows=slice(N, N+1))` that matches the full run.
- Avoid in text paths:
  - Python `hash()` or set iteration order for anything that affects output.
  - Floating-point accumulation for weight normalisation (use integer weights).
  - Locale-dependent `str.lower()`/sorting.
  - Dict ordering derived from sets.
- Freeze phrase banks with a version hash. Text output then changes only when the bank version changes, which can be documented in the stability policy (e.g. a "text bank v3" pin).

### Gaps
- No primary source checked on whether NumPy's `Philox` raw stream itself is guaranteed stable across NumPy versions. NEP 19 suggests BitGenerator raw streams are kept stable while distribution methods may change, but this was not verified on the page.
