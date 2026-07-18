"""Tests for the Bank-in-a-Box certified fraud evalpack (examples/bank_evalpack.py)."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("duckdb")

_EX = Path(__file__).resolve().parent.parent / "examples"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _EX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ft = _load("fraud_typologies")
be = _load("bank_evalpack")


def _bank(seed=3):
    rng = np.random.default_rng(seed)
    n_acc, n_tx = 150, 3000
    accounts = pd.DataFrame({"account_id": np.arange(1, n_acc + 1)})
    accounts["total_spend_aed"] = 0.0
    accounts["txn_count"] = 0
    ts = pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 180 * 24, n_tx), unit="h")
    tx = pd.DataFrame({
        "txn_id": np.arange(1, n_tx + 1),
        "account_id": rng.choice(accounts["account_id"], n_tx),
        "txn_ts": ts,
        "channel": "card_pos",
        "merchant_category": "Groceries",
        "merchant_name": "CARREFOUR",
        "amount_aed": rng.uniform(10, 800, n_tx).round(2),
        "description": "POS PURCHASE",
        "is_fraud": rng.random(n_tx) < 0.02,
    })
    return accounts, tx


def test_evalpack_all_questions_verified(tmp_path):
    accounts, tx = _bank()
    plant = ft.plant_fraud_typologies(transactions=tx, accounts=accounts, seed=5)
    acc = ft.recompute_account_rollups(accounts, plant.transactions)
    tables = {"accounts": acc, "transactions": plant.transactions}

    result = be.build_bank_evalpack(tables, plant.answer_key, tmp_path)
    cert = result["certificate"]

    assert cert["all_match"] is True
    assert cert["candidates_dropped"] == 0
    assert cert["questions_shipped"] > 20


def test_evalpack_writes_artifacts(tmp_path):
    accounts, tx = _bank()
    plant = ft.plant_fraud_typologies(transactions=tx, accounts=accounts, seed=5)
    acc = ft.recompute_account_rollups(accounts, plant.transactions)
    be.build_bank_evalpack({"accounts": acc, "transactions": plant.transactions}, plant.answer_key, tmp_path)

    assert (tmp_path / "questions.json").exists()
    assert (tmp_path / "certificate.json").exists()
    assert (tmp_path / "tables" / "transactions.csv").exists()


def test_ring_total_question_is_correct(tmp_path):
    accounts, tx = _bank()
    plant = ft.plant_fraud_typologies(transactions=tx, accounts=accounts, seed=5)
    acc = ft.recompute_account_rollups(accounts, plant.transactions)
    result = be.build_bank_evalpack({"accounts": acc, "transactions": plant.transactions}, plant.answer_key, tmp_path)

    ring_q = next(q for q in result["shipped"] if "any organized-fraud ring" in q.question)
    planted = plant.transactions["fraud_case_id"].notna().sum()
    assert ring_q.expected_answer == planted
