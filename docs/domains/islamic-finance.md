---
title: "Generate Islamic Finance Synthetic Data in Python | Misata"
description: "Generate synthetic Murabahah (cost-plus sale) contracts that hold to AAOIFI Sharia Standard No. 8: selling price equals cost plus a disclosed margin exactly, and the repayment schedule carries no interest anywhere. No real customer or bank data required."
---

# Generate Islamic Finance Synthetic Data in Python

AI tools that *audit* Sharia compliance already exist and are being adopted by real banks. Nothing generates *synthetic test data* shaped around Islamic finance primitives in the first place — which is a gap, because a `product_type` column that says "Murabahah" next to numbers that behave like a conventional interest-bearing loan is worse than useless for testing a Sharia-compliance pipeline. Misata generates a Murabahah portfolio where the cost-plus structure AAOIFI Standard No. 8 requires actually holds on every row, checked independently against the standard's own formula rather than asserted in a docstring.

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

That is the minimal shape. The full example — a disclosed profit margin fixed at signing, the AAOIFI cost-plus formula, and an equal-installment repayment schedule that sums to the exact selling price — is a working, runnable script: [`examples/islamic_finance_murabahah.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/islamic_finance_murabahah.py) in the repo. Run it directly:

```bash
python examples/islamic_finance_murabahah.py
```

It prints every guarantee below, checked against the data it just generated:

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

## What each number is grounded in

**The cost-plus formula.** AAOIFI Sharia Standard No. 8 (Murabahah) requires the seller to disclose the cost price and the profit margin at the time of contract, with the selling price being exactly their sum: `selling_price = cost_price + profit_margin`. This is not a modeling choice — it is the definitional test that separates a Murabahah sale from any other financing structure, and this example recomputes it independently from the raw `cost_price` and `margin_rate` columns rather than trusting a `selling_price` value the schema happened to write.

**The margin rate.** AAOIFI does not publish a universal profit-margin rate — margin-setting is each bank's own commercial pricing decision, made once at signing and applied to the disclosed cost price. This example declares a realistic market range (2%–12%, centered on 5.5%) the same way the [credit-risk example](credit-risk.md) declares its rating-mix weights: stated plainly as a realistic assumption, not independently cited the way the AAOIFI formula itself is.

**The zero-riba repayment schedule.** A Murabahah's defining difference from a conventional loan is not just how the price is computed — it's that the price, once fixed, never changes with time. There is no rate applied to an outstanding balance, so the total a customer repays over the life of the contract is exactly the selling price fixed at signing, split into **equal** installments. A conventional amortizing loan schedule would instead split each payment into shrinking interest plus growing principal, so early and late installments would differ even at a level total payment. This example checks for that signature directly: every installment on a contract is the same amount, and there is no per-contract drift in installment size by position — the two properties a hidden interest term would break first.

## The connection

`asset_type`, `cost_price`, and `tenor_months` aren't decorative labels sitting next to an independently-random `selling_price`. The selling price is a measured function of the disclosed cost and margin on every row, and the installment schedule is a measured function of that selling price and tenor — checkable, not assumed, the same discipline the [credit-risk](credit-risk.md) and [predictive-maintenance](predictive-maintenance.md) examples apply to their own domains.

## What this is not

This models Murabahah (AAOIFI Standard 8) specifically: a cost-plus sale with disclosed margin and equal-installment deferred payment. It does not model Ijarah (lease), Mudarabah (profit-sharing partnership), Sukuk (investment certificates), or Takaful (mutual insurance) — each of those is governed by a different AAOIFI standard with a different structural test, and none of them reduces to a cost-plus formula. It also does not model the underlying Sharia-board approval process, asset-ownership transfer mechanics, or default/late-payment handling (AAOIFI Standard 8 treats a late-payment charge as a charitable donation, not additional profit, which this example does not yet generate). This is scoped to the contract-and-repayment structure a synthetic test dataset needs, not a full product implementation.
