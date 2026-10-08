<div align="center">

<img src="https://raw.githubusercontent.com/rasinmuhammed/misata/main/public/logo.png" width="180" alt="Misata" />

# Misata

**The relational synthetic data engine that satisfies exact business outcomes.**

Generate complete multi-table databases with foreign keys that resolve, math that reconciles, and domain-authentic prose with zero Lorem Ipsum. From a single sentence, YAML schema, or live database.

[![PyPI version](https://img.shields.io/pypi/v/misata.svg?style=flat-square&color=E89030)](https://pypi.org/project/misata/)
[![Python versions](https://img.shields.io/pypi/pyversions/misata.svg?style=flat-square)](https://pypi.org/project/misata/)
[![CI](https://img.shields.io/github/actions/workflow/status/rasinmuhammed/misata/ci.yml?branch=main&style=flat-square&label=tests)](https://github.com/rasinmuhammed/misata/actions)
[![License](https://img.shields.io/github/license/rasinmuhammed/misata.svg?style=flat-square)](https://github.com/rasinmuhammed/misata/blob/main/LICENSE)
[![Open in Colab](https://img.shields.io/badge/Open%20in-Colab-F9AB00?style=flat-square&logo=googlecolab&logoColor=white)](https://colab.research.google.com/github/rasinmuhammed/misata/blob/main/notebooks/quickstart.ipynb)
[![Paper](https://img.shields.io/badge/arXiv-2606.08736-b31b1b?style=flat-square&logo=arxiv&logoColor=white)](https://arxiv.org/abs/2606.08736v1)
[![smithery badge](https://smithery.ai/badge/misata/misata)](https://smithery.ai/servers/misata/misata)
[![Misata Studio](https://img.shields.io/badge/Studio-no--code%20in%20your%20browser-E89030?style=flat-square)](https://misata.studio)

**[Documentation](https://misata.studio/docs)** · **[Misata Studio](https://misata.studio)** · **[Changelog](https://github.com/rasinmuhammed/misata/blob/main/CHANGELOG.md)**

**Prefer a visual interface?** Try [**Misata Studio**](https://misata.studio) to design schemas on an interactive canvas and generate datasets directly in your browser.

</div>

<!-- mcp-name: io.github.rasinmuhammed/misata -->

---

### The Paradigm Shift

Most synthetic data tools take existing data and imitate it. But in modern engineering, you rarely have clean data to start with—or you need data designed around a **specific target outcome**:
- *"Monthly revenue rises from $50k to $200k with a Q3 slump."*
- *"Fraud rate starts at 1% in Q1 and climbs to 6% by Q4."*
- *"Every customer's `total_spent` strictly equals the sum of their order line items."*

Misata works in reverse: **you declare the outcome, and Misata solves for the individual rows that hit it to $0.00 error**, guaranteed by a closed-form Gamma conditional-sum mechanism ([arXiv:2606.08736](https://arxiv.org/abs/2606.08736v1)). No machine learning models, no real data required, and zero hallucinated foreign keys.

---

## ⚡ 30-Second Quickstart

Install via pip:

```bash
pip install misata
```

### CLI
Generate a complete relational dataset from a single description:

```bash
misata generate \
  --story "Brazilian fintech with R$ payments, CPF verification, and 3% fraud" \
  --rows 1000 \
  --output-dir ./demo_data
```
*Outputs clean CSVs and an `oracle_report.json` verifying zero foreign key orphans, constraint satisfaction, and statistical fidelity.*

### Python
```python
import misata

# Generate multi-table DataFrames from plain English
data = misata.generate("SaaS startup with 500 users, monthly subscriptions, and 12% churn")

users_df = data["users"]
subscriptions_df = data["subscriptions"]
```

### Enrich Existing Data in 1 Line
Replace boring or blank columns in an existing DataFrame with domain-authentic prose:

```python
import misata
import pandas as pd

df = pd.read_csv("support_cases.csv")
# Automatically detects semantic columns (subjects, resolution notes, memos, error traces)
df_enriched = misata.enrich_text(df, seed=42)
```

---

## Replace your data script

The Faker + pandas script draws every column on its own: foreign keys are
uniform, amounts are uniform, timestamps are flat across the clock, emails do
not match names, and nothing reconciles under a JOIN. Write the shape down
instead, and check the result:

```yaml
# misata.yaml
seed: 7
tables:
  customers:
    rows: 2000
    columns:
      customer_id: {type: int, primary_key: true}
      email: {type: text, text_type: email}
      signup_at: {type: datetime, start: "2024-01-01", end: "2025-12-31"}
  orders:
    rows: 20000
    columns:
      order_id: {type: int, primary_key: true}
      customer_id: {type: foreign_key, references: customers.customer_id}
      ordered_at: {type: datetime, start: "2024-01-01", end: "2025-12-31"}
      amount: {type: float, distribution: lognormal, mu: 3.8, sigma: 0.9, decimals: 2}
```

```bash
misata generate --config misata.yaml --output-dir data
misata audit data      # contradictions: shipped before ordered, totals that do not add up
misata realism data    # synthetic tells: uniform money, even fan-out, flat hours, no nulls
```

By default customers are unevenly active (a few place most orders), times of
day and days of the week have a rhythm, and every order postdates its
customer. A typo such as `lamda: 3` is an error with a suggestion, not a
column of noise.

**When the schema is not enough:**

- **Event logs.** `processes:` declares how tickets, claims or orders move
  through steps, with branch probabilities, rework loops and a duration per
  step, and writes an event-log table (`misata.to_xes` for process mining).
  [Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/guides/processes.md)
- **Your own logic.** `@misata.generator("tier")` registers a function that
  sees the parent row and a seeded RNG; the schema names it with
  `generator: tier`, and `misata --plugin my_module` loads it on the CLI.
  [Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/guides/custom-generators.md)
- **Tests.** Installing misata registers a pytest plugin:
  `@pytest.mark.misata(schema="misata.yaml")` and a test receives
  `misata_tables` or a seeded `misata_sqlite` URL. No conftest.
  [Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/guides/testing.md)
- **Nested payloads.** `type: json` with `fields` and `type: array` with
  `items` generate real nested values (emails, cities, codes inside them);
  `misata.to_jsonl` and `misata.to_polars` keep them nested.
  [Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/guides/nested-columns.md)
- **Say what it is for.** `preset: demo | test | load | ml | eval` sets the
  realism defaults that job needs: current dates, small fixtures, volume, or
  declared dirt. [Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/guides/presets.md)
- **Your Django models.** `misata.from_django()` reads fields, choices,
  lengths, validators and relations.
  [Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/guides/django.md)
- **Your existing database.** `misata seed postgresql://...` reads the
  schema, honours CHECK, UNIQUE and column widths, and inserts everything in
  one transaction.

**Does it obey the schema?** On five SQL schemas with CHECK rules,
composite keys, a self-referencing hierarchy and a six-level foreign-key
chain, Misata generated from the DDL alone has zero violations; the Faker
script people write instead has 15,000 to 50,000 per schema, and SDV's
multi-table model, trained on valid data, has 3,000 to 5,600 on the three
schemas it accepts (it refuses the other two). Counted by a checker that
shares no code with Misata
([validity benchmark](https://github.com/rasinmuhammed/misata/blob/main/docs/validity-benchmark.md)).

**How realistic is it?** We test blind generation against held-out real data
([benchmark](https://github.com/rasinmuhammed/misata/blob/main/docs/realism-benchmark.md)).
On Olist's real marketplace orders, a names-and-types schema with no access to
the data is harder to tell from real rows than a Faker script (classifier AUC
0.74 vs 0.79) and close to SDV fitted on 15,000 real orders (0.71). On NYC
taxi trips it gets the night-heavy hour curve closer than SDV does, but its
fares are still too wide, so a classifier separates it from real trips more
easily than the script. The benchmark publishes both, and says which results
followed a fix it prompted.

---

## 🚀 The 6 Unique Capabilities of Misata

What separates Misata from legacy libraries like Faker and imitation models like SDV:

### 1. Exact Outcome Conformance ($0.00 Error)
Declare the aggregate outcome (revenue curve, churn rate, seasonal surge, default curve), and Misata generates micro-rows whose monthly or annual sums match your target **to $0.00 error**. While off-the-shelf synthesizers miss aggregate targets by 74–86%, Misata hits them provably ([read the research paper](https://arxiv.org/abs/2606.08736v1)).

### 2. Instant Sandbox Oracle for AI Coding Agents
Misata includes a native [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server. Cursor, Claude Code, and Windsurf can call `create_sandbox` to spin up an isolated SQLite database seeded with realistic relational data in 2 seconds. AI agents can test SQL queries and test code against real tables instead of guessing schema.
```bash
pip install "misata[mcp]" && misata mcp install --client all
```

### 3. Topological DAG Relational Integrity (0 Orphan Foreign Keys)
Parent-child relationships across 10+ tables are resolved via topological rank ordering. Self-referential hierarchies, composite unique constraints, and temporal causality (`signup_date <= order_date <= payment_date <= refund_date`) are strictly enforced.

### 4. Cross-Vertical Text Realism (Zero Lorem Ipsum)
No Latin placeholder gibberish. Combinatorial microtext generators provide authentic text across 15+ real-world industries:
- **E-Commerce**: Category-conditioned product descriptions (electronics, apparel, home, beauty), authentic return reasons, delivery notes.
- **B2B SaaS**: Support ticket subjects, multi-line issue descriptions, agent resolution notes, competitor churn reasons.
- **FinTech**: Bank statement descriptors, ACH/wire remittance memos, AML audit overrides.
- **Healthcare**: Clinical SOAP progress notes, chief complaints, discharge instructions, medical dosage schedules (`TID`, `QID`, `PRN`).
- **Customer Reviews**: Sentiment calibrated provably to 1-to-5 star ratings.

### 5. Vectorized Speed (100x–500x Faster Than Faker)
While Faker iterates row-by-row in pure Python (5,000–15,000 rows/s), Misata uses vectorized NumPy array operations. It generates **500,000 to 16,000,000 rows/second** on a single CPU core.

### 6. Introspect & Seed Live Databases (`misata seed`)
Point Misata directly at a PostgreSQL, MySQL, or SQLite database. Misata introspects foreign keys, check constraints, enums, and column types, generates a topological insertion plan, and seeds production-like data directly back into your database without writing schema code.

---

## 🎯 Dozens of Real-World Use Cases

Misata is built for engineers, testers, data teams, and founders across dozens of everyday workloads:

### 🛠️ Data Engineering & ETL Pipelines
- **Known-Answer Pipeline Testing**: Declare exact KPI targets (e.g. $1.2M Q4 revenue), generate synthetic raw tables, and verify your dbt, Spark, or SQL transforms return the exact expected figure.
- **High-Throughput Stress Testing**: Churn 10,000,000+ rows in seconds to test partition boundaries, shuffle performance, and warehouse scaling.
- **Schema Migration Dry Runs**: Rehearse destructive column backfills and foreign key additions against realistic data before deploying to production.
- **Deterministic CI/CD Fixtures**: Reproducible seeds ensure test assertions never flake across continuous integration runs.

### 🤖 AI Coding Agents & LLM Development
- **Agent SQL Sandboxes**: Provide Cursor, Claude Code, and Windsurf with isolated, pre-seeded databases to validate SQL queries without production access.
- **Text-to-SQL Benchmark Generation**: Build complex relational schema benches with diverse joins to evaluate fine-tuned coding models.
- **Evaluation Database Packs (Evalpacks)**: Create verified eval datasets with independent DuckDB answer keys where the ground truth cannot be wrong.

### 🗄️ Application Development & Database Seeding
- **Local & Staging Environment Seeding**: Seed staging Postgres, MySQL, or SQLite databases with realistic customer histories and 0 broken foreign keys (`misata seed`).
- **ORM Model Fixtures**: Generate rich fixtures matching your Prisma schema or SQLAlchemy declarative models.
- **Multi-Tenant Isolation Verification**: Test row-level security (RLS) and tenant isolation rules without cross-tenant key leakage.
- **Incremental Data Growth (`generate_diff`)**: Add 5,000 new rows to an existing dataset while auto-offsetting IDs and preserving referential integrity.

### 📊 BI, Product Demos & Sales Engineering
- **Board-Ready Dashboard Demos**: Populate Tableau, PowerBI, and Metabase dashboards with convincing seasonality (Black Friday spikes, summer dips) rather than flat random noise.
- **Sales Engineering Prototypes**: Demo customer-facing analytics with authentic company names, human names, and transaction histories with zero PII exposure.
- **Feature Previews**: Preview upcoming charts, cohorts, and metrics before production customer data accumulates.

### 💳 FinTech, Banking & Payments
- **Double-Entry Ledger Balancing**: Generate accounting transactions where total debits strictly equal credits across every ledger account.
- **Credit Risk & Loan Tapes**: Calibrate delinquency curves, credit score distributions, and default rates for credit portfolio testing.
- **AML & Fraud Detection Testing**: Inforce exact fraud incidence rates (e.g. 2.4%) with authentic transaction memos and AML audit trails.
- **Payment Remittance**: Simulate SWIFT, ACH, and card transactions with valid routing numbers, CVVs, and statement descriptors.

### 🏥 Healthcare & Clinical Informatics
- **Synthetic patient cohorts**: Generate realistic patient populations, vital signs, and encounter histories from a schema, with no real patient record involved.
- **Clinical NLP Model Evaluation**: Evaluate healthcare LLMs against authentic SOAP notes, chief complaints, and discharge summaries.
- **Ward & Scheduling Simulation**: Simulate hospital appointment grids with realistic 15-minute intervals, business hours, and weekend dips.

### 📦 E-Commerce & Supply Chain Logistics
- **Multi-Category Catalog Modeling**: Produce realistic item specs and descriptions conditioned on category (electronics, apparel, home, industrial).
- **Return & Refund Workflows**: Simulate return logistics with authentic return reasons, restocking milestones, and customer refund dates.
- **Route & Fleet Optimization**: Compute realistic routes with Haversine distance calculations and valid secondary addresses (Apt, Suite, Bldg).

### 🛡️ Cybersecurity & IT Infrastructure
- **Network Intrusion Datasets**: Generate netflow logs, port scans, and DDoS traffic patterns for security tool benchmarking.
- **System Exception & Error Analysis**: Populate observability dashboards with realistic deadlocks, HTTP 504 timeouts, and connection pool exhaustion logs.
- **Compliance Audit Logging**: Simulate SOC2- and HIPAA-style access logs with documented managerial access override justifications.

### 🔬 Machine Learning & Statistical Research
- **Synthetic Twins from CSV (`misata.mimic`)**: Clone distributions and correlations from sensitive CSVs without copying a single original row.
- **Hierarchical Cluster Modeling (ICC)**: Generate multi-site data with specified Intraclass Correlation Coefficients for mixed-effects regression.
- **Time-Series Autocorrelation (AR1)**: Generate longitudinal entity trajectories that maintain realistic temporal memory.

---

## ⚡ Why You Should Never Use Faker Again

Faker was built over a decade ago for single-attribute mock values. For modern applications, it introduces critical failure modes:

| Problem in 2026 | Faker Reality | Misata |
|:---|:---|:---|
| **Relational Topology** | ✗ 0 concept of databases or FKs; manual glue code required | **✓ Strict topological DAG; 0 orphan FKs guaranteed** |
| **Cross-Column Coherence** | ✗ Incoherent (e.g. "Male" name, mismatched email, invalid city) | **✓ Coherent identities, addresses, and causality** |
| **Text Realism** | ✗ 2,000-year-old Latin "Lorem Ipsum" or robotic templates | **✓ 15+ domain microtext pools (SOAP notes, tickets, memos)** |
| **Mathematical Consistency**| ✗ Violates basic accounting (`price * qty != total`) | **✓ Exact mathematical formulas and balanced ledgers** |
| **Performance** | ✗ ~10k rows/s (single-threaded Python loops) | **✓ 500k to 16M rows/s (Vectorized NumPy engine)** |
| **Aggregate Targets** | ✗ Impossible (uniform random noise) | **✓ Exact closed-form outcome conformance ($0.00 error)** |
| **Database Seeding** | ✗ Manual SQL scripts or ORM boilerplate | **✓ One-command introspection and seeding (`misata seed`)** |

*Read the complete [Faker vs SDV vs Misata Guide](https://misata.studio/docs/faker-vs-sdv-vs-misata) for full benchmarks and code comparisons.*

---

## 🛠️ Eight Ways to Generate Data

Misata fits whatever workflow you already use:

| Input Mode | Best For | Learn More |
|---|---|---|
| **1. Plain English Story** | Rapid prototyping, zero configuration | [Story Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/generation/story.md) |
| **2. YAML Schema-as-Code** | Committing versioned data definitions to git | [YAML Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/generation/yaml.md) |
| **3. Live Database Seeding** | Introspecting and populating Postgres, MySQL, SQLite | [Database Seeding Guide](https://misata.studio/docs/database-seeding-python) |
| **4. Python Dict Schema** | Programmatic in-memory generation in Python scripts | [Dict Schema Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/generation/dict.md) |
| **5. dbt Project Schemas** | Generating fixtures directly from `schema.yml` | [dbt Seeding Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/guides/dbt-seed.md) |
| **6. Prisma Schema** | Next.js and Node.js developers seeding full-stack apps | [Prisma Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/generation/database.md#prisma) |
| **7. Multi-Provider LLMs** | Groq, OpenAI, Claude, Gemini, or Ollama-driven schemas | [LLM Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/generation/llm.md) |
| **8. Incremental Growth** | Appending rows with offset IDs and preserved FKs | [Incremental Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/generation/incremental.md) |

---

## 🌐 20+ Built-in Industry Domains

Generate domain-complete schemas with tuned statistical distributions out of the box:

[SaaS](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/saas.md) · [E-Commerce](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/ecommerce.md) · [FinTech](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/fintech.md) · [Healthcare](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/healthcare.md) · [Logistics](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/logistics.md) · [Credit Risk](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/credit-risk.md) · [HR & People](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/hr.md) · [Streaming Media](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/streaming.md) · [Insurance](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/insurance.md) · [CRM & Sales](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/crm.md) · [Food Delivery](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/fooddelivery.md) · [Travel & Hospitality](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/travel.md) · [Gaming](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/gaming.md) · [Crypto & DeFi](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/crypto.md) · [Predictive Maintenance](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/predictive-maintenance.md) · [Network Intrusion](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/network-intrusion.md) · [Islamic Finance](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/islamic-finance.md) · [EdTech](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/edtech.md) · [Real Estate](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/realestate.md) · [Contact Centers](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/contact-center.md) · [Manufacturing SPC](https://github.com/rasinmuhammed/misata/blob/main/docs/domains/manufacturing-spc.md)

*See the [Complete Domain Catalog](https://misata.studio/docs/domains).*

---

## ⚡ Performance

Measured on standard Apple M-series hardware (single CPU core, no GPU):

| Workload | Row Count | Generation Time | Throughput |
|:---|--:|--:|--:|
| **Single table (lognormal distribution)** | 1,000,000 | 0.06 s | **~16M rows/s** |
| **Star schema (5 tables, 4 FK dependencies)** | 1,055,030 | 1.54 s | **~687k rows/s** |
| **Multi-table enterprise database** | 100,000 | 0.42 s | **~240k rows/s** |

---

## 📚 Documentation Index

For in-depth guides, API references, and architecture deep dives:

- **[Getting Started & Quickstart](https://misata.studio/docs/quickstart)**: 5-minute tutorial from installation to your first dataset.
- **[Text Realism & `enrich_text`](https://github.com/rasinmuhammed/misata/blob/main/docs/guides/long-form-text.md)**: Deep dive into all 15 microtext pools and DataFrame text enrichment.
- **[AI Agent MCP Server Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/guides/mcp.md)**: Setup and tool reference for Cursor, Claude Code, and Windsurf.
- **[Outcome Curves & Seasonality](https://github.com/rasinmuhammed/misata/blob/main/docs/guides/outcome_curves.md)**: Mathematical specification of revenue and growth curves.
- **[Database Seeding in Python](https://misata.studio/docs/database-seeding-python)**: Introspecting and seeding production databases.
- **[Mimic Mode Guide](https://github.com/rasinmuhammed/misata/blob/main/docs/guides/mimic.md)**: Synthetic twins of a CSV, and why a twin is not anonymous.
- **[Export Formats](https://misata.studio/docs/export)**: Exporting to DuckDB, Apache Parquet, Arrow IPC, and ANSI/Postgres SQL.
- **[Apache Spark & Databricks](https://github.com/rasinmuhammed/misata/blob/main/docs/spark.md)**: Scaling synthetic generation across distributed Spark clusters.
- **[Full Schema Declarations Reference](https://github.com/rasinmuhammed/misata/blob/main/docs/reference/declarations.md)**: Complete parameter reference for every column type and constraint.

---

## 📄 Research & Citation

The closed-form exact-outcome conformance engine is formalised in arXiv preprint **[2606.08736](https://arxiv.org/abs/2606.08736v1)**:

```bibtex
@article{rasin2026declarative,
  title   = {Declarative Outcome-Conformant Synthesis: Exact, Closed-Form
             Specification Satisfaction and a Conformance Benchmark},
  author  = {Rasin, Muhammed},
  year    = {2026},
  url     = {https://arxiv.org/abs/2606.08736v1}
}
```

---

## 🤝 Contributing & Development Status

Misata is currently under massive, rapid development to push synthetic realism to its absolute limit: expanding real-world domain knowledge, deepening seed pool vocabularies, elevating textual column realism, and advancing statistical fidelity across every industry vertical.

Contributions from domain experts, data engineers, and researchers are warmly welcomed! Whether you want to:
- **Enrich Text & Vocabulary Pools**: Add authentic seeds and grammar rules for specialized domains in `misata/vocab_seeds.py` and `misata/microtext.py`.
- **Contribute a Domain Capsule**: Expand built-in industry templates (healthcare, legal, banking, engineering, supply chain).
- **Advance Statistical Fidelity**: Improve multi-variate copulas, time-series dynamics, or outcome-curve solvers.
- **Report Edge Cases & Realism Flaws**: Open an issue or discussion whenever generated values don't look 100% human-authentic.

```bash
git clone https://github.com/rasinmuhammed/misata
cd Misata
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Misata is open-source under the [MIT License](https://github.com/rasinmuhammed/misata/blob/main/LICENSE).
