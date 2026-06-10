<div align="center">

<img src="public/logo.png" width="180" alt="Misata" />

# Misata

**Proof-backed synthetic data — realistic multi-table datasets with validation reports, from a sentence, YAML, or your own database.**

[![PyPI version](https://img.shields.io/pypi/v/misata.svg?style=flat-square&color=E89030)](https://pypi.org/project/misata/)
[![Python versions](https://img.shields.io/pypi/pyversions/misata.svg?style=flat-square)](https://pypi.org/project/misata/)
[![CI](https://img.shields.io/github/actions/workflow/status/rasinmuhammed/misata/ci.yml?branch=main&style=flat-square&label=tests)](https://github.com/rasinmuhammed/misata/actions)
[![License](https://img.shields.io/github/license/rasinmuhammed/misata.svg?style=flat-square)](LICENSE)
[![Open in Colab](https://img.shields.io/badge/Open%20in-Colab-F9AB00?style=flat-square&logo=googlecolab&logoColor=white)](https://colab.research.google.com/github/rasinmuhammed/misata/blob/main/notebooks/quickstart.ipynb)
[![Paper](https://img.shields.io/badge/arXiv-2606.08736-b31b1b?style=flat-square&logo=arxiv&logoColor=white)](https://arxiv.org/abs/2606.08736v1)

</div>

<!-- mcp-name: io.github.rasinmuhammed/misata -->

---

Misata generates consistent, referentially-intact multi-table datasets from a plain-English description, a YAML schema file, or an existing database schema. Every normal generation run can also write an **Oracle report**: a shareable proof bundle for row counts, referential integrity, constraints, temporal consistency, locale/domain fit, privacy notes, fidelity scores, and reproducibility metadata.

No machine-learning model is required. No real data is needed.

Built for:
- **Database seeding** — fill dev and staging environments with production-like data
- **Integration tests** — relational fixtures with FK integrity across every table
- **Demos and prototypes** — realistic numbers, names, and distributions, no PII
- **BI and dashboard development** — data shaped like your real domain before launch

---

## Research

Misata's exact-aggregate engine is backed by an entry-level preprint arXiv paper:

> **Declarative Outcome-Conformant Synthesis: Exact, Closed-Form Specification Satisfaction and a Conformance Benchmark**  
> Muhammed Rasin — arXiv:2606.08736 (2026)  
> [https://arxiv.org/abs/2606.08736v1](https://arxiv.org/abs/2606.08736v1)

The paper formalises the core claim: when you declare `"SaaS MRR from $50k in January to $200k in December"`, Misata generates individual transactions whose monthly totals match the declared curve **to exactly $0.00 error** — not approximately, but provably, via a closed-form Gamma conditional-sum mechanism (Lukacs' characterisation). Off-the-shelf imitation synthesisers trained on the very same data miss the declared monthly aggregate by 74–86%; Misata reaches exactly 0.

The paper also introduces **SpecBench** — the first benchmark measuring conformance to analytical outcomes for cold-start relational synthesis. Misata is the reference implementation.

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

## Install

```bash
pip install misata
```

Optional extras:

```bash
pip install "misata[llm]"        # multi-provider LLM schema generation
pip install "misata[documents]"  # PDF output via weasyprint
pip install "misata[advanced]"   # SDV/CTGAN statistical synthesis
pip install "misata[mcp]"        # MCP server — expose Misata to Claude, Cursor, and other AI agents
```

---

## Use Misata from Claude / Cursor / Windsurf (MCP)

Misata ships a built-in [Model Context Protocol](https://modelcontextprotocol.io) server. Once configured, any MCP-compatible AI assistant can generate realistic synthetic data for you from natural language — no Python required on your end.

**1. Install:**

```bash
pip install "misata[mcp]"
```

**2. Add to Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "misata": {
      "command": "misata-mcp"
    }
  }
}
```

Restart Claude Desktop. Then just ask:

> *"Generate a fintech dataset with 1 000 customers, payments, and a 2% fraud rate."*

> *"Show me what tables Misata would produce for an HR system with 200 employees."*

> *"I need SaaS data: MRR from $50k in January, doubled by December, with a Q3 slump."*

Claude calls Misata, writes CSVs to disk, and returns the file paths plus a preview of each table. See the [MCP guide](docs/guides/mcp.md) for Cursor/Windsurf/Zed setup and all five available tools.

---

## Quick start

```bash
misata generate \
  --story "Brazilian fintech with R$ payments, CPF verification, and 3% fraud" \
  --rows 1000 \
  --output-dir ./demo_data

# Writes CSVs plus:
# ./demo_data/oracle_report.json
```

```python
import misata

# One sentence → multi-table DataFrame dict
tables = misata.generate("A SaaS company with 5k users, monthly subscriptions, and 20% churn")

print(tables["users"].head())
print(tables["subscriptions"].head())
```

```bash
# Or from the CLI
misata generate --story "A SaaS company with 5k users and 20% churn" --rows 5000
```

## Misata Oracle

The Oracle report is Misata's proof layer. It separates hard guarantees from advisory realism checks so generated data can be trusted in CI, demos, notebooks, and research comparisons.

Guaranteed checks:
- referential integrity across configured relationships
- requested row-count fulfillment
- schema validation and configured constraints
- deterministic reproducibility when a seed is set

Advisory checks:
- quality score and plausibility warnings
- privacy heuristics
- schema-vs-output fidelity score
- locale/domain fit for countries, cities, phone prefixes, and national IDs
- data-card metadata

```python
import misata

schema = misata.parse("Brazilian fintech with CPF verification", rows=1000)
tables = misata.generate_from_schema(schema)
oracle = misata.build_oracle_report(tables, schema, seed=schema.seed)

print(oracle["passed"])
print(oracle["advisory"]["locale_domain_fit"]["locale"])
```

---

## Six ways to generate data

### 1. Plain English — no config required

```python
tables = misata.generate("A fintech startup with 10k customers, fraud rate 3%, and IBAN accounts")
```

Misata reads the story, infers domain (fintech), scale (10 000 rows), and column semantics (fraud flag, IBAN format) — no schema authoring needed.

### 2. YAML schema-as-code — commit it to git

```bash
misata init           # scaffolds misata.yaml in the current directory
misata generate       # reads misata.yaml automatically
```

```yaml
# misata.yaml
name: my-app
seed: 42

tables:
  users:
    rows: 1000
    columns:
      user_id: { type: int, unique: true }
      email:   { type: text, text_type: email }
      plan:    { type: categorical, choices: [free, pro, enterprise] }

  orders:
    rows: 5000
    columns:
      order_id: { type: int, unique: true }
      user_id:  { type: foreign_key }
      amount:   { type: float, min: 5.0, max: 500.0 }

relationships:
  - "users.user_id → orders.user_id"

constraints:
  - name: amount_above_cost
    table: orders
    type: inequality
    column_a: amount
    operator: ">"
    column_b: cost
```

```python
schema = misata.load_yaml_schema("misata.yaml")
tables = misata.generate_from_schema(schema)
```

### 3. Seed an existing database directly

```python
from misata import schema_from_db, generate_from_schema, seed_database

# Introspect the live schema — no manual column definitions
schema = schema_from_db("postgresql://user:pass@localhost/myapp")
tables = generate_from_schema(schema)

# Seed it back — insert order respects FK dependencies automatically
report = seed_database(tables, "postgresql://user:pass@localhost/myapp_dev")
# SeedReport: seeded 6 tables, 47,300 rows in 1.2s
```

```bash
# One-command workflow
misata init --db postgresql://user:pass@localhost/myapp   # writes misata.yaml
misata generate --db-url postgresql://user:pass@localhost/myapp_dev --db-create
```

SQLAlchemy models are supported too:

```python
from misata import seed_from_sqlalchemy_models
from myapp.models import Base

report = seed_from_sqlalchemy_models(Base, db_url="sqlite:///test.db", row_count=500, create_tables=True)
```

### 4. Python dict schema

```python
schema = misata.from_dict_schema({
    "customers": {
        "id":    {"type": "integer", "primary_key": True},
        "email": {"type": "email"},
        "plan":  {"type": "string", "enum": ["free", "pro", "enterprise"]},
    },
    "orders": {
        "id":          {"type": "integer", "primary_key": True},
        "customer_id": {"type": "integer", "foreign_key": {"table": "customers", "column": "id"}},
        "amount":      {"type": "float", "min": 1.0, "max": 999.0},
    },
}, row_count=5_000)

tables = misata.generate_from_schema(schema)
```

### 5. LLM-assisted generation — richer semantics, optional

```python
from misata import LLMSchemaGenerator

gen = LLMSchemaGenerator(provider="groq")          # free tier, fast
# gen = LLMSchemaGenerator(provider="anthropic")   # Claude
# gen = LLMSchemaGenerator(provider="ollama", model="llama3")  # fully local, no API key

schema = gen.generate_from_story(
    "A fraud detection dataset — 2% positive rate, FICO scores, transaction velocity features"
)
tables = misata.generate_from_schema(schema)
```

Requires `pip install "misata[llm]"` plus one of `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`.

### 6. Incremental generation — grow a dataset without re-seeding

```python
tables = misata.generate("A fintech company with 1000 customers", seed=1)

# Add 1 000 more rows — IDs auto-offset, FK integrity maintained across both batches
tables = misata.generate_more(tables, schema, n=1000, seed=2)
print(len(tables["customers"]))  # 2000
```

---

## Localisation

Misata automatically detects the country context from your story and generates statistically accurate data for that locale — the right names, salary distributions, national ID formats, currencies, postcodes, and company naming conventions.

```python
# Locale is detected automatically — no extra flag needed
tables = misata.generate("German SaaS company in Berlin with 2k enterprise customers")
# → names from de_DE Faker pool, salary ~ lognormal(μ=10.71, σ=0.5) ≈ €45k median,
#   postcodes are 5-digit, company names end in GmbH/AG/UG

tables = misata.generate("Brazilian fintech with R$ payments and CPF verification, 50k users")
# → pt_BR names, salary median ~BRL 33.6k, national IDs match CPF format ###.###.###-##

tables = misata.generate("Indian startup in Bangalore with ₹ salary bands and Aadhaar KYC")
# → hi_IN names, salary median ~₹350k/yr, national IDs match Aadhaar 12-digit format
```

Force or override a locale explicitly:

```python
schema = misata.parse("An ecommerce store with 10k orders")
tables = misata.generate_from_schema(schema)  # defaults to en_US

# CLI
misata generate --story "Ecommerce store" --locale ja_JP
```

### 15 built-in locales

| Locale | Country | Currency | Salary median | National ID |
|:--|:--|:--|--:|:--|
| `en_US` | United States | USD / $ | $62 000 | SSN `###-##-####` |
| `en_GB` | United Kingdom | GBP / £ | £34 000 | NIN `AA######A` |
| `de_DE` | Germany | EUR / € | €45 000 | Steuer-IdNr |
| `fr_FR` | France | EUR / € | €38 000 | NIR |
| `pt_BR` | Brazil | BRL / R$ | R$33 600 | CPF `###.###.###-##` |
| `es_ES` | Spain | EUR / € | €27 000 | NIE |
| `hi_IN` | India | INR / ₹ | ₹350 000 | Aadhaar `####-####-####` |
| `ja_JP` | Japan | JPY / ¥ | ¥4 400 000 | My Number |
| `zh_CN` | China | CNY / ¥ | ¥90 000 | Resident ID |
| `ar_SA` | Saudi Arabia | SAR | SAR 96 000 | National ID |
| `ko_KR` | South Korea | KRW / ₩ | ₩42 000 000 | RRN |
| `nl_NL` | Netherlands | EUR / € | €42 000 | BSN |
| `it_IT` | Italy | EUR / € | €29 000 | Codice Fiscale |
| `pl_PL` | Poland | PLN | PLN 72 000 | PESEL |
| `tr_TR` | Turkey | TRY | TRY 720 000 | TC Kimlik |

Each pack carries real salary distributions (median and lognormal priors), age distributions, top-ranked cities, phone-number prefixes, postcode patterns, company suffixes, and VAT rates — sourced from OECD, World Bank, ILO, and national statistics offices (2023–24 data).

```python
# Inspect a locale pack directly
pack = misata.get_locale_pack("de_DE")
print(pack.salary_median)       # 45000
print(pack.currency_symbol)     # €
print(pack.top_cities[:3])      # ['Berlin', 'Hamburg', 'Munich']
print(pack.company_suffixes)    # ['GmbH', 'AG', 'UG', 'KG', 'e.K.']

# Auto-detect from a story
locale = misata.detect_locale("South Korean company in Seoul with KRW salaries")
# → "ko_KR"
```

---

## Constraints

Enforce business rules that survive every row of generation:

```python
from misata.constraints import (
    InequalityConstraint,   # price > cost on every row
    ColumnRangeConstraint,  # min_price <= price <= max_price
    RatioConstraint,        # 70% free / 30% pro
    UniqueConstraint,       # no duplicate (user_id, date) pairs
    SumConstraint,          # total_hours per employee per day <= 8
    NotNullConstraint,      # no nulls in required columns
)

c = InequalityConstraint("price", ">", "cost")
df = c.apply(df)
```

Constraints can also be declared in `misata.yaml` — they run at generation time, not as a post-processing step.

---

## Export

```python
misata.to_parquet(tables, "data/")
misata.to_duckdb(tables, "data/dataset.duckdb")
misata.to_jsonl(tables, "data/")
```

---

## Document generation

Render one document per row from any table — useful for demo datasets that need to look real end-to-end:

```python
# Built-in templates: invoice, patient_report, transaction_receipt, user_profile
paths = misata.generate_documents(
    tables, "invoice", table="orders", output_dir="/tmp/invoices", format="html"
)
# format="pdf" requires: pip install "misata[documents]"

# Custom Jinja2 template
tmpl = "<h1>Order #{{ order_id }}</h1><p>Amount: ${{ amount }}</p>"
paths = misata.generate_documents(tables, tmpl, table="orders", output_dir="/tmp/custom")
```

---

## Quality and privacy analysis

```python
bundle = misata.analyze_generation(tables, schema)

print(bundle.data_card.summary())        # row counts, null rates, type distribution
print(bundle.fidelity_report.score)      # 0–1 statistical fidelity score vs. schema intent
print(bundle.privacy_report.pii_risk)    # column-level PII exposure analysis
```

---

## Supported domains

18 built-in domain schemas — each generates a fully relational, multi-table dataset with realistic distributions, FK integrity, and domain-appropriate column semantics.

| Domain | Trigger keywords | Tables generated |
|:--|:--|:--|
| SaaS | saas, subscription, mrr, churn | users, subscriptions, invoices |
| Ecommerce | ecommerce, orders, store, retail | customers, products, orders, order_items |
| Fintech | fintech, payments, banking, fraud | customers, accounts, transactions |
| Healthcare | healthcare, patients, doctors, clinic | doctors, patients, appointments |
| Marketplace | marketplace, sellers, buyers, listings | sellers, buyers, listings, orders |
| Logistics | logistics, shipping, drivers, routes | drivers, vehicles, routes, shipments |
| HR | hr, employees, payroll, workforce | departments, employees, payroll |
| Social | social media, instagram, feed, followers | users, posts, follows, reactions |
| Real Estate | real estate, housing, mortgage | agents, properties, transactions |
| Pharma | pharma, clinical, trials | researchers, projects, trials, timesheets |
| Food Delivery | food delivery, restaurant, takeout | restaurants, customers, couriers, orders, order_items |
| EdTech | edtech, courses, students, enrollments | instructors, courses, students, enrollments, quiz_attempts |
| Gaming | gaming, players, leaderboard, esports | players, matches, sessions, achievements |
| CRM | crm, salesforce, deals, pipeline | companies, contacts, deals, activities |
| Crypto / Web3 | crypto, blockchain, ethereum, defi | wallets, tokens, transactions, token_prices |
| Insurance | insurance, policy, claims, premium | customers, policies, claims, payments |
| Travel | travel, hotel, flights, bookings | users, hotels, flights, bookings, reviews |
| Streaming | streaming, netflix, subscribers, watch history | subscribers, content, watch_history, ratings |

No keyword match → generic single-table schema with smart column inference.

---

## How it works

```
story / YAML / dict / DB introspection / MCP tool call
              ↓
        StoryParser  ·  locale detection  ·  load_yaml_schema  ·  schema_from_db
              ↓
        DetectionReport  (domain, confidence, near_misses, table_preview, warnings)
              ↓
        SchemaConfig  ←  validate_schema() catches issues before any rows are generated
              ↓
        DataSimulator
          ├─ topological sort (FK dependency order)
          ├─ domain priors  →  locale priors (salary, age, monetary)
          ├─ constraint engine (inequality, range, ratio, sum, unique)
          ├─ outcome curves (monthly targets from narrative control points)
          ├─ Iman-Conover correlation engine (Cholesky, preserves marginals)
          └─ RealisticTextGenerator (Faker locale + Kaggle vocabulary assets)
              ↓
        {table_name: DataFrame}
              ↓
        seed_database  ·  to_parquet  ·  to_duckdb  ·  generate_documents  ·  MCP CSV output
```

**Domain priors** — monetary columns get log-normal distributions. Categoricals use Zipf sampling. Blood types, country distributions, and salary bands reflect real-world statistics.

**Locale priors** — salary and age distributions are overridden with country-specific lognormal/normal parameters sourced from national statistics. `"Brazilian fintech"` in your story means salaries are sampled from the BRL distribution, not the USD one.

**Outcome curves** — natural-language narrative is parsed into exact monthly control points. Named events, quarters, and multipliers all work:

```python
# All of these produce precise, shaped outcome curves:
misata.generate("SaaS mrr from $50k in Jan to $200k in Dec, with a Q3 slump")
misata.generate("Ecommerce orders, Black Friday spike, Christmas peak")
misata.generate("SaaS startup — MRR 10x growth over the year")
misata.generate("Fintech payments — strong Q4, dip in Q1")
```

**Realism rules** — `cost` is always less than `price`. `delivered_at` is always after `shipped_at`. `hire_date` is after `date_of_birth` + 18 years and never in the future. `tenure_years` is derived on the same row from `hire_date`. Email addresses derive from first and last name columns.

---

## What makes Misata different

| | Faker | Synth | syda | SDV | **Misata** |
|:--|:--:|:--:|:--:|:--:|:--:|
| No config, one line to multi-table data | — | — | — | — | **Yes** |
| Story auto-detects locale + country stats | — | — | — | — | **Yes** |
| 18 built-in domain schemas (SaaS → streaming) | — | — | — | — | **Yes** |
| Narrative curves (Q4 push, Black Friday, 10×) | — | — | — | — | **Yes** |
| Mimic mode — clone distributions from a CSV | — | — | — | **Yes** | **Yes** |
| Pairwise correlation enforcement (Iman-Conover) | — | — | — | **Yes** | **Yes** |
| Geospatial columns (lat, lng, postal_code) | — | — | — | — | **Yes** |
| Anomaly injection (per-column outlier rate) | — | — | — | — | **Yes** |
| MCP server — usable from Claude / Cursor | — | — | — | — | **Yes** |
| YAML schema committed to git | — | **Yes** | **Yes** | — | **Yes** |
| JSON Schema validation + editor auto-complete | — | — | — | — | **Yes** |
| DB introspection → generate → re-seed | — | **Yes** | — | Limited | **Yes** |
| Direct DB seeding (Postgres / MySQL / SQLite) | — | — | — | — | **Yes** |
| SQLAlchemy model seeding | — | — | — | — | **Yes** |
| Referential integrity across all FK tables | — | **Yes** | **Yes** | **Yes** | **Yes** |
| Inequality / range constraints (`price > cost`) | — | Limited | — | **Yes** | **Yes** |
| Aggregate target curves (monthly MRR shape) | — | — | — | — | **Yes** |
| Domain-realistic distributions | — | — | — | Limited | **Yes** |
| Multi-provider LLM (Groq / OpenAI / Claude / Gemini / Ollama) | — | — | **Yes** | — | **Yes** |
| Fully offline, no LLM required | **Yes** | **Yes** | — | **Yes** | **Yes** |
| Document generation (HTML / PDF per row) | — | — | — | — | **Yes** |
| Quality + privacy reports | — | — | — | Limited | **Yes** |
| Pure Python, no external services | **Yes** | — | — | **Yes** | **Yes** |

**Faker** generates individual fake values — not relational, no schema, no statistical accuracy.  
**Synth** excels at schema-as-code git workflows; limited distribution control.  
**syda** uses an LLM for every row — semantically rich but expensive, slow, and requires an API key.  
**SDV** learns from real data — a different problem (you need real data first).  
**Misata** generates from intent, offline by default, seeds databases directly, and now brings country-accurate statistics to every column automatically.

---

## Performance

Measured on Apple M-series (single core, no GPU):

| Workload | Rows | Time | Throughput |
|:--|--:|--:|--:|
| Single table, lognormal | 1 000 000 | 0.06 s | ~16M rows/s |
| Star schema (5 tables, 4 FKs) | 1 055 030 | 1.54 s | ~687k rows/s |

---

## Contributing

```bash
git clone https://github.com/rasinmuhammed/misata
cd misata
pip install -e ".[dev]"
pytest tests/
```

Issues and PRs welcome — [github.com/rasinmuhammed/misata/issues](https://github.com/rasinmuhammed/misata/issues)

---

<div align="center">
Built by <a href="https://github.com/rasinmuhammed">Muhammed Rasin</a>
</div>
