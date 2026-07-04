# Misata 0.8.1.15: The Scientific Integrity Release

This release came out of a deep adversarial evaluation of the whole engine:
every documented input format executed, every statistical guarantee measured,
every impossible spec thrown at the validator. What the probes caught, this
release fixes. The engine's exactness was never the problem; its input
boundary and feasibility checking were. Both are now hard surfaces.

## Silent wrong-output bugs, fixed

### Bounded floats no longer collapse to a constant

A float column declared with only `min`/`max` fell back to a Normal(100, 20)
and was then clipped to the bounds. With `max: 5` every value clipped to
exactly 5.0; with `max: 100` half the mass piled onto the boundary. Declared
bounds now derive the default distribution (centered mean, (max-min)/6 sigma),
so `{"type": "float", "min": 0, "max": 1}` gives a real spread. This single
fix also repaired declared correlations, which the boundary ties were quietly
destroying: delivered Pearson r moved from errors up to 0.24 to at most 0.011
across positive and negative targets.

### The envelope schema format parses correctly

`from_dict_schema` given the YAML-style envelope (`{"name": ..., "seed": ...,
"tables": {...}, "relationships": [...]}`) used to treat `tables` as a table
named "tables" and silently generate garbage. The envelope now unwraps
properly: per-table `{"rows": N, "columns": {...}}` works, envelope
`relationships` accept `"users.user_id → orders.user_id"` strings, and
envelope constraints route to their tables. The flat format is unchanged.

### `references` strings build relationships

`{"type": "foreign_key", "references": "customers.customer_id"}` (the syntax
in the README's own rollup example) never created a Relationship, so
validation rejected it. It now does, and the README example generates with
zero orphans and exact rollups.

### The Oracle no longer fails its own flagship

`oracle["passed"]` returned False on perfectly curve-conformant datasets
because the row-count check did not know that outcome curves derive their own
row counts. Curve-governed tables now record
`row_count_derived_from_outcome_curve: true` and pass on non-emptiness;
everything else stays strict.

## Impossible specs now fail loudly, before generation

A world-class declared-outcome engine must reject declarations that no data
can satisfy. Three new pre-generation feasibility checks:

- **Rates are probabilities.** A rate curve with `rate: 1.7` raises with the
  fix spelled out, instead of silently clamping to 1.0.
- **Curve targets must fit the column bounds.** If no row count n in
  [min, max transactions per period] satisfies lo·n ≤ target ≤ hi·n, the spec
  is unreachable and the error shows the exact inequality that failed. It
  used to silently break the declared bounds to hit the target.
- **Contradictory constraints are detected.** `a > b` together with `b > a`
  (any cycle) used to silently force the columns equal, the opposite of both
  declarations. Now it raises naming the cycle.

Infeasible correlation sets (jointly impossible pairwise targets, e.g. 0.9,
0.9, -0.9) are projected to the nearest feasible matrix with a warning, and
now deliver real values instead of NaN columns.

## Correlations and exact curves finally compose

Declaring a correlation on the same column as an outcome curve used to give
you the curve and correlation ≈ 0. The engine now applies blockwise
Iman-Conover: values are re-ranked only within each time-period bucket, a
sum-preserving permutation, so per-period totals stay exact to the cent while
the declared correlation is delivered globally (r = 0.53 measured for a
declared 0.6, against 0.03 before). The rebalance pass also learned to leave
already-exact buckets untouched.

## Text intelligence: meaningful values for far more columns

Dict-schema string columns without an explicit `text_type` used to fall
through to business-note filler once outside the known names. Movie titles
became job titles ("Chief Operating Officer"), `cuisine` became "Pending
review by the billing team". New semantics with curated pools and
compositional grammars:

- `genre` (film / music / book pools chosen by table context)
- `cuisine`, `ingredients` (real cuisines; 3–6 ingredient comma lists)
- creative work titles (`movies.title`, `books.title`, `songs.title` compose
  from a title grammar: "The Stranger's Crown", "Hollow Orchard")
- `plot_summary` / `synopsis` (grammar-composed loglines)
- person-role columns (`director`, `author`, `artist`, `composer`, ...) now
  hold person names, never job titles
- `department`, `office_location` route to real departments and cities

## Custom pools, distributions, and patterns via the dict schema

Verified end to end through the Studio's wire format: weighted value pools
(`choices` + `probabilities`), string enums, explicit distributions with
parameters, `text_type` overrides, and pattern codes. Pattern syntax now also
accepts the spreadsheet-style placeholders every no-code user tries first:
`"AB-####"` (digits) and `"??-123"` (letters), alongside the regex forms.

## Property-based fuzzing in CI

A new Hypothesis suite generates hundreds of randomized schemas per run and
enforces the parser contract: tables preserved exactly, row counts honoured,
FK columns never orphaned, numeric bounds hold on every row, same seed gives
byte-identical output, and the envelope format parses identically to the flat
format.

## Install

```bash
pip install misata==0.8.1.15
```

## Verification

986 tests pass (up from 970): 10 format-regression tests, 6 Hypothesis
property suites (~240 randomized schemas per run), and updated conformance
tests for curve+correlation composition. The adversarial probe suite that
found these bugs now runs clean.
