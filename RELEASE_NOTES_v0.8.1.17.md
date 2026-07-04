# Misata 0.8.1.17: B2B Field-Report Fixes

A single studio prompt ("A B2B marketplace with exactly 500 suppliers, 12,000
buyers, and 300,000 orders...") exposed four defects. All fixed at the root
and regression-tested.

## What the field test found, and the fixes

### buyer_segments held person names; supplier_sizes held company names

"segments" and "sizes" were not recognized as lookup-table kinds, so the
table-noun hints ("buyer" → person, "supplier" → company) won. The
reference-table matcher now covers segments, sizes, grades, ranks, bands, and
brackets, with kind-aware pools: buyer_segments → Enterprise / Mid-Market /
SMB / Startup / Individual; supplier_sizes → Micro / Small / Medium / Large /
Enterprise; plan_tiers → Free / Basic / Pro / Business / Enterprise. Supplier
and vendor status pools added (Verified, Onboarding, Suspended, …).

### annual_gmv was constant 50000 — the constant returned despite prompt rules

Prompt guidance does not bind a model, so the guard moved into code: LLM
schema post-processing now sanitizes money-named numeric columns.
``min == max`` widens to ±25% around the value; a missing std becomes 25% of
the mean; a std under 0.1% of the mean (an effectively constant spec no real
dataset exhibits) is raised to 25%. Non-money columns and legitimately tight
specs (year_built mean 1985 std 20) are untouched.

### Philadelphia, Canada

Tables carrying both a city and a country column now keep them coherent, in
two layers: city generation conditions on the row's country when the country
already exists, and a post-generation pass re-maps any remaining incoherent
pair (needed because column order can put the city before the country).
Verified: 0 incoherent pairs across seeds.

## Install

```bash
pip install misata==0.8.1.17
```

## Verification

995 tests pass. Three new regression tests reproduce the exact field-report
failures: segment/size/tier labels, the spread sanitizer cases, and
city-in-country membership across 200 generated rows.
