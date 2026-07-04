# Misata 0.8.1.9: The right tool for every quantitative pattern

This release fixes a class of issues where the LLM funnelled *every* quantitative
statement — rates, proportions, distributions, conditionals — into a single
`outcome_curve`. The model is now taught its full toolbox, the parser is wired to
support it, and several parser-robustness bugs are fixed.

## Added

- **`rate_curves` extracted from natural language.** "Churn rate rises from 2% to
  9% over the year" is now captured as a `rate_curve` (a rate/proportion of a
  boolean or categorical column over time) instead of being folded into a
  magnitude curve. The engine already supported rate curves end to end — only the
  extraction layer (system prompt + parser) was missing.
- **Table-level `correlations` parsed from LLM output.** "Default rate rises as
  credit score falls" becomes a pairwise `{col_a, col_b, r}` correlation
  (negative `r` for inverse relationships) instead of a degenerate empty curve.

## Changed

- **System prompt rewritten with a quantitative-pattern decision tree.** Four
  distinct tools, with rules for when to use each: `outcome_curves` (magnitude
  over time), `rate_curves` (rate/proportion over time), categorical
  `probabilities` (a static split like "70/20/10"), and `distribution_params`
  (a shape like power-law / long-tail). Conditional rates ("approval 80% auto /
  60% health") now map to `depends_on`.

## Fixed

- **Curves on id / primary-key / foreign-key columns are dropped** (both outcome
  and rate curves) — e.g. a curve on `video_views.id` or a rate on
  `tickets.status_id`. A curve on a non-measure column is skipped with a warning.
- **Spurious curves are no longer invented** for prompts that name no time trend.
- **A semantic type in the `type` field no longer crashes the parse.** `type:
  "email"` (or `url`, `phone`, `name`, …) is coerced to a `text` column with the
  intent preserved as `text_type`; any unknown type falls back to `text` with a
  warning instead of raising a `ValidationError`.
- **Product `title`/`category` coherence on marketplace tables.** A "27-inch
  Monitor" tagged `books` is fixed on any product/listing/catalog/marketplace
  table (previously only `*product*`/`*item*` tables and only a `name` column —
  `title` was ignored). The fix is category-authoritative, so coherence does not
  collapse the category distribution to a single value.

## Install

```bash
pip install misata==0.8.1.9
pip install 'misata[llm]'==0.8.1.9   # with Groq / OpenAI support
```

Compatibility: no schema or public-API changes — drop-in upgrade. 922 tests pass
(9 new regression tests).

**Full Changelog**: https://github.com/rasinmuhammed/misata/compare/v0.8.1.6...v0.8.1.9
