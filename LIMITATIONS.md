# Where Misata is expected to fail

This page lists the boundaries of the library as they actually are, found by
adversarial testing of our own output. Every guarantee Misata makes is
machine-checkable (certificates, audits, tests); everything on this page is
what those checks do not cover, or cover only partially. If a claim elsewhere
in the docs seems to contradict this page, this page wins and the docs have a
bug worth reporting.

## Values and vocabulary

- **City to state is exact only for the 58 cities with embedded geodata.**
  Amsterdam always gets North Holland. A generated city outside that set gets a
  state that is correct for its country but may not be correct for that city
  (Toulouse can appear in Ile-de-France). Countries outside the 14 with
  state/format pools fall back to generic values.
- **Priors are name-routed and English-first.** A column named `rating` gets a
  J-shaped distribution; a column named `bewertung` does not. Recognition is by
  exact and suffix name match, deliberately conservative: a name the router
  does not recognise gets a generic distribution, not a guessed one.
- **Priors are US-flavoured where currency or culture matters.** Salary shapes
  center on US dollar magnitudes, price endings follow US retail conventions.
  Locale packs adjust names, phones, and formats, not economic distributions.
- **Free text is grammar-generated, not written.** It agrees with its row:
  reviews follow their rating and name their product, ticket subjects,
  descriptions and resolutions describe one issue, a clinical note keeps one
  case (complaint, findings, diagnosis, medicine and advice agree), a blog
  post stays on one topic, feedback talks about one product's features. It
  does not repeat itself: every kind passes the exact-duplicate, skeleton and
  near-copy checks. On vocabulary, measured by `realism_report` at 2,000 rows
  (real text compresses under 3x under gzip; the check warns above 4x):
  every kind passes except chief complaints, which compress about 4.2x. They
  are seven-word triage fragments, and real triage text is at least as
  repetitive, so there is no real reference to calibrate that kind against.
  Several kinds pass with little margin (3.9-4.0x): product descriptions,
  delivery instructions, discharge instructions, churn reasons and bios. A reader skimming rows will not notice; a
  classifier trained on word n-grams still could. Closing the rest needs
  larger phrase banks or a language model in the data path; Misata keeps
  generation deterministic, seedable and offline instead.
- **Fictional entities are the point, not a bug.** Company names, people, and
  products do not exist. Anything needing real-world facts in the values
  (actual ticker prices, real addresses) is out of scope by design.

## Values and vocabulary (capsule price bands)

- **Price bands need the category generated first.** A capsule's price band
  draws from the row's category value, so the category column must precede
  the price column in the schema's column order. When it does not, the band
  quietly does not apply and the price falls back to its usual priors; the
  audit detector will then flag any out-of-band rows, so the defect is loud
  in the report even though generation gave no warning.
- **The band detector only knows declared bands.** `price_band_violation`
  fires solely when a capsule with `price_bands` is attached (via
  `realism.capsule_file` or the bundled registry). Without a capsule, a $500
  jar of honey is not a defect the audit can name, because nothing in the
  schema says what honey costs.

## Statistics

- **Declared rates are subject to integer rounding.** A 2% rate over 4,824
  rows cannot be exactly 2.00% (96 flagged rows gives 1.99%, 97 gives 2.01%).
  Evalpacks drop such questions rather than ship them; plain generation gets
  the closest achievable count. Anchor-month feasibility can be planned (see
  the docs), interpolated months usually cannot.
- **Aggregate targets take precedence over declared per-row bounds.** A period
  target that is infeasible under the column's min/max (`min * rows > target`)
  is met by violating the bound, with a warning before generation. The
  conformance preview surfaces these conflicts; ignoring the warning means
  accepting the violation.
- **Row-count clamps distort marginals silently.** When a period target needs
  more rows than `max_transactions_per_period` allows, per-row values inflate
  to preserve the sum. Every aggregate check still passes while the row-level
  distribution shifts. The builder warns on saturation; the warning is the
  only signal.
- **Group shares need enough rows per bucket.** A `group_shares` declaration
  places at least one row in every positive-share group, so a curve period
  with fewer rows than groups cannot host the split. Such a bucket is skipped
  with a warning and keeps its generated values; the period total still holds,
  the shares inside that period do not. Tiny shares also inherit integer
  effects: 1% of a 40-row month is one row carrying the whole 1% target.
- **No learned correlation structure.** Misata does not fit a copula or a
  neural model to real data. Correlations exist only when declared, inferred
  from the well-known name pairs `smart_correlations` covers, or implied by a
  mechanism (a review score driving its text). Subtle real-world dependence
  (weather and sales, say) will be absent unless you declare it.

## Cross-table stories

- **SCD2 and stock-flow trajectories are generated, not declared.** The
  invariants are exact (versions tile, ledgers chain), but the particular
  version counts, change dates, and stock movements come from seeded draws.
  Evalpacks therefore ship no questions from these identities: their answers
  would be measured from data rather than derived from a declaration, which
  the answer-key-first construction forbids.
- **Segmented waterfalls partition rows, they do not follow row counts you
  chose.** Each tenant's row share follows its declared gross movement, so a
  tiny tenant on a big table still gets few rows. Declare more rows if every
  tenant needs a dense history.

- **Payments are deliberately not forced to equal order totals.** Partial
  payments and installments are real, so `payment.amount == order.total` is
  not enforced or checked. If your story needs exact settlement, declare it.
- **A cancelled order can carry a payment.** Refund flows make this valid, so
  it is not "fixed". Ship dates and tracking numbers are gated on status;
  payments are not.
- **Sibling share columns are detected, never repaired.** Columns like
  `pct_cash`/`pct_card`/`pct_online` that fail to sum to a whole are flagged by
  `story_audit` as advisory findings. Forcing normalisation would corrupt
  columns that were never partitions of the same whole, so we refuse to guess.
- **`story_audit` checks the rules it has.** It is a catalog of named
  invariants grown from real failures, not a semantic understanding of your
  domain. Data can pass the audit and still be wrong in ways no rule covers.
  A clean audit means "no known defect class present", nothing stronger.

## Realism report

- **The realism report detects tells, it does not prove realism.** Each
  check is a threshold heuristic over a known regularity of real data
  (long-tailed money, concentrated popularity, weekly and daily rhythm,
  name-derived emails). A clean report means none of those tells is present,
  not that the data would fool a classifier trained on production. Measuring
  that needs real data (`fidelity_report`).
- **Column roles are guessed from names.** A money column named `bewertung`
  or a timestamp named `when` gets no shape checks. Benford is applied only to
  transaction-style totals, not to prices or salaries, where it does not hold.

## Scale and memory

- **Whole-table passes still buffer their tables.** `generate_stream` takes
  a story, a dict schema, a `SchemaConfig`, a schema file or DDL. A one-hop
  roll-up (`customers.order_count`, `orders.total` from line items) is
  accumulated per parent while the child streams, so only the parent is held:
  3M orders stream with a 66 MB peak, which grows with the stored key pool
  (about 16 bytes per row), not with row width. Multi-hop roll-ups, cascades,
  group shares, lifecycles, composite keys and cross-table clamps still hold
  their tables in memory, and buffered parents arrive after their children's
  batches. `generate_from_schema` builds everything in memory as before.

## Reproducibility and interfaces (anchored mode)

- **Anchored and legacy modes produce different bytes for the same seed.**
  `generation_mode: "anchored"` derives per-site RNG streams, so switching an
  existing schema to anchored regenerates everything once. After that,
  edits are local. Anchored becomes the default at 0.9; pin the mode
  explicitly if the transition matters to you.
- **Edit stability follows the dependency graph, not the diff.** Editing a
  parent's key column legitimately re-rolls its children's foreign keys;
  editing a column that a formula, correlation, or identity reads re-rolls
  those outputs. "Only what you touch changes" means what the edit touches
  semantically, which can be more than the line you edited.
- **Changing a table's row count re-rolls that table.** Streams are anchored
  per site, not per row, so growing a table from 1,000 to 1,100 rows redraws
  the whole table (its columns' streams are consumed at different lengths).
  Row-level extension stability needs counter-based RNG and is not built.
- **A declared aggregate beats causality on the same row.** When a fact-table
  row cannot both postdate its parent and stay in its declared period, the
  period wins, the warning says so, and the story audit reports the row.
  Align the parent's date range with the curve window to avoid the conflict.

## Reproducibility and interfaces

- **Default fan-out assumes repeat customers.** Popularity weighting
  (children-per-parent Gini about 0.55) fits stores and SaaS. Declare the
  domain as `marketplace`, `travel` or `realestate` and person-like parents
  (customers, buyers, guests) get a mild weighting while products stay
  concentrated; declare `min_children: 1` when every customer has ordered at
  least once. The [realism benchmark](docs/realism-benchmark.md) measures this.
- **Default time-of-day rhythms follow the declared domain.** Daytime for most
  businesses; night-heavy for `transport`, `taxi`, `mobility` and `nightlife`;
  evening for `gaming` and `social`. A domain that does not match the activity
  gets the wrong curve: declare the domain, or `hour_weights` on the column.
- **No fare prior for rides.** Taxi and ride totals take the generic money
  shape, which is wider than real fares; declare the distribution.
- **Name-derived emails need a Latin-script name.** A name in another script
  keeps its generated email, which then does not match the name.
- **Determinism is per-version, and cross-platform within a version.** CI
  regenerates a set of schemas on Linux, macOS and Windows and requires
  identical `misata.fingerprint` hashes; floats are hashed to 10 significant
  digits, so a last-bit libm difference does not count, but a value on a
  rounding boundary could. See [STABILITY.md](STABILITY.md) for the
  cross-version contract. The same schema, seed, and misata version
  reproduce byte-identical output. Upgrading may change the RNG stream (it did
  in 0.8.1.29 and 0.8.2): declared outcomes, identities, and integrity
  survive any upgrade, individual rows do not. Pin the version for
  bit-identical regeneration; evalpack manifests record version, seed, and
  spec hash for exactly this purpose.
- **Strict typing is aspirational, not current.** The public API ships type
  hints and a `py.typed` marker, but the codebase does not pass
  `disallow_untyped_defs` today (roughly 500 unannotated internals). The mypy
  configuration reflects what actually holds.
- **LLM-designed schemas inherit the LLM's mistakes.** The parser validates
  structure, semantic inference repairs common mis-typings, and generation is
  deterministic after that point, but a provider that invents a wrong column
  or bad choices produces a wrong (if internally coherent) dataset. Review the
  schema, not just the data.

## How this page is maintained

Every entry here started as a reproduced defect or a deliberate design
refusal. When an entry gets fixed, it moves to the changelog with its
before/after numbers and a test that keeps it fixed. If you hit a failure not
listed here, that is a bug in this page too: please report both.
