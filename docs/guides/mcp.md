# MCP Server

Misata ships a built-in [Model Context Protocol](https://modelcontextprotocol.io)
server. Once installed, AI assistants — Claude Desktop, Cursor, Windsurf,
Zed, Continue — can generate realistic synthetic data from natural-language
descriptions on the user's behalf.

> **TL;DR**: a developer types *"give me a fintech fraud dataset for testing"*
> in Claude, and Claude calls Misata to generate it.

## Install

```bash
pip install "misata[mcp]"
```

This pulls in the [`mcp`](https://pypi.org/project/mcp/) Python SDK and `jsonschema`
for the YAML validation tool.

## Wire it into your AI assistant

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or the equivalent on your platform:

```json
{
  "mcpServers": {
    "misata": {
      "command": "misata-mcp"
    }
  }
}
```

Restart Claude Desktop. You should see Misata appear in the tools list.

### Cursor / Windsurf / Zed / Continue

Each editor has its own MCP config — usually a JSON or TOML file. The
command is always `misata-mcp` (a console script installed by the `mcp`
extra). Refer to your editor's MCP documentation for the exact file path.

## What the agent can do

The server exposes five tools:

| Tool | Purpose |
|:--|:--|
| `list_domains` | List the 18 built-in domains and a sample story for each |
| `preview_story` | Detect domain, scale, locale, and table preview — no generation |
| `inspect_schema` | Return the full schema (tables, columns, relationships) |
| `generate_dataset` | Generate CSV files on disk and return paths + sample rows |
| `validate_yaml` | Two-layer validation of a `misata.yaml` (structural + semantic) |

`generate_dataset` writes CSVs to a temp directory by default and returns
the paths plus a small preview (5 rows per table). The agent can then read
the CSVs incrementally instead of dumping millions of rows into the chat.

## Example prompts

Once configured, try these in your assistant:

> "Generate a fintech dataset with 1000 customers, payments, and a 2% fraud rate."

> "Show me what tables and columns Misata would produce for an HR system with 200 employees."

> "I'm prototyping a dashboard. Generate sample SaaS subscription data with growth from $50k MRR in January to $200k in December, with a dip in March."

> "Validate this misata.yaml for me before I commit it." *(paste YAML)*

The agent picks the right tool, calls Misata, and shows you the result.

## How it works

The server is a thin protocol shim over Misata's existing public API.
Each MCP tool maps onto one library function:

```text
preview_story  →  misata.preview()
inspect_schema →  misata.parse()
generate_dataset → misata.generate() + DataFrame.to_csv()
validate_yaml  →  misata.json_schema() + misata.validate_schema()
list_domains   →  StoryParser.DOMAIN_KEYWORDS
```

Because it's part of the `misata` package itself (not a separate
distribution), the server and library can never go out of sync. Update
Misata, the MCP server updates with it.

## Running it standalone

You don't normally need to run `misata-mcp` directly — your AI assistant
launches it as a subprocess via stdio. But for debugging:

```bash
misata-mcp
# Server runs on stdio; send JSON-RPC requests on stdin.
```

Real debugging is easier through the [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector misata-mcp
```

This opens a web UI where you can call each tool interactively and see
the responses. Useful when iterating on tool definitions.
