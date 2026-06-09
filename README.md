<div align="center">

<img src="public/logo.png" width="180" alt="Misata" />

# Misata

**Realistic multi-table synthetic data — from a sentence, YAML, or your own database.**

[![PyPI version](https://img.shields.io/pypi/v/misata.svg?style=flat-square&color=E89030)](https://pypi.org/project/misata/)
[![Python versions](https://img.shields.io/pypi/pyversions/misata.svg?style=flat-square)](https://pypi.org/project/misata/)
[![CI](https://img.shields.io/github/actions/workflow/status/rasinmuhammed/misata/ci.yml?branch=main&style=flat-square&label=tests)](https://github.com/rasinmuhammed/misata/actions)
[![License](https://img.shields.io/github/license/rasinmuhammed/misata.svg?style=flat-square)](LICENSE)
[![Open in Colab](https://img.shields.io/badge/Open%20in-Colab-F9AB00?style=flat-square&logo=googlecolab&logoColor=white)](https://colab.research.google.com/github/rasinmuhammed/misata/blob/main/notebooks/quickstart.ipynb)
[![Paper](https://img.shields.io/badge/arXiv-2606.08736-b31b1b?style=flat-square&logo=arxiv&logoColor=white)](https://arxiv.org/abs/2606.08736v1)

</div>

<!-- mcp-name: io.github.rasinmuhammed/misata -->

---

Misata generates consistent, referentially-intact multi-table datasets from a plain-English description, a YAML schema file, or an existing database schema. It focuses on a specific problem: generating data that **conforms to declared analytical outcomes** — things like "monthly revenue should follow this curve" or "fraud rate should be 3% in Q1 rising to 8% by Q4" — without needing any source data to learn from.

No machine-learning model is required. No real data is needed.

```python
import misata

tables = misata.generate(
    "A fintech with 50k transactions. "
    "3% fraud in Q1 rising to 8% by Q4. "
    "Revenue from $200k in January to $1.2M by December."
)
```

---

## Research foundation

Misata's exact-aggregate engine is described in a paper:

> **Declarative Outcome-Conformant Synthesis: Exact, Closed-Form Specification Satisfaction and a Conformance Benchmark**
> Muhammed Rasin — arXiv:2606.08736 (2026)
> [https://arxiv.org/abs/2606.08736v1](https://arxiv.org/abs/2606.08736v1)

The paper studies a specific task — generating tabular data that satisfies declared analytical outcomes exactly, without any source data. It formalises when this is possible, provides a closed-form mechanism based on properties of the Gamma distribution (Lukacs' characterisation), and introduces **SpecBench**: a benchmark for measuring conformance to analytical outcomes in cold-start relational synthesis.

Misata is the reference implementation of that paper. The full SpecBench benchmark lives at [`research/specbench/`](research/specbench/).

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

## Quick start

```bash
misata generate \
  --story "Brazilian fintech with R$ payments, CPF verification, and 3% fraud" \
  --rows 1000 \
  --output-dir ./demo_data
```

```python
import misata

tables = misata.generate("A SaaS company with 5k users, monthly subscriptions, and 20% churn")

print(tables["users"].head())
print(tables["subscriptions"].head())
```

---

## Core capabilities

### Outcome curves — aggregate targets (AME = 0)

When you declare a monthly revenue curve, Misata generates individual rows whose per-period totals match the declared targets exactly. This is the core property proven in the paper.

```python
tables = misata.generate(
    "SaaS MRR from $50k in January to $200k in December, with a Q3 slump."
)
# Each month's sum of amount matches the declared target to $0.00 error.
```

Natural language patterns that work:

```python
misata.generate("SaaS mrr from $50k in Jan to $200k in Dec, with a Q3 slump")
misata.generate("Ecommerce orders, Black Friday spike, Christmas peak")
misata.generate("SaaS startup — MRR 10x growth over the year")
misata.generate("Fintech payments — strong Q4, dip in Q1")
```

Or explicitly in YAML:

```yaml
outcome_curves:
  - table: transactions
    column: amount
    time_column: transaction_date
    avg_transaction_value: 250.0
    curve_points:
      - { month: 1,  target_value: 50000  }
      - { month: 6,  target_value: 120000 }
      - { month: 12, target_value: 200000 }
```

### Rate curves — per-period rate conformance (RCE = 0)

Declare the exact positive-class rate for boolean columns, with optional interpolation between declared periods.

```python
# Misata extracts the RateCurve automatically from natural language:
tables = misata.generate(
    "A fintech with 50k transactions. "
    "3% fraud in Q1 rising to 8% by Q4."
)
# transactions["is_fraud"] per-month positive rate matches the declared rate exactly.
```

Or explicitly:

```python
from misata.schema import RateCurve, SchemaConfig

schema = SchemaConfig(
    ...,
    rate_curves=[
        RateCurve(
            table="transactions",
            column="is_fraud",
            time_column="transaction_date",
            interpolate=True,
            rate_points=[
                {"period": "2024-01", "rate": 0.03},
                {"period": "2024-12", "rate": 0.08},
            ],
        )
    ],
)
```

In YAML:

```yaml
rate_curves:
  - table: transactions
    column: is_fraud
    time_column: transaction_date
    interpolate: true
    rate_points:
      - { period: "2024-01", rate: 0.03 }
      - { period: "2024-12", rate: 0.08 }
```

Rate nouns auto-detected from natural language: `fraud`, `churn`, `defect`, `late`, `delayed`, `default`, `cancelled`, `returned`, `active`.

### Relational temporal coherence

When a parent table is generated with a temporal curve, child and grandchild tables automatically cluster their FK references and date distributions to match the parent's temporal density — no configuration needed.

```
regions (Q4 curve) → stores (inherits density) → sales (inherits density)
```

Level 2 date inheritance is also available explicitly:

```yaml
columns:
  payment_date:
    type: date
    inherits_curve_from: accounts   # payment_date distribution mirrors accounts temporal shape
```

### Referential integrity (FIVR = 0)

Tables are generated in topological order. Every FK value references a valid parent PK — across any number of levels, with no post-processing required.

---

## Six ways to generate data

### 1. Plain English — no config required

```python
tables = misata.generate("A fintech startup with 10k customers, fraud rate 3%, and IBAN accounts")
```

### 2. YAML schema-as-code — commit it to git

```bash
misata init           # scaffolds misata.yaml in the current directory
misata generate       # reads misata.yaml automatically
```

```yaml
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
```

### 3. Seed an existing database directly

```python
from misata import schema_from_db, generate_from_schema, seed_database

schema = schema_from_db("postgresql://user:pass@localhost/myapp")
tables = generate_from_schema(schema)
report = seed_database(tables, "postgresql://user:pass@localhost/myapp_dev")
```

```bash
misata init --db postgresql://user:pass@localhost/myapp
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

### 5. LLM-assisted generation

```python
from misata import LLMSchemaGenerator

gen = LLMSchemaGenerator(provider="groq")
schema = gen.generate_from_story(
    "A fraud detection dataset — 2% positive rate, FICO scores, transaction velocity features"
)
tables = misata.generate_from_schema(schema)
```

Requires `pip install "misata[llm]"` and one of `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`.

### 6. Incremental generation

```python
tables = misata.generate("A fintech company with 1000 customers", seed=1)
tables = misata.generate_more(tables, schema, n=1000, seed=2)
print(len(tables["customers"]))  # 2000
```

---

## Use Misata from Claude / Cursor / Windsurf (MCP)

Misata ships a built-in [Model Context Protocol](https://modelcontextprotocol.io) server.

```bash
pip install "misata[mcp]"
```

Add to Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "misata": { "command": "misata-mcp" }
  }
}
```

Then ask:

> *"Generate a fintech dataset with 50k transactions and a 3% fraud rate."*

See the [MCP guide](docs/guides/mcp.md) for Cursor/Windsurf/Zed setup.

---

## Misata Oracle — validation layer

Every generation run can produce an **Oracle report**: a structured record of what was checked.

**Hard checks (fail the run if violated):**
- Referential integrity across all FK relationships
- Row-count fulfillment
- Schema and constraint validation
- Deterministic reproducibility under the same seed

**Advisory checks:**
- Quality score and plausibility warnings
- Privacy heuristics
- Schema-vs-output fidelity score
- Locale/domain fit

```python
schema = misata.parse("Brazilian fintech with CPF verification", rows=1000)
tables = misata.generate_from_schema(schema)
oracle = misata.build_oracle_report(tables, schema, seed=schema.seed)

print(oracle["passed"])
print(oracle["advisory"]["locale_domain_fit"]["locale"])
```

---

## SpecBench

A benchmark for measuring conformance to analytical outcomes in cold-start relational synthesis. Introduced in the accompanying paper; the implementation lives in [`research/specbench/`](research/specbench/).

Eight tasks, six metrics:

| Metric | Measures |
|:--|:--|
| **AME** | Aggregate match error — how far monthly totals deviate from declared targets |
| **RCE** | Rate conformance error — how far per-period rates deviate from declared rates |
| **FIVR** | FK integrity violation rate |
| **CSAT** | Constraint satisfaction rate |
| **DET** | Determinism under repeated runs with the same seed |
| **GDC** | Generative diversity coefficient |

```python
from research.specbench.metrics import aggregate_match_error, rate_conformance_error

ame = aggregate_match_error(tables, "transactions", "amount", "date", targets)
rce = rate_conformance_error(tables, "transactions", "is_fraud", "date", rate_targets)
```

---

## Localisation

Misata detects country context from your story and generates locale-appropriate data.

```python
tables = misata.generate("German SaaS company in Berlin with 2k enterprise customers")
# → de_DE names, salary distributions, GmbH/AG company suffixes, 5-digit postcodes

tables = misata.generate("Brazilian fintech with R$ payments and CPF verification, 50k users")
# → pt_BR names, BRL salary priors, CPF format ###.###.###-##
```

15 built-in locales with salary distributions, age priors, national ID formats, currencies, and city lists — drawn from OECD, World Bank, ILO, and national statistics offices (2023–24 data).

| Locale | Country | Currency | Salary median | National ID format |
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

---

## Supported domains

18 built-in domain schemas:

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
| Food Delivery | food delivery, restaurant, takeout | restaurants, customers, couriers, orders |
| EdTech | edtech, courses, students, enrollments | instructors, courses, students, enrollments |
| Gaming | gaming, players, leaderboard, esports | players, matches, sessions, achievements |
| CRM | crm, salesforce, deals, pipeline | companies, contacts, deals, activities |
| Crypto / Web3 | crypto, blockchain, ethereum, defi | wallets, tokens, transactions, token_prices |
| Insurance | insurance, policy, claims, premium | customers, policies, claims, payments |
| Travel | travel, hotel, flights, bookings | users, hotels, flights, bookings, reviews |
| Streaming | streaming, netflix, subscribers | subscribers, content, watch_history, ratings |

No keyword match → generic single-table schema with smart column inference.

---

## How it works

```
story / YAML / dict / DB introspection / MCP tool call
              ↓
        StoryParser  ·  locale detection  ·  rate curve extraction
              ↓
        SchemaConfig  ←  validate_schema()
              ↓
        DataSimulator
          ├─ topological sort (FK dependency order)
          ├─ FactEngine  →  Gamma conditional-sum (exact aggregate targets)
          ├─ rate curve enforcement  →  Prop. 2 Bernoulli (exact per-period rates)
          ├─ TemporalDensityMap  →  child/grandchild temporal density inheritance
          ├─ domain priors  →  locale priors (salary, age, monetary distributions)
          ├─ constraint engine (inequality, range, ratio, sum, unique)
          └─ RealisticTextGenerator (Faker + locale-aware Kaggle vocabulary)
              ↓
        {table_name: DataFrame}
              ↓
        seed_database  ·  to_parquet  ·  to_duckdb  ·  generate_documents
```

**Domain priors** — monetary columns use log-normal distributions. Categoricals use Zipf sampling. Blood types, country distributions, and salary bands reflect real-world statistics.

**Outcome curves** — narrative is parsed into monthly control points. Named events, quarters, and multipliers all work. The FactEngine generates rows whose per-period sums hit the declared targets exactly.

**Realism rules** — `cost` is always less than `price`. `delivered_at` is always after `shipped_at`. `hire_date` is after `date_of_birth` + 18 years. Email addresses derive from name columns.

---

## Performance

Measured on Apple M-series (single core, no GPU):

| Workload | Rows | Time | Throughput |
|:--|--:|--:|--:|
| Single table, lognormal | 1 000 000 | 0.06 s | ~16M rows/s |
| Star schema (5 tables, 4 FKs) | 1 055 030 | 1.54 s | ~687k rows/s |

---

## Export

```python
misata.to_parquet(tables, "data/")
misata.to_duckdb(tables, "data/dataset.duckdb")
misata.to_jsonl(tables, "data/")
```

---

## Document generation

```python
paths = misata.generate_documents(
    tables, "invoice", table="orders", output_dir="/tmp/invoices", format="html"
)
# format="pdf" requires: pip install "misata[documents]"
```

---

## Quality and privacy analysis

```python
bundle = misata.analyze_generation(tables, schema)

print(bundle.data_card.summary())
print(bundle.fidelity_report.score)
print(bundle.privacy_report.pii_risk)
```

---

## Contributing

```bash
git clone https://github.com/rasinmuhammed/misata
cd misata
pip install -e ".[dev]"
pytest tests/
```

611 tests, 0 failures. Issues and PRs welcome — [github.com/rasinmuhammed/misata/issues](https://github.com/rasinmuhammed/misata/issues)

---

<div align="center">
Built by <a href="https://github.com/rasinmuhammed">Muhammed Rasin</a>
</div>
