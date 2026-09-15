"""
Ijarah and Ijarah Muntahia Bittamleek (IMB) under AAOIFI Sharia Standard
No. 9 -- a lease, and a lease ending in ownership.

An Ijarah rental is payment for the USE of an asset the lessor still owns,
not repayment of the asset's cost. That's the property this example
checks, because it's the one a loan-shaped schema would get wrong by
default: a loan's payment retires a principal balance, so the lender's
claim on the asset shrinks as payments are made. A lease's payment does
no such thing -- the lessor's ownership of the asset is untouched by how
many rentals have been paid, right up until the day (if ever) it's
actually transferred.

Two structures, one schedule shape:

  * Plain Ijarah -- rent for the term, hand the asset back. No transfer.
  * Ijarah Muntahia Bittamleek -- the same rental schedule, plus a separate,
    small, PRE-AGREED ownership_transfer_price paid once at the end. That
    price is fixed at signing, the same way Murabahah's profit_margin is:
    it does not grow with the rental total or shrink with periods paid,
    because it was never a stand-in for an outstanding loan balance.

Run it directly. Every guarantee below is checked against the data this
script just generated, not asserted.
"""

import numpy as np
import pandas as pd

import misata

RNG_SEED = 9

ASSET_TYPES = ["Aircraft", "Vessel", "Real Estate", "Heavy Equipment", "Fleet Vehicle"]
ASSET_WEIGHTS = [0.10, 0.08, 0.42, 0.25, 0.15]

TERM_MONTHS = [24, 36, 48, 60, 84]
TERM_WEIGHTS = [0.10, 0.25, 0.30, 0.25, 0.10]

# Roughly 60% of Ijarah contracts in practice are Ijarah Muntahia Bittamleek
# (lease-to-own), the dominant Islamic-finance vehicle for asset and
# equipment finance -- declared as a realistic split, not an AAOIFI figure.
LEASE_TYPES = ["ijarah", "ijarah_muntahia_bittamleek"]
LEASE_TYPE_WEIGHTS = [0.40, 0.60]

# Annualized rental yield on asset value, the lessor's return for
# providing use of the asset. A commercial pricing decision, not an
# AAOIFI-published number -- declared here the same way the Murabahah
# example declares its margin-rate band.
RENTAL_YIELD_MEAN = 0.09
RENTAL_YIELD_STD = 0.02
RENTAL_YIELD_MIN = 0.04
RENTAL_YIELD_MAX = 0.18

# The IMB transfer price is nominal by design -- AAOIFI Standard 9 requires
# it be a token amount, not a disguised final installment of the asset's
# cost, or the lease would just be a Murabahah wearing a lease's clothes.
TRANSFER_PRICE_FRACTION = 0.01


def build(n_contracts: int = 1500, seed: int = RNG_SEED):
    schema = {
        "lessees": {
            "__rows__": int(n_contracts * 0.7),
            "lessee_id": {"type": "integer", "primary_key": True},
            "name": {"type": "string", "text_type": "person_name"},
        },
        "ijarah_contracts": {
            "__rows__": n_contracts,
            "contract_id": {"type": "integer", "primary_key": True},
            "lessee_id": {"type": "integer",
                           "foreign_key": {"table": "lessees", "column": "lessee_id"}},
            "asset_type": {"type": "string", "enum": ASSET_TYPES, "weights": ASSET_WEIGHTS},
            "lease_type": {"type": "string", "enum": LEASE_TYPES, "weights": LEASE_TYPE_WEIGHTS},
            "term_months": {"type": "integer", "enum": TERM_MONTHS, "weights": TERM_WEIGHTS},
            "asset_value": {"type": "float", "min": 50_000, "max": 5_000_000,
                             "distribution": "lognormal", "mu": 12.0, "sigma": 1.0,
                             "decimals": 2},
            "lease_start_date": {"type": "date", "min_date": "2022-01-01", "max_date": "2025-12-01"},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))
    return _reconcile(tables, seed)


def _reconcile(tables: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed + 1)

    contracts = tables["ijarah_contracts"].copy()
    contracts["term_months"] = contracts["term_months"].astype(int)
    is_imb = contracts["lease_type"] == "ijarah_muntahia_bittamleek"

    # The rental yield is set once, on the asset value, at signing -- it is
    # never recomputed against a shrinking "balance", because a lease has
    # no balance to shrink.
    rental_yield = np.clip(
        rng.normal(RENTAL_YIELD_MEAN, RENTAL_YIELD_STD, len(contracts)),
        RENTAL_YIELD_MIN, RENTAL_YIELD_MAX,
    )
    contracts["rental_yield"] = rental_yield.round(4)
    annual_rental = (contracts["asset_value"] * contracts["rental_yield"]).round(2)
    contracts["monthly_rental"] = (annual_rental / 12).round(2)
    contracts["total_rental"] = (contracts["monthly_rental"] * contracts["term_months"]).round(2)

    # A nominal, pre-agreed transfer price for IMB contracts -- fixed on
    # asset_value alone, independent of the rental schedule or term.
    contracts["ownership_transfer_price"] = np.where(
        is_imb, (contracts["asset_value"] * TRANSFER_PRICE_FRACTION).round(2), 0.0,
    )

    tables["ijarah_contracts"] = contracts
    tables["ijarah_schedule"] = _build_schedule(contracts)
    return tables


def _build_schedule(contracts: pd.DataFrame) -> pd.DataFrame:
    """One row per contract per rental period, plus a final ownership-
    transfer row for IMB contracts. Rentals are level -- there is no
    amortizing split to make them anything else."""
    rows = []
    row_id = 1
    for contract in contracts.itertuples(index=False):
        n = contract.term_months
        due_dates = pd.date_range(contract.lease_start_date, periods=n, freq="MS") + pd.DateOffset(days=1)
        for i in range(n):
            rows.append({
                "schedule_id": row_id,
                "contract_id": contract.contract_id,
                "period_number": i + 1,
                "due_date": due_dates[i],
                "event_type": "rental",
                "amount": contract.monthly_rental,
                # The asset stays the lessor's throughout the rental
                # period, regardless of how many rentals have been paid --
                # a lease has no principal balance to retire.
                "asset_owner": "lessor",
            })
            row_id += 1
        if contract.lease_type == "ijarah_muntahia_bittamleek":
            transfer_date = due_dates[-1]
            rows.append({
                "schedule_id": row_id,
                "contract_id": contract.contract_id,
                "period_number": n + 1,
                "due_date": transfer_date,
                "event_type": "ownership_transfer",
                "amount": contract.ownership_transfer_price,
                "asset_owner": "lessee",
            })
            row_id += 1
    return pd.DataFrame(rows)


def verify(tables: dict) -> bool:
    contracts = tables["ijarah_contracts"]
    schedule = tables["ijarah_schedule"]
    checks = []

    rentals = schedule[schedule["event_type"] == "rental"]
    transfers = schedule[schedule["event_type"] == "ownership_transfer"]

    # 1. Total rental collected equals monthly_rental x term_months exactly
    # -- the amount is fixed at signing and does not drift with time.
    totals = rentals.groupby("contract_id")["amount"].sum().round(2)
    declared = contracts.set_index("contract_id")["total_rental"]
    checks.append(("sum of rentals equals total_rental exactly, every contract",
                    np.allclose(totals.reindex(declared.index), declared)))

    # 2. Every rental on a contract is the same amount -- level rent, not
    # an amortization schedule with a shrinking balance.
    def _equal_within_a_cent(g):
        return len(g) <= 1 or (g.iloc[:-1] - g.iloc[0]).abs().max() < 0.005
    equal_ok = rentals.groupby("contract_id")["amount"].apply(_equal_within_a_cent)
    checks.append(("every rental on a contract is the same amount (level rent)",
                    bool(equal_ok.all())))

    # 3. The lessor owns the asset for every rental period on every
    # contract -- ownership never partially transfers as rentals accrue.
    checks.append(("asset_owner is 'lessor' for every rental row",
                    (rentals["asset_owner"] == "lessor").all()))

    # 4. IMB contracts get exactly one ownership_transfer row, priced from
    # asset_value alone, not from the rental total or term.
    imb_ids = set(contracts.loc[contracts["lease_type"] == "ijarah_muntahia_bittamleek", "contract_id"])
    checks.append(("every IMB contract has exactly one ownership_transfer row",
                    set(transfers["contract_id"]) == imb_ids and
                    transfers["contract_id"].value_counts().eq(1).all()))
    recomputed_transfer = (contracts.loc[contracts["contract_id"].isin(imb_ids), "asset_value"]
                            * TRANSFER_PRICE_FRACTION).round(2)
    actual_transfer = contracts.loc[contracts["contract_id"].isin(imb_ids), "ownership_transfer_price"]
    checks.append(("IMB transfer price equals asset_value x the nominal fraction exactly",
                    np.allclose(actual_transfer.to_numpy(), recomputed_transfer.to_numpy())))

    # 5. Plain Ijarah contracts never transfer ownership and carry no
    # transfer price.
    plain_ids = set(contracts.loc[contracts["lease_type"] == "ijarah", "contract_id"])
    checks.append(("plain Ijarah contracts have zero ownership_transfer rows",
                    transfers["contract_id"].isin(plain_ids).sum() == 0))
    checks.append(("plain Ijarah contracts carry zero transfer price",
                    (contracts.loc[contracts["contract_id"].isin(plain_ids),
                                    "ownership_transfer_price"] == 0).all()))

    # 6. The IMB transfer price does not scale with the rental total or
    # term -- it is nominal, not a disguised balloon principal payment.
    imb = contracts[contracts["contract_id"].isin(imb_ids)]
    if len(imb) > 5:
        corr = np.corrcoef(imb["total_rental"], imb["ownership_transfer_price"] / imb["asset_value"])[0, 1]
        checks.append(("transfer price as a fraction of asset_value is independent of total_rental",
                        abs(corr) < 0.3))

    # 7. No column anywhere encodes an interest-rate-on-balance term.
    forbidden = {"interest_rate", "apr", "outstanding_principal", "outstanding_balance"}
    checks.append(("no column encodes an interest rate or an outstanding balance",
                    forbidden.isdisjoint(contracts.columns) and forbidden.isdisjoint(schedule.columns)))

    # 8. Structural: no orphaned foreign keys.
    checks.append(("contracts.lessee_id has zero orphans",
                    contracts["lessee_id"].isin(tables["lessees"]["lessee_id"]).all()))
    checks.append(("schedule.contract_id has zero orphans",
                    schedule["contract_id"].isin(contracts["contract_id"]).all()))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)
    return all_ok


if __name__ == "__main__":
    tables = build(n_contracts=1500, seed=RNG_SEED)
    contracts = tables["ijarah_contracts"]
    n_imb = (contracts["lease_type"] == "ijarah_muntahia_bittamleek").sum()
    print(f"lessees: {len(tables['lessees'])}  contracts: {len(contracts)}  "
          f"(IMB: {n_imb})  schedule rows: {len(tables['ijarah_schedule'])}")
    print(f"total asset value: {contracts['asset_value'].sum():,.0f}   "
          f"total rental collected: {contracts['total_rental'].sum():,.0f}")
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
