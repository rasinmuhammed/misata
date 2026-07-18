"""
Bank evalpack — a certified fraud-detection benchmark.
======================================================

An evalpack inverts the usual benchmark order: the ground truth is the
*specification* (here, the fraud answer key), and every question's gold SQL is
executed against the *written* dataset with DuckDB. Only questions whose
observed answer exactly matches the declared answer are shipped. The generator
and the verifier share nothing but the CSV files on disk — exactly what a
downstream consumer would read.

This is the artifact a competitor selling "realistic synthetic data" cannot
produce: a benchmark of questions with certified-correct answers, because the
answers are known by construction rather than annotated after the fact (the
step where public text-to-SQL benchmarks pick up pervasive answer-key errors).

Run:
    python examples/bank_evalpack.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List

import pandas as pd

from misata.evalpack import (
    EvalQuestion,
    _jsonable,
    _require_duckdb,
    _verify_questions,
)


def _fraud_questions(answer_key: pd.DataFrame, next_id: Callable[[], str]) -> List[EvalQuestion]:
    """Derive questions whose expected answers come from the answer key (spec)."""
    q: List[EvalQuestion] = []

    # 1. Count of cases per typology.
    for typ, grp in answer_key.groupby("typology"):
        q.append(EvalQuestion(
            id=next_id(),
            question=f"How many distinct {typ} fraud cases are in the data?",
            gold_sql=(
                "SELECT COUNT(DISTINCT fraud_case_id) FROM transactions "
                f"WHERE fraud_typology = '{typ}'"
            ),
            expected_answer=int(len(grp)),
            answer_type="integer",
            tags=["fraud", "typology_count", typ],
            source={"typology": typ},
        ))

    # 2. Total transactions and accounts touched by organized fraud.
    total_txn = int(answer_key["n_transactions"].sum())
    q.append(EvalQuestion(
        id=next_id(),
        question="How many transactions belong to any organized-fraud ring?",
        gold_sql="SELECT COUNT(*) FROM transactions WHERE fraud_case_id IS NOT NULL",
        expected_answer=total_txn,
        answer_type="integer",
        tags=["fraud", "ring_total"],
    ))

    # 3. Per-case transaction membership (proves the answer key is faithful).
    for _, row in answer_key.iterrows():
        q.append(EvalQuestion(
            id=next_id(),
            question=f"How many transactions make up fraud case {row['case_id']}?",
            gold_sql=(
                "SELECT COUNT(*) FROM transactions "
                f"WHERE fraud_case_id = '{row['case_id']}'"
            ),
            expected_answer=int(row["n_transactions"]),
            answer_type="integer",
            tags=["fraud", "case_membership", row["typology"]],
            source={"case_id": row["case_id"]},
        ))

    # 4. Accounts implicated in each mule chain (fan-in width + collector).
    mule = answer_key[answer_key["typology"] == "mule_chain"]
    for _, row in mule.iterrows():
        ids = ", ".join(str(a) for a in row["account_ids"])
        q.append(EvalQuestion(
            id=next_id(),
            question=f"How many accounts are named in mule chain {row['case_id']}?",
            gold_sql=(
                "SELECT COUNT(DISTINCT account_id) FROM transactions "
                f"WHERE fraud_case_id = '{row['case_id']}' "
                f"AND account_id IN ({ids})"
            ),
            expected_answer=int(row["n_accounts"]),
            answer_type="integer",
            tags=["fraud", "mule_accounts"],
            source={"case_id": row["case_id"]},
        ))

    # 5. Structuring stays under the reporting threshold (a compliance claim
    #    a regulator would ask you to prove).
    q.append(EvalQuestion(
        id=next_id(),
        question="How many structuring deposits exceed the AED 55,000 reporting threshold?",
        gold_sql=(
            "SELECT COUNT(*) FROM transactions "
            "WHERE fraud_typology = 'structuring' AND amount_aed >= 55000"
        ),
        expected_answer=0,
        answer_type="integer",
        tags=["fraud", "structuring", "compliance"],
    ))

    return q


def build_bank_evalpack(
    tables: Dict[str, pd.DataFrame],
    answer_key: pd.DataFrame,
    output_dir: str | Path,
) -> Dict[str, Any]:
    """Write the dataset + a verified fraud-detection evalpack.

    Returns a dict with the shipped questions, dropped candidates, and a
    certificate. Every shipped question's gold SQL was executed against the
    CSVs on disk and matched its declared answer.
    """
    duckdb = _require_duckdb()
    out = Path(output_dir)
    tables_dir = out / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(tables_dir / f"{name}.csv", index=False)

    counter = {"n": 0}

    def next_id() -> str:
        counter["n"] += 1
        return f"q{counter['n']:03d}"

    candidates = _fraud_questions(answer_key, next_id)

    con = duckdb.connect()
    for name in tables:
        csv_path = str((tables_dir / f"{name}.csv").resolve()).replace("'", "''")
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_csv_auto('{csv_path}')")
    shipped, dropped, entries = _verify_questions(con, candidates)

    certificate = {
        "questions_shipped": len(shipped),
        "candidates_dropped": len(dropped),
        "all_match": len(dropped) == 0 and len(shipped) > 0,
        "verified_entries": entries,
    }
    manifest = {
        "questions": [q.to_dict() for q in shipped],
        "dropped_questions": dropped,
        "certificate": certificate,
    }
    (out / "questions.json").write_text(json.dumps([q.to_dict() for q in shipped], indent=2))
    (out / "certificate.json").write_text(json.dumps(certificate, indent=2))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=_jsonable))

    return {"shipped": shipped, "dropped": dropped, "certificate": certificate, "output_dir": out}


def main() -> None:
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import bank_in_a_box as bank
    from fraud_typologies import plant_fraud_typologies, recompute_account_rollups

    import misata

    schema = misata.from_dict_schema(bank.schema_dict, seed=bank.SEED)
    tables = misata.generate_from_schema(
        schema,
        capsule="examples/gcc_banking.capsule.json",
        custom_generators={
            "transactions": {
                "txn_ts": bank._txn_timestamps,
                "amount_aed": bank._amount_aed,
                "description": bank._statement_description,
            }
        },
    )
    plant = plant_fraud_typologies(
        transactions=tables["transactions"], accounts=tables["accounts"], seed=bank.SEED
    )
    tables["transactions"] = plant.transactions
    tables["accounts"] = recompute_account_rollups(tables["accounts"], plant.transactions)

    result = build_bank_evalpack(tables, plant.answer_key, "examples/bank_evalpack_out")
    cert = result["certificate"]

    w = 66
    print()
    print("━" * w)
    print("  Bank Evalpack — certified fraud-detection benchmark")
    print("━" * w)
    print(f"  Questions shipped (all DuckDB-verified): {cert['questions_shipped']:>4}")
    print(f"  Candidates dropped (unverified):         {cert['candidates_dropped']:>4}")
    print(f"  All shipped answers certified correct:   {str(cert['all_match']):>4}")
    print()
    print("  Sample certified questions")
    for q in result["shipped"][:6]:
        print(f"    [{q.id}] {q.question}")
        print(f"           gold answer = {q.expected_answer}")
    print()
    print(f"  Written to: {result['output_dir']}/  (tables/, questions.json, certificate.json)")
    print("━" * w)
    print()


if __name__ == "__main__":
    main()
