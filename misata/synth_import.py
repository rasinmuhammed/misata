"""synth → Misata import: generate from a synth namespace directory.

synth (`shuttle-hq/synth`, "The Declarative Data Generator") stopped receiving
commits on 27 September 2024 and its documentation site now returns a 404, so
the people still running it have a working namespace and nowhere to take it.
This reads that namespace and writes the equivalent Misata schema.

A synth namespace is a directory of JSON files, one per collection, each shaped
``{"type": "array", "length": N, "content": {"type": "object", ...}}``. The
translation:

  - filename                              → table name
  - ``length``                            → row count
  - ``{"type": "number", "id": {}}``      → unique integer key
  - ``range`` / ``constant``              → numeric bounds
  - ``{"type": "string", "faker": {...}}``→ semantic column (email, name, …)
  - ``categorical``                       → weighted value pool
  - ``date_time`` begin/end               → dated column
  - ``bool`` frequency                    → boolean at that rate
  - ``same_as`` and ``"@Table.content.f"``→ foreign key relationships
  - ``one_of`` with a ``null`` variant    → nullable column

Constructs with no Misata equivalent, notably ``pattern`` regexes, ``series``,
and ``hidden`` fields, are reported rather than approximated. A silent wrong
guess is worse than a line in a report telling you to look.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from misata.schema import Column, Relationship, SchemaConfig, Table

# synth leans on the Rust `fake` crate; these are the generators that have a
# direct Misata equivalent. Anything absent falls back to free text and is
# named in the report.
_FAKER_SUBTYPE = {
    "safe_email": "email", "free_email": "email", "email": "email",
    "name": "name", "first_name": "first_name", "last_name": "last_name",
    "username": "username", "user_name": "username",
    "city": "city", "city_name": "city",
    "state_name": "state", "state_abbr": "state",
    "zip_code": "zipcode", "post_code": "zipcode", "postcode": "zipcode",
    "country_name": "country", "country_code": "country",
    "phone_number": "phone", "cell_number": "phone",
    "street_name": "address", "street_address": "address", "address": "address",
    "company_name": "company", "company": "company", "bs": "company",
    "job_title": "job", "title": "job", "profession": "job",
    "currency_code": "currency", "currency_name": "currency",
    "domain_suffix": "url", "url": "url",
}

_REF = re.compile(r"^@?(?P<table>[A-Za-z0-9_]+)\.content\.(?P<column>[A-Za-z0-9_.]+)$")


@dataclass
class SynthReport:
    """What was translated, and what could not be."""
    tables: int = 0
    columns: int = 0
    relationships: int = 0
    unsupported: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def add_unsupported(self, where: str, why: str) -> None:
        self.unsupported.append(f"{where}: {why}")


def find_synth_namespace(start: Optional[Path] = None) -> Optional[Path]:
    """Locate a namespace directory, the way `synth generate <dir>` expects one.

    Looks for ./synth, then the current directory, then walks upward. A
    directory counts only if it holds at least one JSON file whose top level is
    a synth collection, so a folder of unrelated JSON is not mistaken for one.
    """
    here = (start or Path.cwd()).resolve()
    for base in [here, *here.parents]:
        for candidate in (base / "synth", base):
            if candidate.is_dir() and _looks_like_namespace(candidate):
                return candidate
        if base == base.parent:
            break
    return None


def _looks_like_namespace(path: Path) -> bool:
    for f in path.glob("*.json"):
        try:
            doc = json.loads(f.read_text())
        except Exception:
            continue
        if isinstance(doc, dict) and doc.get("type") == "array" and "content" in doc:
            return True
    return False


def _row_count(length: Any, default: int) -> int:
    """synth writes `length` as a bare number or as a generator node."""
    if isinstance(length, (int, float)):
        return max(1, int(length))
    if isinstance(length, dict):
        if "constant" in length:
            return max(1, int(length["constant"]))
        rng = length.get("range") or {}
        if "low" in rng:
            return max(1, int(rng.get("high", rng["low"])))
    return default


def _strip_null_variant(node: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """A `one_of` whose variants include `null` is synth's way of saying
    nullable. Return the surviving variant and whether null was among them."""
    variants = [v for v in node.get("variants", []) if isinstance(v, dict)]
    non_null = [v for v in variants if v.get("type") != "null"]
    nullable = len(non_null) < len(variants)
    if len(non_null) == 1:
        return non_null[0], nullable
    return node, nullable


def _field_to_column(name: str, node: Any, table: str,
                     report: SynthReport) -> Tuple[Optional[Column], Optional[Tuple[str, str]]]:
    """Translate one synth field. Returns (column, foreign_key_target)."""
    # The `"@Table.content.field"` shorthand for a reference.
    if isinstance(node, str):
        m = _REF.match(node)
        if m:
            return (Column(name=name, type="foreign_key",
                           distribution_params={
                               "references": f"{m.group('table')}.{m.group('column')}"}),
                    (m.group("table"), m.group("column")))
        report.add_unsupported(f"{table}.{name}", f"unrecognised shorthand {node!r}")
        return None, None

    if not isinstance(node, dict):
        report.add_unsupported(f"{table}.{name}", "not a generator node")
        return None, None

    nullable = False
    if node.get("type") == "one_of":
        node, nullable = _strip_null_variant(node)
        if node.get("type") == "one_of":
            constants = [v.get("constant") for v in node.get("variants", [])
                         if isinstance(v, dict) and "constant" in v]
            if constants:
                weights = [float(v.get("weight", 1))
                           for v in node.get("variants", []) if "constant" in v]
                total = sum(weights) or 1.0
                return (Column(name=name, type="categorical", nullable=nullable,
                               distribution_params={
                                   "choices": constants,
                                   "weights": [w / total for w in weights]}),
                        None)
            report.add_unsupported(
                f"{table}.{name}",
                "one_of over several generator types, which has no single "
                "column equivalent; imported as free text")
            return Column(name=name, type="text", nullable=nullable), None

    t = node.get("type")

    if t == "same_as":
        ref = node.get("ref", "")
        m = _REF.match(ref)
        if m:
            return (Column(name=name, type="foreign_key", nullable=nullable,
                           distribution_params={
                               "references": f"{m.group('table')}.{m.group('column')}"}),
                    (m.group("table"), m.group("column")))
        report.add_unsupported(f"{table}.{name}", f"same_as ref {ref!r} not understood")
        return None, None

    if t == "number":
        if "id" in node:
            return Column(name=name, type="int", unique=True, nullable=False), None
        subtype = str(node.get("subtype", "i64"))
        is_float = subtype.startswith("f")
        params: Dict[str, Any] = {}
        if "constant" in node:
            params["min"] = params["max"] = node["constant"]
        rng = node.get("range")
        if isinstance(rng, dict):
            if "low" in rng:
                params["min"] = rng["low"]
            if "high" in rng:
                params["max"] = rng["high"]
        return Column(name=name, type="float" if is_float else "int",
                      nullable=nullable, distribution_params=params), None

    if t == "string":
        faker = node.get("faker")
        if isinstance(faker, dict):
            gen = str(faker.get("generator", ""))
            subtype = _FAKER_SUBTYPE.get(gen)
            if subtype:
                return Column(name=name, type="text", nullable=nullable,
                              distribution_params={"subtype": subtype}), None
            report.notes.append(
                f"{table}.{name}: faker generator {gen!r} has no direct "
                f"equivalent, imported as free text")
            return Column(name=name, type="text", nullable=nullable), None
        categorical = node.get("categorical")
        if isinstance(categorical, dict) and categorical:
            total = sum(float(v) for v in categorical.values()) or 1.0
            return Column(name=name, type="categorical", nullable=nullable,
                          distribution_params={
                              "choices": list(categorical.keys()),
                              "weights": [float(v) / total
                                          for v in categorical.values()]}), None
        if "pattern" in node:
            report.add_unsupported(
                f"{table}.{name}",
                f"regex pattern {node['pattern']!r} is not supported; the "
                f"column is imported as free text and needs a real declaration")
            return Column(name=name, type="text", nullable=nullable), None
        return Column(name=name, type="text", nullable=nullable), None

    if t == "date_time":
        params = {}
        if node.get("begin"):
            params["start"] = str(node["begin"])[:10]
        if node.get("end"):
            params["end"] = str(node["end"])[:10]
        return Column(name=name, type="datetime", nullable=nullable,
                      distribution_params=params), None

    if t == "bool":
        freq = node.get("frequency")
        params = {"probability": float(freq)} if freq is not None else {}
        return Column(name=name, type="boolean", nullable=nullable,
                      distribution_params=params), None

    if t == "hidden":
        report.notes.append(
            f"{table}.{name}: hidden field skipped, since synth generates it "
            f"without emitting it")
        return None, None

    if t == "series":
        report.add_unsupported(
            f"{table}.{name}",
            "series (event timing) has no direct import; Misata expresses this "
            "with time grids and rate curves, which have to be declared")
        return None, None

    if t == "null":
        return Column(name=name, type="text", nullable=True), None

    report.add_unsupported(f"{table}.{name}", f"unhandled synth type {t!r}")
    return None, None


def build_schema_from_synth(
    namespace: Path,
    project_name: str = "synth",
    default_rows: int = 500,
    scale: float = 1.0,
) -> Tuple[SchemaConfig, SynthReport]:
    """Read a synth namespace directory and build a Misata SchemaConfig."""
    report = SynthReport()
    tables: List[Table] = []
    columns: Dict[str, List[Column]] = {}
    pending_fks: List[Tuple[str, str, str, str]] = []

    files = sorted(p for p in namespace.glob("*.json"))
    if not files:
        raise ValueError(f"no JSON collections found in {namespace}")

    for path in files:
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            report.add_unsupported(path.name, f"invalid JSON ({e.msg})")
            continue
        if not isinstance(doc, dict) or doc.get("type") != "array":
            report.add_unsupported(path.name, "not a synth collection")
            continue

        table_name = path.stem
        content = doc.get("content")
        if not isinstance(content, dict) or content.get("type") != "object":
            report.add_unsupported(
                path.name,
                f"collection content is {content.get('type') if isinstance(content, dict) else 'missing'!r}, "
                f"not an object, so it has no columns to import")
            continue

        rows = max(1, int(_row_count(doc.get("length"), default_rows) * scale))
        cols: List[Column] = []
        for field_name, node in content.items():
            if field_name == "type":
                continue
            col, fk = _field_to_column(field_name, node, table_name, report)
            if col is None:
                continue
            cols.append(col)
            if fk:
                pending_fks.append((table_name, field_name, fk[0], fk[1]))

        if not cols:
            report.add_unsupported(path.name, "no importable columns")
            continue

        # synth's `{"id": {}}` is a sequential counter, so the imported column
        # is unique by construction. Say so explicitly: left to a default
        # distribution, a unique integer column is asked to draw N distinct
        # values from a shape that was never bounded to hold them.
        for col in cols:
            params = col.distribution_params or {}
            unset = not {k for k in params
                         if k not in ("distribution", "_distribution_is_default")}
            if col.type == "int" and col.unique and unset:
                col.distribution_params = {"distribution": "uniform",
                                           "min": 1, "max": max(rows, 2)}

        tables.append(Table(name=table_name, row_count=rows))
        columns[table_name] = cols
        report.columns += len(cols)

    report.tables = len(tables)
    known = {t.name for t in tables}

    relationships: List[Relationship] = []
    for child, child_col, parent, parent_col in pending_fks:
        if parent not in known:
            report.add_unsupported(
                f"{child}.{child_col}",
                f"references collection {parent!r}, which is not in this namespace")
            continue
        relationships.append(Relationship(
            parent_table=parent, child_table=child,
            parent_key=parent_col, child_key=child_col))
    report.relationships = len(relationships)

    schema = SchemaConfig(
        name=project_name,
        tables=tables,
        columns=columns,
        relationships=relationships,
        description=f"Imported from the synth namespace at {namespace}",
    )
    return schema, report
