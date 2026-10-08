# Misata codebase gap audit (v0.9.6.59): a Faker+pandas script writer's view

Scope: the local clone at /home/user/misata (HEAD `7ed6d5e`, version 0.9.6.59; a shallow clone of 61 commits), with GitHub/PyPI metadata read through the API. All hands-on runs were done on 2026-10-03 in a scratch venv (Python 3.11.15, `uv pip install -e .`) on a 4-core, 16 GB container. Scripts and outputs are under `/tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/` (cited below as `scratch/t/...`). Code links point at tag v0.9.6.59: `https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/<path>`. PyPI and GitHub already have 0.9.6.60 (released 2026-09-28), so a few findings may already have changed upstream.

Side effect to clean up: two of my test runs left empty 0-byte files at **`/b.db` and `/b3.db`** in the container's filesystem root, because of the SQLite URL bug described below. A safety check blocked me from deleting them, so a person needs to remove them.

## 1. Capability inventory: what can a user declare, and what is the escape hatch?

### Takeaway
The declarative surface is very large: 9 column types, about 12 distributions, about 24 certified declarations (outcome/rate curves, group shares, rollups, lifecycles, SCD2, event logs, missingness, duplicates, bitemporal, DAGs, and more), plus story, YAML, dict, DDL, DB, dbt and Prisma inputs. The escape hatch for anything it cannot express is thin. It is a per-column `custom_generators={table:{col: fn}}` callable that only `generate_from_schema`/`DataSimulator` accept, with no YAML/CLI/seed/story equivalent, no access to parent attributes, and a silent-zeros bug. There is no plugin system or row/table post-hook.

### Cited Findings
- `Column.type` is a closed Literal of 9 types: int, float, date, time, datetime, categorical, foreign_key, text, boolean. There are no object/array/JSON/decimal/uuid types. — [misata/schema.py:27](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/schema.py#L27)
- Distribution parameters are an untyped `Dict[str, Any]` (`distribution_params`). For int/float, a missing `distribution` silently defaults to `"normal"`. A categorical with no choices becomes `['Unknown']` with only a warning. — [misata/schema.py:28, 41-65](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/schema.py#L41)
- Distributions referenced in simulator/generators: normal, lognormal (`mu`/`sigma`), uniform, poisson, exponential, beta, binomial, pareto, power_law, zipf (by grep). The docs table lists lognormal as `mu`, `sigma`. — [docs/guides/distributions.md:21](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/docs/guides/distributions.md#L21)
- Schema-level declarations available as pydantic models: OutcomeCurve, RateCurve, CohortRetention, Missingness, LateArrival, GroupShares, Lifecycle, EventLog, SensorResponse, Degradation, StockFlowIdentity, SCD2Config, WaterfallIdentity, NoiseConfig, TimeGrid, Duplicates, Outliers, Typos, Bitemporal, DagEdges, TransitiveClosure, JointDistribution, GraphMotifs. — [misata/schema.py class list (lines 344-1361)](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/schema.py#L344)
- LANGUAGE.md documents these declarations as a formal "language", each with guarantees, refusals and audits. It explicitly puts the LLM story parser, vocabulary/capsule enrichment, PDF export, Spark output, fidelity scoring and `noise_config` outside the contract. — [LANGUAGE.md:516-528](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/LANGUAGE.md#L516)
- `misata/registry.py` says that only 7 of 24 declarations met the "declared and verified" rule before a recent fix, and that all 24 do now. — [misata/registry.py:1-20](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/registry.py#L1)
- Input paths: `misata.generate(story)`, `parse`, `preview`, `generate_from_schema(SchemaConfig|dict)`, `load_yaml_schema`, `from_dict_schema`, `from_ddl`, `schema_from_db`, `schema_from_sqlalchemy`, `seed_from_sqlalchemy_models`, `mimic` (CSV twin), dbt `schema.yml` import, Prisma import, `synth-import`, and `LLMSchemaGenerator` (groq/openai/anthropic/ollama). — [misata/__init__.py:600-722](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L600); [README.md:233-523 "Eight ways to generate data"](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/README.md#L233)
- **Escape hatch #1, `custom_generators`.** `generate_from_schema(schema, custom_generators={table:{col: callable}})`. A 2-arg callable is vectorized `fn(partial_df, context)`. A 3+-arg callable is per-row `fn(row, col_name, context)`, picked by inspecting the signature. — [misata/__init__.py:272-306](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L272); [misata/simulator.py:1491-1519](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/simulator.py#L1491)
- Hands-on: both forms worked when the custom column came after the columns it reads (an `SKU-00948-3` string built from product_id+quantity; an `ltv_bucket` derived from country). The output was byte-reproducible across two runs. — [scratch/t/a_ecom.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/a_ecom.py)
- **Bug:** a per-row custom function on a column positioned before any other generated column gets an empty `partial_df`. The code then returns `np.zeros(size)` without any warning. Hands-on, `tier` → `"gold"` produced `0` for every row. — [misata/simulator.py:1506-1509](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/simulator.py#L1506); hands-on run (inline script, output: `tier` column all `0`)
- **Limitation:** `context` holds only parent primary keys, not their attributes. The simulator comments it as "Lightweight context (IDs only)". Hands-on, `ctx` = `{'c': ['id']}`, so a custom child column cannot read the parent customer's `country`. — [misata/simulator.py:260](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/simulator.py#L260); hands-on run
- `custom_generators` is not a parameter of `misata.generate` (story), `generate_stream`, `seed_database`, or any CLI command. — [misata/__init__.py:202-212, 92-97](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L202); [misata/db.py:33-43](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/db.py#L33)
- No RNG or seed is passed to custom callables, so users must manage their own reproducibility. — [misata/simulator.py:1497-1519](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/simulator.py#L1497)
- **Escape hatch #2, formulas.** Row formulas with cross-table references (`formula: "hours * @employees.hourly_rate"`) exist but need the optional `simpleeval` extra (`misata[formulas]`). — [misata/simulator.py:1347-1358](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/simulator.py#L1347); [misata/formulas.py:78](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/formulas.py#L78); [pyproject.toml formulas extra](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/pyproject.toml)
- **Escape hatch #3**, `Customizer`/`ColumnOverride` plus helper generator factories (price_generator, age_generator, …). — [misata/customization.py:17-245](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/customization.py#L17)
- There are no `entry_points`/plugin discovery and no table-level or post-generation hooks. A grep for `entry_points|importlib.metadata` in `misata/*.py` returned nothing. — local grep
- **Silent acceptance of bad parameters.** Hands-on, with warnings set to `always`: `{"distribution":"poisson","lamda":7}` (typo) and `{"distribution":"gumbel"}` (unsupported) both raised no error and no warning, and silently produced uniform values from 0 to 1000 (mean 501). `{"distribution":"lognormal","mean":3.5,"std":0.8}` (numpy-style naming) was also accepted silently and gave mean 3.49, whereas `mu`/`sigma` gave a mean of 46. — [scratch/t/a2.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/a2.py)
- Object/array columns in a dict schema (`{"type":"object"}`, `{"type":"array"}`) silently became `text` and were filled with business-note prose ("Stakeholder confirmed the updated details earlier today."), with no warning. — hands-on run (Task g)
- LIMITATIONS.md is unusually candid. It notes no learned correlation structure, US-flavoured priors, name-routed English-first priors, grammar-generated text, roll-up tables buffered in memory, `generate_stream` taking only a story, and per-version determinism. — [LIMITATIONS.md](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/LIMITATIONS.md)

### Inferences
- For someone replacing a Faker+pandas script, the declarative core is richer than anything they would hand-write (exact aggregates, lifecycles, SCD2). But the moment they need "column X depends on parent column Y" or "a nested JSON payload", they fall back to post-processing in pandas, which is exactly what they wanted to stop doing.
- The lack of parameter validation (untyped `distribution_params`, unknown keys and distributions accepted silently) is the biggest DX risk for a library that sells "declare it and it holds". A typo yields plausible-looking but wrong data.

### Gaps
- I did not test `formula` columns end to end, `Customizer`, or `LLMSchemaGenerator` (no API keys available).
- I did not exhaustively check whether YAML exposes every pydantic declaration under the same names.

## 2. Hands-on: 8 realistic script-writer tasks

### Takeaway
Basic multi-table generation is fast, FK-correct and reproducible, and streaming scales to 10M rows in about 15 s. But 5 of the 8 tasks showed serious friction:
- seeding a real DDL/Postgres schema failed on CHECK, VARCHAR(n), CHAR(2) and text-PK FKs;
- `--truncate` fails on Postgres with FKs, and seeding is non-atomic;
- relative SQLite URLs resolve to `/`;
- the in-memory path is 10x slower than streaming at 10M rows;
- the time-series seasonality phase is off by a quarter period;
- clickstream and unusual-domain stories produce structurally generic or nonsensical schemas;
- nested JSON is unsupported.

### Cited Findings

**(a) 3-table e-commerce from YAML + custom distribution + custom Python columns**
- It worked: customers 2,000, products 200, orders 20,000 in 0.23 s, 0 FK orphans, categorical proportions exact (US 0.5/DE 0.3/IN 0.2), poisson quantity mean 2.14 clipped to [1,10], and a byte-identical rerun (`repro True`). — [scratch/t/a_ecom.yaml + a_ecom.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/a_ecom.py)
- Friction: a PK named `customer_id: {type: int, unique: true}` in YAML is not treated as a PK. It is drawn from a default range of 1001 and triggers `UserWarning: Range 1001 too small for unique column customer_id (needs 2000). Extending max.`, producing shuffled, non-sequential IDs (580, 658, 1879…). A column literally named `id` gets 1..N. — [misata/simulator.py:1841](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/simulator.py#L1841); hands-on
- Friction: `order_date: {type: date}` came out as `datetime64` with mixed midnight and random clock times (e.g. `2024-04-30 06:15:19`), although `type: date` was declared. — hands-on (a)

**(b) Seed an existing schema from DDL (SQLite and Postgres)**
- `from_ddl` dropped all CHECK constraints (`status IN (...)` became free `text`; `age BETWEEN 18 AND 99` became a normal int), inline `UNIQUE` (email `unique=False`), and `CHAR(2)`/`VARCHAR(12)` lengths. The parser skips table-level `PRIMARY KEY|UNIQUE|CHECK|CONSTRAINT` lines. — [misata/ddl.py:198](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/ddl.py#L198); [scratch/t/b.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/b.py)
- **Bug: relative SQLite URL resolves to the filesystem root.** `sqlite:///b.db` is parsed with `urlparse(...).path` = `/b.db` and opened as an absolute path. Under the SQLAlchemy convention, three slashes means a relative path. The result was a misleading error ("Table 'users' not found. Use --db-create") and an empty file created at `/b.db`. The CLI's own help example `misata seed sqlite:///dev.db` would hit `/dev.db`. Hands-on, `misata seed sqlite:///b3.db --dry-run` reported "No tables found to seed." and created `/b3.db`. — [misata/db.py:315-325](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/db.py#L315); hands-on
- With an absolute path, both `seed_database(from_ddl(...))` and `misata seed sqlite:////abs/path` failed with `CHECK constraint failed: status IN ('active','suspended','deleted')`. After patching status and age by hand, the run then failed with `UNIQUE constraint failed: users.email`, so emails are not unique by default even when the DB demands it. — [scratch/t/b2.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/b2.py)
- Postgres 16 (local cluster, `misata seed postgresql://...`) failed in sequence:
  1. `value too long for type character varying(12)`, after printing a psycopg "pipeline aborted" message;
  2. after widening that column, `value too long for type character(2)`, because country_code was filled with full country names ("Australia", "Germany");
  3. `insert or update on table "order_items" violates foreign key constraint ... Key (product_sku)=(Customer requested expedited processing yesterday afternoon. 2 2)`. The text primary key `sku` was filled with prose sentences plus a uniqueness suffix, and the FK sampling of it broke.
  — hands-on CLI runs
- Postgres introspection also ignored the CHECK on `status` once I dropped it: values `inactive` were generated, which is outside the original `active/suspended/deleted` domain. — hands-on
- **Non-atomic seeding:** each batch is committed separately (`conn.commit()` in `_insert_batch`/`_execute`). After a mid-run failure, `products` was left populated and the other tables empty, so the next run refused with "These tables already contain data: products." — [misata/db.py:336-396](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/db.py#L336); hands-on
- **Bug: `--truncate` fails on Postgres with FKs.** It issues `TRUNCATE TABLE "x"` per table without CASCADE, giving `cannot truncate a table referenced in a foreign key constraint`. — [misata/db.py:303-312](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/db.py#L303); hands-on
- Positive: the seed CLI prints a clear plan (tables, insert order, row counts that scale 300 → 750) and supports `--dry-run`, `--append`, `--skip`; the Postgres COPY path is used. — `misata seed --help`; [misata/db.py:367-380](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/db.py#L367)

**(c) 10M rows: performance and memory**
- Schema: 100k customers plus 10M events (FK, lognormal amount, categorical, datetime).

  | Path | Rows | Time | Peak RSS |
  |---|---|---|---|
  | Streaming via `DataSimulator(...).generate_all()` to a pyarrow ParquetWriter | 10.1M | 15.5 s | 661 MB (184 MB parquet) |
  | In-memory `generate_from_schema` | 10.1M | 154.1 s | 1,124 MB |
  | Streaming | 1.01M | 2.2 s | — |
  | In-memory | 1.01M | 3.8 s | — |

  — [scratch/t/c.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/c.py)
- The 10x gap comes from `_run_simulation` growing each table with `pd.concat([tables[name], batch])` once per 10,000-row batch (default `batch_size=10_000`). That is quadratic copying, about 1,000 concats for 10M rows. The same pattern appears in `generate_more`/`generate_diff`. — [misata/__init__.py:145-149, 428, 533](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L145)
- LIMITATIONS.md claims a 10M-row fact table in about 41 s / 550 MB on disk, and that tables in roll-ups are fully buffered. — [LIMITATIONS.md "Scale and memory"](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/LIMITATIONS.md)
- `generate_stream` accepts only a story, not a schema, so streaming a hand-built schema means using `DataSimulator` internals. Its docstring example uses an undefined loop variable `i`. — [misata/__init__.py:92-133](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L92); [LIMITATIONS.md](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/LIMITATIONS.md)

**(d) Output to Parquet / DuckDB / SQL / Postgres**
- `to_parquet`, `to_duckdb`, `to_jsonl` and `misata.export.to_sql(dialect="postgres")` all worked on a story dataset. Generation of 5k customers, 1k products and 15k orders took 0.4 s. — [scratch/t/d.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/d.py)
- DuckDB tables come out with every column nullable and no PK/FK. The `to_sql` DDL has no PRIMARY KEY, NOT NULL or REFERENCES, and with `dialect="postgres"` it emits `"amount" DOUBLE`, which is not a Postgres type (Postgres uses `DOUBLE PRECISION`). — hands-on output `out_sql/orders.sql`
- `to_sql` and `to_arrow` are imported in `misata/__init__.py` but missing from `__all__`. — [misata/__init__.py:713, 723-905](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L713)
- There is no Polars support anywhere: `grep -rl polars misata/` is empty. Direct-to-Postgres goes only through `seed_database`/`misata seed`. Spark/Delta is supported via `misata.spark` (pyspark extra). — local grep; [pyproject.toml spark extra](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/pyproject.toml); [docs/spark.md](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/docs/spark.md)

**(e) Time series with seasonality and a weekday effect**
- `generate_timeseries` returns a single-metric frame (`date, value/sales, trend, seasonal, is_anomaly`). It is separate from the relational engine. — [misata/timeseries.py:330-344](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/timeseries.py#L330)
- **Bug: seasonality peaks land a quarter period after `peak_offset`.** The docstring says peak_offset is "Period offset where the sine wave peaks", but the code computes `sin((t - peak_offset)·2π/period)`, which is zero at the offset. Hands-on: `Seasonality(type="yearly", peak_offset=340)` (December) peaked in Feb-March (mean 1288 in March) with a trough in August (702). `Seasonality(type="weekly", peak_offset=5)` (Saturday) peaked on Monday (1201) with a trough on Thursday (801). — [misata/timeseries.py:72, 168-180](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/timeseries.py#L168); [scratch/t/e.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/e.py)
- Story-driven seasonality uses hard-coded phases. Any "weekend/weekday" word maps to weekly `peak_offset=1` (Tuesday), and any "yearly/seasonal/summer/winter/holiday" word maps to `peak_offset=180` (summer). Hands-on, "peaking on weekends and in December, with a Black Friday spike" gave a mid-week peak (Wed 1229, Thu 1291; Sun 712), flat months (979-1074), and the biggest anomaly on 2023-10-20. — [misata/timeseries.py:298-305](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/timeseries.py#L298); hands-on
- Row-level: "A coffee shop chain with 3000 sales transactions in 2024, busiest on weekends and in December" produced the stock e-commerce schema (customers 10,000 / products 2,000 / orders 30,000). The weekday distribution was flat (4,179-4,405 per day), dates spanned beyond 2024, and 53% of order timestamps were exactly midnight. — hands-on (e)

**(f) Clickstream / session events**
- "A web analytics clickstream: 2000 users, their browsing sessions, and page view and click events within each session, with a signup funnel" composed `users`, `web_analytics`, `click_events` and `browsing_sessions`. The relationships were inverted (`click_events.click_event_id → browsing_sessions.click_event_id`, so click events are parents of sessions). The entity tables had generic columns (`reference_code`, `status`, `value`), and sessions had statuses `cancelled`/`scheduled`. There was no event sequencing, inter-event gaps, session windows or funnel. — [scratch/t/f.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/f.py)
- The closest declarative primitive is `event_logs`, which guarantees one event per lifecycle state in path order. That is a state log, not a clickstream/sessionization model. — [LANGUAGE.md:384-414](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/LANGUAGE.md#L384)
- The built-in templates are only `['ecommerce', 'saas', 'healthcare', 'fintech']`. — hands-on `misata.list_templates()`

**(g) Nested JSON output**
- Not supported. `to_jsonl` writes flat `orient="records"` rows. There is no nested/array/struct type, and object/array dict types silently become prose text (see section 1). — [misata/export.py:114-137](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/export.py#L114); [docs/export.md](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/docs/export.md)

**(h) Story parser on unusual domains**
- The parser is honest about failure. It warned "StoryParser could not match a built-in domain, so it composed a structural schema…" and "This parser could not turn 'where 15% of visits are emergencies' into a declaration, so it had no effect." — [scratch/t/h.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/h.py)
- The output was still poor:
  - Reptile vet: duplicate entity tables (`exotic_reptiles` and `reptiles`, `vet_visits` and `visits`); reptiles carry only `reference_code/status/value`; prescriptions contain business-note prose; 8,000 prescriptions for 4,000 visits.
  - Ski resort: a table named `saturdays`. "5000 lift ticket scans" became 60 rows, and the 3% failure rate was ignored.
  - "A Japanese convenience store chain with 40 stores in Tokyo and 20000 receipts" ignored both counts. It generated generic e-commerce (10,000 customers, books and sneakers products) with Japanese names but English email local parts (`青木 美加子` → `michelletaylor952@protonmail.com`).
  — hands-on (h)
- Positive: the story-path warnings are explicit, and `misata.preview()` exists for inspecting a schema before generating. — [misata/__init__.py:58-89](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L58)

### Inferences
- The "explicit schema → DataFrames" path is solid and fast enough to replace most Faker loops, even before the 10x concat fix. The "seed my existing DB" path is the riskiest: real DDL with CHECK, VARCHAR(n), CHAR(n), UNIQUE and text keys is the norm, and every one of those broke.
- The story parser is good at its known domains and at refusing honestly, but for novel domains it produces scaffolding rather than data a script writer would accept.

### Gaps
- I did not test MySQL, SQLAlchemy-model seeding, `mimic`, dbt commands, the Spark path, or LLM-backed parsing.
- I measured 10M-row behaviour only for a 2-table schema with no roll-ups. Roll-up and cascade schemas are buffered fully in memory per LIMITATIONS, and I did not test them.

## 3. Dependency weight, import time, Python support, engines

### Takeaway
The core install is moderately heavy: 10 direct deps including scipy, networkx, jinja2, rich and faker; 23 packages; a 252 MB venv. Import is slow (about 1.7 s warm, 2.1 s cold, 1,301 modules) because `misata/__init__.py` eagerly imports almost every submodule. Python 3.10-3.13 are tested in CI. There is no Polars, DuckDB is an extra for evalpack only, and Spark is an extra.

### Cited Findings
- Core dependencies: pandas, numpy, pydantic, click, pyyaml, rich, scipy, networkx, jinja2, faker. There are 16 extras (dev, db, orm, llm, bedrock, formulas, api, studio, advanced[sdv, langgraph, z3], documents, docs, mcp, kaggle, fidelity, spark, evalpack, all). — [pyproject.toml](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/pyproject.toml)
- Hands-on: `uv pip install -e .` produced a 252 MB venv with 23 packages. — scratch venv (`du -sh venv`, `uv pip list | wc -l`)
- Import time: `import misata` took 1.65-1.77 s warm (3 runs), against 1.08 s for `pandas + numpy + scipy.stats` alone. `-X importtime` gave a 2.09 s cumulative total, with `misata.smart_values` costing 619 ms of self-time and `misata.llm_parser` 859 ms cumulative. 1,301 modules were in `sys.modules` after import. — hands-on
- `misata/__init__.py` (905 lines) imports about 60 submodules at import time, including kaggle_integration, documents, assets, spark, llm_parser and profiler. — [misata/__init__.py:600-721](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L600)
- `requires-python = ">=3.10"`. The classifiers list 3.10-3.12, but the CI matrix tests 3.10, 3.11, 3.12 and 3.13. — [pyproject.toml](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/pyproject.toml); [.github/workflows/ci.yml:16](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/.github/workflows/ci.yml#L16)
- `mcp` is pinned `<2.0.0` because mcp 2.0 removed FastMCP and broke CI. — [pyproject.toml dev/mcp extras](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/pyproject.toml)
- Engines: Polars has no support; DuckDB is used as an export target (`to_duckdb`) and in the evalpack extra; Spark/Delta is available via `misata.spark` with the pyspark extra; the in-memory representation is always pandas (`StringDtype` text columns, `datetime64[ns]`). — local grep; hands-on dtypes

### Inferences
- The import cost and the scipy/networkx/jinja2 core deps are acceptable for notebooks but noticeable in pytest collection and CLI startup. Lazy imports in `__init__` would likely remove most of the 0.6-0.7 s on top of pandas and scipy.

### Gaps
- I did not measure install time or wheel size from PyPI, or import time on 3.10 or 3.13.

## 4. API surface coherence, codebase size, test suite

### Takeaway
The surface is sprawling: `__all__` exports 156 names (three duplicated), plus 26 CLI commands, with roughly 15 or more distinct "make data" entry points across story, schema, YAML, dict, DDL, DB, mimic, timeseries, templates, documents, profiles and evalpacks. The internals are large: 131 modules and 69.7k lines, including a 6,064-line `simulator.py`. The test suite is large and green: 2,144 passed, 14 skipped, in 5m50s. There are name collisions and a shadowed CLI command.

### Cited Findings
- Package: 131 `.py` files, 69,692 lines under `misata/`. Largest files: `simulator.py` 6,064, `story_parser.py` 3,464, `cli.py` 3,202, `schema.py` 1,669, `compat.py` 1,421. — local `wc -l`
- Tests: 119 files, 28,360 lines, about 1,802 `test_` functions by grep. `pytest -x -q -m "not slow"` gave **2144 passed, 14 skipped, 1 deselected, 196 warnings in 350.55 s**, exit 0. — local run (`scratch/pytest_x.log`)
- `__all__` has 156 entries. `FidelityReport`, `PrivacyReport` and `SchemaValidationError` appear twice. `FidelityReport`/`PrivacyReport` are imported first from `misata.reporting` (lines 669, 672) and then overwritten by `misata.fidelity` (line 719), so `misata.FidelityReport` is not the class `FidelityChecker` returns. — [misata/__init__.py:669-719, 723-905](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L669); hands-on (`misata.FidelityReport.__module__ == 'misata.fidelity'`)
- `generate_diff` is defined at top level but not in `__all__`. — [misata/__init__.py:456](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L456)
- The CLI has 26 commands (audit, capsule, dbt-fixture, dbt-mutate, dbt-seed, dbt-unit-test, evalpack, examples, generate, graph, init, lint, mimic, parse, prisma-seed, provenance, quality, recipe, schema, seed, serve, studio, synth-import, template, templates-list, validate). — `misata --help`
- **Shadowed CLI command:** `cli.py` defines `validate_cmd` twice. One at line 1391 is the DB/data-dir validator (`--data-dir`, `--db-url`, `--limit`). One at line 1600 is the CSV profiler registered as `validate`. With click 8.5, only the CSV version is reachable (`misata validate --help` shows `CSV_FILE`), so the DB validator is dead code. — [misata/cli.py:1362-1391, 1599-1600](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/cli.py#L1362); hands-on
- The CLI banner still says "AI-Powered Synthetic Data Engine", while the package description says "No ML model" / "Outcome-conformant". — `misata --help`; [pyproject.toml description](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/pyproject.toml)
- Naming is inconsistent: `generate` takes a story but `generate_from_schema` takes a schema or dict; `from_ddl` and `from_dict_schema` versus `schema_from_db` and `schema_from_sqlalchemy` versus `load_yaml_schema`; `validate_domain`, `validate_schema`, `validate_data`, `validate_csv` and `validate_vocabulary` all coexist. — [misata/__init__.py `__all__`](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L723)
- Typing: `py.typed` ships, but mypy runs with `disallow_untyped_defs = false` and about 500 unannotated internals, as admitted in the pyproject comment. — [pyproject.toml [tool.mypy]](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/pyproject.toml)

### Inferences
- A newcomer faces a discoverability problem. The README alone is 1,343 lines and describes "Eight ways to generate data" and more. There is no single obvious "schema-as-code → DataFrames/DB" path with one consistent naming scheme.

### Gaps
- I did not compute test coverage, and I did not run the 1 deselected slow test.

## 5. Project health

### Takeaway
This is a single-maintainer project with very high churn: 450 commits since 2025-12-16, 125 PyPI releases in about 9.5 months, 56 of them in July 2026. It uses four-part `0.9.6.x` patch versions while claiming SemVer and "Production/Stable". There is no stated breaking-change or deprecation policy, and the RNG stream has changed across versions. CI is green.

### Cited Findings
- GitHub (repo created 2025-12-16, last push 2026-10-01): 69 stars, 3 forks, 0 open issues, and a single contributor (`rasinmuhammed`, 450 commits). All issues and PRs (#1-#3) are by the maintainer. — `gh api repos/rasinmuhammed/misata`, `/contributors`, `/issues`
- Commits by month (API, partial pagination): 2026-06 ≥100, 2026-08 59, 2026-09 38, 2026-10 2. The local clone is shallow (61 commits from 2026-08-23). — `gh api .../commits`; `git rev-parse --is-shallow-repository`
- PyPI: 125 releases from `0.1.0b0` (2025-12-16) to `0.9.6.60` (2026-09-28). By month: 2026-07 56, 2026-08 31, 2026-06 15, 2026-09 9. GitHub has 119 releases. — `https://pypi.org/pypi/misata/json`; `gh api .../releases`
- CHANGELOG.md is 3,827 lines with 92 `##` version sections and claims "adheres to Semantic Versioning". Four-part versions like `0.9.6.59` are not valid SemVer. — [CHANGELOG.md:6](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/CHANGELOG.md#L6)
- The classifier is `Development Status :: 5 - Production/Stable` despite the 0.x version. — [pyproject.toml:39](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/pyproject.toml#L39)
- Determinism is per-version only. The RNG stream changed in 0.8.1.29 and 0.8.2. `generation_mode` now defaults to `"anchored"`, which produces different bytes from `"legacy"` for the same seed. — [LIMITATIONS.md "Reproducibility"](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/LIMITATIONS.md); [misata/schema.py:1543-1550](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/schema.py#L1543)
- Commit messages describe silent-wrong-output fixes in recent patches. For example, 0.9.6.59: "__group_shares__ nested that way used to silently generate a completely different, wrong distribution with no warning". 0.9.6.58: a fintech story injected a 'cancelled' category into `accounts.status`. — `git log` (7ed6d5e..0647157)
- CI: recent runs of CI, Publish to PyPI and Deploy Docs were all `success` (2026-09-06 to 2026-10-01). The matrix is Python 3.10-3.13. — `gh api .../actions/runs`; [.github/workflows/ci.yml](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/.github/workflows/ci.yml)
- Docs: an mkdocs site with 74 markdown files under `docs/`. `site_url` is `https://rasinmuhammed.github.io/misata`, while pyproject says Documentation is `https://misata.studio/docs`, so two URLs are in use. — [mkdocs.yml:3](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/mkdocs.yml#L3); [pyproject.toml [project.urls]](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/pyproject.toml)
- Repo clutter: the root includes `blog/`, `grant-applications/`, `research/`, `reports/`, `saas_test/`, `research_notes/`, `notebooks/`, `mcpb/`, `skills/`, `smithery.yaml`, `glama.json` and `funding.json`. — local `ls`

### Inferences
- Bus factor is 1, and the release cadence means users pinning for reproducible bytes face constant upgrade pressure. Recent commits repeatedly fix "silently wrong" outputs. That shows rigour, but it also tells a newcomer the defaults are still moving.

### Gaps
- Both docs URLs returned no response from this container (curl `000`, likely a proxy restriction), so I could not verify the live docs site. There is no written deprecation policy beyond the changelog. I did not check whether 0.9.6.60 fixes any bug listed here.

## 6. Integrations present or missing

### Takeaway
It is strong on dbt (4 commands), Prisma, SQLAlchemy, the MCP server/Docker, Spark/Delta, Streamlit Studio and the FastAPI server. It has pytest fixture factories but no auto-registered pytest plugin. It is missing Django model import, Great Expectations/Soda, Airflow/Dagster, Polars, any JS/TS package, and a VS Code extension. YAML editor validation is only possible through a published JSON Schema URL.

### Cited Findings
- dbt: `dbt.py`, `dbt_import.py`, `dbt_unit.py` and the CLI commands `dbt-seed`, `dbt-unit-test`, `dbt-fixture`, `dbt-mutate`. — [misata/cli.py:1681-3072](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/cli.py#L1681); `misata --help`
- Prisma (`prisma_import.py`, `prisma-seed`), SQLAlchemy (`schema_from_sqlalchemy`, `seed_from_sqlalchemy_models`, `orm` extra), synth import (`synth-import`). — [misata/__init__.py:690-692](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L690)
- pytest: `misata.testing.misata_fixture(story, rows=…)` and `misata_schema_fixture` factories, plus `misata_generate`/`misata_parse`/`misata_preview` fixtures that must be imported into conftest. There is no `pytest11` entry point in pyproject. — [misata/testing.py:1-175](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/testing.py#L1); [pyproject.toml [project.scripts]](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/pyproject.toml)
- MCP server (`misata-mcp`), a Dockerfile for it, `mcpb/` bundle, `server.json`, `smithery.yaml`, `glama.json`. — [Dockerfile](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/Dockerfile)
- Studio (Streamlit, `misata-studio`) and a REST API (`misata serve`, FastAPI extra). — [pyproject.toml](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/pyproject.toml)
- JSON Schema for YAML: `JSON_SCHEMA_URL = https://raw.githubusercontent.com/rasinmuhammed/misata/main/schema/misata.schema.json`, usable by the VS Code YAML extension. — [misata/yaml_schema.py:885-888](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/yaml_schema.py#L885)
- Missing, with no matches in `misata/`: Polars; great_expectations, soda, airflow and dagster (grep empty); Django model import (Django appears only in a comment in `introspect.py:673`); and any JS/TS package or VS Code extension in the repo. — local greps

### Inferences
- The integrations target dbt/analytics and AI-agent (MCP) users more than the app-developer testing workflow, which would need a Django/Pydantic model import, an auto-loaded pytest plugin, and Polars.

### Gaps
- I did not run the dbt, Prisma or MCP integrations hands-on.

## 7. Realism gaps (coordinator add-on)

### Takeaway
At the column level the output looks plausible: coherent name→email, US-style price endings (.99/.95), a J-shaped rating, believable status and payment mixes. At the dataset level it has clear synthetic tells:
- order amounts unrelated to price × quantity;
- about half of all timestamps exactly at midnight, and an inverted diurnal curve peaking at 1-3 am;
- no weekday effect;
- near-uniform product popularity and email-domain shares;
- no heavy-tailed customers;
- price independent of category;
- heavily repeated product names;
- zero nulls or duplicates by default;
- template prose for free text and text keys.

### Cited Findings
All figures below come from the default story e-commerce dataset (`misata.generate("An ecommerce store with 5000 customers, products, orders and order items", seed=3)`; [scratch/t/real.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/real.py)) unless the bullet says otherwise.
- The story asked for "order items", but no `order_items` table was produced (only customers, products, orders), with no warning.
- `orders.amount == products.price × quantity` holds for only 0.2% of rows, and 45.3% of orders have an amount below the unit price of their product.
- Sample row: order 2854, product 244, quantity 4, amount 164.99. Book "Man's Search for Meaning" priced 764.99.
- 49.4% of `order_date` values are exactly 00:00:00. The non-midnight hours peak at 01:00-03:00 (859/856/777) and decline monotonically to 23:00 (68), the inverse of real e-commerce traffic, which peaks in the evening.
- No weekday effect: orders per weekday range from 2,098 to 2,205.
- Month counts rise monotonically from January (921) to December (1,691), and order years skew to 2024 (8,366 vs 1,652 in 2022). That reads as a built-in growth curve, not seasonality.
- No order before signup (0.0%), so the temporal FK holds.
- Orders per customer: median 3, p99 8, max 10, with 5% of customers at zero orders. There are no "whale" customers.
- Product popularity is near uniform: the top 10 of 1,000 products account for 1.74% of orders. Real catalogues are Pareto.
- Price does not depend on category. Medians run 56-79 in every category, and books reach 1,177 while beauty reaches 1,967.
- The `amount` distribution is right-skewed (skew 3.74, median 81.99, max 1,987), which is plausible.
- Price endings: .99 ×511, .00 ×345, .95 ×144.
- Email domains are uniform: yahoo 13.2%, hotmail 12.8%, gmail 12.6%, icloud 12.5%, aol 12.4%, outlook 12.4%, protonmail 12.3%, mail.com 11.9%. Real data is dominated by gmail.
- Customer `country` is independent of name: Vikram Kapoor in France, Abigail Williams in Mexico, Lisa Wright in Spain.
- Only 120 distinct product names across 1,000 products ('Smartwatch Series 5' ×21, 'Robot Vacuum Pro' ×15).
- Zero nulls in any table and zero duplicate emails by default. Missingness, duplicates, outliers and typos exist only when declared. — [LANGUAGE.md:242-440](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/LANGUAGE.md#L242)
- Status mix: completed 72%, shipped 12.4%, pending 7.9%, returned 4.6%, cancelled 3.2%. Payment mix: credit_card 45.5%, debit 24.7%, paypal 14.9%, apple_pay 9.9%, bank_transfer 5%. Both are plausible. Product rating has mean 4.04, median 4.2 and min 2.0.
- Free text and text keys are template prose. Prescriptions' `content` read "Stakeholder approved the proposed changes; details logged in the account history." A Postgres text PK `sku` was filled with "Requester confirmed receipt of the shipment; will follow up next week. 2". — [scratch/t/h.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/h.py); Postgres hands-on
- LIMITATIONS concedes that free text "has template rhythm a careful reader can spot". — [LIMITATIONS.md](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/LIMITATIONS.md)
- Locale coherence breaks across columns. The Japan story yields Japanese-script names with English email local parts (`山口 加奈` → `dorothy.brown2@outlook.com`) and USD-like prices (59.99). A column named `country_code` (CHAR(2)) gets full country names ("Australia"). — hands-on (h), Postgres run
- LIMITATIONS says economic priors are US-flavoured and locale packs only adjust formats. — [LIMITATIONS.md "Values and vocabulary"](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/LIMITATIONS.md)
- There is no learned or default cross-column correlation except name-matched pairs when `smart_correlations=True`. That covers only 12 hard-coded keyword rules such as age↔salary 0.45 and price↔quantity −0.35. — [misata/__init__.py:155-168](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/misata/__init__.py#L155); [LIMITATIONS.md "Statistics"](https://github.com/rasinmuhammed/misata/blob/v0.9.6.59/LIMITATIONS.md)
- Time series: residual lag-1 autocorrelation was 0.548, so noise is not i.i.d. That is good. But the seasonality phase bug places declared peaks a quarter period late (section 2e). — [scratch/t/e.py](file:///tmp/claude-0/-home-user-misata/c1151dc1-f1ea-5128-8eaa-843521027c8e/scratchpad/t/e.py)
- Clickstream output has no session structure: no ordered events, dwell times, bounce or funnel drop-off (section 2f).

### Inferences
- If realism is the headline claim, the defaults most likely to be noticed by a data person are:
  1. midnight-heavy or inverted diurnal timestamps;
  2. order totals unrelated to line prices;
  3. uniform popularity and email-domain shares, with no long-tail customers;
  4. category-blind prices;
  5. "too clean" data (no nulls or dupes).

  All of these are fixable with defaults: a diurnal and weekday prior on event timestamps, Zipf FK sampling, amount = Σ(price × qty) when the parent has a price, and a category price band. Some fixes may already exist behind declarations or capsules, but the default story path does not apply them.
- Declared statistics (curves, rates, shares) are where Misata is genuinely stronger than Faker. The realism risk is concentrated in the undeclared defaults a newcomer sees first.

### Gaps
- I did not compare against real production distributions, beyond qualitative norms such as gmail dominance and evening e-commerce peaks. I did not test `mimic` fidelity on a real CSV, capsules, or `realism: strict` mode, any of which may improve these numbers.
