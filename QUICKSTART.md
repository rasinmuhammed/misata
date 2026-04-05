# Misata Quick Start

This guide is for someone who wants to get useful output fast, without having to decode product jargon.

If you see a playful Misata term in the docs, it will always be followed by the plain-English meaning. Example:

- `Time Machine` = temporal generation
- `Spellbook` = saved recipe
- `Oracle` = validation and reporting

## Install

```bash
pip install misata
```

Optional extras:

```bash
# Database seeding support
pip install "misata[db]"

# SQLAlchemy schema introspection
pip install "misata[orm]"
```

## Your First Dataset

### Rule-based generation

```bash
misata generate \
  --story "A SaaS company with 10K users, subscriptions, invoices, and a churn spike in Q3" \
  --output-dir ./saas_data \
  --seed 42
```

### LLM-assisted generation

```bash
export GROQ_API_KEY=your_key_here

misata generate \
  --story "A mobile fitness app with workouts, meal plans, and seasonal usage peaks" \
  --use-llm \
  --output-dir ./fitness_data
```

## What Misata Writes

Depending on your run, Misata can produce:
- CSV files for each table
- validation reports
- quality reports
- audit artifacts
- reusable recipe files

## Common Workflows

### 1. Generate data from a story

```bash
misata generate --story "An ecommerce shop with products, carts, orders, and refunds"
```

### 2. Save a repeatable run as a Spellbook

In Misata language, a `Spellbook` is just a reusable recipe.

```bash
misata recipe init \
  --name saas_smoke \
  --story "A SaaS company with users and subscriptions" \
  --output ./saas_recipe.yaml

misata recipe run --config ./saas_recipe.yaml --rows 1000
```

### 3. Seed a database

```bash
# SQLite
misata generate \
  --story "A SaaS company with users and subscriptions" \
  --db-url sqlite:///./misata.db \
  --db-create \
  --db-truncate

# PostgreSQL
misata generate \
  --story "An ecommerce company with products and orders" \
  --db-url postgresql://user:pass@localhost:5432/misata \
  --db-create
```

### 4. Generate from SQLAlchemy models

```bash
misata generate \
  --sqlalchemy myapp.models:Base \
  --db-url sqlite:///./app.db \
  --db-create
```

### 5. Introspect an existing schema

```bash
misata schema --db-url sqlite:///./misata.db --output schema.yaml
```

### 6. Run the Oracle

In Misata language, the `Oracle` is validation and reporting.

```bash
misata validate --db-url sqlite:///./misata.db --config schema.yaml
misata quality --db-url sqlite:///./misata.db --config schema.yaml
```

## Python API

### Story parser

```python
from misata import DataSimulator
from misata.story_parser import StoryParser

parser = StoryParser()
config = parser.parse("A SaaS app with 50K users and monthly subscriptions")

simulator = DataSimulator(config)
for table_name, df in simulator.generate_all():
    print(table_name, len(df))
```

### LLM schema generator

```python
from misata import DataSimulator
from misata.llm_parser import LLMSchemaGenerator

llm = LLMSchemaGenerator(provider="groq")
config = llm.generate_from_story(
    "A healthcare system with patients, appointments, claims, and seasonal booking spikes"
)

result = DataSimulator(config).generate_with_reports()
print(result.validation_report.summary())
```

## Important Concepts

### Time Machine

`Time Machine` means temporal shaping. This includes:
- date distributions
- outcome curves
- seasonal density
- growth and decline stories

### Multiverse

`Multiverse` means multiple scenario variants built from the same schema.  
Misata is moving in this direction through scenario planning, exact curves, and reusable configurations.

### Domain Capsule

A `Domain Capsule` is the resolved context pack that helps Misata stay domain-aware:
- locale
- domain vocabulary
- product or role labels
- provenance for imported assets

You do not need to construct one manually for normal usage. The engine builds it internally.

## CLI Commands

| Command | Plain-English meaning |
|---|---|
| `misata generate` | Generate synthetic data from a story or schema |
| `misata recipe init` | Save a reusable run |
| `misata recipe run` | Execute a saved run |
| `misata graph` | Reverse-engineer from a chart description |
| `misata parse` | Output a config for review |
| `misata schema` | Introspect schema from DB or SQLAlchemy |
| `misata serve` | Start the API server |
| `misata validate` | Validate generated data |
| `misata quality` | Run quality checks |

## Troubleshooting

### `misata: command not found`

```bash
pip install -e .
```

### LLM key missing

```bash
export GROQ_API_KEY=your_key_here
```

### I want to stay rule-based

Just omit `--use-llm`.

```bash
misata generate --story "A SaaS app with users and invoices"
```

## Where To Go Next

- [README.md](/Users/muhammedrasin/misata-project/Misata/README.md)
- [FEATURES.md](/Users/muhammedrasin/misata-project/Misata/FEATURES.md)
- [MISATA_VOICE.md](/Users/muhammedrasin/misata-project/Misata/MISATA_VOICE.md)
- [MISATA_GLOSSARY.md](/Users/muhammedrasin/misata-project/Misata/MISATA_GLOSSARY.md)
