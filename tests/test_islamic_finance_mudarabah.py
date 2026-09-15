"""
Mudarabah (AAOIFI Sharia Standard No. 13) and Standard 40's pooled
investment-account distribution rule: profit shared by a pre-agreed
ratio, loss borne entirely by the capital provider.

The property that matters and that these tests actually check: a
non-negligent loss leaves the mudarib's realized P&L at EXACTLY zero.
Most synthetic generators asked to model "profit sharing" default to a
symmetric split -- both parties gain and lose by the same ratio -- which
is precisely the violation these tests are pinned against.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))

from islamic_finance_mudarabah import build, verify


def test_full_verify_passes_on_a_fresh_run():
    tables = build(n_ventures=800, seed=6)
    assert verify(tables)


def test_profit_splits_by_the_preagreed_ratio_exactly():
    tables = build(n_ventures=800, seed=2)
    ventures = tables["mudarabah_ventures"]
    profit = ventures[ventures["venture_pnl"] > 0]
    recomputed = (profit["venture_pnl"] * profit["mudarib_profit_share_ratio"]).round(2)
    assert np.allclose(profit["mudarib_pnl"], recomputed)


def test_ordinary_loss_leaves_mudarib_pnl_at_exactly_zero():
    tables = build(n_ventures=1200, seed=3)
    ventures = tables["mudarabah_ventures"]
    ordinary_loss = ventures[(ventures["venture_pnl"] < 0) & ~ventures["negligent"]]
    assert len(ordinary_loss) > 0, "widen the sample to exercise the loss path"
    assert (ordinary_loss["mudarib_pnl"] == 0.0).all()


def test_ordinary_loss_lands_entirely_on_the_capital_provider():
    tables = build(n_ventures=1200, seed=3)
    ventures = tables["mudarabah_ventures"]
    ordinary_loss = ventures[(ventures["venture_pnl"] < 0) & ~ventures["negligent"]]
    assert np.allclose(ordinary_loss["rabb_al_mal_pnl"], ordinary_loss["venture_pnl"])


def test_negligent_loss_shifts_onto_the_mudarib_instead():
    tables = build(n_ventures=1200, seed=3)
    ventures = tables["mudarabah_ventures"]
    negligent_loss = ventures[(ventures["venture_pnl"] < 0) & ventures["negligent"]]
    assert len(negligent_loss) > 0, "widen the sample to exercise the negligence path"
    assert np.allclose(negligent_loss["mudarib_pnl"], negligent_loss["venture_pnl"])
    assert (negligent_loss["rabb_al_mal_pnl"] == 0.0).all()


def test_no_mudarib_capital_contribution_column():
    tables = build(n_ventures=300, seed=4)
    assert "mudarib_capital_contribution" not in tables["mudarabah_ventures"].columns


def test_pnl_always_reconciles_to_the_venture_total():
    tables = build(n_ventures=800, seed=5)
    ventures = tables["mudarabah_ventures"]
    assert np.allclose(ventures["mudarib_pnl"] + ventures["rabb_al_mal_pnl"], ventures["venture_pnl"])


def test_pool_bank_fee_is_zero_in_a_losing_period():
    tables = build(n_ventures=300, seed=6)
    pool = tables["mudarabah_pool_periods"]
    losing = pool[pool["pool_pnl"] < 0]
    assert (losing["bank_mudarib_fee"] == 0.0).all()


def test_pool_depositor_pnl_reconciles_to_pool_pnl_net_of_bank_fee():
    tables = build(n_ventures=300, seed=6)
    pool = tables["mudarabah_pool_periods"]
    for period, g in pool.groupby("period"):
        pool_pnl = g["pool_pnl"].iloc[0]
        bank_fee = g["bank_mudarib_fee"].sum()
        assert abs(g["depositor_pnl"].sum() - (pool_pnl - bank_fee)) < 0.05, period


def test_zero_orphaned_foreign_keys():
    tables = build(n_ventures=300, seed=7)
    ventures = tables["mudarabah_ventures"]
    assert ventures["provider_id"].isin(tables["capital_providers"]["provider_id"]).all()


def test_coherence_audit_is_clean():
    import misata
    tables = build(n_ventures=500, seed=13)
    report = misata.coherence_audit(tables)
    assert report.clean, report.summary()
