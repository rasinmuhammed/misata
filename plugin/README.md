# Misata

Misata makes realistic multi-table test data whose foreign keys resolve, whose
dates run in order and whose stated totals and rates come out exact. Every
dataset is checked before it is handed over, and the check comes with it as a
certificate. Use it for seed data, fixtures, demo databases and sample data for
a dashboard or a course.

## What is in the plugin

- **The `misata` skill.** It teaches Claude which route fits the request
  (a sentence, a schema, an existing database, a dbt or Prisma project), what is
  worth declaring, and when to show a contradiction instead of guessing. Its
  local commands need `pip install misata` (MIT licensed, runs offline).
- **The hosted Misata server** at `https://api.misata.studio/mcp`. It plans a
  dataset, builds it, answers read-only SQL over it, and exports it as CSV,
  Parquet, SQL, DuckDB, SQLite, dbt and other formats. It also lists ready-made
  free sample databases.

## What it sends, and where

- The skill runs the local `misata` command on your machine. Nothing leaves it.
- The hosted server receives the request or schema Claude sends it, builds the
  dataset on Misata's servers and keeps the files for about two hours so they
  can be queried and downloaded. Nothing from your conversation is read beyond
  what a tool call carries, and the server never asks for or holds a database
  credential: seeding a real database happens through your own connection.
- Building from a schema works without an account. A plain-English request needs
  a model, so it asks you to sign in with a free Misata Studio account (OAuth) or
  to use a model key you have saved in Studio.

Privacy policy: https://www.misata.studio/privacy

## Install

In Claude Code:

```
/plugin marketplace add rasinmuhammed/misata
/plugin install misata@misata
```

The skill alone works with any agent that reads `SKILL.md`:

```bash
mkdir -p ~/.claude/skills
cp -r plugin/skills/misata ~/.claude/skills/
```

## Keeping it true

The skill names commands and declaration keys, so it can drift into describing a
tool that no longer exists. `tests/test_skill.py` checks every command and every
top-level key it mentions against the running package, and checks this folder
against the directory's rules (manifest, license, https servers only).

That test was written after the first draft, which claimed `misata generate
--from-project` (the flag lives on `dbt-seed`) and a top-level `rollups:` key
(roll-ups are inferred from the shape, never declared). Both read perfectly
plausibly. Neither existed.
