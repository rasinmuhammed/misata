---
title: Ledgers That Reconcile to the Cent
description: Generate a general ledger where every journal entry balances, the trial balance is zero, and the receivables roll-forward ties to declared quarter-end balances across two fiscal years, attested by 52 SQL checks.
---

# Ledgers that reconcile

Finance systems are tested on data that cannot be shown to the testers, or
on random numbers that never balance. Neither exercises the code that
matters: the close, the reconciliation, the report that ties one ledger to
another. Here the books balance by construction and the balances you care
about are declared.

**Who:** finance engineering, audit analytics, ERP and fintech teams.
**Time:** under 2 seconds for 44,440 rows.

## The declaration

```yaml
# misata.yaml
name: general_ledger
seed: 8
tables:
  accounts:
    rows: 40
    columns:
      account_id: {type: int, unique: true, min: 1000, max: 1039}
      account_type: {type: categorical, choices: [asset, liability, equity, revenue, expense], probabilities: [0.3, 0.2, 0.05, 0.15, 0.3]}
  journal_entries:
    rows: 8000
    columns:
      entry_id: {type: int, unique: true, min: 1, max: 8000}
      source: {type: categorical, choices: [billing, payroll, payables, manual], probabilities: [0.45, 0.15, 0.3, 0.1]}
      posted_on: {type: date, start: "2024-01-01", end: "2025-12-31"}
  journal_lines:
    rows: 36000
    columns:
      line_id: {type: int, unique: true, min: 1, max: 36000}
      entry_id: {type: foreign_key, sampling: uniform}
      account_id: {type: foreign_key}
      debit: {type: float, distribution: lognormal, mean: 2400, std: 5200, min: 0.01, max: 400000, decimals: 2}
      credit: {type: float, distribution: lognormal, mean: 2400, std: 5200, min: 0.01, max: 400000, decimals: 2}
    constraints:
      - name: double_entry
        type: balanced_ledger
        group_by: [entry_id]
        debit_column: debit
        credit_column: credit
  receivables_rollforward:
    rows: 400
    columns:
      period: {type: categorical, choices: ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]}
      movement_type: {type: categorical, choices: [invoiced, collected, written_off]}
      amount: {type: float, min: 1, max: 250000, decimals: 2}
relationships:
  - {parent: journal_entries.entry_id, child: journal_lines.entry_id, min_children: 2}
  - accounts.account_id -> journal_lines.account_id
waterfalls:
  - table: receivables_rollforward
    period_column: period
    type_column: movement_type
    amount_column: amount
    starting_value: 1250000
    inflow_shares: {invoiced: 1.0}
    outflow_shares: {collected: 0.96, written_off: 0.04}
    outflow_rate: 0.55
    points:
      - {period: "2024-Q1", ending_value: 1318400.00}
      - {period: "2024-Q2", ending_value: 1402750.50}
      - {period: "2024-Q3", ending_value: 1377210.25}
      - {period: "2024-Q4", ending_value: 1461980.75}
      - {period: "2025-Q1", ending_value: 1512006.10}
      - {period: "2025-Q2", ending_value: 1590044.80}
      - {period: "2025-Q3", ending_value: 1566310.35}
      - {period: "2025-Q4", ending_value: 1648902.40}
```

- `balanced_ledger` makes every line one-sided (a debit or a credit) and
  every journal entry's debits equal its credits to the cent.
- `min_children: 2` gives every entry at least two lines, because a one-line
  entry cannot balance.
- The `waterfalls` declaration is an accounts receivable roll-forward:
  opening balance, plus invoices, minus collections and write-offs, lands on
  the declared closing balance every quarter for two years, with collections
  96% and write-offs 4% of what leaves.

```chart
type: columns
title: Declared receivables at each quarter end
source: `waterfalls` in the misata.yaml above, opening at 1,250,000.00; every quarter closes exactly

| Quarter | Closing balance |
|---|---:|
| 2024-Q1 | 1318400.00 |
| 2024-Q2 | 1402750.50 |
| 2024-Q3 | 1377210.25 |
| 2024-Q4 | 1461980.75 |
| 2025-Q1 | 1512006.10 |
| 2025-Q2 | 1590044.80 |
| 2025-Q3 | 1566310.35 |
| 2025-Q4 | 1648902.40 |
```

## Run it

```bash
misata explain misata.yaml
misata generate -c misata.yaml -o books --attest
```

## The check

```bash
python books/verify.py
```

```text
ok    4 file(s) match their attested sha256
ok    52 of 52 invariant(s) hold
```

| Invariant | Count | What it proves |
|---|---:|---|
| `ledger_entry_balance` | 1 | no journal entry where debits differ from credits |
| `ledger_trial_balance` | 1 | total debits equal total credits: 111,369,276.72 each |
| `min_children` | 1 | every entry has at least two lines (here 2 to 15, median 4) |
| `waterfall_balance` | 8 | each quarter closes on its declared balance |
| `waterfall_net` | 8 | each quarter's movements net to the change in balance |
| `waterfall_component` | 24 | invoiced, collected and written off, per quarter |
| keys, domains, uniques | 9 | every line points at a real entry and account |

## What to test with it

- **The close.** Every entry balances, so every slice of entries does: the
  trial balance is zero for 2024 (4,020 entries), for 2025 (3,980), for any
  month and any source. A report that does not tie out has a bug in the
  report.
- **Reconciliations.** The receivables roll-forward opens at 1,250,000.00
  and closes 2025-Q4 at 1,648,902.40. A reconciliation job that computes a
  different closing balance from the movements is wrong, and you know the
  right answer before running it.
- **Known-answer questions.** `misata evalpack -c misata.yaml` turns the
  same declarations into SQL questions with answers, for testing an agent
  or a BI tool on accounting data.

## Related

- [Declaration reference](../reference/declarations.md): `waterfalls`, `balanced_ledger` and every other declaration
- [Attest a dataset](../guides/attest.md): the ledger, waterfall and `min_children` invariants
- [Certificate format](../attestation/certificate-v1.md): what each of the 52 checks records
- [Build an evalpack](../guides/evalpack.md): turn the same books into SQL questions with answers

## Files

The recipe folder runs as it is. Its files on GitHub:

- [`misata.yaml`](https://github.com/rasinmuhammed/misata/blob/main/examples/usecases/ledgers-that-reconcile/misata.yaml)
