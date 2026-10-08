# Adoption drivers and user demands for test/synthetic data libraries

Research date: 2026-10-04. Note on method: this session's network proxy blocked pepy.tech, pypistats.org, news.ycombinator.com, reddit, dev.to, datacebo.com and snaplet.dev for direct fetching, and the GitHub REST API was not enabled. Star counts below come from fetching github.com repo pages on 2026-10-04 (WebFetch summaries, rounded the way GitHub shows them). Download numbers come from search-engine snippets of pypistats/rubygems pages, so treat them as approximate. Several "alternative to X" sources are competitor marketing pages (seedfa.st, seedbase.dev); they are flagged where used.

## 1. Adoption history and scale of incumbents

### Takeaway
The libraries that became defaults (Faker, factory_bot, factory_boy, Hypothesis) are permissively licensed (MIT/MPL), install with one command, plug into the test runner or ORM people already use, and are deterministic when seeded. Multi-table, statistics-driven tools (SDV, Synth) and hosted products (Snaplet, Neosync, Gretel) have far smaller footprints, and in 2024-2025 several of them shut down, were acquired, or moved to a restrictive licence.

### Cited Findings
- Python Faker (joke2k/faker): about 19.4k GitHub stars, 2.1k forks, MIT, only 17 open issues. The README lists a CLI, a pytest fixture, `unique`, seeding for reproducibility, 50+ locales and factory_boy integration. — [GitHub joke2k/faker](https://github.com/joke2k/faker) (fetched 2026-10-04)
- Faker had about 63.5M PyPI downloads in the last month (search snippet of pypistats, about October 2026). — [pypistats faker](https://pypistats.org/packages/faker) (could not fetch directly, number not checked)
- faker-js/faker: about 15.5k stars, MIT, 70+ locales, seedable, stable v10 with v11 in progress. It is the community fork that followed the original faker.js incident. — [GitHub faker-js/faker](https://github.com/faker-js/faker)
- factory_boy: about 3.8k stars, MIT. It supports Django, SQLAlchemy, MongoEngine and Mogo ORMs, offers build/create/stub strategies and SubFactory, and uses Faker for values. Its pitch is to "replace static, hard to maintain fixtures." — [GitHub FactoryBoy/factory_boy](https://github.com/FactoryBoy/factory_boy)
- factory_bot (Ruby): about 331M-345M total RubyGems downloads (two snapshots disagree), about 8.29k stars, 277 contributors. Its pitch is factories as "less error-prone, more explicit" than YAML fixtures. — [rubygems factory_bot](https://rubygems.org/gems/factory_bot); [Ruby Toolbox](https://www.ruby-toolbox.com/projects/factory_bot)
- Hypothesis: about 9.0k stars. Property-based testing that shrinks a failure to the "simplest possible" failing example. — [GitHub HypothesisWorks/hypothesis](https://github.com/HypothesisWorks/hypothesis)
- Mimesis: about 4.8k stars, MIT, 47 locales. It calls itself "the fastest data generator among Python solutions" (no benchmark on the README), has schema-based generators with related datasets/foreign keys, full typing, and pandas/polars plus factory_boy integration. — [GitHub lk-geimfari/mimesis](https://github.com/lk-geimfari/mimesis)
- Polyfactory (Litestar): about 1.5k stars, MIT. It generates mock data from type hints for dataclasses, TypedDicts, Pydantic, msgspec, Odmantic and Beanie, and evolved from pydantic-factories. — [GitHub litestar-org/polyfactory](https://github.com/litestar-org/polyfactory)
- SDV: about 3.6k stars, 422 forks, 149 open issues, Business Source License. Created at MIT's Data to AI Lab in 2016; DataCebo was founded in 2020 to commercialise it. — [GitHub sdv-dev/SDV](https://github.com/sdv-dev/SDV). Search snippets of DataCebo pages claim "18M+ downloads" and a "30K+" community. — [datacebo.com/sdv-dev](https://datacebo.com/sdv-dev/) (not fetched)
- Synth (shuttle-hq, Rust, declarative): about 1.5k stars, Apache-2.0, still labelled "Public Alpha". It imports from Postgres/MySQL/MongoDB and infers relations. — [GitHub shuttle-hq/synth](https://github.com/shuttle-hq/synth)
- Snaplet Seed (now supabase-community/seed): about 790 stars, MIT. Deterministic generation via Copycat, automatic relationship handling, a typed TS client generated from the DB, and optional OpenAI/Groq text. — [GitHub supabase-community/seed](https://github.com/supabase-community/seed)
- Neosync: about 4.1k stars, MIT. Repo archived 2025-08-30 after Grow Therapy acquired the company; it did synthetic data, PII anonymisation, subsetting with referential integrity, and sync across environments. — [GitHub nucleuscloud/neosync](https://github.com/nucleuscloud/neosync)
- MOSTLY AI Synthetic Data SDK: Apache-2.0, `pip install 'mostlyai[local]'`, with a LOCAL mode (own compute) and a CLIENT mode (platform). It ships built-in QA/privacy reports and had about 801 stars at the time of the search snippet. — [MOSTLY AI blog](https://mostly.ai/blog/the-synthetic-data-sdk-an-open-source-python-toolkit-for-high-fidelity-privacy-safe-synthetic-data); [GitHub mostly-ai/mostlyai](https://github.com/mostly-ai/mostlyai)

### Inferences
- Faker's dominance (about 63M downloads a month, versus SDV's claimed 18M lifetime) comes from being a tiny, dependency-light primitive that everything else wraps (factory_boy, Polyfactory, Mimesis comparisons, MCP servers). Misata has a better chance of becoming the default if it composes with Faker or factory_boy than if it asks users to replace them.
- Every tool that became a default plugs into an existing workflow (pytest fixture, ORM factory, Rails test helper). Nothing that needs a separate service or account reached that level.
- Faker's low open-issue count and the fact that its top-voted issues are about typing and autocomplete (see section 2) suggest that once a tool works, DX polish (types, IDE completion, quiet logs) matters most.

### Gaps
- No direct pepy/pypistats time series for factory-boy, mimesis, hypothesis, sdv or polyfactory (domains blocked). Fetch these before quoting growth rates.
- Original adoption narratives (for example why Faker overtook alternatives around 2014-2018) were not researched from primary sources.

## 2. What users ask for (issues, forums)

### Takeaway
Users repeatedly ask for referential integrity across tables (the gap that plain Faker leaves), schema-driven generation from an existing DB or ORM, determinism, scale/performance, constraint support, and typing/IDE DX. SDV users mostly complain about multi-table speed and foreign-key cardinality.

### Cited Findings
- Faker's most thumbs-upped issues are DX items: shell tab completion (#1604, 52 reactions), "faker spamming the logs" (#753), the pyfloat error (#1068), "Add mypy" (#1334) and "Missing type hints and VSCode autocompletion" (#1893). — [joke2k/faker issues sorted by reactions](https://github.com/joke2k/faker/issues?q=is%3Aissue+sort%3Areactions-%2B1-desc)
- SDV's most-reacted issues are optional CUDA/torch dependencies (#2173), CTGAN loss extraction (#896), metrics while training (#460), relational data across linked sources (#562, open) and constraints for the HMA1 multi-table model (#296). — [SDV issues sorted by reactions](https://github.com/sdv-dev/SDV/issues?q=is%3Aissue+sort%3Areactions-%2B1-desc)
- SDV multi-table complaints:
  - A user reported that HMASynthesizer took about 3 days for 1M rows with constraints and asked about GPU support and trials of the paid synthesizers (July 2024). — [SDV #2110](https://github.com/sdv-dev/SDV/issues/2110)
  - Other issues: HMA "always creates a child for every parent row" ([#1673](https://github.com/sdv-dev/SDV/issues/1673)), HMA "may sample foreign key values which were not present" ([#1581](https://github.com/sdv-dev/SDV/issues/1581)), a foreign key that references multiple tables ([#2136](https://github.com/sdv-dev/SDV/issues/2136)), and constraint errors on a child with multiple parents ([#2087](https://github.com/sdv-dev/SDV/issues/2087)).
  - Search snippets also say SDV added a warning when HMA is likely to be slow, and that modelling more than 5 tables causes memory/performance problems on a standard machine. — [DataCebo multi-table synthesizers blog](https://datacebo.com/blog/multi-table-synthesizers/) (not fetched)
- "Faker ... generates single fake values ... with no awareness of your schema or foreign keys", and "Faker and Mockaroo generate independent rows." — [seedbase.dev vs Faker](https://seedbase.dev/vs/faker) (competitor marketing); the same theme appears in [Oracle dev blog on Faker with referential integrity](https://blogs.oracle.com/developers/using-fakerjsfaker-to-generate-test-data-respecting-referential-integrity-in-oracle-database-23c) and [json-schema-faker issue #299 "Generate Relational Data"](https://github.com/json-schema-faker/json-schema-faker/issues/299)
- There is a long tail of small FK-aware Faker wrappers (tablefaker YAML schemas, sql-faker, tsfaker built for a database with hundreds of tables). — [table-faker](https://github.com/necatiarslan/table-faker); [sql-faker](https://github.com/GsiorX/sql-faker); [tsfaker](https://pypi.org/project/tsfaker/)
- Recurring Show HN launches target the same need, for example "Seed your Postgres database with production-like data" (Snaplet, 2023), "A tool to seed your dev database with real data" (2022), Neosync (2024) and "DDL to Data" (SQL DDL to FK-preserving data for Postgres/MySQL). — [HN 37800964](https://news.ycombinator.com/item?id=37800964); [HN 31165538](https://news.ycombinator.com/item?id=31165538); [HN 40443927](https://news.ycombinator.com/item?id=40443927); [HN 46511578](https://news.ycombinator.com/item?id=46511578) (titles from search; comment threads not readable here)
- Neosync's pitch lists the features users wanted from that class of tool: preserving PKs, FKs, unique constraints, circular dependencies and sequences, plus anonymisation and subsetting. — [HN Show HN: Neosync (search snippet)](https://news.ycombinator.com/item?id=40443927); [GitHub neosync](https://github.com/nucleuscloud/neosync)

### Inferences
- Misata's main differentiator, coherent multi-table data with FKs, is the most cited unmet need. Speed at 1M+ rows across more than 5 tables is a place where SDV visibly fails, so a published benchmark against SDV HMA would be a strong trust signal.
- The Faker issue list says typed APIs, IDE autocompletion and no noisy logging are table stakes.
- Circular FKs, multi-parent children and unique/sequence handling are concrete edge cases to test and document.

### Gaps
- Reddit r/dataengineering, r/Python and HN comment text could not be fetched, so no direct user quotes from forums.
- No issue mining for Mimesis, factory_boy or Synth requests.

## 3. Integrations that matter

### Takeaway
The integrations that drove adoption are test runners (pytest fixtures), ORMs (Django, SQLAlchemy, Rails, Prisma, Drizzle), type-hint/model sources (Pydantic, dataclasses), live-DB introspection, and dataframe outputs. dbt unit tests need small mock input rows (dict/CSV/SQL fixtures), which is a natural target for generation.

### Cited Findings
- Faker ships a pytest fixture, and factory_boy integrates with Django, SQLAlchemy and MongoEngine. — [joke2k/faker](https://github.com/joke2k/faker); [factory_boy](https://github.com/FactoryBoy/factory_boy)
- Polyfactory builds factories from Pydantic, dataclasses, TypedDict, msgspec and ODMs. — [polyfactory](https://github.com/litestar-org/polyfactory)
- Mimesis advertises pandas/polars output and a factory_boy integration. — [mimesis](https://github.com/lk-geimfari/mimesis)
- Prisma has a first-class `seed` hook that runs a seed script on demand or after `migrate reset`, but no official seed library (users bring @faker-js/faker). drizzle-seed generates deterministic data from the Drizzle schema with a seedable PRNG. — [Drizzle Seed docs](https://orm.drizzle.team/docs/seed-overview); [PkgPulse comparison 2026](https://www.pkgpulse.com/guides/drizzle-seed-vs-snaplet-seed-vs-prisma-seed-database-2026)
- Supabase's local-dev docs cover seeding (seed.sql), and the community took over Snaplet Seed. — [Supabase seeding guide](https://supabase.com/docs/guides/local-development/seeding-your-database); [supabase-community/seed](https://github.com/supabase-community/seed)
- SeedBase markets reading SQL CREATE TABLE dumps, Django models.py, Prisma schema or a live DB, and emitting rows in FK-safe insertion order. — [seedbase.dev vs Faker](https://seedbase.dev/vs/faker) (competitor marketing)
- dbt unit tests take mock inputs per `ref`/`source` as dict rows, inline YAML or named CSV/SQL fixtures, and are hand-written today. — [dbt docs: unit tests](https://docs.getdbt.com/reference/resource-properties/unit-tests). There is also a dbt-labs agent skill, "adding-dbt-unit-test". — [mcpservers.org](https://mcpservers.org/agent-skills/dbt-labs/adding-dbt-unit-test)
- Synth and Neosync both put DB import/introspection (Postgres, MySQL, Mongo) at the front of their pitch. — [synth](https://github.com/shuttle-hq/synth); [neosync](https://github.com/nucleuscloud/neosync)

### Inferences
- Integrations ranked by evidence:
  1. A pytest fixture/plugin.
  2. Live Postgres/MySQL introspection with FK-ordered insert.
  3. SQLAlchemy/Django model import (Django is already done in Misata 0.9.7).
  4. Pydantic/dataclass import.
  5. Prisma schema import plus a `prisma db seed`-compatible output.
  6. dbt: generate `given:` rows or CSV fixtures for unit tests from the manifest.
  7. DuckDB/Polars/Parquet outputs.
- No evidence was gathered for Airflow/Dagster, Snowflake/BigQuery, OpenAPI, Avro or Protobuf demand. Treat these as lower priority until validated.

### Gaps
- Not researched: GitHub Actions/Docker usage patterns, the Snowflake/BigQuery seeding pain, OpenAPI/JSON Schema/Avro sources, or dbt manifest-driven generators.

## 4. LLM-era tooling (MCP, agents, prompt-to-schema)

### Takeaway
Since 2025 the market has moved quickly to natural-language and agent-driven data generation. Tonic launched the Fabricate Data Agent (November 2025) and a Textual MCP server, and several small MCP-native seeders exist (Seedfast, SeedBase, Seedforge, Faker MCP servers). Most are hosted or Postgres-only, and an open-source, local, Python-first MCP server for multi-table generation is not clearly established.

### Cited Findings
- Tonic acquired Fabricate in April 2025 for "schema-first, AI-powered data generation" and launched the Fabricate Data Agent at AWS re:Invent in November 2025. It generates relational, domain-specific data from natural-language prompts, uploaded schemas or sample data. — [Tonic press release: Data Agent](https://www.tonic.ai/press-releases/tonic-launches-fabricate-data-agent); [Tonic acquires Fabricate](https://www.tonic.ai/press-releases/tonic-ai-acquires-fabricate-expanding-its-leadership-in-synthetic-data)
- Tonic's Textual MCP server is open source, has 21 tools, and handles PII detection, redaction and synthesis across 50+ languages for Claude Desktop/Cursor/Windsurf (announced around March 2026). — [Tonic blog](https://www.tonic.ai/blog/announcing-tonic-textual-mcp-server); [Security Boulevard](https://securityboulevard.com/2026/03/announcing-the-tonic-textual-mcp-server-pii-redaction-meets-ai-agents/)
- Seedfast is an MCP server that seeds Postgres from its live schema with valid FKs, driven by natural language from the IDE agent. — [Seedfast MCP](https://mcpservers.org/servers/seedfa-st-docs-mcp-setup-guide); [seedfa.st](https://seedfa.st/)
- SeedBase is an MCP connector for FK-consistent, context-aware data for AI agents. — [Glama: SeedBase](https://glama.ai/mcp/connectors/io.github.marcelglaeser/seedbase)
- Seedforge is self-hostable, CI-ready and "MCP-native." — [mcpmarket Seedforge](https://mcpmarket.com/server/seedforge)
- A Faker-based QA test-data MCP server also exists. — [Custom MCP Test Data Generator](https://github.com/praveen1993kp/custom-mcp---test-data-generator)
- Snaplet Seed had already added optional LLM text (OpenAI/Groq) before it shut down. — [supabase-community/seed](https://github.com/supabase-community/seed)
- MOSTLY AI moved to an open-source Apache-2.0 SDK with local training. — [MOSTLY AI SDK](https://mostly.ai/synthetic-data-sdk)

### Inferences
- "Describe your data and have the agent seed it" is now a commodity pitch. Misata can differentiate on running locally and deterministically with no LLM call required (a story-to-schema step that is reproducible), on Python/dataframe output, and on realism that can be checked (distributions, FK cardinality), rather than on having MCP at all.
- An MCP server should expose introspection of the live DB plus FK-ordered insert, because that is what Seedfast and SeedBase lead with.

### Gaps
- Not covered: Gretel Navigator's current status after the NVIDIA acquisition, a MOSTLY AI assistant/MCP, and developer surveys on what agents need from test data.

## 5. Trust signals: licence, stability, reproducibility, governance

### Takeaway
Permissive licences (MIT/Apache) correlate with default status. SDV's move to BSL shows that a restrictive licence can coexist with enterprise use but leaves the open-source slot open. Determinism under a seed is a baseline expectation (Faker, drizzle-seed, Snaplet/Copycat). Vendor-backed OSS has a visible shutdown risk.

### Cited Findings
- DataCebo moved SDV libraries from MIT to BSL 1.1 (search snippets put the timing at late 2022/2023). The change date is four years after each release, after which the code becomes MIT. DataCebo says BSL downloads later exceeded pre-BSL downloads. — [DataCebo: Updating the SDV License](https://datacebo.com/blog/sdv-bsl-license/) and [SDGym LICENSE](https://github.com/sdv-dev/SDGym/blob/main/LICENSE) (DataCebo pages not fetchable here; claims come from search snippets)
- drizzle-seed promotes deterministic output from a seedable PRNG, and Faker docs and seeding guides stress fixed seeds for team/CI reproducibility. — [Drizzle Seed](https://orm.drizzle.team/docs/seed-overview)
- Faker advertises seeding for reproducible results, and Snaplet Seed advertises deterministic generation via Copycat. — [joke2k/faker](https://github.com/joke2k/faker); [supabase-community/seed](https://github.com/supabase-community/seed)
- MOSTLY AI ships a built-in QA report that quantifies fidelity and privacy, used as a trust artefact. — [MOSTLY AI SDK blog](https://mostly.ai/blog/the-synthetic-data-sdk-an-open-source-python-toolkit-for-high-fidelity-privacy-safe-synthetic-data)
- Synth has stayed labelled "Public Alpha", a weak stability signal. — [synth](https://github.com/shuttle-hq/synth)
- Faker publishes its Python support policy (3.8+, Python 2 dropped in v4), and factory_boy publishes a support policy for Python, Django and SQLAlchemy versions. — [joke2k/faker](https://github.com/joke2k/faker); [factory_boy](https://github.com/FactoryBoy/factory_boy)

### Inferences
- For Misata, the trust signals to show are: MIT/Apache licence stated prominently, a written stability/semver policy (already done per task #1), a "same seed gives byte-identical output across versions" guarantee or a clearly versioned exception policy, a published benchmark against SDV and Faker scripts, and a quality/fidelity report.
- Shutdowns tied to a vendor (Snaplet, Neosync) suggest highlighting governance and the fact that Misata does not depend on a hosted service.

### Gaps
- Not verified: the exact SDV BSL effective date, the precise restriction text, and community reaction threads.

## 6. Pricing pressure and the market gap

### Takeaway
Between 2024 and 2025 the open-source "seed my dev DB with realistic relational data" space lost its best-funded players: Snaplet shut down (August 2024), Neosync was acquired and archived (August 2025), and Gretel went to NVIDIA (March 2025). SDV is BSL, and Tonic, the main remaining vendor, is commercial and moving toward agents. Small competitors are explicitly marketing themselves as Snaplet and Neosync replacements.

### Cited Findings
- Snaplet shut down on 2024-08-31 after starting in 2021, saying it "did not reach the necessary adoption levels". It open-sourced Seed, Snapshot and Copycat. — [Snaplet blog: shutting down](https://www.snaplet.dev/post/snaplet-is-shutting-down); [Snaplet on X](https://twitter.com/_snaplet/status/1807705240709349643)
- @snaplet/seed is now community-maintained at supabase-community/seed with only "occasional fixes", and Snapshot was archived on 2025-11-05. — [DEV: Snaplet alternative 2026](https://dev.to/jakelaz/snaplet-alternative-in-2026-what-to-use-after-snaplet-shut-down-fh5) (search snippet; author likely promotes an alternative)
- Grow Therapy acquired Neosync on 2025-08-01 (announced 2025-09-25), and the repo was archived on 2025-08-30. Some sources describe the deal as an acqui-hire for privacy engineering. — [GitHub neosync](https://github.com/nucleuscloud/neosync); [Grow Therapy blog](https://growtherapy.com/blog/improving-privacy-in-mental-health/); [PR Newswire](https://www.prnewswire.com/news-releases/grow-therapy-raises-the-privacy-bar-in-mental-health-302567153.html); acqui-hire framing from [seedfa.st](https://seedfa.st/compare/neosync-alternative) (competitor)
- NVIDIA acquired Gretel (about 80 staff) in March 2025 for a reported nine-figure sum, above its $320M valuation, and is folding it into NVIDIA's generative-AI cloud services. — [TechCrunch](https://techcrunch.com/2025/03/19/nvidia-reportedly-acquires-synthetic-data-startup-gretel); [SiliconANGLE](https://siliconangle.com/2025/03/19/nvidia-reportedly-acquires-gretel-320m-strengthen-ai-training-tools/)
- New entrants position themselves explicitly as Snaplet, Neosync or drizzle-seed replacements: Seedfast, Basecut, feint and SeedBase. — [seedfa.st Snaplet alternative](https://seedfa.st/blog/snaplet-seed-alternative); [feint](https://ewry.net/feint/snaplet-alternative/); [seedfa.st drizzle-seed alternative](https://seedfa.st/compare/drizzle-seed-alternative)
- MOSTLY AI chose Apache-2.0 for its SDK (early 2025), the opposite direction from SDV's BSL. — [Tech.eu](https://tech.eu/2025/02/03/the-future-of-ai-innovation-starts-with-synthetic-data-and-an-open-source-sdk/)

### Inferences
- There is a real vacancy for a permissively licensed, locally run, multi-table generator with live-DB seeding. Snaplet users (mostly TypeScript/Postgres/Supabase) and Neosync users (Postgres/MySQL, anonymisation) are orphaned. A Python-first Misata could capture them through Postgres introspection and seeding, a Supabase/Prisma-friendly SQL output, and a migration guide titled "coming from Snaplet Seed / Neosync".
- Snaplet's stated failure reason was insufficient adoption for a business, not lack of user need. This argues for low-cost OSS distribution (pip/npx, CI, MCP) over a hosted product.

### Gaps
- No pricing data was gathered for Tonic, MOSTLY AI or SDV Enterprise.
- No hard numbers on how many users migrated after the shutdowns.
