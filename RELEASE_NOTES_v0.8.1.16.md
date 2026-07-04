# Misata 0.8.1.16: Field-Report Fixes from misata.studio

Two prompts tested live on misata.studio exposed three realism defects. All
three are fixed at the engine level, regression-tested, and guarded in the
LLM schema prompt as well.

## What the field test found

**Prompt 1:** "A real-estate dataset of 10,000 listings where price rises
with square footage and falls with distance from the city center."

- `property_types.name` came back as tier words (Premium, Essential, Team,
  Active) instead of property types.
- `listing_statuses` repeated labels (cancelled twice in a 5-row lookup).
- `price` was visually constant at 80000, which also made the requested
  correlations impossible.

**Prompt 2:** "A SaaS with 8,000 customers on Free/Pro/Enterprise plans where
MRR and churn both depend on the plan tier." Invoice amounts landed near
$50,000 regardless of plan.

## The fixes

### Reference tables get real, distinct labels

Lookup tables (`*_types`, `*_statuses`, `*_categories`, `*_tiers`, `*_methods`,
…) now resolve their label column against head-noun pools:

- `property_types.name` → House, Apartment, Condo, Townhouse, Villa, …
- `listing_statuses.status` → Active, Pending, Sold, Under Offer, Withdrawn, …
- `order_statuses.status` → Pending, Confirmed, Shipped, Delivered, …
- 17 head-noun type pools and 8 domain status pools ship built in; unknown
  heads fall back to distinct generic labels.

Distinctness is enforced: a lookup table enumerates its labels, so weighted
draws that repeat are never produced, even when probabilities were declared
or the semantic layer offered too few choices.

### Mean-scaled default spread

A numeric column declaring only `mean` used to get a fixed std of 20, so
`mean: 80000` produced a ±0.06% spread: visually constant, correlation-dead.
The default std now scales with the declared mean (25%), or derives from
bounds when present. The field-report scenario now delivers: price
450k ± 113k with correlations +0.644 / −0.447 against declared +0.65 / −0.45.

### LLM schema prompt hardening

- Status example no longer teaches the generic active/inactive/pending trio;
  statuses must be entity-specific and lookup tables need at least as many
  choices as rows.
- New monetary-scale rules: SaaS invoices are plan-priced (Free = 0,
  Pro ≈ 29–99, Enterprise ≈ 500–5000) via `depends_on` + `mapping`; money
  columns never get a mean without a std.

## Install

```bash
pip install misata==0.8.1.16
```

## Verification

992 tests pass. Six new regression tests reproduce the exact field-report
failures: head-noun labels, distinct statuses, distinct-despite-probabilities,
mean-only spread, and signed correlations on a mean-only price column.
