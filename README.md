<div align="center">

<img src="public/logo.png" width="180" alt="Misata" />

# Misata

**Realistic multi-table synthetic data that conforms to the outcome you specify — exact revenue curves, fraud rates, referential integrity, and statistical structure — from a sentence, YAML, or your database. No ML model, no real data.**

[![PyPI version](https://img.shields.io/pypi/v/misata.svg?style=flat-square&color=E89030)](https://pypi.org/project/misata/)
[![Python versions](https://img.shields.io/pypi/pyversions/misata.svg?style=flat-square)](https://pypi.org/project/misata/)
[![CI](https://img.shields.io/github/actions/workflow/status/rasinmuhammed/misata/ci.yml?branch=main&style=flat-square&label=tests)](https://github.com/rasinmuhammed/misata/actions)
[![License](https://img.shields.io/github/license/rasinmuhammed/misata.svg?style=flat-square)](LICENSE)
[![Open in Colab](https://img.shields.io/badge/Open%20in-Colab-F9AB00?style=flat-square&logo=googlecolab&logoColor=white)](https://colab.research.google.com/github/rasinmuhammed/misata/blob/main/notebooks/quickstart.ipynb)
[![Paper](https://img.shields.io/badge/arXiv-2606.08736-b31b1b?style=flat-square&logo=arxiv&logoColor=white)](https://arxiv.org/abs/2606.08736v1)
[![smithery badge](https://smithery.ai/badge/misata/misata)](https://smithery.ai/servers/misata/misata)

</div>

<!-- mcp-name: io.github.rasinmuhammed/misata -->

---

Most synthetic-data tools learn from a real dataset and imitate it. Misata works the other way: you **declare the outcome you want** : "monthly revenue rises from \$50k to \$200k," "fraud is 3% in Q1 rising to 8% by Q4," "every customer's `total_spent` equals the sum of their orders" — and Misata generates individual rows whose aggregates hit those targets **exactly**, with full referential integrity, from no source data at all.

This is *outcome-conformant generation*. The mechanism is formalised in an arXiv preprint ([2606.08736](https://arxiv.org/abs/2606.08736v1)): a closed-form method that satisfies declared aggregates to \$0.00 error, where off-the-shelf imitation synthesisers trained on the same data miss by 74–86%. Every run can also emit an **Oracle report**, a proof bundle covering referential integrity, constraints, temporal consistency, and reproducibility.

It generates from a plain-English description, a YAML schema, or an existing database schema. No machine-learning model is required. No real data is needed.

Built for:
- **Database seeding** — fill dev and staging environments with production-like data
- **Integration tests** — relational fixtures with FK integrity across every table
- **Demos and prototypes** — realistic numbers, names, and distributions, no PII
- **BI and dashboard development** — data shaped like your real domain before launch
- **Statistical method validation** — synthetic clinical trial data, longitudinal cohorts, and multi-site studies that pass mixed-effects models, ICC tests, and autocorrelation checks

---

## Research

Misata's exact-aggregate engine is backed by an arXiv preprint:

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

Misata ships a built-in [Model Context Protocol](https://modelcontextprotocol.io) server with a clear division of labour: **the AI agent designs the schema, Misata guarantees the math.** Agents are good at knowing that a veterinary clinic needs a `species` column; Misata is good at making 50 000 rows where every foreign key resolves, every roll-up reconciles to the cent, and the same seed reproduces byte-identical output. The primary tool, `generate_from_schema`, accepts the agent's schema dict and returns the data **plus an integrity proof** — per-relationship orphan counts the agent can show you.

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

> *"Design a clinical-trials database — sites, patients, visits, adverse events — and generate 100k rows."*

> *"I need SaaS data: MRR from $50k in January, doubled by December, with a Q3 slump."*

The agent designs whatever tables the request needs (any domain — it isn't limited to Misata's built-ins), calls Misata, writes CSVs to disk, and reports back with previews and the verified integrity summary. See the [MCP guide](docs/guides/mcp.md) for Cursor/Windsurf/Zed setup and all six available tools.

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

## Mimic mode — clone any CSV in one call

Point `misata.mimic()` at a real dataset and get a synthetic twin that matches every column's distributions but contains none of the original rows. No schema authoring, no config.

```python
import pandas as pd
import misata

real = pd.read_csv("titanic.csv")
twin = misata.mimic(real, rows=2000, seed=42, table_name="passengers")["passengers"]
```

The profiler handles the columns that break other tools:

- **Alphanumeric code columns** (Ticket `"A/5 21171"`, Cabin `"C85"`, SKUs, reference numbers) are detected by their character-class shape and reproduced structurally — same shapes in the right proportions, entirely new values, zero verbatim leak from the source. They no longer fall through to prose text generation.
- **Floats keep their cents.** A Fare of `7.25` generates as `7.25`-shaped values. The profiler infers decimal places from the data; semantic quantization (charm pricing) never fires on mimicked columns.
- **Distributions are fit from the data.** Skewed-positive columns get lognormal; constant columns get a uniform stub; everything else gets normal. Categorical columns with fewer than 50 values carry their real frequencies.

```python
# Verify: no verbatim rows can leak through
shared = [c for c in real.columns if c in twin.columns]
overlap = pd.merge(real[shared].astype(str), twin[shared].astype(str), how="inner")
assert len(overlap) == 0
```

---

## Six ways to generate data

### 1. Plain English, no config required

```python
tables = misata.generate("A fintech startup with 10k customers, fraud rate 3%, and IBAN accounts")
```

Misata reads the story, infers domain (fintech), scale (10 000 rows), and column semantics (fraud flag, IBAN format) — no schema authoring needed.

### 2. YAML schema-as-code, commit it to git

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
        "order_date":  {"type": "date"},
    },
}, row_count=5_000)

tables = misata.generate_from_schema(schema)
```

**Declared outcome curves** — add `__outcome_curves__` as a top-level key alongside the table definitions. Generated rows sum to every declared target exactly, to the cent:

```python
schema = misata.from_dict_schema({
    "__outcome_curves__": [{
        "table": "orders",
        "column": "amount",
        "time_column": "order_date",
        "time_unit": "month",
        "value_mode": "absolute",
        "start_date": "2024-01-01",
        "avg_transaction_value": 120.0,
        "curve_points": [
            {"month": 1,  "target_value":  50_000.0},
            {"month": 6,  "target_value": 110_000.0},
            {"month": 12, "target_value": 200_000.0},
        ],
    }],
    "orders": {
        "__rows__": 5000,
        "order_id":   {"type": "integer", "primary_key": True},
        "amount":     {"type": "float", "min": 5, "max": 500},
        "order_date": {"type": "date"},
    },
}, seed=42)

tables = misata.generate_from_schema(schema)
monthly = (
    tables["orders"]
    .assign(m=pd.to_datetime(tables["orders"]["order_date"]).dt.month)
    .groupby("m")["amount"].sum()
)
assert abs(monthly[1]  -  50_000) < 0.01   # exact
assert abs(monthly[12] - 200_000) < 0.01   # exact
```

**Constraints and correlations** — enforce business rules and inter-column relationships directly in the dict schema:

```python
schema = misata.from_dict_schema({
    "patients": {
        "__rows__": 1000,
        "__constraints__": [
            # visit must be on or after enrollment — enforced at generation, not post-processing
            {"type": "inequality", "column_a": "visit_date",
             "operator": ">=", "column_b": "enroll_date", "action": "cap"},
        ],
        "__correlations__": [
            # heavier patients tend to have higher blood pressure (r = 0.41)
            {"col_a": "bmi", "col_b": "systolic_bp", "r": 0.41},
        ],
        "patient_id":  {"type": "integer", "primary_key": True},
        "enroll_date": {"type": "date"},
        "visit_date":  {"type": "date"},
        "bmi":         {"type": "float", "min": 16, "max": 55},
        "systolic_bp": {"type": "float", "min": 90, "max": 200},
    },
})
```

`__rate_curves__` works the same way for per-period rate targets on boolean or categorical columns (fraud rates, churn flags, plan distributions).

### 5. LLM-assisted generation, richer semantics, optional

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

### 6. Incremental generation, grow a dataset without re-seeding

```python
tables = misata.generate("A fintech company with 1000 customers", seed=1)

# Add 1 000 more rows — IDs auto-offset, FK integrity maintained across both batches
tables = misata.generate_more(tables, schema, n=1000, seed=2)
print(len(tables["customers"]))  # 2000
```

---

## Realism that survives inspection

Synthetic data rarely fails on the big numbers — it fails on the small tells a reviewer spots in five seconds. Misata kills each tell with a specific, deterministic mechanism. No LLM is involved; everything is seeded and reproducible.

| The tell | The mechanism |
|:--|:--|
| `Pablo Müller, Female` — names, genders, and cultures drawn independently | **Joint identity sampling**: `(culture, gender, first, last)` is one draw from culture-keyed pools, with a measured 6% cross-culture intermix (real populations aren't endogamous). Emails derive from the final name. |
| `appointment_date: 2022-08-29 06:36:12.995319155` — nanosecond precision, 6 AM, a Sunday | **Temporal profiles**: scheduled events snap to 15-minute grids in business hours with weekends damped; signups follow waking-hour rhythms; only machine events (logs, clicks) keep sub-second precision; birth dates are dates. |
| Every category equally likely | **Zipf–Mandelbrot marginals**: unweighted categoricals follow the rank-frequency power law real statuses, countries, and categories follow — with the dominant value varying per column. Declared probabilities always win. |
| `Chicago → San Diego, 145.6 km` | **Geographic facts**: distances between named cities are computed (haversine × road circuity) from 289 embedded city coordinates, and travel times follow from distances. Facts, not distributions — so the Oracle can verify them. |
| A five-star review that reads "disappointing" — or lorem ipsum | **Grammar microtext**: review text is generated *from* the row's rating by a seeded grammar (1★ reads angry, 5★ reads delighted — a verifiable invariant), and free-text notes come from a business-note grammar. Lorem ipsum cannot reach output. |
| A 19-minute appointment, a price of $43.27 | **Numeric quantization**: scheduled durations snap to the slot grids calendars actually offer (15/30/45/60), retail prices end in .99/.95/.00, ages are integers. Measured quantities are left alone. |

```python
tables = misata.generate("A hospital with 300 patients, doctors and appointments", seed=7)
# patients:     Tae-yang Ahn (Male) · Valentina Esposito (Female) · pooja.kapoor@icloud.com
# appointments: 2023-03-08 14:00:00 · 2022-07-21 09:15:00 — 15-min grid, business hours, 2% weekends
```

---

## Unknown domains: composed, not confabulated

The 18 built-in domains are templates. For everything else, Misata refuses to fake understanding — and refuses to give up. A compositional synthesizer derives **structure** from your sentence: plural noun phrases become tables, "80 beekeepers" binds a row count, and a small archetype lattice (person / asset / place / event / document) provides honest structural columns and foreign-key wiring.

```python
tables = misata.generate(
    "A beekeeping cooperative with 12 apiaries, 80 beekeepers, hives, inspections and honey harvests"
)
# beekeepers:  beekeeper_id, first_name, last_name, email, joined_at, status
# inspections: inspection_id, beekeeper_id, apiary_id, hive_id, inspection_date, status
# → full FK integrity, profiled timestamps, Zipfian statuses — from one sentence, no LLM
```

What it will *not* do is invent domain semantics: unknown entities get structural columns (reference codes, statuses, dates) and the detection report says exactly that, pointing to the two upgrade paths — a schema dict, or an LLM. The same gate also prevents confabulation: a story that only weakly matches a built-in template (one incidental keyword) is composed from its own entities instead of being forced into the wrong template.

---

## Capsules: teach Misata a domain once

A capsule is one shareable JSON file of domain vocabularies — the species, treatments, and model names a domain calls things — with provenance for every list. Intelligence is spent **once**, at creation; generation stays deterministic, offline, and free.

```bash
# Mine a capsule from example data you already have — no LLM, no key
misata capsule create --domain veterinary --from-csv ./samples/ -o vet.capsule.json
misata capsule show vet.capsule.json
```

```python
# Vocabularies override built-in pools for matching columns
tables = misata.generate("a veterinary clinic with patients and visits",
                         capsule="vet.capsule.json")
```

Capsules can also be written by an LLM once and reviewed before use (`capsule_from_llm`, BYO key — Groq's free tier works), or written by hand: it's JSON. Because a capsule is a file, it's a community artifact — share it via git, a gist, or HF datasets.

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

## Cross-table roll-ups

Make parent summary columns reconcile with child rows, so the data survives a `GROUP BY ... JOIN`. A `customers.total_spent` column generated independently of that customer's actual orders is a giveaway that data is fake; a roll-up computes it from the real child rows.

```python
schema = misata.from_dict_schema({
    "name": "shop",
    "tables": {
        "customers": {
            "rows": 500,
            "columns": {
                "customer_id": {"type": "int", "unique": True},
                # total_spent = sum(orders.amount) per customer
                "total_spent": {"type": "float", "rollup": {
                    "from_table": "orders", "fk": "customer_id",
                    "agg": "sum", "column": "amount"}},
                # completed_spend = sum(amount) where status == "completed"
                "completed_spend": {"type": "float", "rollup": {
                    "from_table": "orders", "fk": "customer_id", "agg": "sum",
                    "column": "amount", "where": {"status": "completed"}}},
            },
        },
        "orders": {
            "rows": 3000,
            "columns": {
                "order_id": {"type": "int", "unique": True},
                "customer_id": {"type": "foreign_key", "references": "customers.customer_id"},
                "amount": {"type": "float", "distribution": "lognormal", "mu": 4, "sigma": 0.5, "min": 1},
                "status": {"type": "categorical", "choices": ["completed", "cancelled", "pending"]},
            },
        },
    },
})
tables = misata.generate_from_schema(schema)
# tables["customers"]["total_spent"] reconciles exactly with the orders table.
```

Aggregations: `sum`, `count`, `mean`, `max`, `min`. When a parent column name explicitly names a child table (`num_orders`, `total_orders`), the roll-up is inferred automatically with no declaration. Roll-ups survive the `misata.yaml` round-trip and run at generation time.

---

## Statistical realism for clinical, longitudinal, and regulated data

Most synthetic data tools generate rows independently from a declared distribution. That works for pipeline tests and database seeding. It does not work when the data needs to pass a statistical method: a mixed-effects model that checks whether sites differ, an autocorrelation test on repeated measurements, or an audit that flags physiologically impossible values.

Misata 0.8.1.0 adds a suite of features that close this gap. All are declared in the same plain dict schema and are reachable from MCP agents, Studio, and direct Python callers.

---

### Stratified distribution profiles — different distributions per subgroup

A real three-arm clinical trial does not have all patients drawn from one HbA1c distribution. The placebo arm looks different from the treatment arm. Use `profiles` on any column to declare this precisely:

```python
schema = misata.from_dict_schema({
    "patients": {
        "__rows__": 2000,
        "patient_id": {"type": "integer", "primary_key": True},
        "arm": {
            "type": "string",
            "enum": ["placebo", "low_dose", "high_dose"],
            "probabilities": [0.34, 0.33, 0.33],
        },
        "hba1c_change": {
            "type": "float",
            "distribution": "normal",
            "mean": -0.35,  # fallback for rows that match no profile
            "std": 0.50,
            "profiles": [
                {"when": "arm == 'placebo'",   "distribution": "normal", "mean": -0.35, "std": 0.50},
                {"when": "arm == 'low_dose'",  "distribution": "normal", "mean": -1.05, "std": 0.55},
                {"when": "arm == 'high_dose'", "distribution": "normal", "mean": -1.25, "std": 0.55},
            ],
        },
    }
})
```

The `when` expression is evaluated as a pandas query against already-generated columns in the same batch. Rows that match no profile get the column's top-level distribution. Profiles can reference any column generated before the current one in declaration order.

---

### Informative missingness — MAR and MNAR

Real clinical and survey datasets have non-random missing data. Misata models both mechanisms:

**Missing At Random (MAR):** The probability of a value being missing depends on an observed predictor column. Patients with higher baseline HbA1c are more likely to miss follow-up visits.

```python
"dropout_visit": {
    "type": "integer",
    "min": 1, "max": 12,
    "nullable": True,
    "missing_if": {
        "predictor": "hba1c_baseline",
        "relationship": "higher_increases_probability",
        "base_rate": 0.05,
        "max_rate": 0.40,
        "mechanism": "MAR",
    },
}
```

**Missing Not At Random (MNAR):** The probability of a value being missing depends on the value itself — the classic censoring mechanism. A lab test result is missing precisely because it was too extreme to report.

```python
"lab_value": {
    "type": "float",
    "distribution": "normal", "mean": 10.0, "std": 3.0,
    "nullable": True,
    "missing_if": {
        "predictor": "lab_value",          # references its own column
        "mechanism": "MNAR",               # value-dependent censoring
        "relationship": "higher_increases_probability",
        "base_rate": 0.02,
        "max_rate": 0.45,
    },
}
```

**Conditional nulls** (`null_when`): Null a column whenever a boolean expression is true. `dropout_visit` should be null when the patient did not drop out.

```python
"dropout_visit": {
    "type": "integer", "min": 1, "max": 12,
    "nullable": True,
    "null_when": "dropout == False",
}
```

---

### Exact incidence control — precise rates, not statistical approximations

A `boolean` column with `probability: 0.22` gives approximately 22% True values across many runs. If you need the dataset to contain exactly 22% — auditable against its own spec — use `exact_incidence`:

```python
"is_adverse_event": {
    "type": "boolean",
    "exact_incidence": {
        "mode": "exact",
        "rate": 0.22,          # exactly floor(n * 0.22) rows are True
    },
}
```

Per-arm exact rates work the same way:

```python
"is_responder": {
    "type": "boolean",
    "exact_incidence": {
        "mode": "exact",
        "group_by": "arm",
        "rates": {"placebo": 0.15, "low_dose": 0.40, "high_dose": 0.55},
    },
}
```

Use `exact_incidence` whenever the dataset will be checked against a declared rate. The difference between "approximately 3% fraud" and "exactly 3% fraud" is the difference between a dataset that passes an audit and one that does not.

---

### Within-entity time-series autocorrelation — longitudinal data that passes statistical tests

Without autocorrelation, a longitudinal dataset (visits, sensor readings, financial time series) is statistically identical to a cross-sectional one. Every off-the-shelf time-series test — Ljung-Box, Durbin-Watson, autocorrelation plot — will immediately detect that the data is synthetic.

The `time_series` spec re-writes a column to have real within-entity autocorrelation:

```python
"hba1c": {
    "type": "float",
    "distribution": "normal", "mean": 8.5, "std": 1.5,
    "time_series": {
        "entity_id": "patient_id",     # one autocorrelation process per patient
        "order_by":  "visit_number",   # temporal ordering within each patient
        "model":     "AR1",            # AR1 | LINEAR_TREND | RANDOM_WALK | MEAN_REVERSION
        "phi":       0.72,             # autocorrelation coefficient
        "noise_std": 0.30,             # measurement noise per step
        "anchor_column": "hba1c_baseline",  # starting value drawn from this column
        "trend": {
            "slope_mean": -0.08,       # average improvement per visit
            "slope_std":  0.02,        # per-patient slope variability
        },
    },
}
```

Four models are available:

| Model | Use case |
|:--|:--|
| `AR1` | Most clinical and physiological measurements — blood pressure, glucose, HbA1c |
| `LINEAR_TREND` | KPIs with a declared direction — revenue growth, weight loss, skill improvement |
| `RANDOM_WALK` | Asset prices, temperature drift, any mean-free Brownian motion |
| `MEAN_REVERSION` | Inventory levels, mood scores, any bounded process that pulls back to average |

---

### Per-patient anchored distributions — separating within-entity and between-entity variation

When generating a child table (visits) whose measurements should be anchored to a parent entity's (patient's) value, use a formula in `distribution.mean`:

```python
"patients": {
    "__rows__": 200,
    "patient_id": {"type": "integer", "primary_key": True},
    "hba1c_baseline": {"type": "float", "distribution": "normal", "mean": 8.5, "std": 1.5},
},
"visits": {
    "__rows__": 2000,
    "visit_id": {"type": "integer", "primary_key": True},
    "patient_id": {"type": "integer", "foreign_key": {"table": "patients", "column": "patient_id"}},
    "hba1c": {
        "type": "float",
        "distribution": "normal",
        "mean": {"formula": "@patients.hba1c_baseline"},  # resolved per row via FK
        "std": 0.40,                                      # within-patient noise
    },
}
```

The engine resolves the FK for every visit row and draws from that patient's personalised distribution. Between-patient variation comes from the spread of `hba1c_baseline` (std 1.5); within-patient visit-to-visit noise is std 0.40. This is the correct two-level structure that a mixed-effects model expects. Generating all visit HbA1c values from a single shared distribution — as every column-independent generator does — produces a dataset that fails every random-effects test immediately.

---

### Hierarchical ICC cluster effects — multi-site and multi-centre designs

In a multi-site clinical trial, patients within the same site share unmeasured site-level factors. This within-site homogeneity — measured by the intraclass correlation coefficient (ICC) — is a defining feature of multi-centre data. Without it, all sites look statistically identical, and any ICC test will detect the synthetic origin.

`__cluster_effect__` is declared on the **parent** table and applies per-entity random intercepts to columns in the **child** table:

```python
"sites": {
    "__rows__": 12,
    "__cluster_effect__": {
        "affects_table": "patients",
        "affects_columns": {
            "systolic_bp": {
                "icc": 0.18,       # target intraclass correlation
                "sd_total": 18.0,  # total std; sd_between = sqrt(0.18) * 18 ≈ 7.6 mmHg
            },
            "hba1c": {
                "sd_between": 0.52,  # supply sd_between directly
            },
        },
    },
    "site_id": {"type": "integer", "primary_key": True},
    "region": {"type": "string", "enum": ["North", "South", "Central", "East", "West"]},
}
```

One random intercept is drawn per site from N(0, sd_between) and added to every patient at that site. The marginal distribution across all patients is preserved. Typical ICC values: 0.05–0.20 for clinical measurements, 0.10–0.30 for educational outcomes, 0.15–0.40 for financial metrics across branches.

---

### Full correlation matrix — declare the complete covariance structure at once

For tables with many correlated columns, the matrix syntax is cleaner than a list of pairs:

```python
"__correlations__": {
    "matrix": {
        "columns": ["hba1c", "glucose", "bmi", "systolic_bp"],
        "values": {
            "hba1c":       [1.00, 0.65, 0.28, 0.22],
            "glucose":     [0.65, 1.00, 0.22, 0.18],
            "bmi":         [0.28, 0.22, 1.00, 0.41],
            "systolic_bp": [0.22, 0.18, 0.41, 1.00],
        }
    }
}
```

The matrix is expanded into pairwise pairs and enforced via Iman-Conover rank reordering, which hits declared Pearson r values while preserving each column's marginal distribution exactly. Pairwise list syntax still works unchanged.

---

### State machine terminal states — process-correct categorical columns

Any column that represents an entity's position in a process — clinical trial status, customer lifecycle stage, order fulfilment state — should follow a Markov chain, not a flat probability. `__state_machine__` generates the correct terminal distribution:

```python
"patients": {
    "__state_machine__": {
        "state_column": "patient_status",
        "initial_state": "enrolled",
        "transitions": {
            "enrolled":     {"on_treatment": 0.97, "screen_failure": 0.03},
            "on_treatment": {"completed": 0.77,    "dropout": 0.23},
        },
    },
    ...
}
```

States with no outgoing transitions are terminal. The engine traverses the chain per row until a terminal state is reached. Declared transition probabilities are preserved in expectation. Works alongside exact incidence, profiles, correlations, and time series in the same table.

---

### Domain-aware validation — audit generated data against physiological and financial bounds

After generating clinical or financial data, validate it against built-in range bounds before using it:

```python
tables = misata.generate_from_schema(schema)

report = misata.validate_domain(tables, domain="clinical_trial")
print(report.summary())
# Domain validation (clinical_trial): 0 errors, 0 warnings.

assert report.passed   # no physiologically impossible values
```

Built-in ranges for `clinical_trial` / `clinical`:

| Column | Min | Max | Unit |
|:--|--:|--:|:--|
| hba1c | 4.0 | 14.0 | % |
| glucose | 2.0 | 40.0 | mmol/L |
| systolic_bp | 60.0 | 260.0 | mmHg |
| diastolic_bp | 30.0 | 160.0 | mmHg |
| bmi | 10.0 | 80.0 | kg/m² |
| age | 0.0 | 130.0 | years |
| heart_rate | 20.0 | 300.0 | bpm |
| creatinine | 0.3 | 20.0 | mg/dL |
| hemoglobin | 3.0 | 25.0 | g/dL |

Built-in ranges for `financial` / `fintech`: price ≥ 0, discount 0–1, rate –1 to 100. Column matching is by substring on the lowercased column name — `"hba1c_baseline"` matches the `hba1c` rule.

Add custom ranges via `custom_ranges` dict. Declare `"__domain__": "clinical_trial"` in the dict schema to attach the domain to the `SchemaConfig` for downstream tooling.

---

## Export

```python
# Columnar / analytical
misata.to_parquet(tables, "data/")
misata.to_arrow(tables, "data/")          # Apache Arrow IPC; requires pip install pyarrow
misata.to_duckdb(tables, "data/dataset.duckdb")

# Row-oriented
misata.to_jsonl(tables, "data/")
misata.to_sql(tables, "data/", dialect="postgresql")   # CREATE TABLE + INSERT statements
                                                        # dialects: ansi, postgresql, mysql
```

### Reproducible incremental rows

Generate additional rows that append cleanly to an existing dataset without ID collisions:

```python
# Day 1: generate the base dataset
schema = misata.from_dict_schema({...}, seed=1)
base = misata.generate_from_schema(schema)
for name, df in base.items():
    df.to_csv(f"./data/{name}.csv", index=False)

# Day 2: generate only new rows, PKs offset above existing max
new_rows = misata.generate_diff(
    schema,
    existing_dir="./data/",
    new_rows={"customers": 200, "orders": 1500},
    output_dir="./data/delta/",   # optional: write delta CSVs
)
```

`generate_diff` reads existing CSVs to find the maximum PK per table and generates new rows with PKs offset above that maximum. Use for streaming pipelines, day-over-day test fixtures, and any workflow where you need to extend a dataset without regenerating it from scratch.

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

No keyword match → the compositional synthesizer builds a structural multi-table schema from your sentence's own entities (see *Unknown domains* above); stories with no entities at all fall back to a generic single table with smart column inference.

---

## How it works

```
story / YAML / dict / DB introspection / MCP tool call
              ↓
        StoryParser  ·  compositional synthesizer  ·  locale detection  ·  load_yaml_schema  ·  schema_from_db
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
          ├─ stratified profiles (per-subgroup distributions, pandas eval)
          ├─ AR1 / time-series autocorrelation (per entity, 4 models)
          ├─ state machine (Markov terminal states)
          ├─ ICC cluster effects (per-parent-entity random intercepts)
          ├─ Iman-Conover correlation engine (pairwise + full matrix)
          ├─ MAR / MNAR missingness (predictor-scaled and value-dependent)
          ├─ exact incidence (floor(n × rate), per-group rates)
          ├─ realism core (joint identities, temporal profiles, Zipf marginals,
          │                geo facts, grammar microtext, numeric quantization)
          └─ RealisticTextGenerator (capsules + Faker locale + vocabulary assets)
              ↓
        {table_name: DataFrame}
              ↓
        validate_domain  ·  seed_database  ·  to_parquet  ·  to_arrow
        to_duckdb  ·  to_sql  ·  to_jsonl  ·  generate_documents  ·  MCP CSV output
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

**Realism rules** — `cost` is always less than `price`. `delivered_at` is always after `shipped_at`. `hire_date` is after `date_of_birth` + 18 years and never in the future. `tenure_years` is derived on the same row from `hire_date`. Email addresses derive from first and last name columns, names agree with declared genders, route distances agree with their cities, and review text agrees with its star rating.

---

## What makes Misata different

Comparison reflects each tool's documented, out-of-the-box behavior as of late 2025; all
of these are capable libraries built for different goals, and a "—" means "not a built-in
feature," not "impossible."

| | Faker | Synth | syda | SDV | **Misata** |
|:--|:--:|:--:|:--:|:--:|:--:|
| No config, one line to multi-table data | — | — | — | — | **Yes** |
| Story auto-detects locale + country stats | — | — | — | — | **Yes** |
| 18 built-in domain schemas (SaaS → streaming) | — | — | — | — | **Yes** |
| Narrative curves (Q4 push, Black Friday, 10×) | — | — | — | — | **Yes** |
| Unknown domains composed from the sentence itself | — | — | — | — | **Yes** |
| Coherent identities (name ↔ gender ↔ email agree) | — | — | — | — | **Yes** |
| Review text provably matches its star rating | — | — | — | — | **Yes** |
| Real city distances on route tables | — | — | — | — | **Yes** |
| Shareable domain vocabulary capsules | — | — | — | — | **Yes** |
| Mimic mode — clone distributions from a CSV | — | — | — | **Yes** | **Yes** |
| Pairwise + full-matrix correlation (Iman-Conover) | — | — | — | **Yes** | **Yes** |
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
| Stratified distributions per subgroup (profiles) | — | — | — | — | **Yes** |
| MAR and MNAR informative missingness | — | — | — | — | **Yes** |
| Exact incidence control (floor(n × rate) True values) | — | — | — | — | **Yes** |
| AR(1) / time-series autocorrelation per entity | — | — | — | — | **Yes** |
| Hierarchical ICC cluster effects (multi-site) | — | — | — | — | **Yes** |
| @parent formula in distribution mean/std | — | — | — | — | **Yes** |
| Markov state machine terminal states | — | — | — | — | **Yes** |
| Domain-aware validation (clinical/financial ranges) | — | — | — | — | **Yes** |
| SQL INSERT export (ansi / postgresql / mysql) | — | — | — | — | **Yes** |
| Apache Arrow IPC export | — | — | — | — | **Yes** |
| Reproducible incremental rows (generate_diff) | — | — | — | — | **Yes** |
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

809 tests, 0 failures. Issues and PRs welcome — [github.com/rasinmuhammed/misata/issues](https://github.com/rasinmuhammed/misata/issues)

---

<div align="center">
Built by <a href="https://github.com/rasinmuhammed">Muhammed Rasin</a>
</div>
