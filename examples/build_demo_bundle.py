"""
Build the compact data bundle the misata.studio fraud-lab route ships.

Generates the GCC bank + fraud rings once, then writes a columnar JSON bundle
(small enough to load and score entirely in the browser — no backend at request
time). Scoring on the client keeps the route static and free to host on Vercel.

Run:
    python examples/build_demo_bundle.py [OUTPUT_PATH]

Default OUTPUT_PATH:
    ../misata-studio/apps/web/public/demo/fraud-lab.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bank_in_a_box as bank
from fraud_typologies import plant_fraud_typologies, recompute_account_rollups

import misata

DEFAULT_OUT = (
    Path(__file__).resolve().parent.parent.parent
    / "misata-studio/apps/web/public/demo/fraud-lab.json"
)


def build() -> dict:
    schema = misata.from_dict_schema(bank.schema_dict, seed=bank.SEED)
    tables = misata.generate_from_schema(
        schema,
        capsule=str(Path(__file__).resolve().parent / "gcc_banking.capsule.json"),
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
    tx = plant.transactions.reset_index(drop=True)
    acc = recompute_account_rollups(tables["accounts"], tx)
    cust = tables["customers"]
    ak = plant.answer_key

    # Encode categoricals as small integer codes to keep the payload tiny.
    channels = sorted(tx["channel"].dropna().unique().tolist())
    cats = sorted(tx["merchant_category"].dropna().unique().tolist())
    typs = ["", "mule_chain", "structuring", "card_bustout"]
    ch_code = {c: i for i, c in enumerate(channels)}
    cat_code = {c: i for i, c in enumerate(cats)}
    typ_code = {t: i for i, t in enumerate(typs)}

    ring = tx["fraud_case_id"].notna()

    # Columnar scoring arrays — one value per transaction, parallel arrays.
    scoring = {
        "amount": [round(float(a), 2) for a in tx["amount_aed"]],
        "channel": [ch_code[c] for c in tx["channel"]],
        "category": [cat_code.get(c, 0) for c in tx["merchant_category"]],
        "is_fraud": [int(bool(x)) for x in tx["is_fraud"]],
        "is_ring": [int(bool(x)) for x in ring],
        "typology": [typ_code.get(t if isinstance(t, str) else "", 0) for t in tx["fraud_typology"].fillna("")],
    }

    # A small, human-facing sample for the ledger view: mix organic + ring rows.
    sample_idx = list(tx.index[:9]) + list(tx.index[ring][:5])
    sample = []
    for i in sample_idx:
        r = tx.loc[i]
        sample.append({
            "txn_id": int(r["txn_id"]),
            "account_id": int(r["account_id"]),
            "ts": str(r["txn_ts"])[:16],
            "channel": str(r["channel"]),
            "category": str(r["merchant_category"]),
            "merchant": str(r["merchant_name"]),
            "amount": round(float(r["amount_aed"]), 2),
            "is_fraud": bool(r["is_fraud"]),
            "case": None if r["fraud_case_id"] is None or (isinstance(r["fraud_case_id"], float)) else str(r["fraud_case_id"]),
        })

    answer_key = [
        {
            "case_id": str(r["case_id"]),
            "typology": str(r["typology"]),
            "n_accounts": int(r["n_accounts"]),
            "n_transactions": int(r["n_transactions"]),
            "note": str(r["note"]),
        }
        for _, r in ak.iterrows()
    ]

    # A few real customer rows to prove name↔nationality coherence in the UI.
    people = [
        {
            "name": str(r["full_name"]),
            "nationality": str(r["nationality"]),
            "emirate": str(r["emirate"]),
            "segment": str(r["segment"]),
        }
        for _, r in cust.head(6).iterrows()
    ]

    spend = tx.groupby("account_id")["amount_aed"].sum().round(2)
    joined = acc.set_index("account_id")["total_spend_aed"].round(2)
    reconciled = int((joined.subtract(spend, fill_value=0.0).abs() < 0.005).sum())

    return {
        "meta": {
            "customers": int(len(cust)),
            "accounts": int(len(acc)),
            "transactions": int(len(tx)),
            "ring_transactions": int(ring.sum()),
            "fraud_cases": int(len(ak)),
            "rollups_reconciled": reconciled,
            "rollups_total": int(len(acc)),
            "orphans": int((~tx["account_id"].isin(set(acc["account_id"]))).sum()),
            "txn_id_unique": bool(tx["txn_id"].is_unique),
            "naive_recall_on_rings": round(float(tx.loc[ring, "is_fraud"].mean()), 4),
            "typology_counts": ak.groupby("typology").size().to_dict(),
        },
        "codes": {"channels": channels, "categories": cats, "typologies": typs},
        "scoring": scoring,
        "sample": sample,
        "answer_key": answer_key,
        "people": people,
    }


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    bundle = build()
    out.write_text(json.dumps(bundle, separators=(",", ":")))
    size_kb = out.stat().st_size / 1024
    print(f"Wrote {out}  ({size_kb:,.0f} KB)")
    print(f"  transactions scored client-side: {bundle['meta']['transactions']:,}")
    print(f"  ring transactions: {bundle['meta']['ring_transactions']:,}  cases: {bundle['meta']['fraud_cases']}")


if __name__ == "__main__":
    main()
