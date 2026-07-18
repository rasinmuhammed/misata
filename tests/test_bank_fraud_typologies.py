"""Tests for the Bank-in-a-Box fraud typology overlay (examples/fraud_typologies.py)."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_MODULE_PATH = Path(__file__).resolve().parent.parent / "examples" / "fraud_typologies.py"
_spec = importlib.util.spec_from_file_location("fraud_typologies", _MODULE_PATH)
ft = importlib.util.module_from_spec(_spec)
sys.modules["fraud_typologies"] = ft  # dataclass type-resolution needs this
_spec.loader.exec_module(ft)


def _base_bank(n_accounts=200, n_txns=4000, seed=1):
    rng = np.random.default_rng(seed)
    accounts = pd.DataFrame({"account_id": np.arange(1, n_accounts + 1)})
    ts = pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 180 * 24, n_txns), unit="h")
    transactions = pd.DataFrame({
        "txn_id": np.arange(1, n_txns + 1),
        "account_id": rng.choice(accounts["account_id"], n_txns),
        "txn_ts": ts,
        "channel": rng.choice(["card_pos", "transfer", "atm"], n_txns),
        "merchant_category": rng.choice(["Groceries", "Fuel", "Dining"], n_txns),
        "merchant_name": "SOME MERCHANT",
        "amount_aed": rng.uniform(10, 900, n_txns).round(2),
        "description": "POS PURCHASE",
        "is_fraud": rng.random(n_txns) < 0.02,
    })
    return accounts, transactions


def test_planting_adds_rows_and_answer_key():
    accounts, tx = _base_bank()
    plant = ft.plant_fraud_typologies(accounts=accounts, transactions=tx, seed=7)
    assert len(plant.transactions) > len(tx)  # rings add rows
    assert len(plant.answer_key) == 12 + 15 + 10  # default case counts
    assert set(plant.answer_key["typology"]) == {"mule_chain", "structuring", "card_bustout"}


def test_answer_key_matches_planted_rows_exactly():
    accounts, tx = _base_bank()
    plant = ft.plant_fraud_typologies(accounts=accounts, transactions=tx, seed=7)
    planted = plant.transactions[plant.transactions["fraud_case_id"].notna()]
    # every txn_id claimed by the answer key exists and is tagged with its case
    for case in plant.cases:
        rows = planted[planted["fraud_case_id"] == case["case_id"]]
        assert sorted(rows["txn_id"]) == sorted(case["txn_ids"])
        assert set(rows["fraud_typology"]) == {case["typology"]}


def test_rings_are_invisible_to_naive_flag():
    accounts, tx = _base_bank()
    plant = ft.plant_fraud_typologies(accounts=accounts, transactions=tx, seed=7)
    planted = plant.transactions[plant.transactions["fraud_case_id"].notna()]
    # organized fraud evades is_fraud on purpose
    assert not planted["is_fraud"].any()


def test_structuring_stays_below_threshold():
    accounts, tx = _base_bank()
    plant = ft.plant_fraud_typologies(accounts=accounts, transactions=tx, seed=7)
    struct = plant.transactions[plant.transactions["fraud_typology"] == "structuring"]
    assert (struct["amount_aed"] < ft.REPORTING_THRESHOLD_AED).all()
    # but each is a large deposit, not noise
    assert (struct["amount_aed"] > 0.8 * ft.REPORTING_THRESHOLD_AED).all()


def test_organic_txn_ids_stay_unique_after_planting():
    accounts, tx = _base_bank()
    plant = ft.plant_fraud_typologies(accounts=accounts, transactions=tx, seed=7)
    assert plant.transactions["txn_id"].is_unique


def test_rollups_reconcile_after_recompute():
    accounts, tx = _base_bank()
    accounts["total_spend_aed"] = 0.0
    accounts["txn_count"] = 0
    plant = ft.plant_fraud_typologies(accounts=accounts, transactions=tx, seed=7)
    acc = ft.recompute_account_rollups(accounts, plant.transactions)
    spend = plant.transactions.groupby("account_id")["amount_aed"].sum().round(2)
    joined = acc.set_index("account_id")["total_spend_aed"]
    assert (joined.subtract(spend, fill_value=0.0).abs() < 0.005).all()


def test_reproducible_with_seed():
    accounts, tx = _base_bank()
    a = ft.plant_fraud_typologies(accounts=accounts, transactions=tx, seed=7).answer_key
    b = ft.plant_fraud_typologies(accounts=accounts, transactions=tx, seed=7).answer_key
    pd.testing.assert_frame_equal(a, b)
