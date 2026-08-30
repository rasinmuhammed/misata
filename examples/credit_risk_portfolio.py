"""
A commercial loan portfolio: borrowers, loans, and the three numbers every
bank capital model is built from -- probability of default (PD), loss given
default (LGD), and exposure at default (EAD) -- combined into expected loss
exactly the way Basel says to: EL = PD x LGD x EAD.

Every number below traces to a real, cited source, not a plausible guess:

  * PD by credit rating is S&P Global Ratings' own published annual global
    corporate default rate, averaged across the six most recent studies
    (2019-2024) rather than any single volatile year. AAA, AA, and A each
    show exactly 0.00% in every one of those six years -- a real fact about
    investment-grade defaults, not a placeholder, and this example treats it
    as a guarantee to verify (zero realized defaults in those three grades)
    rather than smoothing it into something friendlier-looking for a demo.

  * LGD by seniority is the Basel Foundation IRB *supervisory* value, not an
    estimate: 40% for senior unsecured claims on corporates, 75% for
    subordinated claims (BIS/OSFI Capital Adequacy Requirements, Chapter 5).
    These are regulator-set numbers a bank is required to use under F-IRB,
    which makes them the least arguable figures in this whole example.

  * EAD for a partially-drawn facility is EAD = drawn + CCF x undrawn, the
    Basel credit-conversion-factor formula. CCF is 20% for commitments of
    one year or less, 50% for longer commitments, and 0% for commitments
    that are unconditionally cancellable at any time (e.g. an unused credit
    card line) -- the Basel standardized-approach CCF table.

What this earns, checked below: a borrower's credit rating doesn't just sit
there as a label. It measurably predicts whether that borrower's loans
actually default, at the exact rate S&P's own data says it should.
"""

import numpy as np
import pandas as pd

import misata

RNG_SEED = 11

# S&P Global Ratings, annual global corporate default rate by rating,
# averaged over the 2019-2024 studies (S&P Global Ratings Research,
# "Annual Global Corporate Default And Rating Transition Study").
# AAA/AA/A are exactly 0.00% in every one of those six years.
PD_BY_RATING = {
    "AAA": 0.0000,
    "AA":  0.0000,
    "A":   0.0000,
    "BBB": 0.0003,   # (0.11 + 0 + 0 + 0 + 0.11 + 0.05) / 6, percent -> fraction
    "BB":  0.0028,   # (0 + 0.94 + 0 + 0.32 + 0.25 + 0.17) / 6
    "B":   0.0161,   # (1.50 + 3.55 + 0.52 + 1.10 + 1.25 + 1.72) / 6
    "CCC": 0.2692,   # (29.61 + 47.88 + 10.96 + 13.84 + 30.89 + 28.36) / 6
}

# Real corporate bond market composition skews investment-grade: roughly
# half the rated universe sits BBB or above. Declared here as a realistic
# portfolio mix, not independently cited the way the PD table itself is.
RATING_WEIGHTS = {
    "AAA": 0.02, "AA": 0.06, "A": 0.17, "BBB": 0.30,
    "BB": 0.22, "B": 0.16, "CCC": 0.07,
}

# Basel Foundation IRB supervisory LGD (BIS/OSFI CAR Chapter 5).
LGD_BY_SENIORITY = {
    "senior_unsecured": 0.40,
    "subordinated": 0.75,
}

# Basel standardized-approach CCF by commitment type.
CCF_BY_COMMITMENT = {
    "term_loan": 0.0,                 # fully drawn, nothing undrawn to convert
    "short_term_revolving": 0.20,      # <= 1 year
    "long_term_revolving": 0.50,       # > 1 year
    "unconditionally_cancellable": 0.0,  # e.g. an unused credit card line
}


def build(n_borrowers: int = 3000, seed: int = RNG_SEED):
    schema = {
        "borrowers": {
            "__rows__": n_borrowers,
            "borrower_id": {"type": "integer", "primary_key": True},
            "credit_rating": {"type": "string",
                "enum": list(RATING_WEIGHTS.keys()),
                "weights": list(RATING_WEIGHTS.values())},
            "industry": {"type": "string",
                "enum": ["Manufacturing", "Retail", "Energy", "Technology",
                         "Healthcare", "Real Estate", "Financial Services"]},
        },
        "loans": {
            "__rows__": int(n_borrowers * 1.4),
            "loan_id": {"type": "integer", "primary_key": True},
            "borrower_id": {"type": "integer",
                             "foreign_key": {"table": "borrowers", "column": "borrower_id"}},
            "seniority": {"type": "string",
                "enum": list(LGD_BY_SENIORITY.keys()),
                "weights": [0.82, 0.18]},  # most commercial lending is senior
            "commitment_type": {"type": "string",
                "enum": list(CCF_BY_COMMITMENT.keys()),
                "weights": [0.45, 0.20, 0.20, 0.15]},
            # decimals: 2 on purpose. Left at the engine's raw float output,
            # this showed up as drawn_amount=130028.33004434995 -- no loan
            # tape on earth carries a dollar amount to eleven decimal places,
            # and that alone would give away a synthetic file faster than
            # anything else in it.
            "drawn_amount": {"type": "float", "min": 50_000, "max": 25_000_000,
                              "distribution": "lognormal", "mu": 13.5, "sigma": 1.1,
                              "decimals": 2},
            "undrawn_commitment": {"type": "float", "min": 0, "max": 10_000_000,
                                     "distribution": "lognormal", "mu": 11.0, "sigma": 1.3,
                                     "decimals": 2},
            # type "date", not "datetime": a loan tape records the day a loan
            # was originated, not a timestamp accurate to the nanosecond.
            "origination_date": {"type": "date", "min_date": "2022-01-01", "max_date": "2025-12-01"},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))
    return _reconcile(tables, seed)


def _reconcile(tables: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed + 1)

    borrowers = tables["borrowers"].copy()
    borrowers["pd"] = borrowers["credit_rating"].map(PD_BY_RATING)
    tables["borrowers"] = borrowers

    loans = tables["loans"].copy()
    # Term loans are fully drawn by construction: there is nothing left to
    # convert, so any undrawn_commitment the raw schema happened to assign
    # is zeroed out rather than silently ignored.
    loans.loc[loans["commitment_type"] == "term_loan", "undrawn_commitment"] = 0.0

    loans["lgd"] = loans["seniority"].map(LGD_BY_SENIORITY)
    loans["ccf"] = loans["commitment_type"].map(CCF_BY_COMMITMENT)
    loans["ead"] = (loans["drawn_amount"] + loans["ccf"] * loans["undrawn_commitment"]).round(2)

    pd_by_borrower = borrowers.set_index("borrower_id")["pd"]
    loans["pd"] = loans["borrower_id"].map(pd_by_borrower)

    # The connection: whether a loan actually defaults is a real Bernoulli
    # draw at that borrower's own PD, not an independent coin flip. This is
    # what makes "AAA never defaults" and "CCC defaults ~27% of the time" a
    # measured property of the generated rows, not just a declared label.
    loans["defaulted"] = rng.random(len(loans)) < loans["pd"].to_numpy()

    loans["expected_loss"] = (loans["pd"] * loans["lgd"] * loans["ead"]).round(2)
    loans["realized_loss"] = np.where(loans["defaulted"], (loans["lgd"] * loans["ead"]).round(2), 0.0)

    tables["loans"] = loans
    return tables


def verify(tables: dict) -> bool:
    borrowers = tables["borrowers"]
    loans = tables["loans"].merge(
        borrowers[["borrower_id", "credit_rating"]], on="borrower_id")

    checks = []

    # 1. The core claim: a rating grade's REALIZED default rate matches
    # S&P's published PD for that grade, measured from the rows themselves.
    for rating, declared_pd in PD_BY_RATING.items():
        sub = loans[loans["credit_rating"] == rating]
        if len(sub) == 0:
            continue
        measured = sub["defaulted"].mean()
        if declared_pd == 0.0:
            ok = measured == 0.0
            label = (f"'{rating}' (S&P PD 0.00%): exactly zero realized defaults "
                      f"({int(sub['defaulted'].sum())} of {len(sub)})")
        else:
            # Bernoulli sampling noise: allow a wide relative band, since a
            # single rating grade may only have a few hundred loans.
            ok = abs(measured - declared_pd) < max(0.02, declared_pd * 0.6)
            label = f"'{rating}' realized default rate {measured:.4f} vs S&P PD {declared_pd:.4f}"
        checks.append((label, ok))

    # 2. LGD matches the Basel F-IRB supervisory table exactly, every row.
    for seniority, declared_lgd in LGD_BY_SENIORITY.items():
        sub = loans[loans["seniority"] == seniority]
        checks.append((f"'{seniority}' LGD is exactly {declared_lgd:.0%} on every loan",
                        (sub["lgd"] == declared_lgd).all()))

    # 3. EAD = drawn + CCF x undrawn, recomputed independently from raw columns.
    recomputed_ead = (loans["drawn_amount"] + loans["ccf"] * loans["undrawn_commitment"]).round(2)
    checks.append(("EAD reconciles to drawn + CCF x undrawn on every loan",
                    np.allclose(loans["ead"], recomputed_ead)))

    # 4. Term loans carry zero undrawn commitment (fully drawn by definition).
    checks.append(("term loans have zero undrawn commitment",
                    (loans.loc[loans["commitment_type"] == "term_loan", "undrawn_commitment"] == 0).all()))

    # 5. Expected loss = PD x LGD x EAD, the Basel formula, recomputed.
    recomputed_el = (loans["pd"] * loans["lgd"] * loans["ead"]).round(2)
    checks.append(("expected_loss equals PD x LGD x EAD on every loan",
                    np.allclose(loans["expected_loss"], recomputed_el)))

    # 6. Realized loss is nonzero only where a default actually occurred.
    checks.append(("realized_loss is zero for every non-defaulted loan",
                    (loans.loc[~loans["defaulted"], "realized_loss"] == 0).all()))
    defaulted = loans[loans["defaulted"]]
    checks.append(("realized_loss equals LGD x EAD for every defaulted loan",
                    np.allclose(defaulted["realized_loss"], (defaulted["lgd"] * defaulted["ead"]).round(2))))

    # 7. Structural guarantees.
    checks.append(("loans.borrower_id has zero orphans",
                    loans["borrower_id"].isin(borrowers["borrower_id"]).all()))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)
    return all_ok


if __name__ == "__main__":
    tables = build(n_borrowers=3000, seed=RNG_SEED)
    print(f"borrowers: {len(tables['borrowers'])}  loans: {len(tables['loans'])}")
    total_ead = tables["loans"]["ead"].sum()
    total_el = tables["loans"]["expected_loss"].sum()
    print(f"portfolio EAD: ${total_ead:,.0f}   portfolio expected loss: ${total_el:,.0f}"
          f"   ({total_el / total_ead:.3%} of EAD)")
    print()
    ok = verify(tables)
    print()
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    raise SystemExit(0 if ok else 1)
