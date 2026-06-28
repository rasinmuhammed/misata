# Misata 0.8.1.8: Precise value-quality for every column type

This release closes a class of value-quality bugs where columns in lookup and
dimension tables generated human names or lorem sentences instead of the right
kind of data. The fix is multi-layer: the dispatch table, the context-aware
generator, and the studio API enrichment step are all corrected so every common
column pattern — plans, companies, products, users, events, invoices — produces
semantically correct values.

## What was wrong

When the LLM path doesn't emit `inline_data` for a lookup table (which happens
intermittently), Misata falls back to a text generator. Several dispatch bugs
meant that fallback produced the wrong type of text:

| Column | Table | Was generating | Now generates |
|---|---|---|---|
| `name` | `plans` | Person names ("Mohammed Haddad") | Tier labels ("Premium", "Growth") |
| `name` | `companies` | Person names or tier labels | Company names ("Relay Systems") |
| `name` | `products` | Tier labels | Product names ("Merino Wool Sweater") |
| `domain` | `companies` | Product descriptions | URLs ("https://…") |
| `industry` | `companies` | Lorem sentences | Real sectors ("FinTech", "Manufacturing") |
| `event_name` | `events` | Lorem sentences | Event slugs ("page_view", "checkout") |
| `action_name` | `logs` | Tier labels | Event slugs ("login", "onboarding_completed") |
| `customer_name` | `invoices` | Tier labels (via `_infer_semantic`) | Person names |

## Root causes and fixes

**1. `simulator.py` dispatch table** — `_REALISTIC_TYPE_MAP["name"]` was
hard-wired to `"person_name"`, bypassing the table-context guard entirely.
Changed to `"name"` so the new context-aware handler is always reached.

**2. Missing `semantic == "name"` handler** — `realism.generate()` had no
handler for `semantic = "name"`, so it fell through to the product-description
catch-all. Added a full context-aware handler:
- Column has a person qualifier (`customer`, `user`, `recipient`, …) → person name
- Table is a person table (users, customers, members, …) → person name
- Table is a company table (companies, vendors, organizations, …) → company name
- Table is a product table (products, items, catalog, inventory, …) → product name
- Column name contains `event` or `action` → event-type slug
- Everything else (plans, statuses, lookup tables) → short tier label

**3. LLM mislabelling guard** — when the LLM explicitly sets
`text_type: "person_name"` on a bare `name`/`full_name`/`display_name` column
in a non-person table, the old code produced person names unconditionally. Added
a guard: bare name columns in non-person tables are re-routed to the correct
type based on table context.

**4. No pre-inference for undeclared columns** — columns with no `text_type` in
the schema (like `industry`, `event_name`) received `text_type = "sentence"` as
a default and then fell to the lorem-sentence generator before `_infer_semantic`
was ever called. Added a pre-inference step in `simulator.py` that runs
`_infer_semantic` for any undeclared column, catching these before the fallback.

**5. New semantic types** — added `"industry"` (30-item vocabulary: FinTech,
Manufacturing, EdTech, Logistics, …) and `"event_type"` (24-item vocabulary:
`page_view`, `checkout`, `subscription_created`, …) so these columns generate
domain-appropriate values, not generic labels.

**6. `_infer_semantic` qualifier awareness** — the `*_name` suffix branch now
inspects the column qualifier directly (`customer` → person, `company`/`vendor`
→ company, `event`/`action` → event type) regardless of the table name, so
`customer_name` in `invoices` and `recipient_name` in `emails` correctly infer
person-name without needing the table to be named "customers".

**7. Studio API enrichment** — `engine_public._SEMANTIC_RULES` had a `^name`
pattern that stamped `text_type: "name"` on every bare `name` column before it
reached the generator, removing the table-context signal. Removed the bare
`^name` match; qualified patterns (`customer_name`, `full_name`, `display_name`,
`user_name`) are still enriched.

## What's unchanged

- Public API: all functions, dict-schema format, and SchemaConfig fields are
  identical — drop-in upgrade.
- When the LLM returns `is_reference: true` with `inline_data`, plan/status/type
  names come from that inline data (Starter / Pro / Enterprise) and none of these
  generators are called. These fixes only affect the fallback text-generation
  path.

## Install

```bash
pip install misata==0.8.1.8
pip install 'misata[llm]'==0.8.1.8   # with Groq / OpenAI support
```

## Verification

915 tests pass. 4 new regression tests lock in the multi-layer fix:
`test_realism_explicit_person_name_in_lookup_table_is_guarded`,
`test_realism_products_table_name_column_generates_product_names`,
`test_realism_action_name_in_logs_gives_event_type`,
`test_realism_customer_name_infer_semantic_returns_person`.

**Full Changelog**: https://github.com/rasinmuhammed/misata/compare/v0.8.1.7...v0.8.1.8
