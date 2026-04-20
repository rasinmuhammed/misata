# YAML Schema

Define your schema in a file, commit it to git, and reproduce the same dataset anywhere — no LLM required.

## Scaffold

```bash
misata init                                     # writes misata.yaml template
misata init --story "A marketplace"             # parses a story into YAML
misata init --db postgresql://localhost/myapp   # introspects a real database
```

## Schema structure

```yaml
name: my-app
seed: 42

tables:
  users:
    rows: 1000
    columns:
      user_id:  { type: int, unique: true }
      email:    { type: text, text_type: email }
      plan:     { type: categorical, choices: [free, pro, enterprise] }
      mrr:      { type: float, min: 0, max: 2400, distribution: lognormal }
      signed_up: { type: date, start: "2022-01-01", end: "2024-12-31" }

  orders:
    rows: 5000
    columns:
      order_id: { type: int, unique: true }
      user_id:  { type: foreign_key }
      amount:   { type: float, min: 5.0, max: 500.0 }
      cost:     { type: float, min: 2.0, max: 200.0 }

relationships:
  - "users.user_id → orders.user_id"

constraints:
  - name: profit_margin
    table: orders
    type: inequality
    column_a: amount
    operator: ">"
    column_b: cost
```

## Generate

```python
import misata

schema = misata.load_yaml_schema("misata.yaml")
tables = misata.generate_from_schema(schema)
```

Or from the CLI — auto-detected if `misata.yaml` exists in the current directory:

```bash
misata generate
misata generate --output-dir data/
```

## Round-trip

```python
# Inspect a programmatically built schema, then save it
schema = misata.parse("A healthcare company with 500 patients")
misata.save_yaml_schema(schema, "healthcare.yaml")
```

## Column types

| `type` | Description | Key params |
|:--|:--|:--|
| `int` | Integer | `min`, `max`, `unique`, `distribution` |
| `float` | Floating point | `min`, `max`, `decimals`, `distribution` |
| `text` | String / semantic | `text_type` (name, email, city, …) |
| `categorical` | Enum / factor | `choices`, `probabilities`, `sampling` |
| `boolean` | True/False | `probability` |
| `date` | Date column | `start`, `end`, `format` |
| `foreign_key` | FK reference | resolved from `relationships` |
