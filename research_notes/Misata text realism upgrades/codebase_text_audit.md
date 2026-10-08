# Misata text-generation pipeline audit (v0.9.7, branch claude/claim-credits-0lzpbj, HEAD 7c04782)

Method: every claim here was checked by reading code or by running it. The repo was not modified. Scripts and CSV outputs are in
`/tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/textaudit/` (abbreviated `SCRATCH/` below):
`repro.py` (dict schema with customers 1000 / products 500 / reviews 3000 / support_tickets 2000, `__seed__` 11), `trace.py` (monkeypatched routing tracer), `rep.py` (realism_report), `cat_variants.py` (categorical declaration forms), `capacity.py` (grammar enumeration and saturation), `perf.py` (10k-row diversity and timing per semantic), `coh.py` (cross-column coherence).
Sources are cited as file:line in the local clone (`/home/user/misata`). End-to-end generation of the 4-table, 6,500-row repro took 2.23 s.

## 1. Architecture: how a text column gets its values

### Takeaway
A text column is routed by **column name heuristics**, one column at a time, to one of about 80 independent generators. Most of them are `rng.choice` over a flat pool of 8–30 strings. Nothing passes a row-level latent state between columns. Coherence is patched afterwards in post-passes (`apply_realism_rules`), but only for a few pairs: city/country, email/name, category/product_name, review/rating.

### Cited Findings
- Simulator TEXT branch, in priority order: (1) reference-table labels; (2) capsule conditional vocab (`_capsule_conditional_for_column`, one parent column → pool map); (3) user-capsule vocab keyed by column name, but only when its provenance is not `misata-defaults`; (4) `pattern`; (5) unique-text; (6) `smart_generate` (off by default); (7) `_REALISTIC_TYPE_MAP` / `_infer_semantic` → `RealisticTextGenerator.generate`; (8) legacy pool sampler for `sentence/word/address/phone/url` — [misata/simulator.py:2763-3036](/home/user/misata/misata/simulator.py). `smart_mode` defaults to False — [misata/simulator.py:247,287](/home/user/misata/misata/simulator.py).
- `_infer_semantic` is a ~300-line if-chain on column and table substrings that returns a semantic token. Its catch-all is `"description"` — [misata/realism.py:1011-1317](/home/user/misata/misata/realism.py). The simulator ignores that catch-all ([misata/simulator.py:2995](/home/user/misata/misata/simulator.py)), and such columns fall to the legacy `notes()` pool sampler ([misata/simulator.py:3011-3036](/home/user/misata/misata/simulator.py)).
- `RealisticTextGenerator.generate` dispatches on the semantic. If the semantic is declared and a `Lexicon` spec exists, Lexicon wins. Only 4 built-in specs exist: person_name, company_name, vessel_name, medical_procedure — [misata/realism.py:441-451](/home/user/misata/misata/realism.py), [misata/lexicon.py:326-450](/home/user/misata/misata/lexicon.py). The undeclared path dispatches at [misata/realism.py:483-950](/home/user/misata/misata/realism.py).
- `MicrotextGenerator` holds 4 real recursive grammars (review, title, note, comment) — [misata/microtext.py:484-491](/home/user/misata/misata/microtext.py). The other "microtext" methods (ticket_subjects, resolution_notes, transaction_memos, error_messages, clinical_notes, delivery/return/churn/audit reasons, customer_feedback, product_descriptions) are plain `rng.choice(pool)` over lists in `vocab_seeds.py` — [misata/microtext.py:572-679](/home/user/misata/misata/microtext.py).
- The domain capsule is filled by `SemanticVocabularyGenerator`. Its own small `_infer_semantic` decides which assets a schema "needs", and when no asset store has them it inserts `DEFAULT_VOCABULARIES` / `DOMAIN_SPECIFIC_DEFAULTS` tagged `source_name="misata-defaults"` — [misata/vocabulary.py:26-60,128-197](/home/user/misata/misata/vocabulary.py). `DomainCapsule.get_values` returns those defaults ahead of any fallback the caller passes — [misata/domain_capsule.py:54-59](/home/user/misata/misata/domain_capsule.py).
- Columns are generated in declared order. The only reordering is an explicit `depends_on` — [misata/simulator.py:531-556](/home/user/misata/misata/simulator.py). A generator can therefore condition only on columns declared earlier (via `table_data`).
- Post-pass order lives in `apply_realism_rules`: geo → temporal → money → identity → `_fix_category_from_product_name` → route geo → `_fix_review_sentiment` → status/end-date — [misata/realism.py:2337-2403](/home/user/misata/misata/realism.py).
- Routing actually observed in the repro (trace.py):

| column | semantic used | generator |
|---|---|---|
| customers.city/country/company_name/job_title | city/country/company_name/job_title | `rng.choice` over capsule defaults |
| customers.bio | bio | `_generate_bio` |
| customers.notes | notes | `MicroText.notes` |
| products.product_name | product_name | `_generate_product_text`, with 500 per-row `_vocabulary` calls |
| products.description | product_description | `_generate_product_text` → capsule's 8 defaults |
| products.brand | (none) | legacy path: 2,500 × `MicroText.notes(1)` |
| support_tickets.subject and description | support_ticket | `_generate_support_ticket`, independently |
| support_tickets.resolution_notes | resolution_notes | `MicroText.resolution_notes` |
| reviews.review_title | **job_title** (later overwritten) | — |
| reviews.review_text | review | `MicroText.reviews` (called a second time by the post-pass) |

### Inferences
- The architecture is "semantic → independent sampler". Even a perfect pool cannot make subject, description and resolution agree, because nothing shares a row-level draw between them.

### Gaps
- Generator paths for MCP, Studio and story (`misata.generate(story)`) were not traced. The story path for "ecommerce with … reviews and support tickets" produced only customers/products/orders (story.py), so it never reaches these generators.

## 2. Measured diversity per text semantic (reproduction)

### Takeaway
All reported symptoms reproduce, except "declared choices are flattened", which does not reproduce (section 4). Free text built from a real grammar (reviews, notes, addresses, person names) is diverse. Every flat-pool semantic saturates at 8–30 values regardless of row count.

### Cited Findings
Repro (SCRATCH/repro.py, seed 11), distinct/rows:
- products.description **8/500**; top value 14.4%.
- products.brand 389/500 — and it is business-note prose ("Pending review by the billing team…"). This is a new bug, not in the original symptom list.
- support_tickets.subject **120/2000**, description 120/2000, resolution_notes **15/2000** (top 7.6%).
- reviews.review_title 30/3000; review_text 2994/3000.
- customers: company_name 28, job_title 22, country 10, bio 718/1000, notes 805/1000, address 908/1000.
- customers.city was 167/1000 in this repro because a `country` column exists (see section 3).

10k-row isolated measurements (SCRATCH/perf.py; distinct / top-value share / most common 3-word opener share):

| semantic | distinct/10k | top share | top 3-word opener |
|---|---|---|---|
| product_description (default capsule) | 8 | 0.129 | 0.129 |
| resolution_notes | 15 | 0.070 | 0.070 |
| customer_feedback | 12 | 0.089 | 0.089 |
| city (no country column) | 20 | 0.055 | 0.055 |
| job_title | 22 | 0.049 | 0.049 |
| ticket_subject | 25 | 0.045 | 0.045 |
| company_name (undeclared) | 28 | 0.038 | 0.038 |
| short_review_title | 30 | 0.042 | 0.042 |
| support_ticket | 120 | 0.022 | 0.072 |
| product_name | 136 | 0.009 | 0.009 |
| comment_body | 147 | 0.033 | 0.067 |
| email_body | 420 | 0.004 | 0.020 |
| first_name | 424 | 0.008 | 0.008 |
| bio | 1,781 | 0.003 | 0.006 |
| notes | 4,315 | 0.024 | 0.029 |
| person_name | 7,089 | 0.001 | 0.001 |
| ticket_body (with product context) | 8,608 | 0.001 | 0.001 |
| caption | 9,540 | 0.001 | 0.102 |
| review | 9,949 | 0.000 | 0.033 |
| address | 9,995 | 0.000 | 0.000 |

- The Lexicon path, reached only when the semantic is declared, gives company_name 6,720/10k, person_name 9,763/10k and vessel_name 5,508/10k (SCRATCH/perf.py).
- realism_report on the repro scored 0.77, with 15 warnings and 1 fail. It flagged text_templates on products.description (98% duplicates), subject/description (94%) and resolution_notes (99%). It flagged category_balance on company_name, country, job_title, products.description and resolution_notes. It failed placeholder_values on company_name: 3.8% of values are "Acme Retail" (SCRATCH/rep.py).

Cross-column coherence (SCRATCH/coh.py):
- Ticket subject vs description: the first sentence matches in **7.0%** of rows. That is the 1/15 = 6.7% expected from two independent draws over 15 issues.
- 100% of subjects end in "." (full sentences); mean subject length is 88.6 characters.
- Subject matches the declared ticket category's keywords in 8% of shipping tickets, 25% of billing, 26% of account and 62% of technical.
- Resolution notes mention "refund" in 7% of rows, the same rate whether or not the subject is about billing.
- resolution_notes is non-null for 100% of rows in every status, including "open".
- Wording like "urgent" or "immediate" in the description appears at about 9–11% for every priority, so the text is independent of priority.
- Product description shares a ≥4-letter word with the product name in **1%** of rows. "Wren Linen Summer Dress" got "Lightweight and portable with a modern aesthetic."
- Mean price is about $56–68 in every category, so price is not conditioned on category.
- customers.bio: 100% match the "Role | vibe" template; 15 distinct roles; the bio role agrees with job_title in 0%.
- customers.address: 0% contain the row's city; 90% end in a US "ST 12345" form even though countries are France, Canada, India and others.
- review_title is rating-coherent (1★ "Complete waste of money" … 5★ "Best purchase this year").
- 24.5% of review texts contain a generic stand-in subject word (unit/item/product/model/order). The reviews table has only `product_id`, so the actual product name is never woven in.

### Inferences
- The "realism" signal from flat pools is driven by top-share (4–13%) and opener repetition more than by the raw distinct count. A reader notices the same sentence about every 8–25 rows.

### Gaps
- The exact user schema behind the original symptom list was not provided. The symptoms were matched with an equivalent dict schema; city=20 needs the no-country variant (section 3).

## 3. Root cause of each symptom

### Takeaway
The causes are concrete and local: one bad provenance check, two routing rules that send ticket columns to the wrong generator, flat 15-item pools that ignore their `context` argument, single-template generators, and uniform draws over 20–28-value default pools.

### Cited Findings
- **products.description = 8 values, mismatched to the product.** `_generate_product_text` reads `self._vocabulary("product_description", [])`. It uses those values whenever they differ from `PRODUCT_DESCRIPTION_TEMPLATES` (29 entries) — [misata/realism.py:1655-1657](/home/user/misata/misata/realism.py).
  - The capsule always holds the 8 generic `misata-defaults` sentences from [misata/vocabulary.py:35-44](/home/user/misata/misata/vocabulary.py), added whenever a product table has a description column ([misata/vocabulary.py:166-167](/home/user/misata/misata/vocabulary.py)). The check therefore always passes. Built-in defaults beat the category-aware `microtext.product_descriptions`, and provenance is never checked here, unlike [misata/simulator.py:527](/home/user/misata/misata/simulator.py) and [misata/realism.py:483-490](/home/user/misata/misata/realism.py).
  - Even the bypassed path is small: `PRODUCT_DESCRIPTIONS_BY_CATEGORY` has 3–5 sentences per category (electronics 5, clothing 5, home 5, beauty 4, industrial 3, software 3, generic 4) — [misata/vocab_seeds.py:1356](/home/user/misata/misata/vocab_seeds.py), [misata/microtext.py:662-679](/home/user/misata/misata/microtext.py). With no capsule it gives 23 distinct values over 5,000 rows, keyed on category only; Sports and Toys fall back to "generic" (SCRATCH, inline run).
  - It never sees `product_name`, so a description cannot match the name.
- **product_name ignores its category.** `_vocabulary("product_name", PRODUCT_NAME_POOLS[key])` returns the capsule's flat 136-item `_ALL_PRODUCTS` default for every category, because capsule values win over the per-category fallback — [misata/realism.py:1651](/home/user/misata/misata/realism.py), [misata/vocabulary.py:23,33](/home/user/misata/misata/vocabulary.py). `_fix_category_from_product_name` then **rewrites category** from the name — [misata/realism.py:3171](/home/user/misata/misata/realism.py). That is why the declared "Toys" share collapsed to 3%: no pool name maps to it.
- **products.brand gets note sentences.** "brand" matches no rule in `_infer_semantic`, which returns `"description"` ([misata/realism.py:1317](/home/user/misata/misata/realism.py)). The simulator explicitly skips `"description"` ([misata/simulator.py:2995](/home/user/misata/misata/simulator.py)), and with no semantic the column reaches the legacy sampler, which fills a pool of `min(max(size*5,200),10000)` `notes()` sentences ([misata/simulator.py:3011-3036](/home/user/misata/misata/simulator.py)). The same happens to any unrecognised short-label column on a table without a topic semantic.
- **ticket subject is a full sentence; description describes a different issue.** For column `subject` in a ticket table, `_infer_semantic` returns `support_ticket`, not `ticket_subject` — [misata/realism.py:1044-1045](/home/user/misata/misata/realism.py). `description` in a ticket table also maps to `support_ticket` — [misata/realism.py:1175-1177](/home/user/misata/misata/realism.py). Both go to `_generate_support_ticket`, which is 15 issue sentences × 10 context strings (7 non-empty + 3 empty, so 8 distinct) = **120** possible outputs, each column drawn independently — [misata/realism.py:1410-1444](/home/user/misata/misata/realism.py). That matches the measured 120 exactly.
  - The proper `ticket_subjects` pool (25 short subjects, [misata/vocab_seeds.py:1188](/home/user/misata/misata/vocab_seeds.py)) and `ticket_bodies` (which accepts a `subject` context slot, [misata/microtext.py:577-609](/home/user/misata/misata/microtext.py)) are reachable only for columns literally named `ticket_subject`/`issue_subject`/`case_subject` or `ticket_body`/`issue_body`.
- **resolution_notes = 15 values, unrelated fixes.** `MicrotextGenerator.resolution_notes(size, context)` accepts `context` and ignores it, returning `rng.choice` over the 15-item `RESOLUTION_NOTES` — [misata/microtext.py:611-614](/home/user/misata/misata/microtext.py), [misata/vocab_seeds.py:1216](/home/user/misata/misata/vocab_seeds.py). It is also populated for open/pending tickets.
  - The same "accepts context, ignores it" pattern occurs in `error_messages` ([misata/microtext.py:621-624](/home/user/misata/misata/microtext.py)) and `customer_feedback` (accepts `ratings`, ignores it: [misata/microtext.py:657-660](/home/user/misata/misata/microtext.py); `CUSTOMER_FEEDBACK` has 12 items).
- **bio = one pattern.** `_generate_bio` has a single template `f"{Role} | {vibe}{emoji}"` over 15 roles × 15 vibes × 8 distinct extras = 1,800 combinations — [misata/realism.py:1351-1364](/home/user/misata/misata/realism.py). Its capacity is fine; it has no structural variety, and it ignores the job_title, city and name in the same row.
- **city = 20 values in near-equal shares.** With no country column in `table_data`, `city` draws uniformly from `pack.top_cities` — [misata/realism.py:775-782](/home/user/misata/misata/realism.py). en_US has 20 cities ([misata/locales/packs.py:136-141](/home/user/misata/misata/locales/packs.py)). The code comment says "population-ranked", but no weights are applied.
  - With a country column, `_fix_city_country` resamples cities uniformly from `CITIES_BY_COUNTRY` (10–30 per country, 175 total) — [misata/realism.py:2056-2092](/home/user/misata/misata/realism.py). That is why the repro has 167 cities.
  - Undeclared country is uniform over 10 values ([misata/realism.py:740](/home/user/misata/misata/realism.py)). company_name is uniform over the 28-value ecommerce default ([misata/realism.py:704-706](/home/user/misata/misata/realism.py)); 1 in 28 is "Acme Retail", which trips placeholder_values. job_title is uniform over 22 values ([misata/realism.py:731](/home/user/misata/misata/realism.py)). Locale ≠ en_US switches company/job/city to Faker.
- **address does not match city/country.** `type: string` with the guessed `text_type: address` is a legacy type, so it goes to the Faker/`text_gen.full_address` pool ([misata/simulator.py:3016-3026](/home/user/misata/misata/simulator.py)). That yields US "City, ST 12345" strings with no link to the row's city or country. The `MicroText.addresses` street grammar ([misata/microtext.py:681-698](/home/user/misata/misata/microtext.py)) is reached only via semantic `address`.
- **review_title routed to job_title.** `"title" in name` → `job_title` ([misata/realism.py:1150](/home/user/misata/misata/realism.py)). This is masked because `_fix_review_sentiment` overwrites `review_title` afterwards ([misata/realism.py:2471-2488](/home/user/misata/misata/realism.py)). The same rule would put job titles in `article_title`, `listing_title` and similar columns on tables without a media/product hint.

### Inferences
- A pattern runs through several of these bugs: when built-in defaults are placed in the capsule as if they were data, the capsule shadows better per-category or grammar fallbacks. `misata-defaults` provenance should mean "use only when nothing better exists", and only two call sites honour that today.

### Gaps
- The full list of column names that fall through to the legacy notes sampler was not enumerated. "brand" is the confirmed one.

## 4. Are declared-choice categoricals flattened?

### Takeaway
**Not reproduced.** In v0.9.7, declared `choices` without probabilities are Zipf–Mandelbrot weighted and pass `category_balance` with chi² p≈0, in every declaration form tested. The balanced columns realism_report flags are **text-semantic columns drawn uniformly from small pools** (company_name, job_title, country, city, description, resolution_notes). They look like categoricals to the checker.

### Cited Findings
- The categorical branch applies `w_k ∝ (k+q)^-s` with s=0.85, q=2 and a CRC32-seeded rank permutation per column when `sampling="auto"` (the default) — [misata/simulator.py:2053,2071-2095](/home/user/misata/misata/simulator.py). The exception is `size <= len(choices)` without declared probabilities, which samples without replacement — [misata/simulator.py:2067-2069](/home/user/misata/misata/simulator.py).
- cat_variants.py (2,000 rows; `type string + choices`, `string + enum`, `categorical + choices`, and columns named priority/status/tier/category): every column passes, max share 0.28–0.42, min share 0.15–0.28, chi² p_vs_uniform = 0.0. In the full repro, support_tickets.category/priority/status and customers.segment were also uneven (top shares 0.295/0.322/0.316/0.362).
- `_check_category_balance` uses chi² vs uniform and runs only for n≥300, 3≤k≤30 and k/n≤0.05 — [misata/tells.py:260-279](/home/user/misata/misata/tells.py). That is exactly why 8–28-value text pools are flagged as "categories".
- One post-pass does distort declared categories: `_fix_category_from_product_name` overwrote product `category` from the name pool. "Toys" fell to 3.0% because no product-name pool maps to it (repro; [misata/realism.py:3171](/home/user/misata/misata/realism.py)).
- The mild Zipf (s=0.85, q=2) gives only about a 1.8× max/min ratio for 4 choices (computed from the formula). That is detectable at n=2,000, but visually still close to balanced.

### Inferences
- The original symptom most likely came from these pool-based text columns, or from an older build. If the user's report named specific declared-choice columns, rerun cat_variants.py against their exact schema. The coherence engine and post-passes did not flatten declared choices in any form tested.

### Gaps
- `generate_more`, streaming batches, `custom` plugins and the `_REFERENCE_TABLE_RE` path were not tested for this effect.

## 5. Why reviews work, and reusable mechanisms

### Takeaway
Reviews get three things the other text columns lack: (a) a deep compositional grammar with **one entry symbol per conditioning level** (`review_1`..`review_5`); (b) a **post-pass that regenerates text from the final value of the conditioning column**, so column order does not matter; (c) **open-vocabulary slots** filled from row values (`subject`, `when`, `agent`). These three pieces are the template for every other prose column.

### Cited Findings
- Grammar: `Grammar` is a seeded weighted recursive template expander whose unknown placeholders raise — [misata/microtext.py:54-104](/home/user/misata/misata/microtext.py). `_REVIEW_RULES` composes opener + body (1–2 topic-coherent aspect sentences built as noun + verb + tail within one topic) + closer, separately for each star level — [misata/microtext.py:111-215](/home/user/misata/misata/microtext.py).
- Conditioning: `reviews()` maps ratings to levels via `normalize_ratings` (handles 0–10 scales and NaN, with a J-shaped fallback) and expands `review_{lvl}` with per-row slots — [misata/microtext.py:493-543](/home/user/misata/misata/microtext.py). `_prose_context` pulls slot values from the row only if a candidate column has ≥5 distinct values — [misata/realism.py:2421-2441](/home/user/misata/misata/realism.py).
- Order independence: `_fix_review_sentiment` regenerates review_text and review_title from the rating column after all columns exist, and skips protected (user-declared) columns — [misata/realism.py:2444-2488](/home/user/misata/misata/realism.py).
- Capacity tests: `tests/test_microtext_capacity.py` enumerates every reachable string. It asserts that aspect sentences number >800, that 120k five-star reviews give >50k distinct, that the duplicate rate on 20k reviews is <10%, and that every reachable sentence is well-formed (ends with punctuation, no double spaces, capitalised, no stranded participles) — [tests/test_microtext_capacity.py:1-80](/home/user/misata/tests/test_microtext_capacity.py).
- Other reusable pieces:
  - capsule `conditional_vocabularies` (parent column → pool, e.g. brand→model) — [misata/simulator.py:400-430](/home/user/misata/misata/simulator.py), [misata/capsules_registry/sneakers.capsule.json](/home/user/misata/misata/capsules_registry/sneakers.capsule.json);
  - capsule price bands per category — [misata/simulator.py:432](/home/user/misata/misata/simulator.py);
  - `_person_frame`, one joint person draw per table shared by first/last/full/username/email — [misata/realism.py:1673-1685](/home/user/misata/misata/realism.py). This is an existing **latent per-row frame**, the exact pattern a "scenario" needs;
  - `Lexicon` head + composed tail with raw/effective capacity — [misata/lexicon.py:72-312](/home/user/misata/misata/lexicon.py);
  - `detect_sentiment` with POSITIVE/NEGATIVE marker lexicons for conformance checks — [misata/microtext.py:701-722](/home/user/misata/misata/microtext.py).
- Weak spot even in reviews: the reviews table carries only `product_id`, so `_prose_context` finds no `product_name`. 24.5% of reviews use a generic stand-in ("the unit"/"the item"), and the product is never named (SCRATCH/coh.py). No FK join pulls parent attributes into the prose context.

### Inferences — proposed latent "scenario" design
- **ScenarioFrame**: generalise `_person_frame` into `_scenario_frame(table, size)`. It draws one row-level latent per row from a scenario catalogue, before or alongside column generation, and caches it per (table, batch) like person frames. Each column generator becomes a renderer of that latent rather than an independent sampler.
- **Ticket scenario** record: `{issue_key, category, default_priority_dist, product_area, symptom, error_detail, customer_steps, root_cause, fix_action, resolved_bool}`. Rendering:
  - category = scenario.category, overriding uniform/Zipf only when the column is undeclared. When category is declared, condition the scenario draw on the declared category instead.
  - subject = short noun-phrase grammar from (product_area, symptom), e.g. "Checkout payment declined", "2FA code not arriving". This replaces the 120-string sentence pool.
  - description = `ticket_bodies` grammar seeded with the same symptom, steps and error_detail.
  - priority = sample from the scenario's priority distribution (outage → high/urgent).
  - resolution_notes = grammar over root_cause + fix_action, null unless status ∈ {resolved, closed}.
- **Product scenario**: `{category, subcategory, base_noun, material/attribute set, price_band}`. product_name = Lexicon-style composition (brand + attribute + base_noun + variant). description = grammar over the same attributes (material, use-case, care, dimensions). price = log-uniform inside price_band. category is never rewritten afterwards because it caused the draw. Under this design `_fix_category_from_product_name` becomes unnecessary for generated rows.
- Implementation hook: precompute the frame when a table contains ≥2 columns that resolve to the same scenario family (ticket_* or product_*). Pass it through `table_data`, or a `scenario` attribute on the generator, the way `_prose_context` passes slots. Keep a post-pass form, like `_fix_review_sentiment`, so the result is order-independent and declared/protected columns still win.
- Cross-table context: for child tables (reviews, order_items, tickets), join the FK parent's name and category into `_prose_context`. Then reviews can name the real product and tickets can mention the customer's plan or product.

### Gaps
- Scenario catalogue sizes needed for believable variety were not measured. Grammar-level capacity tests (section 6) should gate them.

## 6. Grammar and pool capacity, and where each saturates

### Takeaway
Only the review, note and address generators (and the declared-semantic Lexicon) have capacity above 10⁴. Everything else saturates at its pool size almost immediately, and those pools are drawn uniformly. Notes saturate at exactly 6,253 strings.

### Cited Findings (SCRATCH/capacity.py: exact derivation counts via enumeration, then empirical distinct counts)
- Review derivations with slots fixed: review_1 263,250; review_2 80,730; review_3 78,955,835; review_4 371,010; review_5 236,910. Empirical distinct (unconditioned ratings): 998/1k, 9,876/10k, 88,898/100k.
- Review titles: 5–8 per star level, **30 total**, saturated at 1k rows.
- Notes grammar: **6,253** derivations. Empirical 803/1k, 4,354/10k, 6,253/100k (fully saturated). Top share was 2.4% at 10k, because the `status_note` branch (5 strings, weight 0.4/4.0) is concentrated.
- Comment grammar: 115 derivations; 147 distinct/10k (the extra comes from realism's own comment_body templates).
- Flat pools (`vocab_seeds.py`):
  - TICKET_SUBJECTS 25, RESOLUTION_NOTES 15, TRANSACTION_MEMOS 28, SYSTEM_ERROR_MESSAGES 19;
  - CLINICAL_NOTES 8, CHIEF_COMPLAINTS 12, DISCHARGE_INSTRUCTIONS 10;
  - DELIVERY_INSTRUCTIONS 12, RETURN_REASONS 12, CHURN_REASONS 12, AUDIT_REASONS 12, CUSTOMER_FEEDBACK 12;
  - PRODUCT_DESCRIPTIONS_BY_CATEGORY 3–5 per category (29 total).
- Ticket generators: `_generate_support_ticket` = 120 (15×8). `ticket_bodies` without context = 25×7×6 = 1,050, empirically 1,050/10k (saturated). With a product-name context slot: 8,608/10k.
- Bio: 1,800 (15×15×8); 1,781/10k (near saturation by 10k).
- Company: undeclared default pool 28. The fallback composition (16×16×7 = 1,792) is never reached because the capsule default exists. Lexicon company_name: raw_capacity 35,140, effective 8,000, 6,720/10k.
- Default capsule pools: product_name 136 (flat, all categories), first_name 160, last_name 119, city 178, country 10, job_title 22. Per-category product pools: 16–22 each.
- Addresses: 9,899 house numbers × 61 street names × 9 suffixes, ±24 secondary units → effectively unbounded (9,995/10k).

### Inferences
- A useful CI gate, like `test_microtext_capacity.py`, is: for every semantic, `distinct(10k) / min(10k, plausible real cardinality)` and top-share < 2%. Short labels (job_title, city) are an exception: there, a Zipf shape matters more than cardinality.

### Gaps
- Vocabulary growth (Heaps exponent) per semantic was not measured. Only distinct-string counts were.

## 7. Performance cost per 10k rows

### Takeaway
Text generation is cheap except for grammar expansion. Reviews cost about 1.2 s per 10k rows, and they are generated twice (once in the column, once in the post-pass). Captions and notes cost about 0.45–0.5 s. Per-row Python `rng.choice` loops and per-row `_vocabulary` calls are the hot spots.

### Cited Findings (SCRATCH/perf.py, 10k rows, single `RealisticTextGenerator.generate` call)
- review 1,198 ms; notes 510 ms; caption 448 ms; comment_body 365 ms; product_name 226 ms (one `_vocabulary` + `rng.choice` per row, [misata/realism.py:1647-1653](/home/user/misata/misata/realism.py)); ticket_body 162 ms; short_review_title 138 ms; resolution_notes 111 ms; ticket_subject 101 ms; customer_feedback 89 ms; product_description 79 ms; support_ticket 32 ms; email_body 25 ms; address 15 ms; bio 14 ms; company/job/city/person_name ≤1 ms.
- Lexicon draws per 10k: person 29 ms, company 43 ms, vessel 46 ms, procedure 40 ms.
- trace.py showed `MicroText.reviews` called twice for reviews.review_text: by the column generator and again by `_fix_review_sentiment` ([misata/realism.py:2444-2488](/home/user/misata/misata/realism.py)). The first ~1.2 s/10k is thrown away.
- The pool-based `rng.choice(pool)` inside list comprehensions (e.g. [misata/microtext.py:574,613](/home/user/misata/misata/microtext.py)) does one Python-level RNG call per row. A vectorised `rng.choice(pool, size)` would be about 100× faster, judging by the ≤1 ms vectorised semantics above.
- Grammar.expand does one `rng.choice(len, p=…)` per node, recursively ([misata/microtext.py:87-104](/home/user/misata/misata/microtext.py)).

### Inferences
- A scenario-based ticket/product grammar of about the same depth as reviews would cost roughly 0.5–1.5 s/10k per column. Batching the top-level choices (pre-drawing indices per symbol with vectorised `rng.choice(n, size, p)`) or memoising sub-expansions could cut grammar cost by an estimated several-fold. Not measured.

### Gaps
- Profiling at 1M rows and memory cost were not measured.

## 8. Prioritized fix list (with estimated effort)

### Takeaway
The cheapest high-impact fixes are: the provenance check in `_generate_product_text`, ticket routing, `brand`, and Zipf weights for default pools. A ticket/product scenario frame is the structural fix for cross-column coherence.

### Cited Findings (each fix maps to a root cause cited in section 3)

| # | Fix | Where | Effort |
|---|---|---|---|
| P0 | Treat `misata-defaults` capsule vocab as a fallback: in `_generate_product_text`, use capsule descriptions only when provenance ≠ misata-defaults, else `microtext.product_descriptions`. Same for `product_name`: prefer `PRODUCT_NAME_POOLS[key]` over the flat default. This fixes the 8-value descriptions and the category rewrite / Toys collapse. | [realism.py:1647-1657](/home/user/misata/misata/realism.py) | S (<0.5 day) |
| P0 | Route ticket `subject`/`title` → `ticket_subject` (short noun phrase). Generate `description` with `ticket_bodies(context={"subject": subject_col})` so the body starts from that row's subject. | [realism.py:1044,1175](/home/user/misata/misata/realism.py), [microtext.py:577](/home/user/misata/misata/microtext.py) | S |
| P0 | Add `brand`/`manufacturer`/`vendor` → a brand semantic (capsule brands or a Lexicon brand spec). Change the simulator's fall-through for unknown short columns on non-notes names to a label generator, not `notes()`. | [realism.py:1317](/home/user/misata/misata/realism.py), [simulator.py:2995-3036](/home/user/misata/misata/simulator.py) | S |
| P1 | `resolution_notes`: honour `context`. Pick fix families by ticket category/subject keyword, and make the column null when status ∈ {open, pending, new}. Add a `_fix_ticket_coherence` post-pass modelled on `_fix_review_sentiment`. | [microtext.py:611](/home/user/misata/misata/microtext.py), [realism.py:2398](/home/user/misata/misata/realism.py) | M (1–2 days) |
| P1 | Zipf/population-weight undeclared label pools (city top_cities, country, company, job_title, CITIES_BY_COUNTRY), reusing the categorical branch's (k+q)^-s with a per-column permutation. Remove "Acme"-style placeholder names from `COMPANY_NAMES` heads, or switch undeclared company_name to the Lexicon company spec (6,720/10k). | [realism.py:704-782,2056-2092](/home/user/misata/misata/realism.py), [simulator.py:2087-2095](/home/user/misata/misata/simulator.py) | S–M |
| P1 | Stop routing `*title*` to job_title unless the column also contains job, position or role context. Route review_title → short_review_title directly. | [realism.py:1150](/home/user/misata/misata/realism.py) | S |
| P1 | Remove the double review generation: skip the column-time draw when the post-pass will regenerate, or have the post-pass skip when the text was already generated from the same rating. Saves ~1.2 s/10k. | [realism.py:1403-1408,2444-2488](/home/user/misata/misata/realism.py) | S |
| P2 | Product scenario frame: (category → subcategory → base noun + attributes + price band). Name, description and price all render from it. Grow `PRODUCT_DESCRIPTIONS_BY_CATEGORY` into a grammar (feature, material, use-case, care, warranty sentences per category) with a capacity test. | new `_scenario_frame` beside `_person_frame` ([realism.py:1673](/home/user/misata/misata/realism.py)); capsule price bands ([simulator.py:432](/home/user/misata/misata/simulator.py)) | L (3–5 days) |
| P2 | Ticket scenario frame: (category, product_area, symptom, root_cause, fix, priority distribution) driving subject, description, priority and resolution_notes. Expand subject/description/resolution into grammars with enumerated capacity tests. | microtext.py + vocab_seeds.py | L (3–5 days) |
| P2 | Bio grammar with several structures (sentence, pipe list, "X at Y"), conditioned on job_title, city and company when present. | [realism.py:1351](/home/user/misata/misata/realism.py) | M |
| P2 | Address coherence: route `address` to the semantic path (MicroText street grammar), with city/state/postcode drawn from the row's city and country rather than Faker US strings. | [simulator.py:2981-3026](/home/user/misata/misata/simulator.py), [realism.py:2056-2186](/home/user/misata/misata/realism.py) | M |
| P2 | FK-joined prose context: let `_prose_context` pull the parent's `product_name`/`name` via FK, so reviews and tickets name the real product. | [realism.py:2421](/home/user/misata/misata/realism.py) | M |
| P3 | Turn the remaining 8–28-item flat pools (customer_feedback ignoring ratings, error_messages, memos, clinical, reasons) into small grammars. Make customer_feedback rating-conditioned like reviews. | [microtext.py:616-660](/home/user/misata/misata/microtext.py) | M each |
| P3 | Capacity and coherence CI: extend `tests/test_microtext_capacity.py` with per-semantic distinct@10k, top-share, and an enumerated well-formedness check for every new grammar; add coherence asserts (subject↔description keyword overlap, product name↔description noun overlap). | tests/ | M |
| P3 | Vectorise per-row `rng.choice(pool)` loops and per-row `_vocabulary` calls. | [microtext.py:572-679](/home/user/misata/misata/microtext.py), [realism.py:1647](/home/user/misata/misata/realism.py) | S |

### Inferences
- The P0 items alone should lift products.description from 8 to about 23 distinct values (measured with capsule=None), make subjects short, and make the description's first clause match the subject. Expected text_templates and category_balance warnings drop on description, subject and brand. These effects are inferred from the code paths, not measured after a patch.
- Effort estimates are engineering judgement, not measured.

### Gaps
- No patch was applied or benchmarked, per the constraint against modifying the repo. Post-fix realism_report scores are therefore not available.
