# Open-source synthetic / fake / test data landscape vs Misata (as of 2026-10-03)

Method note: GitHub numbers (stars, forks, last push, archived flag, license) were pulled on 2026-10-03 from the GitHub search API through the GitHub MCP tool. PyPI latest version, release date, first release date, release count and license come from the `pypi.org/pypi/<pkg>/json` endpoint on the same day, and npm data from `registry.npmjs.org`. pypistats.org, pepy.tech, api.npmjs.org, libraries.io, NuGet search, Maven Central search and the ClickHouse PyPI dataset were all blocked by the network egress proxy. So the monthly download figures below come only from search-engine snippets of pypistats/npm pages, are labelled as such, and could not be checked first-hand. I could not collect contributor counts, because the per-repo GitHub API was not enabled for this session.

## Adoption snapshot (reference table)

### Takeaway
Adoption is very uneven. The value-level fakers (Faker 19.4k stars, roughly 63M PyPI downloads a month; @faker-js/faker 15.5k stars, roughly 17M npm downloads a week) and Hypothesis (9.0k stars, roughly 48M a month) are one to two orders of magnitude ahead of every "synthesizer". SDV (3.6k stars) leads model-based tabular synthesis but is now BUSL-licensed. Misata has 69 stars and its first PyPI release was 2025-12-16.

### Cited Findings
| Tool | Job | GH stars / forks | Last push | License | Latest release | Source |
|---|---|---|---|---|---|---|
| joke2k/faker (Python) | value faker | 19,421 / 2,124 | 2026-09-29 | MIT | 40.40.0, 2026-09-29; first release 2010-12-23; 507 releases | [GitHub](https://github.com/joke2k/faker), [PyPI JSON](https://pypi.org/pypi/faker/json) |
| faker-js/faker | value faker (JS) | 15,506 / 1,126 | 2026-10-02 | MIT (npm) | 10.6.0, 2026-08-14; package created 2022-01-10 | [GitHub](https://github.com/faker-js/faker), [npm registry](https://registry.npmjs.org/@faker-js/faker) |
| bchavez/Bogus (.NET) | value faker | 9,739 / 538 | 2025-12-22 | MIT-like (NOASSERTION on GH) | NuGet registration upper version 35.6.5 | [GitHub](https://github.com/bchavez/Bogus), [NuGet API](https://api.nuget.org/v3/registration5-semver1/bogus/index.json) |
| lk-geimfari/mimesis | value faker | 4,840 / 364 | 2026-09-29 | MIT | 22.2.0, 2026-09-23; first 2017-07-15 | [GitHub](https://github.com/lk-geimfari/mimesis), [PyPI JSON](https://pypi.org/pypi/mimesis/json) |
| datafaker-net/datafaker (JVM) | value faker | 1,800 / 242 | 2026-10-01 | Apache-2.0 | (Maven not reachable) | [GitHub](https://github.com/datafaker-net/datafaker) |
| HypothesisWorks/hypothesis | property-based testing | 9,038 / 686 | 2026-09-28 | MPL-2.0 | 6.168.3, 2026-09-28; 1,571 releases | [GitHub](https://github.com/HypothesisWorks/hypothesis), [PyPI JSON](https://pypi.org/pypi/hypothesis/json) |
| schemathesis/schemathesis | API property testing | 3,645 / 226 | 2026-10-02 | MIT | 4.29.0, 2026-10-01; 488 releases | [GitHub](https://github.com/schemathesis/schemathesis), [PyPI JSON](https://pypi.org/pypi/schemathesis/json) |
| python-jsonschema/hypothesis-jsonschema | JSON-schema strategies | 280 / 37 | 2025-12-05 | MPL-2.0 | 0.23.1, 2024-02-28 | [GitHub](https://github.com/python-jsonschema/hypothesis-jsonschema), [PyPI JSON](https://pypi.org/pypi/hypothesis-jsonschema/json) |
| FactoryBoy/factory_boy | ORM fixtures | 3,810 / 424 | 2026-01-01 | MIT | 3.3.3, 2025-02-03 | [GitHub](https://github.com/FactoryBoy/factory_boy), [PyPI JSON](https://pypi.org/pypi/factory-boy/json) |
| litestar-org/polyfactory | Pydantic/dataclass factories | 1,513 / 121 | 2026-10-02 | MIT | 3.3.0, 2026-02-22; first 2023-04-01 | [GitHub](https://github.com/litestar-org/polyfactory), [PyPI JSON](https://pypi.org/pypi/polyfactory/json) |
| model-bakers/model_bakery | Django fixtures | 1,007 / 107 | 2026-10-01 | Apache-2.0 | 1.24.1, 2026-09-22 | [GitHub](https://github.com/model-bakers/model_bakery), [PyPI JSON](https://pypi.org/pypi/model-bakery/json) |
| sdv-dev/SDV | model-based tabular/relational | 3,568 / 422 | 2026-09-30 | BUSL-1.1 | 1.38.5, 2026-09-28 | [GitHub](https://github.com/sdv-dev/SDV), [PyPI JSON](https://pypi.org/pypi/sdv/json) |
| sdv-dev/CTGAN | GAN model | 1,572 / 335 | 2026-09-14 | BUSL-1.1 | 0.12.1, 2026-02-13 | [GitHub](https://github.com/sdv-dev/CTGAN), [PyPI JSON](https://pypi.org/pypi/ctgan/json) |
| mostly-ai/mostlyai | model-based (TabularARGN) | 802 / 67 | 2026-09-23 | Apache-2.0 | 6.1.5, 2026-09-23; 146 releases | [GitHub](https://github.com/mostly-ai/mostlyai), [PyPI JSON](https://pypi.org/pypi/mostlyai/json) |
| vanderschaarlab/synthcity | research benchmark/synth | 687 / 98 | 2026-04-21 | Apache-2.0 | 0.2.12, 2025-05-08 | [GitHub](https://github.com/vanderschaarlab/synthcity), [PyPI JSON](https://pypi.org/pypi/synthcity/json) |
| gretelai/gretel-synthetics | model-based + DP | 683 / 103 | 2025-06-24 | Gretel source-available | 0.22.20, 2025-06-24; **archived** | [GitHub](https://github.com/gretelai/gretel-synthetics), [PyPI JSON](https://pypi.org/pypi/gretel-synthetics/json) |
| NVIDIA-NeMo/DataDesigner | LLM + sampler declarative SDG | 2,298 / 216 | 2026-10-02 | Apache-2.0 | data-designer 0.9.3, 2026-09-21; first 2025-11-20; repo created 2025-10-16 | [GitHub](https://github.com/NVIDIA-NeMo/DataDesigner), [PyPI JSON](https://pypi.org/pypi/data-designer/json) |
| ydata-synthetic | GAN tabular/time series | (repo not returned by search) | — | custom | 2.0.1, 2026-04-23 (migration shim) | [PyPI JSON](https://pypi.org/pypi/ydata-synthetic/json) |
| ydata-sdk | YData commercial SDK | — | — | YData proprietary licence text | 3.2.3, 2026-02-27; first 2025-01-23 | [PyPI JSON](https://pypi.org/pypi/ydata-sdk/json) |
| DataSynthesizer | Bayesian-net DP synth | — | — | MIT | 0.1.13, 2023-10-18 (stale) | [PyPI JSON](https://pypi.org/pypi/datasynthesizer/json) |
| be-great (GReaT, LLM tabular) | LLM fine-tune tabular | — | — | MIT | 0.0.14, 2026-05-12; 13 releases total | [PyPI JSON](https://pypi.org/pypi/be-great/json) |
| tdspora/syngen | VAE tabular | 18 / 12 | 2026-09-25 | GPL-3.0 | 1.0.12, 2026-09-25 | [GitHub](https://github.com/tdspora/syngen) |
| supabase-community/seed (ex-Snaplet) | schema-aware DB seeder | 790 / 36 | 2026-10-01 | MIT (repo); npm @snaplet/seed FSL-1.1-MIT | npm 0.98.0, 2024-07-30 (no release since) | [GitHub](https://github.com/supabase-community/seed), [npm registry](https://registry.npmjs.org/@snaplet/seed) |
| shuttle-hq/synth | declarative DB generator (Rust) | 1,486 / 111 | 2024-09-27 | Apache-2.0 | README still says "Public Alpha" | [GitHub](https://github.com/shuttle-hq/synth) |
| nucleuscloud/neosync | anonymize + synth + sync | 4,139 / 233 | 2025-08-30 | MIT-ish (NOASSERTION) | **archived** | [GitHub](https://github.com/nucleuscloud/neosync) |
| databrickslabs/dbldatagen | Spark-scale generator | 498 / 105 | 2026-08-07 | Databricks License | PyPI 0.4.0.post1, 2024-07-26 | [GitHub](https://github.com/databrickslabs/dbldatagen), [PyPI JSON](https://pypi.org/pypi/dbldatagen/json) |
| drizzle-seed | ORM seeder (TS) | — | — | Apache-2.0 | 0.3.1, 2025-01-29 | [npm registry](https://registry.npmjs.org/drizzle-seed) |
| TonicAI/condenser | DB subsetting | 337 / 53 | 2025-07-28 | MIT | — | [GitHub](https://github.com/TonicAI/condenser) |
| rapiddweller-benerator-ce | Java generator/anonymizer | 162 / 27 | 2026-09-24 | NOASSERTION | — | [GitHub](https://github.com/rapiddweller/rapiddweller-benerator-ce) |
| plaitpy/plaitpy | YAML fake-data modeler | 437 / 22 | 2018-12-27 | MIT | 0.1.1, 2018-01-26 (dead) | [GitHub](https://github.com/plaitpy/plaitpy), [PyPI JSON](https://pypi.org/pypi/plaitpy/json) |
| pydbgen | fake DB tables | — | — | MIT | 1.0.5, 2018-03-11, only release (dead) | [PyPI JSON](https://pypi.org/pypi/pydbgen/json) |
| confluentinc/kafka-connect-datagen | Kafka demo stream gen | 52 / 92 | 2026-10-03 | Apache-2.0 | — | [GitHub](https://github.com/confluentinc/kafka-connect-datagen) |
| MaterializeInc/datagen | Kafka/Postgres mock data | 170 / 21 | 2025-09-13 | Apache-2.0 | **archived** | [GitHub](https://github.com/MaterializeInc/datagen) |
| ShadowTraffic | streaming/DB traffic sim | examples repo 52 stars (engine is closed source) | 2026-09-28 | commercial | — | [GitHub](https://github.com/ShadowTraffic/shadowtraffic-examples) |
| redpanda-data/connect (Benthos) | stream processor with `generate` input | 8,775 / 974 | 2026-10-02 | mixed | — | [GitHub](https://github.com/redpanda-data/connect) |
| rasinmuhammed/misata | outcome-conformant relational synth | 69 / 3 | 2026-10-01 | MIT | 0.9.6.60, 2026-09-28; first 2025-12-16; 125 releases | [GitHub](https://github.com/rasinmuhammed/misata), [PyPI JSON](https://pypi.org/pypi/misata/json) |

Download figures (search snippets of pypistats/npm pages, not checked first-hand):
- Faker (Python): 63,470,337 downloads last month; the snippet listed the latest version as 40.39.0, which dates it to about September 2026 — [pypistats Faker](https://pypistats.org/packages/faker) (via search snippet)
- Hypothesis: ~48,026,434/month, ~11.18M/week, ~1.37M/day — [pypistats hypothesis](https://pypistats.org/packages/hypothesis) (via search snippet)
- factory-boy: 22,912,485 last month — [pypistats factory-boy](https://pypistats.org/packages/factory-boy) (via search snippet)
- polyfactory: 11,692,057 last month — [pypistats polyfactory](https://pypistats.org/packages/polyfactory) (via search snippet)
- @faker-js/faker: 17,313,684 weekly downloads per one snippet; the search summary noted other sources range from ~8.9M to 18.5M/week — [npm @faker-js/faker](https://www.npmjs.com/package/@faker-js/faker), [npmtrends](https://npmtrends.com/@faker-js/faker-vs-faker) (conflicting, via search snippet)
- The original faker.js was "downloaded over 20 million times a month" when it was sabotaged in Jan 2022 — [i-programmer](https://www.i-programmer.info/news/136-open-source/15154-faker-re-released-as-community-controlled-project.html)
- SDV: 10 million cumulative downloads announced 2025-01-12, and "more than 18 million downloads, cited in over 5,000 research papers, used by more than 30,000 data scientists" announced with SDV 2.0 on 2026-09-15 — [DataCebo 10M announcement](https://datacebo.com/announcements/sdv-reaches-10-million-downloads/); [PR Newswire SDV 2.0](https://www.prnewswire.com/news-releases/datacebo-releases-sdv-2-0-for-building-generative-relational-models-of-enterprise-data-302879009.html) (both via search snippets)

### Inferences
- Faker's ~63M downloads a month is about 3.5x SDV's entire cumulative download count (18M) every month. Value-level fakers are infrastructure. Synthesizers are niche tools.
- Among close peers in the "declarative, relational, from-scratch" niche, NeMo Data Designer (2.3k stars within about a year, NVIDIA-backed) is the fastest-rising competitor. Synth (1.5k) and Snaplet seed (790) are the incumbents by stars, and both are effectively frozen.

### Gaps
- No verified monthly downloads for mimesis, SDV, mostlyai, synthcity, ydata, be-great, misata, data-designer, dbldatagen, Bogus (NuGet), Datafaker (Maven): every download-stat host was blocked by the egress proxy.
- No contributor counts: the per-repo GitHub API (`/contributors`) was not enabled for this session.
- I could not get the repo stats for ydata-synthetic, DataSynthesizer and be_great. The GitHub search returned no matching repos, possibly because they moved: ydata-synthetic now appears under "Data-Centric-AI-Community/ydata-synthetic".

## Value-level fakers: Faker, Mimesis, Faker.js, Datafaker, Bogus — why is Faker the default despite its limits?

### Takeaway
Faker (Python) is the default because it got there first (first PyPI release December 2010) and was then built into the testing toolchain: a pytest plugin, factory_boy's `factory.Faker`, and polyfactory. That beats Mimesis's large measured speed and uniqueness advantage. None of these tools does cross-row or cross-table semantics, aggregates, or FK integrity. That gap is exactly where Misata sits.

### Cited Findings
- Faker's first PyPI upload was 2010-12-23, and it has shipped 507 releases (latest 40.40.0 on 2026-09-29) — [PyPI JSON](https://pypi.org/pypi/faker/json)
- Faker ships its own pytest plugin providing a `faker` fixture: session-scoped, en-US default, reseeded with 0 before each test, `.unique` cleared, with locale and seed overridable via `faker_session_locale` / `faker_seed` fixtures — [Faker docs: Pytest Fixtures](https://faker.readthedocs.io/en/master/pytest-fixtures.html)
- factory_boy wraps Faker directly: `factory.Faker` takes a provider name plus a locale and passes other kwargs to the underlying provider — [factory_boy factory.faker source](https://factoryboy.readthedocs.io/en/latest/_modules/factory/faker.html)
- polyfactory has an open issue about reusing the pytest `faker` fixture instance, and another about supporting mimesis as an alternative provider. Faker is the built-in default — [polyfactory #441](https://github.com/litestar-org/polyfactory/issues/441), [polyfactory #394](https://github.com/litestar-org/polyfactory/issues/394)
- Faker is organized as "providers" of "fakes" with locale fallback to en_US — [Faker PyPI](https://pypi.org/project/Faker/40.39.0/)
- Mimesis benchmark: 10k names in 0.137s (99.88% unique) vs Faker 1.758s (93.63%); 1M names in 13.7s (84.76% unique) vs Faker 185.9s (33.02% unique); "≈12 times faster". Mimesis uses pre-computed datasets and skips regex-based generation — [Mimesis about page](https://mimesis.name/latest/about.html) (vendor benchmark)
- faker.js history: maintainer Marak Squires posted "No more free work from Marak — Pay Me or Fork This" (Nov 2020). On 2022-01-04/05 he force-pushed a wipe and shipped an infinite-loop release (npm `faker` 6.6.6, 2022-01-05, still the final version of that package). The community forked it as @faker-js/faker with multi-maintainer governance, and the fork overtook the original — [BleepingComputer](https://www.bleepingcomputer.com/news/security/dev-corrupts-npm-libs-colors-and-faker-breaking-thousands-of-apps/), [Faker team announcement 2022-01-14](https://fakerjs.dev/about/announcements/2022-01-14.html), [npm registry faker](https://registry.npmjs.org/faker), [npm registry @faker-js/faker](https://registry.npmjs.org/@faker-js/faker)
- Each language has its own default faker: Bogus for .NET ("Based on and ported from faker.js"; 9.7k stars) and Datafaker for JVM (1.8k stars, Apache-2.0, active October 2026) — [Bogus GitHub](https://github.com/bchavez/Bogus), [Datafaker GitHub](https://github.com/datafaker-net/datafaker)
- Faker brands now reach LLM agents too. Several "Faker MCP servers" (e.g., funsjanssen/faker-mcp, vinkius-labs/faker-mcp) expose Faker.js to Claude Desktop, Cursor, Copilot and Cline, and some claim "structured datasets with referential integrity" — [funsjanssen/faker-mcp](https://github.com/funsjanssen/faker-mcp), [Glama listing](https://glama.ai/mcp/servers/vinkius-labs/faker-mcp), [fjan.nl blog](https://www.fjan.nl/en/posts/why-and-when-to-use-the-faker-mcp-server-inside-ai-agents-like-github-copilot)

### Inferences
- Faker's moat is that other tools depend on it, not its quality. Once factory_boy, polyfactory and pytest fixtures all called Faker, Mimesis's 12x speed advantage did not matter. Misata should compose with Faker (a Faker provider bridge, or factory_boy/polyfactory interop) rather than compete with it on value generation.
- The faker.js episode shows that a single-maintainer project is a supply-chain risk users now care about. Misata's bus factor of one (69 stars, 3 forks) is a real adoption objection.
- "Faker" has become the generic word in agent tooling (the MCP servers). A Misata MCP server would compete directly with these, and they already claim FK integrity.

### Gaps
- No verified Mimesis, Bogus or Datafaker download counts.
- No primary source found explaining why Faker beat Mimesis. The "first mover plus integrations" explanation is my inference from the release dates and integration points.

## Model / statistical tabular synthesis: SDV, Synthcity, YData, Mostly AI SDK, Gretel, DataSynthesizer, synthpop, GReaT/LLM

### Takeaway
SDV is still the brand default for "learn from real data, emit synthetic tables, including multi-table". But it is BUSL-1.1 (late 2022/2023), and DataCebo is pushing toward paid SDV Enterprise 2.0 (Sept 2026, from $500/month). That leaves room for permissive alternatives: Mostly AI's Apache-2.0 SDK (Jan 2025) and NVIDIA's Apache-2.0 NeMo Data Designer (from Gretel). Gretel's own OSS and YData's OSS were wound down. All of these optimize fidelity to source data. A peer-reviewed-style preprint by Misata's author argues these learned synthesizers miss declared aggregates by 74 to 86%.

### Cited Findings
- SDV license change: DataCebo moved SDV ecosystem libraries from MIT to the Business Source License 1.1 in late 2022/2023. The stated reason was to stop "others with marketing megaphones" using parts of SDV as a "shortcut vehicle". PyPI metadata for sdv 1.38.5 and ctgan 0.12.1 both declare `BUSL-1.1` — [DataCebo: Updating the SDV License](https://datacebo.com/blog/sdv-bsl-license/) (via search snippet), [PyPI sdv JSON](https://pypi.org/pypi/sdv/json), [PyPI ctgan JSON](https://pypi.org/pypi/ctgan/json)
- SDV 2.0 (2026-09-15) builds "one generative relational model" across an enterprise database. It automates PK/FK/composite-key detection, detects and enforces business constraints, and "generate[s] task-specific datasets". SDV Enterprise 2.0 connects to Oracle, SQL Server, BigQuery, Spanner and AlloyDB. Self-service consumption pricing starts at $500/month — [PR Newswire / Webull syndication](https://www.webull.com/news/15582334917952512) (via search snippet)
- DataCebo publishes a blog arguing that "Comparisons to SDV Community Are Misleading for Enterprise Evaluation", i.e., the OSS edition is now positioned as a lesser tier — [DataCebo blog](https://datacebo.com/blog/misleading-sdv-community-comparisons/) (title only, via search)
- Mostly AI launched an open-source Synthetic Data SDK (`mostlyai`, Apache-2.0) on 2025-01-23. It is powered by TabularARGN, supports differential privacy, and runs in LOCAL (on-prem) or CLIENT (hosted platform) mode. Generators are compatible with its Enterprise Platform — [BigDATAwire](https://www.bigdatawire.com/this-just-in/mostly-ai-unveils-open-source-toolkit-for-synthetic-data-generation/), [Mostly AI blog](https://mostly.ai/blog/unlocking-ai-training-data-for-all-mostly-ai-releases-worlds-first-industry-grade-open-source-toolkit-for-synthetic-data), [arXiv 2508.00718](https://arxiv.org/html/2508.00718)
- The mostly.ai homepage now reads "MOSTLY AI powered by Syntho", suggesting a corporate combination with Syntho. Date and terms are not verified — [mostly.ai](https://mostly.ai/)
- NVIDIA acquired Gretel (announced around GTC, March 2025; reported nine figures, above Gretel's last $320M valuation; ~80 employees) — [TechCrunch 2025-03-19](https://techcrunch.com/2025/03/19/nvidia-reportedly-acquires-synthetic-data-startup-gretel)
- gretel-synthetics is archived. The GitHub API shows `archived: true` with last push 2025-06-24, and the last PyPI release is 0.22.20 on 2025-06-24. A search snippet says the archive happened 2026-02-18 (the GitHub API exposes only last-push time, not archive date). Gretel's tech was split into NeMo Data Designer and NeMo Safe Synthesizer — [GitHub gretel-synthetics](https://github.com/gretelai/gretel-synthetics), [PyPI JSON](https://pypi.org/pypi/gretel-synthetics/json), [SynthForge comparison (secondary)](https://synthforge.io/alternatives/gretel/)
- NeMo Data Designer was open-sourced under Apache-2.0. It is "the synthetic data framework used to build Nemotron datasets", incorporates Gretel's technology, and uses "a declarative configuration format in which users define each dataset column" (samplers, LLM columns, structured outputs, validators, LLM-as-judge). Paper: arXiv 2609.17699 (Sept 2026) — [HN thread](https://news.ycombinator.com/item?id=46136055), [arXiv 2609.17699](https://arxiv.org/html/2609.17699v1), [NVIDIA docs](https://docs.nvidia.com/nemo-platform/documentation/design-synthetic-data)
- YData: ydata-synthetic was "originally ... developed in 2020 for educating users" and "not optimized for quality, performance, and scalability". It was renamed `fg-data-synthetic`, and users are steered to the proprietary `ydata-sdk`. Old imports emit deprecation warnings pointing to `ydata.sdk.synthesizers` — [ydata-synthetic PyPI](https://pypi.org/project/ydata-synthetic/), [DeepWiki summary](https://deepwiki.com/ydataai/ydata-synthetic), [YData blog](https://ydata.ai/resources/upgrade-ydata-synthetic)
- Synthcity (Cambridge van der Schaar lab, Apache-2.0) is positioned as a benchmark framework (NeurIPS 2023 Datasets & Benchmarks). Its last PyPI release was 0.2.12 on 2025-05-08 — [NeurIPS paper](https://proceedings.neurips.cc/paper_files/paper/2023/file/09723c9f291f6056fd1885081859c186-Paper-Datasets_and_Benchmarks.pdf), [PyPI JSON](https://pypi.org/pypi/synthcity/json)
- SDV vs Synthcity comparative study: no clear overall winner on statistical similarity; Synthcity's Bayesian Network won the 1:1 experiment — [arXiv 2506.17847](https://arxiv.org/pdf/2506.17847)
- DataSynthesizer has had no release since 0.1.13 (2023-10-18) — [PyPI JSON](https://pypi.org/pypi/datasynthesizer/json)
- synthpop (R) remains the statistical-disclosure-control standard (CART/parametric sequential synthesis). The latest CRAN version is 1.9-2 (2025-07-12) — [CRAN synthpop](https://cran.r-project.org/package=synthpop)
- be-great (GReaT, LLM-based tabular): 13 releases since 2022, latest 0.0.14 on 2026-05-12 — [PyPI JSON](https://pypi.org/pypi/be-great/json)
- Misata's author (Muhammed Rasin) published arXiv 2606.08736 (2026-06-07), "Declarative Outcome-Conformant Synthesis". It argues that conformance and fidelity are orthogonal axes. It reports that off-the-shelf learned synthesizers trained on a real dataset "miss the declared monthly aggregate by 74 to 86 percent" while a closed-form generator reaches 0, and it ships an MIT benchmark — [arXiv 2606.08736](https://arxiv.org/abs/2606.08736)

### Inferences
- The model-based camp is consolidating into vendor funnels. OSS SDKs now feed enterprise platforms (SDV to Enterprise, mostlyai to the Mostly platform, ydata-synthetic to ydata-sdk, Gretel to NVIDIA NeMo). A permissive MIT project with no commercial upsell (Misata) differs on licensing and on intent, which may matter to users burned by the BUSL switch.
- These tools need real data to fit, so they do not compete head-on with Misata's "cold start from a story/schema" use. NeMo Data Designer and SDV 2.0's "task-specific datasets / scenarios" are the two that reach into Misata's space.
- Misata's main differentiator against this camp is exact aggregate conformance, which the arXiv paper benchmarks. It is a clear and defensible claim, but it comes from the author, not an independent party.

### Gaps
- No verified monthly downloads for SDV, mostlyai, synthcity.
- I could not fetch the DataCebo BSL blog directly (blocked), so the exact SDV version and date of the switch are from snippets ("late 2022" and "2023" both appear).
- Mostly AI and Syntho relationship: only the homepage tagline seen; no announcement found.

## Schema / relational seeders: Snaplet seed, Synth, Neosync, dbldatagen, factory_boy / model_bakery / polyfactory, Mockaroo, Benerator, Tonic, Supabase, Prisma/Drizzle

### Takeaway
No healthy OSS default exists for "schema-aware, FK-correct, multi-table seeding." In Python the de facto practice is ORM factories (factory_boy ~23M/month, polyfactory ~12M/month) wrapping Faker, wired by hand. In TypeScript it is a hand-written `prisma/seed.ts` with @faker-js/faker, or the newer drizzle-seed. The dedicated tools all stalled or died: Snaplet shut down in Aug 2024, Neosync was archived in Aug 2025 after an acqui-hire, Synth has had no push since Sept 2024, and plaitpy and pydbgen were abandoned in 2018. This is the most open slot for Misata, but it is also where companies have repeatedly failed to make money.

### Cited Findings
- Snaplet shut down on 2024-08-31 because "they did not reach the necessary adoption levels to continue". It open-sourced Seed and Copycat, and the team joined Supabase, which moved the projects to `supabase-community` — [Snaplet blog](https://www.snaplet.dev/post/snaplet-is-shutting-down) (via search snippet), [Supabase blog: Snaplet is now open source](https://supabase.com/blog/snaplet-is-now-open-source), [Snaplet tweet](https://twitter.com/_snaplet/status/1807705240709349643)
- `@snaplet/seed` latest npm version is 0.98.0, published 2024-07-30, with no release since. Its license is `FSL-1.1-MIT` (Functional Source License) on npm. The supabase-community/seed repo has 790 stars and its last push was 2026-10-01 — [npm registry](https://registry.npmjs.org/@snaplet/seed), [GitHub](https://github.com/supabase-community/seed)
- Snaplet Seed "generates realistic synthetic data based off a database schema and automatically determines the values in your database so you don't have to define each value" — [Supabase blog](https://supabase.com/blog/snaplet-is-now-open-source)
- Neosync: acquired by Grow Therapy (deal dated 2025-09-25 by trackers; founder's tweet about August 2025). It was effectively an acqui-hire for HIPAA data-privacy engineering. The GitHub repo was archived (4,139 stars, last push 2025-08-30) and the cloud product is offline — [Evis Drenova on X](https://x.com/evisdrenova/status/1951401561760080121), [Grow Therapy blog](https://growtherapy.com/blog/improving-privacy-in-mental-health/), [PrivSource](https://www.privsource.com/acquisitions/deal/grow-therapy-acquires-neosync-D8S9Ny), [GitHub](https://github.com/nucleuscloud/neosync)
- Synth (shuttle-hq/getsynth, Rust): "data as code" declarative config, `synth import` from Postgres/MySQL/MongoDB that infers relations and distributions. README still says "Public Alpha". Last push 2024-09-27, not formally archived. Earlier release notes announced new volunteer maintainers — [GitHub](https://github.com/shuttle-hq/synth), [Releases](https://github.com/getsynth/synth/releases)
- dbldatagen (Databricks Labs): Spark-dataframe-based generation at scale, including in Delta Live Tables. It has experimental "generate from existing data or schema". The last PyPI release was 0.4.0.post1 (2024-07-26), though the repo is still pushed (2026-08-07) and the changelog lists unreleased work (type hints, JSON serialization, DBR 13.3 LTS baseline) — [GitHub](https://github.com/databrickslabs/dbldatagen), [CHANGELOG](https://github.com/databrickslabs/dbldatagen/blob/master/CHANGELOG.md), [Docs](https://databrickslabs.github.io/dbldatagen/public_docs/generating_from_existing_data.html)
- Mockaroo (SaaS, not OSS): free tier has 1,000 rows per file and 200 API calls/day. Paid tiers run $60/yr (100k rows) up to $7,500/yr enterprise. It has 200+ field types. It does not connect to your DB, so it cannot read or honor live FK constraints — [Mockaroo pricing](https://www.mockaroo.com/pricing), [Seedfast comparison (vendor)](https://seedfa.st/compare/mockaroo-alternative)
- Prisma has no official seed library, just a `prisma db seed` convention where "you bring @faker-js/faker". drizzle-seed (Apache-2.0, first published 2024-08) does schema-aware automatic generation tied to Drizzle ORM. The naive seed.ts approach "breaks down for complex relational data" because of FK ordering — [PkgPulse guide](https://www.pkgpulse.com/guides/drizzle-seed-vs-snaplet-seed-vs-prisma-seed-database-2026), [npm registry drizzle-seed](https://registry.npmjs.org/drizzle-seed)
- Tonic's OSS footprint is small: condenser (DB subsetting, 337 stars, last push 2025-07-28). Its core products are commercial — [GitHub condenser](https://github.com/TonicAI/condenser)
- Benerator CE (rapiddweller, Java; generate/obfuscate/pseudonymize) is still pushed (2026-09-24) but has only 162 stars — [GitHub](https://github.com/rapiddweller/rapiddweller-benerator-ce)
- plaitpy, a YAML "fake data modeler" and the closest historical analogue to Misata's YAML mode, last released 2018-01-26 and was last pushed 2018-12-27. pydbgen had one release, 2018-03-11 — [GitHub plaitpy](https://github.com/plaitpy/plaitpy), [PyPI pydbgen](https://pypi.org/pypi/pydbgen/json)
- A newer commercial entrant, Seedfast, is publishing aggressive SEO "alternative to Snaplet / Neosync / Mockaroo / Gretel" pages aimed at the orphaned users — [Seedfast Snaplet alternative](https://seedfa.st/blog/snaplet-seed-alternative), [Seedfast Neosync alternative](https://seedfa.st/blog/neosync-alternative)
- A community dev.to post titled "Snaplet Alternative in 2026: What to Use After Snaplet Shut Down" shows users are still looking — [DEV Community](https://dev.to/jakelaz/snaplet-alternative-in-2026-what-to-use-after-snaplet-shut-down-fh5)

### Inferences
- Snaplet seed (TS, Postgres, FK-aware, schema-introspecting) was the nearest product to Misata's "DB schema to relational data" mode, and it is orphaned. Neosync is too. A Python tool with Postgres introspection, FK integrity and a migration guide for Snaplet users could pick up those users. Seedfast is already competing for them commercially.
- Every VC-backed seeder failed on monetization or adoption, not on technology. For Misata this argues for staying a library with low operating cost, embedded in other tools, rather than a hosted product.
- Python ORM factories already have huge distribution (factory_boy ~23M/month). A `misata` to factory_boy/polyfactory bridge, or a pytest fixture, would ride that distribution.

### Gaps
- Supabase's current official seeding docs could not be fetched (blocked). Unknown whether they still recommend @snaplet/seed.
- No adoption numbers for drizzle-seed, model_bakery, or Mockaroo's user base.
- Synth: no announcement of deprecation found; "abandoned" is inferred from no pushes since 2024-09-27.

## Streaming / event and time-series data

### Takeaway
Streaming has no strong OSS default. Confluent's kafka-connect-datagen (fixed quickstart schemas, "not suitable for production") is the demo default. Materialize's datagen was archived in Sept 2025. The most capable tool, ShadowTraffic, is closed source and commercial ($399/yr developer tier). For time series, the OSS options are GAN research codebases (TimeGAN, DoppelGANger via ydata-synthetic or gretel-synthetics, TSGM) and SDV's sequential PAR. Two of those vehicles are now deprecated or archived.

### Cited Findings
- kafka-connect-datagen "generates mock data for demonstration purposes and is not suitable for production". It ships quickstart schemas such as CLICKSTREAM_USERS, ORDERS, RATINGS, USERS and pageviews, installs via Confluent Hub, and is also offered as a managed Confluent Cloud connector — [StreamNative docs](https://docs.streamnative.io/connect/connectors/kafka-connect-datagen/current/kafka-connect-datagen-source), [Confluent Cloud Datagen](https://docs.confluent.io/cloud/current/connectors/cc-datagen-source.html)
- MaterializeInc/datagen generated mock data from a SQL/JSON/Avro schema to Kafka. It is archived (170 stars, last push 2025-09-13) — [GitHub](https://github.com/MaterializeInc/datagen)
- ShadowTraffic is "a containerized service for declaratively generating data ... to mimic your production traffic to Kafka, S3, Postgres, and more". Its founder, Michael Drogalis, previously led Kafka Streams/ksqlDB at Confluent. Pricing: a 30-day trial (600 events/min), Developer at $399/year, and Enterprise unlimited. It integrates with Aiven — [ShadowTraffic](https://shadowtraffic.io/), [Pricing](https://shadowtraffic.io/pricing.html), [Aiven tutorial](https://aiven.io/developer/synthetic-data-for-ai-with-aiven-and-shadowtraffic), [Kafkanated interview](https://getkafkanated.substack.com/p/building-realistic-synthetic-streaming)
- Redpanda Connect (ex-Benthos, 8.8k stars) is a general stream processor; its `generate` input is commonly used for synthetic streams — [GitHub](https://github.com/redpanda-data/connect)
- Time series: ydata-synthetic offered TimeGAN and DoppelGANger; Gretel released a PyTorch DoppelGANger in gretel-synthetics; TSGM is a separate framework — [KDnuggets](https://www.kdnuggets.com/2022/06/generate-synthetic-timeseries-data-opensource-tools.html), [TSGM arXiv 2305.11567](https://arxiv.org/pdf/2305.11567), [TimeGAN repo](https://github.com/jsyoon0823/TimeGAN)

### Inferences
- The "declarative config to realistic event stream" niche is held by a closed-source product (ShadowTraffic). That shows willingness to pay, and it also shows the OSS gap. Misata's event logs and lifecycles plus a Kafka/Postgres sink could fill the gap, though ShadowTraffic is far ahead on streaming ops (rates, throttles, multiple sinks).
- No time-series default exists in OSS. Each prior vehicle (ydata-synthetic, gretel-synthetics) has been deprecated by its vendor.

### Gaps
- I did not verify SDV's PARSynthesizer status or license specifics for sequential data (searches did not surface it).
- No usage numbers for kafka-connect-datagen (its 52 stars understate usage via Confluent Hub/Cloud).

## Property-based testing: Hypothesis, hypothesis-jsonschema, Schemathesis

### Takeaway
Hypothesis is the uncontested Python default (~48M downloads/month, 1,571 releases). Schemathesis is the default for OpenAPI/GraphQL fuzzing. Both generate structurally valid inputs to find bugs, not realistic or semantically coherent datasets, so they complement Misata. The 2025–26 trend of LLM agents writing property-based tests adds to their momentum.

### Cited Findings
- Hypothesis has ~48.0M downloads/month (snippet), 9.0k stars, MPL-2.0, and its latest release is 6.168.3 (2026-09-28) — [pypistats](https://pypistats.org/packages/hypothesis) (snippet), [PyPI JSON](https://pypi.org/pypi/hypothesis/json), [GitHub](https://github.com/HypothesisWorks/hypothesis)
- Schemathesis: 3.6k stars, 488 releases, latest 4.29.0 on 2026-10-01 — [PyPI JSON](https://pypi.org/pypi/schemathesis/json), [GitHub](https://github.com/schemathesis/schemathesis)
- hypothesis-jsonschema has been slow-moving (0.23.1 released 2024-02-28) — [PyPI JSON](https://pypi.org/pypi/hypothesis-jsonschema/json)
- Anthropic published "Finding bugs with Claude and property-based testing" (2026), and an arXiv paper on "Agentic Property-Based Testing: Finding Bugs Across the Python Ecosystem" (2510.09907) exists. An empirical Springer EMSE 2026 article studies PBT use in Python — [Anthropic red team blog](https://red.anthropic.com/2026/property-based-testing/), [arXiv 2510.09907](https://arxiv.org/html/2510.09907v1), [Springer EMSE](https://link.springer.com/article/10.1007/s10664-026-10953-w)

### Inferences
- A Hypothesis strategy adapter (e.g., `misata.strategies` emitting schema-valid relational fixtures) would put Misata where Hypothesis users already work, without competing with it.

### Gaps
- No verified schemathesis download numbers.

## De facto default per job, and what made it the default

### Takeaway
Each default won on distribution (first mover, framework integration, or a platform owner), not on technical superiority.

### Cited Findings
- **Fake values (Python):** Faker. It shipped first (2010), has a pytest plugin, and is the provider inside factory_boy and polyfactory — [PyPI JSON](https://pypi.org/pypi/faker/json), [Faker pytest docs](https://faker.readthedocs.io/en/master/pytest-fixtures.html), [factory_boy](https://factoryboy.readthedocs.io/en/latest/_modules/factory/faker.html)
- **Fake values (JS / .NET / JVM):** @faker-js/faker (community fork after the 2022 sabotage, ~17M weekly downloads per snippet), Bogus, and Datafaker respectively — [faker-js announcement](https://fakerjs.dev/about/announcements/2022-01-14.html), [Bogus](https://github.com/bchavez/Bogus), [Datafaker](https://github.com/datafaker-net/datafaker)
- **Test fixtures / ORM seeding:** factory_boy (Python, ~23M/month), polyfactory for Pydantic (~12M/month), model_bakery for Django. In JS it is Prisma's seed.ts convention with faker-js, or drizzle-seed — [pypistats factory-boy](https://pypistats.org/packages/factory-boy), [pypistats polyfactory](https://pypistats.org/packages/polyfactory), [PkgPulse](https://www.pkgpulse.com/guides/drizzle-seed-vs-snaplet-seed-vs-prisma-seed-database-2026)
- **Schema-aware relational DB seeding:** no living OSS default. The previous leaders were Snaplet seed (shut down 2024-08-31) and Neosync (archived 2025-08-30) — [Supabase blog](https://supabase.com/blog/snaplet-is-now-open-source), [Neosync GitHub](https://github.com/nucleuscloud/neosync)
- **Privacy-preserving / model-based tabular synthesis:** SDV, which got there through MIT academic origins and citations (5,000+ papers per DataCebo) and is now BUSL. The permissive challengers are mostlyai (Apache-2.0) and, in R / official statistics, synthpop — [Webull/PRN syndication](https://www.webull.com/news/15582334917952512), [mostlyai GitHub](https://github.com/mostly-ai/mostlyai), [CRAN synthpop](https://cran.r-project.org/package=synthpop)
- **LLM-driven declarative dataset design:** NeMo Data Designer, which has NVIDIA distribution and the Nemotron pedigree — [arXiv 2609.17699](https://arxiv.org/html/2609.17699v1)
- **Property-based testing:** Hypothesis. API fuzzing: Schemathesis — [GitHub Hypothesis](https://github.com/HypothesisWorks/hypothesis), [GitHub Schemathesis](https://github.com/schemathesis/schemathesis)
- **Streaming demo data:** kafka-connect-datagen, which ships inside the Confluent quickstarts. The capable option is ShadowTraffic (commercial) — [Confluent docs](https://docs.confluent.io/cloud/current/connectors/cc-datagen-source.html), [ShadowTraffic](https://shadowtraffic.io/)
- **Spark-scale generation:** dbldatagen (Databricks Labs) — [GitHub](https://github.com/databrickslabs/dbldatagen)
- **Time series:** no clear OSS default (TimeGAN, DoppelGANger, TSGM research code) — [KDnuggets](https://www.kdnuggets.com/2022/06/generate-synthetic-timeseries-data-opensource-tools.html)

### Inferences
- The two defaults Misata could realistically take are the empty ones: "schema-aware relational seeding (Python)" and "scenario / outcome-driven synthetic analytics data". No living OSS default exists for either.
- What Misata does that none of the above do in OSS: exact declared aggregates (the arXiv paper), story-to-schema from plain English, and lifecycle/SCD2/event-log semantics. What the others do that Misata does not, or does less: learn from real data with DP guarantees (SDV, mostlyai, Safe Synthesizer), LLM-generated free-text columns at scale (Data Designer), Spark-scale throughput (dbldatagen), streaming sinks with rate control (ShadowTraffic), shrinking/bug-finding (Hypothesis), massive locale/provider catalogs (Faker, ~500 releases of provider growth).

### Gaps
- Whether Misata itself does DP, live DB introspection, or streaming sinks was not re-checked in this pass. The comparison relies on the brief's description of Misata.

## Which tools died and why; lessons for Misata

### Takeaway
Tools died in three ways: (1) the venture-backed product failed to monetize and the company shut down or was acqui-hired (Snaplet, Neosync); (2) the OSS was absorbed or relicensed into a vendor funnel (Gretel to NVIDIA, ydata-synthetic to ydata-sdk, SDV to BUSL); (3) single-maintainer burnout or abandonment (faker.js sabotage, plaitpy, pydbgen, DataSynthesizer stale, Synth stalled). The survivors are either community-governed (Faker, faker-js, Hypothesis, factory_boy) or owned by a platform for whom data generation is a loss leader (Confluent datagen, Databricks dbldatagen, NVIDIA Data Designer).

### Cited Findings
- Snaplet: "did not reach the necessary adoption levels to continue"; shut down 2024-08-31 — [Snaplet blog](https://www.snaplet.dev/post/snaplet-is-shutting-down) (via snippet)
- Neosync: acqui-hire by Grow Therapy; repo archived 2025-08-30; cloud offline — [Seedfast (secondary, vendor)](https://seedfa.st/blog/neosync-alternative), [GitHub](https://github.com/nucleuscloud/neosync), [Grow Therapy blog](https://growtherapy.com/blog/improving-privacy-in-mental-health/)
- Gretel: acquired by NVIDIA March 2025; gretel-synthetics archived; tech reborn as Apache-2.0 NeMo Data Designer — [TechCrunch](https://techcrunch.com/2025/03/19/nvidia-reportedly-acquires-synthetic-data-startup-gretel), [GitHub gretel-synthetics](https://github.com/gretelai/gretel-synthetics), [HN](https://news.ycombinator.com/item?id=46136055)
- YData: OSS repositioned as "educational", users routed to ydata-sdk — [ydata-synthetic PyPI](https://pypi.org/project/ydata-synthetic/)
- SDV: MIT to BUSL to protect against competitors free-riding — [DataCebo blog](https://datacebo.com/blog/sdv-bsl-license/) (via snippet)
- Materialize datagen archived 2025 — [GitHub](https://github.com/MaterializeInc/datagen)
- faker.js: maintainer demanded pay ("Pay Me or Fork This", Nov 2020), then sabotaged releases in Jan 2022. The community fork with multi-maintainer governance became the new default — [i-programmer](https://www.i-programmer.info/news/136-open-source/15154-faker-re-released-as-community-controlled-project.html), [HN](https://news.ycombinator.com/item?id=29961274)
- plaitpy (YAML modeler) has been dead since 2018 despite 437 stars. pydbgen shipped a single release in 2018 — [GitHub plaitpy](https://github.com/plaitpy/plaitpy), [PyPI pydbgen](https://pypi.org/pypi/pydbgen/json)

### Inferences
- Lesson 1 (governance): add co-maintainers and a governance or foundation path early. The faker.js case shows single-maintainer risk drives users to a fork. Misata's 3 forks and solo authorship make this its biggest structural weakness.
- Lesson 2 (license credibility): users have now been burned by BUSL (SDV), FSL (@snaplet/seed), vendor deprecations (ydata, Gretel) and shutdowns. A public commitment to keeping Misata MIT for good is a competitive asset worth stating explicitly.
- Lesson 3 (do not depend on a hosted product): Snaplet and Neosync died as SaaS businesses while their OSS cores still had users. Misata should keep its value in the library, so it survives without revenue.
- Lesson 4 (scope): plaitpy and pydbgen show that "YAML to fake tables" alone does not sustain a project. Exact-aggregate conformance, the paper and its benchmark give Misata a sharper, citable reason to exist.
- Lesson 5 (orphaned users): there are concrete migration audiences (Snaplet seed, Neosync, Synth, gretel-synthetics, ydata-synthetic users). Migration guides and importers are cheap ways to win them.

### Gaps
- No post-mortem found for Synth explaining its stall (likely shuttle.rs company pivot, unverified).

## Distribution channels that drove adoption

### Takeaway
Adoption came from being embedded in where developers already work: test frameworks (pytest fixtures, factory_boy, Hypothesis), ORMs and DB platforms (Prisma convention, Drizzle, Supabase picking up Snaplet), data platforms (Confluent Hub, Databricks Labs, NVIDIA NeMo), academia (SDV citations), and now LLM agents (Faker MCP servers, agentic PBT). dbt packages exist but are small.

### Cited Findings
- pytest: Faker ships a pytest plugin with a `faker` fixture — [Faker docs](https://faker.readthedocs.io/en/master/pytest-fixtures.html)
- Fixture libraries: factory_boy's `factory.Faker` wrapper; polyfactory defaults to Faker — [factory_boy](https://factoryboy.readthedocs.io/en/latest/_modules/factory/faker.html), [polyfactory #394](https://github.com/litestar-org/polyfactory/issues/394)
- ORM: drizzle-seed is built into Drizzle's ecosystem; Prisma's `db seed` convention pulls in faker-js — [PkgPulse](https://www.pkgpulse.com/guides/drizzle-seed-vs-snaplet-seed-vs-prisma-seed-database-2026)
- DB platform: Supabase adopted Snaplet's OSS and team — [Supabase blog](https://supabase.com/blog/snaplet-is-now-open-source)
- Data platforms: kafka-connect-datagen via Confluent Hub and Confluent Cloud; dbldatagen via Databricks Labs and Delta Live Tables; Data Designer via NVIDIA NeMo/NGC and OpenRouter tutorials — [Confluent](https://docs.confluent.io/cloud/current/connectors/cc-datagen-source.html), [dbldatagen](https://github.com/databrickslabs/dbldatagen), [OpenRouter blog](https://openrouter.ai/blog/tutorials/distillable-models-and-synthetic-data-pipelines-with-nemo-data-designer/)
- Academia: SDV "cited in over 5,000 research papers"; Synthcity at NeurIPS 2023 — [Webull/PRN](https://www.webull.com/news/15582334917952512), [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2023/file/09723c9f291f6056fd1885081859c186-Paper-Datasets_and_Benchmarks.pdf)
- dbt: `edanalytics/dbt_synth_data` on dbt Package Hub (Snowflake, Postgres, DuckDB, BigQuery, SQLite). It generates distributions and references to other tables in SQL via CTEs, and warns that its output is not fully realistic and not for ML training — [dbt Hub](https://hub.getdbt.com/edanalytics/dbt_synth_data/latest/), [GitHub](https://github.com/edanalytics/dbt_synth_data)
- LLM agents: multiple Faker MCP servers for Claude Desktop, Cursor, Copilot and Cline; NeMo Data Designer tagged `mcp`/`agentic-ai`; agentic PBT work at Anthropic — [funsjanssen/faker-mcp](https://github.com/funsjanssen/faker-mcp), [DataDesigner GitHub](https://github.com/NVIDIA-NeMo/DataDesigner), [Anthropic](https://red.anthropic.com/2026/property-based-testing/)
- Docker: ShadowTraffic ships as a container — [ShadowTraffic](https://shadowtraffic.io/)
- SEO / comparison content: Seedfast publishes many "X alternative" pages targeting orphaned tools — [Seedfast](https://seedfa.st/blog/database-seeding)

### Inferences
- The highest-leverage channels for Misata, in order of evidence: (1) a pytest plugin or fixture and factory_boy/polyfactory interop; (2) an MCP server or agent tool, given that LLM agents are already reaching for "Faker MCP" to get relational data; (3) a dbt package or DuckDB integration for analytics engineers, since dbt_synth_data shows demand but is weak on realism; (4) migration guides for Snaplet, Neosync, Synth and gretel/ydata users; (5) citations of the arXiv paper and benchmark in the academic channel that made SDV.

### Gaps
- No quantitative attribution data (e.g., what share of Faker installs come through factory_boy) was found.
- No VS Code extension for synthetic data generation with meaningful adoption was found. The search was not performed in depth.

## Realism: how each competitor gets or claims it, how the field measures it, and whether any no-source tool credibly claims it

### Takeaway
Tools get "realism" in three different ways. (1) **Learned** generators (SDV, mostlyai, synthcity, YData, Gretel/Safe Synthesizer, GReaT) copy a real source table and measure realism as *fidelity to that source*, using SDMetrics, synthcity's α-precision/β-recall, Mostly AI's QA accuracy, TSTR, and DCR for privacy. (2) **Rule/value** generators (Faker, Mimesis, Mockaroo, Synth, Snaplet seed, dbldatagen, ShadowTraffic) claim "realistic" or "production-like" values but publish no realism metric, and their realism is per-value, not cross-column. (3) **LLM** generators (NeMo Data Designer, GReaT, LLM-for-tables research) claim semantic coherence and measure it with validators and LLM-as-judge scores. The field's realism metrics nearly all need a real reference dataset, so a no-source tool cannot report them as usually defined. The no-source projects that make *credible* realism claims did so through **domain-grounded simulation plus external validation**: Synthea, checked against published clinical quality measures, with documented gaps; and Synthetic Hospital (CMU, Sept 2026), where blinded physicians told its charts from real ones at 53%, near chance. No general-purpose no-source OSS tool I found publishes a realism benchmark. That gap is open for Misata to fill, and Misata's own arXiv paper is careful to claim *conformance*, not fidelity.

### Cited Findings
**How competitors get or claim realism**
- Learned from real data: SDV 2.0 "learns the database as a connected whole, capturing the statistical patterns, data structure, relationships, context, and business rules", which requires a "representative subset of their data" — [Webull/PRN syndication](https://www.webull.com/news/15582334917952512)
- Learned: Mostly AI SDK trains TabularARGN generators on proprietary data, and its QA splits the source into training and holdout halves for evaluation — [BigDATAwire](https://www.bigdatawire.com/this-just-in/mostly-ai-unveils-open-source-toolkit-for-synthetic-data-generation/), [mostlyai-qa](https://github.com/mostly-ai/mostlyai-qa)
- Learned plus LLM: GReaT's paper title is literally "Language models are realistic tabular data generators" (fine-tunes an LLM on the real table) — [arXiv 2210.06280](https://arxiv.org/pdf/2210.06280)
- LLM from scratch or seeds: NeMo Data Designer combines statistical samplers, LLM-generated columns and dependency-aware fields. It gates quality with "deterministic validators, remote services, and LLM judges" that add pass/fail metadata or scores — [arXiv 2609.17699](https://arxiv.org/html/2609.17699v1), [NVIDIA LLM-column docs](https://docs.nvidia.com/nemo/microservices/latest/design-synthetic-data-from-scratch-or-seeds/define-your-data-columns/column-types/llm-based-columns.html)
- Rule or value based (claims only, no metric). Repo descriptions as published: Mimesis "fake but realistic data"; supabase-community/seed "production-like dummy data based on your schema"; MaterializeInc/datagen "authentic looking mock data"; ShadowTraffic "mimic your production traffic"; Synth "realistic data"; Mockaroo's realism credited to its "200 built-in data types" — [Mimesis GitHub](https://github.com/lk-geimfari/mimesis), [supabase-community/seed](https://github.com/supabase-community/seed), [MaterializeInc/datagen](https://github.com/MaterializeInc/datagen), [ShadowTraffic](https://shadowtraffic.io/), [Synth](https://github.com/shuttle-hq/synth), [GeeksforGeeks on Mockaroo](https://www.geeksforgeeks.org/data-science/mockaroo-realistic-data-generation/)
- The structural weakness of value fakers: "generators like Faker generate column contents independently ... only cover common semantic types, and do not maintain value dependencies between columns (e.g., matching Zipcode and City)" — [arXiv 2410.21717 (LLM tabular generation)](https://arxiv.org/html/2410.21717)
- dbt_synth_data says outright that its output "should not be mistaken as being fully realistic, reflecting all correlations that may be present in the real world, and therefore should not be used to train ML models" — [GitHub edanalytics/dbt_synth_data](https://github.com/edanalytics/dbt_synth_data)
- Even distribution-matching generators break semantics: "Synthetic tabular data can match real data distributions while still violating semantic constraints ... existing tabular generators mainly optimize distributional fidelity" — [arXiv 2609.16069](https://arxiv.org/pdf/2609.16069)

**How realism is measured in the field (all reference-based)**
- SDMetrics (SDV's metrics library) Quality Report = mean of **Column Shapes** (KSComplement for numeric/datetime, TVComplement for categorical) and **Column Pair Trends** (CorrelationSimilarity, ContingencySimilarity). The separate Diagnostic Report covers Data Validity and Data Structure. Scores run 0–1, with a multi-table API — [SDMetrics Quality Report docs](https://docs.sdv.dev/sdmetrics/data-metrics/quality/quality-report), [What's included](https://docs.sdv.dev/sdmetrics/reports/quality-report/whats-included), [Multi Table API](https://docs.sdv.dev/sdmetrics/data-metrics/quality/quality-report/multi-table-api)
- Synthcity: sample-level **α-precision** (fidelity: share of synthetic samples in high-density regions of the real data), **β-recall** (diversity: coverage of the real data) and **authenticity** (share of genuinely novel samples), plus JS distance, Wasserstein and MMD, organized as fidelity, utility and privacy — [Synthcity NeurIPS 2023](https://papers.neurips.cc/paper_files/paper/2023/file/09723c9f291f6056fd1885081859c186-Paper-Datasets_and_Benchmarks.pdf), [Synthcity README](https://github.com/vanderschaarlab/synthcity/blob/main/README.md)
- Mostly AI QA: holdout-based accuracy plus privacy by **DCR** (distance to closest record; the DCR share closer to training than to holdout "should not be significantly larger than 50%") and **NNDR** — [mostlyai-qa](https://github.com/mostly-ai/mostlyai-qa), [Mostly AI QA blog](https://mostly.ai/blog/synthetic-data-quality-assurance)
- Utility: **TSTR** (train on synthetic, test on real) is "the most common protocol used to evaluate the utility of generative models" — [arXiv 2404.14445](https://arxiv.org/html/2404.14445v2), [Emergent Mind summary](https://www.emergentmind.com/topics/train-on-synthetic-test-on-real-tstr)
- Standard taxonomy: Utility / Fidelity / Privacy, with fidelity = column-wise distribution similarity, pairwise correlation and mutual information; privacy = DCR, membership-inference and attribute-inference risk. A systematic review flags "critical challenges" in evaluation standardization — [arXiv 2504.18544 systematic review](https://arxiv.org/pdf/2504.18544), [arXiv 2503.05954 survey](https://arxiv.org/pdf/2503.05954), [PMC health evaluation framework](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12058740/)
- Detection or "discriminator" tests: train a classifier to tell real from synthetic and use XAI to explain why synthetic data is distinguishable — [arXiv 2504.20687](https://arxiv.org/html/2504.20687)
- LLM-as-discriminator (June 2026): LLaMA and Gemini were asked to label rows REAL or SYNTHETIC on Adult and ACS Census, with CTGAN, TVAE and Gaussian Copula synthesizers, 451 valid trials and a 2-annotator, 240-trial human pilot. Results varied sharply by model: LLaMA detected 0% on Adult, while Gemini detected 100% for CTGAN and TVAE. The authors frame it as a privacy-audit signal that needs careful reporting — [arXiv 2606.09865](https://arxiv.org/abs/2606.09865), [arXiv HTML](https://arxiv.org/html/2606.09865v1)
- LLM-as-judge realism scoring is also in use. NeMo's evaluator supports LLM-as-a-judge, and at least one 2026 paper scores sample realism 1–5 with an LLM agent and averages it. Attribution comes from a search summary and was not checked — [NeMo Evaluator LLM-as-a-Judge](https://docs.nvidia.com/nemo/microservices/26.3.1/evaluator/metrics/llm-as-a-judge.html), [Amalgam arXiv 2603.27254](https://arxiv.org/pdf/2603.27254)
- Human Turing tests are rare for tabular data, because tabular quality is "even more challenging" for humans to judge than images or text. They are more common in medical imaging (e.g., four embryologists classifying images) — [arXiv 2504.20687](https://arxiv.org/html/2504.20687), [arXiv 2511.18204](https://arxiv.org/pdf/2511.18204)

**Do any no-source tools credibly claim realism?**
- **Synthea** (MITRE, open source) generates synthetic patients from public health statistics and clinical guidelines with no real patient data. It aims for data that is "structurally and statistically realistic" but not real. A peer-reviewed validation against clinical quality measures found it adequate at the aggregate population level, but it did not model care deviations and outcomes. A later study found its medication data "unrealistic" until enhanced — [JAMIA 2018](https://academic.oup.com/jamia/article/25/3/230/4098271), [BMC Med Inform 2019 validation](https://link.springer.com/article/10.1186/s12911-019-0793-0), [JAMIA Open 2023 medication](https://academic.oup.com/jamiaopen/article/6/3/ooad052/7223896)
- **Synthetic Hospital** (Park, Chen, Dettmers, CMU, submitted 2026-09-24): 1,268 patients and 5,602 encounters built only from public medical-education material, grounded in ICD-10-CM, SNOMED CT and LOINC with a provenance chain. "In a blinded review, physicians distinguished its records from real patient charts at near-chance rates (53%)" — [arXiv 2609.30027](https://arxiv.org/abs/2609.30027), [author post on X](https://x.com/sparkcpark/status/2103474938095239336), [GitHub](https://github.com/sparkcpark/synthetic_hospital)
- **Misata's own paper** frames the cold-start task as "outcome-conformant synthesis". It argues that "its evaluation axis is conformance rather than fidelity" and that "the two axes are orthogonal". So the published Misata claim is exactness of declared aggregates, not realism — [arXiv 2606.08736](https://arxiv.org/abs/2606.08736)
- NeMo Data Designer can run from scratch (no seed data) and relies on LLM priors plus validators and judges for plausibility. I found no published human-indistinguishability or reference-fidelity result for its from-scratch mode — [arXiv 2609.17699](https://arxiv.org/html/2609.17699v1)

### Inferences
- The incumbents' "realism" means "statistically close to *your* data", which a no-source tool cannot claim by definition. If Misata leads with REALISM, it needs a different definition it can defend. The evidence above supports a stack of: (a) **semantic and cross-column coherence** (city matches zip, lifecycles valid, temporal order holds), which Faker and dbt_synth_data openly do not do and which arXiv 2609.16069 says even learned generators miss; (b) **plausibility against public reference statistics**, the Synthea-style approach (e.g., realistic churn and seasonality ranges); (c) **blinded human or LLM discrimination tests**, the Synthetic Hospital and LLM-as-discriminator approach; and (d) **exact conformance** to declared targets, which Misata's paper already shows.
- A practical, credible realism benchmark for Misata: run it against public datasets that have a known schema (e.g., a retail or SaaS dataset). Generate cold-start data from only a story or schema plus a few public aggregates. Then report SDMetrics Column Shapes / Column Pair Trends, a classifier-detection AUC, an LLM-discriminator rate, and a small blinded human test *against the held-out real data*. That shows realism with the field's own tools while honestly labelling Misata as never seeing the data. No general-purpose no-source OSS competitor I found publishes such numbers, so Misata would be first.
- Risk: claiming "realistic" with no metric would put Misata alongside Faker, Mockaroo and Snaplet, whose realism claims are marketing copy. The 53% physician result shows what a credible no-source realism claim looks like in 2026: a blinded test, a number, and domain grounding.
- The LLM-discriminator results swing from 0% to 100% depending on the model. Any LLM-judge realism score Misata publishes should report several models, or reviewers will discount it.

### Gaps
- arXiv, datacebo.com and prnewswire were blocked for direct fetch. Findings from 2606.09865, 2603.27254, 2504.18544 and 2609.30027 come from search-engine summaries of the abstracts and HTML, not full-text reads. In particular, attributing the "LLM agent scores realism 1–5" method to the Amalgam paper is uncertain.
- I did not find whether SDMetrics, synthcity or mostlyai-qa offer any reference-free (no real data) realism metric. Their documented metrics all compare against real data.
- I did not find any published realism or human-evaluation result for Faker, Mimesis, Snaplet seed, Synth, Mockaroo, ShadowTraffic or NeMo Data Designer's from-scratch mode. As far as these searches show, none exists.
