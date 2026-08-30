---
title: "Generate Credit Risk Synthetic Data in Python | Misata"
description: "Generate synthetic loan portfolios with PD, LGD, and EAD computed from real regulator-published numbers: S&P default rates by credit rating, Basel Foundation IRB supervisory LGD, and the Basel credit-conversion-factor formula for EAD. No real loan data required."
---

# Generate Credit Risk Synthetic Data in Python

Every bank capital model runs on three numbers: probability of default (PD), loss given default (LGD), and exposure at default (EAD), combined into expected loss as `EL = PD × LGD × EAD`. A `credit_score` column and a `defaulted` column with no statistical relationship between them is worse than useless for validating a risk model — realized defaults have to actually track the declared PD, by rating grade, for the data to mean anything. Misata generates a loan portfolio where they do, using the regulator's own published numbers rather than plausible-sounding placeholders.

```python
import misata

schema = {
    "borrowers": {
        "__rows__": 3000,
        "borrower_id": {"type": "integer", "primary_key": True},
        # S&P's real credit-rating scale, not a fictional 1-10 score.
        "credit_rating": {"type": "string",
            "enum": ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"],
            "weights": [0.02, 0.06, 0.17, 0.30, 0.22, 0.16, 0.07]},
    },
    "loans": {
        "__rows__": 4200,
        "loan_id": {"type": "integer", "primary_key": True},
        "borrower_id": {"type": "integer", "foreign_key": {"table": "borrowers", "column": "borrower_id"}},
        "seniority": {"type": "string", "enum": ["senior_unsecured", "subordinated"], "weights": [0.82, 0.18]},
        "drawn_amount": {"type": "float", "distribution": "lognormal", "mu": 13.5, "sigma": 1.1,
                          "min": 50_000, "max": 25_000_000, "decimals": 2},
    },
}
tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=11))
print(list(tables.keys()))   # ['borrowers', 'loans']
```

That is the minimal shape. The full example — PD by rating, LGD by seniority, EAD from drawn plus a credit-conversion-factor on undrawn commitment, and a real Bernoulli default draw at each borrower's own PD — is a working, runnable script: [`examples/credit_risk_portfolio.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/credit_risk_portfolio.py) in the repo. Run it directly:

```bash
python examples/credit_risk_portfolio.py
```

It prints every guarantee below, checked against the data it just generated:

```
borrowers: 3000  loans: 4200
portfolio EAD: $5,629,505,202   portfolio expected loss: $62,364,849   (1.108% of EAD)

  [OK] 'AAA' (S&P PD 0.00%): exactly zero realized defaults (0 of 68)
  [OK] 'AA' (S&P PD 0.00%): exactly zero realized defaults (0 of 281)
  [OK] 'A' (S&P PD 0.00%): exactly zero realized defaults (0 of 718)
  [OK] 'BBB' realized default rate 0.0016 vs S&P PD 0.0003
  [OK] 'BB' realized default rate 0.0033 vs S&P PD 0.0028
  [OK] 'B' realized default rate 0.0141 vs S&P PD 0.0161
  [OK] 'CCC' realized default rate 0.2803 vs S&P PD 0.2692
  [OK] 'senior_unsecured' LGD is exactly 40% on every loan
  [OK] 'subordinated' LGD is exactly 75% on every loan
  [OK] EAD reconciles to drawn + CCF x undrawn on every loan
  [OK] term loans have zero undrawn commitment
  [OK] expected_loss equals PD x LGD x EAD on every loan
  [OK] realized_loss is zero for every non-defaulted loan
  [OK] realized_loss equals LGD x EAD for every defaulted loan
  [OK] loans.borrower_id has zero orphans

ALL CHECKS PASSED
```

## What each number is grounded in

**PD, by credit rating.** S&P Global Ratings' own published annual global corporate default rate, averaged across the six most recent studies (2019-2024) rather than any single volatile year. AAA, AA, and A each show exactly 0.00% in every one of those six years — a real fact about investment-grade defaults, not a placeholder. This example treats that as a guarantee to verify (exactly zero realized defaults in those three grades, checked against the actual generated rows) rather than smoothing it into something that looks more "generator-friendly."

**LGD, by seniority.** The Basel Foundation IRB *supervisory* value: 40% for senior unsecured claims on corporates, 75% for subordinated claims. This is not an estimate — it is the number a bank using the F-IRB approach is required to use (BIS/OSFI Capital Adequacy Requirements, Chapter 5, Internal Ratings-Based Approach), which makes it the least arguable figure in the whole example.

**EAD, for a partially-drawn facility.** `EAD = drawn + CCF × undrawn`, the Basel credit-conversion-factor formula. CCF is 20% for commitments of one year or less, 50% for longer commitments, and 0% for commitments that are unconditionally cancellable at any time — the same table used in the Basel standardized approach. A term loan is fully drawn by construction, so its undrawn commitment is exactly zero, not a stray random value the schema happened to assign.

**Expected loss.** `EL = PD × LGD × EAD`, recomputed independently in `verify()` from the raw columns, not just declared.

**The connection.** A borrower's `credit_rating` is not a decorative label sitting next to an independently-random `defaulted` flag. Whether a loan actually defaults is a real Bernoulli draw at that borrower's own S&P-published PD, so the realized default rate per rating grade is a measured property of the generated rows — checkable, not assumed.

## Portfolio composition

The rating-grade mix (2% AAA, 6% AA, 17% A, 30% BBB, 22% BB, 16% B, 7% CCC) is declared to be realistic of the real corporate bond market's skew toward investment grade, not independently cited the way the PD table itself is — stated plainly, the same honesty split used for the designed severity-tier progression in the [healthcare comorbidity example](healthcare.md#comorbidity-clusters-and-severity-driven-length-of-stay).

## A realism bug found and fixed after this shipped

The first release of this example passed every guarantee above and still gave itself away: `drawn_amount` came out as `130028.33004434995`, and `origination_date` as `2025-09-12 08:16:54`. No loan tape on earth carries a dollar figure to eleven decimal places or an origination date to the nanosecond. The first was a one-line schema fix (`"decimals": 2`). The second was a real engine bug — `"type": "date"` was silently getting a time-of-day added by the same temporal-profile system that gives `"type": "datetime"` columns their realistic business-hour grids, in four separate code paths in `misata/simulator.py`. Fixed in 0.9.6.36, with a permanent regression test at the engine level (`tests/test_date_type_has_no_time.py`) so any schema declaring `"type": "date"`, not just this one, stays a calendar day rather than a timestamp.

## What this is not

This models unsecured commercial lending using the Foundation IRB's own supervisory parameters, not a full internal-ratings-based capital calculation. Real F-IRB models also incorporate maturity adjustments, correlation parameters, and a bank's own internal PD estimation rather than S&P's public corporate-bond default study — this example is grounded in real, checkable regulatory numbers to produce realistic *test* data, not a substitute for an actual capital adequacy filing. Retail/consumer lending (mortgages, credit cards held by individuals) uses different LGD conventions than the corporate F-IRB values used here; this example is scoped to commercial/corporate lending specifically.
