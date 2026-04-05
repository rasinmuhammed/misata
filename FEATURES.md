# Misata Features

This is the straight, practical guide to what Misata can do today.

If the README is the front door, this file is the room-by-room walkthrough.

## 1. Story to Schema

Misata can turn a plain-English prompt into a usable schema plan.

What it does:
- identifies likely tables
- infers columns and relationships
- chooses reasonable defaults
- can use either rule-based parsing or LLM-assisted planning

Use it when:
- you have a business story, not a finished schema
- you want to move faster than hand-writing configs

Main entry points:
- `StoryParser`
- `LLMSchemaGenerator`
- `misata generate --story "..."`

## 2. Relational Generation

Misata generates linked tables with referential integrity.

What it does:
- creates parent tables before child tables
- fills foreign keys in valid order
- keeps relationship structure intact

Use it when:
- you need database seeding
- you need realistic test datasets across multiple tables

## 3. Planning and Row Scaling

Misata plans row counts using relationship structure instead of assigning the same number of rows everywhere.

What it does:
- detects likely entity tables and transaction tables
- applies deterministic multipliers when realism planning is enabled
- preserves user-specified row counts when they are explicit

Use it when:
- flat row counts would make the dataset feel fake
- you want `customers`, `orders`, and `order_items` to scale naturally

Important:
- planning is explicit
- default behavior remains backward compatible

## 4. Exact Outcome Curves

Misata can generate rows that roll up to exact business targets.

What it does:
- allocates rows by period
- generates values that sum to target totals
- supports scenarios such as rising revenue, seasonal dips, and shaped monthly totals

Use it when:
- you are building BI demos
- you need dashboards to show the exact requested story
- you need mathematically controlled fact data

## 5. Time Density

Misata can shape when events happen, not just what values they hold.

What it does:
- changes date density by period
- supports spikes, peaks, slowdowns, and seasonal concentration
- avoids invalid operations on datetime values by treating time as a probability distribution

Use it when:
- the timing of rows matters
- January should be busier than February
- Q4 should carry more activity than Q2

## 6. Realism Engine

Misata adds semantic coherence across columns.

What it does:
- derives `email` from names where appropriate
- aligns geography fields
- keeps job titles and ages from clashing
- keeps product labels aligned to category context

Use it when:
- rows need to look like they belong to the same world
- independent random columns would create contradictions

Modes:
- `off`
- `standard`
- `strict`

## 7. Workflow Engine

Misata supports business lifecycle logic for process-style tables.

What it does:
- applies workflow presets
- keeps status and timestamps consistent
- supports order, subscription, and ticket-like flows

Use it when:
- you are generating operational data
- state progression matters
- timestamps must make sense relative to status

## 8. Controlled Noise

Misata can add realistic imperfections without breaking protected guarantees.

What it does:
- injects nulls, typos, outliers, or duplicates when requested
- protects exact-target and constrained columns in safe modes
- keeps clean deterministic defaults when noise is not configured

Use it when:
- you want data that behaves more like production messiness
- you are testing pipelines against imperfect records

## 9. Domain Capsules and Asset-Backed Vocabulary

Misata can resolve context-specific vocabularies before generation.

What it does:
- compiles a domain capsule from schema hints and assets
- prefers approved imported vocabularies over generic defaults
- tracks provenance for imported assets

Use it when:
- names, labels, products, roles, or categories need domain fit
- you want a path beyond hardcoded fallback pools

This is the foundation for:
- localization
- vertical-specific realism
- asset-backed generation

## 10. Reporting and Validation

Misata can check whether generation matched the requested shape.

What it does:
- validates exact-target outcomes
- checks relationships and structural issues
- produces advisory privacy and fidelity reports
- supports streaming-safe report generation

Use it when:
- trust matters
- you need proof, not just output
- you want summaries that fit large runs

## 11. Database and Schema Bridges

Misata can work with existing database structure.

What it does:
- introspects schemas
- supports SQLAlchemy models
- seeds databases directly

Use it when:
- you already have an app schema
- you want to generate data into a working environment

## 12. Recipes

Misata supports reusable generation setups.

What it does:
- stores generation configs for replay
- helps teams standardize repeatable runs
- makes demo and testing workflows easier to reproduce

Use it when:
- you have a dataset pattern worth keeping
- you want to share setup across teammates

## 13. Reports vs Guarantees

Some Misata features are exact guarantees. Some are advisory reports.

Guaranteed when properly configured:
- referential integrity
- exact constrained aggregates
- deterministic generation with a fixed seed
- protected-column handling in safe noise modes

Advisory in the current architecture:
- privacy scoring
- fidelity scoring
- data cards
- realism heuristics outside hard constraints

This distinction matters. Misata should sound exciting, but it should never overclaim.

## 14. What Is Emerging

These ideas are part of Misata's direction and vocabulary, but they are still growing:
- `Multiverse` for first-class scenario branching
- richer domain capsules
- broader localization packs
- higher-scale vectorized workflow simulation

## Quick Mental Model

If you are new, think of Misata like this:

1. Describe the world.
2. Let Misata infer or load the structure.
3. Plan how much data should exist and how it should behave.
4. Generate rows with constraints, realism, and workflows.
5. Validate the result.

That is the whole product in one loop.
