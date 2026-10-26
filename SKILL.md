---
name: misata
description: Generate relational test, demo or evaluation data from a declared schema with Misata, where every declaration (foreign keys, unique and CHECK rules, monthly revenue curves, rates, group shares, ledger identities) holds exactly or is refused before generation, then attest the files. Use when a task needs a seeded database, fixtures that load without constraint errors, a demo or BI dataset with believable shapes, or a text-to-SQL eval with known answers, and there is no real data to use.
---

# Misata

Misata turns a schema into data that holds what the schema declares. A
declaration it cannot honour is refused before any row exists, with the
arithmetic and a remedy. Full guidance for agents is in
[AGENTS.md](https://github.com/rasinmuhammed/misata/blob/main/AGENTS.md).

## Install

```bash
pip install misata                 # or run without installing: uvx misata --help
pip install "misata[mcp]"          # the MCP server, misata-mcp
```

## The loop

1. **Write the schema.** From DDL: `misata.from_ddl(ddl)`. From a live
   database: `misata init --db URL`. From scratch: `misata init` writes a
   `misata.yaml` to edit. Always set a seed.
2. **Plan.** `misata explain misata.yaml --json` returns planned rows per
   table, which declaration writes which column, and every conflict. Exit 3
   means the declarations cannot all hold: read `conflicts`, apply each
   `remedy` in the schema, run it again.
3. **Generate.** `misata generate -c misata.yaml -o out --attest --json`.
4. **Report what the attestation says.** `data.attestation.result` is
   `PASSED` only when every declared invariant holds in the files on disk.
   `out/verify.py` lets anyone recheck it with only `duckdb`.

When the numbers that matter come out of a pipeline (net revenue in a dbt
model, a SQL metric) rather than off a column, declare an exact outcome curve
on the column that drives them and run `misata solve -c solve.yaml -o out
--json`. Exit 0 means every period is within tolerance; otherwise
`data.solve.reason` and `message` say why it stopped and what to change.

## Reading results

Every command takes `--json` and prints one envelope on stdout: `ok`,
`code`, `exit_code`, `message`, `conflicts`, `data`, `warnings`. Exit codes:
0 ok, 1 a check failed, 2 bad arguments or unreadable input, 3 the
declarations cannot all hold and nothing was written.

A `ConformanceWarning` in `warnings` means a declaration bent; its message
says which and why. Fix findings in the schema, never by editing rows.

## MCP tools

`explain_schema` before generating, `generate_from_schema` to generate,
`solve_outcome` to hit targets computed by SQL over the data,
`attest_dataset` to prove the output, `check_realism` for the statistical
tells of generated data, `seed_database` to fill a real database (it plans
first; never pass `truncate` without the user's consent).

## Do not claim

- that `mimic()` output is private or anonymous: it is fitted to real rows;
- that the data is indistinguishable from real data;
- byte-identical output across Misata versions (within one version, yes).
