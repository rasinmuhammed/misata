#!/usr/bin/env python3
"""Re-verify a Misata attestation against the files beside it.

    python verify.py            # the directory this script is in
    python verify.py DIR        # another attested directory

Reads ``attestation.intoto.json``, recomputes the SHA-256 of every subject
file, loads the tables into DuckDB and runs every invariant's SQL. Exits 0
when every digest matches and every invariant holds, and 1 otherwise.

It needs only the Python standard library and ``duckdb``, and shares no code
with the generator, so it can run wherever the data goes. Misata ships this
file unchanged as each attested directory's ``verify.py``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

STATEMENT_FILE = "attestation.intoto.json"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://misata.studio/attestation/certificate/v1"

_READERS = {
    ".csv": "read_csv_auto",
    ".tsv": "read_csv_auto",
    ".parquet": "read_parquet",
    ".json": "read_json_auto",
    ".jsonl": "read_json_auto",
}


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file, read in 1 MiB blocks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def format_value(value: Any, value_type: str, like: str = "") -> str:
    """Write ``value`` the way its invariant writes its expected value.

    Decimals take the number of places that ``like`` (the expected string)
    has, so a sum observed as 209999.99999999997 reads as 210000.00 and two
    float renderings can never disagree about equality.
    """
    if value is None:
        return "null"
    if value_type == "boolean":
        return "true" if bool(value) else "false"
    if value_type == "string":
        return str(value)
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    if value_type == "integer":
        return str(number.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    places = len(like.partition(".")[2])
    return str(number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN))


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def load_statement(directory: Path) -> Dict[str, Any]:
    """The Statement in ``directory``, checked for its type and predicate type."""
    statement: Dict[str, Any] = json.loads((directory / STATEMENT_FILE).read_text(encoding="utf-8"))
    if statement.get("_type") != STATEMENT_TYPE:
        raise ValueError(f"{STATEMENT_FILE} is not an in-toto v1 Statement")
    if statement.get("predicateType") != PREDICATE_TYPE:
        raise ValueError(f"{STATEMENT_FILE} does not carry a Misata certificate predicate")
    return statement


def subject_path(directory: Path, name: str) -> Path:
    """Resolve a subject name inside ``directory``, refusing anything outside it."""
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"subject {name!r} points outside the attested directory")
    return directory.joinpath(*relative.parts)


def check_subjects(directory: Path, subjects: List[Dict[str, Any]]) -> List[str]:
    """One problem line per subject that is missing or whose digest differs."""
    problems = []
    for subject in subjects:
        name = subject["name"]
        path = subject_path(directory, name)
        if not path.is_file():
            problems.append(f"{name}: missing")
            continue
        actual = sha256_file(path)
        if actual != subject["digest"]["sha256"]:
            problems.append(f"{name}: sha256 {actual[:12]} does not match the attested "
                            f"{subject['digest']['sha256'][:12]}")
    return problems


def connect(directory: Path, subjects: List[Dict[str, Any]]) -> Any:
    """A DuckDB connection with one view per table.

    A subject's ``annotations.tables`` names the tables it holds; without it,
    the file holds one table named by its stem. A table spread over several
    Parquet parts is read as one, with Hive partition columns taken from the
    folder names. A DuckDB file is attached read-only.
    """
    import duckdb

    con = duckdb.connect()
    parts: Dict[str, List[Path]] = {}
    for index, subject in enumerate(subjects):
        path = subject_path(directory, subject["name"])
        tables = (subject.get("annotations") or {}).get("tables") or [path.stem]
        if path.suffix.lower() == ".duckdb":
            alias = f"attested_{index}"
            con.execute(f"ATTACH {_literal(str(path.resolve()))} AS {alias} (READ_ONLY)")
            for table in tables:
                con.execute(f"CREATE VIEW {_ident(table)} AS SELECT * FROM {alias}.{_ident(table)}")
            continue
        for table in tables:
            parts.setdefault(table, []).append(path)
    for table, paths in parts.items():
        # Row formats are parsed once into a table; Parquet is columnar and
        # stays a view, so a large dataset is never copied into memory.
        kind = "VIEW" if all(p.suffix.lower() == ".parquet" for p in paths) else "TABLE"
        con.execute(f"CREATE {kind} {_ident(table)} AS SELECT * FROM {_source(directory, paths)}")
    return con


def _source(directory: Path, paths: List[Path]) -> str:
    """The DuckDB table function reading ``paths`` as one table."""
    suffixes = {p.suffix.lower() for p in paths}
    reader = _READERS.get(suffixes.pop()) if len(suffixes) == 1 else None
    if reader is None:
        raise ValueError(f"no single DuckDB reader for {', '.join(p.name for p in paths)}")
    if len(paths) == 1 and reader != "read_parquet":
        return f"{reader}({_literal(str(paths[0].resolve()))})"
    listed = "[" + ", ".join(_literal(str(p.resolve())) for p in paths) + "]"
    hive = any("=" in part for p in paths for part in p.relative_to(directory).parts[:-1])
    return (f"{reader}({listed}, hive_partitioning = {str(hive).lower()}"
            + (", union_by_name = true)" if reader == "read_parquet" else ")"))


def evaluate(con: Any, invariant: Dict[str, Any]) -> Tuple[str, bool]:
    """Run one invariant; return the observed value as written and whether it held."""
    try:
        row = con.execute(invariant["sql"]).fetchone()
    except Exception as exc:  # noqa: BLE001 - any SQL failure is a failed invariant
        return f"error: {str(exc).splitlines()[0]}", False
    observed = format_value(row[0] if row else None, invariant["valueType"], invariant["expected"])
    if invariant.get("comparator") == "within_tolerance":
        return observed, within_tolerance(observed, invariant["expected"], invariant["tolerance"])
    return observed, observed == invariant["expected"]


def within_tolerance(observed: str, expected: str, tolerance: str) -> bool:
    """``|observed - expected| <= tolerance * |expected|``, in exact decimals."""
    try:
        got, want, rel = Decimal(observed), Decimal(expected), Decimal(tolerance)
    except InvalidOperation:
        return False
    return abs(got - want) <= rel * abs(want)


def verify(directory: Path) -> Tuple[bool, List[str]]:
    """Check every digest and every invariant; return the verdict and a report."""
    statement = load_statement(directory)
    subjects = statement["subject"]
    problems = check_subjects(directory, subjects)
    lines = [f"FAIL  {p}" for p in problems] or [
        f"ok    {len(subjects)} file(s) match their attested sha256"]

    present = [s for s in subjects if subject_path(directory, s["name"]).is_file()]
    try:
        con = connect(directory, present)
    except ImportError:
        raise
    except Exception as exc:  # noqa: BLE001 - unreadable files are a failed check
        lines.append(f"FAIL  the attested files cannot be read: {str(exc).splitlines()[0]}")
        return False, lines
    invariants = statement["predicate"]["invariants"]
    broken = 0
    for invariant in invariants:
        observed, held = evaluate(con, invariant)
        if not held:
            broken += 1
            lines.append(f"FAIL  {invariant['id']}: expected {invariant['expected']}, "
                         f"observed {observed}")
    con.close()
    verdict = "ok  " if broken == 0 else "FAIL"
    lines.append(f"{verdict}  {len(invariants) - broken} of {len(invariants)} invariant(s) hold")
    return not problems and broken == 0, lines


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    directory = Path(args[0]) if args else Path(__file__).resolve().parent
    try:
        ok, lines = verify(directory)
    except ImportError:
        print("FAIL  this check needs DuckDB: pip install duckdb")
        return 2
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL  cannot verify {directory}: {exc}")
        return 1
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
