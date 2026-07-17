"""
dbt → Misata import: generate seed data from a dbt project's own contract.

Reads the properties YAML files of an existing dbt project (``models/**/*.yml``,
``seeds/**/*.yml``), translates the declared columns and generic tests into a
Misata :class:`~misata.schema.SchemaConfig`, and lets the normal generation
pipeline produce seed CSVs that satisfy the project's own ``dbt test`` suite:

  - ``relationships`` tests  → FK relationships (referential integrity)
  - ``accepted_values`` test → categorical columns restricted to those values
  - ``unique`` test          → unique columns (sequential PKs for ids)
  - ``not_null`` test        → non-nullable columns
  - ``data_type``            → column type mapping
  - untyped columns          → semantic name inference (email, dates, names, …)

Usage from CLI::

    misata dbt-seed --from-project          # inside any dbt project

Usage from Python::

    from misata.dbt_import import build_schema_from_dbt_project
    schema, report = build_schema_from_dbt_project(Path("~/my-dbt-repo"))
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from misata.dbt import DbtProjectInfo, detect_dbt_project


# ---------------------------------------------------------------------------
# Parsed dbt entities
# ---------------------------------------------------------------------------

@dataclass
class DbtColumnSpec:
    """A column as declared in a dbt properties file."""

    name: str
    description: Optional[str] = None
    data_type: Optional[str] = None
    unique: bool = False
    not_null: bool = False
    accepted_values: Optional[List[Any]] = None
    # (to_entity, field) from a relationships test; None if not an FK
    relationship: Optional[Tuple[str, str]] = None
    skipped_tests: List[str] = field(default_factory=list)


@dataclass
class DbtEntitySpec:
    """A seed or model entry from a dbt properties file."""

    name: str
    resource_type: str  # "seed" | "model"
    source_file: Path
    description: Optional[str] = None
    columns: List[DbtColumnSpec] = field(default_factory=list)


@dataclass
class DbtImportReport:
    """What the importer read and how it translated it."""

    yml_files_read: int = 0
    entities: List[DbtEntitySpec] = field(default_factory=list)
    targets: List[str] = field(default_factory=list)
    relationships_translated: int = 0
    accepted_values_translated: int = 0
    unique_translated: int = 0
    not_null_translated: int = 0
    skipped_tests: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    # (table, column) pairs that must be written date-only (no time part):
    # dbt declared them `data_type: date`, or they are `*_date`-named.
    date_only_columns: List[Tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Read {self.yml_files_read} properties file(s), "
            f"{len(self.entities)} declared entit(ies), "
            f"targeting {len(self.targets)} table(s): {', '.join(self.targets)}",
            f"Tests translated: {self.relationships_translated} relationships, "
            f"{self.accepted_values_translated} accepted_values, "
            f"{self.unique_translated} unique, {self.not_null_translated} not_null",
        ]
        if self.skipped_tests:
            lines.append(f"Skipped (not translatable): {', '.join(sorted(set(self.skipped_tests)))}")
        lines.extend(self.warnings)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Properties file parsing
# ---------------------------------------------------------------------------

_REF_RE = re.compile(r"""ref\(\s*['"]([^'"]+)['"]\s*(?:,\s*['"]([^'"]+)['"]\s*)?\)""")


def _parse_ref(to_expr: str) -> Optional[str]:
    """Extract the target name from ``ref('x')`` / ``ref('pkg', 'x')``."""
    m = _REF_RE.search(str(to_expr))
    if not m:
        return None
    # Two-arg form: ref('package', 'model') → second group is the model
    return m.group(2) or m.group(1)


def _test_args(spec: Any) -> Dict[str, Any]:
    """Return a generic test's argument dict, tolerating both the legacy
    inline form and the dbt 1.9+ ``arguments:`` nesting."""
    if not isinstance(spec, dict):
        return {}
    if isinstance(spec.get("arguments"), dict):
        merged = {k: v for k, v in spec.items() if k not in ("arguments", "config")}
        merged.update(spec["arguments"])
        return merged
    return {k: v for k, v in spec.items() if k != "config"}


def _parse_column(raw: Dict[str, Any]) -> DbtColumnSpec:
    col = DbtColumnSpec(
        name=str(raw.get("name", "")),
        description=raw.get("description"),
        data_type=(str(raw["data_type"]).lower() if raw.get("data_type") else None),
    )

    # dbt 1.8 renamed `tests:` to `data_tests:`; accept both.
    tests = raw.get("data_tests", raw.get("tests", [])) or []
    for t in tests:
        if isinstance(t, str):
            name, spec = t, {}
        elif isinstance(t, dict) and len(t) == 1:
            name, spec = next(iter(t.items()))
        else:
            col.skipped_tests.append(str(t))
            continue

        args = _test_args(spec)
        if name == "unique":
            col.unique = True
        elif name == "not_null":
            col.not_null = True
        elif name == "accepted_values":
            values = args.get("values")
            if isinstance(values, list) and values:
                col.accepted_values = values
        elif name == "relationships":
            target = _parse_ref(args.get("to", ""))
            fld = args.get("field")
            if target and fld:
                col.relationship = (target, str(fld))
            else:
                col.skipped_tests.append(f"relationships({args.get('to')})")
        else:
            # dbt_utils.*, custom generic tests, etc.
            col.skipped_tests.append(str(name))
    return col


def parse_dbt_properties(project: DbtProjectInfo) -> Tuple[List[DbtEntitySpec], int]:
    """Scan a dbt project's model and seed paths for properties YAML files.

    Returns (entities, yml_files_read). Both ``models:`` and ``seeds:``
    sections are collected; ``sources:`` are ignored (they describe data that
    already exists in a warehouse, not something to seed).
    """
    search_dirs: List[Path] = []
    for p in project.model_paths:
        search_dirs.append(project.project_root / p)
    search_dirs.append(project.seeds_dir_abs)

    entities: List[DbtEntitySpec] = []
    files_read = 0
    seen: set = set()

    for base in search_dirs:
        if not base.is_dir():
            continue
        for yml in sorted(list(base.rglob("*.yml")) + list(base.rglob("*.yaml"))):
            if yml in seen:
                continue
            seen.add(yml)
            try:
                data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            found_section = False
            for section, rtype in (("seeds", "seed"), ("models", "model")):
                for raw in data.get(section) or []:
                    if not isinstance(raw, dict) or not raw.get("name"):
                        continue
                    found_section = True
                    entities.append(DbtEntitySpec(
                        name=str(raw["name"]),
                        resource_type=rtype,
                        source_file=yml,
                        description=raw.get("description"),
                        columns=[
                            _parse_column(c)
                            for c in (raw.get("columns") or [])
                            if isinstance(c, dict) and c.get("name")
                        ],
                    ))
            if found_section:
                files_read += 1

    return entities, files_read


# ---------------------------------------------------------------------------
# Translation to a Misata schema
# ---------------------------------------------------------------------------

_DATA_TYPE_MAP: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"bool"), "boolean"),
    (re.compile(r"^(big|small|tiny)?int|^integer|^serial"), "int"),
    (re.compile(r"float|double|real|numeric|decimal|number"), "float"),
    (re.compile(r"^timestamp|^datetime"), "datetime"),
    (re.compile(r"^date$"), "date"),
    (re.compile(r"^time$"), "time"),
    (re.compile(r"char|text|string|varchar"), "text"),
]


def _map_data_type(data_type: str) -> Optional[str]:
    for pattern, misata_type in _DATA_TYPE_MAP:
        if pattern.search(data_type):
            return misata_type
    return None


def _looks_like_id(name: str) -> bool:
    return name == "id" or name.endswith("_id")


def build_schema_from_dbt(
    entities: List[DbtEntitySpec],
    *,
    project_name: str = "dbt project",
    rows: int = 200,
    seed: int = 42,
    target: str = "auto",
) -> Tuple["SchemaConfig", DbtImportReport]:
    """Translate parsed dbt entities into a generatable Misata schema.

    Args:
        entities:     Output of :func:`parse_dbt_properties`.
        project_name: For the schema's name field.
        rows:         Row count per generated table.
        seed:         Random seed.
        target:       ``"seeds"``, ``"models"``, ``"all"``, or ``"auto"``
                      (seeds if any are declared, else models).

    Returns:
        (schema_config, report)
    """
    from misata.schema import Column, Relationship, SchemaConfig, Table
    from misata.semantic import SemanticInference

    report = DbtImportReport(entities=entities)

    if target == "auto":
        target = "seeds" if any(e.resource_type == "seed" for e in entities) else "models"
    if target == "seeds":
        chosen = [e for e in entities if e.resource_type == "seed"]
    elif target == "models":
        chosen = [e for e in entities if e.resource_type == "model"]
    else:
        chosen = list(entities)

    # Deduplicate by name (a table may be declared in several files; merge columns)
    by_name: Dict[str, DbtEntitySpec] = {}
    for e in chosen:
        if e.name in by_name:
            existing_cols = {c.name for c in by_name[e.name].columns}
            by_name[e.name].columns.extend(
                c for c in e.columns if c.name not in existing_cols
            )
        else:
            by_name[e.name] = e
    chosen = list(by_name.values())
    target_names = {e.name for e in chosen}
    report.targets = sorted(target_names)

    inference = SemanticInference()
    tables: List[Table] = []
    columns: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    for entity in chosen:
        cols: List[Column] = []
        for spec in entity.columns:
            report.skipped_tests.extend(spec.skipped_tests)
            if spec.unique:
                report.unique_translated += 1
            if spec.not_null:
                report.not_null_translated += 1

            # 1. relationships test → FK column
            if spec.relationship is not None:
                parent, parent_key = spec.relationship
                if parent in target_names:
                    relationships.append(Relationship(
                        parent_table=parent,
                        child_table=entity.name,
                        parent_key=parent_key,
                        child_key=spec.name,
                    ))
                    report.relationships_translated += 1
                    cols.append(Column(
                        name=spec.name, type="foreign_key",
                        nullable=False, unique=spec.unique,
                        description=spec.description,
                    ))
                    continue
                report.warnings.append(
                    f"'{entity.name}.{spec.name}' references '{parent}' which is "
                    f"not among the generated tables; generating as a plain id."
                )
                cols.append(Column(
                    name=spec.name, type="int",
                    distribution_params={"min": 1, "max": max(rows, 1)},
                    nullable=False, unique=spec.unique,
                ))
                continue

            # 2. accepted_values → categorical restricted to exactly those values
            if spec.accepted_values:
                report.accepted_values_translated += 1
                cols.append(Column(
                    name=spec.name, type="categorical",
                    distribution_params={"choices": list(spec.accepted_values)},
                    nullable=False, unique=spec.unique,
                    description=spec.description,
                ))
                continue

            # 3. declared data_type
            misata_type: Optional[str] = None
            params: Dict[str, Any] = {}
            if spec.data_type:
                misata_type = _map_data_type(spec.data_type)

            # 4. semantic name inference (email, *_date, first_name, price, …)
            if misata_type in (None, "text", "int", "float"):
                inferred = inference.infer_column(spec.name)
                if inferred is not None:
                    inferred_type, inferred_params = inferred
                    # A declared numeric/text type wins over a conflicting guess,
                    # but inference fills in useful params for matching types
                    # and decides entirely for undeclared columns.
                    if misata_type is None or inferred_type == misata_type:
                        misata_type, params = inferred_type, inferred_params

            # 5. id-looking columns default to sequential ints
            if misata_type is None and _looks_like_id(spec.name):
                misata_type = "int"
                params = {"min": 1, "max": max(rows * 10, 1000)}

            if misata_type is None:
                misata_type = "text"

            if misata_type == "date" and (
                spec.data_type == "date"
                or spec.name == "date"
                or spec.name.endswith("_date")
            ):
                report.date_only_columns.append((entity.name, spec.name))

            cols.append(Column(
                name=spec.name, type=misata_type,
                distribution_params=params,
                nullable=False,
                unique=spec.unique or (spec.name == "id" and misata_type == "int"),
                description=spec.description,
            ))

        # A referenced parent key must exist even if its yml omits the column
        needed_keys = {
            r.parent_key for r in relationships if r.parent_table == entity.name
        }
        declared = {c.name for c in cols}
        for key in sorted(needed_keys - declared):
            cols.append(Column(name=key, type="int", unique=True, nullable=False))

        if not cols:
            report.warnings.append(
                f"'{entity.name}' declares no columns in its properties file; skipped."
            )
            continue

        tables.append(Table(
            name=entity.name,
            row_count=rows,
            description=entity.description,
            columns=[c.name for c in cols],
        ))
        columns[entity.name] = cols

    # Late pass: relationships found after the parent table was built
    for rel in relationships:
        parent_cols = columns.get(rel.parent_table)
        if parent_cols is not None and rel.parent_key not in {c.name for c in parent_cols}:
            parent_cols.append(Column(
                name=rel.parent_key, type="int", unique=True, nullable=False,
            ))
            for t in tables:
                if t.name == rel.parent_table:
                    t.columns.append(rel.parent_key)

    # Drop relationships whose parent table ended up skipped (no columns)
    built = {t.name for t in tables}
    relationships = [
        r for r in relationships
        if r.parent_table in built and r.child_table in built
    ]

    schema = SchemaConfig(
        name=f"{project_name} seeds",
        description=f"Generated by misata from the dbt project's schema.yml contract",
        tables=tables,
        columns=columns,
        relationships=relationships,
        seed=seed,
    )
    return schema, report


def apply_date_only_columns(tables: Dict[str, Any], report: DbtImportReport) -> None:
    """Strip time parts from columns dbt declared as plain dates (in place)."""
    import pandas as pd

    for table_name, column_name in report.date_only_columns:
        df = tables.get(table_name)
        if df is not None and column_name in df.columns:
            df[column_name] = (
                pd.to_datetime(df[column_name], errors="coerce").dt.strftime("%Y-%m-%d")
            )


def build_schema_from_dbt_project(
    project_dir: Optional[Path] = None,
    *,
    rows: int = 200,
    seed: int = 42,
    target: str = "auto",
) -> Tuple["SchemaConfig", DbtImportReport]:
    """One-call convenience: detect + parse + translate a dbt project.

    Raises ``FileNotFoundError`` if no ``dbt_project.yml`` is found, and
    ``ValueError`` if the project declares no seed/model columns to build from.
    """
    project = detect_dbt_project(project_dir)
    if project is None:
        raise FileNotFoundError(
            f"No dbt_project.yml found at or above {project_dir or Path.cwd()}"
        )

    entities, files_read = parse_dbt_properties(project)
    usable = [e for e in entities if e.columns]
    if not usable:
        raise ValueError(
            f"dbt project '{project.project_name}' declares no seed or model "
            f"columns in its properties files; nothing to generate from. "
            f"Declare columns (and tests) in a schema.yml, or use "
            f"`misata dbt-seed --story ...` instead."
        )

    schema, report = build_schema_from_dbt(
        entities,
        project_name=project.project_name,
        rows=rows,
        seed=seed,
        target=target,
    )
    report.yml_files_read = files_read
    return schema, report
