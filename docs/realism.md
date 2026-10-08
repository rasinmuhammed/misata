# Realism report: find the tells of generated data

`misata audit` catches contradictions: orders shipped before they were placed,
ages that disagree with birth dates. Data can pass every one of those checks
and still look fake to anyone who has worked with a production table, because
its *shapes* are wrong. `realism_report` looks for those shapes. It needs no
real data to compare against, and it works on data from any generator: a
Faker script, SDV, Mockaroo, or Misata.

```python
import misata

tables = misata.generate("An ecommerce store with 2000 customers and 10000 orders")
report = misata.realism_report(tables)
print(report.summary())
report.passed   # False if any check failed outright
report.score    # 0.0 - 1.0: pass = 1, warn = 0.5, fail = 0
```

```bash
misata realism ./seed_data/                 # exit 1 on any failure
misata realism ./seed_data/ --strict        # exit 1 on warnings too
misata realism ./seed_data/ --skip too_clean --json
```

## The checks

| Check | Applies to | Tell | Status |
|---|---|---|---|
| `amount_shape` | money-named numeric columns | values spread evenly from min to max; or a thin tail (skew < 0.5, p99 < 2x median) | fail / warn |
| `benford` | transaction totals spanning 2+ orders of magnitude, 500+ rows | first-digit MAD above 0.015 (Nigrini's threshold) | warn |
| `fanout_skew` | every FK (from the schema, or `<entity>_id` matched by name) | children per parent too even: Gini < 0.25 fails, < 0.4 warns | fail / warn |
| `category_balance` | 3-30 category columns, 300+ rows | shares statistically indistinguishable from uniform | warn |
| `weekday_rhythm` | activity timestamps spanning 4+ weeks | every weekday equally busy | warn |
| `daily_rhythm` | timestamps with a time of day | over 10% exactly at midnight (fail); flat hours, or a peak between 00:00 and 05:59 (warn) | fail / warn |
| `placeholder_values` | text columns | `@example.com`, John Doe, Acme, lorem ipsum, `test1` | fail above 1%, warn below |
| `email_domains` | consumer email columns | providers evenly shared | warn |
| `name_email` | tables with an email and a name | email local part unrelated to the name: < 20% fail, < 50% warn | fail / warn |
| `value_diversity` | name, product, company and title columns | fewer than 20% distinct values | warn |
| `text_templates` | free-text columns, 200+ rows | > 20% exact duplicates; > 50% open with one of ten three-word openings; for texts of 8+ words, > 35% repeat another's sentence skeleton, or > 5% are near-copies | warn |
| `text_diversity` | free-text columns, 200+ rows | gzip ratio > 4; < 40% of word trigrams distinct; length CV < 0.15 (8+ words); Zipf slope flatter than -0.5 (10+ words) | warn |
| `text_context` | a rating with review text, or a title with a body | review tone uncorrelated with the rating (Spearman < 0.1); body shares no more words with its own title than with a random row's (< 1.5x) | warn |
| `too_clean` | tables with 5+ non-key columns | not a single null | warn |

Each check runs only when the table is big enough for the statistic to mean
something, so a five-row fixture gets a short report. Every finding carries
its evidence (`report.to_dict()`): the Gini, the chi-square p-value, the hour
histogram, the examples that matched.

### The free-text checks

"Free text" means prose columns: names such as `description`, `review_text`,
`subject`, `notes`, `bio`, or any text column whose values have a median of
five words or more. Emails, addresses, names, companies, codes and log or
error columns are left out; real system logs are legitimately templated.

The thresholds come from a local calibration on seven real English corpora
(product and hotel reviews, news, tweets, forum posts and titles), 2,000 rows
each. Every real corpus compressed under 3x, had over 70% distinct word
trigrams, under 16% repeated skeletons, under 0.2% near-copies, a length CV
over 0.29 and a top-10 opener share under 0.28. Template text sits 5x to 50x
outside those bands, and each threshold sits well inside that gap.

A *skeleton* is the text with numbers masked to `#`, emails to `@E` and
every word that is not a stopword to `W`. "The kettle arrived on time" and
"The lamp arrived on time" share one; people almost never write the same
skeleton twice at sentence length, while slot-filling templates do on every
row.

These checks are strict. Misata's own text passes the repetition and context
checks for every kind, and `text_diversity` for every kind except chief
complaints (gzip about 4.2x at 2,000 rows): seven-word triage fragments,
which real triage text does not beat either; see [LIMITATIONS](https://github.com/rasinmuhammed/misata/blob/main/LIMITATIONS.md).
Skip `text_diversity` when the vocabulary does not matter to you, for example
in UI fixtures.

## What a clean report means

Each threshold is a heuristic chosen to flag shapes real data almost never
has. A clean report means none of the known tells is present. It does not
mean the data is indistinguishable from production; for that you need real
data to compare against (`misata.fidelity_report`).

Some tells are legitimate in context. A randomized A/B assignment *is*
balanced (columns named `variant`, `group`, `arm`, `cohort` and similar are
exempt), a nightly batch job *does* run at midnight, and a pristine demo
table may be exactly what you want. Skip what does not apply:

```python
misata.realism_report(tables, skip=["too_clean", "daily_rhythm"])
```
