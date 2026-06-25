# Resilience & Coverage Design — being bulletproof across every domain

> **Goal.** A user can describe *any* business — a SaaS, a vineyard, a vet clinic,
> a semiconductor fab, a microfinance co-op in Lagos — and get data that is
> *structurally correct, statistically plausible, business-rule valid, and
> domain-recognisable*. Where we cannot be accurate, we are **honestly
> approximate and never silently wrong**. This document defines the bar, audits
> where we stand, and lays out an implementable path to get there.

This is the difference between "yet another Faker wrapper" and an engine teams
trust. The perception of "simple tool" is earned the moment a user sees a
`sensor_readings` table with no reading value, or a 200-case law firm with
10,000 attorneys. This doc is about never shipping that moment.

---

## 1. The bar: five fidelity dimensions

The synthetic-data literature converges on five axes. We hold every dataset to
all five, in priority order:

1. **Structural fidelity** — the right tables, keys, and relationships exist.
2. **Referential integrity** — no orphans; child rows point at real parents.
3. **Business-logic validity** — rows obey domain rules (a refund ≤ the order;
   a discharge date ≥ an admission date; a churned user has a cancel event).
   *This is the axis most tools fail* — data that is "statistically plausible
   but violates domain logic."
4. **Statistical fidelity** — marginals and joint distributions look real
   (lognormal revenue, bimodal ages, correlated height/weight).
5. **Domain recognisability** — a domain expert glancing at the data says "yes,
   that's a vet clinic" (species, breeds, vaccine names) not "that's the
   archetype skeleton of a vet clinic" (model, status, acquired_date).

Misata is already strong on 1–2, partial on 3–4, and **weakest on 5** — which
is exactly the axis a human notices first.

---

## 2. Where we stand: the tiered resilience model (honest audit)

Misata already has a real, layered architecture — not a single keyword lookup.
Coverage degrades gracefully across tiers:

| Tier | Mechanism | Module | Covers | Limit |
|---|---|---|---|---|
| T1 | **Keyword domains** (18) | `story_parser.DOMAIN_KEYWORDS` | saas, ecommerce, fintech, healthcare, pharma, crypto, social, realestate, marketplace, logistics, hr, edtech, gaming, crm, insurance, travel, streaming, fooddelivery | Hand-tuned; only these 18 are rich |
| T2 | **Statistical priors** (7) | `domain_priors` | realistic distributions for known metrics (mrr, salary, premium…) | Only 7 domains, ~dozens of metrics |
| T3 | **Archetype lattice** | `composer` | *any* unseen domain → person/asset/place/event/document tables via morphology | Structurally good, **value-shallow** |
| T4 | **LLM schema + values** | `llm_parser`, `smart_values` | open-ended stories, niche columns | Needs a key; non-deterministic unless cached |
| T5 | **Learn-from-real** | `profiler`, `mimic`, `capsule_from_dataframes` | exact-domain fidelity from a sample CSV | Requires the user to *have* data |
| T6 | **Capsules** | `capsules` | shareable, reviewable domain vocab packs (vet, legal, …) | Today few exist; community-seeded |

**The fallback chain works.** The cliff is *what each tier produces for niche
columns*, not *whether* it produces something.

---

## 3. The empirical cliffs (stress test, June 2026)

Four niche domains pushed through the story path (`misata.generate`). Structure
held; the gaps below are real and reproducible.

### C1 — Archetype collapse drops domain-specific columns
- **Vet clinic** `animals` → `[animal_id, model, status, acquired_date]`.
  An animal became an *asset* (model/acquired_date) instead of having
  **species, breed, name, age, weight**.
- **Vineyard** `wine_lots` → `[name, city, is_active]` — a wine lot got a
  `city` (place confusion), not varietal/vintage/volume.

### C2 — Measured values are missing (the whole point of telemetry/labs)
- **Factory** `sensor_readings` → `[…, reading_date, status]` with **no
  temperature, no vibration** — the measurement named in the story is absent.
- Event/reading entities lack their core numeric payload.

### C3 — Explicit story attributes are ignored
- "temperature and vibration sensor readings", "billable hours" — named in the
  prompt, **never become columns**. The parser extracts *entities*, not
  *attributes*.

### C4 — Cardinality is unrealistic / ignores stated and implied ratios
- 200 legal cases → **10,000 attorneys** and **10,000 clients**.
- 300 pet owners → 2,000 animals (≈7 pets each) and 30,000 vaccinations.
- 50 machines → 30,000 readings (no link to "hourly × duration").
- Default `30000`/`10000`/`2000` row counts override commonsense ratios.

These four cliffs are the entire gap between "plausible skeleton" and
"recognisable dataset." Each is independently fixable.

---

## 4. Use-case taxonomy (what we must cover)

Two orthogonal axes. Resilience = covering the **product** of them, not just
the rows.

**A. Domain breadth** (industry vocabulary + business rules)
SaaS · ecommerce/retail · fintech/banking · payments/fraud · crypto/web3 ·
healthcare/clinical · pharma/trials · insurance/actuarial · HR/payroll ·
CRM/sales · logistics/supply-chain · manufacturing/IoT · energy/utilities ·
telco · real-estate · travel/hospitality · gaming · streaming/media · social ·
edtech · gov/civic · legal · agriculture · scientific/lab · non-profit ·
automotive/AV · construction · field-service.

**B. Data-shape archetypes** (the *physics* of the rows, domain-independent)
1. **Entity/dimension** (users, products) — identity + attributes.
2. **Event/fact** (orders, clicks, payments) — timestamped, FK-heavy.
3. **Time-series/telemetry** (sensor readings, prices, vitals) — regular
   cadence, autocorrelated values, units.
4. **State-machine/lifecycle** (subscriptions, claims, tickets) — status
   transitions with valid orderings.
5. **Hierarchy/graph** (org charts, bill-of-materials, referrals) — self-refs.
6. **Ledger/double-entry** (accounting, wallets) — sums that must balance.
7. **Document/text** (reviews, notes, contracts) — realistic prose.
8. **Geospatial/movement** (trips, deliveries) — coherent lat/long paths.

Misata is strong on 1, 2, 7; partial on 4; **weak on 3, 5, 6, 8**. These shape
archetypes are *more leverage than more domains* — they generalise across every
industry. A robust time-series + ledger + lifecycle engine makes 30 domains
credible at once.

---

## 5. The resilience architecture (implementable)

Seven mechanisms, each mapped to code, each closing a specific cliff. Ordered by
impact-to-effort.

### M1 — Attribute extraction from the story  *(closes C3)*
Teach the parser to lift **named attributes**, not just entities. "machines
emitting **temperature and vibration**", "**billable hours**", "orders with a
**total** and **discount**".

- *Where:* new pass in `composer.extract_entities` / `story_parser`, run after
  entity extraction. Regex + a noun-attribute lexicon (`temperature→float°C`,
  `hours→float`, `vibration→float`), attached to the nearest entity.
- *Output:* extra `Column`s with `domain_priors`-backed distributions.
- *Acceptance:* the factory story yields `sensor_readings.temperature` and
  `.vibration` with sane units/ranges.

### M2 — Measured-value columns for event/reading archetypes  *(closes C2)*
Every `event`/`reading` entity gets a **payload column** appropriate to its
verb: a `reading` → a `value` (+`unit`); a `payment` → an `amount`; a `test` →
a `result`. Misata already tags `MONETARY_EVENTS`; generalise to
`MEASURED_EVENTS` → `{value, unit}` and `SCORED_EVENTS` → `{score}`.

- *Where:* `composer._columns_for(entity)` archetype → column synthesis.
- *Acceptance:* no reading/measurement table ships without its numeric payload.

### M3 — Cardinality realism engine  *(closes C4)*
Replace flat `30000`/`10000` defaults with **ratio-aware** row counts:
1. Honour explicitly stated counts ("200 cases", "50 machines").
2. Derive child counts from **relationship multipliers** (pets-per-owner ≈ 1.6;
   readings = machines × cadence × window; attorneys ≪ cases).
3. Default multipliers per `(parent_archetype, child_archetype)` pair, seeded
   from `domain_priors` + commonsense lattice; overridable in the schema.

- *Where:* `composer._default_rows` + `RealismConfig.relationship_multipliers`
  (already exists — wire it into the composer path and the studio).
- *Acceptance:* a 200-case firm has ~20–60 attorneys, not 10,000.

### M4 — Domain capsules as the niche-coverage flywheel  *(closes C1, C5)*
Capsules are the scalable answer to "infinite domains." A capsule supplies:
vocab pools (species, breeds, vaccine names, varietals), per-column
distributions, business rules, and cardinality priors — **without touching the
engine**.

- *Ship a starter library* (vet, legal, manufacturing, energy, agriculture,
  scientific) using `capsule_from_llm` + human review, stored as reviewable
  JSON. Each new capsule upgrades a domain from T3→T1 quality.
- *Auto-select* a capsule when story keywords match; *auto-build* one on the
  fly via `capsule_from_llm` when a key is present and no capsule fits, then
  cache it.
- *Where:* `capsules`, `story_parser` domain hook, `realism` vocab lookup.
- *Acceptance:* "vet clinic" animals have species/breed/name; a community PR
  adds a domain in one reviewable file.

### M5 — Shape-archetype generators  *(closes weak shapes 3/5/6/8)*
Domain-independent generators for the data *physics*:
- **Time-series:** cadence + AR(1)/trend/seasonality + noise + unit. (Partial
  `time_series` param exists — promote to a first-class archetype with cadence
  inference from the story: "every hour".)
- **Ledger/double-entry:** a `balance`/`__ledger__` directive guaranteeing
  debits = credits and running balances ≥ 0.
- **Hierarchy/graph:** self-referential FK with depth/branching control.
- **Geospatial:** coherent point sequences within a bounding region.
- *Where:* new `generators` + simulator hooks; declared via dict directives so
  the studio can expose them no-code.
- *Acceptance:* an accounting dataset balances to the cent; sensor telemetry is
  autocorrelated, not white noise.

### M6 — Business-rule validation gate (the trust moment)  *(raises axis 3)*
A post-generation **validator** that checks declared + inferred invariants and
either repairs or reports them, surfaced like the integrity proof:
- temporal ordering (`created_at ≤ updated_at ≤ closed_at`),
- lifecycle legality (status transitions follow the declared machine),
- arithmetic (`line_items.sum == order.total`, `refund ≤ amount`),
- range/category sanity per column.
- *Where:* extend `validation.py` + the `integrity` proof into a full
  **conformance report** returned with every run.
- *Acceptance:* every run ships a pass/fail card per invariant; violations are
  never silent.

### M7 — Honest-degradation contract (never silently wrong)  *(safety net)*
When confidence is low, **say so** instead of guessing:
- a per-column/table **confidence** (T1 capsule vs T3 archetype guess),
- a run-level **coverage report**: "animals: archetype-inferred (no vet
  capsule) — values are generic; add a capsule or sample CSV for fidelity,"
- the existing `StoryParser` fallback warning, generalised and structured.
- *Acceptance:* a user never *discovers* shallowness by surprise; the tool
  told them, with the fix one step away (capsule / CSV / LLM key).

---

## 6. The "always credible" guarantee (degradation ladder)

For any input, Misata picks the **highest tier that applies** and reports it:

```
exact CSV sample?        → T5 mimic            (highest fidelity, privacy-safe twin)
matching capsule?        → T1/T4 capsule        (domain-recognisable values)
known keyword domain?    → T1 priors            (tuned schema + distributions)
LLM key + niche story?   → T4 LLM + cache       (open-ended, then frozen)
anything else?           → T3 archetype + M1/M2 (structurally right, honestly generic)
```

No branch returns broken or silently-wrong data. Every branch returns the
conformance + coverage report (M6/M7). That contract — *correct or candid,
never confidently wrong* — is what separates a serious engine from a toy.

---

## 7. Phased roadmap (impact-ordered, each shippable)

**Phase 1 — Recognisability & honesty (closes the "simple tool" perception)**
- M1 attribute extraction, M2 measured-value columns, M3 cardinality realism.
- M7 coverage report (cheap, huge trust win).
- *Result:* niche stories produce *recognisable* schemas with payloads and sane
  scale, and admit what they inferred.

**Phase 2 — The capsule flywheel (scales to infinite domains)**
- M4 starter capsule library (6–10 domains) + auto-select + on-the-fly build.
- Capsule contribution guide + CI validation; community can add a domain in one
  file.

**Phase 3 — Shape mastery (credible across data physics)**
- M5 time-series, ledger, hierarchy, geospatial archetypes.
- Studio no-code controls for each.

**Phase 4 — The trust gate (enterprise-grade)**
- M6 full business-rule conformance report, repair loop, exportable as an audit
  artifact.

Each phase is independently valuable and independently shippable; each adds
acceptance tests to `tests/` (e.g. `test_resilience_<phase>.py`) so coverage is
provable, not asserted.

---

## 8. How we measure "bulletproof" (so it's not vibes)

A **coverage benchmark**: a corpus of ~40 stories spanning the §4 taxonomy,
scored automatically on the five §1 axes + recognisability (expert rubric or
capsule-match rate). Run in CI; a release cannot regress the aggregate score.
This turns "resilient for every use case" into a number that goes up.

---

### Sources
- [Synthetic data by industry — use cases & regulation (bluegen.ai)](https://bluegen.ai/what-industries-use-synthetic-data/)
- [Top synthetic data use cases (AIMultiple)](https://research.aimultiple.com/synthetic-data-use-cases/)
- [How reliable is synthetic data — failure modes (bluegen.ai)](https://bluegen.ai/how-reliable-is-synthetic-data/)
- [Why referential integrity matters in test data (Synthesized)](https://www.synthesized.io/post/why-referential-integrity-matters-in-test-data-management)
- [Benchmarking fidelity & utility of synthetic relational data (arXiv)](https://arxiv.org/html/2410.03411v1)
- [How to validate synthetic data: fidelity, utility, privacy (MJV)](https://www.mjvinnovation.com/blog/how-to-validate-synthetic-data-the-guide-to-fidelity-utility-and-privacy/)
