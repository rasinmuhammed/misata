# Misata certificate predicate, v1

Predicate type: `https://misata.studio/attestation/certificate/v1`

A Misata certificate states that a set of files holds the invariants a
declarative schema implies, and records each check so that anyone can rerun
it. It is the predicate of an
[in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md)
whose subjects are those files.

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
| `id` | Stable, readable identifier built from the declaration (`table.column.period.kind`). Unique within the predicate. |
| `kind` | The declaration it comes from: `outcome_curve_period`, `outcome_curve_total`, `outcome_curve_argmax`, `plan_row_count`, `rate_curve_anchor`, `group_share_period`, `group_share_total`, `ledger_entry_balance`, `ledger_trial_balance`, `waterfall_net`, `waterfall_component`, `waterfall_balance`, `fk_integrity` or `unique`. |
| `table` | The table the check is about; a relationship belongs to its child table. |
| `sql` | DuckDB SQL that returns one value. Table names are the subject files' stems. |
| `expected` | The declared answer as a string. |
| `observed` | The answer the SQL returned, written the same way. |
| `valueType` | `decimal`, `integer`, `boolean` or `string`. Decimals are compared at the number of places `expected` has. |
| `comparator` | `eq`: `observed` must equal `expected` as a string. |
| `passed` | Whether it held. |

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

Misata ships this procedure as `verify.py` beside every attestation; it
needs only Python and `duckdb`.

## Versioning

Fields may be added within v1. A change to the meaning of an existing field
gets a new predicate type.
