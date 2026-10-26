---
title: "Attest a Synthetic Dataset: in-toto Attestation and verify.py"
description: "Check written CSV, Parquet or DuckDB files against every invariant their schema declares, pin each file by SHA-256 in an in-toto Statement, and hand over a verify.py that reruns the proof with DuckDB."
---

# Attest a dataset

An attestation is a signed-ready record that a dataset holds what its schema
declared. Misata writes it in the format software supply chains already use,
an [in-toto Statement](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md),
so the tools that verify build artifacts verify data the same way.

```bash
misata generate -c misata.yaml -o out --attest
# or, for files that already exist
misata attest out --schema misata.yaml
```

```python
import misata

tables = misata.generate_from_schema(schema)
# ... write the tables to out/ as Parquet or CSV ...
result = misata.attest("out", schema)
assert result.passed, result.summary()
```

```diagram
# Generate, attest, verify: who runs what
 you                                   anyone with the folder
 ───                                   ──────────────────────
 misata.yaml / schema.sql
      │  derive invariants (before reading a row)
      ▼
 misata generate -o out ──▶ out/*.parquet, *.csv, data.duckdb
      │
      ▼
 --attest / misata attest
      │  DuckDB runs every invariant's SQL on the files
      │  each file pinned by SHA-256
      ▼
 out/attestation.intoto.json ─────────▶ python out/verify.py
 out/attestation.dsse.json                 1. sha256 of every file
 out/verify.py                             2. rerun every invariant
      │                                    exit 0: PASSED
      ▼                                    exit 1: a byte or a rule changed
 cosign / actions/attest (optional) ──▶ gh attestation verify
```

## What it checks

Every invariant comes from the schema, never from the data. Misata derives
them before reading a row, then DuckDB runs each one against the files on
disk.

| Declaration | Invariant |
|---|---|
| `outcome_curves` | each period's total, the curve's grand total, its peak period, and the planned row count per period |
| `rate_curves` | each anchor's matching count is within one row of rate × rows |
| `group_shares` | each group's total in every period and over the whole table |
| `balanced_ledger` | every journal entry and the trial balance net to zero |
| `waterfalls` | opening plus movements equals closing, per component |
| relationships | no child row points at a missing parent |
| a relationship's `min_children` | no parent has fewer children than declared |
| a relationship's `partition_by` | every child shares its parent's partition columns |
| `unique` columns | no value appears twice |
| `inequality` and `col_range` constraints, including a DDL `CHECK (due_on > issued_on)` | no row breaks the rule |
| a declared string domain: `choices`, or a DDL `CHECK (plan IN (...))` | no value falls outside it |
| a declared NOT NULL: DDL `NOT NULL`, `nullable: false`, a primary key | no value is null |
| `dag_edges` | no cycle outside a declared motif case |
| `graph_motifs` | each motif shape has exactly its planned edges, and exactly the flagged ones are flagged |
| `lifecycles` | every row's timestamps are one of its state's routes, in order and after the start; each state's count is within one row of its weight |

Row rules are left out on a column that `typos`, `outliers`, `missingness`
or `late_arrivals` targets, and everywhere when `noise` injects nulls,
outliers or typos, because those declarations break the rule on purpose.

The files can be CSV, JSON Lines or Parquet (one file per table, or a
folder of parts, Hive-partitioned or not), or a single `data.duckdb`: every
layout `misata generate --format` writes. Each file is a subject, annotated
with the tables it holds.

These are the same derivations `misata evalpack` uses, so an attestation
and an evalpack built from one schema cannot disagree. Every evalpack now
carries an attestation too, with its checker named `verify_attestation.py`.

Expected and observed values are written as decimal strings at a fixed
precision, so a sum that floats to `209999.99999999997` reads `210000.00`
and equality never depends on how a number was printed.

## What it writes

| File | Contents |
|---|---|
| `attestation.intoto.json` | the in-toto Statement: each file pinned by SHA-256, and the certificate predicate |
| `attestation.dsse.json` | the same bytes in an unsigned [DSSE envelope](https://github.com/secure-systems-lab/dsse), ready for a signer |
| `verify.py` | a standalone checker that needs only Python and `duckdb` |

Anyone with the folder can rerun the whole proof:

```bash
python out/verify.py
# ok    13 file(s) match their attested sha256
# ok    103 of 103 invariant(s) hold
```

It exits 0 when every digest matches and every invariant holds, and 1
otherwise. Change one byte of one file and both the digest and the
invariants that byte touched report it.

`misata attest` exits 0 when the result is `PASSED`, 1 when an invariant does
not hold, and 2 when the folder cannot be attested (a table has no file, or
the schema declares nothing checkable).

## Sign it

Misata does not sign anything itself. The Statement is the standard input of
the signing tools, so use the one your organisation already trusts.

With [cosign](https://docs.sigstore.dev/cosign/verifying/attestation/):

```bash
cosign attest-blob \
  --statement out/attestation.intoto.json \
  --bundle out/attestation.sigstore.json \
  out/orders.parquet
```

In GitHub Actions, with
[`actions/attest`](https://github.com/actions/attest), which signs through
Sigstore with the workflow's own identity and stores the attestation on
the repository:

```yaml
jobs:
  fixtures:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
      attestations: write
      artifact-metadata: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install "misata[evalpack]"
      - run: misata generate -c misata.yaml -o out --attest
      - run: jq .predicate out/attestation.intoto.json > out/predicate.json
      - uses: actions/attest@v4
        with:
          subject-path: "out/*.csv"
          predicate-type: https://misata.studio/attestation/certificate/v1
          predicate-path: out/predicate.json
```

Anyone can then check a file against it:

```bash
gh attestation verify out/orders.csv --repo OWNER/REPO \
  --predicate-type https://misata.studio/attestation/certificate/v1
```

## Export the checks

The same invariants in the formats data platforms already read:

```bash
misata attest out --schema misata.yaml --export odcs --export openlineage
```

- **`datacontract.odcs.yaml`** is an
  [Open Data Contract Standard](https://bitol-io.github.io/open-data-contract-standard/)
  v3.2.0 contract with one `type: sql` quality rule per invariant and a
  `local` server pointing at the files, so
  [`datacontract test`](https://cli.datacontract.com/) runs every check with
  DuckDB and fails when one breaks.
- **`openlineage.json`** is an [OpenLineage](https://openlineage.io/) `RunEvent`.
  Each input carries the standard `dataQualityAssertions` facet (one
  assertion per invariant) and a `misata_certificate` facet with the expected
  and observed values, the spec digest and the seed. Send it to Marquez or
  any OpenLineage backend.

## In an agent

The MCP server's `attest_dataset` tool takes the folder and the same schema
dict that `generate_from_schema` took, writes the three files, and returns
the result with any failing invariants. Report `result` to the user:
`PASSED` means every declared property holds in the files on disk.

## Limits

- An attestation proves the files match the declarations. It says nothing
  about how realistic the rows are; that is
  [`misata.realism_report`](../validate.md).
- `verifiedAt` changes on every run, so two attestations of the same files
  differ in that one field. The subjects and invariants do not.
- The predicate is specified at
  [`https://misata.studio/attestation/certificate/v1`](../attestation/certificate-v1.md).

## See it end to end

- [Seed a dev database from its DDL](../usecases/seed-a-dev-database.md):
  22 invariants from three `CREATE TABLE` statements.
- [A warehouse before the product has users](../usecases/warehouse-before-users.md):
  80 invariants over partitioned Parquet.
- [Fraud and AML data with labelled truth](../usecases/fraud-aml.md): an
  acyclic check written as a recursive DuckDB query.
- [Publish to Hugging Face](publish.md) re-verifies an attested folder
  before it uploads anything.
