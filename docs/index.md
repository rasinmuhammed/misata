---
title: Misata — Proof-Backed Python Synthetic Data Generator
description: Generate realistic multi-table synthetic data from plain English, YAML, or your own database, with Oracle reports for validation, realism, privacy, and reproducibility.
---

# Misata — Proof-Backed Python Synthetic Data Generator

**Realistic multi-table synthetic data with validation reports — from a sentence, YAML, or your own database.**

No ML model. No real data needed. Referential integrity guaranteed across every table. Every CLI generation writes an Oracle report by default.

---

```bash
misata generate \
  --story "Brazilian fintech with R$ payments, CPF verification, and 3% fraud" \
  --rows 1000 \
  --output-dir ./demo_data

# CSVs + ./demo_data/oracle_report.json
```

The Oracle report separates hard guarantees from advisory realism checks: row counts, referential integrity, constraints, temporal consistency, locale/domain fit, privacy notes, fidelity scores, and reproducibility metadata.

[Get started →](quickstart.md){ .md-button .md-button--primary }
[View on GitHub →](https://github.com/rasinmuhammed/misata){ .md-button }

---

=== "Plain English"

    ```python
    import misata

    tables = misata.generate(
        "A SaaS company with 5k users, monthly subscriptions, and 20% churn"
    )
    print(tables["users"].head())
    print(tables["subscriptions"].head())
    ```

=== "YAML Schema"

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
    ```

    ```python
    schema = misata.load_yaml_schema("misata.yaml")
    tables = misata.generate_from_schema(schema)
    ```

=== "From a Database"

    ```python
    from misata import schema_from_db, generate_from_schema, seed_database

    schema = schema_from_db("postgresql://user:pass@localhost/myapp")
    tables = generate_from_schema(schema)
    report = seed_database(tables, "postgresql://user:pass@localhost/myapp_dev")
    # SeedReport: seeded 6 tables, 47,300 rows in 1.2s
    ```

---

## Install

```bash
pip install misata
```

## Why Misata over Faker or SDV?

Faker generates one column at a time — you write the loop, manage the IDs, enforce uniqueness yourself.
SDV requires real training data and a fitted model before you get anything.
**Misata generates a complete relational dataset from a single sentence — no training data, no boilerplate.**

| Feature | Faker | SDV | **Misata** |
|:--|:--:|:--:|:--:|
| One-liner multi-table generation | — | — | **✓** |
| Story auto-detects locale + country stats | — | — | **✓** |
| 18 built-in domain schemas (SaaS → streaming) | — | — | **✓** |
| Narrative growth curves (Q4 push, Black Friday, 10×) | — | — | **✓** |
| MCP server — usable from Claude / Cursor / Windsurf | — | — | **✓** |
| YAML schema committed to git | — | — | **✓** |
| DB introspection → generate → re-seed | — | Limited | **✓** |
| Direct PostgreSQL / SQLite seeding | — | — | **✓** |
| FK integrity across all tables | — | **✓** | **✓** |
| Fully offline, no LLM required | **✓** | **✓** | **✓** |
| Time-series generation | — | — | **✓** |
| 15 country locale packs | — | — | **✓** |
| Shareable Oracle report | — | — | **✓** |

---

## Narrative control — tell Misata exactly what shape your data should have

Misata understands natural-language growth patterns and turns them into exact monthly targets:

```python
# Seasonal ecommerce with named events
misata.generate("Ecommerce store with 5k orders — Black Friday spike, Christmas peak")

# SaaS growth curve with a quarterly dip
misata.generate("SaaS mrr from $50k in Jan to $200k in Dec, Q3 slump")

# 10× startup trajectory
misata.generate("SaaS startup — MRR 10x growth over the year")

# Quarterly narrative
misata.generate("Fintech payments — strong Q4, dip in Q1, flat Q2")
```

Quarterly patterns (`Q1`–`Q4`), named events (Black Friday, Christmas, summer slump, back to school), multipliers (`doubled`, `tripled`, `10x`, `halved`) — all resolve to exact per-month control points in the generated data.

---

## Use Misata from Claude, Cursor, or Windsurf (MCP)

Misata ships a built-in [Model Context Protocol](https://modelcontextprotocol.io) server. Once configured, AI assistants can generate synthetic data on the user's behalf from natural language.

```bash
pip install "misata[mcp]"
```

Add to Claude Desktop config:

```json
{ "mcpServers": { "misata": { "command": "misata-mcp" } } }
```

Then ask Claude: *"Generate a fintech fraud dataset with 1 000 customers and a 2% fraud rate."*

[MCP setup guide →](guides/mcp.md)

---

## What people use Misata for

- **Test data generation** — seed your dev/staging database with realistic data in seconds
- **BI and dashboard demos** — populate a demo environment with coherent, believable numbers
- **Database seeding in CI/CD** — reproducible, seed-controlled datasets for every test run
- **Privacy-safe development** — work with realistic schemas without exposure to PII
- **AI agent workflows** — let Claude or Cursor generate the dataset directly via MCP

---

## Supported domains

Misata auto-detects your domain from the story and applies statistically accurate priors:

`saas` · `ecommerce` · `fintech` · `healthcare` · `marketplace` · `logistics` · `hr` · `social` · `realestate` · `pharma` · `fooddelivery` · `edtech` · `gaming` · `crm` · `crypto` · `insurance` · `travel` · `streaming`

[See all domains →](domains.md)
