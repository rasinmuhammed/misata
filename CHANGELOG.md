# Changelog

All notable changes to Misata will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0.4] - 2026-06-11

Patch release. 761 tests, 0 failures.

### Fixed

- **`pattern` and `text_type` now reach the engine from dict schemas.** `from_dict_schema`
  dropped both keys, so the pattern codes shipped in 0.8.0.3 and explicit semantic text
  types were unreachable for Studio, MCP agents, and any non-Python caller.
- **Thousands separators in stories.** "A fintech with 2,000 customers" previously
  parsed the scale as 0 (the regex stopped at the comma) and crashed generation.
  Scale extraction now accepts `2,000`, `20,000`, and `1.5M` alike.
- **Declared `text_type` wins over column-name inference.** A column named `contact`
  declared as `person_name` previously generated description text because name-based
  inference outranked the explicit declaration. The schema's word is now final; inference
  only fills gaps.

## [0.8.0.3] - 2026-06-11

Enterprise simulation release. Misata can now generate a complete, internally-consistent
company dataset where every number ties together — the kind of deeply interconnected data
no other synthetic-data library produces. 757 tests, 0 failures.

### Added

- **Realism core.** Six deterministic mechanisms that kill the classic synthetic-data
  tells: joint name-gender-culture identities, semantic temporal profiles (appointments
  on 15-minute business grids; no nanosecond noise anywhere), Zipf-Mandelbrot categorical
  marginals, geographic facts (289 city coordinates; route distances and travel times are
  computed, not sampled), rating-conformant grammar microtext (lorem ipsum removed), and
  numeric quantization (durations on calendar grids, charm prices).
- **Compositional schema synthesis.** Unknown domains get structural multi-table schemas
  composed from the story's own entities (archetype lattice + FK wiring) instead of
  template confabulation or a single generic table; weak keyword matches are gated.
- **MCP schema-first agent contract.** New `generate_from_schema` tool: the agent designs
  the schema dict, Misata returns data plus a per-relationship integrity proof.
- **Capsules.** Shareable single-file domain vocabulary packs: mine from CSVs
  (`misata capsule create --from-csv`), generate once with an LLM, or write by hand;
  `generate(..., capsule=...)` makes them drive matching columns deterministically.
- **Pattern codes.** `pattern: "REC-\\d{5}"` on text columns for SKU/reference codes.


- **Flagship pharma CRO domain.** `misata.generate("A pharmaceutical CRO with 60
  employees, 20 clinical research projects, and clients")` now produces a full four-table
  company (clients → projects → employees → timesheets) whose figures reconcile end to
  end: `timesheets.billed_usd = hours * employee.hourly_rate`, `projects.revenue_usd =
  sum(billed)`, `projects.total_hours = sum(hours)`, timesheet dates inside each project's
  window, and a 24h/day capacity cap. Run a `GROUP BY ... JOIN` and the totals add up.
- **`from_dict_schema` full feature passthrough.** The plain-dict entry point (used by
  LLMs and non-Python callers) now exposes the complete engine: `distribution` and its
  shape parameters (`mu`/`sigma`/`mean`/`std`/`alpha`/...), `probabilities`, `formula`,
  `depends_on`, `mapping`, `zero_inflate`, `rollup`, `references`, `relative_to`,
  `null_if`, and boolean `probability`. Previously these were silently dropped, so a dict
  schema lost its distributions, exact percentages, and formulas.

### Fixed

- **Cross-table formula resolution.** `@parent.column` lookups (e.g. `hours *
  @employees.hourly_rate`) now resolve the parent's real primary key (`employee_id`,
  `customer_id`) instead of a hardcoded `id`, and the generation context retains the
  parent columns a child formula references. These lookups previously returned 0 / garbage
  on any schema not keyed on a literal `id`.
- **Constraint → formula ordering.** Formula columns are re-applied after business-rule
  constraints, so a derived value stays consistent when a constraint changes its inputs.
  Before this fix, a capacity cap that reduced `hours` left `billed_usd` computed from the
  pre-cap value, and the revenue roll-up summed the stale figures.

## [0.8.0.2] - 2026-06-10

Realism and correctness release. Focus: making generated relational data *reconcile* the
way real data does, and closing a multi-batch correctness gap. 633 tests, 0 failures.

### Added

- **Cross-table aggregate roll-ups** (`misata/rollups.py`) — parent summary columns now
  reconcile with child rows: `customers.total_spent` equals `sum(orders.amount)` per
  customer, surviving a `GROUP BY ... JOIN`. Declare on a column via
  `distribution_params={"rollup": {"from_table": "orders", "fk": "customer_id",
  "agg": "sum", "column": "amount"}}`. Aggregations: `sum`, `count`, `mean`, `max`, `min`.
  Optional `where` filter (`{"status": "completed"}`, scalar or list). Exact
  reconciliation, FK-safe, deterministic.
- **Zero-config roll-up inference** — when a parent column name explicitly names a child
  table (`num_orders`, `total_orders`), the roll-up is inferred automatically. Deliberately
  conservative: declines on ambiguous names (`total_sales`, `stock_count`) rather than
  produce a wrong number, so there are no false positives on the built-in domains.
- **Zero-inflated distributions** — `distribution_params={"zero_inflate": 0.3}` injects a
  spike of structural zeros (free-tier, no-spend periods) on top of any base distribution,
  applied after the `min` clamp so structural zeros are not lifted. Opt-in; not
  auto-applied to curated domains that already model semantic zeros.

### Fixed

- **Relative-curve cross-batch convergence** — relative outcome curves
  (`relative_value` control points) now hold their shape *exactly* regardless of
  `batch_size`. Previously, generating a >10k-row table in multiple batches drifted the
  shape (e.g. a 4× December/January ratio fell to ~3.5× at small batch sizes). Per-month
  factors are now interpolated for all months and corrected against actual accumulated row
  counts.
- **YAML round-trip for generation features** — `rollup`, `zero_inflate`, `depends_on`,
  `mapping`, `formula`, and `inherits_curve_from` now survive
  `save_yaml_schema` → `load_yaml_schema`. They were previously dropped on load, silently
  disabling these features for schemas committed to `misata.yaml`.

### Notes

- The accompanying arXiv preprint (arXiv:2606.08736v1) describes the exact-aggregate
  engine; this release extends it from temporal aggregate conformance toward *relational*
  aggregate coherence (parent/child roll-ups).

## [0.8.0] - 2026-05-10

### Research

- Posted **"Declarative Outcome-Conformant Synthesis: Exact, Closed-Form Specification Satisfaction and a Conformance Benchmark"** (arXiv:2606.08736v1) — an arXiv preprint formalising Misata's exact-aggregate engine. Shows the mechanism is exactly conditional-sum sampling of a Gamma population (Lukacs' characterisation), contributes **SpecBench** (a conformance benchmark for cold-start relational synthesis), and reports that off-the-shelf imitation synthesisers miss declared monthly aggregates by 74–86% (per-period-conditioned ~19%) while the closed-form engine reaches exactly 0.

### Added

#### Mimic mode — privacy-safe synthetic twins from real CSVs
- `misata/profiler.py` — `DataProfiler` class that analyzes every column: distribution fitting (lognormal/normal/uniform), cardinality detection, date range capture, semantic type inference
- `misata.mimic(source, rows, seed)` — one-liner public API; accepts CSV path, DataFrame, or list of either for multi-table mimicry
- `misata mimic <file.csv>` CLI command with `--rows`, `--output`, `--seed` flags
- Detects email, name, city, country, latitude, URL, phone, and more automatically

#### Geospatial realism
- `CITY_GEODATA` in `vocab_seeds.py` — 60+ cities across 20 countries with real centroid coordinates and postal prefixes
- `_generate_latitude`, `_generate_longitude` — coordinates cluster around real city centroids with natural Gaussian scatter (~20–35 km)
- `_generate_postal_code` — format-correct codes using per-country prefix patterns
- `text_type: "latitude"`, `"longitude"`, `"postal_code"` — auto-detected from column names `lat`, `lng`, `zip`, `postal_code`, etc.

#### Long-form text generators
- `_generate_review` — multi-sentence product reviews, sentiment-weighted 65/22/13% positive/neutral/negative
- `_generate_support_ticket` — realistic issue descriptions with context sentences
- `_generate_email_body` — greeting + business body + closing format
- All three auto-detected from column names and table context

#### Correlation engine (Iman-Conover)
- `Table.correlations` field — declare pairwise Pearson correlations: `[{"col_a": "age", "col_b": "salary", "r": 0.65}]`
- `DataSimulator._apply_correlations` — Cholesky decomposition → correlated normal scores → rank re-ordering; preserves marginal distributions exactly
- Supports multiple pairs simultaneously; silently skips if correlation matrix is not positive-definite

#### Anomaly injection
- `anomaly_rate` param on any `Column` — e.g. `"anomaly_rate": 0.02` injects outliers into 2% of rows
- Numeric: values at 3–6 standard deviations from the mean
- Categorical/text: sentinel `"__anomaly__"` value for downstream detection
- Applies after null_if and formulas, before outcome curves

#### Jupyter magic
- `misata/magic.py` — `%load_ext misata.magic` registers `%%misata` cell magic
- Options: `rows=N seed=N` on the magic line
- Injects `_misata` dict and per-table `<name>_df` variables into notebook namespace
- Renders HTML summary table with row counts and column previews

#### REST API — `POST /generate`
- New endpoint on the existing `misata serve` server
- Body: `{story, rows, seed, format}` — no API key required, uses rule-based StoryParser
- Response: `{tables: {...}, meta: {domain, row_counts}}`
- `format: "columns"` returns dict-of-arrays instead of list-of-records

#### Documentation
- `docs/guides/mimic.md` — full mimic mode reference
- `docs/guides/geospatial.md` — coordinate generation and postal codes
- `docs/guides/long-form-text.md` — reviews, tickets, email bodies, captions
- `docs/guides/correlations.md` — Iman-Conover engine with domain examples
- `docs/guides/anomaly-injection.md` — outlier injection with fraud detection example
- `docs/guides/jupyter.md` — magic setup and workflow
- `docs/guides/rest-api.md` — HTTP API reference with curl, JS, and Go examples
- All 7 pages added to `mkdocs.yml` navigation

#### Five new domain schemas
- **CRM** — `companies`, `contacts`, `deals`, `activities`; pipeline stages, deal values, close dates, activity types
- **Crypto / Web3** — `wallets`, `tokens`, `transactions`, `token_prices`; blockchain addresses, wallet balances, token symbols, USD prices
- **Insurance** — `customers`, `policies`, `claims`, `payments`; policy types, premium amounts, claim status, coverage limits
- **Travel** — `users`, `hotels`, `flights`, `bookings`, `reviews`; airport codes, seat classes, booking status, cancellation reasons (conditional null)
- **Streaming** — `subscribers`, `content`, `watch_history`, `ratings`; churn coherence (`churned_at` only set when `is_churned = true`), content genres, watch duration
- All five domains fully integrated into the 18-domain test matrix (113 tests: parse + validate, generate at two scales, FK integrity, YAML roundtrip, determinism, rows=1)

#### Locale-aware phone numbers
- `_generate_phone_number()` in `realism.py` — uses locale pack's `phone_prefix` to produce format-correct numbers (US: `+1-###-###-####`, UK: `+44 #### ######`, IN: `+91-#####-#####`, DE: `+49 ### #######`, etc.)
- Columns named `phone`, `mobile`, `telephone`, or `tel` automatically route to the locale-aware generator
- Removed phone from the Faker passthrough list so custom formatting is always applied

#### Temporal coherence improvements
- `after_column` + `max_date: "today"` — date columns derived from another column (e.g. `hire_date` after `date_of_birth`) are now capped at today, preventing future-dated hire dates
- `date_diff_to: "today"` — float column deriving exact tenure in fractional years from a reference date column (e.g. `tenure_years` from `hire_date`)
- Age coherence enforced in HR schema: employees are at least 18 years old at hire, never hired in the future
- Hire date → tenure derived on the same row without separate distributions

#### Name-derived email addresses
- Email columns adjacent to `first_name` + `last_name` columns in the same table automatically adopt the person's name (`jane.doe@acmecorp.com`) instead of generating unrelated random emails

#### DetectionReport and preview() API
- `DetectionReport` dataclass — structured account of what `StoryParser` understood: `domain`, `domain_confidence` (`"high"` / `"low"` / `"none"`), `matched_keywords`, `near_misses`, `scale_params`, `temporal_events`, `locale`, `table_preview`, `total_rows`, `warnings`
- `DetectionReport.summary()` — renders a concise multi-line human-readable summary with table widths and column counts
- `misata.preview(story, rows)` — one-liner public API returning a `DetectionReport`; call this before `generate()` for a confirmation step
- `StoryParser.detection_report()` — access the last parse's report directly on the parser instance

#### Scored domain detection
- Domain detection changed from first-match (dict order) to scored: **+5** if the literal domain name appears in the story, **+1** per matched keyword
- Prevents "fintech with crypto wallets" from matching SaaS just because "churn" appears; the "fintech" literal gives fintech +5 and wins
- `crypto` moved before `fintech` in `DOMAIN_KEYWORDS` (both have "wallet"; crypto keywords are more specific)
- `_matched_keywords` and `_near_misses` recorded on every parse for transparent reporting

#### JSON Schema for misata.yaml
- `schema/misata.schema.json` and `misata/_schemas/misata.schema.json` — Draft 2020-12 JSON Schema with descriptions on every field, all 18 domain names enumerated, all text types enumerated
- `misata.json_schema()` — public function returning the loaded schema dict
- `misata.JSON_SCHEMA_URL` — constant pointing to the published schema URL for the `yaml-language-server` header
- `misata init` scaffolds `misata.yaml` with `# yaml-language-server: $schema=...` header for editor auto-complete

#### Actionable validation error messages
- `SchemaValidationError.issues` now includes fix hints on every message:
  - Probability sum: `"Fix: scale all values down by ×0.8333, or adjust one value by -0.2000"`
  - Length mismatch: `"Fix: add N more probabilities entries"`
  - FK without relationship: suggests the exact `Relationship(parent_table='...', ...)` call to add
  - OutcomeCurve / ScenarioEvent column not found: `"Fix: columns in 'table': col1, col2, ..."`
  - Cycle detection: `"Circular dependency: A → B → A"`

#### MCP server — expose Misata to AI agents
- `misata/mcp/server.py` — FastMCP server exposing five tools over stdio:
  - `list_domains` — lists all 18 domains with trigger keywords and a sample story each
  - `preview_story` — dry-run detection, table preview, row counts, and warnings without generating
  - `inspect_schema` — full schema (every column, type, params, relationships, outcome curves)
  - `generate_dataset` — generates CSV files, returns paths + per-table row samples; `sample_rows` capped at 50
  - `validate_yaml` — two-layer structural (JSON Schema) + semantic (fix-hint) YAML validation
- All five tools wrap exceptions and return `{"ok": false, "error": "...", "suggestion": "..."}` — agents recover gracefully instead of seeing Python tracebacks
- `misata-mcp` console script — launch via stdio; Claude Desktop, Cursor, Windsurf, Zed, Continue all supported
- `pip install "misata[mcp]"` — new optional extra pulling `mcp>=1.0.0` and `jsonschema>=4.0.0`
- `smithery.yaml` in repo root — enables auto-indexing on Smithery.ai
- `docs/guides/mcp.md` — install guide, Claude Desktop config, tool reference, example prompts, MCP Inspector debugging

#### Narrative story patterns — quarterly, seasonal, and multiplier
- **Quarterly modifiers**: `"Q4 spike"`, `"dip in Q3"`, `"strong Q4"`, `"Q1 slump"` expand to all three constituent months with the appropriate factor
- **Quarter-level anchors**: `"$100k in Q2"` pins months 4, 5, and 6 all at $100k
- **Named seasonal events**: `"Black Friday"` → Nov ×1.55, `"Christmas"` → Dec ×1.40, `"holiday season"` → Dec ×1.35, `"summer slump"` → Jul+Aug ×0.75, `"back to school"` → Aug ×1.20, `"New Year"` → Jan ×1.25, `"tax season"` → Apr ×1.20
- **Relative multipliers**: `"doubled"` → 2×, `"tripled"` → 3×, `"10x growth"` → 10×, `"halved"` → 0.5×, `"Nx"` notation, `"grew 300%"` → 4× factor
- **One-anchor multiplier**: `"$50k in January, doubled by December"` pins Jan at $50k and derives Dec at $100k exactly
- **Extended qualitative keywords**: `slump`, `boom`, `crash`, `slow`, `strong`, `push`, `flat` alongside existing `dip`, `peak`, `spike`, `surge`
- `CURVE_SIGNAL_TOKENS` extended to trigger on `"q1"–"q4"`, `"black friday"`, `"christmas"`, `"summer slump"`, `"doubled"`, `"tripled"`, `"halved"`

#### Examples and test coverage
- `examples/narrative_to_data.py` — end-to-end demo: `preview()` → generate → ASCII monthly bar chart → assertions on curve shape
- `tests/test_mcp_server.py` — 17 tests covering all five tools, error recovery contract, determinism, temp-dir behaviour, sample cap
- `tests/test_narrative_patterns.py` — 30 tests: quarter modifiers, named events, multipliers, extended keywords, integration stories
- `tests/test_domain_hardening.py` — 113 tests: 18 domains × (parse+validate, generate at 2 scales, FK integrity, YAML roundtrip, determinism, rows=1)
- `tests/test_detection_report.py` — 13 tests: DetectionReport contract, confidence levels, near_misses, table preview, no-domain warnings
- Total test count: **581 passing**

## [0.7.2] - 2026-04-20

### Added

#### Food delivery domain
- `StoryParser._build_fooddelivery_schema` — new domain with 5 tables: `restaurants`, `customers`, `couriers`, `orders`, `order_items`
- Cuisine type, delivery fee, avg prep time, vehicle type, payment method, customer rating columns — all with calibrated distributions
- `delivered_at` uses `after_column: placed_at` so every order delivery is chronologically valid
- `DOMAIN_KEYWORDS["fooddelivery"]` moved before `ecommerce` so UberEats/DoorDash stories don't fall through to the generic ecommerce schema

#### Social domain improvements
- `_generate_caption` — realistic social media captions with emoji and hashtags via template engine (replaces product-description Lorem Ipsum)
- `_generate_bio` — role + vibe + optional emoji format (e.g. "Developer | sharing what I love 🚀")
- `caption` and `bio` text types now route correctly through `_infer_semantic` in `RealisticTextGenerator`

#### Ecommerce domain improvements
- `products` table added (product_id, name, category, price, stock_count, rating)
- `orders` now FK to `products` for realistic item linkage

#### Realism engine hardening
- Fixed `Set[str]` / `List[str]` typing imports in `realism.py` (Python 3.10 built-in generics)
- `_infer_semantic` extended to handle `bio`, `caption`, `description`, and product/item/listing tables

#### Simulator improvements
- Integer columns with only `min`/`max` (no `mean`) now default to `"uniform"` distribution (was `"normal"` — produced mean-heavy clusters)
- `after_column` date param: generated date is always ≥ base column + `min_delta_days`
- `_REALISTIC_TYPE_MAP` expanded with `city`, `state`, `country`, `username`, `product_name`, `description`

#### Distribution fixes
- Logistics `estimated_hours`: lognormal instead of uniform
- Logistics `delivered_at`: `after_column: shipped_at` — eliminates delivery-before-shipment rows
- HR `net_pay`: formula column (`gross_pay * (1 - tax_withheld)`) — eliminates net > gross violations
- Social `follower_count`: lognormal power-law (median ~245, tail ~50M) — replaced broken Pareto
- Fintech `transaction_amount` / `amount`: sigma lowered to 1.3 for realistic spread
- Real estate `state`: US states categorical with real population-weighted probabilities
- Marketplace `price` / `amount`: lognormal with realistic e-commerce spread

### Fixed
- `parent_comment_id` in social `comments` was compressing to max ~167; now uniform up to `num_comments`

## [0.7.1] - 2026-04-16

### Added

#### Localisation system — 15 locale data packs, automatic story detection
- `misata/locales/packs.py` — `LocalePack` dataclass with real statistical data per country: salary medians (OECD/World Bank/ILO 2023–24), lognormal salary priors, age distributions, currency codes and symbols, phone prefixes, postcode patterns, national ID formats (SSN, NIN, Steuer-IdNr, NIE, CPF, Aadhaar, etc.), ranked top cities, company suffixes, VAT rates, timezones
- 15 built-in locales: `en_US`, `en_GB`, `de_DE`, `fr_FR`, `pt_BR`, `es_ES`, `hi_IN`, `ja_JP`, `zh_CN`, `ar_SA`, `ko_KR`, `nl_NL`, `it_IT`, `pl_PL`, `tr_TR`
- `misata/locales/detector.py` — `detect_locale_from_story(story)`: keyword + currency symbol + city scoring with per-signal weights; fires automatically from any story string — no annotation needed
- `misata/locales/registry.py` — `LocaleRegistry` with per-locale Faker instance cache (process-level singleton); `supported_locales()` list
- `TextGenerator(locale=)` — Faker-backed locale-aware generation for names, addresses, phone numbers, postcodes, and national IDs; pure-Python `_expand_pattern()` handles regex patterns (`\d{5}`, `[A-Z]{2}\d{3}`) with no additional dependencies
- `RealisticTextGenerator(locale=)` — uses Faker for locale-specific names, cities, and company suffixes; asset-backed vocabulary (Kaggle enrichment) always takes precedence over locale defaults
- `apply_locale_priors(column, params, locale)` in `domain_priors.py` — automatically overlays locale-specific lognormal salary distributions and age normal priors; only fires when the user has not explicitly set distribution parameters
- `StoryParser` auto-detects locale and injects it into `schema.realism.locale` — "Brazilian fintech with R$ payments" → `pt_BR` with no extra code
- `misata generate --locale de_DE` — CLI flag to force or override locale at generation time
- `misata.LocalePack`, `misata.LocaleRegistry`, `misata.LOCALE_PACKS`, `misata.detect_locale`, `misata.get_locale_pack` all exported from top-level `__init__.py`
- `faker>=20.0.0` added as a core dependency (was already used transitively; now declared)

#### YAML schema-as-code (`misata init`)
- `misata/yaml_schema.py` — first-class YAML schema format: more readable than Synth's JSON, no LLM required (unlike syda)
- `misata.load_yaml_schema(path)` — load a `misata.yaml` file into a `SchemaConfig` for immediate generation
- `misata.save_yaml_schema(schema, path)` — round-trip serialize any `SchemaConfig` back to YAML; commit it to git
- Arrow shorthand for relationships: `"users.user_id → orders.user_id"` (also accepts ASCII `->`)
- Per-table and top-level constraints in YAML with explicit `table:` field for unambiguous assignment
- `MISATA_YAML_TEMPLATE` — commented starter schema written by `misata init`
- `misata generate` auto-detects `misata.yaml` in the working directory if no other source is given

#### `misata init` CLI command
- Three modes: `misata init` (template scaffold), `misata init --db <url>` (DB introspection), `misata init --story "..."` (story parse)
- `--output` / `--force` flags; refuses to overwrite without `--force`
- Makes Misata's workflow parallel to `synth init` — schema lives in git, reproducible across the whole team

#### New constraint types
- `InequalityConstraint(col_a, operator, col_b)` — enforces `col_a OP col_b` (e.g. `price > cost`) on every row; fixes violations by adjusting `col_a` with a small offset
- `ColumnRangeConstraint(column, low_col, high_col)` — clips `column` to `[low_col, high_col]` per row
- `ConstraintEngine.from_schema_constraint(c)` — factory method dispatching all constraint types from a `schema.Constraint` Pydantic model
- `schema.Constraint` model extended with `inequality` and `col_range` types and five new optional fields: `column_a`, `operator`, `column_b`, `low_column`, `high_column`
- Both constraint types available in `misata.yaml` constraints list and in `__all__`

### Changed
- README restructured to show all six generation entry points with DB seeding as a hero workflow; comparison table now includes Synth and syda
- Version badge and `__version__` updated to 0.8.0

### Tests
- 31 new tests: `tests/test_yaml_schema.py` (load/save/round-trip, arrow relationships, constraint parsing), `TestInequalityConstraint`, `TestColumnRangeConstraint`, `TestCLIInit`; suite grows from 283 → 314 passing

---

## [0.7.0] - 2026-04-14

### Added

#### Document generation
- `misata.generate_documents(tables, template, table, output_dir, format)` — renders one document per row from any generated table; output can be `"html"` (default), `"markdown"`, `"txt"`, or `"pdf"` (requires `pip install "misata[documents]"`)
- `DocumentTemplate` — Jinja2-backed renderer; accepts a built-in name, a raw template string, or a file path
- Five built-in templates: `"invoice"`, `"patient_report"`, `"user_profile"`, `"transaction_receipt"`, `"generic"`
- `"auto"` mode: picks the best built-in template by inspecting column names
- `misata.list_document_templates()` — returns all built-in template names
- Added `jinja2>=3.1.0` to core dependencies; added `documents` optional extras group (`weasyprint`)

#### Multi-provider LLM support
- `LLMSchemaGenerator` now supports five providers: `"openai"`, `"groq"`, `"anthropic"`, `"gemini"`, `"ollama"`
- Anthropic uses its native SDK wire format; Gemini uses the OpenAI-compatible endpoint; Ollama works fully locally (no API key)
- Provider detected automatically from environment keys or explicit `provider=` argument

#### Custom callable generators
- `generate_from_schema(schema, custom_generators={table: {col: fn}})` — override any column with a Python callable
- Two supported signatures: vectorized `fn(df, context_tables)` returning an array, or per-row `fn(row, col_name, context_tables)` returning a scalar
- Signature detected automatically via `inspect.signature`

#### Schema import and FK integrity
- `misata.from_dict_schema(schemas, row_count, seed)` — converts a plain `{table: {col: {type, constraints}}}` dict into a `SchemaConfig`; supports 20+ type aliases, `enum`/`choices`, `min`/`max`, `nullable`, `unique`, `foreign_key`, `primary_key`, `min_date`/`max_date`
- `misata.verify_integrity(tables, schema)` → `IntegrityReport` — post-generation referential integrity check with orphan counts and sample values; call `.raise_if_invalid()` to turn failures into exceptions

#### Incremental generation
- `misata.generate_more(tables, schema, n, seed)` — append `n` more rows to an existing dataset; scales all tables proportionally, offsets IDs to avoid collisions

#### Kaggle vocabulary enrichment
- `misata.enrich_from_kaggle(domain)` — downloads CC0-licensed datasets from Kaggle and stores vocabulary (names, companies, cities, etc.) in `~/.misata/assets/`; all subsequent `generate()` calls use the richer vocabulary automatically
- `misata.kaggle_find(domain)` — list candidate datasets without downloading
- `misata.kaggle_status()` — print a summary of locally stored vocabulary assets with value counts
- `misata.ingest_csv_vocab(path, domain, column_map)` — import any local CSV into the asset store without Kaggle credentials
- `misata.detect_column_assets(columns)` — heuristically map 60+ column name patterns to semantic asset names
- Requires `pip install kaggle` and Kaggle credentials for auto-download; manual CSV import has no extra deps

#### Domain-aware text generation
- Name, email, company, city, state, and job-title columns now route through `RealisticTextGenerator` (domain capsule + Kaggle asset store) by default, replacing the lorem-ipsum pool

### Fixed
- Country columns no longer output lorem-ipsum text — changed to categorical with 15 real country names and realistic probability weights
- `customer_id`, `user_id`, `order_id` in generated schemas now produce unique values instead of repeating the `max` bound
- Duplicate names/emails on small datasets fixed (pool size was capped at `min(n, 10 000)`, now scales at `5×n` with a 200-item floor)
- Multi-batch outcome curve generation no longer crashes with `ValueError: Exhausted unique values` — unique pools auto-extend instead of raising

## [0.6.1] - 2026-04-11

### Changed
- Bump Development Status classifier to Production/Stable
- Add `Testing::Mocking` and `Utilities` PyPI classifiers

### Documentation
- Rewrote all 5 `docs/` pages with working one-liner API and real output numbers
- Rewrote `QUICKSTART.md` to use `misata.generate()` / `misata.parse()` / `misata.generate_from_schema()`
- Added Colab quickstart notebook (`notebooks/quickstart.ipynb`) with matplotlib charts
- Added Colab badge to README
- Added "Run the examples" section to README

## [0.6.0] - 2026-04-11

### Added

#### One-liner public API
- `misata.generate(story, rows, seed)` — story → dict of DataFrames in one call, no imports needed beyond `import misata`
- `misata.parse(story, rows)` — parse a story to a `SchemaConfig` for inspection before generation
- `misata.generate_from_schema(schema)` — generate from an already-built schema
- `SchemaConfig.summary()` — human-readable schema overview for REPL and notebooks

#### Schema validation
- `validate_schema(schema)` — pre-generation validation that collects all issues at once and raises `SchemaValidationError` with a full bullet-list of problems
- Checks: duplicate table names, FK columns without a backing Relationship, categorical probability sums, outcome curve references, circular dependency detection

#### LLM parser hardening
- Exponential backoff retry (1s / 2s / 4s) on transient errors (rate limit, 429, timeout, 5xx)
- `_extract_json()` strips markdown fences and extracts the first JSON object from prose responses
- Graceful handling of malformed LLM output: skips tables without names, skips non-dict columns, normalizes type aliases — warns instead of crashing

#### Story parser fixes
- Fixed pharma domain crash when `rows < 100` (integer division produced zero projects)
- Fixed logistics `delivered_at` column using a nonsensical relative-date reference
- Added `UserWarning` when no domain keyword is detected (tells user which keywords to use)

#### Examples (all verified)
- `examples/saas_revenue_curve.py` — all 12 monthly MRR targets hit exactly, log-normal distribution proof
- `examples/fintech_fraud_detection.py` — FICO credit score matches real-world statistics, fraud rate = 2.00%
- `examples/healthcare_multi_table.py` — ABO/Rh blood type frequencies, 2 FK edges with 0 orphans
- `examples/ecommerce_seasonal.py` — seasonal revenue curve with Black Friday and December peaks

#### CI / CD
- GitHub Actions CI matrix (Python 3.10 / 3.11 / 3.12) on every push and PR
- Trusted publishing workflow (OIDC) — PyPI publish on GitHub release, no stored API tokens

### Fixed
- `test_version_command` was asserting a hardcoded version string; now reads `misata.__version__`
- `test_formula_engine` skipped when optional `simpleeval` dependency is absent (was crashing CI)

## [0.5.3] - 2026-03-22

### Added

#### Reusable Runs
- Added `RecipeSpec` and `RunManifest` models for repeatable generation workflows
- Added `misata recipe init` to create YAML recipe files
- Added `misata recipe run --config recipe.yaml` to execute saved runs

#### Run Artifacts
- Every recipe run now writes a machine-readable `run_manifest.json`
- Optional `validation_report.json` is generated from the existing validation engine
- Optional `quality_report.json` is generated from the existing quality checker
- Optional `audit_report.json` is generated when audit mode is enabled

### Changed
- Normalized exposed version metadata to `0.5.3` across package, CLI, API, and Studio
- Primary-key style `id` columns now generate stable sequential values, which fixes SQLite/Postgres seeding collisions for generated tables

## [0.5.2] - 2026-03-08

### 🧠 The Realism Engine — Beyond Faker
**Every column is now aware of every other column. Misata no longer generates random independent values — it generates data that is mathematically consistent, temporally ordered, and proportionally scaled.**

#### Proportional Row Counts (NEW)
Stop getting flat 100 rows per table. Misata now analyzes your FK graph to assign realistic proportions:
- **Reference tables** (categories, tags): 15% of base count
- **Entity tables** (users, products): 100% of base count
- **Transaction tables** (orders, invoices): 250% of base count
- **Line-item tables** (order_items): 500% of base count
- **Activity tables** (reviews, logs): 150% of base count

```bash
misata generate --db-url sqlite:///mydb.db --rows 100
# categories: 15, users: 100, orders: 250, order_items: 500, reviews: 150
```

#### Column Enrichment (NEW)
Auto-detects column semantics from names and sets proper constraints:
- `price` → uniform $5–$999, 2 decimal places
- `rating` → categorical 1–5 (37% five-star, J-curve distribution)
- `status` in orders → `delivered` (45%), `shipped` (15%), `pending` (15%)
- `email` → composed from `first_name` + `last_name`
- `phone` → formatted numbers like `+1 (312) 555-0167`
- `quantity` → uniform 1–10 (not 50–150)
- `tier` → `free` (60%), `premium` (30%), `enterprise` (10%)

#### Cross-Column Consistency (NEW)
11 post-generation rules that enforce mathematical and logical relationships:

| Rule | What It Does |
|------|-------------|
| `total = subtotal + tax + shipping` | Exact arithmetic, always |
| `cost < price` | cost = 30–70% of price (realistic margins) |
| `line_total = qty × unit_price − discount` | Exact arithmetic |
| `discount ≤ 30% of unit_price` | Hard cap |
| `delivered_at > created_at` | +1–14 days |
| `delivered_at = NULL when not delivered` | Status-dependent |
| `email = first.last@domain` | Composed from name columns |
| `slug = slugify(name)` | Auto-derived |
| `updated_at ≥ created_at` | Temporal ordering |
| `end_date ≥ start_date` | Temporal ordering |
| `plan → price mapping` | free=\$0, premium=\$19.99 |

### Bug Fixes
- Fixed `sqlite3.ProgrammingError: type 'Timestamp' not supported` when seeding SQLite databases
- Fixed `LLMSchemaGenerator.generate_from_story()` missing `default_rows` parameter
- Fixed circular dependency detection for self-referencing tables

---

## [0.5.0] - 2026-02-03

### 🎯 Production-Ready Realism (Major Release)
**Synthetic data that looks and behaves like real data. No more placeholders!**

#### Value Pool Enrichment
- **15 NEW domain pools** with 300+ curated realistic values:
  - `medical_specialty`: 25 clinical specialties (Cardiology, Neurology, etc.)
  - `transaction_type`: 23 financial transaction types
  - `account_type`: 15 bank/financial account types
  - `brand`: 35 real-world brand names
  - `payment_method`: 18 payment options (Credit Card, PayPal, etc.)
  - `order_status`: 15 e-commerce order states
  - `customer_segment`: 17 B2B/B2C segments
  - `subscription_plan`: 16 SaaS plan types
  - `priority_level`: 10 priority/urgency values
  - `license_type`: 16 software license types
  - `file_type`: 18 document/file types
  - Generic fallbacks: `name`, `description`, `title`, `status`, `type`

#### Zero Placeholder Guarantee
- **`get_pool()` now NEVER returns empty** - cascading fallback logic ensures every column gets realistic values
- Automatic domain inference from column names (e.g., `product_name` → product pool)
- Ultimate fallback to curated generic pools when all else fails

#### Enhanced Domain Detection
- **8 NEW domain patterns** for automatic column matching
- Improved pattern matching for common column suffixes (`_name`, `_type`, `_status`)
- Generic pattern matching for ambiguous columns

### Changed
- Upgraded from beta (0.4.0b0) to stable release
- Improved LLM fallback behavior - never crashes on API failures

---

## [0.4.0b0] - 2026-01-03

### 📊 Outcome Curve Designer (KILLER FEATURE!)
**Draw the business outcome you want. Misata generates transactions that aggregate to your exact curve.**

```
User draws: Revenue from $100K → $700K over 12 months (hockey stick)
Misata generates: 36,863 individual transactions
When aggregated: 94.85% match score to target curve!
```

- 8 preset curve shapes: Linear, Exponential, Hockey Stick, Seasonal, SaaS, Churn Decline, V-Recovery, Plateau
- Configure metric type, time granularity, scale
- Dirichlet-based amount distribution for realistic variance
- Instant verification of generated vs target curve

### 🎨 Misata Studio GUI
- **4 Input Modes**: Outcome Curve, LLM Story, Distribution Designer, Sample Data
- **Schema Builder**: Review and edit columns before generating
- **Schema Inference**: Auto-detect types from uploaded CSV

### Installation
```bash
pip install misata[studio]
misata studio
```

### New Files
- `misata/studio/outcome_curve.py` - Reverse time-series generation engine
- `misata/studio/inference.py` - Schema inference from data
- `misata/studio/app.py` - Streamlit UI with 3-step wizard

---

## [0.3.1b0] - 2026-01-03

### Performance (3.8x Faster Text Generation!)
- **Text Pooling**: Generate pool of 10k values once, sample with NumPy
  - Before: 390K rows/sec → After: **1.48M rows/sec**
  - 1 million names now generates in 0.6s instead of 2.5s
- `TEXT_POOL_SIZE = 10,000` configurable constant

### Realism (Correlated Columns!)
- **`depends_on` parameter**: Columns can now depend on other column values
  - Numeric mapping: `salary` based on `job_title` (Intern→$40k, CTO→$250k)
  - Categorical mapping: `state` based on `country`
  - Boolean probability: `churned` based on `plan` (free→40%, enterprise→2%)
- Vectorized conditional generation using `np.select` for speed

### Memory Efficiency
- **`MAX_CONTEXT_ROWS = 50,000`**: Context storage capped to prevent RAM explosion
- Large parent tables (10M+ rows) no longer crash child generation
- Reservoir sampling for random FK selection from capped context

---

## [0.3.0b0] - 2025-12-29

### Added

#### Distribution Profiles (`misata.profiles`)
- **12+ pre-built statistical distributions** matching real-world patterns
- `salary_tech` - Gaussian mixture ($50k-$500k, mean ~$145k)
- `salary_usd` - Lognormal for general US salaries
- `age_adult` / `age_population` - Realistic age demographics
- `price_retail` / `price_saas` - E-commerce and SaaS pricing
- `transaction_amount` - Pareto distribution for transactions
- `rating_5star` - Beta distribution skewed toward high ratings
- `nps_score`, `conversion_rate`, `churn_rate` - Business metrics
- Helper functions: `get_profile()`, `list_profiles()`, `generate_with_profile()`

#### Conditional Generation
- **New Class**: `ConditionalCategoricalGenerator` for hierarchical data
- Generate values dependent on parent column (e.g., state matches country)
- 4 built-in lookup tables:
  - `country_to_state` - 8 countries with states/provinces
  - `department_to_role` - 7 departments with job titles
  - `category_to_subcategory` - Product category hierarchies
  - `industry_to_company_type` - Industry-specific company types
- Factory: `create_conditional_generator(lookup_name, parent_column)`

#### Realistic Edge Cases
- **Null Injection**: `BaseGenerator.inject_nulls(values, null_rate)`
- **Outlier Injection**: `BaseGenerator.inject_outliers(values, outlier_rate)`
- **Post-processing**: `BaseGenerator.post_process(values, params)`

#### Template Composition
- `SmartValueGenerator.generate_with_template()` for unlimited variety
- `SmartValueGenerator.generate_composite_pool()` for domain templates
- Templates: `address`, `email`, `product`, `company_name`
- ID templates: `order_id`, `invoice_number`, `sku`, `username`

#### Enhanced Exports
- All generators: `IntegerGenerator`, `FloatGenerator`, `BooleanGenerator`, etc.
- All constraints: `SumConstraint`, `RangeConstraint`, `UniqueConstraint`, etc.
- New: `GenerationContext`, `SmartValueGenerator`, `DistributionProfile`
- Exceptions: `MisataError`, `ColumnGenerationError`, `LLMError`, etc.

### Changed
- `SmartValueGenerator.get_pool()` now defaults to larger pool sizes
- Improved `smart_generate()` sampling with `random.choices()`

---

## [0.2.0-beta] - 2024-12-28

### Added

#### Data Quality Improvements
- **35 domain patterns** for smart value generation (up from 15)
  - 🍽️ Food: restaurant_name, cuisine_type, menu_item
  - 🎓 Education: course_name, university, degree
  - 📅 Events: event_name, venue
  - 📋 Projects: project_name, task_name, milestone
  - ⭐ Reviews: review_title, review_text
  - 📍 Location: city, country, address
  - 🏢 Business: company_name, industry
  - 💻 Tech: feature_name, bug_type, api_endpoint, skill

- **30 curated fallback pools** for domain-specific values without LLM
- **Smart distribution defaults** in LLM prompt for realistic data:
  - Age: normal(mean=35, std=12)
  - Rating: realistic 1-5 star skew
  - Price: exponential distribution
  - Status: 70/20/10 active/inactive/pending

#### New Modules
- `misata.quality` - Data quality validation
  - `DataQualityChecker` class
  - `check_quality()` convenience function
  - Distribution plausibility checks
  - Referential integrity validation
  - Temporal consistency checks
  - Quality scoring (0-100)

- `misata.templates.library` - Pre-built schema templates
  - `load_template("ecommerce")` - 7 tables, ~230K rows
  - `load_template("saas")` - 5 tables, ~527K rows
  - `load_template("healthcare")` - 5 tables, ~135K rows
  - `load_template("fintech")` - 5 tables, ~560K rows
  - `list_templates()` - Show available templates

### Changed
- Enhanced LLM system prompt with smart distribution guidelines
- Expanded `__all__` exports to include new modules

## [0.1.0-beta] - 2024-11-15

### Added
- Initial beta release
- Core `DataSimulator` for synthetic data generation
- `SchemaConfig` for defining tables, columns, relationships
- LLM-powered schema generation (Groq, OpenAI, Ollama)
- CLI tool: `misata generate --story "..."`
- Reference tables with inline data
- Transactional tables with foreign keys
- Business rule constraints
- Noise injection for ML training data
- Streaming support for 10M+ rows
- Performance: 390K rows/second
