# FOSS United Project Grant — Application Draft

**Apply at:** https://fossunited.org/grants/projects/apply  
**Email for questions:** grants@fossunited.org  
**Target amount:** ₹5,00,000 (~$6,000)

---

## Project Name
Misata

## Project URL / Repository
https://github.com/rasinmuhammed/misata

## Website
https://misata.studio

## Maintainer Name
Muhammed Rasin

## Maintainer Location
India

## Are you the primary maintainer?
Yes. I am the sole maintainer. All commits, releases, and design decisions are mine.

## Brief description of the project (2–3 sentences)

Misata is a Python library that generates realistic, multi-table synthetic data conforming to outcomes you declare — exact revenue curves, fraud rates, and referential integrity — from a plain-English description, a YAML schema, or an existing database. No ML model or real data is needed. The core mechanism is formalised in an arXiv preprint (arXiv:2606.08736) and benchmarked to $0.00 aggregate error, compared to 74–86% error for off-the-shelf imitation synthesisers.

---

## What is the use case?

**Primary use cases:**

1. **Database seeding for development and CI.** Teams need production-like data in dev and staging environments without copying real user data. Misata fills entire relational schemas with FK-consistent rows that match the statistical shape of the real domain.

2. **Integration test fixtures.** Writing `pytest` fixtures by hand for multi-table schemas is tedious and fragile. Misata generates seeded, reproducible, FK-valid fixture sets from a schema dict.

3. **BI and dashboard prototyping.** When a dashboard needs to show a demo, the data must tell the right story (revenue rising Q1 to Q4, fraud peaking in October). Misata generates rows that roll up to the exact declared curve — no hacking CSVs.

4. **Statistical method validation.** Researchers validating mixed-effects models, ICC tests, or time-series methods need synthetic datasets with known structure. Misata produces longitudinal and grouped datasets that pass standard validation tests.

5. **AI agent tooling.** Misata ships a Model Context Protocol (MCP) server. AI coding agents (Claude, Cursor, Windsurf) can call it directly to generate test data as part of agentic workflows.

---

## How many users does the project have?

As of July 2026:
- **PyPI downloads:** ~959 downloads in the last 30 days (without mirrors: ~350 real installs). Download trend has grown roughly 5× from December 2025 to June 2026.
- **GitHub stars:** 59
- **MCP registry:** Listed on smithery.ai as a published MCP server
- **ArXiv preprint:** arXiv:2606.08736, published June 2026
- **CI:** Passing on Python 3.10, 3.11, 3.12 via GitHub Actions

The user base is early but real, growing, and technically serious. Downloads spike sharply on release days and stay elevated between releases — a pattern consistent with repeat users, not bots.

---

## What makes it special compared to alternatives?

| Tool | What it does | Gap |
|------|-------------|-----|
| **Faker** | Generates random field values | No relational structure, no aggregate control |
| **SDV / CTGAN** | Learns from real data, imitates it | Requires real data, misses declared aggregates by 74–86% |
| **Mockaroo** | Web-based random row generator | No FK integrity, no outcome conformance, no Python API |
| **Snaplet** | Copies and anonymises production snapshots | Requires production access, shut down |
| **Misata** | Declares outcome, generates from scratch | **No real data needed, $0.00 aggregate error, full FK integrity, MCP-native** |

The key differentiator is *outcome conformance*: Misata is the only tool that lets you say "monthly revenue rises from ₹50L in January to ₹2Cr in December" and get individual transaction rows whose monthly sums hit those targets exactly. This is proven in a published paper and benchmarked against alternatives.

---

## Is this a niche project? How big is that niche?

Yes, it is niche by design: developer tooling for synthetic relational data generation. The niche is meaningful:

- Every team with a relational database needs test/demo data. That is nearly every software team.
- The synthetic data market is estimated at $710M in 2026 (Mordor Intelligence), though the enterprise slice (privacy-preserving ML training data) is larger than the dev-tools slice Misata targets.
- Comparable commercial tools charge $50–$500/year for inferior capabilities (Mockaroo: $50/year, no relational integrity; Tonic.ai: enterprise pricing, privacy-focused).
- The closest open-source competitor, SDV (Python library), spawned a company (DataCebo) that raised $12M — proof the niche supports real investment.

Misata is differentiated within this niche by its arXiv-backed exact-aggregate claim and its MCP server integration, which positions it squarely in the AI-agent coding workflow where demand is currently growing fastest.

---

## What will the grant be used for?

Requested amount: **₹5,00,000** (~$6,000), to be used over 12 months.

Breakdown:
- **50% — Developer time (~₹2.5L):** Sustaining active maintenance, addressing issues, reviewing PRs, and shipping planned features. Without this, the project competes with paid work for attention.
- **30% — Misata Studio (~₹1.5L):** Completing and hosting the web-based GUI (already partially built as `misata/studio`). This is the SaaS layer that enables future monetisation and makes the library accessible to non-Python users.
- **20% — Community and documentation (~₹1L):** Writing tutorials for dbt, Databricks, and pytest users; presenting at FOSS events; growing the contributor base.

---

## Milestones

These are the public milestones I commit to over the grant period:

| Quarter | Milestone |
|---------|-----------|
| Q1 | Ship misata-studio v1 as a hosted free-tier web app at misata.studio. Add GitHub Sponsors page. |
| Q1 | Publish SpecBench results as a standalone community leaderboard page. |
| Q2 | SQLAlchemy schema introspection — generate from an existing live database connection. |
| Q2 | One community talk (IndiaFOSS, PyCon India, or equivalent). |
| Q3 | Paid tier for misata-studio (team seats, scheduled generation, PDF Oracle reports). |
| Q3 | dbt seed file export — generate dbt-compatible seed CSVs directly from a `schema.yml`. |
| Q4 | Guest post or quarterly forum update on FOSS United. Open a public roadmap on GitHub. |

---

## Can this project become sustainable 5 years from now?

Yes, and there is a clear path. The open-source library drives adoption; the hosted Studio becomes the paid product. This is the same model DataCebo used to turn SDV (free library, millions of downloads) into a company that raised $12M for an enterprise layer.

Misata's commercial angle is more focused: it is not competing for enterprise privacy-data budgets. It targets individual developers and small teams who need demo and test data quickly, at a price point of $15–100/month — a tier where a solo developer can operate profitably without VC.

The MCP server integration also creates a potential partnership channel: platforms like Smithery, Claude, and Cursor that surface MCP tools to developers already embed Misata as a listed tool. As agentic coding grows, Misata is positioned as the "generate test data" tool within those workflows.

---

## Are there existing FOSS alternatives? How does Misata compare?

Yes. The closest alternatives are:

- **Faker** (MIT, Python): No relational structure, no aggregate control. Misata is not a competitor — it is a layer above Faker, and actually uses it for semantic field generation internally.
- **SDV / CTGAN** (MIT, Python): Requires real training data, generates imitation data. Misata does not require real data and targets exact aggregate conformance rather than statistical similarity.
- **Factory Boy / Model Bakery** (Python, Django/ORM-specific): Test fixture factories, not data generators. Single-table, code-first, no aggregate control.

Misata occupies a gap none of these fill: cold-start (no real data), multi-table, outcome-conformant.

---

## What does this project need that the grant would provide?

Time. The library is technically ready and has real users. What is missing is sustained developer hours to ship misata-studio, answer issues faster, write tutorials, and grow the user base to the level where it supports itself. Without the grant, those things happen slowly around a day job.

---

## Additional notes

The arXiv preprint (arXiv:2606.08736) is publicly verifiable and contains the benchmark numbers cited in this application. The `research/specbench/` directory in the repo contains the raw CSV result files. The CI badge in the README reflects real test runs across three Python versions.

I am happy to do a quarterly update post on the FOSS United forum and speak at IndiaFOSS or any community event where misata would be relevant.

---

*Application prepared July 2026. Questions: rasinbinabdulla@gmail.com*
