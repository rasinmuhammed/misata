#!/usr/bin/env python3
"""Re-verify an evalpack, or score candidate SQL against it.

    python verify.py                         # every gold SQL on every database
    python verify.py --candidates FILE       # your SQL, one {"id", "sql"} per line

An evalpack holds one database in ``tables/``, or several in
``rotations/<seed>/tables/`` that share the same declared answers. A query
counts as correct only when it returns the expected answer on every
database, so a query that depends on particular rows rather than on the
question fails even when it fits one of them.

Numeric answers are compared at each question's ``round_decimals`` and
strings exactly. Exits 0 when everything checked matches, 1 otherwise. Needs
only the Python standard library and ``duckdb``. Misata ships this file
unchanged as each pack's ``verify.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def databases(pack: Path) -> List[Tuple[str, Path]]:
    """``(label, tables_dir)`` for each database in the pack."""
    rotations = pack / "rotations"
    if rotations.is_dir():
        return [(d.name, d / "tables") for d in sorted(rotations.iterdir())
                if (d / "tables").is_dir()]
    return [("tables", pack / "tables")]


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def connect(tables_dir: Path) -> Any:
    """A DuckDB connection with one view per CSV, named by its stem."""
    import duckdb

    con = duckdb.connect()
    for csv in sorted(tables_dir.glob("*.csv")):
        source = _literal(str(csv.resolve()))
        con.execute(f"CREATE VIEW {_ident(csv.stem)} AS SELECT * FROM read_csv_auto({source})")
    return con


def answers_match(question: Dict[str, Any], observed: Any) -> bool:
    """Numbers at the question's ``round_decimals``; strings exactly."""
    expected = question["expected_answer"]
    if observed is None:
        return False
    if question["answer_type"] == "string":
        return str(observed) == str(expected)
    places = question.get("round_decimals", 0) or 0
    try:
        return abs(round(float(observed), places) - round(float(expected), places)) < 1e-9
    except (TypeError, ValueError):
        return False


def run(con: Any, sql: str) -> Tuple[Any, Optional[str]]:
    """The first column of the first row, or the error text."""
    try:
        row = con.execute(sql).fetchone()
    except Exception as exc:  # noqa: BLE001 - a failing query is a wrong answer
        return None, str(exc).splitlines()[0]
    return (row[0] if row else None), None


def load_questions(pack: Path) -> Dict[str, Dict[str, Any]]:
    questions = {}
    for line in (pack / "questions.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            question = json.loads(line)
            questions[question["id"]] = question
    return questions


def load_candidates(path: Path) -> Dict[str, str]:
    """Candidate SQL by question id.

    Accepts JSON Lines of ``{"id", "sql"}``, a JSON list of them, or one JSON
    object mapping id to SQL.
    """
    text = path.read_text(encoding="utf-8").strip()
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        data = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(data, dict):
        is_item = "id" in data and "sql" in data
        data = [data] if is_item else [{"id": k, "sql": v} for k, v in data.items()]
    return {str(item["id"]): str(item["sql"]) for item in data}


def check(pack: Path, sql_by_id: Dict[str, str]) -> Tuple[int, List[str]]:
    """Run each query on every database; return the failure count and a report."""
    questions = load_questions(pack)
    dbs = [(label, connect(tables)) for label, tables in databases(pack)]
    failures, lines = 0, []
    for qid, sql in sql_by_id.items():
        question = questions.get(qid)
        if question is None:
            failures += 1
            lines.append(f"FAIL {qid}: no such question")
            continue
        missed = []
        for label, con in dbs:
            observed, error = run(con, sql)
            if not answers_match(question, observed):
                missed.append(f"{label}: {error or observed!r}")
        if missed:
            failures += 1
            lines.append(f"FAIL {qid}: expected {question['expected_answer']!r}; "
                         + "; ".join(missed))
        else:
            lines.append(f"OK   {qid}: {question['expected_answer']!r}")
    for _, con in dbs:
        con.close()
    lines.append(f"\n{len(sql_by_id) - failures}/{len(sql_by_id)} match on all "
                 f"{len(dbs)} database(s)")
    return failures, lines


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    pack = Path(__file__).resolve().parent
    if args and args[0] == "--candidates":
        if len(args) < 2:
            print("usage: python verify.py --candidates FILE")
            return 2
        sql_by_id = load_candidates(Path(args[1]))
    else:
        sql_by_id = {qid: q["gold_sql"] for qid, q in load_questions(pack).items()}
    try:
        failures, lines = check(pack, sql_by_id)
    except ImportError:
        print("FAIL  this check needs DuckDB: pip install duckdb")
        return 2
    print("\n".join(lines))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
