# Contributing to Misata

Thank you for wanting to improve Misata.

Misata should feel technically serious and human to read. We want contributions that make the library stronger, clearer, and easier to trust.

## Core Principles

- Keep the public surface easy to understand.
- Keep the internal architecture honest and inspectable.
- Use playful naming only when the plain-English meaning stays obvious.
- Prefer clarity over cleverness.
- Write docs like a strong engineer explaining a difficult system to another strong engineer.

## Before You Start

Make sure you have:
- Python 3.10+
- Git
- an LLM provider key if you want to test the LLM-assisted paths

## Development Setup

```bash
git clone https://github.com/YOUR_USERNAME/misata.git
cd misata

python -m venv venv
source venv/bin/activate

pip install -e ".[dev]"
```

Optional:

```bash
cp .env.example .env
# add your provider keys if needed
```

## Making Changes

### What good changes look like

A good Misata change usually does at least one of these:
- improves realism without making behavior mysterious
- adds control without adding confusion
- makes generated data easier to validate
- makes docs easier for a normal person to follow

### Branch names

Use short, readable branch names:
- `feature/domain-capsule`
- `fix/time-density`
- `docs/readme-refresh`

### Commit messages

Keep commits short and human.

Good examples:
- `Teach Misata to shape time density safely`
- `Add asset-backed vocabularies to the realism engine`
- `Rewrite the quickstart for clarity`

## Testing

Run the relevant tests for the area you touched.

```bash
pytest tests/ -v
```

Examples:

```bash
pytest tests/test_simulator.py -v
pytest tests/test_validation.py -v
pytest tests/test_assets.py -v
```

If your change affects generation behavior, add or update tests.

## Documentation Rules

Misata uses a distinct voice, but the docs must remain easy to scan.

### Always do this

- explain the feature in plain English first
- pair magical terminology with a plain-English label
- show a concrete example
- make it obvious why the feature exists

### Never do this

- rename technical concepts so aggressively that users cannot guess what they do
- use fantasy language without a plain-English explanation nearby
- write marketing copy where setup instructions should be

### Example

Good:

`Time Machine` is Misata's label for temporal shaping. It controls date density, seasonality, and time-based scenarios.

Bad:

`The Time Machine bends chronology through arcane currents of probabilistic destiny.`

## Writing Style

Please read [MISATA_VOICE.md](MISATA_VOICE.md) before large doc changes.
Please read [MISATA_GLOSSARY.md](MISATA_GLOSSARY.md) before introducing a new magical term.

The short version:
- write like a talented human, not like a corporate template
- be warm, but not vague
- be memorable, but not theatrical
- be precise, especially in technical docs

## Areas That Need Help

Good contribution areas:
- realism and coherence rules
- asset-backed vocabularies
- time-density generation
- workflow simulation
- validation and reporting
- docs and examples

## Pull Requests

A strong PR should include:
- a clear summary
- tests when behavior changes
- docs updates when the public surface changes
- notes on tradeoffs if the change affects performance, realism, or determinism

## Questions

If something is unclear:
- open an issue
- open a discussion
- propose a doc change first if the confusion is in naming or explanation

Misata should become more magical only when it also becomes easier to understand.
