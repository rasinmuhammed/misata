# Misata 0.8.1.10: Conformance hardening + the full quantitative toolbox

This release is the product of three intensive **engine-conformance sweeps** that
validate generated *output* statistically — not just that generation runs. They
surfaced a class of "silently-wrong-data" bugs where a feature worked in its happy
path but broke on a common variation. Eight were found and fixed, each with a
standing regression test. It also sharpens the LLM's quantitative-pattern routing
and adds two long-missing structural features.

## Added

- **`rate_curves` are extracted from natural language** and parsed end to end — a
  rate/proportion of a boolean or categorical column over time ("churn rises from
  2% to 9%"), distinct from an outcome curve's magnitude.
- **Table-level `correlations` are parsed from LLM/dict output** (`{col_a, col_b,
  r}`), including negative `r` for inverse relationships.
- **Self-referential foreign keys** (`employees.manager_id → employees.id`, comment
  threads, category trees) are now supported instead of rejected as a cycle.
- **Empty (`__rows__: 0`) tables** are honoured as empty tables with their columns.
- New docs: guides for **rate curves**, **conditional columns (`depends_on`)**, a
  full **distribution reference**, and a `__correlations__` section.

## Changed

- **System prompt rewritten with a quantitative-pattern decision tree**, so the
  model stops forcing every statement into an `outcome_curve`: magnitude-over-time
  → `outcome_curves`; rate-over-time → `rate_curves`; a static split → categorical
  `probabilities`; a heavy-tailed shape → a `distribution`; a conditional rate →
  `depends_on`. A sharpened litmus keeps "70/20/10" as probabilities, not a curve.

## Fixed

- **`from_dict_schema` silently dropped distribution params.** Poisson `lambda`
  (only `lam` was forwarded, but the generator reads `lambda`), binomial `n`/`p`,
  per-column `null_rate`/`outlier_rate`, and the `depends_on` `default` branch were
  all dropped — so declared behaviour degraded to defaults. The studio canvas
  round-trips every schema through this path, so hosted generation was affected.
- **The numeric engine lacked `binomial` and `zipf`** — both fell through to
  `uniform[0,1000]`. `zipf` is what the prompt now emits for heavy-tailed columns,
  so power-law requests were producing uniform noise.
- **Cross-table formulas mis-joined** when the parent PK name differed from the
  child FK name (the standard `id` / `entity_id` convention) — they joined on the
  child's own `id` and produced wrong values for most rows. The formula engine now
  receives the authoritative FK column from the relationships.
- **Categorical rate curves leaked the base incidence** on top of the target
  (Jan 0.14 vs 0.05 declared); negatives still holding the positive label are now
  reassigned, so the realised rate is exact. Boolean/numeric flags were already.
- **A correlation and an outcome curve on the same column now warn** instead of the
  correlation being silently dropped (they conflict on one column).
- **A child of an empty parent now gets NULL foreign keys, not fabricated orphans**,
  preserving referential integrity.
- **A semantic type in the `type` field no longer crashes the parse** (`type:
  "email"` → `text` + `text_type`); unknown types fall back to `text`.

## Verification

`tests/test_engine_conformance.py` is a new standing suite that asserts on output
statistically (distribution fidelity, rate/outcome-curve and categorical-rate
conformance, correlation, cross-table formula joins, self-ref FK, empty tables).
**944 tests pass.** No public-API or schema changes — drop-in upgrade.

## Install

```bash
pip install misata==0.8.1.10
pip install 'misata[llm]'==0.8.1.10
```

**Full Changelog**: https://github.com/rasinmuhammed/misata/compare/v0.8.1.9...v0.8.1.10
