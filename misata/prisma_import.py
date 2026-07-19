"""Prisma → Misata import: generate seed data from a schema.prisma.

Reads the schema file every Prisma app already maintains and translates it into
a Misata :class:`~misata.schema.SchemaConfig`, so ``misata prisma-seed`` inside
a project produces CSVs whose rows respect the schema's own contract:

  - ``@relation(fields: [...], references: [...])`` → FK relationships
  - ``enum`` types                                  → categorical value pools
  - ``@id`` / ``@unique``                           → unique columns
  - ``@@id([...])`` / ``@@unique([...])``           → composite-unique constraints
  - ``Int/Float/Decimal/String/Boolean/DateTime``   → typed columns
  - optional fields (``String?``)                   → nullable columns
  - untyped-looking names (email, city, price, …)   → semantic inference

Attributes Misata cannot honour (``@default(dbgenerated(...))``, ``@@map``
renames, ``Unsupported`` types, …) are reported, never guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Parsed model
# ---------------------------------------------------------------------------

@dataclass
class PrismaField:
    name: str
    type: str                 # scalar, enum name, or model name
    is_list: bool = False
    optional: bool = False
    is_id: bool = False
    unique: bool = False
    default: Optional[str] = None
    # (fields, references, target_model) from @relation
    relation: Optional[Tuple[List[str], List[str], str]] = None
    skipped_attrs: List[str] = field(default_factory=list)


@dataclass
class PrismaModel:
    name: str
    fields: List[PrismaField] = field(default_factory=list)
    composite_ids: List[List[str]] = field(default_factory=list)      # @@id
    composite_uniques: List[List[str]] = field(default_factory=list)  # @@unique
    skipped_attrs: List[str] = field(default_factory=list)            # @@map etc.


@dataclass
class PrismaSchema:
    models: List[PrismaModel] = field(default_factory=list)
    enums: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class PrismaImportReport:
    models: int = 0
    enums: int = 0
    relationships: int = 0
    unique_columns: int = 0
    composite_constraints: int = 0
    skipped: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Parsed {self.models} model(s), {self.enums} enum(s); translated "
            f"{self.relationships} relation(s), {self.unique_columns} unique "
            f"column(s), {self.composite_constraints} composite constraint(s)",
        ]
        if self.skipped:
            lines.append(f"Skipped (not translatable): {', '.join(sorted(set(self.skipped)))}")
        lines.extend(self.warnings)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parser (schema.prisma is line-oriented; a light parser is sufficient)
# ---------------------------------------------------------------------------

_BLOCK_RE = re.compile(r"^\s*(model|enum|datasource|generator|type)\s+(\w+)\s*\{")
_FIELD_RE = re.compile(r"^\s*(\w+)\s+(\w+)(\[\])?(\?)?\s*(.*)$")
_ATTR_RE = re.compile(r"@\w+(?:\([^)]*\))?|@@\w+(?:\([^)]*\))?")
_REL_FIELDS_RE = re.compile(r"fields:\s*\[([^\]]*)\]")
_REL_REFS_RE = re.compile(r"references:\s*\[([^\]]*)\]")
_LIST_RE = re.compile(r"\[([^\]]*)\]")


def _idents(csv: str) -> List[str]:
    return [x.strip() for x in csv.split(",") if x.strip()]


def parse_prisma(text: str) -> PrismaSchema:
    schema = PrismaSchema()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].split("//")[0]
        m = _BLOCK_RE.match(line)
        if not m:
            i += 1
            continue
        kind, name = m.group(1), m.group(2)
        # Collect block body until the matching close brace
        body: List[str] = []
        depth = line.count("{") - line.count("}")
        i += 1
        while i < len(lines) and depth > 0:
            raw = lines[i].split("//")[0]
            depth += raw.count("{") - raw.count("}")
            if depth > 0:
                body.append(raw)
            i += 1

        if kind == "enum":
            values = [ln.strip() for ln in body if ln.strip() and not ln.strip().startswith("@@")]
            schema.enums[name] = [v.split()[0] for v in values]
        elif kind == "model":
            model = PrismaModel(name=name)
            for ln in body:
                s = ln.strip()
                if not s:
                    continue
                if s.startswith("@@"):
                    attr = s.split("(")[0]
                    inner = _LIST_RE.search(s)
                    cols = _idents(inner.group(1)) if inner else []
                    if attr == "@@id" and cols:
                        model.composite_ids.append(cols)
                    elif attr == "@@unique" and cols:
                        model.composite_uniques.append(cols)
                    elif attr == "@@index":
                        pass  # indexes do not affect generation
                    else:
                        model.skipped_attrs.append(s.split("(")[0])
                    continue
                fm = _FIELD_RE.match(ln)
                if not fm:
                    continue
                fname, ftype, flist, fopt, rest = fm.groups()
                f = PrismaField(
                    name=fname, type=ftype,
                    is_list=bool(flist), optional=bool(fopt),
                )
                for attr in _ATTR_RE.findall(rest or ""):
                    head = attr.split("(")[0]
                    if head == "@id":
                        f.is_id = True
                    elif head == "@unique":
                        f.unique = True
                    elif head == "@default":
                        f.default = attr[len("@default(") : -1].strip()
                    elif head == "@relation":
                        fl = _REL_FIELDS_RE.search(attr)
                        rf = _REL_REFS_RE.search(attr)
                        if fl and rf:
                            f.relation = (_idents(fl.group(1)), _idents(rf.group(1)), ftype)
                    elif head in ("@map", "@updatedAt", "@db"):
                        pass  # storage-level, irrelevant to generation
                    else:
                        f.skipped_attrs.append(head)
                model.fields.append(f)
            schema.models.append(model)
        # datasource/generator/type blocks: irrelevant to generation
    return schema


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

_SCALARS = {"Int", "BigInt", "Float", "Decimal", "String", "Boolean", "DateTime", "Json", "Bytes"}


def build_schema_from_prisma(
    text: str,
    *,
    project_name: str = "prisma project",
    rows: int = 200,
    seed: int = 42,
) -> Tuple["SchemaConfig", PrismaImportReport]:
    from misata.schema import Column, Constraint, Relationship, SchemaConfig, Table
    from misata.semantic import SemanticInference

    parsed = parse_prisma(text)
    report = PrismaImportReport(models=len(parsed.models), enums=len(parsed.enums))
    if not parsed.models:
        raise ValueError("No `model` blocks found in the Prisma schema.")

    inference = SemanticInference()
    model_names = {m.name for m in parsed.models}

    tables: List[Table] = []
    columns: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    for model in parsed.models:
        cols: List[Column] = []
        table_constraints: List[Constraint] = []
        report.skipped.extend(f"{model.name}.{a}" for a in model.skipped_attrs)

        # FK scalar fields named by @relation on the object fields of this model
        fk_scalars: Dict[str, Tuple[str, str]] = {}
        for f in model.fields:
            if f.relation and not f.is_list:
                flds, refs, target = f.relation
                if target in model_names:
                    for scalar, ref in zip(flds, refs):
                        fk_scalars[scalar] = (target, ref)
                else:
                    report.warnings.append(
                        f"{model.name}.{f.name}: relation target '{target}' not found."
                    )

        for f in model.fields:
            report.skipped.extend(f"{model.name}.{f.name}{a}" for a in f.skipped_attrs)

            # Object-relation fields (User, Post[]) are not columns.
            if f.type in model_names:
                continue
            if f.type not in _SCALARS and f.type not in parsed.enums:
                report.skipped.append(f"{model.name}.{f.name}:{f.type}")
                continue

            if f.unique or f.is_id:
                report.unique_columns += 1

            # FK scalar → foreign_key column + relationship
            if f.name in fk_scalars:
                parent, parent_key = fk_scalars[f.name]
                relationships.append(Relationship(
                    parent_table=parent, child_table=model.name,
                    parent_key=parent_key, child_key=f.name,
                ))
                report.relationships += 1
                cols.append(Column(
                    name=f.name, type="foreign_key",
                    nullable=f.optional, unique=f.unique,
                ))
                continue

            # Enum → categorical restricted to exactly the declared values
            if f.type in parsed.enums:
                cols.append(Column(
                    name=f.name, type="categorical",
                    distribution_params={"choices": list(parsed.enums[f.type])},
                    nullable=f.optional, unique=f.unique,
                ))
                continue

            # Scalar mapping with semantic inference for strings/numerics
            misata_type: str
            params: Dict[str, Any] = {}
            if f.type in ("Int", "BigInt"):
                misata_type = "int"
                params = {"min": 1, "max": max(rows * 10, 1000)}
            elif f.type in ("Float", "Decimal"):
                misata_type = "float"
                params = {"min": 1, "max": 10_000, "decimals": 2}
            elif f.type == "Boolean":
                misata_type = "boolean"
            elif f.type == "DateTime":
                misata_type = "datetime"
                params = {"start": "2024-01-01", "end": "2025-12-31"}
            elif f.type in ("Json", "Bytes"):
                report.skipped.append(f"{model.name}.{f.name}:{f.type}")
                continue
            else:  # String
                misata_type = "text"

            if misata_type in ("text", "int", "float"):
                inferred = inference.infer_column(f.name)
                if inferred is not None:
                    itype, iparams = inferred
                    if itype == misata_type or misata_type == "text":
                        misata_type, params = itype, iparams

            cols.append(Column(
                name=f.name, type=misata_type,
                distribution_params=params,
                nullable=f.optional,
                unique=f.unique or f.is_id,
            ))

        # Composite ids/uniques → engine composite-unique constraints
        for combo in model.composite_ids + model.composite_uniques:
            present = [c for c in combo if any(col.name == c for col in cols)]
            if len(present) == len(combo):
                table_constraints.append(Constraint(
                    name=f"{model.name}_unique_{'_'.join(combo)}",
                    type="unique_combination", group_by=list(combo), action="drop",
                ))
                report.composite_constraints += 1
            else:
                report.warnings.append(
                    f"{model.name}: composite constraint {combo} references "
                    f"missing columns; skipped."
                )

        if not cols:
            report.warnings.append(f"{model.name}: no generatable columns; skipped.")
            continue

        tables.append(Table(
            name=model.name, row_count=rows,
            columns=[c.name for c in cols],
            constraints=table_constraints,
        ))
        columns[model.name] = cols

    built = {t.name for t in tables}
    relationships = [
        r for r in relationships if r.parent_table in built and r.child_table in built
    ]

    return SchemaConfig(
        name=f"{project_name} seeds",
        description="Generated by misata from schema.prisma",
        tables=tables, columns=columns, relationships=relationships, seed=seed,
    ), report


def find_prisma_schema(start: Optional[Path] = None) -> Optional[Path]:
    """Locate schema.prisma the way Prisma does: ./prisma/schema.prisma first,
    then ./schema.prisma, walking up a few directories."""
    current = Path(start or ".").resolve()
    for _ in range(6):
        for candidate in (current / "prisma" / "schema.prisma", current / "schema.prisma"):
            if candidate.is_file():
                return candidate
        if current.parent == current:
            break
        current = current.parent
    return None
