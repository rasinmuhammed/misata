# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.9.x   | ✓         |
| < 0.9   | ✗         |

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email **hello@misata.studio** with the subject line `[SECURITY] Misata – <short description>`.

Include:
- a description of the vulnerability and its potential impact
- steps to reproduce, or a minimal proof of concept
- the Misata and Python versions you tested against

You will receive an acknowledgement within **72 hours**. A confirmed issue is fixed within **14 days** when critical and **30 days** otherwise. You are welcome to request credit in the release notes.

## Threat model

Misata runs on your machine, as you, with your permissions. It reads schemas,
generates rows and writes files or database tables. The guarantees below are
the ones it makes about what it will and will not do on your behalf; each is
covered by a test in `tests/test_sandbox_security.py`,
`tests/test_mcp_workspace.py` or `tests/test_hardening.py`.

### Nothing leaves the machine

Generation, auditing, verification and every export are offline. No default
code path opens a network connection; a test runs generation with sockets
disabled. Three opt-in paths use the network, and only when you ask for them:

- `misata capsule` with a Wikidata source fetches vocabulary from Wikimedia
  over `https` only.
- An LLM-designed schema (`misata generate --use-llm`, or
  `misata.LLMSchemaGenerator`, with the `[llm]` extra) sends your story to
  the provider you configured. Rows are never sent; the model designs the
  schema and Misata generates the data. `misata.generate()` uses the
  rule-based parser and needs no key.
- `--smart` value generation (off by default) asks Groq for column value
  pools when `GROQ_API_KEY` is set, sending table and column names.
  `--smart-no-llm` keeps it offline with curated pools.

### Writing to databases

- `misata seed` writes inside a single transaction. It never truncates unless
  you pass `--truncate`, and it never uses `CASCADE`, so tables outside your
  schema are untouched.
- Every table and column name interpolated into SQL is escaped
  (`misata.sqlutil.quote_ident`), including names read back from a database.

### Sandboxes

- A sandbox is a SQLite file that Misata created, marked in the file header
  (`PRAGMA application_id`). `create_sandbox` replaces a file only if it is
  missing, empty or already a Misata sandbox; any other database is refused
  and left byte-for-byte unchanged.
- `query_sandbox` opens the file read-only at three layers: `mode=ro`,
  `PRAGMA query_only`, and an authorizer that denies every action other than
  reading (which also blocks `ATTACH`, `VACUUM`, state-changing pragmas and
  `load_extension`). Read-only does not depend on how the query is written.

### The MCP server

`misata-mcp` serves tools to a local AI agent. An agent's arguments can be
influenced by text it has read, so the server treats them as untrusted:

- Every path argument (`output_dir`, `dataset_dir`, `db_path`) is resolved,
  symlinks included, and must fall inside an allowed root: the working
  directory and the system temporary directory by default, or exactly the
  directories listed in `MISATA_MCP_ROOTS` when that variable is set. A
  working directory at the filesystem root is never treated as a workspace.
- `seed_database` plans by default and writes only when called with
  `apply=true`; the server's instructions tell the agent to show the plan and
  ask first, and never to choose `truncate` on the user's behalf.
- Errors come back as structured results, never as tracebacks containing
  local paths beyond the one the agent supplied.

### Untrusted schemas and documents

- YAML is loaded with `yaml.safe_load`. Formulas are evaluated with
  `simpleeval` against an allow-list of functions, never with `eval`.
- Custom generators (`@misata.generator`, `--plugin`) are code you choose to
  import, and run with your permissions, like any Python import.
- HTML documents escape every interpolated value; Markdown and text documents
  are written verbatim.

### What Misata does not claim

- **`mimic` output is not anonymous.** It is fitted to real rows and can
  reproduce rare values. Do not describe it as privacy-safe.
- Generated data contains no real person's information because no real data
  goes in. That is a property of declared generation, not of `mimic`.

## Out of scope

Issues that require physical access to the machine running Misata, and issues
that only affect the statistical properties of generated data.

## Disclosure policy

We follow coordinated disclosure. Please give us reasonable time to release a
fix before publishing. We credit reporters by name, or anonymously if you
prefer, in the changelog.
