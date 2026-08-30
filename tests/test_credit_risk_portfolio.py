"""
Credit risk: loan-level PD/LGD/EAD data where the numbers are the regulator's,
not a plausible-sounding guess.

PD by credit rating is S&P Global Ratings' own published annual global
corporate default rate, averaged across the 2019-2024 studies. LGD by
seniority is the Basel Foundation IRB *supervisory* value (40% senior
unsecured, 75% subordinated) -- a number banks are required to use, not one
they estimate. EAD for a partially-drawn facility follows the Basel
credit-conversion-factor formula: EAD = drawn + CCF x undrawn.

The property that matters and that these tests actually check: a borrower's
credit rating is not a decorative label. Whether that borrower's loans
default is a real Bernoulli draw at the rating's own published PD, so the
realized default rate per rating grade is a measured fact about the
generated rows, checked against the cited source, not an assertion about
what the engine is supposed to do.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))

from credit_risk_portfolio import (
    build, verify, PD_BY_RATING, LGD_BY_SENIORITY, CCF_BY_COMMITMENT,
)


def test_full_verify_passes_on_a_fresh_run():
    tables = build(n_borrowers=2000, seed=3)
    assert verify(tables)


def test_investment_grade_never_defaults():
    # AAA, AA, and A are each exactly 0.00% in every one of the six S&P
    # studies averaged here. That is a real fact about the cited data, not
    # a rounding artifact, and it should hold EXACTLY in the generated
    # rows: zero defaults, not "close to zero."
    tables = build(n_borrowers=4000, seed=5)
    loans = tables["loans"].merge(
        tables["borrowers"][["borrower_id", "credit_rating"]], on="borrower_id")
    for rating in ("AAA", "AA", "A"):
        sub = loans[loans["credit_rating"] == rating]
        assert len(sub) > 0, f"no loans drawn for {rating}, widen the sample"
        assert sub["defaulted"].sum() == 0, (rating, sub["defaulted"].sum())


def test_speculative_grades_default_at_roughly_the_cited_rate():
    tables = build(n_borrowers=6000, seed=7)
    loans = tables["loans"].merge(
        tables["borrowers"][["borrower_id", "credit_rating"]], on="borrower_id")
    for rating in ("BB", "B", "CCC"):
        sub = loans[loans["credit_rating"] == rating]
        measured = sub["defaulted"].mean()
        declared = PD_BY_RATING[rating]
        assert abs(measured - declared) < max(0.02, declared * 0.6), (rating, measured, declared)


def test_lgd_matches_basel_foundation_irb_exactly():
    tables = build(n_borrowers=1500, seed=2)
    loans = tables["loans"]
    for seniority, declared_lgd in LGD_BY_SENIORITY.items():
        sub = loans[loans["seniority"] == seniority]
        assert (sub["lgd"] == declared_lgd).all(), seniority


def test_ead_reconciles_to_drawn_plus_ccf_times_undrawn():
    tables = build(n_borrowers=1500, seed=2)
    loans = tables["loans"]
    recomputed = (loans["drawn_amount"] + loans["ccf"] * loans["undrawn_commitment"]).round(2)
    assert np.allclose(loans["ead"], recomputed)
    # And the CCF actually used is the declared Basel table, not something
    # else silently substituted in.
    for commitment_type, declared_ccf in CCF_BY_COMMITMENT.items():
        sub = loans[loans["commitment_type"] == commitment_type]
        assert (sub["ccf"] == declared_ccf).all(), commitment_type


def test_term_loans_have_no_undrawn_commitment():
    tables = build(n_borrowers=1500, seed=2)
    term = tables["loans"][tables["loans"]["commitment_type"] == "term_loan"]
    assert (term["undrawn_commitment"] == 0).all()


def test_expected_loss_equals_pd_times_lgd_times_ead():
    tables = build(n_borrowers=1500, seed=2)
    loans = tables["loans"]
    recomputed = (loans["pd"] * loans["lgd"] * loans["ead"]).round(2)
    assert np.allclose(loans["expected_loss"], recomputed)


def test_realized_loss_is_consistent_with_the_default_flag():
    tables = build(n_borrowers=3000, seed=9)
    loans = tables["loans"]
    assert (loans.loc[~loans["defaulted"], "realized_loss"] == 0).all()
    defaulted = loans[loans["defaulted"]]
    if len(defaulted):
        assert np.allclose(defaulted["realized_loss"], (defaulted["lgd"] * defaulted["ead"]).round(2))


def test_zero_orphaned_foreign_keys():
    tables = build(n_borrowers=800, seed=4)
    assert tables["loans"]["borrower_id"].isin(tables["borrowers"]["borrower_id"]).all()


def test_reproducible_with_the_same_seed():
    a = build(n_borrowers=500, seed=13)
    b = build(n_borrowers=500, seed=13)
    assert a["borrowers"]["credit_rating"].equals(b["borrowers"]["credit_rating"])
    assert a["loans"]["defaulted"].equals(b["loans"]["defaulted"])
    assert a["loans"]["expected_loss"].equals(b["loans"]["expected_loss"])


def test_dollar_amounts_never_carry_more_than_cent_precision():
    # Found in a manual realism audit: drawn_amount and undrawn_commitment
    # shipped as raw engine floats (130028.33004434995), which gives away a
    # synthetic file faster than anything else in it -- no loan tape on
    # earth carries a dollar amount to eleven decimal places. Pinned here so
    # a future schema edit that drops "decimals": 2 fails loudly instead of
    # shipping to the public dataset again.
    tables = build(n_borrowers=500, seed=6)
    for col in ("drawn_amount", "undrawn_commitment", "ead", "expected_loss", "realized_loss"):
        values = tables["loans"][col]
        cents = (values * 100).round()
        assert np.allclose(values * 100, cents, atol=1e-6), f"{col} carries sub-cent precision"


def test_origination_date_has_no_time_of_day():
    # A second, related realism finding from the same audit: "type": "date"
    # was silently getting a time-of-day added by the engine's temporal
    # profile system, so origination_date read as
    # "2025-09-12 08:16:54" instead of a plain calendar day. Fixed in
    # misata/simulator.py's date-generation branch; pinned here so a
    # regression there is caught at this level too, not just in the
    # engine's own test suite.
    tables = build(n_borrowers=500, seed=8)
    dates = tables["loans"]["origination_date"]
    assert (dates.dt.normalize() == dates).all()
