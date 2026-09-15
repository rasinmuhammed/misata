"""
Murabahah: a cost-plus sale under AAOIFI Sharia Standard No. 8, where
selling_price = cost_price + profit_margin exactly and the repayment
schedule carries no interest.

The property that matters and that these tests actually check: the total
a customer repays across the life of a contract is fixed at signing and
split into equal installments, not a schedule that quietly re-derives
itself as rate x outstanding_balance the way a conventional amortizing
loan would. That reintroduction of riba is the specific failure mode a
Sharia-literate reviewer would audit for, and it's what most of these
tests are pinned against.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))

from islamic_finance_murabahah import (
    build, verify, MARGIN_RATE_MIN, MARGIN_RATE_MAX,
)


def test_full_verify_passes_on_a_fresh_run():
    tables = build(n_contracts=1000, seed=3)
    assert verify(tables)


def test_selling_price_equals_cost_plus_margin_exactly():
    tables = build(n_contracts=800, seed=2)
    contracts = tables["murabahah_contracts"]
    recomputed = (contracts["cost_price"] + contracts["profit_margin"]).round(2)
    assert np.allclose(contracts["selling_price"], recomputed)


def test_profit_margin_traces_to_a_disclosed_rate_on_cost_price():
    tables = build(n_contracts=800, seed=2)
    contracts = tables["murabahah_contracts"]
    recomputed = (contracts["cost_price"] * contracts["margin_rate"]).round(2)
    assert np.allclose(contracts["profit_margin"], recomputed)


def test_margin_rate_stays_within_the_declared_band():
    tables = build(n_contracts=800, seed=2)
    rates = tables["murabahah_contracts"]["margin_rate"]
    assert rates.between(MARGIN_RATE_MIN, MARGIN_RATE_MAX).all()


def test_no_column_encodes_an_interest_rate():
    # A Murabahah contract has a cost, a disclosed margin, and a selling
    # price. Nothing here should look like a per-period interest rate
    # applied to a balance -- if it did, this would be a conventional loan
    # wearing Murabahah vocabulary, not an actual cost-plus sale.
    tables = build(n_contracts=500, seed=4)
    contracts = tables["murabahah_contracts"]
    forbidden = {"interest_rate", "apr", "compounding_period", "outstanding_balance"}
    assert forbidden.isdisjoint(contracts.columns)


def test_total_repaid_equals_selling_price_fixed_at_signing():
    tables = build(n_contracts=1000, seed=6)
    contracts = tables["murabahah_contracts"]
    installments = tables["murabahah_installments"]
    totals = installments.groupby("contract_id")["installment_amount"].sum().round(2)
    priced = contracts.set_index("contract_id")["selling_price"]
    assert np.allclose(totals.reindex(priced.index), priced)


def test_every_installment_on_a_contract_is_the_same_amount():
    # The hallmark that separates a fixed Murabahah repayment from a
    # reducing-balance amortization: no split into shrinking interest plus
    # growing principal, because there is nothing to split.
    tables = build(n_contracts=1000, seed=6)
    installments = tables["murabahah_installments"]

    def equal_within_a_cent(g):
        return len(g) <= 1 or (g.iloc[:-1] - g.iloc[0]).abs().max() < 0.005

    ok = installments.groupby("contract_id")["installment_amount"].apply(equal_within_a_cent)
    assert bool(ok.all())


def test_installment_count_matches_tenor_months_exactly():
    tables = build(n_contracts=1000, seed=6)
    contracts = tables["murabahah_contracts"]
    installments = tables["murabahah_installments"]
    counts = installments.groupby("contract_id").size()
    tenors = contracts.set_index("contract_id")["tenor_months"]
    assert (counts.reindex(tenors.index) == tenors).all()


def test_zero_orphaned_foreign_keys():
    tables = build(n_contracts=500, seed=4)
    contracts = tables["murabahah_contracts"]
    installments = tables["murabahah_installments"]
    assert contracts["customer_id"].isin(tables["customers"]["customer_id"]).all()
    assert installments["contract_id"].isin(contracts["contract_id"]).all()


def test_dollar_amounts_never_carry_more_than_cent_precision():
    tables = build(n_contracts=500, seed=6)
    contracts = tables["murabahah_contracts"]
    installments = tables["murabahah_installments"]
    for df, col in (
        (contracts, "cost_price"), (contracts, "profit_margin"),
        (contracts, "selling_price"), (installments, "installment_amount"),
    ):
        values = df[col]
        cents = (values * 100).round()
        assert np.allclose(values * 100, cents, atol=1e-6), f"{col} carries sub-cent precision"


def test_reproducible_with_the_same_seed():
    a = build(n_contracts=300, seed=13)
    b = build(n_contracts=300, seed=13)
    assert a["murabahah_contracts"]["selling_price"].equals(b["murabahah_contracts"]["selling_price"])
    assert a["murabahah_installments"]["installment_amount"].equals(
        b["murabahah_installments"]["installment_amount"])


def test_coherence_audit_is_clean():
    import misata
    tables = build(n_contracts=500, seed=8)
    report = misata.coherence_audit(tables)
    assert report.clean, report.summary()
