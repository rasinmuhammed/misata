---
title: "Generate Islamic Finance Synthetic Data in Python | Misata"
description: "Generate synthetic Murabahah, Ijarah, Mudarabah, Sukuk, and Takaful data that holds to its own AAOIFI Sharia Standard exactly: cost-plus formulas, zero-riba repayment, asymmetric loss allocation, and fund separation, all checked independently against the data generated. No real customer or bank data required."
---

# Generate Islamic Finance Synthetic Data in Python

AI tools that *audit* Sharia compliance already exist and are being adopted by real banks. Nothing generates *synthetic test data* shaped around Islamic finance primitives in the first place — which is a gap, because a `product_type` column that says "Murabahah" next to numbers that behave like a conventional interest-bearing loan is worse than useless for testing a Sharia-compliance pipeline. Misata generates five such primitives, one per AAOIFI Sharia Standard, where the structure each standard actually requires holds on every row — checked independently against the standard's own formula, not asserted in a docstring.

| Primitive | AAOIFI Standard | Script | The property that actually matters |
|:--|:--|:--|:--|
| Murabahah | No. 8 | [`islamic_finance_murabahah.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/islamic_finance_murabahah.py) | `selling_price = cost_price + profit_margin`, repaid in equal, non-amortizing installments |
| Ijarah / Ijarah Muntahia Bittamleek | No. 9 | [`islamic_finance_ijarah.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/islamic_finance_ijarah.py) | Level rent for USE of an asset, not repayment of its cost; ownership stays with the lessor |
| Mudarabah + pooled accounts | No. 13, No. 40 | [`islamic_finance_mudarabah.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/islamic_finance_mudarabah.py) | Profit shared by a pre-agreed ratio; loss borne **entirely** by the capital provider |
| Investment Sukuk | No. 17 | [`islamic_finance_sukuk.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/islamic_finance_sukuk.py) | A Periodic Distribution Amount that traces to real underlying asset income, never called "interest" or "coupon" |
| Takaful | (mutual insurance) | [`islamic_finance_takaful.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/islamic_finance_takaful.py) | Participants' fund and operator's fund never commingle |

Each is a working, runnable script. Run any of them directly:

```bash
python examples/islamic_finance_murabahah.py
python examples/islamic_finance_ijarah.py
python examples/islamic_finance_mudarabah.py
python examples/islamic_finance_sukuk.py
python examples/islamic_finance_takaful.py
```

## Murabahah — the cost-plus sale (AAOIFI Standard 8)

```python
import misata

schema = {
    "murabahah_contracts": {
        "__rows__": 2000,
        "contract_id": {"type": "integer", "primary_key": True},
        "asset_type": {"type": "string",
            "enum": ["Vehicle", "Real Estate", "Equipment", "Commodity", "Consumer Goods"]},
        "tenor_months": {"type": "integer", "enum": [12, 24, 36, 48, 60]},
        "cost_price": {"type": "float", "distribution": "lognormal", "mu": 10.8, "sigma": 1.0,
                        "min": 8_000, "max": 2_000_000, "decimals": 2},
    },
}
tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=8))
print(list(tables.keys()))   # ['murabahah_contracts']
```

That is the minimal shape. The full script adds a disclosed profit margin fixed at signing, the AAOIFI cost-plus formula, and an equal-installment repayment schedule that sums to the exact selling price:

```
customers: 1400  contracts: 2000  installments: 67392
portfolio cost: 158,587,377   portfolio selling price: 167,326,073   total disclosed profit: 8,738,696

  [OK] selling_price equals cost_price + profit_margin exactly, every contract
  [OK] profit_margin equals cost_price x margin_rate exactly, every contract
  [OK] margin_rate stays within [2%, 12%] on every contract
  [OK] sum of installments equals selling_price exactly, every contract
  [OK] every installment on a contract is the same amount (equal, not amortizing)
  [OK] no per-contract drift in installment_amount by position (|slope| < 0.001)
  [OK] installment count matches tenor_months exactly, every contract
  [OK] contracts.customer_id has zero orphans
  [OK] installments.contract_id has zero orphans

Coherence audit: score=100.0  clean=True
ALL CHECKS PASSED
```

**The cost-plus formula.** AAOIFI Sharia Standard No. 8 requires the seller to disclose the cost price and the profit margin at the time of contract, with the selling price being exactly their sum: `selling_price = cost_price + profit_margin`. This is not a modeling choice — it is the definitional test that separates a Murabahah sale from any other financing structure, and the script recomputes it independently from the raw `cost_price` and `margin_rate` columns rather than trusting a `selling_price` value the schema happened to write.

**The margin rate.** AAOIFI does not publish a universal profit-margin rate — margin-setting is each bank's own commercial pricing decision, made once at signing and applied to the disclosed cost price. The script declares a realistic market range (2%–12%, centered on 5.5%) the same way the [credit-risk example](credit-risk.md) declares its rating-mix weights: stated plainly as a realistic assumption, not independently cited the way the AAOIFI formula itself is.

**The zero-riba repayment schedule.** A Murabahah's defining difference from a conventional loan is not just how the price is computed — it's that the price, once fixed, never changes with time. There is no rate applied to an outstanding balance, so the total a customer repays over the life of the contract is exactly the selling price fixed at signing, split into **equal** installments. A conventional amortizing loan schedule would instead split each payment into shrinking interest plus growing principal, so early and late installments would differ even at a level total payment. The verification checks for that signature directly: every installment is the same amount, and there is no per-contract drift in installment size by position.

## Ijarah and Ijarah Muntahia Bittamleek — the lease (AAOIFI Standard 9)

```
lessees: 1050  contracts: 1500  (IMB: 872)  schedule rows: 75644
total asset value: 403,757,717   total rental collected: 148,808,362

  [OK] sum of rentals equals total_rental exactly, every contract
  [OK] every rental on a contract is the same amount (level rent)
  [OK] asset_owner is 'lessor' for every rental row
  [OK] every IMB contract has exactly one ownership_transfer row
  [OK] IMB transfer price equals asset_value x the nominal fraction exactly
  [OK] plain Ijarah contracts have zero ownership_transfer rows
  [OK] plain Ijarah contracts carry zero transfer price
  [OK] transfer price as a fraction of asset_value is independent of total_rental
  [OK] no column encodes an interest rate or an outstanding balance
  [OK] contracts.lessee_id has zero orphans
  [OK] schedule.contract_id has zero orphans

Coherence audit: score=100.0  clean=True
ALL CHECKS PASSED
```

**Rent for use, not repayment of cost.** An Ijarah rental is payment for the USE of an asset the lessor still owns — not repayment of the asset's cost the way a loan installment retires principal. That's the property a loan-shaped schema gets wrong by default: a loan's payment shrinks the lender's claim on the asset as payments are made; a lease's payment does no such thing. The script checks this directly — `asset_owner` stays `"lessor"` for every rental row on every contract, right up until an actual transfer event.

**Two structures, one schedule shape.** Plain Ijarah rents for the term and hands the asset back — no transfer, no `ownership_transfer_price`. Ijarah Muntahia Bittamleek (IMB) adds a separate, **nominal**, pre-agreed transfer price paid once at the end. AAOIFI Standard 9 requires that price be a token amount, not a disguised final installment of the asset's cost — the script prices it from `asset_value` alone (1% of it) and checks that it is statistically independent of the rental total, so a schema that quietly turned it into a balloon payment on a hidden loan balance would fail this check, not pass it by coincidence.

**Level rent, not amortizing.** Every rental on a contract is the same amount, and there is no per-contract drift in rental size by installment position — the same zero-riba signature Murabahah checks for, applied to a lease instead of a sale.

## Mudarabah and pooled investment accounts — asymmetric loss (AAOIFI Standards 13, 40)

```
providers: 900  ventures: 1500  (loss-making: 326, negligent: 43)
total capital: 281,164,632   total mudarib P&L: 10,412,416   total rabb_al_mal P&L: 18,862,215

  [OK] profitable ventures: mudarib_pnl equals venture_pnl x the agreed ratio exactly
  [OK] profitable ventures: mudarib + rabb_al_mal profit reconciles to venture_pnl exactly
  [OK] ordinary-loss ventures: mudarib_pnl is exactly zero, every one
  [OK] ordinary-loss ventures: rabb_al_mal absorbs the entire loss exactly
  [OK] negligent-loss ventures exist to exercise the exception path
  [OK] negligent-loss ventures: mudarib bears the loss, rabb_al_mal is made whole
  [OK] no mudarib_capital_contribution column exists (mudarib contributes no capital)
  [OK] mudarib_pnl + rabb_al_mal_pnl equals venture_pnl exactly, every venture
  [OK] losing pool periods: bank_mudarib_fee is exactly zero
  [OK] every pool period: depositor P&L reconciles to pool P&L net of bank fee
  [OK] within a profitable period, P&L-per-weighted-capital is uniform across depositors
  [OK] ventures.provider_id has zero orphans

Coherence audit: score=100.0  clean=True
ALL CHECKS PASSED
```

**The actual hard part.** A Mudarabah has two parties: the rabb al-mal (capital provider), who puts up all the capital and none of the labor, and the mudarib (managing partner), who puts up all the labor and none of the capital. Profit splits by a ratio agreed *before* the venture starts. Loss does not split at all — the rabb al-mal bears every dirham of financial loss, and the mudarib bears none, only the uncompensated value of their own time. Most synthetic generators asked to model "profit sharing" would default to a symmetric split, the way conventional equity partners share both gains and losses. That default is exactly the violation the script's `verify()` checks for and refuses to produce: on every loss-making, non-negligent venture, `mudarib_pnl` is checked to be **exactly zero**, not close to zero.

**The one real exception.** If the mudarib breached the contract or acted with proven negligence (`ta'addi`), Sharia makes them liable for the resulting loss. The script models this as a genuine minority case (15% of loss-making ventures) with its own separate check — negligent-loss ventures shift the loss onto the mudarib and make the rabb al-mal whole — so the exception has real conditions attached rather than being a backdoor for a symmetric split by default.

**Structural, not just numeric.** There is no `mudarib_capital_contribution` column at all — not a column holding zero on every row, which the engine's own coherence audit flags as a near-constant realism smell, but the field's actual absence, proving the mudarib contributes no capital by construction rather than by convention.

**Standard 40: pooled investment accounts.** A bank running a Mudarabah-based savings product pools many rabb al-mal depositors' capital, weights each depositor's share of the pool's profit by their own capital and how long it sat in the pool that period (AAOIFI's "weightage" mechanism), and takes its own agreed management fee off the top — but only when the pool actually made money. The script checks that a losing pool period leaves the bank's fee at exactly zero, not negative, and that depositor P&L always reconciles exactly to the pool's P&L net of that fee.

## Investment Sukuk — the Periodic Distribution Amount (AAOIFI Standard 17)

```
issuances: 6  certificates: 30000  distribution rows: 144
total issuance value: 86,000,000   total distributed: 15,156,958

  [OK] total_issuance_value equals face_value x n_certificates exactly
  [OK] every certificate's face_value matches its issuance's declared face value
  [OK] periodic_distribution_amount equals pool_rental_income / n_certificates exactly
  [OK] no column anywhere is named 'interest' or 'coupon'
  [OK] redemption_amount_per_certificate equals face_value_per_certificate exactly
  [OK] each issuance has exactly maturity_months distribution periods
  [OK] certificates.issuance_id has zero orphans
  [OK] distributions.issuance_id has zero orphans

Coherence audit: score=100.0  clean=True
ALL CHECKS PASSED
```

**The vocabulary is the tell.** A sukuk certificate is not a bond, its holder is not a creditor, and what it pays is not interest and not a coupon — it's a Periodic Distribution Amount (PDA), AAOIFI's own term, because the holder owns an undivided fraction of a real income-producing asset, not a claim on the issuer's general credit. Calling this column `interest` or `coupon` is itself a credibility tell for anyone who actually works in this space, so the script's `verify()` asserts directly that no such column exists anywhere in the generated tables.

**Backed by a real asset, not a separately-invented number.** This script imports [`islamic_finance_ijarah.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/islamic_finance_ijarah.py) and builds a real lease pool as the underlying asset for each sukuk issuance. `periodic_distribution_amount` is recomputed as that pool's actual monthly rental income divided across certificates — not a declared rate applied to face value, which is what would make this interest wearing a different name.

**Redemption at maturity is exactly face value.** The issuer executes a purchase undertaking and buys each certificate back at exactly its face value — nothing compounds into that number between issuance and maturity, regardless of how many distributions were paid along the way.

## Takaful — the fund that never commingles

```
participants: 960  policies: 1200  claims: 614
final PTF balance: 1,252,201   final operator balance: 649,370

  [OK] wakala_fee equals contribution x the disclosed fee rate exactly
  [OK] wakala_fee + ptf_contribution equals contribution exactly, every policy
  [OK] every claim is paid_from_fund == 'participants'
  [OK] ptf_balance_after_claims never goes negative, any period
  [OK] amount_paid never exceeds amount_requested
  [OK] total claims paid in a period never exceeds that period's PTF balance
  [OK] operator_balance reconciles to cumulative operator_fee_in alone, unaffected by claims
  [OK] sum_insured and contribution are single declared values, not a revision history
  [OK] policies.participant_id has zero orphans
  [OK] claims.policy_id has zero orphans

Coherence audit: score=100.0  clean=True
ALL CHECKS PASSED
```

**Two funds, never one.** Takaful is mutual/cooperative insurance: the Participants' Takaful Fund (PTF) and the Operator's Fund are two separate ledgers. The operator takes an agreed Wakala (agency) fee off each contribution up front, into its own fund, and manages the PTF as an agent — but claims are paid from the PTF alone, never from the operator's fund. The script tracks both as separate running balances and checks that `operator_balance` reconciles to nothing but the cumulative Wakala fee, completely unaffected by any claim.

**The PTF can't go negative.** A claim is capped at what the fund actually holds that period — the structural guarantee that makes this a real mutual fund and not an unfunded promise. The script checks `ptf_balance_after_claims >= 0` in every period, not as an assumption but as an emergent property of how claims are paid: capped at the fund's own balance, never above it.

**No `gharar`.** `sum_insured` and `contribution` are fixed, disclosed values at policy inception — one row per policy, never a revision history either side can retroactively change, which is the AAOIFI concern about excessive undisclosed uncertainty entering a contract after the fact.

## The connection, across all five

None of these primitives decorate a random number with a Sharia-sounding label. `asset_type`, `cost_price`, `capital_contributed`, `sum_insured` — none of them sit next to an independently-random outcome column. In every one of the five scripts, the outcome is a measured function of the declared inputs, recomputed independently in `verify()` and checked exactly, the same discipline the [credit-risk](credit-risk.md) and [predictive-maintenance](predictive-maintenance.md) examples apply to their own domains. Each script also runs Misata's own coherence audit against the data it generates and prints the score, so a structural realism regression (a near-constant column, a broken derived-math relationship, an orphaned foreign key) surfaces the same way it would for any other domain.

## What this is not

Each script models exactly one AAOIFI standard's defining structural test, not a full product implementation. Specifically out of scope for now: the underlying Sharia-board approval process; default and late-payment handling (AAOIFI Standard 8 treats a late-payment charge on Murabahah as a charitable donation, not additional profit, which none of these scripts generate); early termination or partial redemption of a sukuk before maturity; and a Musharakah (joint-venture, symmetric capital-and-loss) primitive, which is a different structure from Mudarabah's asymmetric one and is not modeled here. This is scoped to the contract-and-cashflow structure a synthetic test dataset needs for each standard, not a full regulatory or product implementation of it.
