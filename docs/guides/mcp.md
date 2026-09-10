---
title: MCP Server, Use Misata from Claude, Cursor, and AI Coding Assistants
description: Misata ships a built-in Model Context Protocol (MCP) server. Wire it into Claude Desktop, Cursor, Windsurf, or any MCP-compatible assistant and generate realistic synthetic data from natural language descriptions.
---

# MCP Server

Misata ships a built-in [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server. Once wired in, AI assistants, Claude Desktop, Cursor, Windsurf, Zed, Continue, can generate realistic synthetic datasets on your behalf without you writing a single line of Python.

> **TL;DR**: type *"generate a fintech fraud dataset with 10k customers"* in Claude, and Claude calls Misata, writes the CSVs to disk, and shows you a preview.

---

## Install

```bash
pip install "misata[mcp]"
```

This pulls in the [`mcp`](https://pypi.org/project/mcp/) Python SDK and `jsonschema` for the YAML validation tool. The server binary is registered as a console script:

```bash
which misata-mcp   # → /path/to/venv/bin/misata-mcp
```

---

## Wire it into your AI assistant

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, or `%APPDATA%\Claude\claude_desktop_config.json` on Windows:

```json
{
  "mcpServers": {
    "misata": {
      "command": "misata-mcp"
    }
  }
}
```

Restart Claude Desktop. Misata will appear in the tools list, look for the plug icon in the input area.

### Cursor

Open **Settings → MCP** (or `.cursor/mcp.json`) and add:

```json
{
  "misata": {
    "command": "misata-mcp"
  }
}
```

### Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "misata": {
      "command": "misata-mcp"
    }
  }
}
```

### Zed / Continue / other editors

The command is always `misata-mcp`. Refer to your editor's MCP documentation for the exact config file path. The pattern is identical across all clients.

---

## What the agent can do

The server exposes nine tools:

| Tool | Purpose |
|:--|:--|
| `generate_from_schema` | **Primary.** The agent designs a schema dict (any domain); Misata generates CSVs and returns an integrity proof (per-relationship orphan counts, exact roll-ups, seeded reproducibility), a coherence score, and — when a `__domain__` is declared — a domain-validation pass |
| `generate_dataset` | Story-based generation: Misata's own parser designs the schema from one sentence. Also returns a coherence score |
| `list_domains` | List all 18 built-in domains with a sample story for each |
| `preview_story` | Detect domain, scale, locale, and table layout: zero rows generated |
| `inspect_schema` | Return the full schema (tables, columns, FK relationships) as structured JSON |
| `audit_dataset` | Run the coherence audit on any folder of CSVs: backwards timestamps, totals that don't reconcile, near-constant columns, scored 0-100 |
| `validate_domain` | Flag physiologically or financially impossible values in a folder of CSVs (`clinical`, `financial`) |
| `validate_yaml` | Two-layer validation (structural JSON Schema + semantic coherence checks) of a `misata.yaml` |
| `seed_database` | Insert generated rows into a real Postgres or SQLite database. Plans by default; writes only on `apply=true` |

The division of labour is deliberate: agents are good at deciding that a veterinary clinic needs a `species` column; Misata is good at guaranteeing the math, FK integrity, exact aggregates, declared distributions, byte-identical reruns under a seed. `generate_from_schema`'s tool description teaches the agent the full schema-dict language — per-table `__rows__`, the distribution set, formulas with `@parent.column` references, exact roll-ups, pattern codes, correlations, ICC cluster effects, state machines, time-series autocorrelation, plus the schema-level declarations (`__outcome_curves__`, `__group_shares__`, `__waterfalls__`, `__stock_flows__`, `__lifecycles__`, and the `__duplicates__` / `__typos__` / `__outliers__` trio) — so any MCP-capable model can drive most of what the engine supports without reading these docs first.

Both generation tools write CSVs to a temp directory by default. The agent gets back file paths and a small preview, it never has to dump millions of rows into the chat context.

---

## Prompts to try

Paste any of these into your assistant. Each one is chosen to push a
different part of the engine.

**One sentence, let the parser design it**

> "Generate a fintech fraud dataset with 10k customers and a 2% fraud rate."

> "Give me an HR system for 200 employees in Germany, with a payroll table."

> "Build a food delivery dataset: 300 restaurants, 2k couriers, 40k orders over the last quarter."

**Declare the outcome, not the rows**

> "Generate SaaS subscription data where MRR grows from $50k in January to $200k in December, with a dip in Q3 and a spike in November. Starter is 20% of revenue, Pro 50%, Enterprise 30%."

> "Ecommerce orders for 2026 where Q4 revenue lands at exactly $2.4M and the refund rate climbs from 1% to 4% after a pricing change in September."

> "A logistics dataset where on-time delivery is 87% overall, breaching the SLA in Q3, and worst in the Nordics region."

**Ask for structure that survives a second look**

> "Design a clinical trial: 400 patients across 12 sites, three arms, HbA1c measured at 6 visits each. The arms need different treatment effects, measurements within a patient should be autocorrelated, and sites should show a random-intercept effect. Then audit it."

> "Generate an order-fulfilment dataset where every order moves through placed → paid → shipped → delivered, with a small fraction refunded, and status can never skip a step."

**Prove data you already have**

> "Audit the CSVs in ./seed_data and tell me the coherence score and the worst three findings."

> "Validate the dataset in ./trial_export against clinical domain rules."

**Fill a real database**

> "Plan a seed of my dev database at postgresql://localhost/myapp_dev, then show me the plan before writing anything."

**Dirty data on purpose**

> "Generate a contacts table with exactly 60 duplicate rows and 120 typo'd city values, so I can test a cleaning pipeline against a known count."

---

## Getting the best results

**Let the agent design the schema, you describe the outcome.** The single
biggest difference between a mediocre result and a good one is whether the
request states *what has to be true of the data* — a period total, a rate, a
share, a correlation — rather than a min/max on a column. "Revenue grows to
$200k by December" is an `__outcome_curves__` declaration the engine hits
exactly. "Revenue between $0 and $200k" is not.

**Read the coherence score before you use the data.** Every
`generate_from_schema` and `generate_dataset` response now carries a
`coherence` block with a score from 0 to 100 and its findings. A score in the
90s means the data holds up. A lower score almost always means the *schema* is
missing realism structure — correlations between columns that co-vary, per-group
`profiles`, `time_series` for longitudinal data, a `__state_machine__` for an
entity that moves through stages. Ask the agent to add that and regenerate,
rather than accepting the first pass.

**Use the right tool for the shape of the request:**

| The request is… | Tool |
|:--|:--|
| one sentence, common domain | `generate_dataset` |
| specific tables, columns, or declared outcomes | `generate_from_schema` |
| "will this schema even work?" before a big run | `validate_yaml` |
| checking data that already exists | `audit_dataset`, `validate_domain` |
| loading a real dev database | `seed_database` (plan first) |

**Set a seed if you want the run to be repeatable.** The same schema and seed
produce byte-identical output on any machine. Omit it and each run is fresh.

**For anything touching a real database, expect two calls.** `seed_database`
plans by default and writes nothing; it only inserts after a second call with
`apply=true`, and it refuses to touch a table that already has rows unless you
pick `truncate` (destructive) or `append`.

---

## A full worked flow

What a good agent session looks like end to end:

1. **You:** "I need demo data for a Series B logistics company selling into the Nordics. On-time delivery should be 87% and degrading in Q3."
2. Agent calls `generate_from_schema` with a warehouses / shipments / carriers schema and an `__outcome_curves__` declaration for the on-time rate.
3. Response comes back: files written, `integrity.verified: true`, `coherence.score: 78`, with a finding that `carrier_cost` is near-constant.
4. Agent adds a `lognormal` distribution and a correlation between `distance_km` and `carrier_cost`, regenerates. `coherence.score: 94`.
5. Agent calls `audit_dataset` on the output to confirm, then reports: *"Generated and verified. On-time delivery is 87.0% overall, 81% in Q3. Every foreign key resolves. Coherence 94/100."*

---

## Tool reference

### `list_domains`

Returns a list of all 18 domain objects, each with `name`, `keywords`, and `sample_story`.

**Input:** none

**Output:**
```json
{
  "ok": true,
  "domains": [
    {
      "name": "saas",
      "keywords": ["saas", "subscription", "mrr", "arr", "churn"],
      "sample_story": "A SaaS startup with 5k users, 20% monthly churn, MRR $50k"
    },
    ...
  ]
}
```

---

### `preview_story`

Parses a story and returns domain detection, scale, locale, and table layout, no rows generated.

**Input:**
```json
{
  "story": "A fintech startup with 10k customers, 3% fraud rate",
  "rows": 10000
}
```

**Output:**
```json
{
  "ok": true,
  "domain": "fintech",
  "domain_confidence": "high",
  "matched_keywords": ["fintech", "fraud"],
  "scale_params": {"users": 10000},
  "locale": null,
  "table_preview": [
    {"name": "customers",     "rows": 10000, "columns": 9},
    {"name": "accounts",      "rows": 10000, "columns": 6},
    {"name": "transactions",  "rows": 80000, "columns": 8}
  ],
  "total_rows": 100000,
  "temporal_events": [],
  "warnings": []
}
```

---

### `inspect_schema`

Returns the full parsed schema as structured data, including table names, column definitions, and FK relationships.

**Input:**
```json
{
  "story": "A SaaS company with 5k users",
  "rows": 5000
}
```

**Output:**
```json
{
  "ok": true,
  "tables": [
    {
      "name": "users",
      "rows": 5000,
      "columns": [
        {"name": "user_id",    "type": "int",         "unique": true},
        {"name": "email",      "type": "email"},
        {"name": "plan",       "type": "categorical", "values": ["free", "pro", "enterprise"]},
        {"name": "created_at", "type": "datetime"}
      ]
    },
    ...
  ],
  "relationships": [
    {"from": "subscriptions.user_id", "to": "users.user_id"}
  ],
  "outcome_curves": [
    {"table": "subscriptions", "column": "mrr", "curve_points": [...]}
  ]
}
```

---

### `generate_from_schema`

The primary tool: the agent supplies a schema dict it designed itself, Misata generates the data and proves the integrity. Supports per-table row counts, the full distribution set, derived columns (`formula`, including cross-table `@parent.column` references), exact roll-ups, FK declarations, and pattern-based codes.

**Input:**
```json
{
  "schema": {
    "customers": {
      "__rows__": 500,
      "id":             {"type": "integer", "primary_key": true},
      "name":           {"type": "string"},
      "lifetime_value": {"rollup": {"from_table": "orders", "fk": "customer_id",
                                    "agg": "sum", "column": "total"}}
    },
    "orders": {
      "__rows__": 5000,
      "id":          {"type": "integer", "primary_key": true},
      "customer_id": {"type": "integer", "foreign_key": {"table": "customers", "column": "id"}},
      "quantity":    {"type": "integer", "min": 1, "max": 5},
      "unit_price":  {"type": "float", "distribution": "lognormal", "mean": 40, "std": 25},
      "total":       {"formula": "quantity * unit_price"},
      "placed_at":   {"type": "datetime"}
    }
  },
  "seed": 7
}
```

**Output:** the same file/preview envelope as `generate_dataset`, plus an
integrity proof, a coherence score, and — when the schema declares a
`__domain__` — a domain-validation pass:
```json
{
  "integrity": {
    "verified": true,
    "status": "verified",
    "declared": 1,
    "checked": 1,
    "relationships": [
      {"relationship": "orders.customer_id → customers.id", "intact": true, "orphans": 0}
    ]
  },
  "coherence": {
    "available": true,
    "score": 96.0,
    "clean": true,
    "summary": "Coherence: clean — no reader-visible contradictions.",
    "findings": [],
    "findings_truncated": 0
  }
}
```

The agent can tell you: *"Generated and verified: 0 orphaned foreign keys, every
customer's `lifetime_value` reconciles exactly with their orders, and the data
scores 96/100 for coherence with no reader-visible contradictions."*

If the coherence score is low, the `findings` array names what a reader would
catch — a column that is 98% one value, a `total` that does not equal
`quantity * unit_price`, a `shipped_at` before its `ordered_at`. Fix those in
the schema and regenerate.

---

### `generate_dataset`

Generates a full dataset and writes one CSV per table to `output_dir` (defaults to a temp directory).

**Input:**
```json
{
  "story": "Ecommerce store — 5k customers, Black Friday spike, Q1 slump",
  "rows": 5000,
  "seed": 42,
  "output_dir": "/tmp/misata_out"
}
```

**Output:**
```json
{
  "ok": true,
  "output_dir": "/tmp/misata_out",
  "files": [
    {"table": "customers",   "path": "/tmp/misata_out/customers.csv",   "rows": 5000},
    {"table": "products",    "path": "/tmp/misata_out/products.csv",    "rows": 200},
    {"table": "orders",      "path": "/tmp/misata_out/orders.csv",      "rows": 15000},
    {"table": "order_items", "path": "/tmp/misata_out/order_items.csv", "rows": 45000}
  ],
  "preview": {
    "customers": [
      {"customer_id": 1, "email": "alice@example.com", "country": "US", ...},
      ...
    ]
  }
}
```

The agent can tell you: *"Generated 65,200 rows across 4 tables. Files are at `/tmp/misata_out/`. Here's a preview of the customers table…"*

Every `files` entry also carries a `sample` of the first few rows, and the
response carries a `coherence` block identical in shape to
`generate_from_schema`'s.

---

### `audit_dataset`

Runs the coherence audit on a folder of CSVs — one per table — and scores it 0
to 100. Works on anything: a folder Misata just wrote, a folder a person built
by hand, another tool's output.

**Input:**
```json
{ "dataset_dir": "/tmp/misata_out", "top_findings": 20 }
```

**Output:**
```json
{
  "ok": true,
  "score": 71.0,
  "clean": false,
  "summary": "Coherence: 3 findings (1 high, 2 medium).",
  "tables_audited": ["customers", "orders", "order_items"],
  "findings": [
    {"severity": "high", "table": "orders", "column": "shipped_at",
     "finding": "312 rows shipped before they were ordered"},
    {"severity": "medium", "table": "orders", "column": "total",
     "finding": "total does not equal quantity * unit_price for 88 rows"}
  ],
  "findings_truncated": 1
}
```

Checks include: timestamps that run backwards, derived columns that do not
reconcile with their inputs, geographic fields that disagree (city / state /
postcode / country), near-constant columns, filler text, out-of-scale numerics.

---

### `validate_domain`

Checks a folder of CSVs for values that are physiologically or financially
impossible for a stated domain.

**Input:**
```json
{ "dataset_dir": "/tmp/trial_export", "domain": "clinical" }
```

`domain` must be one of `clinical_trial`, `clinical`, `financial`, `fintech` —
an unknown domain is refused, not silently passed.

**Output:**
```json
{
  "ok": true,
  "domain": "clinical",
  "passed": false,
  "summary": "1 error, 2 warnings.",
  "errors": [
    {"table": "visits", "column": "hba1c", "message": "4 values outside 4-14%"}
  ],
  "warnings": [],
  "tables_checked": ["patients", "visits"]
}
```

Built-in ranges — clinical: HbA1c 4-14%, BMI 10-80, systolic BP 60-260, age
0-130, glucose 2-40, cholesterol 1-20, hemoglobin 3-25. Financial: price >= 0,
discount 0-1, rate -1 to 100.

---

### `seed_database`

Fills a live Postgres or SQLite database with data read from its own schema.
**Plans by default** — nothing is written until a second call with `apply=true`.

**Input (plan):**
```json
{ "db_url": "postgresql://localhost/myapp_dev", "rows": 500 }
```

**Output (plan):**
```json
{
  "ok": true,
  "applied": false,
  "insert_order": ["accounts", "users", "invoices"],
  "foreign_keys": 2,
  "tables": [
    {"name": "accounts", "existing_rows": 0, "will_insert": 200},
    {"name": "users",    "existing_rows": 0, "will_insert": 1240},
    {"name": "invoices", "existing_rows": 0, "will_insert": 4800}
  ],
  "note": "Plan only, nothing was written. To write, call again with apply=true."
}
```

Then `{ "db_url": "...", "apply": true }` performs the insert (parents before
children) and queries the database back to confirm every foreign key resolves.
If a target table already has rows, the write is refused unless you pass
`truncate=true` (wipes it, destructive) or `append=true` (keeps it, seeds only
empty tables). Requires the db extra: `pip install "misata[db]"`.

---

### `validate_yaml`

Three-layer validation of a `misata.yaml` string: structural (JSON Schema),
semantic (FK consistency, formula references, distribution params), then
feasibility (declarations that each parse but cannot all hold at once — shares
that sum past 1.0, a period total below the sum of its parts).

**Input:**
```json
{
  "yaml_text": "tables:\n  users:\n    rows: 1000\n    columns:\n      ..."
}
```

**Output (valid):**
```json
{
  "ok": true,
  "valid": true,
  "errors": [],
  "warnings": []
}
```

**Output (invalid):**
```json
{
  "ok": true,
  "valid": false,
  "errors": [
    "tables[0].columns[2]: 'distribution' must be one of: uniform, normal, lognormal, ...",
    "tables[1].columns[0]: formula references column 'gross_pay' which is not defined in this table"
  ],
  "warnings": [
    "tables[0]: no primary key column — consider adding a unique int column"
  ]
}
```

---

## Error handling

All nine tools return a consistent `{"ok": true/false, ...}` envelope. When something goes wrong the agent receives a structured error instead of a Python traceback, and can take corrective action:

```json
{
  "ok": false,
  "error": "ValueError",
  "message": "No domain could be detected from the story.",
  "suggestion": "Name the domain explicitly — e.g. add 'fintech', 'saas', or 'ecommerce' to your story."
}
```

```json
{
  "ok": false,
  "error": "OSError",
  "message": "[Errno 13] Permission denied: '/protected/output'",
  "suggestion": "Check that the output_dir path exists and is writable, or omit it to use a temp directory."
}
```

The agent can read the `suggestion` field and reformulate its next call without surfacing raw Python errors to the user.

---

## How it works

The server is a thin protocol shim over Misata's existing public API. Each tool maps to library functions you could call yourself:

```text
list_domains          →  StoryParser.DOMAIN_KEYWORDS
preview_story          →  misata.preview()
inspect_schema         →  misata.parse()
generate_dataset       →  misata.generate() + coherence_audit() + to_csv()
generate_from_schema   →  misata.from_dict_schema() + generate_from_schema()
                          + verify_integrity() + coherence_audit()
audit_dataset          →  misata.coherence_audit()
validate_domain        →  misata.validate_domain()
validate_yaml          →  json_schema() + validate_schema() + check_feasibility()
seed_database          →  misata.introspect + misata.db.seed_database()
```

Because the MCP server is bundled inside the `misata` package itself, not a separate distribution, the server and library are always in sync. Update Misata, the MCP server updates automatically.

---

## Running standalone / debugging

You don't normally need to run `misata-mcp` directly, your AI assistant launches it as a subprocess via stdio. For debugging:

```bash
misata-mcp
# Runs on stdio; send JSON-RPC requests on stdin, responses on stdout.
```

The easiest way to explore the tools interactively is the [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector misata-mcp
```

This opens a web UI where you can call each tool, inspect inputs and outputs, and iterate on prompts. Useful when writing system prompts that use Misata tools.

---

## Discovery: Smithery

Misata is listed on [Smithery.ai](https://smithery.ai), the MCP server discovery directory. If your AI assistant supports one-click MCP installation via Smithery, you can find Misata there and install it without editing config files manually.

---

## Security note

`generate_dataset` and `generate_from_schema` write CSV files to disk. By
default they use a system temp directory that only the current user can read;
if you pass a custom `output_dir` the agent writes only inside that directory.
`audit_dataset` and `validate_domain` read the CSVs in a directory and write
nothing.

`seed_database` is the only tool that writes to a database. It plans by
default and inserts nothing until a second call with `apply=true`, and it will
not overwrite a table that already contains rows without an explicit
`truncate` or `append`. Point it only at a database you are willing to have
written to.
