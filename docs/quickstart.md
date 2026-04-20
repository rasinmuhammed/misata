---
title: Quick Start — Misata Synthetic Data Generator
description: Get started with Misata in 5 minutes. Install, generate your first multi-table synthetic dataset from plain English, and export to CSV, Parquet, or your database.
---

# Quick Start

## Install

```bash
pip install misata
```

Optional extras:

```bash
pip install "misata[llm]"        # Groq / OpenAI / Claude / Gemini / Ollama schema generation
pip install "misata[documents]"  # PDF output via weasyprint
pip install "misata[advanced]"   # SDV/CTGAN statistical synthesis
```

---

## Your first dataset

```python
import misata

tables = misata.generate(
    "A SaaS company with 5k users, monthly subscriptions, and 20% churn",
    seed=42,
)

for name, df in tables.items():
    print(f"{name}: {len(df):,} rows")
    print(df.head(3))
    print()
```

`generate()` returns a `dict[str, pd.DataFrame]` — one key per table, FK integrity guaranteed.

---

## Inspect the schema first

```python
schema = misata.parse("A fintech company with 10k customers")
print(schema.summary())
# Tables: customers, accounts, transactions
# Relationships: customers → accounts → transactions
# Rows: 10000 / 25000 / 80000

tables = misata.generate_from_schema(schema)
```

---

## Export

```python
misata.to_parquet(tables, "data/")
misata.to_duckdb(tables, "data/dataset.duckdb")
misata.to_jsonl(tables, "data/")
```

---

## CLI

```bash
# Generate from a story
misata generate --story "A marketplace with 10k sellers" --rows 10000

# Generate from YAML schema
misata init        # scaffold misata.yaml
misata generate    # reads misata.yaml automatically

# Profile a CSV file
misata validate customers.csv
```

---

## Next

- [All six generation methods →](generation/index.md)
- [Localisation (15 country packs) →](localisation.md)
- [Time-series generation →](timeseries.md)
- [CLI reference →](cli.md)
