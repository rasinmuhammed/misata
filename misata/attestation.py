"""Attest that a dataset holds what its schema declared.

An attestation is a standard in-toto Statement (v1) whose subjects are the
dataset's files, each pinned by SHA-256, and whose predicate is a Misata
certificate: every invariant the schema implies, as DuckDB SQL with the
declared answer and the answer observed in the written files.

    result = misata.attest("out/", schema)
    assert result.passed

``attest`` writes three files next to the data:

    attestation.intoto.json   the Statement, ready for ``cosign attest-blob``
                              or ``actions/attest``
    attestation.dsse.json     the same Statement in an unsigned DSSE envelope
    verify.py                 a standalone checker (standard library and
                              duckdb only) that recomputes every digest and
                              reruns every invariant

The invariants come from the declarations, never from the data: outcome-curve
totals and their row plan, rate anchors, foreign keys, unique columns, ledger
identities, group shares, waterfalls, row rules, minimum children per parent,
partitioned relationships and declared graph structure. Expected and observed values are
written as decimal strings at a fixed precision, so float formatting can never
decide equality. ``result`` is ``PASSED`` only when every invariant holds.

Signing is left to the tools built for it; see ``docs/guides/attest.md``.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Union

from pydantic import BaseModel

from misata import attestation_verify
from misata.attestation_verify import (PREDICATE_TYPE, STATEMENT_FILE, STATEMENT_TYPE,
                                       canonical_decimal)
from misata.exceptions import MisataError
from misata.sqlutil import quote_ident, quote_literal

if TYPE_CHECKING:  # pragma: no cover
    from misata.schema import SchemaConfig

__all__ = [
    "DSSE_FILE",
    "PAYLOAD_TYPE",
    "PREDICATE_TYPE",
    "STATEMENT_FILE",
    "AttestationError",
    "Attestation",
    "Invariant",
    "attest",
    "derive_invariants",
    "spec_reference",
    "to_odcs",
    "to_openlineage",
]

DSSE_FILE = "attestation.dsse.json"
PAYLOAD_TYPE = "application/vnd.in-toto+json"
TABLE_SUFFIXES = (".parquet", ".csv", ".jsonl")

PathLike = Union[str, Path]


class AttestationError(MisataError):
    """The dataset cannot be attested: missing tables or nothing to check."""


@dataclass(frozen=True)
class Invariant:
    """One declared property of the data, as SQL with the answer it must give."""

    id: str
    kind: str
    sql: str
    expected: str
    value_type: str  # "decimal" | "integer" | "boolean" | "string"
    table: str = ""
    comparator: str = "eq"  # "eq" | "within_tolerance"
    #: Relative tolerance as a decimal string, for ``within_tolerance`` only.
    tolerance: Optional[str] = None

    def to_predicate(self, observed: str, passed: bool) -> Dict[str, Any]:
        predicate = {
            "id": self.id,
            "kind": self.kind,
            "table": self.table,
            "sql": self.sql,
            "expected": self.expected,
            "observed": observed,
            "valueType": self.value_type,
            "comparator": self.comparator,
            "passed": passed,
        }
        if self.tolerance is not None:
            predicate["tolerance"] = self.tolerance
        return predicate


@dataclass
class Attestation:
    """The outcome of :func:`attest`."""

    directory: Path
    statement: Dict[str, Any]
    files: Dict[str, Path] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return bool(self.statement["predicate"]["result"] == "PASSED")

    @property
    def invariants(self) -> List[Dict[str, Any]]:
        return list(self.statement["predicate"]["invariants"])

    @property
    def failures(self) -> List[Dict[str, Any]]:
        return [i for i in self.invariants if not i["passed"]]

    def summary(self) -> str:
        invariants = self.invariants
        held = len(invariants) - len(self.failures)
        lines = [
            f"Attestation: {self.directory}",
            f"  result: {self.statement['predicate']['result']}",
            f"  files pinned: {len(self.statement['subject'])}",
            f"  invariants held: {held} of {len(invariants)}",
        ]
        for failure in self.failures:
            lines.append(f"  FAIL {failure['id']}: expected {failure['expected']}, "
                         f"observed {failure['observed']}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Invariants: derived from the declarations alone
# --------------------------------------------------------------------------- #

_VALUE_TYPES = {"number": "decimal", "integer": "integer", "string": "string"}


def _expected_string(value: Any, value_type: str, places: int) -> str:
    if value_type == "string":
        return str(value)
    return canonical_decimal(Decimal(str(value)), places if value_type == "decimal" else 0)


def _question_table(source: Dict[str, Any]) -> str:
    """The table a question is about; a relationship belongs to its child."""
    if "table" in source:
        return str(source["table"])
    return str(source.get("relationship", "")).split(".", 1)[0]


def _invariant_id(source: Dict[str, Any]) -> str:
    parts = [str(v).replace(" -> ", "->") for k, v in source.items() if k != "kind"]
    return ".".join(parts + [str(source.get("kind", "invariant"))])


def _rate_invariants(schema: "SchemaConfig") -> List[Invariant]:
    """A declared rate holds to the nearest row: the matching count is within
    one of rate times the window's row count, which is as exact as an integer
    count of rows can be."""
    from misata.evalpack import rate_anchors

    out = []
    for anchor in rate_anchors(schema):
        rc = anchor.rate_curve
        time_col = quote_ident(rc.time_column)
        start = quote_literal(str(anchor.start))
        end = quote_literal(str(anchor.end))
        sql = (
            f"SELECT ABS(SUM(CASE WHEN {quote_ident(rc.column)} = {quote_literal(rc.true_value)} "
            f"THEN 1 ELSE 0 END) - {anchor.rate!r} * COUNT(*)) < 1 "
            f"FROM {quote_ident(rc.table)} "
            f"WHERE {time_col} >= CAST({start} AS TIMESTAMP) "
            f"AND {time_col} < CAST({end} AS TIMESTAMP)"
        )
        out.append(Invariant(
            id=f"{rc.table}.{rc.column}.{anchor.period}.rate_curve_anchor",
            kind="rate_curve_anchor", sql=sql, expected="true", value_type="boolean",
            table=rc.table,
        ))
    return out


def _unique_invariants(schema: "SchemaConfig") -> List[Invariant]:
    out = []
    for table in schema.tables:
        for column in schema.get_columns(table.name):
            if not column.unique:
                continue
            col = quote_ident(column.name)
            out.append(Invariant(
                id=f"{table.name}.{column.name}.unique",
                kind="unique",
                sql=f"SELECT COUNT({col}) - COUNT(DISTINCT {col}) FROM {quote_ident(table.name)}",
                expected="0", value_type="integer", table=table.name,
            ))
    return out


_ROW_RULE_OPERATORS = {">", ">=", "<", "<="}


def _disturbed_columns(schema: "SchemaConfig") -> Optional[set]:
    """Columns a dirt declaration is meant to break; None when noise touches every column.

    Typos, outliers, missingness and late arrivals plant values outside a
    column's rules on purpose, so row-level rules are not attested there.
    """
    noise = schema.noise_config
    if noise is not None and noise.mode != "off" and (
            noise.null_rate or noise.outlier_rate or noise.typo_rate):
        return None
    disturbed = set()
    declarations: List[BaseModel] = [*schema.typos, *schema.outliers, *schema.missingness,
                                     *schema.late_arrivals]
    for declaration in declarations:
        table = getattr(declaration, "table", None)
        names = {c.name for c in schema.get_columns(table)} if table else set()
        for value in declaration.model_dump().values():
            for name in value if isinstance(value, list) else [value]:
                if isinstance(name, str) and name in names:
                    disturbed.add((table, name))
    return disturbed


def _row_rule_invariants(schema: "SchemaConfig") -> List[Invariant]:
    """Row-level rules the engine enforces by construction, each counted as violations.

    Declared inequalities and ranges between columns, a declared string
    domain (a DDL ``CHECK (... IN (...))`` or ``choices``) and a declared
    NOT NULL. A column's ``nullable`` counts only when it was set: the
    model's default of False is not a declaration.
    """
    disturbed = _disturbed_columns(schema)
    if disturbed is None:
        return []
    out = []

    def violations(table: str, name: str, where: str) -> Invariant:
        return Invariant(id=f"{table}.{name}", kind=name.rsplit(".", 1)[-1],
                         sql=f"SELECT COUNT(*) FROM {quote_ident(table)} WHERE {where}",
                         expected="0", value_type="integer", table=table)

    for table in schema.tables:
        columns = {c.name: c for c in schema.get_columns(table.name)}
        for rule in table.constraints:
            touched = {rule.column_a, rule.column_b, rule.column, rule.low_column,
                       rule.high_column} - {None}
            if not touched <= set(columns) or any((table.name, c) in disturbed for c in touched):
                continue
            if rule.type == "inequality" and rule.operator in _ROW_RULE_OPERATORS:
                a, b = quote_ident(str(rule.column_a)), quote_ident(str(rule.column_b))
                out.append(violations(
                    table.name, f"{rule.column_a}{rule.operator}{rule.column_b}.inequality",
                    f"{a} IS NOT NULL AND {b} IS NOT NULL AND NOT ({a} {rule.operator} {b})"))
            elif rule.type == "col_range":
                low, col = quote_ident(str(rule.low_column)), quote_ident(str(rule.column))
                high = quote_ident(str(rule.high_column))
                out.append(violations(
                    table.name, f"{rule.column}.col_range",
                    f"{col} IS NOT NULL AND NOT ({low} <= {col} AND {col} <= {high})"))
        for column in columns.values():
            if (table.name, column.name) in disturbed:
                continue
            col = quote_ident(column.name)
            if not column.nullable and "nullable" in column.model_fields_set:
                out.append(violations(table.name, f"{column.name}.not_null", f"{col} IS NULL"))
            choices = (column.distribution_params or {}).get("choices")
            if column.type == "categorical" and choices and all(
                    isinstance(c, str) for c in choices):
                domain = ", ".join(quote_literal(c) for c in choices)
                out.append(violations(
                    table.name, f"{column.name}.domain",
                    f"{col} IS NOT NULL AND CAST({col} AS VARCHAR) NOT IN ({domain})"))
    return out


def _min_children_invariants(schema: "SchemaConfig") -> List[Invariant]:
    """Every parent a relationship covers has at least its declared children."""
    out = []
    for rel in schema.relationships:
        if rel.min_children < 1 or rel.filters:
            continue
        parent, child = quote_ident(rel.parent_table), quote_ident(rel.child_table)
        pk, fk = quote_ident(rel.parent_key), quote_ident(rel.child_key)
        out.append(Invariant(
            id=f"{rel.parent_table}.{rel.parent_key}->{rel.child_table}.{rel.child_key}"
               f".min_children",
            kind="min_children",
            sql=(f"SELECT COUNT(*) FROM {parent} p LEFT JOIN (SELECT {fk} AS k, COUNT(*) AS n "
                 f"FROM {child} GROUP BY {fk}) c ON c.k = p.{pk} "
                 f"WHERE COALESCE(c.n, 0) < {int(rel.min_children)}"),
            expected="0", value_type="integer", table=rel.child_table,
        ))
    return out


def _partition_invariants(schema: "SchemaConfig") -> List[Invariant]:
    """A child shares every ``partition_by`` column with the parent it points at."""
    out = []
    for rel in schema.relationships:
        if not rel.partition_by:
            continue
        parent, child = quote_ident(rel.parent_table), quote_ident(rel.child_table)
        pk, fk = quote_ident(rel.parent_key), quote_ident(rel.child_key)
        differs = " OR ".join(f"p.{quote_ident(c)} IS DISTINCT FROM c.{quote_ident(c)}"
                              for c in rel.partition_by)
        out.append(Invariant(
            id=f"{rel.parent_table}.{rel.parent_key}->{rel.child_table}.{rel.child_key}"
               f".partition_by",
            kind="partition_by",
            sql=f"SELECT COUNT(*) FROM {child} c JOIN {parent} p ON p.{pk} = c.{fk} "
                f"WHERE {differs}",
            expected="0", value_type="integer", table=rel.child_table,
        ))
    return out


def acyclic_sql(table: str, from_column: str, to_column: str, where: str = "") -> str:
    """Count the nodes on or downstream of a cycle among an edge table's rows.

    Kahn's algorithm as a keyed recursive CTE: every node starts with its
    in-degree, and each round removes the nodes left with none, lowering
    their successors' counts. The rounds stop after the longest path whether
    or not a cycle exists, and a node still holding a count afterwards sits
    on a cycle or below one. Zero means the graph is acyclic. Needs DuckDB
    1.3 or later for ``USING KEY``.
    """
    src, dst = quote_ident(from_column), quote_ident(to_column)
    filtered = f" WHERE {where}" if where else ""
    return (
        "WITH RECURSIVE e AS ("
        f"SELECT DISTINCT {src} AS src, {dst} AS dst FROM {quote_ident(table)}{filtered}), "
        "nodes AS (SELECT src AS n FROM e UNION SELECT dst FROM e), "
        "peel(n, remaining) USING KEY (n) AS ("
        "SELECT nodes.n, COALESCE(indegree.c, 0) FROM nodes LEFT JOIN "
        "(SELECT dst, COUNT(*) AS c FROM e GROUP BY dst) indegree ON indegree.dst = nodes.n "
        "UNION "
        "SELECT e.dst, ANY_VALUE(r.remaining) - COUNT(*) "
        "FROM peel w JOIN e ON e.src = w.n JOIN recurring.peel r ON r.n = e.dst "
        "WHERE w.remaining = 0 GROUP BY e.dst) "
        "SELECT COUNT(*) FROM peel WHERE remaining > 0"
    )


def _graph_invariants(schema: "SchemaConfig") -> List[Invariant]:
    """Declared graph structure: an acyclic background and exact motif counts.

    A ``dag_edges`` table has no cycle, except inside the cases a
    ``graph_motifs`` declaration on the same endpoints planted. Each motif
    kind carries exactly its planned number of edges, and a flag column marks
    exactly the flagged ones.
    """
    from misata.graphs import planned_motif_edges

    rows = {t.name: t.row_count for t in schema.tables}
    out = []
    for dag in schema.dag_edges:
        cases = [m.case_column for m in schema.graph_motifs
                 if (m.table, m.from_column, m.to_column) == (dag.table, dag.from_column,
                                                              dag.to_column)]
        where = " AND ".join(f"COALESCE(CAST({quote_ident(c)} AS VARCHAR), '') = ''"
                             for c in cases)
        out.append(Invariant(
            id=f"{dag.table}.{dag.from_column}->{dag.to_column}.acyclic",
            kind="acyclic", sql=acyclic_sql(dag.table, dag.from_column, dag.to_column, where),
            expected="0", value_type="integer", table=dag.table,
        ))
    for motif in schema.graph_motifs:
        if motif.table not in rows:
            continue
        table = quote_ident(motif.table)
        label = quote_ident(motif.label_column)
        planned = planned_motif_edges(motif, rows[motif.table])
        for kind in sorted({k for k, _ in planned}):
            edges = sum(n for (k, _), n in planned.items() if k == kind)
            out.append(Invariant(
                id=f"{motif.table}.{motif.name}.{kind}.motif_edges", kind="motif_edges",
                sql=f"SELECT COUNT(*) FROM {table} WHERE {label} = {quote_literal(kind)}",
                expected=str(edges), value_type="integer", table=motif.table,
            ))
        if motif.flag_column:
            flag = quote_ident(motif.flag_column)
            flagged = sum(n for (_, f), n in planned.items() if f)
            out.append(Invariant(
                id=f"{motif.table}.{motif.name}.flagged_edges", kind="flagged_edges",
                sql=f"SELECT COUNT(*) FROM {table} WHERE CAST({flag} AS BOOLEAN)",
                expected=str(flagged), value_type="integer", table=motif.table,
            ))
    return out


def derive_invariants(schema: "SchemaConfig") -> List[Invariant]:
    """Every invariant the schema's declarations imply, before any data exists.

    The aggregate and integrity checks are the evalpack's own derivation, so
    an attestation and an evalpack built from one schema can never disagree.
    Rate anchors are checked to the nearest row instead of at four decimals,
    and unique columns and row-level rules are added.
    """
    from misata.evalpack import derive_questions

    invariants: List[Invariant] = []
    for question in derive_questions(schema):
        if question.source.get("kind") == "rate_curve_anchor":
            continue
        value_type = _VALUE_TYPES[question.answer_type]
        places = question.round_decimals or 0
        invariants.append(Invariant(
            id=_invariant_id(question.source),
            kind=str(question.source.get("kind", "declared")),
            sql=question.gold_sql,
            expected=_expected_string(question.expected_answer, value_type, places),
            value_type=value_type,
            table=_question_table(question.source),
        ))
    invariants += _rate_invariants(schema)
    invariants += _unique_invariants(schema)
    invariants += _row_rule_invariants(schema)
    invariants += _min_children_invariants(schema)
    invariants += _partition_invariants(schema)
    invariants += _graph_invariants(schema)

    seen: Dict[str, int] = {}
    unique_ids = []
    for invariant in invariants:
        count = seen.get(invariant.id, 0) + 1
        seen[invariant.id] = count
        unique_ids.append(invariant if count == 1 else
                          dataclasses.replace(invariant, id=f"{invariant.id}#{count}"))
    return unique_ids


# --------------------------------------------------------------------------- #
# The Statement
# --------------------------------------------------------------------------- #

def _table_sources(directory: Path, tables: List[str]) -> List[Tuple[Path, List[str]]]:
    """Every file holding a schema table, with the tables it holds.

    A table is ``<table>.parquet``, ``.csv`` or ``.jsonl`` (in that order), a
    ``<table>/`` folder of Parquet parts, which may be Hive-partitioned, in
    the directory or its ``tables/`` folder, or a table inside
    ``data.duckdb``.
    """
    from misata.sinks import DUCKDB_FILE

    sources: List[Tuple[Path, List[str]]] = []
    found: set = set()
    for folder in (directory, directory / "tables"):
        for name in tables:
            if name in found:
                continue
            single = next((folder / f"{name}{s}" for s in TABLE_SUFFIXES
                           if (folder / f"{name}{s}").is_file()), None)
            parts = sorted((folder / name).rglob("*.parquet")) if (folder / name).is_dir() else []
            if single is not None:
                sources.append((single, [name]))
            elif parts:
                sources.extend((part, [name]) for part in parts)
            else:
                continue
            found.add(name)
    database = directory / DUCKDB_FILE
    if database.is_file() and len(found) < len(tables):
        import duckdb

        with duckdb.connect(str(database), read_only=True) as con:
            held = {row[0] for row in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
        inside = [name for name in tables if name not in found and name in held]
        if inside:
            sources.append((database, inside))
            found.update(inside)
    missing = [name for name in tables if name not in found]
    if missing:
        raise AttestationError(
            f"no file for table(s) {', '.join(missing)} in {directory} or {directory / 'tables'}; "
            f"expected <table>.parquet, <table>.csv, a <table>/ folder of Parquet parts, "
            f"or {DUCKDB_FILE}"
        )
    return sorted(sources, key=lambda source: source[0].relative_to(directory).as_posix())


def spec_reference(schema: "SchemaConfig", spec_path: Optional[PathLike]) -> Dict[str, Any]:
    """The Statement's ``spec``: the spec file's digest, or the schema's canonical JSON digest."""
    if spec_path is not None:
        path = Path(spec_path)
        return {"name": path.name, "digest": {"sha256": attestation_verify.sha256_file(path)}}
    canonical = json.dumps(json.loads(schema.model_dump_json()), sort_keys=True,
                           separators=(",", ":"))
    return {"name": "schema.json",
            "digest": {"sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def dsse_envelope(payload: bytes) -> Dict[str, Any]:
    """An unsigned DSSE envelope around ``payload``; a signer fills ``signatures``."""
    return {
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode("ascii"),
        "signatures": [],
    }


def attest(
    data_dir: PathLike,
    schema: "SchemaConfig",
    *,
    spec_path: Optional[PathLike] = None,
    write: bool = True,
    script_name: str = "verify.py",
    extra_invariants: Sequence[Invariant] = (),
) -> Attestation:
    """Check a written dataset against its schema and record the result.

    Args:
        data_dir:    Directory holding one ``<table>.parquet`` or ``<table>.csv``
                     per schema table, directly or in a ``tables/`` folder.
        schema:      The :class:`~misata.schema.SchemaConfig` that generated it.
        spec_path:   The schema file, when there is one; its bytes are hashed
                     into the Statement. Otherwise the schema's canonical JSON is.
        write:       Write the Statement, the DSSE envelope and the verifier.
        script_name: File name for the verifier, for directories that already
                     have a ``verify.py``.
        extra_invariants: Checks beyond what the schema implies, appended after
                     the derived ones; :func:`misata.solve` adds its solved
                     targets here.

    Returns:
        An :class:`Attestation`; ``.passed`` is True when every invariant holds.

    Raises:
        AttestationError: a schema table has no file, or the schema declares
            nothing that can be checked.
    """
    import duckdb

    import misata

    directory = Path(data_dir)
    subjects = [
        {"name": path.relative_to(directory).as_posix(),
         "digest": {"sha256": attestation_verify.sha256_file(path)},
         "annotations": {"tables": held}}
        for path, held in _table_sources(directory, [t.name for t in schema.tables])
    ]

    invariants = derive_invariants(schema) + list(extra_invariants)
    if not invariants:
        raise AttestationError(
            "the schema declares nothing to attest: add a relationship, a unique "
            "column, an outcome curve, a rate curve, group shares or a ledger"
        )

    con = attestation_verify.connect(directory, subjects)
    checked = []
    for invariant in invariants:
        observed, held = attestation_verify.evaluate(con, invariant.to_predicate("", False))
        checked.append(invariant.to_predicate(observed, held))
    con.close()

    statement: Dict[str, Any] = {
        "_type": STATEMENT_TYPE,
        "subject": subjects,
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "result": "PASSED" if all(c["passed"] for c in checked) else "FAILED",
            "spec": spec_reference(schema, spec_path),
            "producer": {"name": "misata", "uri": f"pkg:pypi/misata@{misata.__version__}"},
            "seed": schema.seed,
            "verifiedAt": _now(),
            "engine": {"name": "duckdb", "version": duckdb.__version__},
            "invariants": checked,
        },
    }
    result = Attestation(directory=directory, statement=statement)
    if write:
        payload = (json.dumps(statement, indent=2) + "\n").encode("utf-8")
        result.files = {
            "statement": directory / STATEMENT_FILE,
            "envelope": directory / DSSE_FILE,
            "verifier": directory / script_name,
        }
        result.files["statement"].write_bytes(payload)
        result.files["envelope"].write_text(
            json.dumps(dsse_envelope(payload), indent=2) + "\n", encoding="utf-8")
        result.files["verifier"].write_text(
            Path(attestation_verify.__file__).read_text(encoding="utf-8"), encoding="utf-8")
    return result


# --------------------------------------------------------------------------- #
# Exports: the same invariants in the formats data platforms already read
# --------------------------------------------------------------------------- #

ODCS_API_VERSION = "v3.2.0"
OPENLINEAGE_PRODUCER = "https://github.com/rasinmuhammed/misata"
_OPENLINEAGE_RUN_EVENT = "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/RunEvent"
_OPENLINEAGE_ASSERTIONS = ("https://openlineage.io/spec/facets/1-0-1/"
                           "DataQualityAssertionsDatasetFacet.json"
                           "#/$defs/DataQualityAssertionsDatasetFacet")
_CERTIFICATE_FACET = "https://misata.studio/attestation/openlineage/MisataCertificateFacet.json"

_ODCS_LOGICAL_TYPES = {
    "int": "integer", "foreign_key": "integer", "float": "number", "boolean": "boolean",
    "date": "date", "datetime": "timestamp", "text": "string", "categorical": "string",
}


def _odcs_rule(invariant: Dict[str, Any]) -> Dict[str, Any]:
    """An ODCS ``type: sql`` rule whose query returns a number to compare."""
    sql, expected = invariant["sql"], invariant["expected"]
    must_be: Union[int, float]
    if invariant["valueType"] == "boolean":
        query, must_be = f"SELECT CAST(({sql}) AS INTEGER)", 1 if expected == "true" else 0
    elif invariant["valueType"] == "string":
        query, must_be = f"SELECT CAST((({sql}) = {quote_literal(expected)}) AS INTEGER)", 1
    elif invariant["valueType"] == "integer":
        query, must_be = sql, int(expected)
    else:
        query, must_be = sql, float(expected)
    return {
        "id": invariant["id"].replace(".", "_").replace("->", "_to_").replace("#", "_"),
        "name": invariant["id"],
        "description": f"Misata declared {invariant['kind']}: expected {expected}.",
        "type": "sql",
        "query": query,
        "mustBe": must_be,
    }


def to_odcs(attestation: Attestation, schema: "SchemaConfig") -> Dict[str, Any]:
    """An Open Data Contract Standard contract that rechecks every invariant.

    One ``type: sql`` quality rule per invariant sits under its table, and a
    ``local`` server points at the attested files, so ``datacontract test``
    runs the same checks with DuckDB.
    """
    subjects = attestation.statement["subject"]
    suffix = Path(subjects[0]["name"]).suffix if subjects else ".parquet"
    folder = Path(subjects[0]["name"]).parent.as_posix() if subjects else "."
    rules: Dict[str, List[Dict[str, Any]]] = {}
    for invariant in attestation.invariants:
        rules.setdefault(invariant["table"], []).append(_odcs_rule(invariant))

    objects = []
    for table in schema.tables:
        properties = [
            {"name": c.name, "logicalType": _ODCS_LOGICAL_TYPES.get(c.type, "string")}
            for c in schema.get_columns(table.name)
        ]
        obj: Dict[str, Any] = {"name": table.name, "physicalName": table.name,
                               "logicalType": "object", "properties": properties}
        if rules.get(table.name):
            obj["quality"] = rules[table.name]
        objects.append(obj)

    predicate = attestation.statement["predicate"]
    return {
        "apiVersion": ODCS_API_VERSION,
        "kind": "DataContract",
        "id": f"misata-{predicate['spec']['digest']['sha256'][:16]}",
        "name": schema.name,
        "version": "1.0.0",
        "status": "active",
        "description": {
            "purpose": "Synthetic data generated by Misata from a declared schema.",
            "usage": f"Every quality rule restates an invariant from {STATEMENT_FILE}.",
        },
        "servers": [{
            "server": "local",
            "type": "local",
            "format": suffix.lstrip(".") or "parquet",
            "path": f"{folder}/{{model}}{suffix}" if folder != "." else f"./{{model}}{suffix}",
        }],
        "schema": objects,
    }


def to_openlineage(attestation: Attestation) -> Dict[str, Any]:
    """An OpenLineage ``RunEvent`` with a data-quality assertion per invariant.

    The standard ``dataQualityAssertions`` facet carries pass or fail; the
    ``misata_certificate`` facet carries the expected and observed values,
    the spec digest and the seed. The run id is derived from the Statement,
    so exporting the same attestation twice gives the same event.
    """
    statement = attestation.statement
    predicate = statement["predicate"]
    payload = json.dumps(statement, sort_keys=True).encode("utf-8")
    run_id = uuid.uuid5(uuid.NAMESPACE_URL, "misata:" + hashlib.sha256(payload).hexdigest())

    by_table: Dict[str, List[Dict[str, Any]]] = {}
    for invariant in attestation.invariants:
        by_table.setdefault(invariant["table"], []).append(invariant)

    inputs = []
    for subject in statement["subject"]:
        table = Path(subject["name"]).stem
        checks = by_table.get(table, [])
        inputs.append({
            "namespace": f"file://{attestation.directory.resolve().as_posix()}",
            "name": subject["name"],
            "facets": {
                "misata_certificate": {
                    "_producer": OPENLINEAGE_PRODUCER,
                    "_schemaURL": _CERTIFICATE_FACET,
                    "predicateType": statement["predicateType"],
                    "statement": STATEMENT_FILE,
                    "sha256": subject["digest"]["sha256"],
                    "specSha256": predicate["spec"]["digest"]["sha256"],
                    "seed": predicate["seed"],
                    "invariants": [{"id": c["id"], "expected": c["expected"],
                                    "observed": c["observed"]} for c in checks],
                },
            },
            "inputFacets": {
                "dataQualityAssertions": {
                    "_producer": OPENLINEAGE_PRODUCER,
                    "_schemaURL": _OPENLINEAGE_ASSERTIONS,
                    "assertions": [{"assertion": c["id"], "success": bool(c["passed"])}
                                   for c in checks],
                },
            },
        })

    return {
        "eventType": "COMPLETE",
        "eventTime": predicate["verifiedAt"],
        "producer": OPENLINEAGE_PRODUCER,
        "schemaURL": _OPENLINEAGE_RUN_EVENT,
        "run": {"runId": str(run_id), "facets": {}},
        "job": {"namespace": "misata", "name": "attest", "facets": {}},
        "inputs": inputs,
        "outputs": [],
    }
