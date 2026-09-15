"""
Takaful: the Participants' Takaful Fund (PTF) and the Operator's Fund
never commingle. Claims draw from the PTF only, capped at what the fund
actually holds; the operator's fund is a pure running sum of Wakala fees,
completely unaffected by claims.

The property that matters and that these tests actually check: the PTF
balance never goes negative, and no claim ever reaches into the
operator's fund -- the structural separation the whole model exists to
prove, not a docstring claim about it.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))

from islamic_finance_takaful import build, verify


def test_full_verify_passes_on_a_fresh_run():
    tables = build(n_policies=600, seed=8)
    assert verify(tables)


def test_contribution_splits_exactly_into_fee_and_ptf_share():
    tables = build(n_policies=500, seed=2)
    policies = tables["takaful_policies"]
    recomputed_fee = (policies["contribution"] * policies["wakala_fee_rate"]).round(2)
    assert np.allclose(policies["wakala_fee"], recomputed_fee)
    assert np.allclose(policies["wakala_fee"] + policies["ptf_contribution"], policies["contribution"])


def test_every_claim_is_marked_paid_from_participants_fund():
    tables = build(n_policies=800, seed=3)
    claims = tables["takaful_claims"]
    assert (claims["paid_from_fund"] == "participants").all()


def test_ptf_balance_never_goes_negative():
    tables = build(n_policies=800, seed=3)
    ledger = tables["takaful_fund_ledger"]
    assert (ledger["ptf_balance_after_claims"] >= -0.005).all()


def test_claims_never_exceed_what_they_requested():
    tables = build(n_policies=800, seed=3)
    claims = tables["takaful_claims"]
    assert (claims["amount_paid"] <= claims["amount_requested"] + 0.005).all()


def test_operator_fund_is_unaffected_by_claims():
    tables = build(n_policies=800, seed=4)
    ledger = tables["takaful_fund_ledger"]
    recomputed = ledger["operator_fee_in"].cumsum().round(2)
    assert np.allclose(ledger["operator_balance"], recomputed)


def test_claims_in_a_period_never_exceed_that_periods_ptf_balance():
    tables = build(n_policies=800, seed=5)
    ledger = tables["takaful_fund_ledger"]
    claims = tables["takaful_claims"]
    period_ptf = ledger.set_index("period")["ptf_balance_before_claims"]
    claims_by_period = claims.groupby("period")["amount_paid"].sum()
    assert (claims_by_period <= period_ptf.reindex(claims_by_period.index) + 0.01).all()


def test_zero_orphaned_foreign_keys():
    tables = build(n_policies=400, seed=6)
    policies = tables["takaful_policies"]
    claims = tables["takaful_claims"]
    assert policies["participant_id"].isin(tables["participants"]["participant_id"]).all()
    assert claims["policy_id"].isin(policies["policy_id"]).all()


def test_reproducible_with_the_same_seed():
    a = build(n_policies=300, seed=13)
    b = build(n_policies=300, seed=13)
    assert a["takaful_policies"]["contribution"].equals(b["takaful_policies"]["contribution"])


def test_coherence_audit_is_clean():
    import misata
    tables = build(n_policies=500, seed=21)
    report = misata.coherence_audit(tables)
    assert report.clean, report.summary()
