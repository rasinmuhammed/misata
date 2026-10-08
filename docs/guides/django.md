# Seeding a Django project

`misata.from_django()` reads your models (field types, `max_length`,
`choices`, `unique`, `null`, min/max validators, decimal places, foreign keys,
one-to-one and many-to-many) and returns a schema whose rows fit the tables
`migrate` created.

```bash
pip install "misata[django]"
```

```python
# python manage.py shell
import misata

schema = misata.from_django(app_labels=["shop"], default_rows=500)
for t in schema.tables:
    if t.name == "shop_order":
        t.row_count = 5000

misata.seed_database(schema, "postgresql://localhost/shop_dev")   # one transaction
```

Tables and columns use the database names (`shop_book`, `author_id`).
Many-to-many through tables are included and kept unique per pair, as are
`unique_together` and `UniqueConstraint` combinations. `django.contrib`
models (users, sessions) are skipped unless you pass `include_contrib=True`
or name their app. A `JSONField` becomes a small JSON object; give it
`fields` (see [nested columns](nested-columns.md)) to shape it.

The result is an ordinary schema: add curves, lifecycles or processes to it,
or save it as YAML and keep it next to your models.
