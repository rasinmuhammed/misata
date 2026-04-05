# Misata Glossary

This glossary exists for one reason: a playful name should never make the product harder to understand.

Every Misata term below maps to a concrete feature, not a vague mood.

## Core Terms

### Wand

Plain-English meaning: a fast way to generate a first dataset.

Use it when:
- you want a quick first run
- you are exploring a schema idea
- you want something useful without tuning every option

What it is not:
- a separate engine
- a special file format
- a replacement for the main API

Typical examples:
- `misata generate --story "..."`
- a first Python `DataSimulator(config)` run

### Spellbook

Plain-English meaning: a saved recipe or reusable generation setup.

Use it when:
- you want repeatable runs
- you want to save a good config and replay it later
- you want a team-friendly setup that can be versioned

What it is not:
- a hidden state file
- a different schema type

Typical examples:
- recipe config files
- saved generation presets for QA, demos, or CI

### Time Machine

Plain-English meaning: temporal shaping.

Use it when:
- the story depends on growth, decline, seasonality, spikes, or dips
- dates need to follow a realistic distribution
- metrics must roll up correctly by month, quarter, or year

What it includes:
- outcome curves
- date density
- temporal buckets
- time-based scenario shaping

What it is not:
- random date generation without structure

### Multiverse

Plain-English meaning: multiple scenario variants built from the same schema or business world.

Use it when:
- you want best case, base case, and worst case outputs
- you want to compare multiple business stories on the same structure

Current status:
- part of Misata's direction
- supported today through reusable configs and scenario planning patterns
- not yet a single flagship API concept across the entire product

### Constellation

Plain-English meaning: the relationship graph of the dataset.

Use it when:
- you want to understand how tables connect
- you are reasoning about parents, children, and generation order

What it includes:
- primary keys
- foreign keys
- dependency ordering
- topology-aware planning

### Runes

Plain-English meaning: rules, constraints, and formulas.

Use it when:
- one field must depend on another
- a business rule must always hold
- an aggregate target must match exactly

Examples:
- `profit = revenue - cost`
- `status = cancelled` means no `delivered_at`
- `CEO` implies an age floor

### Potion

Plain-English meaning: a realism or noise profile.

Use it when:
- you want imperfect data on purpose
- you want nulls, typos, or controlled irregularity
- you need a specific noise mode such as `analytics_safe`

What it is not:
- a default surprise mutation

Important:
- Misata stays clean and deterministic by default
- noise is opt-in

### Oracle

Plain-English meaning: validation and reporting.

Use it when:
- you want proof that generation matched the requested rules
- you want fidelity or privacy reports
- you want a data card or summary artifact

What it includes:
- validation checks
- advisory reports
- summary outputs

### Portal

Plain-English meaning: an import or export bridge.

Use it when:
- you want to work with databases
- you want schema introspection
- you want to bring external structure into Misata or send output out

Typical examples:
- SQLAlchemy introspection
- database seeding
- schema export

### Domain Capsule

Plain-English meaning: the resolved context pack used during generation.

It can include:
- locale
- domain hints
- vocabulary assets
- provenance
- realism context

Use it when:
- the generated values need to fit a specific world
- names, products, titles, or labels should be domain-aware

What it is not:
- a user-facing requirement for normal usage

Most users will never build one directly. Misata can compile it internally.

## Product Features Behind The Terms

### Story to Schema

Plain-English meaning: turn a plain-English description into a schema plan.

Main building blocks:
- `StoryParser`
- `LLMSchemaGenerator`

### Planning

Plain-English meaning: determine row counts, table roles, and generation strategy before rows are emitted.

Main building blocks:
- `GenerationPlanner`
- topology-aware row scaling

### Realism Engine

Plain-English meaning: fix contradictions and make rows behave like they belong to the same world.

Main building blocks:
- coherent emails and usernames
- geography alignment
- role-age rules
- product-category alignment

### Workflow Engine

Plain-English meaning: make process-style tables behave like real business lifecycles.

Main building blocks:
- workflow presets
- timestamp consistency
- event-sequence helpers

### Fact Engine

Plain-English meaning: generate constrained fact rows that match requested aggregate targets.

Main building blocks:
- exact sums
- bucket allocation
- time-based shaping

### Asset Store

Plain-English meaning: a local store of reusable vocabularies and imported assets.

Main building blocks:
- license-aware ingestion
- provenance tracking
- local reuse of approved assets

## Writing Rule

If a user can remember the magical term but not the actual feature, the term failed.

Misata names should help memory, not replace meaning.
