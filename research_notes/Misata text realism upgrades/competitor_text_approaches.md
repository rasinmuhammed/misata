# Competitor text approaches: how synthetic data tools generate realistic free text and categorical text, and keep it coherent with other columns

Research date: 2026-10-03. Repos were shallow-cloned on 2026-10-03; latest-commit dates are recorded so readers can see how current each repo is. Many vendor docs sites (tonic.ai, docs.sdk.ydata.ai, nvidia-nemo.github.io, arxiv.org, huggingface.co, syntho.ai) were blocked by the egress proxy. For those vendors the findings come from search-result snippets and are marked as such. Example outputs labelled "run locally" came from my own runs in a scratch venv (Faker 40.40.0, faker-commerce 1.0.4, faker_food 0.3.0, mimesis at git HEAD 2026-09-29).

## Faker and Mimesis: how text providers work, how realistic they are, and community providers

### Takeaway
Faker and Mimesis both pick items from static lists with a seeded PRNG. Faker's lorem builds "sentences" from a word list with no grammar. `catch_phrase` and `bs` join one random word from each of three lists. Mimesis `text()` returns whole sentences drawn from about 28 fixed sentences per locale, mostly about programming languages. Output is fully deterministic and costs nothing, but it has no semantic link to other columns. Community providers improve realism only by adding domain word lists, and their combinatorial output can still be nonsensical ("Wooden Pizza").

### Cited Findings
- Faker's lorem `words()`/`sentence()` choose from a built-in word list, or from a user-supplied `ext_word_list`. The `part_of_speech` filter only works with the built-in list. — [faker/providers/lorem/__init__.py](https://github.com/joke2k/faker/blob/master/faker/providers/lorem/__init__.py) (repo HEAD 2026-09-28)
- The en_US lorem provider file is about 3,180 lines of word list. — [faker/providers/lorem/en_US/__init__.py](https://github.com/joke2k/faker/blob/master/faker/providers/lorem/en_US/__init__.py)
- `catch_phrase()` is `" ".join([self.random_element(word_list) for word_list in self.catch_phrase_words])`, which takes one word from each of three tuples (adjectives like "Adaptive", "Advanced", "Ameliorated", ...). `bs()` works the same way. — [faker/providers/company/__init__.py L17, L521-527](https://github.com/joke2k/faker/blob/master/faker/providers/company/__init__.py)
- Example output (run locally, `Faker.seed(42)`, en_US):
  - sentence: "Agent every development say."
  - paragraph: "Opportunity all behavior discussion. Ago current practice nation determine operation speak according. Recently future choice whatever."
  - catch_phrase: "Mandatory bi-directional array"; bs: "synergize mission-critical convergence"; job: "Local government officer"
  - Re-seeding with 42 reproduced "Agent every development say." exactly, so output is deterministic.
- Faker core providers are address, automotive, bank, barcode, color, company, credit_card, currency, date_time, doi, emoji, file, geo, internet, isbn, job, lorem, misc, passport, person, phone_number, profile, python, sbn, ssn, user_agent. There is no product, review, or ticket provider. — [faker/providers/](https://github.com/joke2k/faker/tree/master/faker/providers)
- Faker's official community-providers list includes AI Provider, Airtravel, Biology, Credit Score, `faker-datasets` ("Build providers based on datasets"), Ecommerce (`faker-ecommerce-provider`), Education, Healthcare (diseases, ICD-10, medications), Market Data, Microservice, Music, Observability ("fake logs, correlated OpenTelemetry-style traces, and k8s metadata"), Posts (markdown, `mdgen`), Vehicle, and others. — [docs/communityproviders.rst](https://github.com/joke2k/faker/blob/master/docs/communityproviders.rst)
- `faker-commerce` "adds fake commerce product names, prices, categories and descriptions". — [PyPI faker-commerce](https://pypi.org/project/faker-commerce/). However, the public methods of v1.0.4 that I inspected are only `ecommerce_name`, `ecommerce_category`, `ecommerce_material`, and `ecommerce_price`. I found no description method, so the PyPI blurb and the installed package disagree.
- faker-commerce example output (run locally, seed 7): names `['Table', 'Wooden Pizza', 'Fish']`, category `Sports`. The name comes from adjective+material+product combinatorics with no coherence to the category.
- `faker_food` provides `dish()`, `dish_description()`, `ethnic_category()`, `fruit()`, `ingredient()`, `measurement()`, and more. — [PyPI faker_food](https://pypi.org/project/faker_food/). Example (run locally): dish "Risotto with seafood", dish_description "Three egg omelet with Roquefort cheese, chives, and ham. With a side of roasted potatoes, and your choice of toast or croissant." The description is a fixed curated string and is not about the sampled dish.
- Mimesis `Text.text(quantity)` is `" ".join(self.random.choices(text, k=quantity))` over a locale JSON list. `sentence()` and `title()` both just call `text(quantity=1)`. — [mimesis/providers/text.py](https://github.com/lk-geimfari/mimesis/blob/master/mimesis/providers/text.py) (HEAD 2026-09-29)
- The Mimesis en `text.json` has keys alphabet, answers, color, level, questions, quotes, text, words. `text` has only 28 sentences, e.g. "Haskell is a standardized, general-purpose purely functional programming language...". `quotes` holds movie quotes ("Frankly, my dear, I don't give a damn."). — [mimesis/datasets/en/text.json](https://github.com/lk-geimfari/mimesis/blob/master/mimesis/datasets/en/text.json)
- Mimesis en `food.json` sizes are dishes 359, drinks 311, fruits 152, spices 77, vegetables 127. — same datasets dir. Example (run locally, seed 1): `Food.dish()` gives "Chicken Liver Pate".
- Mimesis example (run locally, seed 42): `text(2)` gives 'Messages can be sent to and received from ports, but these messages must obey the so-called "port protocol." Haskell is a standardized...'. `title()` gives "Erlang is known for its designs that are well suited for systems."

### Inferences
- The main realism complaints follow from these mechanisms. Lorem is syntactically broken English. Mimesis text is real English but has tiny cardinality (28 sentences) and is off-topic for any business domain. Neither can condition text on a rating, category, or name.
- Misata's grammar/template "microtext" is already a step above both, because templates can take slots from row values. `faker-datasets` (providers built from datasets) suggests a cheap path: ship curated, domain-tagged phrase banks.

### Gaps
- I did not find a canonical GitHub issue that lists Faker realism complaints, so the complaints above are inferred from the mechanisms and outputs, not cited.
- I did not inspect `faker-ecommerce-provider` (a different package from faker-commerce).

## NVIDIA NeMo Data Designer (open source): LLM text columns, samplers, seeds, personas, validators, judges

### Takeaway
Data Designer is a declarative DAG of columns. Cheap non-LLM sampler columns (category, subcategory, person/persona, numeric distributions) act as diversity "steering" attributes. LLM text, structured, code, and judge columns are Jinja prompt templates that reference those columns, so each row gets a distinct, conditioned prompt. Diversity comes from the sampler space (plus temperature), not from dedup. The tool even warns when a prompt references no columns. Validators (code, local callable, remote) and LLM-judge rubric columns score the output.

### Cited Findings
- History: Gretel launched "Navigator Data Designer" ([Gretel blog](https://www.gretel.ai/blog/build-high-quality-datasets-for-ai-using-gretel-navigator)). NVIDIA acquired Gretel in March 2025, reportedly for nine figures, with about 80 employees folded into NVIDIA ([TechCrunch, 2025-03-19](https://techcrunch.com/2025/03/19/nvidia-reportedly-acquires-synthetic-data-startup-gretel)). The open-source successor is `NVIDIA-NeMo/DataDesigner`: Apache-2.0, `pip install data-designer`, Python 3.10-3.14, providers NVIDIA Build, OpenAI, OpenRouter. — [README](https://github.com/NVIDIA-NeMo/DataDesigner) (HEAD 2026-09-28)
- Column config classes in the repo: `SamplerColumnConfig`, `SamplerMultiColumnConfig`, `LLMTextColumnConfig`, `LLMStructuredColumnConfig`, `LLMCodeColumnConfig`, `LLMJudgeColumnConfig`, `ValidationColumnConfig`, `ExpressionColumnConfig`, `EmbeddingColumnConfig`, `CustomColumnConfig`, `SeedDatasetColumnConfig`, `SeedDatasetMultiColumnConfig`. — [packages/data-designer-config/.../column_configs.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/column_configs.py)
- Sampler types: uuid, category, subcategory, uniform, gaussian, bernoulli, bernoulli_mixture, binomial, poisson, scipy, person, person_from_faker, datetime, timedelta. `conditional_params` is a dict keyed by a condition such as `"age > 21"`, with sampler params to use when the condition holds. — [column_configs.py L40-80](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/column_configs.py); [sampler_params.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/sampler_params.py)
- The `subcategory` sampler takes a parent column and a dict of parent value to child values. The tutorial maps Electronics to Smartphones/Laptops/Headphones/Cameras/Accessories, Books to Fiction/Non-Fiction/Self-Help/Textbooks/Classics, and so on. — [docs/notebook_source/1-the-basics.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/docs/notebook_source/1-the-basics.py)
- The tutorial calls sampler columns "particularly useful for **steering the diversity** of the generated data". It adds `review_style` as a weighted category `["rambling","brief","detailed","structured with bullet points"]` with weights `[1,2,2,1]`, plus `number_of_stars` as uniform 1-5 converted to int. — same notebook
- Multi-column coherence uses Jinja chaining. `product_name` is an LLM text column with the prompt "Come up with a creative product name for a product in the '{{ product_category }}' category, focusing on products related to '{{ product_subcategory }}'. The target age range ... is {{ target_age_range }}". `customer_review` then uses "You are a customer named {{ customer.first_name }} from {{ customer.city }}, {{ customer.state }}. You are {{ customer.age }} years old and recently purchased a product called {{ product_name }}. Write a review of this product, which you gave a rating of {{ number_of_stars }} stars. The style of the review should be '{{ review_style }}'." Nested person fields are reached with dot notation. — same notebook
- Default tutorial model: `nvidia/nemotron-3.5-lightning-30b-a3b` with temperature=1.0, top_p=0.95, max_tokens=2048, thinking disabled. — same notebook
- The validation engine emits a `PROMPT_WITHOUT_REFERENCES` warning: "This means the same prompt will be used for every row in the dataset. To increase the diversity of the generated data, consider adding references to other columns in the prompt template." — [engine/validation.py ~L160-180](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-engine/src/data_designer/engine/validation.py)
- The `person` sampler draws from managed **Nemotron Personas** datasets, with filters by locale, sex, city, and age_range, and an optional `with_synthetic_personas` flag that "appends additional synthetic persona columns including personality traits, interests, and background descriptions". There is also `person_from_faker`. — [sampler_params.py L420-460](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/sampler_params.py)
- Managed persona datasets and download sizes: en_US 1.24 GB, en_IN 2.39 GB, en_SG 0.30 GB, fr_FR 3.87 GB, hi_Deva_IN 4.14 GB, hi_Latn_IN 2.7 GB, ja_JP 1.69 GB, ko_KR 2.66 GB, pt_BR 2.33 GB. — [config/utils/constants.py L396-406](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/utils/constants.py)
- Seed datasets: `SeedConfig` has `sampling_strategy` of `ORDERED` (default) or `SHUFFLE`. Seed columns can then be referenced in prompts. — [config/seed.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/seed.py); tutorial `3-seeding-with-a-dataset.py`
- Judges: `LLMJudgeColumnConfig` extends the LLM text column with `scores: list[Score]`. Each `Score` has a name, a description, and `options` mapping score values (e.g. 1-5 or "Poor"/"Good") to descriptions. Validators: `ValidatorType` CODE (Python/SQL), LOCAL_CALLABLE, REMOTE. — [column_configs.py L331-382](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/column_configs.py); [validator_params.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/validator_params.py)
- Determinism: the configs get a "deterministic content-addressable fingerprint" (`fingerprint.py`). Samplers use a numpy `RandomState` seeded via `check_random_state(seed)`. The model client request type has an optional `seed: int | None`. — [config/fingerprint.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/fingerprint.py); [sampling_gen/utils.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-engine/src/data_designer/engine/sampling_gen/utils.py); [models/clients/types.py L69](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-engine/src/data_designer/engine/models/clients/types.py)
- Cost and scale (search snippets of the NDD paper and docs; arxiv/docs fetch was blocked): Data Designer auto-collects `input_tokens_median_per_record` and `output_tokens_median_per_record`. It "has supported the generation of approximately 10 trillion tokens". One recipe costs "roughly four model calls per document". Multi-stage pipelines "generate more candidates than they retain", which increases cost. — [arXiv 2609.17699 (NeMo Data Designer paper)](https://arxiv.org/html/2609.17699v1); [docs: architecture-performance](https://docs.nvidia.com/nemo/datadesigner/concepts/architecture-performance); open issue requesting structured cost/usage in results: [Issue #956](https://github.com/NVIDIA-NeMo/DataDesigner/issues/956)

### Inferences
- Data Designer's coherence comes from generation order. Upstream columns (category → subcategory → name → rating → style) are sampled first, and downstream text is conditioned on them through the prompt. Misata can copy this exactly, without an LLM: sample the latent attributes (rating, sentiment, style, persona) first, then pick or compose text from a bank keyed on those attributes.
- Its diversity model is "diversity = product of sampler cardinalities". Misata can measure the same thing statically and warn the way `PROMPT_WITHOUT_REFERENCES` does, for example "template references no row columns".
- LLM determinism is only best-effort. The provider `seed` param does not guarantee identical tokens across hardware or model versions, and the fingerprint only covers the config, not the outputs. This is my inference; I found no doc claiming bitwise reproducibility of LLM columns.

### Gaps
- I could not read the docs site or the paper in full (blocked). The exact semantics of the user-facing sampler seed and any built-in near-dup filtering are unverified. A grep for dedup/diversity code found no text-dedup step in the engine.
- No published $/1k-rows figure.

## Gretel, Mostly AI, Tonic Fabricate, Tonic Textual, YData, Synthesized

### Takeaway
The commercial field has consolidated. Gretel is now NVIDIA (Data Designer). The company behind Mostly AI reportedly ceased operations in March 2026, and its brand went to Syntho in June 2026. Mostly AI's open-source SDK learns text from source data using a from-scratch LSTM or a fine-tuned HF causal LM, conditioned on the synthesized tabular columns. Tonic Fabricate is an LLM agent with a validation-agent loop. Tonic Textual does NER-based PII replacement inside real text. YData's LLM Synthesizer generates tables from natural-language column descriptions and supports deterministic `calculated_features`. I found little public detail on Synthesized's text handling.

### Cited Findings
- **Mostly AI SDK** (`mostly-ai/mostlyai`, HEAD 2026-09-23, depends on `mostlyai-engine==2.7.1`). `ModelEncodingType` includes `LANGUAGE_TEXT` ("Model will sample free text, using a LANGUAGE model"), `LANGUAGE_CATEGORICAL`, `LANGUAGE_NUMERIC`, `LANGUAGE_DATETIME`, alongside `TABULAR_CATEGORICAL` ("samples from existing (non-rare) categories") and `TABULAR_CHARACTER`. — [mostlyai/sdk/domain.py L509-534](https://github.com/mostly-ai/mostlyai/blob/main/mostlyai/sdk/domain.py)
- "The default language model is a basic, non-pre-trained LSTM (`LSTMFromScratch-3m`), particularly effective for textual data with limited scope (short lengths, narrow variety) and sufficient training samples." Alternatively, any HF `AutoModelForCausalLM` model "can be selected to be then fine-tuned on the provided training data". "A modern GPU is highly recommended." Example model ids are `MOSTLY_AI/Small|Medium|Large`, `MOSTLY_AI/LSTMFromScratch-3m`, `microsoft/phi-1_5`, and `Qwen/Qwen2.5-Coder-0.5B` in a README example. — [README](https://github.com/mostly-ai/mostlyai/blob/main/README.md); [domain.py L1240-1260](https://github.com/mostly-ai/mostlyai/blob/main/mostlyai/sdk/domain.py)
- Mostly AI's config marks a column as text per column: `{'name': 'headline', 'model_encoding_type': 'LANGUAGE_TEXT'}`. Conditional generation works through `mostly.probe(g, seed=[{"age": 24, "sex": "Male"}] * 10_000)`, i.e. fix some columns and sample the rest. — [docs/usage.md L303-313](https://github.com/mostly-ai/mostlyai/blob/main/docs/usage.md); [README L89](https://github.com/mostly-ai/mostlyai/blob/main/README.md)
- Mostly AI's SDK paper (search snippet): a pre-trained LLM "is fine-tuned on the dataset using Low-Rank Adaptation (LoRA), integrating additional context from tabular features into the text generation process". — [arXiv 2508.00718](https://arxiv.org/html/2508.00718v1)
- Corporate status: "The vendor behind MOSTLY AI ceased operations in March 2026"; "On June 9, 2026, Syntho ... announced the acquisition of the MOSTLY AI Brand", which continues as "MOSTLY AI, powered by Syntho". Per a third-party summary, the announcement says nothing about the SDK. — [Syntho announcement](https://www.syntho.ai/syntho-acquires-mostly-ai-trademark-and-related-assets/) (fetch blocked; via search snippet); [beri.net 2026 article](https://www.beri.net/article/best-synthetic-data-platforms-real-data-cannot-leave-2026). The mostly.ai site now brands itself "MOSTLY AI powered by Syntho" ([mostly.ai](https://mostly.ai/)). The SDK repo still had commits in Sept 2026, as observed in the clone.
- **Tonic Fabricate**: the "Fabricate Data Agent" generates data "from scratch ... through a natural language chat interface", combining "the vast domain expertise of Large Language Models (LLMs)" with "Tonic.ai's industry-leading synthetic data generators". It produces relational data for PostgreSQL/MySQL/Oracle and nested JSON, plus unstructured free text exported as PDF/DOCX/PPTX/EML. It can pair with a "Validation Agent that reviews generated data and prompts refinements ... The two agents work in a loop". — [Tonic press release](https://www.tonic.ai/press-releases/tonic-launches-fabricate-data-agent); [Fabricate product page](https://www.tonic.ai/products/fabricate) (search snippets; fetch blocked)
- **Tonic Textual**: transformer NER detects "46+ entity types across 50+ languages". Synthesis replaces PII with realistic fakes so that "a synthesized name is still a plausible name in the right position in the sentence", instead of placeholder tokens like `[NAME_GIVEN_xxxx]`. — [Tonic blog: LLM fine-tuning on sensitive data](https://www.tonic.ai/cookbooks/llm-fine-tuning-on-sensitive-data); [Tonic FAQs](https://www.tonic.ai/faqs) (search snippets)
- **YData SDK "Text to Dataset" (LLM Synthesizer)**: "you describe tables and columns in prompts; the model produces a single table (Dataset) or multiple related tables (MultiDataset) with primary and foreign keys". Columns "with a single correct answer given the others — such as arithmetic identities, mandatory copies, and deterministic flags — do not have to be generated, and can be passed to `fit(calculated_features=...)`". There are optional per-column PII blocks (format, examples, pattern). — [YData SDK docs](https://docs.sdk.ydata.ai/latest/synthetic_data/text_to_dataset/) (search snippet; fetch blocked)
- **Synthesized**: the SDK is on PyPI with a 30-day trial licence. I found no public documentation of its free-text design. — [PyPI synthesized](https://pypi.org/project/synthesized/)

### Inferences
- These tools follow two coherence patterns:
  1. Learned joint models (Mostly AI). Text is modelled conditionally on tabular columns, so coherence is learned from real data. This requires source data and a GPU.
  2. Prompt-time conditioning plus an agent/validator loop (Data Designer, Fabricate, YData).
- YData's `calculated_features` matches Misata's philosophy: compute anything that is derivable deterministically, and leave the generator only for genuinely free fields.
- Tonic Textual's "realistic surrogate in the right position" idea maps to Misata templates. Slots should be filled with entity values that agree with the row (the same customer name as the `customer` column).

### Gaps
- I could not access Fabricate docs for the claimed code-sandbox mechanism. Snippets did not confirm whether Fabricate writes generator code in a sandbox.
- No vendor published per-row pricing. The Synthesized text approach is undocumented publicly.

## DataDreamer, distilabel, HF synthetic-data-generator, PersonaHub, Cosmopedia: pipelines for diversity, personas, dedup, filtering

### Takeaway
LLM-dataset pipelines get diversity mainly from conditioning attributes injected into prompts: AttrPrompt in DataDreamer, personas in PersonaHub, audience/style/seed topic in Cosmopedia. Afterwards they remove near-duplicates with MinHash or embedding dedup and score quality with judge or classifier steps. Several of these projects are now dormant or superseded.

### Cited Findings
- **DataDreamer** (HEAD 2025-02-02, so dormant) has prompt steps `DataFromPrompt`, `DataFromAttributedPrompt`, `FewShotPrompt`, `FewShotPromptWithRetrieval`, `FilterWithPrompt`, `JudgePairsWithPrompt`, `RankWithPrompt`, `ProcessWithPrompt`, `RAGPrompt`. `DataFromAttributedPrompt` implements AttrPrompt ([arXiv 2306.15895](https://arxiv.org/abs/2306.15895)): an instruction like `"Generate a {adjective} sentence that is {length}."` is filled with combinations from an `attributes` dict. — [src/steps/prompt/data_from_attributed_prompt.py](https://github.com/datadreamer-dev/DataDreamer/blob/main/src/steps/prompt/data_from_attributed_prompt.py)
- DataDreamer promotes itself as "Reproducible: Workflows ... are easily shareable, reproducible". It achieves this by caching LLM outputs on disk (`cache_folder_path`), not by deterministic decoding. — [README](https://github.com/datadreamer-dev/DataDreamer); [src/llms/llm.py](https://github.com/datadreamer-dev/DataDreamer/blob/main/src/llms/llm.py)
- **distilabel** (HEAD 2025-12-15) has filtering steps `MinHashDedup` ("Deduplicates text using MinHash and MinHashLSH") and `EmbeddingDedup` (a cosine-similarity `threshold`). Tasks include self_instruct, evol_instruct, evol_quality, magpie, ultrafeedback, quality_scorer, complexity_scorer, prometheus_eval, text_classification, and structured_generation. — [src/distilabel/steps/filtering/minhash.py](https://github.com/argilla-io/distilabel/blob/main/src/distilabel/steps/filtering/minhash.py); [embedding.py](https://github.com/argilla-io/distilabel/blob/main/src/distilabel/steps/filtering/embedding.py); [steps/tasks/](https://github.com/argilla-io/distilabel/tree/main/src/distilabel/steps/tasks)
- **HF/Argilla synthetic-data-generator** (a Gradio Space, Apache-2.0, HEAD 2025-09-19). Its README says: "Check the succesor of this project: https://github.com/huggingface/aisheets". — [README](https://github.com/argilla-io/synthetic-data-generator)
- **PersonaHub**: "1 billion diverse personas" (~13% of world population). It has released 200k personas, then 370M "elite personas" (Feb 2025), plus samples: math 50K, reasoning 50K, instructions 50K, knowledge 10K, NPC 10K, tools 5K. Data is CC BY-NC-SA 4.0 (non-commercial) and code is MIT. — [README](https://github.com/tencent-ailab/persona-hub) (HEAD 2025-02-18). Example personas from `data/persona.jsonl`: "A Political Analyst specialized in El Salvador's political landscape."; "A legal advisor who understands the legal implications of incomplete or inaccurate project documentation"; "A maternal health advocate focused on raising awareness about postpartum complications."
- PersonaHub templates prepend a persona to a task, e.g. `knowledge_template = '''{persona}\n\nAssume you are the persona described above and you are writing a Quora article using your knowledge...'''`. The math template asks the model to "make full use of the persona description ... to ensure that the math problem is unique and specific to the persona." — [code/prompt_templates.py](https://github.com/tencent-ailab/persona-hub/blob/main/code/prompt_templates.py)
- PersonaHub's paper describes Text-to-Persona and Persona-to-Persona construction plus dedup. I could not fetch it (arxiv blocked), and the README does not describe dedup. — [arXiv 2406.20094](https://arxiv.org/abs/2406.20094)
- **Cosmopedia** (HEAD 2024-11-20) has "over 30 million files and 25 billion tokens" generated by Mixtral-8x7B-Instruct-v0.1 in "> 10k H100 GPU hours" via llm-swarm. Prompts are built from seed data (openstax, khanacademy, stanford, wikihow, stories, auto_math_text, web_samples with topic clustering). — [README](https://github.com/huggingface/cosmopedia)
- Cosmopedia audience conditioning: `STYLES = {"young children": ..., "college students": ...}`, plus a scholarly "highly knowledgeable audience" style. Each style carries its own criteria, such as "Avoid technical jargon ... conversational tone". — [prompts/openstax/build_openstax_prompts.py](https://github.com/huggingface/cosmopedia/blob/main/prompts/openstax/build_openstax_prompts.py)
- Cosmopedia dedup: MinHash via datatrove. "we carefully crafted the prompts to ensure distinct outputs even with identical seeds, the volume of duplicates found in Cosmopedia was less than 1% of the files". — [deduplication/README.md](https://github.com/huggingface/cosmopedia/blob/main/deduplication/README.md)

### Inferences
- In every pipeline, diversity comes from conditioning combinatorics (attributes × personas × audiences × seed topics), and dedup is only a cleanup step (<1% in Cosmopedia). For Misata, the attribute grid is the important part to copy. Misata can also run a cheap MinHash or n-gram uniqueness check on generated text columns as a quality metric.
- Cosmopedia's cost works out to roughly 25B tokens / 10k H100-hours ≈ 2.5M tokens per H100-hour. This is my arithmetic from the cited figures.

### Gaps
- I did not verify the PersonaHub paper's dedup thresholds (blocked).

## Multi-column coherence (ticket subject/description/resolution, review vs rating, product description vs name/category/price)

### Takeaway
No tool I examined enforces cross-column text coherence with constraints. Coherence comes from three mechanisms:
- Generation order plus conditioning: Data Designer Jinja, PersonaHub/Cosmopedia prompts, AttrPrompt.
- Learned conditional models: Mostly AI LANGUAGE_TEXT with tabular context.
- Post-hoc checking: Data Designer judge/validator columns, the Fabricate Validation Agent.

Faker and Mimesis have no coherence mechanism.

### Cited Findings
- Review vs rating: Data Designer samples `number_of_stars` first, then injects "which you gave a rating of {{ number_of_stars }} stars" and the style into the review prompt. — [1-the-basics.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/docs/notebook_source/1-the-basics.py)
- Product name vs category: Data Designer chains category → subcategory (conditional sampler) → LLM product_name that sees both. — same
- Conditional samplers keep categorical columns coherent without an LLM, e.g. `conditional_params={"age > 21": ...}` and `subcategory`. — [column_configs.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/column_configs.py)
- Mostly AI conditions the text model on generated tabular features (LoRA fine-tuning "integrating additional context from tabular features"). — [arXiv 2508.00718](https://arxiv.org/html/2508.00718v1)
- Fabricate uses a Validation Agent loop to correct mismatches. — [Tonic press release](https://www.tonic.ai/press-releases/tonic-launches-fabricate-data-agent)
- Faker/faker-commerce produce independent values: "Wooden Pizza" with category "Sports" (run locally). faker_food's `dish_description` is unrelated to the `dish` sampled in the same call (run locally).

### Inferences
- For ticket subject/description/resolution, the transferable pattern is to sample a latent ticket "intent" or category (plus severity and product) once per row. Every text field is then generated from that shared latent, with the subject derived from the description's key phrase, so that the fields cannot disagree. This is Data Designer's DAG done without an LLM.
- A judge column has a non-LLM analogue for Misata: a deterministic validator, such as sentiment-lexicon polarity vs rating, or checking that a category keyword appears in the description, reported as a coherence score.

### Gaps
- I found no tool publishing quantitative coherence metrics for text vs other columns.

## Determinism/reproducibility and cost per 1k rows for LLM-based approaches

### Takeaway
LLM-based tools offer, at best, config fingerprints, sampler seeds, optional provider `seed` params, and output caching (DataDreamer). None claim bit-identical regeneration of LLM text. Per-1k-row cost is not published, but at current mini-model prices a short review column costs well under $1 per 1k rows. Multi-call pipelines with judges multiply that by 2-4x.

### Cited Findings
- Data Designer has a deterministic config fingerprint, seeded numpy samplers, and an optional `seed` on model requests. It reports median input/output tokens per record. — [fingerprint.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/fingerprint.py); [types.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-engine/src/data_designer/engine/models/clients/types.py); [arXiv 2609.17699](https://arxiv.org/html/2609.17699v1)
- Data Designer recipe: "roughly four model calls per document (artifact extraction, Q&A generation, deduplication, quality judging)". — [arXiv 2609.17699 snippet](https://arxiv.org/html/2609.17699v1)
- DataDreamer's reproducibility comes from caching. — [README](https://github.com/datadreamer-dev/DataDreamer)
- Prices (third-party aggregators): GPT-4.1-mini costs $0.40/1M input and $1.60/1M output; GPT-5-mini costs $0.25/1M input and $2/1M output. — [economize.cloud](https://www.economize.cloud/resources/open-ai/pricing/gpt-4.1-mini/); [inworld.ai GPT-5 mini](https://inworld.ai/models/openai-gpt-5-mini)
- Faker/Mimesis: re-seeding reproduced identical output (run locally). Mostly AI requires GPU training for language models. — [mostlyai README](https://github.com/mostly-ai/mostlyai)

### Inferences
- Worked estimate (my assumptions, not sourced): a review column at about 150 input + 120 output tokens per row is 150k in and 120k out per 1k rows. On GPT-5-mini that is about $0.04 + $0.24 ≈ $0.28 per 1k rows for one column. Adding product_name and a judge column takes it to roughly $0.6-1.0 per 1k rows. A million rows across a relational schema then costs hundreds of dollars and hours of wall-clock time, compared with near-zero for template generation. Latency and rate limits, not dollars, are likely the binding constraint.
- Misata's determinism guarantee (same seed gives the same bytes) is a real differentiator. The only way to keep it while using LLMs is offline: generate phrase banks once, version and hash them, and ship them as data.

### Gaps
- No vendor-published $/1k rows. Pricing figures come from aggregators, not openai.com, which I did not fetch.

## What a non-LLM deterministic tool (Misata) can borrow

### Takeaway
Misata can borrow nearly the whole Data Designer conditioning design without LLM calls at generation time. The pieces are categorical and subcategory samplers with conditional params as latent attributes, persona banks, seed datasets, attribute-keyed phrase banks that an LLM (or a human) generates offline once, and deterministic validator/"judge" columns that score coherence and diversity.

### Cited Findings
- Sampler-as-diversity-steering, subcategory, and conditional params: [Data Designer tutorial](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/docs/notebook_source/1-the-basics.py); [column_configs.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/column_configs.py)
- Diversity lint ("prompt does not reference any columns"): [validation.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-engine/src/data_designer/engine/validation.py)
- Persona banks: Nemotron Personas (9 locales, 0.3-4.1 GB each) — [constants.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/utils/constants.py). PersonaHub is CC BY-NC-SA, so it is unsuitable for bundling in a commercial or permissive tool — [persona-hub README](https://github.com/tencent-ailab/persona-hub)
- Seed datasets with ORDERED/SHUFFLE sampling: [seed.py](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/packages/data-designer-config/src/data_designer/config/seed.py). Faker's `faker-datasets` community provider: [communityproviders.rst](https://github.com/joke2k/faker/blob/master/docs/communityproviders.rst)
- AttrPrompt attribute grids: [DataDreamer](https://github.com/datadreamer-dev/DataDreamer/blob/main/src/steps/prompt/data_from_attributed_prompt.py). Audience/style dicts: [Cosmopedia](https://github.com/huggingface/cosmopedia/blob/main/prompts/openstax/build_openstax_prompts.py)
- Deterministic derived columns: YData `calculated_features`. — [YData SDK docs](https://docs.sdk.ydata.ai/latest/synthetic_data/text_to_dataset/)
- Dedup/uniqueness checks: distilabel MinHashDedup/EmbeddingDedup; Cosmopedia MinHash (<1% dups). — [distilabel](https://github.com/argilla-io/distilabel/tree/main/src/distilabel/steps/filtering); [cosmopedia dedup](https://github.com/huggingface/cosmopedia/blob/main/deduplication/README.md)

### Inferences
- Concrete borrowings for Misata:
  1. **Latent-first DAG.** Sample rating, sentiment, category, intent, persona, and style columns before text. Every text template slot then reads from them, which is coherence by construction.
  2. **Offline LLM-generated phrase banks.** Run something like Data Designer once per domain/attribute cell (e.g. category × sentiment × style). Dedup with MinHash, filter with a judge, then freeze the bank as versioned data in the package. Generation stays deterministic and free, and realism approaches LLM quality.
  3. **Persona bank.** A permissively licensed, compact persona list (not PersonaHub, given its NC license) can drive voice and vocabulary choice in templates.
  4. **Validator/judge columns, deterministically.** Report lexicon-sentiment vs rating agreement, keyword-category agreement, distinct-n and MinHash near-dup rate per text column, and a lint for templates with no row references.
  5. **Optional LLM column with caching.** If Misata ever adds an LLM mode, it should key a cache by (config fingerprint, row seed, prompt hash), as DataDreamer does, so re-runs are reproducible.

### Gaps
- No evidence found of any open tool shipping LLM-pre-generated, attribute-keyed phrase banks as a product feature. This appears to be an open niche (based on absence of evidence).
