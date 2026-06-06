"""
Deterministic test for the outcome-curve time_column normalization added to the LLM->schema
bridge (misata/llm_parser.py::_parse_schema). It makes no API call: it feeds two malformed
schema dicts (the exact patterns two different models produced) through the bridge and checks
that the curve's time_column resolves to a real date column, so the schema validates.

  - dotted path  : "orders.customer_id.order_date"  (gpt-5.3 marketplace failure)
  - integer month: "revenue.month" typed int        (llama-3.3 gaming failure)

Run:  PYTHONPATH=. python3 research/specbench/test_timecol_repair.py
"""
from __future__ import annotations
from misata.llm_parser import LLMSchemaGenerator
from misata.validation import validate_schema

gen = LLMSchemaGenerator.__new__(LLMSchemaGenerator)   # no __init__, no client, no API key

DOTTED = {
    "name": "marketplace", "tables": [{"name": "orders", "row_count": 2000}],
    "columns": {"orders": [
        {"name": "amount", "type": "float"},
        {"name": "order_date", "type": "date",
         "distribution_params": {"start": "2024-01-01", "end": "2024-12-31"}}]},
    "outcome_curves": [{"table": "orders", "column": "amount",
        "time_column": "orders.customer_id.order_date", "value_mode": "absolute",
        "curve_points": [{"month": 1, "target_value": 150000},
                         {"month": 12, "target_value": 600000}]}]}

INT_MONTH = {
    "name": "gaming", "tables": [{"name": "revenue", "row_count": 2000}],
    "columns": {"revenue": [
        {"name": "amount", "type": "float"},
        {"name": "month", "type": "int"},
        {"name": "revenue_date", "type": "date",
         "distribution_params": {"start": "2024-01-01", "end": "2024-12-31"}}]},
    "outcome_curves": [{"table": "revenue", "column": "amount", "time_column": "revenue.month",
        "value_mode": "absolute",
        "curve_points": [{"month": 1, "target_value": 60000},
                         {"month": 12, "target_value": 240000}]}]}


def _check(name, d):
    schema = gen._parse_schema(d)
    c = schema.outcome_curves[0]
    types = {col.name: col.type for col in schema.get_columns(c.table)}
    assert types.get(c.time_column) in ("date", "datetime"), \
        f"{name}: time_column '{c.time_column}' is not a date column"
    # validate_schema raises on any issue; isolate the time_column class.
    try:
        validate_schema(schema)
    except Exception as exc:
        assert "time_column" not in str(exc), f"{name}: time_column issue remains: {exc}"
    print(f"PASS  {name:11} time_column -> '{c.time_column}' (type {types[c.time_column]}); validator clean on time_column")


if __name__ == "__main__":
    _check("dotted-path", DOTTED)
    _check("int-month", INT_MONTH)
    print("\nboth malformed patterns repaired deterministically.")
