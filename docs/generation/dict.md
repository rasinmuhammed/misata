# Python Dict Schema

Import your own schema structure — useful when you already have a dict representation of your tables (e.g. from an ORM introspection or a JSON schema).

```python
import misata

schema = misata.from_dict_schema({
    "customers": {
        "id":    {"type": "integer", "primary_key": True},
        "email": {"type": "email"},
        "plan":  {"type": "string", "enum": ["free", "pro", "enterprise"]},
        "mrr":   {"type": "float", "min": 0.0, "max": 2400.0},
    },
    "orders": {
        "id":          {"type": "integer", "primary_key": True},
        "customer_id": {
            "type": "integer",
            "foreign_key": {"table": "customers", "column": "id"},
        },
        "amount": {"type": "float", "min": 1.0, "max": 999.0},
    },
}, row_count=5_000)

tables = misata.generate_from_schema(schema)
```

## Type mapping

| Dict `type` | Misata type |
|:--|:--|
| `integer`, `int` | `int` |
| `float`, `number`, `decimal` | `float` |
| `string`, `str`, `text`, `email`, `url` | `text` |
| `boolean`, `bool` | `boolean` |
| `date`, `datetime`, `timestamp` | `date` |
| `enum` (with `enum` key) | `categorical` |
