"""What a schema will do, before a row is generated.

:func:`explain` gathers, in one JSON-able object, everything Misata decides
about a schema up front: the tables and how many rows each will get, the
declarations and the columns each one writes, the conflicts that would make
generation refuse, the conformance preview of every outcome curve, and the
invariants an attestation of the output will check. Nothing is generated.

    >>> report = misata.explain(schema)
    >>> report.will_generate
    True
    >>> print(report.summary())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from misata.schema import SchemaConfig

#: In-memory bytes per value, by column type, as pandas holds them. Text and
#: categories are Python strings: a 49-byte object header, the characters,
#: and the 8-byte pointer in the column.
_BYTES_PER_VALUE = {
    "int": 8, "float": 8, "date": 8, "datetime": 8, "time": 8, "foreign_key": 8,
    "boolean": 1, "categorical": 66, "text": 90, "json": 120, "array": 120,
}
_DEFAULT_BYTES = 66


@dataclass
class Explanation:
    """The plan for one schema. ``to_dict()`` is what the CLI and MCP tool return."""

    name: str
    seed: Any
    tables: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    declarations: List[Dict[str, Any]] = field(default_factory=list)
    writers: Dict[str, List[str]] = field(default_factory=dict)
    overlaps: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Any] = field(default_factory=list)
    conformance: Dict[str, Any] = field(default_factory=dict)
    invariants: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def will_generate(self) -> bool:
        """False when generation would refuse with ``InfeasibleSchema``."""
        return not self.conflicts

    @property
    def total_rows(self) -> int:
        return sum(int(t["rows"]) for t in self.tables)

    @property
    def estimated_bytes(self) -> int:
        """Approximate in-memory size of every table held at once.

        ``generate_from_schema`` returns all tables together, so this is the
        floor of its peak memory. ``generate_stream`` holds one batch at a time.
        """
        return sum(int(t["estimated_bytes"]) for t in self.tables)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "seed": self.seed,
            "will_generate": self.will_generate,
            "total_rows": self.total_rows,
            "estimated_bytes": self.estimated_bytes,
            "tables": self.tables,
            "relationships": self.relationships,
            "declarations": self.declarations,
            "writers": self.writers,
            "overlaps": self.overlaps,
            "conflicts": [{"kind": c.kind, "where": c.where,
                           "declarations": list(c.declarations),
                           "arithmetic": c.arithmetic, "remedy": c.remedy}
                          for c in self.conflicts],
            "conformance": self.conformance,
            "invariants": self.invariants,
        }

    def summary(self) -> str:
        lines = [f"{self.name}: {len(self.tables)} table(s), {self.total_rows:,} rows, "
                 f"about {_megabytes(self.estimated_bytes)} in memory, seed {self.seed}"]
        for t in self.tables:
            note = f"  ({t['rows_from']})" if t["rows_from"] != "row_count" else ""
            lines.append(f"  {t['name']:<24} {t['rows']:>10,} rows  {t['columns']:>3} cols{note}")
        if self.declarations:
            lines.append("Declarations:")
            for d in self.declarations:
                lines.append(f"  {d['key']} x{d['count']}: {d['summary']}")
        for o in self.overlaps:
            lines.append(f"  ! {o['table']}.{o['column']}: {o['later']} runs after "
                         f"{o['earlier']}; {o['note']}")
        for warning in self.conformance.get("warnings", []):
            lines.append(f"  ! {warning}")
        lines.append(f"An attestation will check {len(self.invariants)} invariant(s).")
        if self.conflicts:
            lines.append(f"Generation would refuse: {len(self.conflicts)} conflict(s).")
        return "\n".join(lines)


def _megabytes(n: int) -> str:
    return f"{n / 1_000_000:,.1f} MB" if n >= 100_000 else f"{n / 1000:,.0f} kB"


def _declarations(schema: "SchemaConfig") -> List[Dict[str, Any]]:
    from misata.registry import DECLARATIONS

    out = []
    for decl in DECLARATIONS:
        if decl.key == "constraints":
            count = sum(len(getattr(t, "constraints", None) or []) for t in schema.tables)
        elif decl.key == "noise":
            count = int(bool(getattr(schema, "noise_config", None)))
        else:
            value = getattr(schema, decl.key, None)
            count = len(value) if isinstance(value, (list, dict)) else int(bool(value))
        if count:
            out.append({"key": decl.key, "count": count, "summary": decl.summary})
    return out


def _writers(schema: "SchemaConfig") -> Dict[str, List[str]]:
    """Each column a declaration writes, with its writers in the order they run."""
    from misata.composition import _claims

    by_column: Dict[str, List[Any]] = {}
    for claim in _claims(schema):
        if claim.writes:
            by_column.setdefault(f"{claim.table}.{claim.column}", []).append(claim)
    return {column: [c.declaration for c in sorted(claims, key=lambda c: c.rank)]
            for column, claims in sorted(by_column.items())}


def _tables(schema: "SchemaConfig", planned: Dict[str, int]) -> List[Dict[str, Any]]:
    out = []
    for table in schema.tables:
        columns = schema.get_columns(table.name) or []
        rows = planned.get(table.name, int(table.row_count or 0))
        per_row = sum(_BYTES_PER_VALUE.get(str(c.type), _DEFAULT_BYTES) for c in columns)
        out.append({
            "name": table.name,
            "rows": rows,
            "rows_from": "outcome curve plan" if table.name in planned else "row_count",
            "columns": len(columns),
            "estimated_bytes": rows * per_row,
        })
    return out


def explain(schema: "SchemaConfig") -> Explanation:
    """Everything Misata will do with ``schema``, without generating a row.

    Args:
        schema: A :class:`~misata.schema.SchemaConfig`, or the dict form
            :func:`misata.from_dict_schema` accepts.
    """
    from misata.attestation import derive_invariants
    from misata.composition import find_overlaps
    from misata.conformance import conformance_preview
    from misata.feasibility import find_conflicts

    if isinstance(schema, dict):
        from misata.compat import from_dict_schema
        schema = from_dict_schema(schema)

    conflicts = find_conflicts(schema)
    preview = conformance_preview(schema) if getattr(schema, "outcome_curves", None) else None
    planned: Dict[str, int] = {}
    for curve in preview.curves if preview else []:
        planned[curve.table] = max(planned.get(curve.table, 0), int(curve.total_rows))

    return Explanation(
        name=schema.name,
        seed=schema.seed,
        tables=_tables(schema, planned),
        relationships=[{"parent": r.parent_table, "child": r.child_table,
                        "parent_key": r.parent_key, "child_key": r.child_key}
                       for r in schema.relationships or []],
        declarations=_declarations(schema),
        writers=_writers(schema),
        overlaps=[{"table": o.table, "column": o.column, "earlier": o.earlier,
                   "later": o.later, "note": o.note}
                  for o in find_overlaps(schema)
                  if "may or may not be what was intended" not in o.note],
        conflicts=conflicts,
        conformance=preview.to_dict() if preview else {},
        invariants=[{"id": i.id, "kind": i.kind, "table": i.table, "expected": i.expected}
                    for i in (derive_invariants(schema) if not conflicts else [])],
    )
