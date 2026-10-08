"""Build a Misata schema from Django models.

Django projects already describe their data precisely: field types, lengths,
choices, uniqueness, nullability, validators and foreign keys. Reading that
directly means the generated rows fit the tables ``migrate`` created, with no
schema written twice::

    import django; django.setup()
    import misata

    schema = misata.from_django(app_labels=["shop"], default_rows=500)
    misata.seed_database(schema, "postgresql://localhost/shop_dev")

Mapping:

- ``AutoField`` and friends: a unique integer key.
- integer, float and decimal fields: numbers, honouring ``MinValueValidator``/
  ``MaxValueValidator``, ``Positive*`` and ``decimal_places``.
- ``CharField``/``TextField``/``SlugField``/``EmailField``/``URLField``/
  ``UUIDField``/``GenericIPAddressField``: text, with ``max_length`` held and
  the semantic type set where the field says it.
- any field with ``choices``: the choice values.
- ``DateField``/``DateTimeField``/``TimeField``/``BooleanField``: as named.
- ``JSONField``: a small JSON object (declare ``fields`` on the column to
  shape it; see the nested-columns docs).
- ``ForeignKey``/``OneToOneField``: a relationship on the real column
  (``author_id``); one-to-one is unique.
- ``ManyToManyField``: its through table, with both foreign keys.

Tables and columns use ``db_table`` and ``column``, the names in the database.
"""
from __future__ import annotations

import warnings
from typing import Any, Dict, Iterable, List, Optional

from misata.schema import Column, Constraint, Relationship, SchemaConfig, Table


def _require_django():
    try:
        import django  # noqa: F401
        from django.apps import apps
    except ImportError:
        raise ImportError('from_django() needs Django: pip install "misata[django]"') from None
    if not apps.ready:
        raise RuntimeError("Django is not set up: call django.setup() (or run inside "
                           "manage.py shell) before from_django().")
    return apps


def _validator_bounds(field) -> Dict[str, Any]:
    from django.core import validators as v
    out: Dict[str, Any] = {}
    for val in getattr(field, "validators", []) or []:
        if isinstance(val, v.MinValueValidator) and isinstance(val.limit_value, (int, float)):
            out["min"] = val.limit_value
        elif isinstance(val, v.MaxValueValidator) and isinstance(val.limit_value, (int, float)):
            out["max"] = val.limit_value
    return out


def _column_for(field, rows: int) -> Optional[Column]:
    from django.db import models as m

    name = field.column
    nullable = bool(getattr(field, "null", False))
    unique = bool(getattr(field, "unique", False)) or bool(getattr(field, "primary_key", False))

    if getattr(field, "choices", None):
        values = [c[0] for c in field.flatchoices] if hasattr(field, "flatchoices") \
            else [c[0] for c in field.choices]
        if values:
            return Column(name=name, type="categorical", nullable=nullable,
                          distribution_params={"choices": values})

    if isinstance(field, (m.AutoField, m.BigAutoField, m.SmallAutoField)):
        return Column(name=name, type="int", unique=True, nullable=False,
                      distribution_params={"distribution": "uniform", "min": 1,
                                           "max": max(rows, 1)})
    if isinstance(field, m.BooleanField):
        return Column(name=name, type="boolean", nullable=nullable)
    if isinstance(field, (m.IntegerField,)):
        params = _validator_bounds(field)
        if isinstance(field, (m.PositiveIntegerField, m.PositiveSmallIntegerField,
                              m.PositiveBigIntegerField)):
            params.setdefault("min", 0)
        return Column(name=name, type="int", unique=unique, nullable=nullable,
                      distribution_params=params)
    if isinstance(field, m.DecimalField):
        params = _validator_bounds(field)
        params["decimals"] = int(field.decimal_places or 0)
        if field.max_digits:
            params.setdefault("max", float(10 ** (field.max_digits - (field.decimal_places or 0)) - 1))
        return Column(name=name, type="float", unique=unique, nullable=nullable,
                      distribution_params=params)
    if isinstance(field, m.FloatField):
        return Column(name=name, type="float", unique=unique, nullable=nullable,
                      distribution_params=_validator_bounds(field))
    if isinstance(field, m.DateTimeField):
        return Column(name=name, type="datetime", nullable=nullable)
    if isinstance(field, m.DateField):
        return Column(name=name, type="date", nullable=nullable)
    if isinstance(field, m.TimeField):
        return Column(name=name, type="time", nullable=nullable)
    if isinstance(field, m.JSONField):
        return Column(name=name, type="json", nullable=nullable, distribution_params={
            "fields": {"source": {"type": "string", "enum": ["web", "app", "api", "import"]},
                       "version": {"type": "int", "min": 1, "max": 5}}})
    text_type = None
    if isinstance(field, m.EmailField):
        text_type = "email"
    elif isinstance(field, m.URLField):
        text_type = "url"
    elif isinstance(field, m.UUIDField):
        text_type = "uuid"
    elif isinstance(field, m.SlugField):
        text_type = "slug"
    elif isinstance(field, m.GenericIPAddressField):
        text_type = "ipv4"
    if isinstance(field, (m.CharField, m.TextField, m.UUIDField, m.GenericIPAddressField)):
        params: Dict[str, Any] = {}
        if text_type:
            params["text_type"] = text_type
        max_len = getattr(field, "max_length", None)
        if max_len:
            params["max_length"] = int(max_len)
        return Column(name=name, type="text", unique=unique, nullable=nullable,
                      distribution_params=params)
    if isinstance(field, (m.BinaryField, m.FileField)):
        return Column(name=name, type="text", nullable=nullable,
                      distribution_params={"max_length": getattr(field, "max_length", None) or 100})
    warnings.warn(f"from_django: {field.model.__name__}.{field.name} "
                  f"({type(field).__name__}) has no mapping and was skipped")
    return None


def from_django(models: Optional[Iterable[Any]] = None, *,
                app_labels: Optional[Iterable[str]] = None,
                default_rows: int = 1000,
                include_contrib: bool = False) -> SchemaConfig:
    """A :class:`SchemaConfig` for Django models.

    Args:
        models: model classes to include. Default: every installed model.
        app_labels: limit to these apps (``["shop", "billing"]``).
        default_rows: rows per table; adjust ``table.row_count`` afterwards.
        include_contrib: also include ``django.contrib`` models (auth users,
            sessions, admin log). Off by default: they are usually seeded by
            Django itself.
    """
    apps = _require_django()
    if models is None:
        models = apps.get_models(include_auto_created=True)
    models = list(models)
    labels = set(app_labels or [])
    chosen = []
    for model in models:
        meta = model._meta
        if labels and meta.app_label not in labels:
            continue
        if not include_contrib and model.__module__.startswith("django.contrib") \
                and not (labels and meta.app_label in labels):
            continue
        if meta.proxy or meta.abstract or not meta.managed and not meta.auto_created:
            continue
        chosen.append(model)
    # Explicit models: add their auto-created many-to-many through tables.
    for model in list(chosen):
        for m2m in model._meta.local_many_to_many:
            through = m2m.remote_field.through
            if through._meta.auto_created and through not in chosen:
                chosen.append(through)

    names = {mdl._meta.db_table for mdl in chosen}
    tables: List[Table] = []
    columns: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []
    for model in chosen:
        meta = model._meta
        table = meta.db_table
        tables.append(Table(name=table, row_count=default_rows,
                            description=str(meta.verbose_name_plural)))
        cols: List[Column] = []
        for field in meta.concrete_fields:
            if field.is_relation and field.many_to_one or field.one_to_one and field.is_relation:
                target = field.related_model._meta
                parent_key = field.target_field.column
                if target.db_table not in names:
                    warnings.warn(f"from_django: {meta.label}.{field.name} references "
                                  f"{target.label}, which is not included; it is generated "
                                  f"as a plain value")
                    cols.append(Column(name=field.column, type="int", nullable=field.null))
                    continue
                cols.append(Column(name=field.column, type="foreign_key", nullable=field.null,
                                   unique=bool(field.one_to_one or field.unique)))
                if target.db_table != table:
                    relationships.append(Relationship(
                        parent_table=target.db_table, child_table=table,
                        parent_key=parent_key, child_key=field.column))
                continue
            col = _column_for(field, default_rows)
            if col is not None:
                cols.append(col)
        columns[table] = cols
        # Composite uniqueness: unique_together, UniqueConstraint, and every
        # many-to-many through table (one row per pair). Duplicate
        # combinations are dropped, so such a table may come out a little
        # short of default_rows.
        combos = [tuple(u) for u in (meta.unique_together or [])]
        try:
            from django.db.models import UniqueConstraint
            combos += [tuple(c.fields) for c in meta.constraints
                       if isinstance(c, UniqueConstraint) and c.fields and c.condition is None]
        except ImportError:
            pass
        by_name = {f.name: f.column for f in meta.concrete_fields}
        for i, combo in enumerate(combos):
            cols_ = [by_name.get(f, f) for f in combo]
            if len(cols_) > 1:
                tables[-1].constraints.append(Constraint(
                    name=f"{table}_unique_{i}", type="unique_combination",
                    group_by=cols_, action="drop"))
    return SchemaConfig(name="django", tables=tables, columns=columns,
                        relationships=relationships)
