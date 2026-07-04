# Misata 0.8.1.7: Crash-proof LLM schemas + clean lookup values

This release hardens the prompt → schema → data pipeline against the small,
inevitable imperfections in any LLM's output. A slightly-off model response no
longer aborts a whole generation — it gets repaired or skipped. It also fixes the
value-quality issues where lookup/dimension columns rendered as person names or
lorem sentences, and adds an AWS Bedrock provider.

## What changed

### Never crash on an imperfect schema

Cross-domain testing found several ways a model's near-miss used to raise and
fail the entire run. Each is now coerced or skipped instead of fatal:

- **Foreign key without a matching relationship** — the most common slip (e.g.
  `sellers.tier_id` with no link to `tiers`). The parser infers the parent table
  from the column name and adds the relationship, or demotes a truly-orphan FK to
  a plain `int` so the schema still validates.
- **Malformed categorical `probabilities`** (mixed ints/strings, wrong length, or
  not summing to 1) are coerced to floats and renormalised, or dropped so the
  engine falls back to a uniform distribution. (Previously crashed on `sum()`.)
- **Out-of-range `outcome_curve` `time_unit`** (e.g. `"quarter"`) is normalised to
  `day` / `week` / `month`; any still-malformed curve is skipped rather than
  failing the whole schema.

### Clean lookup / dimension values (LLM path)

- `domain` / `website` / `*_url` columns now generate URLs (were product
  descriptions).
- A bare `name` is a person only in person tables (users, customers, …); in a
  `plans` / `status` / `type` lookup table it becomes a short label.
- `status` / `type` / `tier` / `category` and `*_name` columns (`batch_name`,
  `block_name`, …) become short labels, not lorem sentences.
- The system prompt is reinforced so lookup tables reliably ship as reference
  tables with real `inline_data` (e.g. Starter / Pro / Enterprise), which the
  engine already honours exactly.

### New: AWS Bedrock provider (Claude via the Converse API)

`LLMSchemaGenerator` gains a `bedrock` provider, ideal as a credit-funded server
default with BYOK still available as an override.

```python
from misata import LLMSchemaGenerator
gen = LLMSchemaGenerator(provider="bedrock")  # uses AWS_REGION + BEDROCK_MODEL_ID
```

Credentials come from the standard AWS chain (env vars / IAM role), the region
from `AWS_REGION`, and the model from `BEDROCK_MODEL_ID`
(default `anthropic.claude-sonnet-4-5-20250929-v1:0`; set a Haiku id for
cheaper/faster). Install with `pip install 'misata[bedrock]'`.

## Install

```bash
pip install misata==0.8.1.7
# with an LLM provider:
pip install 'misata[llm]'        # Groq / OpenAI / Anthropic / Gemini
pip install 'misata[bedrock]'    # Claude on Amazon Bedrock
```

## Model guidance (Groq)

Use `llama-3.3-70b-versatile` on the free tier — it's reliable and returns rich
schemas. Avoid `openai/gpt-oss-120b` on the free tier: it can return
`413 Request too large`. Reserve the larger model for a paid Groq tier.

## Scope, honestly

- The repairs make generation robust to imperfect schemas; they don't invent
  domain knowledge. A lookup table with no `inline_data` gets neutral labels, not
  the exact business values — supply them in the story or the schema for those.
- No schema or public-API changes: the dict schema format and all public
  functions are unchanged. This is a drop-in upgrade.

## Verification

New regression tests cover FK auto-repair (with integrity), probability
coercion/renormalisation, `time_unit` normalisation, and lookup/domain value
quality. The full suite passes (918 tests).

**Full Changelog**: https://github.com/rasinmuhammed/misata/compare/v0.8.1.6...v0.8.1.7
