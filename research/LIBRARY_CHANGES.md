# Library changes made during the paper work (for your review)

Two edits were made to `misata/llm_parser.py` to support the cross-model E12 experiment and to
fix a reproducible failure class. Both are confined to the LLM-to-schema bridge. They do not
touch the generation engine, the schema model, the validator, or any guarantee the paper
relies on. The engine proposition checks (E1 to E4) and all 51 existing parser tests pass
after the changes.

## 1. OpenAI parameter compatibility for newer models

`LLMSchemaGenerator._call_openai_compatible`

The previous code always sent `max_tokens` and a custom `temperature`. The gpt-5 family and
the o-series reasoning models reject `max_tokens` (they require `max_completion_tokens`) and
only accept the model-default temperature, so the OpenAI path failed on every gpt-5-class
model. The new code tries the legacy form first (preserving the exact behavior for gpt-4o and
the Groq-hosted Llama path), and only on the specific 400 error that names the unsupported
parameter does it retry with `max_completion_tokens` and no custom temperature. An optional
`reasoning_effort` attribute on the generator, when set, is passed through on that modern path;
the E12 runner sets it to keep a one-sentence extraction fast and cheap.

Why it is safe: the legacy path is attempted unchanged, so existing providers behave exactly
as before; the modern path only activates after an explicit unsupported-parameter error. No
model names are hard-coded, so future models that follow the same parameter convention work
without further edits.

## 2. Outcome-curve time_column normalization

`LLMSchemaGenerator._parse_schema` (just before the `SchemaConfig` is returned)

Language models occasionally emit a malformed `time_column` for an outcome curve. Two patterns
recurred across different models in E12: a dotted path such as `order_items.order_id.order_date`
(GPT-5.3, marketplace) and a non-date integer "month" column such as `revenue.month`
(Llama-3.3, gaming). The schema validator rejected both, so an otherwise correct curve was
lost. The new code, for each outcome curve, reduces a dotted pointer to its leaf name, then
points `time_column` at a real date or datetime column in the curve's own table, and coerces
the referenced column to a date type only if the table has no date column to point at. Curves
that already reference a date column are left untouched.

Why it is safe and not overfitting: the normalization is a general repair for two structural
classes of malformed pointer, not a per-domain patch; curves that are already well-formed pass
through unchanged (verified: the 16 domains that already worked were unaffected). A
deterministic, no-API unit test covers both patterns:
`research/specbench/test_timecol_repair.py`.

## What you should decide

- Whether you want these in the shipped library or kept as a research-only patch. Both are
  small and self-contained; the diff is `git diff misata/llm_parser.py`.
- Whether the time_column repair should also live one layer deeper (in the validator or the
  engine) so the declarative path benefits too, not only the LLM path. As written it sits in
  the LLM bridge, which is where LLM output quirks belong, but that is a design call that is
  yours to make.
