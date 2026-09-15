"""
Ijarah and Ijarah Muntahia Bittamleek (AAOIFI Sharia Standard No. 9):
lease payments for the use of an asset, not repayment of its cost.

The property that matters and that these tests actually check: rental is
level, not amortizing, because a lease carries no principal balance to
retire. For Ijarah Muntahia Bittamleek, the ownership_transfer_price is a
separate, nominal, pre-agreed figure independent of the rental total --
if it scaled with the rental total or term, it would really be a
disguised balloon payment on a loan wearing a lease's vocabulary.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))

from islamic_finance_ijarah import build, verify, TRANSFER_PRICE_FRACTION


def test_full_verify_passes_on_a_fresh_run():
    tables = build(n_contracts=800, seed=4)
    assert verify(tables)


def test_total_rental_equals_monthly_rental_times_term():
    tables = build(n_contracts=600, seed=2)
    contracts = tables["ijarah_contracts"]
    recomputed = (contracts["monthly_rental"] * contracts["term_months"]).round(2)
    assert np.allclose(contracts["total_rental"], recomputed)


def test_every_rental_on_a_contract_is_level():
    tables = build(n_contracts=600, seed=2)
    schedule = tables["ijarah_schedule"]
    rentals = schedule[schedule["event_type"] == "rental"]

    def equal_within_a_cent(g):
        return len(g) <= 1 or (g.iloc[:-1] - g.iloc[0]).abs().max() < 0.005

    ok = rentals.groupby("contract_id")["amount"].apply(equal_within_a_cent)
    assert bool(ok.all())


def test_lessor_owns_the_asset_through_every_rental_period():
    tables = build(n_contracts=400, seed=3)
    schedule = tables["ijarah_schedule"]
    rentals = schedule[schedule["event_type"] == "rental"]
    assert (rentals["asset_owner"] == "lessor").all()


def test_imb_transfer_price_is_nominal_and_traces_to_asset_value_alone():
    tables = build(n_contracts=800, seed=5)
    contracts = tables["ijarah_contracts"]
    imb = contracts[contracts["lease_type"] == "ijarah_muntahia_bittamleek"]
    recomputed = (imb["asset_value"] * TRANSFER_PRICE_FRACTION).round(2)
    assert np.allclose(imb["ownership_transfer_price"], recomputed)


def test_plain_ijarah_never_transfers_ownership():
    tables = build(n_contracts=800, seed=5)
    contracts = tables["ijarah_contracts"]
    schedule = tables["ijarah_schedule"]
    plain_ids = set(contracts.loc[contracts["lease_type"] == "ijarah", "contract_id"])
    transfers = schedule[schedule["event_type"] == "ownership_transfer"]
    assert transfers["contract_id"].isin(plain_ids).sum() == 0
    assert (contracts.loc[contracts["contract_id"].isin(plain_ids),
                           "ownership_transfer_price"] == 0).all()


def test_no_interest_rate_or_outstanding_balance_column():
    tables = build(n_contracts=300, seed=6)
    forbidden = {"interest_rate", "apr", "outstanding_principal", "outstanding_balance"}
    assert forbidden.isdisjoint(tables["ijarah_contracts"].columns)
    assert forbidden.isdisjoint(tables["ijarah_schedule"].columns)


def test_zero_orphaned_foreign_keys():
    tables = build(n_contracts=400, seed=7)
    contracts = tables["ijarah_contracts"]
    schedule = tables["ijarah_schedule"]
    assert contracts["lessee_id"].isin(tables["lessees"]["lessee_id"]).all()
    assert schedule["contract_id"].isin(contracts["contract_id"]).all()


def test_reproducible_with_the_same_seed():
    a = build(n_contracts=200, seed=13)
    b = build(n_contracts=200, seed=13)
    assert a["ijarah_contracts"]["total_rental"].equals(b["ijarah_contracts"]["total_rental"])


def test_coherence_audit_is_clean():
    import misata
    tables = build(n_contracts=400, seed=9)
    report = misata.coherence_audit(tables)
    assert report.clean, report.summary()
