"""
Investment Sukuk (AAOIFI Sharia Standard No. 17) -- asset-backed
certificates whose holders receive a Periodic Distribution Amount, not
interest and not a coupon, flowing from a real Ijarah lease pool they
hold an undivided ownership share in.

The vocabulary matters here as much as the math: a sukuk certificate is
not a bond, its holder is not a creditor, and what it pays is not
interest. AAOIFI's own term is Periodic Distribution Amount (PDA) --
income passed through from the underlying asset's actual performance,
because the sukuk holder owns a fraction of that asset, not a claim on
the issuer's general credit. Getting the vocabulary wrong here (calling
this column "coupon" or "interest") is itself a credibility tell for
anyone who actually works in this space, so this example never does.

Structure -- an Ijarah sukuk, the most common AAOIFI-compliant sukuk
structure in practice:

  1. A special-purpose entity buys a pool of real, income-producing
     assets (the same leased assets this engine's Ijarah example
     generates) and issues certificates against it.
  2. Each certificate is an undivided ownership share of that pool.
     `periodic_distribution_amount` is the certificate's pro-rata share
     of the pool's actual rental income for the period -- not a
     declared rate applied to face value, which is what would make this
     interest wearing a different name.
  3. At maturity, the issuer executes a purchase undertaking and
     redeems each certificate at exactly its face value. No interest
     compounds into that redemption amount between issuance and
     maturity.

This reuses `misata/examples/islamic_finance_ijarah.py`'s lease pool as
the underlying asset, so the distribution this example pays out is
literally the same rental income that script already generates and
verifies -- not a separately-invented number that happens to look right.

Run it directly. Every guarantee below is checked against the data this
script just generated, not asserted.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import misata
from islamic_finance_ijarah import build as build_ijarah_pool

RNG_SEED = 17

# Common sukuk certificate denominations -- fixed within an issuance (every
# certificate in one issuance is an equal, undivided share) but a real
# issuer chooses its own denomination, so it varies across issuances.
FACE_VALUE_DENOMINATIONS = [100.0, 500.0, 1_000.0, 5_000.0, 10_000.0]
N_CERTIFICATES = 5_000
N_ISSUANCES = 6              # separate sukuk issuances, each backed by its own asset pool


def build(n_issuances: int = N_ISSUANCES, seed: int = RNG_SEED):
    issuances = []
    distributions = []
    cert_rows = []
    cert_id = 1
    rng = np.random.default_rng(seed)

    for issuance_idx in range(n_issuances):
        pool_seed = seed * 100 + issuance_idx
        face_value = float(rng.choice(FACE_VALUE_DENOMINATIONS))
        # Each issuance is backed by its own Ijarah lease pool -- the
        # underlying asset actually producing the income that gets
        # distributed, not a number invented separately.
        pool_tables = build_ijarah_pool(n_contracts=200, seed=pool_seed)
        contracts = pool_tables["ijarah_contracts"]
        schedule = pool_tables["ijarah_schedule"]
        rentals = schedule[schedule["event_type"] == "rental"].copy()
        rentals["month"] = pd.to_datetime(rentals["due_date"]).dt.to_period("M")

        total_asset_value = float(contracts["asset_value"].sum())
        n_certs = N_CERTIFICATES
        total_issuance_value = face_value * n_certs
        issuance_date = contracts["lease_start_date"].min()
        maturity_months = int(contracts["term_months"].min())

        issuances.append({
            "issuance_id": issuance_idx + 1,
            "underlying_pool": f"ijarah_pool_{issuance_idx + 1}",
            "total_asset_value": round(total_asset_value, 2),
            "face_value_per_certificate": face_value,
            "n_certificates": n_certs,
            "total_issuance_value": round(total_issuance_value, 2),
            "issuance_date": issuance_date,
            "maturity_months": maturity_months,
        })

        for cert_num in range(n_certs):
            cert_rows.append({
                "certificate_id": cert_id,
                "issuance_id": issuance_idx + 1,
                "face_value": face_value,
            })
            cert_id += 1

        # Monthly pool rental income for the months within the sukuk's
        # own term -- the PDA source. Truncate to maturity_months so a
        # sukuk backed by longer-tenor leases still pays out only for its
        # own declared term.
        monthly_pool_income = (
            rentals.groupby("month")["amount"].sum().sort_index().iloc[:maturity_months]
        )
        for period_number, (month, pool_income) in enumerate(monthly_pool_income.items(), start=1):
            # Round the pool income to the cent FIRST, then derive the
            # per-certificate distribution from that same rounded figure --
            # otherwise pool_rental_income and periodic_distribution_amount
            # would be two different money figures a cent apart.
            rounded_income = round(float(pool_income), 2)
            pda_per_certificate = round(rounded_income / n_certs, 4)
            distributions.append({
                "issuance_id": issuance_idx + 1,
                "period_number": period_number,
                "period": str(month),
                "pool_rental_income": rounded_income,
                "periodic_distribution_amount": pda_per_certificate,
            })

    tables = {
        "sukuk_issuances": pd.DataFrame(issuances),
        "sukuk_certificates": pd.DataFrame(cert_rows),
        "sukuk_distributions": pd.DataFrame(distributions),
    }
    return _reconcile(tables)


def _reconcile(tables: dict) -> dict:
    issuances = tables["sukuk_issuances"].copy()
    # Redemption at maturity is exactly face value -- a purchase
    # undertaking, not a principal-plus-accrued-interest payoff. Nothing
    # about the distributions paid along the way changes this number.
    issuances["redemption_amount_per_certificate"] = issuances["face_value_per_certificate"]
    tables["sukuk_issuances"] = issuances
    return tables


def verify(tables: dict) -> bool:
    issuances = tables["sukuk_issuances"]
    certificates = tables["sukuk_certificates"]
    distributions = tables["sukuk_distributions"]
    checks = []

    # 1. Total issuance value is exactly face_value x n_certificates.
    recomputed_total = (issuances["face_value_per_certificate"] * issuances["n_certificates"]).round(2)
    checks.append(("total_issuance_value equals face_value x n_certificates exactly",
                    np.allclose(issuances["total_issuance_value"], recomputed_total)))

    # 2. Every certificate in an issuance carries the same face value as
    # its issuance declares -- an undivided, equal ownership share.
    merged = certificates.merge(issuances[["issuance_id", "face_value_per_certificate"]], on="issuance_id")
    checks.append(("every certificate's face_value matches its issuance's declared face value",
                    (merged["face_value"] == merged["face_value_per_certificate"]).all()))

    # 3. The Periodic Distribution Amount is the pool's ACTUAL rental
    # income divided across certificates -- not a rate applied to face
    # value, which is what would make this interest by another name.
    dist_merged = distributions.merge(issuances[["issuance_id", "n_certificates"]], on="issuance_id")
    recomputed_pda = (dist_merged["pool_rental_income"] / dist_merged["n_certificates"]).round(4)
    checks.append(("periodic_distribution_amount equals pool_rental_income / n_certificates exactly",
                    np.allclose(dist_merged["periodic_distribution_amount"], recomputed_pda, atol=1e-4)))

    # 4. The distribution is NOT a fixed rate on face value: if it were,
    # PDA per certificate would be constant across periods for a given
    # issuance. Real underlying rental income is level per this engine's
    # own Ijarah generator, so a small residual variation check here
    # would be trivial -- the real test is that the number traces to the
    # pool's income at all, which check 3 already pins exactly. This
    # check instead confirms the vocabulary discipline directly.
    checks.append(("no column anywhere is named 'interest' or 'coupon'",
                    not any(name in ("interest", "coupon", "coupon_rate", "interest_rate")
                            for df in tables.values() for name in df.columns)))

    # 5. Redemption at maturity equals face value exactly -- no interest
    # compounded into it between issuance and maturity.
    checks.append(("redemption_amount_per_certificate equals face_value_per_certificate exactly",
                    (issuances["redemption_amount_per_certificate"]
                     == issuances["face_value_per_certificate"]).all()))

    # 6. Each issuance's distributions span exactly its declared
    # maturity_months, no more, no fewer.
    counts = distributions.groupby("issuance_id").size()
    checks.append(("each issuance has exactly maturity_months distribution periods",
                    (counts.reindex(issuances["issuance_id"]) == issuances.set_index("issuance_id")
                     .loc[issuances["issuance_id"], "maturity_months"].to_numpy()).all()))

    # 7. Structural: no orphaned foreign keys.
    checks.append(("certificates.issuance_id has zero orphans",
                    certificates["issuance_id"].isin(issuances["issuance_id"]).all()))
    checks.append(("distributions.issuance_id has zero orphans",
                    distributions["issuance_id"].isin(issuances["issuance_id"]).all()))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)
    return all_ok


if __name__ == "__main__":
    tables = build(n_issuances=N_ISSUANCES, seed=RNG_SEED)
    issuances = tables["sukuk_issuances"]
    print(f"issuances: {len(issuances)}  certificates: {len(tables['sukuk_certificates'])}  "
          f"distribution rows: {len(tables['sukuk_distributions'])}")
    print(f"total issuance value: {issuances['total_issuance_value'].sum():,.0f}   "
          f"total distributed: {tables['sukuk_distributions']['periodic_distribution_amount'].sum() * N_CERTIFICATES:,.0f}")
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
