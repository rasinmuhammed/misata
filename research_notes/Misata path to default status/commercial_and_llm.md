# Commercial and LLM-Based Synthetic Data Market (as it bears on Misata), as of Oct 2026

Research note: several primary vendor sites (tonic.ai, syntho.ai, seedfa.st, synthforge.io, news.ycombinator.com, blog.pebblous.ai) were blocked by the research egress proxy, and GitHub API access to third-party repos wasn't available. Many findings below therefore come from search-result snippets of those pages, not full-page reads. Claims from competitor "alternatives/compare" pages (Seedfast, SynthForge, Tonic, K2view) are marketing and are flagged as such.

## 1. Vendors: what paying customers buy, pricing, target buyer, flagship features, and what happened to them

### Takeaway
The commercial market has split in two. (a) Enterprise test data management (TDM) and privacy vendors (Tonic Structural, Perforce Delphix, K2view, GenRocket, Syntho, SAS/Hazy) sell to regulated enterprises. Their pitch is masking, subsetting, referential integrity across production databases, connectors and governance. (b) A newer, cheap self-serve tier of "LLM/agent generates a database from a prompt" tools (Tonic Fabricate, Seedfast, SynthForge, Mockaroo at the low end) sells to individual developers. The independent "ML-model trained on your data" synthesizers have largely failed or been absorbed: Gretel went to NVIDIA (Mar 2025), Hazy to SAS (Nov 2024), and MOSTLY AI ceased operations (Mar 2026), after which Syntho bought its brand (Jun 2026). For a greenfield, no-ML library like Misata, the live competitors are Fabricate, the agent-native seeders and plain LLM+Faker. The enterprise TDM incumbents aren't.

### Cited Findings
**Gretel → NVIDIA (March 2025)**
- NVIDIA acquired Gretel (San Diego) in March 2025 for a reported nine-figure price, above Gretel's last valuation of $320M. About 80 employees were folded into NVIDIA, and the tech is deployed in NVIDIA's generative AI developer services — [TechCrunch, 2025-03-19](https://techcrunch.com/2025/03/19/nvidia-reportedly-acquires-synthetic-data-startup-gretel/)
- Gretel's capabilities re-emerged as two NeMo microservices under NVIDIA AI Enterprise: Data Designer (synthetic dataset generation) and Safe Synthesizer (privacy-preserving synthesis) — [NVIDIA NeMo Data Designer docs](https://docs.nvidia.com/nemo/datadesigner/getting-started/welcome); [NVIDIA NeMo platform docs](https://docs.nvidia.com/nemo-platform/documentation/design-synthetic-data)
- Safe Synthesizer has a public GitHub repo, NVIDIA-NeMo/Safe-Synthesizer ("Create private, safe versions of sensitive tabular datasets") — [GitHub](https://github.com/NVIDIA-NeMo/Safe-Synthesizer)
- Competitor claim (Seedfast, not independently verified): as of July 2026, gretel.ai redirects to nvidia.com, the gretelai GitHub org is archived, the old pricing page returns 404, the self-serve free tier is discontinued, pricing is sales-gated, and "nobody sent the free-tier and self-serve accounts a migration plan" — [Seedfast "Gretel Alternative"](https://seedfa.st/compare/gretel-alternative)
- Gretel Navigator (Gretel's LLM-based tabular generator) still has archived docs/FAQ at docs.gretel.ai. I found no source confirming it as a standalone NVIDIA product. Data Designer appears to be its successor — [Gretel Navigator FAQ](https://docs.gretel.ai/create-synthetic-data/navigator/faq)

**MOSTLY AI → ceased operations (March 2026); brand bought by Syntho (June 9, 2026)**
- MOSTLY AI open-sourced its synthetic data SDK (Apache 2.0, TabularARGN model, built-in differential privacy), announced as the "first industry-grade open-source synthetic data toolkit" in Feb 2025 — [BigDATAwire](https://www.bigdatawire.com/this-just-in/mostly-ai-unveils-open-source-toolkit-for-synthetic-data-generation/); [Tech.eu, 2025-02-03](https://tech.eu/2025/02/03/the-future-of-ai-innovation-starts-with-synthetic-data-and-an-open-source-sdk/)
- Pre-shutdown commercial pricing: a Marketplace tier at $3,000/month (one platform installation, unlimited usage, API and Python SDK, SLAs). Enterprise and Cloud tiers were contact-sales — [Toolradar](https://toolradar.com/tools/mostly-ai)
- MOSTLY AI ceased operations in March 2026 after raising about $31.14M. Syntho acquired the brand on June 9, 2026, and the brand continues as "MOSTLY AI, powered by Syntho". The announcement reportedly says nothing about existing customers, support continuity or the SDK — [beri.net](https://www.beri.net/article/best-synthetic-data-platforms-real-data-cannot-leave-2026); [Syntho press release](https://www.syntho.ai/syntho-acquires-mostly-ai-trademark-and-related-assets/) (the Syntho page itself was not readable, so details come from search snippets)
- mostly.ai blog pages are now branded "MOSTLY AI powered by Syntho" — [mostly.ai blog](https://mostly.ai/blog/using-datallm-to-generate-synthetic-data-from-scratch)

**Hazy → SAS (closed November 12, 2024)**
- SAS acquired "the primary software capabilities" of London-based Hazy (an IP/asset deal, terms undisclosed) and folded them into SAS Data Maker, first announced early 2024. A preview was planned for early 2025 — [TechTarget](https://www.techtarget.com/searchbusinessanalytics/news/366615499/SAS-acquires-synthetic-data-generator-to-aid-AI-development); [ITWeb "SAS acquires synthetic data IP from Hazy"](https://www.itweb.co.za/article/sas-acquires-synthetic-data-ip-from-hazy/LPp6VMrBGdKMDKQz)

**Tonic.ai (Structural, Textual, Fabricate)**
- Tonic Fabricate tiers: Free ($0/month, $5 of monthly credits, no card), Plus ($29/month, $25 credits) and Enterprise. A standard agent "turn" costs about $0.17; a complex multi-table schema refinement costs about $0.37 — [Tonic pricing](https://www.tonic.ai/pricing) (from search snippet; page blocked)
- Fabricate's Data Agent is a conversational agent that generates relational databases, PDFs, docx and other unstructured formats from a prompt, a schema or a live database connection — [Tonic Fabricate](https://www.tonic.ai/products/fabricate); [Tonic webinar](https://www.tonic.ai/webinars/introducing-fabricate-data-agent-the-ai-agent-for-synthetic-data-generation)
- Architecture: a "hybrid generation engine that delegates creative text to the LLM but executes code in a secure Javascript sandbox for mathematically rigid fields" — [Tonic Fabricate vs Claude](https://www.tonic.ai/blog/tonic-fabricate-vs-claude) (snippet)
- Tonic's own head-to-head claim: Fabricate was 2x faster end to end and used 2.5x less token spend than Claude Code for synthetic data generation (vendor benchmark; methodology not readable) — [Tonic blog](https://www.tonic.ai/blog/tonic-fabricate-vs-claude)
- Tonic publishes "build vs buy" content aimed squarely at teams that would roll their own LLM pipeline — [Tonic guide](https://www.tonic.ai/guides/build-vs-buy-synthetic-data-with-llms)
- Structural (database de-identification, subsetting) and Textual (unstructured PII redaction) sit on the same pricing page. I couldn't read their tier details — [Tonic pricing](https://www.tonic.ai/pricing); a third-party summary exists at [Codeables](https://codeables.dev/article/tonic-pricing-what-s-included-in-structural-vs-textual-vs-fabricate)

**Enterprise TDM incumbents (Perforce Delphix, K2view, GenRocket)**
- Perforce Delphix positions itself as a data automation platform that unifies data delivery, masking, synthetic data generation and centralized control across hybrid and multicloud. It was a Gartner Peer Insights Customers' Choice in the 2025 Voice of the Customer for TDM — [Perforce TDM](https://www.perforce.com/solutions/test-data-management); [K2view blog summary](https://www.k2view.com/blog/top-test-data-management-tools-for-2026/)
- K2view sells an "entity-based data product" platform that unifies production data across systems into business entities and provisions compliant test data on demand — [K2view](https://www.k2view.com/blog/delphix-vs-k2view)
- GenRocket is commonly listed as "best for advanced synthetic test data" in TDM roundups — [K2view top TDM tools 2026](https://www.k2view.com/blog/top-test-data-management-tools-for-2026/)
- Gartner maintains a Test Data Management peer-reviews market — [Gartner Peer Insights TDM](https://www.gartner.com/reviews/market/test-data-management)

**YData**
- YData Fabric: freemium, with a free Community tier, pay-as-you-go and Enterprise (prices undisclosed), plus SaaS, AWS/Azure marketplace and Kubernetes self-hosted options. The SDK `ydata-fabric-sdk` 1.1.5 (MIT) shipped Feb 7, 2025, and `ydata-synthetic` was superseded by `ydata-sdk` with automatic model selection — [PyPI](https://pypi.org/project/ydata-fabric-sdk/); [GitHub ydata-synthetic](https://github.com/ydataai/ydata-synthetic); [SoftwareSuggest](https://www.softwaresuggest.com/ydata)

**Synthesized.io**
- UK-based, founded 2018, with a platform that "automates test data generation, provisioning, and execution", i.e. it has repositioned toward TDM — [CB Insights](https://www.cbinsights.com/compare/synthesized-vs-ydata)

**Mockaroo (paid)**
- Free: 1,000 rows per file, 200 API requests/day. Silver $60/year: 100K rows per file, 1M records/day API. Gold $500/year: 10M rows per file, 10M records/day. Enterprise $7,500/year: unlimited — [Mockaroo pricing](https://www.mockaroo.com/pricing)

**New agent-native entrants (2025–2026)**
- Seedfast (founded Sept 2025, Bratislava) reads a live Postgres schema, resolves table dependencies and satisfies foreign keys. It exposes a `seedfast_run` MCP tool so one agent call fills every table. It won DDAccelerator Finals in Jan 2026 — [Seedfast](https://seedfa.st/); [Seedfast About](https://seedfa.st/about); [Seedfast Claude Code MCP blog](https://seedfa.st/blog/claude-code-mcp-database-seeding)
- SynthForge positions itself as "greenfield test data" versus Tonic's de-identification and publishes Gretel/Tonic alternative pages (May 2026) — [SynthForge vs Tonic](https://synthforge.io/alternatives/tonic-ai/); [SynthForge vs Gretel](https://synthforge.io/alternatives/gretel/)
- DATAMIMIC: model-driven, deterministic synthetic test data for CI/CD, with Python APIs, XML pipelines and MCP/IDE integration — [GitHub datamimic](https://github.com/DYNOSuprovo/datamimic); [DATAMIMIC vs Tonic](https://datamimic.io/blog/datamimic-vs-tonic-ai/)

### Inferences
- What enterprise buyers pay for is mostly not generation. It is getting realistic data out of production safely: masking, subsetting with referential integrity, DB connectors, provisioning and virtualization, plus compliance and governance reporting. Generation from nothing is a feature inside TDM suites, not the core sale. Misata doesn't compete there unless it adds "learn from/mirror a real schema" features.
- The standalone "train a generative model on your sensitive data" business has proven hard to sustain independently: Gretel was acquired, Hazy sold as an IP deal, and MOSTLY AI shut down despite open-sourcing its SDK. Open-sourcing alone didn't save MOSTLY AI. That is a cautionary data point for monetization, not for adoption.
- Gretel and MOSTLY AI going away stranded self-serve and free-tier developers (if Seedfast's characterization is accurate). That leaves an opening for a free, local, OSS tool for developer-scale synthetic data.
- Price anchors for the developer segment are low: Mockaroo at $60–$500/year and Fabricate at $0–$29/month. A free OSS library competes mainly on convenience and correctness, not on price.

### Gaps
- Couldn't confirm list prices for Tonic Structural/Textual, K2view, GenRocket, Delphix, Syntho, Synthesized or Datprof (all contact-sales or unreadable).
- No information found on Statice (acquired by Anonos; the date was not verified in this session) or Datprof. Treat any Statice→Anonos details as unverified.
- Couldn't read Tonic's Fabricate-vs-Claude methodology. The 2x/2.5x figures are an unaudited vendor claim.
- Didn't verify the exact launch dates of Tonic Fabricate's Data Agent and MCP server (search results only say 2025–2026).
- MOSTLY AI's shutdown date (March 2026) comes from one secondary source (beri.net) plus a Syntho press release I couldn't open.

## 2. LLM approaches to synthetic data and their known failure modes on tabular/relational data

### Takeaway
LLM-based tools fall into three groups. NVIDIA NeMo Data Designer (open-sourced; Gretel's successor) and Tonic Fabricate are hybrids: a declarative schema plus deterministic samplers, with an LLM used only for free-text columns. The second group, distilabel, the HF/Argilla Synthetic Data Generator and DataDreamer, is aimed at LLM training/eval text data, not relational DBs. The third is ad-hoc "ask the chatbot", which runs into well-documented FK, uniqueness, statistical-consistency, cost and determinism problems. Notably, the serious LLM vendors have converged on Misata-like rigid deterministic machinery for structure and use the LLM for semantics.

### Cited Findings
- NVIDIA open-sourced NeMo Data Designer, "the synthetic data framework used to build Nemotron datasets" (pre- and post-training data). It is a declarative data generation framework that integrates with NeMo Curator — [HN thread, item 46136055](https://news.ycombinator.com/item?id=46136055) (title only; date not verified, likely late 2025); [NeMo Curator docs](https://docs.nvidia.com/nemo/curator/curate-text/synthetic/nemo-data-designer); [GitHub NVIDIA-NeMo/DataDesigner AGENTS.md](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/AGENTS.md)
- Data Designer is described as "schema-driven generation, with optional LLM-generated columns"; Safe Synthesizer handles DP synthesis from a real seed dataset — [Seedfast Gretel alternative](https://seedfa.st/compare/gretel-alternative)
- Tonic Fabricate's hybrid engine uses the LLM for creative text and a JS sandbox for "mathematically rigid fields" — [Tonic](https://www.tonic.ai/blog/tonic-fabricate-vs-claude)
- distilabel is a framework for "synthetic data and AI feedback" pipelines (instruction following, dialogue, judging, classification). Argilla's Synthetic Data Generator builds LM fine-tuning datasets from natural language using distilabel — [Argilla distilabel](https://argilla.io/blog/introducing-distilabel-1/); [GitHub argilla-io/synthetic-data-generator](https://github.com/argilla-io/synthetic-data-generator)
- DataDreamer is a tool for synthetic data generation and reproducible LLM workflows, integrated with Hugging Face datasets — [arXiv 2402.10379](https://arxiv.org/html/2402.10379v2)
- Failure modes:
  - LLM output "lacks statistical consistency across large datasets, doesn't inherently preserve referential integrity across relational tables, and can hallucinate unrealistic values" — [Tonic best synthetic data tools 2026](https://www.tonic.ai/synthetic-data/best-synthetic-data-tools) (vendor source)
  - When ChatGPT-style LLMs mock data for a unique-constrained FK, they reach for a Faker module, which produces duplicates and unique-constraint violations even at about 1,000 rows (zip-code example) — [Neurelo on DEV](https://dev.to/neurelo/in-the-land-of-llms-can-we-do-better-mock-data-generation-489)
  - Faker is column-by-column, with "no concept of relationships between columns, tables, or records", so it is unsuitable for full-database generation — [search summary of Tonic/tsfaker sources](https://pypi.org/project/tsfaker/)
- Academic work (LLM-TabFlow, Mar 2025) exists specifically because LLM tabular generation fails to keep inter-column logical relationships — [arXiv 2503.02161](https://arxiv.org/html/2503.02161v1/)
- MOSTLY AI also had an LLM-from-scratch product, DataLLM — [mostly.ai blog](https://mostly.ai/blog/using-datallm-to-generate-synthetic-data-from-scratch)

### Inferences
- Misata's design (declarative, closed-form, no ML) is the same architectural bet NVIDIA (Data Designer samplers) and Tonic (JS sandbox) made for the structural layer. The difference is that Misata is local, free and doesn't require an LLM call per generation. That is a credible positioning: "the deterministic engine agents should call" rather than "an alternative to LLMs".
- Raw LLM generation is weakest exactly where Misata is strongest: FK integrity across many tables, uniqueness, reproducibility/seeding, scale (millions of rows without token costs) and distributional consistency. LLMs are strongest at semantic plausibility (realistic free text, domain-appropriate names and categories), which a rule-based engine handles less well.
- The "ask the LLM to write Faker code" path inherits Faker's column-by-column limitation. The LLM must hand-write relationship logic each time, which is non-reproducible across sessions.

### Gaps
- No primary benchmark found that quantifies LLM-written Faker scripts' error rates (FK violations, constraint failures) at scale. Evidence is anecdotal or comes from vendors.
- Didn't verify Data Designer's license (likely Apache 2.0) or its exact open-source date.
- ChatGPT Advanced Data Analysis "vibe-generated" data: no sources found describing its usage or limits specifically.

## 3. Is MCP/agent tooling a real adoption channel for data generation?

### Takeaway
Yes, and it's already crowded. Tonic Fabricate, Seedfast and DATAMIMIC all ship MCP servers marketed for Claude, Cursor and VS Code, plus many hobby servers. Tonic also publishes "agent skills" on GitHub. MCP is table stakes for agent distribution, not a differentiator. Calling it a "real adoption channel" rests on vendor investment, not on published usage numbers.

### Cited Findings
- Tonic Fabricate's MCP server "brings the full generation capability into clients like Claude, Cursor, and VS Code", returning "referentially intact datasets" without leaving the editor — [Tonic Fabricate](https://www.tonic.ai/products/fabricate); [Tonic best tools 2026](https://www.tonic.ai/synthetic-data/best-synthetic-data-tools)
- Tonic publishes TonicAI/agents: "Agent skills for profiling databases locally and generating synthetic data with Fabricate" — [GitHub TonicAI/agents](https://github.com/TonicAI/agents)
- Seedfast markets one-prompt database seeding from Claude Code and Codex CLI via MCP (`seedfast_run`) — [Seedfast Claude Code](https://seedfa.st/blog/claude-code-mcp-database-seeding); [Seedfast Codex CLI](https://seedfa.st/blog/codex-cli-database-seeding)
- Other MCP servers include:
  - marc-shade/synthetic-data-mcp ("enterprise-grade", HIPAA/PCI/SOX/GDPR, multi-LLM) — [GitHub](https://github.com/marc-shade/synthetic-data-mcp)
  - Generate Data MCP (7 tools, NL schema design) — [mcpservers.org](https://mcpservers.org/servers/ns-3e/generate-data-mcp)
  - Mock Data Generator MCP — [PulseMCP](https://www.pulsemcp.com/servers/mockdata)
  - Random User synthetic data — [Glama](https://glama.ai/mcp/connectors/ai.saifs/synthetic-data-random-user)
  - A Faker-based test data MCP — [GitHub](https://github.com/praveen1993kp/custom-mcp---test-data-generator)
  - An Apify synthetic data actor exposed via MCP — [Apify](https://apify.com/web.harvester/synthetic-data-generator/api/mcp)
  - DATAMIMIC MCP/IDE integration — [GitHub](https://github.com/DYNOSuprovo/datamimic)
- As of March 2026, ten major agents support custom remote MCP servers with OAuth 2.1, including Claude/Claude Code, ChatGPT, VS Code Copilot, Cursor, Zed, Kiro, Amazon Q Developer CLI, OpenCode and Docker MCP Toolkit — [Truthifi "state of MCP 2026"](https://truthifi.com/education/state-of-mcp-2026-ai-agents-custom-connectors) (secondary)

### Inferences
- Paid vendors (Tonic) and VC-stage startups (Seedfast) betting on MCP and agent skills signals they see agents as the developer acquisition funnel. Misata already having an MCP server puts it at parity, not ahead.
- Tonic shipping "agent skills" alongside MCP suggests the channel is moving beyond MCP tools toward packaged skills, plugins and instructions that teach the agent when to call the tool. Misata may need the same (e.g., a Claude Code skill or Cursor rules) so agents choose Misata instead of writing Faker code.
- The agent is the one picking the tool. Being in MCP registries (PulseMCP, Glama, mcpservers.org, the official MCP registry) and having agent-readable docs (llms.txt, AGENTS.md; NVIDIA's DataDesigner ships an AGENTS.md) are probably real discovery levers.

### Gaps
- No public usage metrics (installs, calls) for any synthetic-data MCP server were found.
- Couldn't verify whether Seedfast or Tonic disclose MCP-driven adoption numbers.

## 4. Market size, fastest-growing use cases, and Gartner statements

### Takeaway
Analyst forecasts put synthetic data generation at roughly $1.3–2.5B by 2030 for mainstream estimates (one outlier says $9.7B), with a 32–37% CAGR. Tabular data is the largest segment (~39% share in 2023). Gartner frames synthetic data as maturing (moving up the Slope of Enlightenment in 2025–26) and has predicted heavy GenAI use for synthetic customer data. Vendor fates show the money concentrating in TDM/privacy suites and AI-training pipelines (NVIDIA) rather than standalone synthesizers.

### Cited Findings
- Grand View Research: $1,788.1M by 2030, 35.3% CAGR 2024–2030. Tabular data was the largest segment, with a 38.8% revenue share in 2023 — [Grand View Research press release](https://www.grandviewresearch.com/press-release/global-synthetic-data-generation-market); [report](https://www.grandviewresearch.com/industry-analysis/synthetic-data-generation-market-report)
- IndustryARC: $2.5B by 2030, 32% CAGR — [IndustryARC](https://www.industryarc.com/Research/Synthetic-Data-Market-Research-800249)
- Strategic Market Research: $1.3B (2024) to $9.7B (2030), 37.4% CAGR — [Strategic Market Research](https://www.strategicmarketresearch.com/market-report/synthetic-data-generation-market)
- "Synthetic test data for AI" sub-market: 35.2% CAGR through 2030 — [OpenPR](https://www.openpr.com/news/4646016/synthetic-test-data-for-artificial-intelligence-ai-market) (press-release aggregator, low reliability)
- Gartner Hype Cycle for AI 2025 charted synthetic data alongside agents, ModelOps and AI engineering — [AIwire/HPCwire, 2025-09-05](https://www.hpcwire.com/aiwire/2025/09/05/ai-hype-cycle-gartner-charts-the-rise-of-agents-modelops-synthetic-data-and-ai-engineering/). A Gartner Hype Cycle for AI 2026 exists — [Gartner](https://www.gartner.com/en/documents/8319853). A secondary source says synthetic data is "rapidly moving up the Slope of Enlightenment" — [testRigor](https://testrigor.com/blog/gartner-hype-cycle-for-ai-2025/) (secondary interpretation)
- Gartner: "By 2026, 75% of businesses will use generative AI to create synthetic customer data, up from less than 5% in 2023" — [Gartner, "What Generative AI Means for Business"](https://www.gartner.com/en/insights/generative-ai-for-business) (via search snippet)
- Gartner advice, as reported by K2view: enterprises should prioritize TDM products that include synthetic data creation (synthetic records, events, tabular synthetic data) to speed up TDM processes — [K2view](https://www.k2view.com/blog/top-test-data-management-tools-for-2026/) (vendor paraphrase of Gartner)

### Inferences
- The "75% of businesses using GenAI for synthetic customer data by 2026" prediction, if even partly realized, means most synthetic data is now produced via LLMs. That is the "just ask the LLM" behavior. It enlarges the pool of people who want synthetic data, but each instance may be throwaway rather than a tool adoption.
- Growth vectors that matter for Misata: (1) dev and test seeding and CI fixtures (Seedfast, Fabricate and DATAMIMIC all target this); (2) demo/sandbox data; (3) LLM eval and agent test data (NVIDIA Data Designer's focus, though mostly text). Privacy-preserving ML training data from real datasets is where the vendor shakeout happened.
- Market-size reports differ by 5x and are low quality. Treat them as directional only.

### Gaps
- No credible split of growth by use case (TDM vs ML training vs LLM eval vs demos) found. Analyst segmentations are by data type and industry.
- I couldn't access the primary Gartner documents (the TDM Market Guide, the Hype Cycle 2026 position of synthetic data). Statements are via secondary sources.
- No Forrester data found.

## 5. What an OSS library needs to win against "just ask the LLM to write Faker code"

### Takeaway
The winning position is to be the deterministic, relationally-correct engine that the agent calls instead of writing Faker code. That means beating the LLM on what it gets wrong (FK/unique integrity, cross-table consistency, reproducibility, scale, zero token cost) and staying as easy as a prompt. Commercial and LLM-native competitors (Fabricate, Seedfast, NVIDIA Data Designer) have already validated this hybrid "LLM for intent and semantics, code engine for structure" architecture. Misata's differentiation has to be local/free/OSS, deterministic, plus agent-ergonomics and seeding into real databases.

### Cited Findings
- The specific gaps of LLM+Faker that vendors market against: no referential integrity across tables, no statistical consistency at scale, hallucinated values, unique-constraint violations — [Tonic](https://www.tonic.ai/synthetic-data/best-synthetic-data-tools); [Neurelo/DEV](https://dev.to/neurelo/in-the-land-of-llms-can-we-do-better-mock-data-generation-489)
- Features competitors foreground for developers:
  - live DB schema introspection with FK-aware fill (Seedfast for Postgres) — [Seedfast](https://seedfa.st/)
  - generation from prompt, schema or live DB connection, including unstructured docs (Fabricate) — [Tonic Fabricate](https://www.tonic.ai/products/fabricate)
  - determinism for CI/CD (DATAMIMIC) — [GitHub datamimic](https://github.com/DYNOSuprovo/datamimic)
  - MCP server plus agent skills (Tonic) — [GitHub TonicAI/agents](https://github.com/TonicAI/agents)
- Price anchors developers compare against: Fabricate Free ($5 credits) / Plus ($29/mo, about $0.17–$0.37 per agent turn) and Mockaroo Silver ($60/yr) — [Tonic pricing](https://www.tonic.ai/pricing); [Mockaroo pricing](https://www.mockaroo.com/pricing)
- Tonic's own benchmark frames the competitor as "Claude Code" itself. The pitch is faster and cheaper than letting the general agent do it — [Tonic Fabricate vs Claude](https://www.tonic.ai/blog/tonic-fabricate-vs-claude)
- Vendor-continuity risk is real for developers: Gretel's self-serve tier disappeared after the NVIDIA deal, and MOSTLY AI shut down in March 2026 — [Seedfast](https://seedfa.st/compare/gretel-alternative); [beri.net](https://www.beri.net/article/best-synthetic-data-platforms-real-data-cannot-leave-2026)

### Inferences
Requirements for an OSS library to win:
1. **Agent-first ergonomics.** It must be quicker for the agent to call Misata (MCP tool, skill, or a one-line `pip install` and API) than to write Faker code. That needs crisp tool descriptions, agent docs (AGENTS.md, llms.txt, a Claude Code skill/plugin, Cursor rules) and registry listings.
2. **Guaranteed correctness the LLM can't match.** FK, uniqueness and check constraints valid by construction, cross-table consistency (e.g., order dates after signup dates, totals equal line-item sums), and a validation report the agent can show the user.
3. **Determinism.** Seeded, reproducible output, and schemas/stories saved as versionable config files for CI fixtures. LLM output varies run to run.
4. **Scale and zero marginal cost.** Millions of rows locally in seconds with no tokens, against Fabricate's per-turn pricing and the LLM's context limits.
5. **Real-DB integration.** Introspect existing schemas (Postgres, MySQL, SQLite, ORM models like Prisma, Django, SQLAlchemy), write directly into DBs, and output in the formats teams use (SQL, CSV, Parquet). Seedfast and Fabricate both lead with live DB connection.
6. **Optional LLM hook for semantics.** Following Data Designer and Fabricate, let an LLM fill free-text columns or translate the "story" while the engine owns structure. This turns LLMs into a complement rather than a competitor.
7. **Trust and longevity.** Permissive license, no vendor lock-in. The Gretel and MOSTLY AI events are a selling point for OSS ("your data tooling won't be shut down").

Is the LLM trend a threat or a help? Mostly a help for distribution, because agents need deterministic tools and MCP gives Misata a path into the agent's toolbelt. It is a threat at the low end: for a 50-row single-table fixture, "just ask the LLM" is good enough and Misata adds friction. Misata wins as the task grows to multi-table, many rows, needs reproducibility, or feeds CI. Its pitch should target that threshold explicitly.

### Gaps
- No user research or surveys found on how often developers use LLMs vs tools for fake data, or at what dataset size or complexity they switch to a tool.
- No public comparison of NVIDIA Data Designer vs rule-based tools on relational multi-table generation. Data Designer's multi-table and FK support wasn't verified.
- Didn't evaluate how Misata compares feature by feature with SDV (an ML-based OSS incumbent) or Faker-based seeders (e.g., drizzle-seed, Snaplet), which are likely out of scope for this note.
