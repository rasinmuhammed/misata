---
title: "Misata Certificate Predicate v1, an in-toto Predicate for Data"
description: "Specification of https://misata.studio/attestation/certificate/v1: the in-toto predicate that records every declared invariant of a dataset as DuckDB SQL with its expected and observed values."
---

# Misata certificate predicate, v1

Predicate type: `https://misata.studio/attestation/certificate/v1`

A Misata certificate states that a set of files holds the invariants a
declarative schema implies, and records each check so that anyone can rerun
it. It is the predicate of an
[in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md)
whose subjects are those files.

```diagram
# Where the predicate sits in an attestation
in-toto Statement v1  (attestation.intoto.json)
├── subject[]          one entry per file: name, sha256, annotations.tables
├── predicateType      https://misata.studio/attestation/certificate/v1
└── predicate
    ├── result         PASSED only when every invariant passed
    ├── spec           the schema file and its sha256
    ├── producer       pkg:pypi/misata@<version>
    ├── seed · verifiedAt · engine (duckdb + version)
    └── invariants[]   id · kind · table · sql · expected · observed
                       valueType · comparator · tolerance? · passed

attestation.dsse.json  the same Statement in an unsigned DSSE envelope
verify.py              reruns every check with Python and duckdb only
```

## Example

```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {"name": "customers.csv", "digest": {"sha256": "4b1d..."},
     "annotations": {"tables": ["customers"]}},
    {"name": "orders/status=paid/part-00000.parquet", "digest": {"sha256": "9e07..."},
     "annotations": {"tables": ["orders"]}}
  ],
  "predicateType": "https://misata.studio/attestation/certificate/v1",
  "predicate": {
    "result": "PASSED",
    "spec": {"name": "misata.yaml", "digest": {"sha256": "c3a0..."}},
    "producer": {"name": "misata", "uri": "pkg:pypi/misata@0.9.8"},
    "seed": 42,
    "verifiedAt": "2026-11-20T10:00:00Z",
    "engine": {"name": "duckdb", "version": "1.4.1"},
    "invariants": [
      {
        "id": "orders.amount.month:3.outcome_curve_period",
        "kind": "outcome_curve_period",
        "table": "orders",
        "sql": "SELECT ROUND(SUM(\"amount\"), 2) FROM \"orders\" WHERE ...",
        "expected": "31000.00",
        "observed": "31000.00",
        "valueType": "decimal",
        "comparator": "eq",
        "passed": true
      }
    ]
  }
}
```

## Fields

| Field | Type | Meaning |
|---|---|---|
| `result` | `"PASSED"` or `"FAILED"` | `PASSED` only when every invariant passed. A consumer that ignores the predicate never treats missing evidence as a pass. |
| `spec.name` | string | The schema file, or `schema.json` when the schema was built in code. |
| `spec.digest.sha256` | hex | SHA-256 of the schema file's bytes, or of the schema's canonical JSON (sorted keys, no whitespace). |
| `producer.uri` | purl | The Misata release that derived and checked the invariants. |
| `seed` | integer or null | The generation seed recorded in the schema. |
| `verifiedAt` | RFC 3339 UTC | When the invariants were run against the subjects. |
| `engine` | object | The SQL engine that ran them, with its version. |
| `invariants[]` | array | One entry per check, in derivation order. |

Each invariant:

| Field | Meaning |
|---|---|
| `id` | Stable, readable identifier built from the declaration (`table.column.period.kind`). Unique within the predicate: a second invariant that would share an id gets `#2`, `#3` and so on. |
| `kind` | The declaration it comes from. See the table of kinds below. |
| `table` | The table the check is about; a relationship belongs to its child table. |
| `sql` | DuckDB SQL that returns one value. Table names are the subject files' stems. |
| `expected` | The declared answer as a string. |
| `observed` | The answer the SQL returned, written the same way. |
| `valueType` | `decimal`, `integer`, `boolean` or `string`. Decimals are compared at the number of places `expected` has. |
| `comparator` | `eq`: `observed` must equal `expected` as a string. `within_tolerance`: `abs(observed - expected) <= tolerance * abs(expected)`, in exact decimals. |
| `tolerance` | Present only with `within_tolerance`: the relative tolerance as a decimal string (`"0.005"` for 0.5%). |
| `passed` | Whether it held. |

### Kinds

| `kind` | Declared by | Checks |
|---|---|---|
| `outcome_curve_period` | `outcome_curves` | one period's total |
| `outcome_curve_total` | `outcome_curves` | the curve's grand total |
| `outcome_curve_argmax` | `outcome_curves` | which period is the peak |
| `plan_row_count` | `outcome_curves` | the planned number of rows in a period |
| `rate_curve_anchor` | `rate_curves` | the matching count is within one row of rate times rows (`valueType` boolean) |
| `group_share_period`, `group_share_total` | `group_shares` | a group's total in a period, and over the whole table |
| `ledger_entry_balance`, `ledger_trial_balance` | `balanced_ledger` | each journal entry, and the trial balance, nets to zero |
| `waterfall_net`, `waterfall_component`, `waterfall_balance` | `waterfalls` | opening plus movements equals closing |
| `fk_integrity` | relationships | no child row points at a missing parent |
| `min_children` | a relationship's `min_children` | parents with fewer children than declared, which must be 0 |
| `partition_by` | a relationship's `partition_by` | children whose partition columns differ from their parent's, which must be 0 |
| `unique` | `unique` columns, primary keys | no value appears twice |
| `inequality`, `col_range` | row constraints, a DDL `CHECK (a > b)` | rows breaking the rule, which must be 0 |
| `domain` | `choices`, a DDL `CHECK (x IN (...))` | values outside the declared set, which must be 0 |
| `not_null` | `nullable: false`, DDL `NOT NULL` | nulls, which must be 0 |
| `acyclic` | `dag_edges` | nodes on or below a cycle outside a declared motif case, which must be 0 |
| `motif_edges`, `flagged_edges` | `graph_motifs` | edges of each motif shape, and flagged edges |
| `lifecycle_history` | `lifecycles` | rows whose timestamps are not their state's path from `initial`, set in order and not before `start_column`, with every other timestamp null, which must be 0 |
| `lifecycle_mix` | `lifecycles` | states whose row count is a full row or more from its weighted share of the table, which must be 0 |
| `solved_target` | `misata solve` with a SQL pipeline | the pipeline's metric for a period, with `within_tolerance` |

A lifecycle's state column carries no `domain` invariant: its domain is the
lifecycle's states, which `lifecycle_history` checks row by row.

Row rules are left out on a column that a dirt declaration (`typos`,
`outliers`, `missingness`, `late_arrivals`, or `noise` that injects nulls,
outliers or typos) breaks on purpose. A consumer must treat an unknown
`kind` as opaque: the SQL, the expected value and the comparator are enough
to check it.

## Verifying

1. Check each subject's SHA-256 against the file.
2. Build one DuckDB view per table. A subject's `annotations.tables` names
   the tables it holds; a subject without annotations holds one table, named
   by its file stem. A table held by several Parquet parts is read as one
   (`read_parquet` with `union_by_name`), with Hive partition columns taken
   from `column=value` folders. A `.duckdb` subject is attached read-only
   and each of its tables becomes a view.
3. Run each invariant's `sql`, write the value as `valueType` at the
   precision of `expected`, and compare with `comparator`.
4. The predicate passes only when every subject's digest matches and every
   invariant passes.

Misata ships this procedure as `verify.py` beside every attestation; it
needs only Python and `duckdb`.

## Signing

The predicate is unsigned. The Statement is the standard input of
`cosign attest-blob` and GitHub's `actions/attest`; see
[Attest a dataset](../guides/attest.md#sign-it). To verify a GitHub
attestation of a file:

```bash
gh attestation verify out/orders.csv --repo OWNER/REPO \
  --predicate-type https://misata.studio/attestation/certificate/v1
```

## Versioning

Fields may be added within v1. A change to the meaning of an existing field
gets a new predicate type.
