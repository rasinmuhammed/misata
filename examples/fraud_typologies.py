"""
Fraud typology engine — organized-fraud overlays with exact answer keys.
========================================================================

The declared fraud-rate curve on ``transactions.is_fraud`` models *point*
anomalies: individually suspicious transactions, scattered at a known rate.
Real financial crime is rarely a lone flagged transaction — it is a *pattern*
across many transactions and accounts, deliberately shaped so each individual
row looks ordinary and slips past the naive flag.

This module plants three such patterns into an already-generated bank and
returns an **answer key**: for every planted case, exactly which accounts and
transactions belong to it. That answer key is the thing a competitor selling
"realistic synthetic data" cannot ship — realism without ground truth is
un-scorable. A fraud team can point their detection model at this dataset and
get a real precision/recall number, because the truth is known by construction.

Planted rows carry ``is_fraud = False`` on purpose: organized fraud is built to
evade the point-anomaly flag, so the ring is invisible to a system that only
trusts ``is_fraud``. The truth lives in ``fraud_typology`` / ``fraud_case_id``.
Because the overlay only *adds* rows (never mutates the organic ones), the
declared fraud-rate curve stays exact on the organic population.

Typologies
----------
- **mule_chain**   fan-in / fan-out: many small inbound transfers converge on a
                   collector account within a short window, then a few large
                   outbound transfers drain it.
- **structuring**  one account splits a large sum into several deposits each
                   just under the AED 55,000 cash-reporting threshold, days
                   apart, to stay below the trigger.
- **card_bustout** an account builds a normal history, then bursts into a run
                   of maxed-out card spend across categories before going dark.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

# UAE cash-transaction reporting threshold (AED). Structuring hugs just below.
REPORTING_THRESHOLD_AED = 55_000.0


@dataclass
class FraudPlant:
    """Result of planting typologies: the augmented table plus the answer key."""

    transactions: pd.DataFrame
    answer_key: pd.DataFrame  # one row per case: case_id, typology, accounts, txns, note
    cases: List[Dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = ["Planted fraud cases (ground truth):"]
        by_type = self.answer_key.groupby("typology")
        for typ, grp in by_type:
            n_txn = int(grp["n_transactions"].sum())
            n_acct = int(grp["n_accounts"].sum())
            lines.append(f"  {typ:<14} {len(grp):>3} cases  {n_acct:>4} accounts  {n_txn:>5} transactions")
        return "\n".join(lines)


def plant_fraud_typologies(
    transactions: pd.DataFrame,
    accounts: pd.DataFrame,
    *,
    seed: int = 42,
    n_mule_chains: int = 12,
    n_structuring: int = 15,
    n_bustouts: int = 10,
) -> FraudPlant:
    """Overlay organized-fraud typologies onto a generated bank.

    Args:
        transactions: generated transactions (needs account_id, txn_ts, channel,
                      merchant_category, merchant_name, amount_aed, description,
                      is_fraud). A txn_id column is used if present, else added.
        accounts:     generated accounts (needs account_id).
        seed:         RNG seed; the whole overlay is reproducible.
        n_*:          number of cases to plant per typology.

    Returns:
        FraudPlant with the augmented transactions, an answer-key DataFrame, and
        the raw case dicts.
    """
    rng = np.random.default_rng(seed)
    tx = transactions.copy()
    if "txn_id" not in tx.columns:
        tx.insert(0, "txn_id", np.arange(1, len(tx) + 1))

    # New ground-truth columns, null on every organic row.
    tx["fraud_typology"] = pd.array([pd.NA] * len(tx), dtype="string")
    tx["fraud_case_id"] = pd.array([pd.NA] * len(tx), dtype="string")

    acct_ids = accounts["account_id"].to_numpy()
    next_txn_id = int(tx["txn_id"].max()) + 1
    window_start = pd.Timestamp("2025-01-05")
    window_end = pd.Timestamp("2025-06-25")

    new_rows: List[dict] = []
    cases: List[Dict] = []

    def _pick_accounts(k: int) -> np.ndarray:
        return rng.choice(acct_ids, size=k, replace=False)

    def _ts_around(anchor: pd.Timestamp, spread_hours: float) -> pd.Timestamp:
        delta = rng.normal(0, spread_hours)
        return anchor + pd.Timedelta(hours=float(delta))

    def _row(txn_id, account_id, ts, channel, category, merchant, amount, desc, case_id, typology):
        return {
            "txn_id": txn_id,
            "account_id": int(account_id),
            "txn_ts": ts,
            "channel": channel,
            "merchant_category": category,
            "merchant_name": merchant,
            "amount_aed": round(float(amount), 2),
            "description": desc,
            "is_fraud": False,  # invisible to the naive flag — that's the point
            "fraud_typology": typology,
            "fraud_case_id": case_id,
        }

    # ── Mule chains: fan-in then fan-out ──────────────────────────────────
    for c in range(n_mule_chains):
        case_id = f"MULE-{c+1:03d}"
        n_mules = int(rng.integers(4, 9))
        members = _pick_accounts(n_mules + 1)
        collector, mules = members[0], members[1:]
        anchor = window_start + pd.Timedelta(days=float(rng.uniform(0, (window_end - window_start).days)))
        case_txn_ids: List[int] = []

        # fan-in: each mule debits its own account, the collector is credited —
        # a real transfer shows on both ledgers, so both accounts appear.
        inbound_total = 0.0
        for m in mules:
            amt = float(rng.uniform(3_500, 9_500))
            inbound_total += amt
            ref = rng.integers(10**7, 10**8)
            ts = _ts_around(anchor, 30)
            new_rows.append(_row(next_txn_id, m, ts, "transfer", "Remittance",
                                 f"IPI DR TO {int(collector)}", amt,
                                 f"OUTWARD TRANSFER REF{ref}", case_id, "mule_chain"))
            case_txn_ids.append(next_txn_id); next_txn_id += 1
            new_rows.append(_row(next_txn_id, collector, ts, "transfer", "Remittance",
                                 f"IPI CR FROM {int(m)}", amt,
                                 f"INWARD TRANSFER REF{ref}", case_id, "mule_chain"))
            case_txn_ids.append(next_txn_id); next_txn_id += 1

        # fan-out: collector drains via 1-3 large outbound transfers a bit later
        drain_anchor = anchor + pd.Timedelta(hours=float(rng.uniform(12, 72)))
        n_out = int(rng.integers(1, 4))
        for _ in range(n_out):
            amt = inbound_total / n_out * float(rng.uniform(0.9, 1.0))
            new_rows.append(_row(next_txn_id, collector, _ts_around(drain_anchor, 10),
                                 "transfer", "Remittance", "IPI DR OUTWARD",
                                 amt, f"OUTWARD TRANSFER REF{rng.integers(10**7,10**8)}",
                                 case_id, "mule_chain"))
            case_txn_ids.append(next_txn_id); next_txn_id += 1

        cases.append({
            "case_id": case_id, "typology": "mule_chain",
            "account_ids": [int(collector), *map(int, mules)],
            "collector_account_id": int(collector),
            "txn_ids": list(case_txn_ids),
            "note": f"{n_mules} mules fan in AED {inbound_total:,.0f}, collector drains via {n_out} transfer(s)",
        })

    # ── Structuring: deposits hugging just below the reporting threshold ──
    for c in range(n_structuring):
        case_id = f"STRUCT-{c+1:03d}"
        acct = int(_pick_accounts(1)[0])
        n_dep = int(rng.integers(3, 7))
        anchor = window_start + pd.Timedelta(days=float(rng.uniform(0, (window_end - window_start).days)))
        case_txn_ids: List[int] = []
        total = 0.0
        for d in range(n_dep):
            amt = float(rng.uniform(0.87, 0.995)) * REPORTING_THRESHOLD_AED  # 47.8k–54.7k
            total += amt
            ts = anchor + pd.Timedelta(days=float(d) + float(rng.uniform(-0.3, 0.3)))
            new_rows.append(_row(next_txn_id, acct, ts, "transfer", "Cash",
                                 "CASH DEPOSIT CDM", amt,
                                 f"CASH DEP CDM REF{rng.integers(10**7,10**8)}",
                                 case_id, "structuring"))
            case_txn_ids.append(next_txn_id); next_txn_id += 1
        cases.append({
            "case_id": case_id, "typology": "structuring",
            "account_ids": [acct], "collector_account_id": acct,
            "txn_ids": list(case_txn_ids),
            "note": f"{n_dep} deposits totalling AED {total:,.0f}, each < {REPORTING_THRESHOLD_AED:,.0f}",
        })

    # ── Card bust-out: trust-building then a maxed-out burst ──────────────
    burst_cats = ["Electronics", "Gold & Jewellery", "Fashion", "Travel"]
    for c in range(n_bustouts):
        case_id = f"BUST-{c+1:03d}"
        acct = int(_pick_accounts(1)[0])
        anchor = window_start + pd.Timedelta(days=float(rng.uniform(30, (window_end - window_start).days)))
        case_txn_ids: List[int] = []
        n_burst = int(rng.integers(5, 11))
        total = 0.0
        for _ in range(n_burst):
            cat = str(rng.choice(burst_cats))
            amt = float(rng.uniform(6_000, 24_000))  # near/at card limit
            total += amt
            ts = _ts_around(anchor, 18)
            channel = str(rng.choice(["card_pos", "card_online"], p=[0.4, 0.6]))
            new_rows.append(_row(next_txn_id, acct, ts, channel, cat,
                                 "HIGH-VALUE MERCHANT", amt,
                                 f"{'ECOM' if channel=='card_online' else 'POS'} PURCHASE REF{rng.integers(10**7,10**8)}",
                                 case_id, "card_bustout"))
            case_txn_ids.append(next_txn_id); next_txn_id += 1
        cases.append({
            "case_id": case_id, "typology": "card_bustout",
            "account_ids": [acct], "collector_account_id": acct,
            "txn_ids": list(case_txn_ids),
            "note": f"{n_burst} maxed-out purchases totalling AED {total:,.0f} in a short burst",
        })

    if new_rows:
        planted = pd.DataFrame(new_rows)
        planted["fraud_typology"] = planted["fraud_typology"].astype("string")
        planted["fraud_case_id"] = planted["fraud_case_id"].astype("string")
        # Align columns to the base table's order where they overlap.
        tx = pd.concat([tx, planted], ignore_index=True)
        tx = tx.sort_values("txn_ts").reset_index(drop=True)

    answer_key = pd.DataFrame([
        {
            "case_id": k["case_id"],
            "typology": k["typology"],
            "n_accounts": len(k["account_ids"]),
            "n_transactions": len(k["txn_ids"]),
            "account_ids": k["account_ids"],
            "txn_ids": k["txn_ids"],
            "note": k["note"],
        }
        for k in cases
    ])
    return FraudPlant(transactions=tx, answer_key=answer_key, cases=cases)


def recompute_account_rollups(accounts: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    """Recompute total_spend_aed and txn_count from the final transactions.

    After planting rings, the account-level rollups must be recomputed so the
    shipped dataset still reconciles to the fils, ring activity included.
    """
    acc = accounts.copy()
    spend = transactions.groupby("account_id")["amount_aed"].sum().round(2)
    counts = transactions.groupby("account_id")["txn_id"].count()
    acc["total_spend_aed"] = acc["account_id"].map(spend).fillna(0.0).round(2)
    acc["txn_count"] = acc["account_id"].map(counts).fillna(0).astype(int)
    return acc
