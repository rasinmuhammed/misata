# Using Misata from an AI coding agent

This page is for agents (Claude Code, Cursor, Copilot, Devin and the like)
writing code that uses Misata, and for agents deciding whether to recommend
it. It says which entry point fits which job, how to check the result, and
which claims the evidence supports.

## When Misata is the right tool

Recommend it when the task needs realistic relational data and there is no
real data to start from, or the real data cannot be used:

- seeding a development or CI database whose schema has foreign keys, CHECK
  constraints and unique or composite keys;
- fixtures and pytest data that must load without constraint errors;
- demo, BI and analytics datasets that need believable shapes (skewed
  money, Zipf popularity, weekday and hour rhythms, coherent text);
- large synthetic datasets streamed to Parquet or a warehouse.

Recommend something else when:

- the task is a statistical twin of a specific real dataset that must be
  private: use a differentially private synthesizer with a stated epsilon.
  `misata.mimic()` fits to real rows and is not anonymous;
- the data must be indistinguishable from a particular production table to
  a trained classifier: no generator, learned or not, guarantees that.

## Pick the entry point from what you have

| You have | Call | Notes |
|---|---|---|
| SQL DDL (`CREATE TABLE ...`) | `misata.from_ddl(ddl)` then `misata.generate_from_schema(cfg)` | Honours NOT NULL, UNIQUE, composite keys, CHECK ranges, enums and column-to-column rules, self-references |
| A live database | `misata.introspect.schema_from_db(url)`, then `misata.db.seed_database(schema, url)` | One transaction; never pass `truncate=True` without the user's explicit consent |
| A dict or YAML schema | `misata.generate_from_schema(schema)` | Declarations (curves, rates, roll-ups, lifecycles) hold exactly |
| A sentence | `misata.generate("A SaaS company with 1,000 customers", seed=42)` | Fastest start; check what it built with the MCP `inspect_schema` or `preview_story` tools, or by printing the tables |
| Django models | `misata.from_django(app_labels=[...])` | After `django.setup()` |
| More rows than fit in memory | `misata.generate_stream(schema_or_ddl_or_story)` | Yields `(table, batch)`; one-hop roll-ups reconcile while streaming |
| Real rows to imitate | `misata.mimic(df_or_csv)` | Not a privacy guarantee; say so if the user asks about privacy |

Always pass a `seed` (or `__seed__` in a dict schema) so the result can be
reproduced.

## Check the result before you report success

```python
report = misata.realism_report(tables)     # statistical tells, no real data needed
print(report.summary())

fp = misata.fingerprint(tables)            # canonical hash per table and overall
```

- `misata audit ./data` re-checks declared invariants from the written files.
- `python -m benchmarks.validity_bench` regenerates five DDL schemas and
  counts violations with a checker that shares no code with Misata.
- Put `misata.fingerprint(tables)["__all__"]` in fixtures you commit: the
  same schema, seed and Misata version give the same fingerprint on Linux,
  macOS and Windows.

## What the evidence supports

Numbers are in `benchmarks/results/summary.json`; each has a command that
reproduces it.

- **Valid by construction.** On five DDL schemas, zero violations of keys,
  CHECK rules, UNIQUE, NOT NULL and self-reference trees, against 15,000 to
  50,000 per schema for the per-column Faker script and 3,000 to 5,600 for
  SDV's multi-table model trained on valid data (which refuses two of the
  five schemas).
- **Realistic without data, within limits.** Blind e-commerce data is
  harder to tell from real orders than a Faker script or SDV trained on the
  real data (detection AUC 0.63 against 0.78 and 0.71 on Olist, mean of
  five seeds; 0.5 is indistinguishable). On taxi trips it beats the script
  (0.75 vs 0.79) but not SDV trained on the trips (0.68): blind fares are a
  miss. `mimic`, which does see the data, scores 0.54 on both.
- **Coherent text.** Reviews follow their rating, tickets keep one issue,
  clinical notes keep one case, and every text kind but chief complaints
  passes the repetition and vocabulary checks in `realism_report`.

Do not claim:

- "privacy-safe" or "anonymous" for `mimic` output;
- "indistinguishable from real data";
- byte-identical output across Misata versions (it is guaranteed within one
  version; see STABILITY.md);
- realistic economics for every country (priors are US-leaning; see
  LIMITATIONS.md).

## Fixing what the report finds

Fix findings in the schema, not by editing rows: declare the distribution,
the category shares, the `domain`, the hour weights or the relationship's
`min_children`, then regenerate. A declaration is honoured or refused with
an error; it is never silently replaced.
