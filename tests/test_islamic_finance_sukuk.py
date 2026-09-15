"""
Investment Sukuk (AAOIFI Sharia Standard No. 17): a Periodic Distribution
Amount that traces to a real underlying asset pool's actual income, not
a rate applied to face value -- and never called "interest" or "coupon".

The property that matters and that these tests actually check: the PDA
is recomputed exactly from the underlying Ijarah pool's own rental
income (built by `islamic_finance_ijarah.py`), and redemption at maturity
is exactly face value with nothing compounded into it.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))

from islamic_finance_sukuk import build, verify


def test_full_verify_passes_on_a_fresh_run():
    tables = build(n_issuances=3, seed=11)
    assert verify(tables)


def test_total_issuance_value_equals_face_value_times_certificates():
    tables = build(n_issuances=3, seed=2)
    issuances = tables["sukuk_issuances"]
    recomputed = (issuances["face_value_per_certificate"] * issuances["n_certificates"]).round(2)
    assert np.allclose(issuances["total_issuance_value"], recomputed)


def test_pda_traces_exactly_to_pool_rental_income():
    tables = build(n_issuances=3, seed=2)
    distributions = tables["sukuk_distributions"]
    issuances = tables["sukuk_issuances"]
    merged = distributions.merge(issuances[["issuance_id", "n_certificates"]], on="issuance_id")
    recomputed = (merged["pool_rental_income"] / merged["n_certificates"]).round(4)
    assert np.allclose(merged["periodic_distribution_amount"], recomputed, atol=1e-4)


def test_no_column_is_named_interest_or_coupon():
    tables = build(n_issuances=2, seed=3)
    forbidden = {"interest", "coupon", "coupon_rate", "interest_rate"}
    for df in tables.values():
        assert forbidden.isdisjoint(df.columns)


def test_redemption_equals_face_value_exactly():
    tables = build(n_issuances=3, seed=4)
    issuances = tables["sukuk_issuances"]
    assert (issuances["redemption_amount_per_certificate"] == issuances["face_value_per_certificate"]).all()


def test_every_certificate_matches_its_issuances_face_value():
    tables = build(n_issuances=3, seed=5)
    issuances = tables["sukuk_issuances"]
    certificates = tables["sukuk_certificates"]
    merged = certificates.merge(issuances[["issuance_id", "face_value_per_certificate"]], on="issuance_id")
    assert (merged["face_value"] == merged["face_value_per_certificate"]).all()


def test_zero_orphaned_foreign_keys():
    tables = build(n_issuances=2, seed=6)
    issuances = tables["sukuk_issuances"]
    assert tables["sukuk_certificates"]["issuance_id"].isin(issuances["issuance_id"]).all()
    assert tables["sukuk_distributions"]["issuance_id"].isin(issuances["issuance_id"]).all()


def test_reproducible_with_the_same_seed():
    a = build(n_issuances=2, seed=13)
    b = build(n_issuances=2, seed=13)
    assert a["sukuk_issuances"]["total_issuance_value"].equals(b["sukuk_issuances"]["total_issuance_value"])


def test_coherence_audit_is_clean():
    import misata
    tables = build(n_issuances=3, seed=17)
    report = misata.coherence_audit(tables)
    assert report.clean, report.summary()
