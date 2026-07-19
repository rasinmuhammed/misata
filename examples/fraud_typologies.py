"""
Fraud typology engine — FATF-grade organized-fraud overlays with exact answer keys.
===================================================================================

The declared fraud-rate curve on ``transactions.is_fraud`` models *point*
anomalies: individually suspicious transactions at a known rate. Real financial
crime is a *pattern* across many transactions and accounts, shaped so each row
looks ordinary and slips past the naive flag. This module plants recognized
money-laundering typologies into an already-generated bank and returns an
**answer key**: for every case, exactly which accounts and transactions belong
to it, plus the red-flag rationale a financial-crime analyst would cite.

Design guarantee: the answer key is *derived from the rows actually written*.
Each typology planter emits transactions tagged with a case id; the framework
computes each case's account and transaction membership from those rows. The
answer key therefore cannot disagree with the data — there is no second source
of truth to drift.

Planted rows carry ``is_fraud = False`` on purpose: organized laundering is
built to evade the point-anomaly flag, so the ring is invisible to a system
that only trusts ``is_fraud``. The truth lives in ``fraud_typology`` /
``fraud_case_id``. Because the overlay only *adds* rows, the declared
fraud-rate curve stays exact on the organic population.

Typologies (each maps to a FATF / Wolfsberg red flag)
-----------------------------------------------------
- smurfing              many parties deposit sub-threshold cash to one beneficiary
- structuring           one account splits a sum into sub-threshold deposits
- mule_network          fan-in from mules to a collector, then fan-out drain
- layering_chain        rapid sequential pass-through A→B→C→D to obscure origin
- circular_payment      funds return to the originator via intermediaries (round-trip)
- rapid_movement        large credit immediately followed by a near-equal debit
- dormant_reactivation  a long-dormant account suddenly processes high-value flow
- salary_mule           one account collects unrelated payroll credits, remits abroad
- card_bustout          trust is built, then a burst of maxed-out card spend
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd

# UAE cash-transaction reporting threshold (AED). Structuring hugs just below.
REPORTING_THRESHOLD_AED = 55_000.0


@dataclass
class FraudPlant:
    """Result of planting typologies: the augmented table plus the answer key."""

    transactions: pd.DataFrame
    answer_key: pd.DataFrame  # one row per case
    cases: List[Dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = ["Planted fraud cases (ground truth):"]
        for typ, grp in self.answer_key.groupby("typology"):
            n_txn = int(grp["n_transactions"].sum())
            n_acct = int(grp["n_accounts"].sum())
            lines.append(f"  {typ:<20} {len(grp):>3} cases  {n_acct:>4} accounts  {n_txn:>5} transactions")
        return "\n".join(lines)


# ── Planting context ─────────────────────────────────────────────────────────


class _Ctx:
    """Shared helpers + id/row bookkeeping for typology planters."""

    def __init__(self, rng: np.random.Generator, accounts: pd.DataFrame, next_txn_id: int):
        self.rng = rng
        self.acct_ids = accounts["account_id"].to_numpy()
        # Dormant accounts are the natural home for reactivation typology.
        self.dormant_ids = (
            accounts.loc[accounts.get("status", pd.Series(dtype=str)) == "dormant", "account_id"].to_numpy()
            if "status" in accounts.columns else np.array([], dtype=int)
        )
        self._next = next_txn_id
        self.rows: List[dict] = []
        self.window_start = pd.Timestamp("2025-01-05")
        self.window_end = pd.Timestamp("2025-06-25")

    def new_id(self) -> int:
        i = self._next
        self._next += 1
        return i

    def pick(self, k: int, replace: bool = False, pool: np.ndarray | None = None) -> np.ndarray:
        src = self.acct_ids if pool is None or len(pool) < k else pool
        return self.rng.choice(src, size=k, replace=replace)

    def anchor(self, min_day: float = 0.0) -> pd.Timestamp:
        span = (self.window_end - self.window_start).days
        return self.window_start + pd.Timedelta(days=float(self.rng.uniform(min_day, span)))

    def ts_around(self, anchor: pd.Timestamp, spread_hours: float) -> pd.Timestamp:
        return anchor + pd.Timedelta(hours=float(self.rng.normal(0, spread_hours)))

    def ref(self) -> int:
        return int(self.rng.integers(10**7, 10**8))

    def emit(self, account_id, ts, channel, category, merchant, amount, desc, case_id, typology) -> int:
        tid = self.new_id()
        self.rows.append({
            "txn_id": tid,
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
        })
        return tid

    def transfer(self, src, dst, ts, amount, case_id, typology) -> None:
        """A transfer books on both ledgers, so both accounts appear in the case."""
        r = self.ref()
        self.emit(src, ts, "transfer", "Remittance", f"IPI DR TO {int(dst)}", amount,
                  f"OUTWARD TRANSFER REF{r}", case_id, typology)
        self.emit(dst, ts, "transfer", "Remittance", f"IPI CR FROM {int(src)}", amount,
                  f"INWARD TRANSFER REF{r}", case_id, typology)


# ── Typology planters — each returns case metadata; rows land in ctx.rows ─────

Planter = Callable[[_Ctx, str], Dict]


def _smurfing(ctx: _Ctx, case_id: str) -> Dict:
    beneficiary = int(ctx.pick(1)[0])
    n_smurfs = int(ctx.rng.integers(5, 12))
    smurfs = [int(x) for x in ctx.pick(n_smurfs, pool=ctx.acct_ids)]
    anchor = ctx.anchor()
    total = 0.0
    for s in smurfs:
        amt = float(ctx.rng.uniform(0.75, 0.97)) * REPORTING_THRESHOLD_AED
        total += amt
        ts = ctx.ts_around(anchor, 40)
        ctx.emit(s, ts, "transfer", "Cash", "CASH DEPOSIT CDM", amt,
                 f"CASH DEP CDM REF{ctx.ref()}", case_id, "smurfing")
        ctx.transfer(s, beneficiary, ctx.ts_around(anchor, 40), amt * 0.99, case_id, "smurfing")
    return {"rationale": "Multiple parties depositing sub-threshold cash then funnelling to one beneficiary (FATF smurfing).",
            "note": f"{n_smurfs} smurfs funnel AED {total:,.0f} to one beneficiary, each deposit < {REPORTING_THRESHOLD_AED:,.0f}"}


def _structuring(ctx: _Ctx, case_id: str) -> Dict:
    acct = int(ctx.pick(1)[0])
    n_dep = int(ctx.rng.integers(3, 7))
    anchor = ctx.anchor()
    total = 0.0
    for d in range(n_dep):
        amt = float(ctx.rng.uniform(0.87, 0.995)) * REPORTING_THRESHOLD_AED
        total += amt
        ts = anchor + pd.Timedelta(days=float(d) + float(ctx.rng.uniform(-0.3, 0.3)))
        ctx.emit(acct, ts, "transfer", "Cash", "CASH DEPOSIT CDM", amt,
                 f"CASH DEP CDM REF{ctx.ref()}", case_id, "structuring")
    return {"rationale": "One account splitting a large sum into deposits each just under the reporting threshold.",
            "note": f"{n_dep} deposits totalling AED {total:,.0f}, each < {REPORTING_THRESHOLD_AED:,.0f}"}


def _mule_network(ctx: _Ctx, case_id: str) -> Dict:
    n_mules = int(ctx.rng.integers(4, 9))
    members = ctx.pick(n_mules + 1)
    collector, mules = int(members[0]), [int(m) for m in members[1:]]
    anchor = ctx.anchor()
    inbound = 0.0
    for m in mules:
        amt = float(ctx.rng.uniform(3_500, 9_500))
        inbound += amt
        ctx.transfer(m, collector, ctx.ts_around(anchor, 30), amt, case_id, "mule_network")
    drain = anchor + pd.Timedelta(hours=float(ctx.rng.uniform(12, 72)))
    n_out = int(ctx.rng.integers(1, 4))
    for _ in range(n_out):
        ctx.emit(collector, ctx.ts_around(drain, 10), "transfer", "Remittance", "IPI DR OUTWARD",
                 inbound / n_out * float(ctx.rng.uniform(0.9, 1.0)), f"OUTWARD TRANSFER REF{ctx.ref()}",
                 case_id, "mule_network")
    return {"rationale": "Many low-value inbound transfers converging on a collector, then drained outward (mule network).",
            "note": f"{n_mules} mules fan in AED {inbound:,.0f}, collector drains via {n_out} transfer(s)"}


def _layering_chain(ctx: _Ctx, case_id: str) -> Dict:
    hops = int(ctx.rng.integers(4, 7))
    chain = [int(x) for x in ctx.pick(hops)]
    anchor = ctx.anchor()
    amt = float(ctx.rng.uniform(60_000, 220_000))
    start = amt
    for i in range(hops - 1):
        ts = anchor + pd.Timedelta(hours=float(i) * float(ctx.rng.uniform(2, 8)))
        ctx.transfer(chain[i], chain[i + 1], ts, amt, case_id, "layering_chain")
        amt *= float(ctx.rng.uniform(0.94, 0.99))  # small skim per hop
    return {"rationale": "Rapid sequential pass-through across a chain of accounts to obscure origin (layering).",
            "note": f"AED {start:,.0f} moves through {hops} accounts in hours, small skim per hop"}


def _circular_payment(ctx: _Ctx, case_id: str) -> Dict:
    ring = [int(x) for x in ctx.pick(int(ctx.rng.integers(3, 5)))]
    anchor = ctx.anchor()
    amt = float(ctx.rng.uniform(40_000, 150_000))
    for i in range(len(ring)):
        src, dst = ring[i], ring[(i + 1) % len(ring)]
        ts = anchor + pd.Timedelta(days=float(i) * float(ctx.rng.uniform(0.5, 2.0)))
        ctx.transfer(src, dst, ts, amt * float(ctx.rng.uniform(0.98, 1.0)), case_id, "circular_payment")
    return {"rationale": "Funds returning to the originator through intermediaries with no economic purpose (round-tripping).",
            "note": f"AED {amt:,.0f} circulates {len(ring)} accounts and returns to origin, net ~zero"}


def _rapid_movement(ctx: _Ctx, case_id: str) -> Dict:
    acct = int(ctx.pick(1)[0])
    counterpart_in, counterpart_out = [int(x) for x in ctx.pick(2)]
    anchor = ctx.anchor()
    amt = float(ctx.rng.uniform(50_000, 180_000))
    ctx.transfer(counterpart_in, acct, anchor, amt, case_id, "rapid_movement")
    out_ts = anchor + pd.Timedelta(hours=float(ctx.rng.uniform(0.5, 6)))
    ctx.transfer(acct, counterpart_out, out_ts, amt * float(ctx.rng.uniform(0.97, 0.995)), case_id, "rapid_movement")
    return {"rationale": "Funds transiting an account with minimal residence time, no business rationale (pass-through).",
            "note": f"AED {amt:,.0f} in and near-equal out within hours"}


def _dormant_reactivation(ctx: _Ctx, case_id: str) -> Dict:
    pool = ctx.dormant_ids if len(ctx.dormant_ids) else ctx.acct_ids
    acct = int(ctx.rng.choice(pool))
    counter = [int(x) for x in ctx.pick(3)]
    anchor = ctx.anchor(min_day=60)  # reactivates later in the window
    total = 0.0
    for cp in counter:
        amt = float(ctx.rng.uniform(30_000, 120_000))
        total += amt
        ctx.transfer(cp, acct, ctx.ts_around(anchor, 12), amt, case_id, "dormant_reactivation")
    ctx.emit(acct, ctx.ts_around(anchor + pd.Timedelta(hours=24), 6), "transfer", "Remittance",
             "IPI DR OUTWARD", total * 0.98, f"OUTWARD TRANSFER REF{ctx.ref()}", case_id, "dormant_reactivation")
    return {"rationale": "A long-dormant account suddenly processing concentrated high-value flow (dormant reactivation).",
            "note": f"dormant account receives AED {total:,.0f} in a burst, then remits out"}


def _salary_mule(ctx: _Ctx, case_id: str) -> Dict:
    acct = int(ctx.pick(1)[0])
    employers = [int(x) for x in ctx.pick(int(ctx.rng.integers(4, 8)))]
    anchor = ctx.anchor()
    total = 0.0
    for e in employers:
        amt = float(ctx.rng.uniform(4_000, 12_000))
        total += amt
        r = ctx.ref()
        # WPS-style salary credit from an unrelated employer account
        ctx.emit(e, ctx.ts_around(anchor, 20), "transfer", "Remittance", "WPS SALARY DR", amt,
                 f"WPS SIF REF{r}", case_id, "salary_mule")
        ctx.emit(acct, ctx.ts_around(anchor, 20), "transfer", "Remittance", "WPS SALARY CR", amt,
                 f"WPS SIF REF{r}", case_id, "salary_mule")
    # remit the pooled "salaries" abroad via an exchange house
    ctx.emit(acct, ctx.ts_around(anchor + pd.Timedelta(days=1), 8), "transfer", "Remittance",
             "EXCHANGE HOUSE REMITTANCE", total * 0.98, f"REMIT REF{ctx.ref()}", case_id, "salary_mule")
    return {"rationale": "One account collecting multiple unrelated payroll credits then remitting abroad (payroll/salary mule).",
            "note": f"{len(employers)} unrelated WPS credits pooled to AED {total:,.0f}, then remitted"}


def _card_bustout(ctx: _Ctx, case_id: str) -> Dict:
    acct = int(ctx.pick(1)[0])
    anchor = ctx.anchor(min_day=30)
    cats = ["Electronics", "Gold & Jewellery", "Fashion", "Travel"]
    n = int(ctx.rng.integers(5, 11))
    total = 0.0
    for _ in range(n):
        amt = float(ctx.rng.uniform(6_000, 24_000))
        total += amt
        ch = str(ctx.rng.choice(["card_pos", "card_online"], p=[0.4, 0.6]))
        ctx.emit(acct, ctx.ts_around(anchor, 18), ch, str(ctx.rng.choice(cats)), "HIGH-VALUE MERCHANT",
                 amt, f"{'ECOM' if ch == 'card_online' else 'POS'} PURCHASE REF{ctx.ref()}",
                 case_id, "card_bustout")
    return {"rationale": "An account building history then bursting into maxed-out card spend before going dark (bust-out).",
            "note": f"{n} maxed-out purchases totalling AED {total:,.0f} in a short burst"}


# name → (planter, code prefix, default case count)
TYPOLOGIES: List[Tuple[str, Planter, str, int]] = [
    ("smurfing", _smurfing, "SMURF", 10),
    ("structuring", _structuring, "STRUCT", 12),
    ("mule_network", _mule_network, "MULE", 12),
    ("layering_chain", _layering_chain, "LAYER", 9),
    ("circular_payment", _circular_payment, "CIRC", 7),
    ("rapid_movement", _rapid_movement, "RAPID", 9),
    ("dormant_reactivation", _dormant_reactivation, "DORM", 6),
    ("salary_mule", _salary_mule, "SALMULE", 7),
    ("card_bustout", _card_bustout, "BUST", 8),
]


def plant_fraud_typologies(
    transactions: pd.DataFrame,
    accounts: pd.DataFrame,
    *,
    seed: int = 42,
    counts: Dict[str, int] | None = None,
) -> FraudPlant:
    """Overlay FATF-grade organized-fraud typologies onto a generated bank.

    Args:
        transactions: generated transactions (account_id, txn_ts, channel,
                      merchant_category, merchant_name, amount_aed, description,
                      is_fraud; a txn_id is added if absent).
        accounts:     generated accounts (account_id; optional status for the
                      dormant-reactivation typology).
        seed:         RNG seed; the whole overlay is reproducible.
        counts:       optional {typology_name: n_cases} overriding defaults.

    Returns:
        FraudPlant with augmented transactions, an answer-key DataFrame, and the
        raw case dicts. Case membership is derived from the written rows.
    """
    rng = np.random.default_rng(seed)
    tx = transactions.copy()
    if "txn_id" not in tx.columns:
        tx.insert(0, "txn_id", np.arange(1, len(tx) + 1))
    tx["fraud_typology"] = pd.array([pd.NA] * len(tx), dtype="string")
    tx["fraud_case_id"] = pd.array([pd.NA] * len(tx), dtype="string")

    ctx = _Ctx(rng, accounts, next_txn_id=int(tx["txn_id"].max()) + 1)
    counts = counts or {}
    meta_by_case: Dict[str, Dict] = {}

    for name, planter, prefix, default_n in TYPOLOGIES:
        n = counts.get(name, default_n)
        for c in range(n):
            case_id = f"{prefix}-{c + 1:03d}"
            meta = planter(ctx, case_id)
            meta_by_case[case_id] = {"case_id": case_id, "typology": name, **meta}

    planted = pd.DataFrame(ctx.rows)
    if not planted.empty:
        planted["fraud_typology"] = planted["fraud_typology"].astype("string")
        planted["fraud_case_id"] = planted["fraud_case_id"].astype("string")
        tx = pd.concat([tx, planted], ignore_index=True).sort_values("txn_ts").reset_index(drop=True)

    # Derive case membership from the rows actually written — single source of truth.
    cases: List[Dict] = []
    if not planted.empty:
        grouped = planted.groupby("fraud_case_id")
        for case_id, meta in meta_by_case.items():
            grp = grouped.get_group(case_id)
            cases.append({
                **meta,
                "account_ids": sorted(int(a) for a in grp["account_id"].unique()),
                "txn_ids": sorted(int(t) for t in grp["txn_id"]),
            })

    answer_key = pd.DataFrame([
        {
            "case_id": k["case_id"], "typology": k["typology"],
            "n_accounts": len(k["account_ids"]), "n_transactions": len(k["txn_ids"]),
            "account_ids": k["account_ids"], "txn_ids": k["txn_ids"],
            "rationale": k["rationale"], "note": k["note"],
        }
        for k in cases
    ])
    return FraudPlant(transactions=tx, answer_key=answer_key, cases=cases)


def recompute_account_rollups(accounts: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    """Recompute total_spend_aed and txn_count from the final transactions.

    After planting rings, account rollups must be recomputed so the shipped
    dataset still reconciles to the fils, ring activity included.
    """
    acc = accounts.copy()
    spend = transactions.groupby("account_id")["amount_aed"].sum().round(2)
    counts = transactions.groupby("account_id")["txn_id"].count()
    acc["total_spend_aed"] = acc["account_id"].map(spend).fillna(0.0).round(2)
    acc["txn_count"] = acc["account_id"].map(counts).fillna(0).astype(int)
    return acc
