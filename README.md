<div align="center">

# Misata
### Synthetic data with logic, realism, and a little wonder

[![PyPI version](https://img.shields.io/pypi/v/misata.svg?style=for-the-badge)](https://pypi.org/project/misata/)
[![Python versions](https://img.shields.io/pypi/pyversions/misata.svg?style=for-the-badge)](https://pypi.org/project/misata/)
[![License](https://img.shields.io/github/license/rasinmuhammed/misata.svg?style=for-the-badge)](https://github.com/rasinmuhammed/misata/blob/main/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/misata?style=for-the-badge)](https://pypi.org/project/misata/)

**Stop writing one-off fake data scripts.**  
**Describe a world, and let Misata build it.**

[Quick Start](#quick-start) • [Core Features](#core-features) • [Python API](#python-api) • [Misata Language](#misata-language) • [Enterprise Direction](#enterprise-direction)

</div>

## Why Misata

Misata is a Python synthetic data library for people who want control and not guesswork.

If someone is searching for a Python synthetic data generator, a realistic test data library, a database seeding tool, or a multi-table fake data engine, Misata is built for that job.

Most tools can generate rows. Misata is built to generate systems:
- relational data with foreign keys that hold up
- time-based stories that aggregate correctly
- workflows that behave like real business lifecycles
- realism rules that keep rows from contradicting themselves
- repeatable runs that can be validated and reviewed

Misata is simple to start with and deep when you need it.

## What People Use Misata For

Misata is built for practical synthetic data generation in Python.

Common use cases:
- test data generation for local development
- database seeding for staging and QA
- multi-table synthetic data with foreign keys
- dashboard and BI demo datasets
- scenario simulation for SaaS, ecommerce, healthcare, finance, and operations
- privacy-safe stand-in data when real production data should not be copied around

If your search starts with one of these questions, you should be able to find Misata:
- `python synthetic data library`
- `synthetic data generator python`
- `test data generator python`
- `database seeding python`
- `multi-table synthetic data python`
- `fake data generator with foreign keys`

## Quick Start

### Install

```bash
pip install misata
```

### Generate a dataset from a story

```bash
misata generate --story "A SaaS platform with 50K users, monthly subscriptions, and a churn spike in Q3"
```

That single command can:
- infer a relational schema
- generate linked tables
- apply constraints and realism rules
- write the output to disk

### Use an LLM for richer schema planning

```bash
export GROQ_API_KEY=gsk_...
misata generate --story "An ecommerce company with seasonal demand and repeat customers" --use-llm
```

## Core Features

### 1. Story to Schema

Misata can turn a plain-English prompt into a usable schema. It supports both rule-based parsing and LLM-assisted planning.

Example:

```bash
misata generate --story "A healthcare app with patients, doctors, appointments, invoices, and seasonal booking spikes"
```

### 2. Exact Outcome Curves

If you ask for a business story such as:

`Revenue rises from 50k in January to 200k in December with a dip in September`

Misata can generate rows that roll up to those exact targets.

This is especially useful for:
- BI demos
- dashboard testing
- finance scenarios
- realistic sandbox data

### 3. Realism Engine

Misata fixes the contradictions that make synthetic data look fake.

Examples:
- `email` can derive from `first_name` and `last_name`
- `delivered_at` can be cleared if the order is not delivered
- `CEO` can imply an age floor
- `product_name` can match `category`

### 4. Planning and Proportions

Misata sizes tables using relationship structure instead of giving every table the same row count.

That means a schema like:
- `customers`
- `orders`
- `order_items`

can naturally become:
- fewer customers
- more orders
- even more line items

### 5. Workflows

Misata supports explicit business lifecycles such as:
- order states
- support tickets
- subscriptions

This helps rows behave like process data rather than disconnected facts.

### 6. Streaming Validation

Misata validates large generations without keeping the whole world in memory.

That matters when you want:
- CI-safe generation
- repeatable audits
- large local runs
- report generation without RAM blowups

### 7. Asset-Backed Vocabulary

Misata now has a domain vocabulary layer. Instead of relying only on hardcoded default names and product labels, it can compile a domain capsule from local assets and approved ingestion sources.

This is the foundation for:
- localization
- domain-specific names
- sector-specific vocabularies
- safer reuse of public reference material

## Python API

### Basic generation

```python
from misata import DataSimulator
from misata.story_parser import StoryParser

parser = StoryParser()
config = parser.parse("A SaaS company with users, subscriptions, and invoices")

simulator = DataSimulator(config)
for table_name, df in simulator.generate_all():
    print(table_name, len(df))
```

### LLM-assisted schema generation

```python
from misata import DataSimulator
from misata.llm_parser import LLMSchemaGenerator

llm = LLMSchemaGenerator(provider="groq")
config = llm.generate_from_story(
    "A healthcare platform with patients, doctors, claims, and seasonal appointment peaks"
)

simulator = DataSimulator(config)
for table_name, df in simulator.generate_all():
    df.to_csv(f"{table_name}.csv", index=False)
```

### Reports and validation

```python
from misata import DataSimulator

result = DataSimulator(config).generate_with_reports()

print(result.validation_report.summary())
print(result.table_row_counts)
print(result.tables_are_samples)
```

## Frequently Asked Questions

### Is Misata a Python synthetic data generator?

Yes. Misata is a Python library for synthetic data generation, with support for relational datasets, temporal scenarios, realism rules, and validation.

### Can Misata generate test data for databases?

Yes. Misata can generate multi-table test data, preserve foreign-key relationships, and help with database seeding for SQLite, PostgreSQL, and SQLAlchemy-based projects.

### Can Misata generate realistic synthetic data instead of flat fake rows?

Yes. Misata focuses on realism through topology-aware row planning, exact aggregate targets, coherence rules, workflow presets, and domain-aware vocabularies.

### Is Misata only for LLM-based generation?

No. Misata supports both rule-based generation and LLM-assisted schema planning. You can stay fully rule-based if you want deterministic local generation.

## Misata Language

Misata should feel memorable, but never confusing. We use playful names in docs and product language, then immediately pair them with the plain-English meaning.

| Misata term | Plain-English meaning |
|---|---|
| **Wand** | A fast way to generate a first dataset |
| **Spellbook** | A saved recipe or reusable generation setup |
| **Time Machine** | Temporal generation and time-density shaping |
| **Multiverse** | Multiple scenario variants of the same schema |
| **Constellation** | The relationship graph of a dataset |
| **Runes** | Rules, constraints, and formulas |
| **Potion** | A realism or noise profile |
| **Oracle** | Validation and reporting |
| **Portal** | Import or export bridge |
| **Domain Capsule** | The resolved vocabulary and context pack used during generation |

Important rule:

The code stays clear. The naming in docs and UX adds charm, not ambiguity.

That means:
- docs can say `Time Machine`
- APIs can still say `outcome_curves`, `time_unit`, or `generate_with_reports`

## What Makes Misata Different

| Capability | Faker | SDV | Misata |
|---|:---:|:---:|:---:|
| Story-driven schema generation | No | No | Yes |
| Referential integrity | No | Yes | Yes |
| Exact aggregate targets | No | Limited | Yes |
| Explicit business constraints | No | Limited | Yes |
| Workflow-aware rows | No | No | Yes |
| Streaming-safe validation | No | No | Yes |
| Asset-backed domain vocabularies | No | Limited | Yes |

## Documentation Map

- [QUICKSTART.md](/Users/muhammedrasin/misata-project/Misata/QUICKSTART.md): hands-on setup and common commands
- [FEATURES.md](/Users/muhammedrasin/misata-project/Misata/FEATURES.md): the plain-English guide to every major feature
- [CONTRIBUTING.md](/Users/muhammedrasin/misata-project/Misata/CONTRIBUTING.md): development workflow and contribution guide
- [MISATA_VOICE.md](/Users/muhammedrasin/misata-project/Misata/MISATA_VOICE.md): writing style, naming rules, and tone guide
- [MISATA_GLOSSARY.md](/Users/muhammedrasin/misata-project/Misata/MISATA_GLOSSARY.md): magical terms mapped to actual features

## Search Guides

These pages are written around the questions people actually search for:

- [docs/python-synthetic-data-generator.md](/Users/muhammedrasin/misata-project/Misata/docs/python-synthetic-data-generator.md)
- [docs/database-seeding-python.md](/Users/muhammedrasin/misata-project/Misata/docs/database-seeding-python.md)
- [docs/multi-table-synthetic-data.md](/Users/muhammedrasin/misata-project/Misata/docs/multi-table-synthetic-data.md)
- [docs/synthetic-data-for-bi-demos.md](/Users/muhammedrasin/misata-project/Misata/docs/synthetic-data-for-bi-demos.md)
- [docs/faker-vs-sdv-vs-misata.md](/Users/muhammedrasin/misata-project/Misata/docs/faker-vs-sdv-vs-misata.md)

## Examples

- [examples/python_synthetic_data_generator.py](/Users/muhammedrasin/misata-project/Misata/examples/python_synthetic_data_generator.py)
- [examples/database_seeding_postgres.py](/Users/muhammedrasin/misata-project/Misata/examples/database_seeding_postgres.py)
- [examples/multi_table_synthetic_data.py](/Users/muhammedrasin/misata-project/Misata/examples/multi_table_synthetic_data.py)
- [examples/bi_demo_dataset.py](/Users/muhammedrasin/misata-project/Misata/examples/bi_demo_dataset.py)

## Enterprise Direction

Misata is strongest when the user wants control.

That means:
- exact scenario shaping
- explicit constraints
- repeatable runs
- inspectable logic
- domain-aware realism

The long-term goal is not to be a black-box generator. The goal is to become a synthetic data framework that people can understand, trust, and shape.

## Contributing

If you want to contribute, start here:

- read [CONTRIBUTING.md](/Users/muhammedrasin/misata-project/Misata/CONTRIBUTING.md)
- keep public docs simple and human
- use magical terminology only when the plain-English meaning is also obvious

<div align="center">
Built by <a href="https://github.com/rasinmuhammed">Muhammed Rasin</a>
</div>
