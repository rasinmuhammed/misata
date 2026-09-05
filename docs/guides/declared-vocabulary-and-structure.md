# Lexicons, motifs and joint margins

Three declarations added in 0.9.6.46 through 0.9.6.50. Each one closes a gap
where the engine used to produce something plausible instead of something
stated.

## `semantic`: vocabulary that keeps growing

A text column used to draw from a fixed pool. Over thirty thousand rows that
pool runs out and the column starts repeating, which is the fastest way for
synthetic data to give itself away.

`semantic` names what a column *means*, and the engine resolves it to a
generative lexicon: a small head of real, high-frequency values drawn with
Zipfian weight over rank, plus composition over morpheme slots for everything
past the head.

```python
schema = {
    "port_calls": {
        "__rows__": 30_000,
        "id": {"type": "integer", "primary_key": True},
        "vessel": {"type": "text", "semantic": "vessel_name"},
        "master": {"type": "text", "semantic": "person_name"},
    },
}
```

Built-in lexicons: `person_name`, `company_name`, `vessel_name`,
`medical_procedure`. Inspect one with:

```python
from misata.lexicon import get_spec
spec = get_spec("vessel_name")
print(spec.description, spec.effective_capacity())
```

### Effective capacity, not raw capacity

`effective_capacity()` is the number that matters. A pattern drawn 4% of the
time contributes 4% of the draws however many values it could form, so a
column duplicates at the rate of the pattern that saturates first. Raw
capacity overstates by up to 300x.

Feasibility refuses a column whose row count exceeds what its lexicon can
carry, before generating anything, using a per-type `rows_per_distinct`.
Repetition is a property of the type, not a defect: clinical coding genuinely
concentrates on a handful of procedures, so thirty thousand rows over a few
thousand distinct values is what real data looks like, while thirty thousand
customers sharing two thousand names is not.

### Locale still wins

Person names are region-specific and the locale pack gets them right. Lexicons
marked `locale_sensitive` step aside for any locale other than `en_US`, so
`locale="ja_JP"` still returns 鈴木 くみ子.

## `graph_motifs`: the patterns worth detecting exist on purpose

`dag_edges` guarantees a graph with no cycles. That is the right default and
the wrong dataset for anyone building a detector, because the shapes worth
finding are exactly the ones a DAG forbids.

`graph_motifs` rewrites a declared fraction of an edge table into rings,
fan-in, fan-out, scatter-gather and chains at an exact mix, each labelled with
a case id, leaving every other edge as the DAG put it.

```python
schema = {
    "accounts": {"__rows__": 5_000, "id": {"type": "integer", "primary_key": True}},
    "transfers": {
        "__rows__": 80_000,
        "src": {"type": "integer"}, "dst": {"type": "integer"},
        "amount": {"type": "float", "min": 10, "max": 90_000},
    },
    "__graph_motifs__": [{
        "name": "laundering", "table": "transfers",
        "from_column": "src", "to_column": "dst",
        "node_table": "accounts", "node_key": "id",
        "rate": 0.02,
        "shares": {"cycle": 0.4, "fan_in": 0.25, "fan_out": 0.2, "scatter_gather": 0.15},
        "benign_rate": 0.02,
        "benign_shares": {"cycle": 0.5, "fan_in": 0.5},
        "flag_column": "is_suspicious",
    }],
}
```

Three columns come back on the edge table. `motif` names the shape (`cycle`,
`fan_in`, `fan_out`, `scatter_gather`, `chain`, or `""` for a background edge),
`motif_case` groups the edges belonging to one instance, and `flag_column`, if
you name one, is the label: `True` for the flagged motifs and `False` for
everything else, including the benign ones. Without it a benign ring and a
flagged ring are indistinguishable, which defeats the point of declaring them.

The property that follows is exact rather than statistical:

> the subgraph of edges carrying no case id is acyclic

So every cycle in the output belongs to a case somebody declared, and an
accidental pattern cannot exist rather than merely being unlikely. A detector
run against it cannot produce an unexplained hit.

This holds only when `dag_edges` covers the same table and endpoints. Motifs
rewrite a fraction of an edge table; they do not make the rest of it acyclic.
Measured over 60,000 edges: 879 background cycles without the `dag_edges` spec,
zero with it. The audit reports `motif_background_not_declared_acyclic` when it
is missing.

`benign_shares` declares hard negatives: real motifs of the same shapes,
labelled legitimate. A detector is then measured on telling a ring from an
innocent loop rather than on finding loops.

Feasibility refuses a node pool too small to lay out the widest motif without
repeating a node inside one case.

## `joint_distributions`: several margins, all at once, exactly

Two declared margins used to be satisfiable one at a time and silently
inconsistent together. This solves for the unique maximum-entropy table
consistent with every declared margin, by iterative proportional fitting.

```python
schema = {
    "accounts": {
        "__rows__": 50_000,
        "region": {"type": "string", "enum": ["emea", "apac", "amer"]},
        "tier": {"type": "string", "enum": ["free", "pro", "enterprise"]},
    },
    "__joint_distributions__": [{
        "name": "region_by_tier", "table": "accounts",
        "margins": {
            "region": {"emea": 0.42, "apac": 0.31, "amer": 0.27},
            "tier": {"free": 0.70, "pro": 0.22, "enterprise": 0.08},
        },
    }],
}
```

Margins that cannot all hold are refused up front, with both declarations and
the arithmetic named, rather than one being quietly dropped.

Two-way tables integerise with **both** margins exact, which is always
solvable. Three-way and above preserve the grand total exactly and say so
rather than implying more, because integer margin preservation above two
dimensions has no such guarantee.

Pass `emphasis` to bias the interior of the table towards a known
association, or `forbidden` to zero out combinations that cannot occur.
