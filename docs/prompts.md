---
title: "Copy-paste prompts for Misata: agents, schemas and plain English"
description: "Ready-to-paste prompts for generating synthetic data with Misata, whether you are driving it from Claude, Cursor or ChatGPT, writing a schema directly, or starting from a sentence. Every prompt here was run before publishing."
---

# Prompts

Three ways to reach the same engine, in descending order of how much you can
trust the result without checking it.

```diagram
# Reliability, and where the checking happens

  you write the schema        an agent writes it         plain English
        ▏                            ▏                        ▏
  exact, every key            exact once emitted,      approximate, and
  under your control          agent may guess          silently so
        ▏                            ▏                        ▏
  ▼                            ▼                        ▼
  feasibility refuses a contradiction in all three; only the first two
  guarantee that what you asked for is what was asked of the engine
```

Every prompt on this page was executed against the engine before publishing,
and the plain-English section says exactly where that path breaks.

---

## 1. Driving Misata from an agent

The most reliable way to get a schema you did not want to write by hand. The
agent produces a schema, the engine validates it, and feasibility refuses
anything contradictory, so a bad guess fails loudly instead of quietly.

Paste this into Claude, Cursor, ChatGPT or any coding agent, then add your own
last paragraph.

```text
You are writing a schema for Misata, a declarative synthetic data engine
(pip install misata). Read https://misata.studio/llms.txt for the full
documentation index; each page is also available as raw Markdown by appending
.md to its URL.

Rules:
- Output one Python dict, built with
  schema = misata.from_dict_schema(<the dict>, seed=42)
  tables = misata.generate_from_schema(schema)
  Note generate_from_schema takes a SchemaConfig and takes no seed of its own;
  the seed belongs on from_dict_schema.
- Top-level keys are table names. Each table takes "__rows__" plus its columns.
- Column types: integer, float, string, text, date, datetime, boolean,
  foreign_key. A foreign key is
  {"type": "foreign_key", "foreign_key": {"table": "parent", "column": "id"}}.
- Schema-level declarations are __dunder__ keys beside the tables:
  __outcome_curves__ (an aggregate over time, hit exactly)
  __rate_curves__ (a rate over time, hit exactly)
  __group_shares__ (exact shares of a measure across a category)
  __joint_distributions__ (several margins holding at once)
  __waterfalls__ (movements reconciling to declared balances)
  __stock_flows__ (closing = opening + received - shipped, per unit)
  __lifecycles__ (a state machine, with legal transitions)
  __missingness__ (why values are missing, conditionally)
  __constraints__, __dag_edges__, __closures__, __graph_motifs__
- Prefer declaring the aggregate over inventing per-row values. If the user
  says "revenue grows to 200k", that is an __outcome_curves__ declaration,
  not a min/max on a column.
- Do not invent declaration names. If you are unsure a key exists, fetch
  https://misata.studio/docs/reference/declarations.md and check.
- Always pass a seed, so the run is reproducible.

Now write a schema for: <describe your dataset here>
```

Why this prompt works: it points the agent at a machine-readable index rather
than hoping the model remembers the API, it names the declarations explicitly so
the model does not invent plausible ones, and it tells the model to reach for a
declaration rather than fake the number per row, which is the single most common
mistake.

### Shorter version, for a model that already has the docs

```text
Write a Misata schema (misata.from_dict_schema(..., seed=42) then
misata.generate_from_schema(schema)) for:
<your dataset>.

Use __outcome_curves__ for any "grows to X" aggregate, __group_shares__ for any
"A is 40% of B", and foreign_key columns for every relationship. Check key names
against https://misata.studio/docs/reference/declarations.md before answering.
```

### Giving an agent the tools directly

Misata ships an MCP server, so an agent can generate data itself rather than
writing code you then run:

```bash
pip install "misata[mcp]"
```

See the [MCP guide](guides/mcp.md). Once connected, this is enough:

```text
Use the Misata MCP server to generate a 5-table ecommerce dataset with 2,000
buyers and 20,000 orders where GMV grows from $80k in January 2026 to $260k in
December 2026, then show me the integrity verification.
```

---

## 2. Schema recipes, ready to paste

These run as written.

### A SaaS book with revenue that hits its targets

```python
import misata

schema = misata.from_dict_schema({
    "customers": {
        "__rows__": 800,
        "id": {"type": "integer", "primary_key": True},
        "company": {"type": "text", "semantic": "company_name"},
        "signed_up": {"type": "date"},
    },
    "invoices": {
        "__rows__": 6000,
        "id": {"type": "integer", "primary_key": True},
        "customer_id": {"type": "foreign_key",
                        "foreign_key": {"table": "customers", "column": "id"}},
        "issued_at": {"type": "date"},
        "amount": {"type": "float", "min": 50, "max": 4000},
        "plan": {"type": "string", "enum": ["Starter", "Pro", "Enterprise"]},
    },
    "__outcome_curves__": [{
        "table": "invoices", "column": "amount",
        "time_column": "issued_at", "time_unit": "month",
        "value_mode": "absolute",
        "curve_points": [{"date": "2026-01-01", "target_value": 50000},
                         {"date": "2026-12-01", "target_value": 200000}],
    }],
    "__group_shares__": [{
        "table": "invoices", "measure": "amount", "group_column": "plan",
        "shares": {"Starter": 0.2, "Pro": 0.5, "Enterprise": 0.3},
    }],
}, seed=42)
tables = misata.generate_from_schema(schema)
```

Every month's invoice total equals its declared target, and within every total
the three plans split 20/50/30, exactly.

### An MRR waterfall that reconciles

```python
schema = misata.from_dict_schema({
    "mrr_movements": {
        "__rows__": 900,
        "period": {"type": "string"},
        "movement_type": {"type": "string"},
        "amount": {"type": "float"},
    },
    "__waterfalls__": [{
        "table": "mrr_movements", "starting_value": 100000,
        "points": [{"period": f"2026-{m:02d}", "ending_value": 100000 + m * 6000}
                   for m in range(1, 7)],
        "inflow_shares": {"new": 0.7, "expansion": 0.3},
        "outflow_shares": {"churn": 1.0},
    }],
}, seed=42)
tables = misata.generate_from_schema(schema)
```

### An order lifecycle nobody can contradict

```python
schema = misata.from_dict_schema({
    "orders": {
        "__rows__": 5000,
        "id": {"type": "integer", "primary_key": True},
        "status": {"type": "string"},
        "placed_at": {"type": "date"},
    },
    "__lifecycles__": [{
        "name": "order_flow", "table": "orders",
        "state_column": "status", "start_column": "placed_at",
        "states": [{"name": "placed"}, {"name": "paid"}, {"name": "shipped"},
                   {"name": "delivered"}, {"name": "refunded", "terminal": True}],
        "transitions": [["placed", "paid"], ["paid", "shipped"],
                        ["shipped", "delivered"], ["delivered", "refunded"]],
        "initial": "placed",
    }],
}, seed=42)
tables = misata.generate_from_schema(schema)
```

### Dirty data on purpose, for testing a cleaning step

```python
schema = misata.from_dict_schema({
    "contacts": {
        "__rows__": 5000,
        "id": {"type": "integer", "primary_key": True},
        "name": {"type": "text", "semantic": "person_name"},
        "city": {"type": "string", "enum": ["Berlin", "Lisbon", "Oslo", "Porto"]},
        "notes": {"type": "text"},
        "is_active": {"type": "boolean"},
    },
    "__typos__": [{"table": "contacts", "column": "city", "count": 120}],
    "__duplicates__": [{"table": "contacts", "count": 60}],
    "__missingness__": [{
        "table": "contacts", "column": "notes",
        "rate": 0.75, "else_rate": 0.05,
        "when_column": "is_active", "when_op": "==", "when_value": False,
    }],
}, seed=42)
tables = misata.generate_from_schema(schema)
```

Exactly 120 corrupted city values and exactly 60 duplicate rows, so your
cleaning step has a known number to find and your test can assert it.

### Seed a real database

```bash
misata seed "postgresql://user:pass@localhost:5432/mydb" --rows 5000
```

It reads the schema from the database, inserts parents before children, and
verifies every foreign key afterwards. It plans by default; add `--apply` once
the plan looks right. See [Database seeding in Python](guides/database-seeding-python.md).

---

## 3. Plain English

`misata.generate("...")` parses a sentence into a schema. It is the fastest way
to something on screen and the least precise, so use it to start and then edit
the schema it produced.

### What works

Nouns with counts, in one clause:

```python
misata.generate("A SaaS company with 800 customers and 1200 subscriptions", seed=11)
```

Put a rate in its own sentence rather than in a relative clause:

```python
misata.generate(
    "A payments processor with 500 merchants and 20000 transactions. "
    "The dispute rate is 1.5%.",
    seed=11,
)
```

### What does not, measured

These are real results from the current parser, not cautions in principle.

- **An entity can be dropped silently.** `"800 customers, 1200 subscriptions and
  5000 invoices"` produces `customers` and `subscriptions` only. No warning, no
  invoices table.
- **A relative clause can become a table.** `"...where 12% of admissions are
  readmissions within 30 days"` produces a table named `are_readmissions`.
  Splitting the rate into its own sentence avoids it.
- **Row counts drift when a curve is in the same sentence.** Adding "where
  revenue grows from X to Y" to a sentence that also declares counts can leave a
  table at the default row count instead of the one you asked for.

So: always check what you got before you trust it.

```python
tables = misata.generate("...", seed=11)
print({name: (len(df), list(df.columns)) for name, df in tables.items()})
```

If a table is missing or a count is wrong, move to a dict schema. The plain
English path is a draft; the schema is the specification. Sections 1 and 2 above
exist because that is the honest split.

The [canvas at misata.studio/try](https://misata.studio/try) shows the parsed
schema visually before you generate, which is the fastest way to catch a
misreading.

---

## Next

- [Declaration reference](reference/declarations.md), every property you can state
- [Quick start](quickstart.md)
- [Try it without installing](https://misata.studio/try)
- [Ready-made datasets](https://misata.studio/datasets)
- [What Misata does not do well yet](https://misata.studio/limitations)
