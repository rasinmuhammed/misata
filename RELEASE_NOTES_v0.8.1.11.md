# Misata 0.8.1.11: Resilient curve directives

A small but important robustness release: a single malformed schema-level curve
directive can no longer take down a whole generation.

## Fixed

- **A bad `__rate_curves__` / `__outcome_curves__` entry no longer aborts the
  entire generation.** `from_dict_schema` raised a `ValueError` on the first
  invalid curve, so one wrong directive — e.g. a UI sending `{column: "table.col",
  start_rate, end_rate}` instead of the engine's `{table, column, rate_points}` —
  produced **no data at all** ("Schema rejected by engine"). Invalid curves are
  now skipped with a warning and the rest of the schema still generates, matching
  the resilience the LLM-parser path already had.

## Unchanged by design

- `__noise__` remains fail-loud: it is the ground truth a data-quality pipeline is
  tested against, so a malformed spec must surface immediately rather than silently
  running the test on clean data. `__constraints__` already skipped invalid entries
  with a warning; `__correlations__` is validated at apply time.

## Install

```bash
pip install misata==0.8.1.11
```

No public-API or schema changes — drop-in upgrade. 945 tests pass.

**Full Changelog**: https://github.com/rasinmuhammed/misata/compare/v0.8.1.10...v0.8.1.11
