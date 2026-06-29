---
title: "Conditional Columns, Make One Column Depend on Another"
description: "Use depends_on to make a column's distribution conditional on another column or a parent table — salary by role, MRR by plan tier, approval rate by policy type — including across foreign keys."
---

# Conditional Columns (`depends_on`)

Real data is conditional: salary depends on role, MRR depends on plan tier, claim-approval probability depends on policy type. `depends_on` makes a column's distribution switch on the value of another column — in the same table, or in a parent table across a foreign key.

> If two *numeric* columns should move together statistically (without one strictly determining the other), use a [correlation](correlations.md) instead. Use `depends_on` when a category picks the distribution.

---

## Same-table dependency

```python
import misata

schema = {
    "employees": {
        "__rows__": 8000,
        "role":   {"type": "string", "enum": ["Intern", "Engineer", "CTO"],
                   "probabilities": [0.3, 0.6, 0.1]},
        "salary": {
            "type": "float",
            "depends_on": "role",
            "mapping": {
                "Intern":   {"mean": 40000,  "std": 3000},
                "Engineer": {"mean": 120000, "std": 10000},
                "CTO":      {"mean": 300000, "std": 20000},
            },
            "default": {"mean": 80000, "std": 8000},   # used for any unmapped value
        },
    }
}
tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=1))
```

Each `mapping` value is itself a set of distribution parameters, so the conditional branches can have entirely different shapes.

## Boolean outcome (a conditional rate)

For a boolean column, map each case to a probability:

```python
"approved": {
    "type": "boolean",
    "depends_on": "policy_type",
    "mapping": {"auto": 0.80, "health": 0.60, "life": 0.55},
}
```

## Across a foreign key

Reference a **parent** column with dotted `fk_column.parent_column` notation. The child row resolves the parent value through its foreign key, then picks the matching branch:

```python
schema = {
    "plans": {"__rows__": 2, "id": {"type": "integer", "primary_key": True},
              "tier": {"type": "string", "enum": ["Free", "Enterprise"]}},
    "subscriptions": {
        "__rows__": 5000,
        "id":      {"type": "integer", "primary_key": True},
        "plan_id": {"type": "integer", "foreign_key": {"table": "plans", "column": "id"}},
        "mrr": {
            "type": "float",
            "depends_on": "plan_id.tier",       # parent column via the FK
            "mapping": {"Free": {"mean": 0, "std": 1},
                        "Enterprise": {"mean": 1000, "std": 50}},
        },
    },
}
```

## Keys

| Key | Meaning |
|-----|---------|
| `depends_on` | The predictor column. `"col"` for same-table, `"fk_col.parent_col"` across a FK. |
| `mapping` | `{value → params}`. Numeric → `{mean, std}` (or any distribution params); boolean → a probability; categorical → a list of choices. |
| `default` | Distribution params used when a row's predictor value is not in `mapping`. |

## In the studio

The column **Inspector** has a *Conditional* section: pick the predictor column and add `when value → outcome` cases (μ/σ for numeric columns, P(true) for booleans). Cross-table dependencies use the `fk_col.parent_col` form.
