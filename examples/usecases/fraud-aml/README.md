---
title: Fraud and AML Data With Labelled Truth
description: Generate a transfer network where every laundering ring, fan-in and scatter-gather was declared, hard negatives share their shapes, and no cycle exists that nobody planted, with each count attested by SQL.
---

# Fraud and AML data with labelled truth

A transaction-monitoring model is only as good as the labels it is scored
on, and real labels are late, partial and argued over. Grown synthetic
graphs have the opposite problem: patterns appear by accident, so a
detector's false positives may be the data's fault. Here every suspicious
pattern is declared, and the rest of the graph cannot contain one.

**Who:** risk, AML and fraud ML teams; graph analytics engineers.
**Time:** about 3 seconds for 320,000 rows.

## The declaration

```yaml
# misata.yaml
name: transfer_network
seed: 21
tables:
  accounts:
    rows: 20000
    columns:
      account_id: {type: int, unique: true, min: 1, max: 20000}
      kind: {type: categorical, choices: [personal, business], probabilities: [0.85, 0.15]}
      country: {type: categorical, choices: [US, GB, DE, AE, SG], probabilities: [0.45, 0.2, 0.15, 0.1, 0.1]}
      opened_on: {type: date, start: "2019-01-01", end: "2025-06-30"}
  transfers:
    rows: 300000
    columns:
      transfer_id: {type: int, unique: true, min: 1, max: 100000000}
      src: {type: int, min: 1, max: 20000}
      dst: {type: int, min: 1, max: 20000}
      amount: {type: float, distribution: lognormal, mean: 900, std: 2500, min: 1, max: 250000, decimals: 2}
      sent_at: {type: datetime, start: "2025-07-01", end: "2025-10-01"}
dag_edges:
  - name: background
    table: transfers
    node_table: accounts
    node_key: account_id
    from_column: src
    to_column: dst
graph_motifs:
  - name: laundering
    table: transfers
    node_table: accounts
    node_key: account_id
    from_column: src
    to_column: dst
    rate: 0.01
    shares: {cycle: 0.4, fan_in: 0.25, fan_out: 0.2, scatter_gather: 0.15}
    benign_rate: 0.01
    benign_shares: {cycle: 0.5, fan_in: 0.5}
    flag_column: is_suspicious
```

- `dag_edges` lays the 300,000 transfers out as a graph with no cycles.
- `graph_motifs` then rewrites 1% of them into flagged motifs (rings,
  fan-ins, fan-outs and scatter-gathers in the declared mix), and another
  1% into benign rings and fan-ins of the same shapes, the hard negatives.
- Each motif edge carries its shape in `motif`, its case id in
  `motif_case`, and `is_suspicious` is true for the flagged ones only.

## Run it

```bash
pip install "misata[parquet,duckdb]"
misata explain misata.yaml
misata generate -c misata.yaml -o out --format parquet --attest
```

## The check

```bash
python out/verify.py
```

```text
ok    2 file(s) match their attested sha256
ok    10 of 10 invariant(s) hold
```

| Invariant | Expected | What it proves |
|---|---:|---|
| `transfers.src->dst.acyclic` | 0 | no cycle among the 294,000 edges outside a declared case |
| `transfers.laundering.cycle.motif_edges` | 2,700 | 1,200 flagged ring edges plus 1,500 benign ones |
| `transfers.laundering.fan_in.motif_edges` | 2,250 | 750 flagged plus 1,500 benign |
| `transfers.laundering.fan_out.motif_edges` | 600 | flagged only |
| `transfers.laundering.scatter_gather.motif_edges` | 450 | flagged only |
| `transfers.laundering.flagged_edges` | 3,000 | exactly 1% of transfers are labelled suspicious |

The acyclic check is Kahn's algorithm written as a DuckDB recursive query:
it removes nodes with no incoming edges round by round and counts what is
left. It finishes in under half a second on this graph, and it fails on a
single planted cycle, so a reader who does not trust the generator can
confirm that every cycle in the file belongs to a case.

## What it is for

Because the background is acyclic, a perfect cycle finder flags exactly the
2,700 ring edges, and only 1,200 of them are suspicious: 44% precision from
topology alone. That is the point of declaring hard negatives. A detector is
scored on telling a laundering ring from an innocent loop, and every miss
and every false alarm traces to a case id.

The transfers table is an edge list, so it loads into any graph tool as it
is: `src` and `dst` are account ids, and `accounts` holds the node
attributes.
