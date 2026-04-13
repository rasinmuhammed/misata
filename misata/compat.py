"""
Schema import utilities for Misata.

Provides helpers for converting common schema formats into a native
``SchemaConfig``, so you can bring your existing schema definitions
into Misata without rewriting them.

Supported input formats:
- Generic dict-based schemas (column name → type + constraints)
- SQLAlchemy ORM models (via ``misata.schema_from_sqlalchemy``)
- YAML / JSON files (via ``misata.load_recipe``)

Example::

    import misata

    schemas = {
        "customers": {
            "id":     {"type": "integer", "primary_key": True},
            "name":   {"type": "string"},
            "email":  {"type": "email"},
            "status": {"type": "string", "enum": ["active", "inactive", "trial"]},
        },
        "orders": {
            "id":          {"type": "integer", "primary_key": True},
            "customer_id": {"type": "integer", "foreign_key": {"table": "customers", "column": "id"}},
            "amount":      {"type": "float",   "min": 1.0, "max": 5000.0},
            "placed_at":   {"type": "date",    "min_date": "2023-01-01", "max_date": "2025-12-31"},
        },
    }

    schema = misata.from_dict_schema(schemas, row_count=2000)
    tables = misata.generate_from_schema(schema)
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional

from misata.schema import Column, Relationship, SchemaConfig, Table


# ---------------------------------------------------------------------------
# Type normalisation
# ---------------------------------------------------------------------------

_TYPE_MAP: Dict[str, str] = {
    "integer": "int",
    "int": "int",
    "number": "int",
    "bigint": "int",
    "smallint": "int",
    "serial": "int",
    "float": "float",
    "decimal": "float",
    "double": "float",
    "numeric": "float",
    "real": "float",
    "money": "float",
    "string": "text",
    "text": "text",
    "varchar": "text",
    "char": "text",
    "uuid": "text",
    "email": "text",
    "phone": "text",
    "url": "text",
    "address": "text",
    "zipcode": "text",
    "date": "date",
    "datetime": "datetime",
    "timestamp": "datetime",
    "boolean": "boolean",
    "bool": "boolean",
    "foreign_key": "foreign_key",
    "array": "text",
    "json": "text",
    "object": "text",
}

_TEXT_TYPE_HINTS: Dict[str, str] = {
    "email": "email",
    "phone": "phone",
    "name": "name",
    "full_name": "name",
    "first_name": "name",
    "last_name": "name",
    "company": "company",
    "address": "address",
    "url": "url",
    "website": "url",
}


def _col_from_dict(
    col_name: str,
    col_def: Dict[str, Any],
    primary_key_col: Optional[str],
) -> Optional[Column]:
    """Convert a single dict column definition to a Misata ``Column``."""
    raw_type = str(col_def.get("type", "string")).lower()

    # Primary keys → sequential unique int (name must be "id" for Misata's auto-sequence)
    if col_def.get("primary_key") and col_name == primary_key_col:
        return Column(
            name=col_name,
            type="int",
            distribution_params={"distribution": "uniform", "min": 1, "max": 2_000_000},
            nullable=False,
            unique=True,
        )

    # FK declared inline as a nested dict
    fk_ref = col_def.get("foreign_key")
    if fk_ref or raw_type == "foreign_key":
        return Column(name=col_name, type="foreign_key", distribution_params={})

    misata_type = _TYPE_MAP.get(raw_type, "text")

    # Detect categorical from enum constraint
    enum = col_def.get("enum") or col_def.get("choices")
    if enum and isinstance(enum, list) and misata_type in ("text", "int", "float"):
        misata_type = "categorical"

    params: Dict[str, Any] = {}

    if misata_type == "categorical":
        choices = [str(c) for c in enum] if enum else ["Unknown"]
        params["choices"] = choices

    elif misata_type in ("int", "float"):
        if col_def.get("min") is not None:
            params["min"] = col_def["min"]
        if col_def.get("max") is not None:
            params["max"] = col_def["max"]
        if col_def.get("decimals") is not None:
            params["decimals"] = col_def["decimals"]

    elif misata_type == "text":
        # Infer text_type from column name
        for hint_key, text_type in _TEXT_TYPE_HINTS.items():
            if hint_key in col_name.lower():
                params["text_type"] = text_type
                break
        # Explicit raw type overrides name-based hint
        if raw_type in ("email", "phone", "url", "uuid"):
            params["text_type"] = raw_type

    elif misata_type in ("date", "datetime"):
        params["start"] = col_def.get("min_date", "2020-01-01")
        params["end"] = col_def.get("max_date", "2024-12-31")

    nullable = bool(col_def.get("nullable", True))
    unique = bool(col_def.get("unique", False))
    description = col_def.get("description") or None

    return Column(
        name=col_name,
        type=misata_type,
        distribution_params=params,
        nullable=nullable,
        unique=unique,
        description=description,
    )


def _detect_pk(table_def: Dict[str, Any]) -> Optional[str]:
    for col_name, col_def in table_def.items():
        if isinstance(col_def, dict) and col_def.get("primary_key"):
            return col_name
    return "id" if "id" in table_def else None


def from_dict_schema(
    schemas: Dict[str, Any],
    row_count: int = 1000,
    seed: Optional[int] = 42,
) -> SchemaConfig:
    """Convert a plain dict schema definition to a Misata ``SchemaConfig``.

    This accepts a flexible format where each table is a dict of column
    definitions.  Supported column definition keys:

    - ``type``: data type (see full list below)
    - ``primary_key``: ``True`` to mark as PK (auto-generated, excluded from output)
    - ``foreign_key``: ``{"table": "...", "column": "..."}`` to declare a FK
    - ``min`` / ``max``: numeric range
    - ``min_date`` / ``max_date``: date range
    - ``enum`` / ``choices``: list of allowed values (becomes categorical)
    - ``decimals``: decimal places for floats
    - ``nullable``: whether ``None`` values are allowed (default ``True``)
    - ``unique``: whether values must be unique

    Supported types: ``integer``, ``float``, ``decimal``, ``string``, ``text``,
    ``email``, ``phone``, ``url``, ``uuid``, ``date``, ``datetime``,
    ``timestamp``, ``boolean``, ``foreign_key``.

    Args:
        schemas:   Dict mapping table name → column definitions dict.
        row_count: Default row count for every table.
        seed:      Random seed for reproducibility.

    Returns:
        :class:`~misata.schema.SchemaConfig` ready for
        :func:`~misata.generate_from_schema`.

    Example::

        schema = misata.from_dict_schema({
            "products": {
                "id":       {"type": "integer", "primary_key": True},
                "name":     {"type": "string"},
                "price":    {"type": "float", "min": 1.0, "max": 999.0},
                "category": {"type": "string", "enum": ["Electronics", "Clothing", "Books"]},
            },
            "orders": {
                "id":         {"type": "integer", "primary_key": True},
                "product_id": {"type": "integer",
                               "foreign_key": {"table": "products", "column": "id"}},
                "quantity":   {"type": "integer", "min": 1, "max": 10},
                "placed_at":  {"type": "date"},
            },
        }, row_count=5000)

        tables = misata.generate_from_schema(schema)
    """
    tables: List[Table] = []
    columns_map: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    for table_name, table_def in schemas.items():
        if not isinstance(table_def, dict):
            warnings.warn(f"Skipping non-dict entry for table '{table_name}'.")
            continue

        # Support both __table_description__ and __description__ as table-level metadata
        table_desc = (
            table_def.get("__table_description__")
            or table_def.get("__description__")
            or None
        )

        pk_col = _detect_pk(table_def)
        table_cols: List[Column] = []

        for col_name, col_def in table_def.items():
            if col_name.startswith("__") or not isinstance(col_def, dict):
                continue

            # Collect FK relationships
            fk_ref = col_def.get("foreign_key")
            if fk_ref and isinstance(fk_ref, dict):
                relationships.append(Relationship(
                    parent_table=fk_ref["table"],
                    child_table=table_name,
                    parent_key=fk_ref.get("column", "id"),
                    child_key=col_name,
                ))

            col = _col_from_dict(col_name, col_def, primary_key_col=pk_col)
            if col is not None:
                table_cols.append(col)

        tables.append(Table(name=table_name, row_count=row_count, description=table_desc))
        columns_map[table_name] = table_cols

    return SchemaConfig(
        name="Imported schema",
        tables=tables,
        columns=columns_map,
        relationships=relationships,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Post-generation referential integrity verification
# ---------------------------------------------------------------------------

class IntegrityReport:
    """Result of a referential integrity check across FK relationships."""

    def __init__(self, violations: List[Dict[str, Any]]):
        self.violations = violations
        self.ok = len(violations) == 0

    def __repr__(self) -> str:
        if self.ok:
            return "IntegrityReport(ok=True, violations=0)"
        lines = [f"IntegrityReport(ok=False, violations={len(self.violations)}):"]
        for v in self.violations:
            count = v["orphan_count"]
            count_str = f"{count:,} orphans" if count >= 0 else "table missing"
            lines.append(f"  {v['relationship']}: {count_str} — {v['issue']}")
            if "sample_orphans" in v:
                lines.append(f"    sample values: {v['sample_orphans']}")
        return "\n".join(lines)

    def raise_if_invalid(self) -> None:
        """Raise ``ValueError`` if any violations were found."""
        if not self.ok:
            raise ValueError(str(self))


def verify_integrity(
    tables: Dict[str, Any],
    schema: SchemaConfig,
) -> IntegrityReport:
    """Verify referential integrity across all FK relationships.

    Misata guarantees zero orphans during generation. Use this after manual
    edits, data merges, or multi-step pipelines to catch regressions.

    Args:
        tables: Dict mapping table name → ``pd.DataFrame``.
        schema: The ``SchemaConfig`` that describes the relationships.

    Returns:
        :class:`IntegrityReport` — check ``.ok`` for pass/fail, or call
        ``.raise_if_invalid()`` to turn failures into exceptions.

    Example::

        tables = misata.generate("An ecommerce store with 5k orders", seed=42)
        report = misata.verify_integrity(tables, schema)
        print(report)  # IntegrityReport(ok=True, violations=0)
    """
    violations: List[Dict[str, Any]] = []

    for rel in schema.relationships:
        pname, cname = rel.parent_table, rel.child_table
        pkey, ckey = rel.parent_key, rel.child_key
        label = f"{cname}.{ckey} → {pname}.{pkey}"

        if pname not in tables:
            violations.append({"relationship": label,
                                "issue": f"Parent table '{pname}' not found.",
                                "orphan_count": -1})
            continue
        if cname not in tables:
            violations.append({"relationship": label,
                                "issue": f"Child table '{cname}' not found.",
                                "orphan_count": -1})
            continue

        parent_df = tables[pname]
        child_df = tables[cname]

        if pkey not in parent_df.columns:
            violations.append({"relationship": label,
                                "issue": f"Column '{pkey}' not in '{pname}'.",
                                "orphan_count": -1})
            continue
        if ckey not in child_df.columns:
            violations.append({"relationship": label,
                                "issue": f"Column '{ckey}' not in '{cname}'.",
                                "orphan_count": -1})
            continue

        valid_ids = set(parent_df[pkey].dropna().unique())
        child_vals = child_df[ckey].dropna()
        orphans = child_vals[~child_vals.isin(valid_ids)]

        if len(orphans) > 0:
            violations.append({
                "relationship": label,
                "issue": "Orphaned FK values detected.",
                "orphan_count": int(len(orphans)),
                "sample_orphans": orphans.unique()[:5].tolist(),
            })

    return IntegrityReport(violations=violations)
