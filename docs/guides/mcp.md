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

The server exposes six tools:

| Tool | Purpose |
|:--|:--|
| `generate_from_schema` | **Primary.** The agent designs a schema dict (any domain); Misata generates CSVs and returns an integrity proof: per-relationship orphan counts, exact roll-ups, seeded reproducibility |
| `generate_dataset` | Story-based generation: Misata's own parser designs the schema from one sentence |
| `list_domains` | List all 18 built-in domains with a sample story for each |
| `preview_story` | Detect domain, scale, locale, and table layout: zero rows generated |
| `inspect_schema` | Return the full schema (tables, columns, FK relationships) as structured JSON |
| `validate_yaml` | Two-layer validation (structural JSON Schema + semantic coherence checks) of a `misata.yaml` |

The division of labour is deliberate: agents are good at deciding that a veterinary clinic needs a `species` column; Misata is good at guaranteeing the math, FK integrity, exact aggregates, declared distributions, byte-identical reruns under a seed. `generate_from_schema`'s tool description teaches the agent the full schema-dict language (per-table `__rows__`, distributions, formulas with `@parent.column` references, exact roll-ups, pattern codes), so any MCP-capable model can drive everything Misata's engine supports.

Both generation tools write CSVs to a temp directory by default. The agent gets back file paths and a small preview, it never has to dump millions of rows into the chat context.

---

## Example prompts

Once configured, try these in your assistant:

> "Generate a fintech fraud dataset with 10k customers and a 2% fraud rate."

> "Show me what tables and columns Misata would produce for an HR system with 200 employees in Germany."

> "I'm building a BI dashboard. Generate SaaS subscription data with MRR growing from $50k in January to $200k in December, with a Q3 slump and a Black Friday spike."

> "Validate this misata.yaml before I commit it." *(paste YAML inline)*

> "List all available Misata domains and pick the best one for an e-learning platform."

The assistant picks the right tool, calls Misata, and returns a concise summary with the file paths or validation result.

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

**Output:** the same file/preview envelope as `generate_dataset`, plus:
```json
{
  "integrity": {
    "verified": true,
    "relationships": [
      {"relationship": "orders.customer_id → customers.id", "intact": true, "orphans": 0}
    ]
  }
}
```

The agent can tell you: *"Generated and verified: 0 orphaned foreign keys, and every customer's `lifetime_value` reconciles exactly with their orders."*

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

---

### `validate_yaml`

Two-layer validation of a `misata.yaml` string: structural (JSON Schema) then semantic (FK consistency, formula references, distribution params).

**Input:**
```json
{
  "yaml_content": "tables:\n  - name: users\n    rows: 1000\n    columns:\n..."
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

All six tools return a consistent `{"ok": true/false, ...}` envelope. When something goes wrong the agent receives a structured error instead of a Python traceback, and can take corrective action:

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

The server is a thin protocol shim over Misata's existing public API. Each tool maps to one library function:

```text
list_domains     →  StoryParser.DOMAIN_KEYWORDS
preview_story    →  misata.preview()
inspect_schema   →  misata.parse()
generate_dataset →  misata.generate() + DataFrame.to_csv()
validate_yaml    →  misata.json_schema() + misata.validate_schema()
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

`generate_dataset` writes files to disk. By default it uses a system temp directory that only the current user can read. If you pass a custom `output_dir`, ensure it is an appropriate path, the agent will not write outside the directory you specify.
