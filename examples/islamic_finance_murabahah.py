"""
Murabahah — a cost-plus sale under AAOIFI Sharia Standard No. 8, with the
one property that actually distinguishes it from a conventional loan
checked independently: the total a customer repays is fixed the day the
contract is signed and never changes with time, because there is no
interest accruing on an outstanding balance.

AAOIFI Standard 8 requires two things to be disclosed at contract signing:
the seller's cost price and the profit margin added on top of it. The
selling price is the sum of the two, nothing else enters it:

    selling_price = cost_price + profit_margin

That sale is then repaid over an agreed tenor in EQUAL installments. This
is the part a symmetric-looking conventional amortization schedule gets
wrong for Murabahah data: a mortgage-style schedule splits each payment
into shrinking interest plus growing principal, so early installments and
late installments differ. Murabahah has no such split — the installment
amount is selling_price / tenor, identical on every due date, because
there is nothing left to compute once the price is fixed. A dataset that
quietly re-derives installment_amount as rate x outstanding_balance would
be reintroducing riba (interest) into data that is supposed to model its
absence, which is the actual audit a Sharia-literate reviewer would run
on this.

Run it directly. Every guarantee below is checked against the data this
script just generated, not asserted.
"""

import numpy as np
import pandas as pd

import misata

RNG_SEED = 8

ASSET_TYPES = ["Vehicle", "Real Estate", "Equipment", "Commodity", "Consumer Goods"]
ASSET_WEIGHTS = [0.35, 0.30, 0.15, 0.12, 0.08]

TENOR_MONTHS = [12, 24, 36, 48, 60]
TENOR_WEIGHTS = [0.15, 0.30, 0.25, 0.20, 0.10]

# Flat profit margin as a fraction of cost, fixed once at signing and
# independent of tenor. Not an AAOIFI-published number — margin-setting is
# each bank's own commercial decision — declared here as a realistic market
# range the way the credit-risk example declares its rating-mix weights,
# not independently cited the way the AAOIFI cost-plus formula itself is.
MARGIN_RATE_MEAN = 0.055
MARGIN_RATE_STD = 0.015
MARGIN_RATE_MIN = 0.02
MARGIN_RATE_MAX = 0.12


def build(n_contracts: int = 2000, seed: int = RNG_SEED):
    schema = {
        "customers": {
            "__rows__": int(n_contracts * 0.7),
            "customer_id": {"type": "integer", "primary_key": True},
            "name": {"type": "string", "text_type": "person_name"},
        },
        "murabahah_contracts": {
            "__rows__": n_contracts,
            "contract_id": {"type": "integer", "primary_key": True},
            "customer_id": {"type": "integer",
                             "foreign_key": {"table": "customers", "column": "customer_id"}},
            "asset_type": {"type": "string", "enum": ASSET_TYPES, "weights": ASSET_WEIGHTS},
            "tenor_months": {"type": "integer", "enum": TENOR_MONTHS, "weights": TENOR_WEIGHTS},
            "cost_price": {"type": "float", "min": 8_000, "max": 2_000_000,
                            "distribution": "lognormal", "mu": 10.8, "sigma": 1.0,
                            "decimals": 2},
            "contract_date": {"type": "date", "min_date": "2022-01-01", "max_date": "2025-12-01"},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))
    return _reconcile(tables, seed)


def _reconcile(tables: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed + 1)

    contracts = tables["murabahah_contracts"].copy()
    contracts["tenor_months"] = contracts["tenor_months"].astype(int)

    # The margin rate is disclosed and fixed at signing, not derived from
    # tenor or from any later recomputation of an outstanding balance.
    margin_rate = np.clip(
        rng.normal(MARGIN_RATE_MEAN, MARGIN_RATE_STD, len(contracts)),
        MARGIN_RATE_MIN, MARGIN_RATE_MAX,
    )
    contracts["margin_rate"] = margin_rate.round(4)
    contracts["profit_margin"] = (contracts["cost_price"] * contracts["margin_rate"]).round(2)

    # AAOIFI Standard 8: selling_price = cost_price + profit_margin. No
    # other term enters this — no rate applied to time, no compounding.
    contracts["selling_price"] = (contracts["cost_price"] + contracts["profit_margin"]).round(2)

    tables["murabahah_contracts"] = contracts
    tables["murabahah_installments"] = _build_installments(contracts)
    return tables


def _build_installments(contracts: pd.DataFrame) -> pd.DataFrame:
    """Equal installments summing exactly to selling_price, one row per
    contract per due month. Equal, not amortizing, is the point: a real
    Murabahah repayment schedule has nothing left to split into interest
    and principal once the price is fixed at signing."""
    rows = []
    installment_id = 1
    for contract in contracts.itertuples(index=False):
        n = contract.tenor_months
        base = round(contract.selling_price / n, 2)
        # Equal installments to the cent, with any rounding residual
        # absorbed by the final installment so the sum is exact — the same
        # residual-absorption convention this engine's balanced_ledger
        # constraint uses for double-entry lines.
        amounts = np.full(n, base)
        amounts[-1] = round(contract.selling_price - base * (n - 1), 2)
        due_dates = pd.date_range(contract.contract_date, periods=n, freq="MS") + pd.DateOffset(days=1)
        for i in range(n):
            rows.append({
                "installment_id": installment_id,
                "contract_id": contract.contract_id,
                "installment_number": i + 1,
                "due_date": due_dates[i],
                "installment_amount": amounts[i],
            })
            installment_id += 1
    return pd.DataFrame(rows)


def verify(tables: dict) -> bool:
    contracts = tables["murabahah_contracts"]
    installments = tables["murabahah_installments"]
    checks = []

    # 1. The AAOIFI Standard 8 cost-plus formula, recomputed independently.
    recomputed_price = (contracts["cost_price"] + contracts["profit_margin"]).round(2)
    checks.append(("selling_price equals cost_price + profit_margin exactly, every contract",
                    np.allclose(contracts["selling_price"], recomputed_price)))

    # 2. profit_margin traces to a disclosed rate on cost_price, not a
    # value fitted after the fact.
    recomputed_margin = (contracts["cost_price"] * contracts["margin_rate"]).round(2)
    checks.append(("profit_margin equals cost_price x margin_rate exactly, every contract",
                    np.allclose(contracts["profit_margin"], recomputed_margin)))

    # 3. Every disclosed margin rate falls in the declared realistic band.
    checks.append(("margin_rate stays within [2%, 12%] on every contract",
                    contracts["margin_rate"].between(MARGIN_RATE_MIN, MARGIN_RATE_MAX).all()))

    # 4. The zero-riba claim: total repaid across the life of a contract
    # equals the selling price fixed at signing, to the cent. If interest
    # were accruing on an outstanding balance this would drift with tenor.
    totals = installments.groupby("contract_id")["installment_amount"].sum().round(2)
    priced = contracts.set_index("contract_id")["selling_price"]
    checks.append(("sum of installments equals selling_price exactly, every contract",
                    np.allclose(totals.reindex(priced.index), priced)))

    # 5. Equal installments: the hallmark that separates a fixed Murabahah
    # repayment from a conventional amortizing loan, where interest
    # shrinks and principal grows across the schedule so payments split
    # differently even when the total payment is level. Here there is no
    # split to begin with, so every installment on a contract is the same
    # amount (up to the one-cent rounding residual absorbed by the last).
    def _equal_within_a_cent(g):
        return bool((g.iloc[:-1] - g.iloc[0]).abs().max() < 0.005 if len(g) > 1 else True)
    equal_ok = installments.groupby("contract_id")["installment_amount"].apply(_equal_within_a_cent).all()
    checks.append(("every installment on a contract is the same amount (equal, not amortizing)",
                    bool(equal_ok)))

    # 6. Within each contract's own schedule, installment_amount shows no
    # trend against installment_number. Fit per contract (not pooled
    # across contracts, which differ wildly in scale) so a reducing-balance
    # amortization's declining-then-flat interest component, which would
    # show up as a real per-contract slope, has somewhere to hide if it
    # were there.
    def _per_contract_slope(g):
        if len(g) < 3:
            return 0.0
        normalized = g["installment_amount"].to_numpy() / g["installment_amount"].iloc[0]
        return np.polyfit(g["installment_number"].to_numpy(), normalized, 1)[0]

    slopes = installments.groupby("contract_id").apply(_per_contract_slope, include_groups=False)
    checks.append(("no per-contract drift in installment_amount by position (|slope| < 0.001)",
                    bool((slopes.abs() < 0.001).all())))

    # 7. Exactly tenor_months installment rows per contract, no fewer, no more.
    counts = installments.groupby("contract_id").size()
    checks.append(("installment count matches tenor_months exactly, every contract",
                    (counts.reindex(priced.index) == contracts.set_index("contract_id")["tenor_months"]).all()))

    # 8. Structural: no orphaned foreign keys anywhere in the chain.
    checks.append(("contracts.customer_id has zero orphans",
                    contracts["customer_id"].isin(tables["customers"]["customer_id"]).all()))
    checks.append(("installments.contract_id has zero orphans",
                    installments["contract_id"].isin(contracts["contract_id"]).all()))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)
    return all_ok


if __name__ == "__main__":
    tables = build(n_contracts=2000, seed=RNG_SEED)
    contracts = tables["murabahah_contracts"]
    print(f"customers: {len(tables['customers'])}  contracts: {len(contracts)}  "
          f"installments: {len(tables['murabahah_installments'])}")
    print(f"portfolio cost: {contracts['cost_price'].sum():,.0f}   "
          f"portfolio selling price: {contracts['selling_price'].sum():,.0f}   "
          f"total disclosed profit: {contracts['profit_margin'].sum():,.0f}")
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
