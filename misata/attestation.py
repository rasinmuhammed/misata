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
identities, group shares and waterfalls. Expected and observed values are
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
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Union

from misata import attestation_verify
from misata.attestation_verify import PREDICATE_TYPE, STATEMENT_FILE, STATEMENT_TYPE
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
    quantum = Decimal(1).scaleb(-places) if value_type == "decimal" else Decimal(1)
    return str(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_EVEN))


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


def derive_invariants(schema: "SchemaConfig") -> List[Invariant]:
    """Every invariant the schema's declarations imply, before any data exists.

    The aggregate and integrity checks are the evalpack's own derivation, so
    an attestation and an evalpack built from one schema can never disagree.
    Rate anchors are checked to the nearest row instead of at four decimals,
    and unique columns are added.
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
