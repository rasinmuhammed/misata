"""
Mudarabah (AAOIFI Sharia Standard No. 13) and the distribution rule for
pooled investment accounts (AAOIFI Sharia Standard No. 40) -- profit
sharing with an ASYMMETRIC loss allocation, which is the actual hard part
to get right and the actual proof point of this example.

A Mudarabah has two parties: the rabb al-mal (capital provider), who puts
up all the capital and none of the labor, and the mudarib (managing
partner), who puts up all the labor and none of the capital. Profit is
split by a ratio agreed BEFORE the venture starts. Loss is not split at
all: the rabb al-mal bears every dirham of financial loss, because it was
their capital, and the mudarib bears no financial loss -- only the lost
value of their own time and effort, which this example does not attempt
to price. The one exception, and the reason `negligent` exists as a
column at all: if the mudarib breached the contract or acted with proven
negligence (ta'addi), Sharia makes them liable for the resulting loss.
That is a real exception with real conditions attached, not a backdoor
for reintroducing a symmetric split by default.

Most synthetic generators asked to model "profit sharing" would default
to a symmetric P&L split -- both parties share gains AND losses by the
same ratio, the way conventional equity partners do. That default is
exactly the violation this example's `verify()` checks for and refuses to
produce: on every loss-making, non-negligent venture, the mudarib's
realized P&L must be EXACTLY zero.

Two tables, two AAOIFI standards:

  * `mudarabah_ventures` -- single-venture Mudarabah under Standard 13.
  * `mudarabah_pool_periods` -- a bank's pooled investment accounts under
    Standard 40: many rabb al-mal depositors share one pool's profit,
    weighted by their own capital and how long it sat in the pool, after
    the bank (acting as mudarib for the pool) takes its own agreed share.

Run it directly. Every guarantee below is checked against the data this
script just generated, not asserted.
"""

import numpy as np
import pandas as pd

import misata

RNG_SEED = 13

VENTURE_TYPES = ["Trade Finance", "Real Estate Development", "Commodity Trading",
                  "Equipment Leasing Fund", "Working Capital"]
VENTURE_WEIGHTS = [0.25, 0.20, 0.20, 0.15, 0.20]

# Profit-sharing ratio for the mudarib, agreed before the venture starts.
# Not an AAOIFI-published number -- each Mudarabah agreement sets its own
# ratio -- declared here as a realistic market range.
MUDARIB_SHARE_MEAN = 0.30
MUDARIB_SHARE_STD = 0.08
MUDARIB_SHARE_MIN = 0.10
MUDARIB_SHARE_MAX = 0.50

# Most ventures return a profit; a minority run at a loss, and among
# those a small minority are attributable to proven mudarib negligence
# rather than ordinary commercial risk.
LOSS_RATE = 0.22
NEGLIGENCE_RATE_GIVEN_LOSS = 0.15


def build(n_ventures: int = 1500, seed: int = RNG_SEED):
    schema = {
        "capital_providers": {
            "__rows__": int(n_ventures * 0.6),
            "provider_id": {"type": "integer", "primary_key": True},
            "name": {"type": "string", "text_type": "person_name"},
        },
        "mudarabah_ventures": {
            "__rows__": n_ventures,
            "venture_id": {"type": "integer", "primary_key": True},
            "provider_id": {"type": "integer",
                             "foreign_key": {"table": "capital_providers", "column": "provider_id"}},
            "venture_type": {"type": "string", "enum": VENTURE_TYPES, "weights": VENTURE_WEIGHTS},
            "capital_contributed": {"type": "float", "min": 20_000, "max": 3_000_000,
                                      "distribution": "lognormal", "mu": 11.5, "sigma": 1.1,
                                      "decimals": 2},
            "venture_start_date": {"type": "date", "min_date": "2022-01-01", "max_date": "2024-12-01"},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))
    return _reconcile(tables, seed)


def _reconcile(tables: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed + 1)

    ventures = tables["mudarabah_ventures"].copy()
    n = len(ventures)

    # The profit-sharing ratio is fixed before results are known -- it
    # never depends on whether the venture ends up making money.
    mudarib_share = np.clip(
        rng.normal(MUDARIB_SHARE_MEAN, MUDARIB_SHARE_STD, n),
        MUDARIB_SHARE_MIN, MUDARIB_SHARE_MAX,
    )
    ventures["mudarib_profit_share_ratio"] = mudarib_share.round(4)

    # A venture return on capital -- can be positive or negative, drawn
    # independently of the profit-sharing ratio, because the ratio only
    # governs how a positive return gets split, not whether one occurs.
    is_loss = rng.random(n) < LOSS_RATE
    return_pct = np.where(
        is_loss,
        -np.abs(rng.normal(0.12, 0.08, n)),
        np.abs(rng.normal(0.15, 0.10, n)),
    )
    ventures["venture_roi"] = return_pct.round(4)
    ventures["venture_pnl"] = (ventures["capital_contributed"] * ventures["venture_roi"]).round(2)

    negligent = is_loss & (rng.random(n) < NEGLIGENCE_RATE_GIVEN_LOSS)
    ventures["negligent"] = negligent

    profit_mask = ventures["venture_pnl"] > 0
    loss_mask = ventures["venture_pnl"] < 0

    mudarib_pnl = np.zeros(n)
    rabb_al_mal_pnl = np.zeros(n)

    # Profit: split by the pre-agreed ratio. Both parties gain.
    mudarib_pnl[profit_mask.to_numpy()] = (
        ventures.loc[profit_mask, "venture_pnl"] * ventures.loc[profit_mask, "mudarib_profit_share_ratio"]
    ).to_numpy()
    rabb_al_mal_pnl[profit_mask.to_numpy()] = (
        ventures.loc[profit_mask, "venture_pnl"] * (1 - ventures.loc[profit_mask, "mudarib_profit_share_ratio"])
    ).to_numpy()

    # Loss, ordinary commercial risk (not negligent): the rabb al-mal
    # absorbs the ENTIRE loss. The mudarib's financial P&L is exactly
    # zero -- they lose their own uncompensated effort, which is not a
    # dirham figure this table carries.
    ordinary_loss = loss_mask & ~ventures["negligent"]
    rabb_al_mal_pnl[ordinary_loss.to_numpy()] = ventures.loc[ordinary_loss, "venture_pnl"].to_numpy()
    mudarib_pnl[ordinary_loss.to_numpy()] = 0.0

    # Loss attributable to proven mudarib negligence: Sharia makes the
    # mudarib liable for this specific loss, so it -- and only it --
    # shifts onto them. The rabb al-mal's capital is made whole.
    negligent_loss = loss_mask & ventures["negligent"]
    mudarib_pnl[negligent_loss.to_numpy()] = ventures.loc[negligent_loss, "venture_pnl"].to_numpy()
    rabb_al_mal_pnl[negligent_loss.to_numpy()] = 0.0

    ventures["mudarib_pnl"] = np.round(mudarib_pnl, 2)
    ventures["rabb_al_mal_pnl"] = np.round(rabb_al_mal_pnl, 2)
    # Deliberately no `mudarib_capital_contribution` column: the mudarib
    # never contributes capital, so there is nothing for such a column to
    # carry but a structural zero on every row. Its own entire input to
    # the venture is management, which is what makes it not liable for
    # ordinary commercial loss in the first place -- proving that by
    # leaving the field out entirely, rather than by shipping a column
    # that is a constant by construction.

    tables["mudarabah_ventures"] = ventures
    tables["mudarabah_pool_periods"] = _build_pool_periods(seed)
    return tables


def _build_pool_periods(seed: int) -> pd.DataFrame:
    """AAOIFI Standard 40: a bank runs one pooled Mudarabah investment
    account. Multiple rabb al-mal depositors share each period's pool
    profit weighted by their own capital and how long it sat in the pool
    (the standard's "weightage" mechanism), after the bank -- acting as
    mudarib for the whole pool -- takes its own agreed share off the top.
    The same asymmetric loss rule applies at the pool level: a losing
    period debits every depositor pro-rata to their weighted capital, and
    the bank's own management fee for that period is zero, not negative."""
    rng = np.random.default_rng(seed + 2)
    n_depositors = 40
    n_periods = 12
    bank_mudarib_share = 0.20  # the bank's agreed share of pool profit

    capital = rng.lognormal(10.5, 1.0, n_depositors).round(2)
    weight_days = rng.integers(15, 31, n_depositors)  # days held within the period
    weighted_capital = capital * weight_days
    pool_return_pct = rng.normal(0.008, 0.02, n_periods)  # monthly pool return, can be negative

    rows = []
    for period in range(n_periods):
        total_weighted = weighted_capital.sum()
        pool_pnl = round(float(capital.sum() * pool_return_pct[period]), 2)
        if pool_pnl > 0:
            bank_share_amount = round(pool_pnl * bank_mudarib_share, 2)
            depositor_pool = pool_pnl - bank_share_amount
        else:
            # A losing period: depositors absorb the whole loss pro-rata
            # to their weighted capital, and the bank's management fee
            # for that period is exactly zero -- not a negative fee, and
            # not a share of a loss it did not put capital into.
            bank_share_amount = 0.0
            depositor_pool = pool_pnl
        # Round every depositor's share but the last, then absorb the
        # rounding residual into the last one, so depositor_pnl sums to
        # depositor_pool EXACTLY -- the same residual-absorption
        # convention the Murabahah and Ijarah examples use for their own
        # equal-installment schedules.
        shares = weighted_capital / total_weighted
        depositor_pnls = np.round(depositor_pool * shares, 2)
        depositor_pnls[-1] = round(depositor_pool - depositor_pnls[:-1].sum(), 2)
        for i in range(n_depositors):
            rows.append({
                "period": period + 1,
                "depositor_id": i + 1,
                "capital": float(capital[i]),
                "weighted_capital": float(weighted_capital[i]),
                "pool_pnl": pool_pnl,
                "bank_mudarib_fee": bank_share_amount if i == 0 else 0.0,
                "depositor_pnl": float(depositor_pnls[i]),
            })
    return pd.DataFrame(rows)


def verify(tables: dict) -> bool:
    ventures = tables["mudarabah_ventures"]
    pool = tables["mudarabah_pool_periods"]
    checks = []

    # 1. Profit split by the pre-agreed ratio, recomputed independently.
    profit = ventures[ventures["venture_pnl"] > 0]
    recomputed_mudarib = (profit["venture_pnl"] * profit["mudarib_profit_share_ratio"]).round(2)
    checks.append(("profitable ventures: mudarib_pnl equals venture_pnl x the agreed ratio exactly",
                    np.allclose(profit["mudarib_pnl"], recomputed_mudarib)))
    recomputed_rabb = (profit["venture_pnl"] * (1 - profit["mudarib_profit_share_ratio"])).round(2)
    checks.append(("profitable ventures: mudarib + rabb_al_mal profit reconciles to venture_pnl exactly",
                    np.allclose(profit["mudarib_pnl"] + profit["rabb_al_mal_pnl"], profit["venture_pnl"])
                    and np.allclose(profit["rabb_al_mal_pnl"], recomputed_rabb)))

    # 2. THE hard part: an ordinary (non-negligent) loss lands 100% on the
    # rabb al-mal. The mudarib's financial P&L is EXACTLY zero -- not a
    # symmetric split, not a partial absorption.
    ordinary_loss = ventures[(ventures["venture_pnl"] < 0) & ~ventures["negligent"]]
    checks.append(("ordinary-loss ventures: mudarib_pnl is exactly zero, every one",
                    len(ordinary_loss) > 0 and (ordinary_loss["mudarib_pnl"] == 0.0).all()))
    checks.append(("ordinary-loss ventures: rabb_al_mal absorbs the entire loss exactly",
                    np.allclose(ordinary_loss["rabb_al_mal_pnl"], ordinary_loss["venture_pnl"])))

    # 3. The one exception has real conditions: proven negligence shifts
    # that specific loss onto the mudarib, and only that loss.
    negligent_loss = ventures[(ventures["venture_pnl"] < 0) & ventures["negligent"]]
    checks.append(("negligent-loss ventures exist to exercise the exception path",
                    len(negligent_loss) > 0))
    checks.append(("negligent-loss ventures: mudarib bears the loss, rabb_al_mal is made whole",
                    np.allclose(negligent_loss["mudarib_pnl"], negligent_loss["venture_pnl"])
                    and (negligent_loss["rabb_al_mal_pnl"] == 0.0).all()))

    # 4. Structural: the mudarib never contributes capital -- there is no
    # such column at all. If one existed with a real value, "no capital,
    # no financial loss exposure" would not follow.
    checks.append(("no mudarib_capital_contribution column exists (mudarib contributes no capital)",
                    "mudarib_capital_contribution" not in ventures.columns))

    # 5. P&L always reconciles: mudarib + rabb_al_mal == venture_pnl,
    # whether the venture made money or lost it.
    checks.append(("mudarib_pnl + rabb_al_mal_pnl equals venture_pnl exactly, every venture",
                    np.allclose(ventures["mudarib_pnl"] + ventures["rabb_al_mal_pnl"], ventures["venture_pnl"])))

    # 6. Standard 40 pool: the bank's fee is drawn only from a profitable
    # period's pool P&L, never conjured from a losing one.
    losing_periods = pool[pool["pool_pnl"] < 0]
    checks.append(("losing pool periods: bank_mudarib_fee is exactly zero",
                    (losing_periods["bank_mudarib_fee"] == 0.0).all()))

    # 7. Standard 40 pool: within each period, depositor P&L sums exactly
    # to the pool P&L net of the bank's fee (profit) or to the full pool
    # P&L (loss, since the bank takes no fee on a loss).
    for period, g in pool.groupby("period"):
        pool_pnl = g["pool_pnl"].iloc[0]
        bank_fee = g["bank_mudarib_fee"].sum()
        depositor_total = round(float(g["depositor_pnl"].sum()), 2)
        expected = round(pool_pnl - bank_fee, 2)
        if abs(depositor_total - expected) > 0.05:
            checks.append((f"period {period}: depositor P&L reconciles to pool P&L net of bank fee", False))
            break
    else:
        checks.append(("every pool period: depositor P&L reconciles to pool P&L net of bank fee", True))

    # 8. Standard 40 pool: depositor P&L is weighted by capital x days
    # held, not flat per depositor -- the weightage mechanism the
    # standard actually specifies.
    # Exclude the last depositor in each period: it absorbs that period's
    # rounding residual (the same convention Murabahah uses for its final
    # installment), so its own per-unit ratio is not expected to match.
    profitable_period = pool[pool["pool_pnl"] > 0]["period"].iloc[0]
    g = pool[pool["period"] == profitable_period].iloc[:-1]
    per_unit = (g["depositor_pnl"] / g["weighted_capital"]).round(6)
    checks.append(("within a profitable period, P&L-per-weighted-capital is uniform across depositors",
                    (per_unit.max() - per_unit.min()) < 1e-4))

    # 9. Structural: no orphaned foreign keys.
    checks.append(("ventures.provider_id has zero orphans",
                    ventures["provider_id"].isin(tables["capital_providers"]["provider_id"]).all()))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)
    return all_ok


if __name__ == "__main__":
    tables = build(n_ventures=1500, seed=RNG_SEED)
    ventures = tables["mudarabah_ventures"]
    n_loss = (ventures["venture_pnl"] < 0).sum()
    n_negligent = ventures["negligent"].sum()
    print(f"providers: {len(tables['capital_providers'])}  ventures: {len(ventures)}  "
          f"(loss-making: {n_loss}, negligent: {n_negligent})")
    print(f"total capital: {ventures['capital_contributed'].sum():,.0f}   "
          f"total mudarib P&L: {ventures['mudarib_pnl'].sum():,.0f}   "
          f"total rabb_al_mal P&L: {ventures['rabb_al_mal_pnl'].sum():,.0f}")
    print()
    ok = verify(tables)
    print()

    report = misata.coherence_audit(tables)
    print(f"Coherence audit: score={report.score:.1f}  clean={report.clean}")
    if not report.clean:
        print(report.summary())
        ok = False

    print()
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    raise SystemExit(0 if ok else 1)
