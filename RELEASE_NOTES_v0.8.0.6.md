v0.8.0.6: Agent-reachable constraints

This is a contract-completeness release. The schema-first path that Studio, MCP agents,
and any non-Python caller use — `from_dict_schema` — can now reach the engine's
constraint and correlation features, and those features are actually enforced during
generation rather than merely declared. The motivating case is AI agents designing
schemas for regulated data (clinical, financial): they need ordering guarantees like
`visit_date >= enrollment_date` and realistic inter-column correlation, expressed as
plain dict directives. 770 tests pass, 0 failures.

## Added

**Constraints and correlations in dict schemas.** `from_dict_schema` accepts two new
table-level directives, matching the `__outcome_curves__` / `__rate_curves__` idiom:

```python
"patients": {
    "__constraints__": [
        {"type": "inequality", "column_a": "visit_date", "operator": ">=",
         "column_b": "enroll_date", "action": "drop"}
    ],
    "__correlations__": [{"col_a": "bmi", "col_b": "systolic_bp", "r": 0.41}],
    # ... columns ...
}
```

`__constraints__` accepts the full set of row-level rules (`inequality`, `col_range`,
`max_per_group`, and the rest). The `name` field the `Constraint` model requires is now
auto-synthesised from the constraint's shape, so dict, YAML, and MCP-agent callers don't
have to invent one. `__correlations__` declares pairwise Pearson targets between numeric
columns, enforced post-generation by the existing Iman-Conover pass that preserves each
column's marginal distribution.

## Fixed

**`inequality` and `col_range` constraints are now enforced during generation.** Both
types were defined on the `Constraint` model, but the simulator's constraint pass only
handled `max_per_group`, `min_per_group`, `sum_limit`, and `unique_combination` — so an
inequality or range rule was silently a no-op through the real generation path. (A
standalone `misata.constraints` toolkit implemented them but was never wired into the
simulator.) They now run in the post-batch pass:

- `inequality` — `column_a <op> column_b` with `action="drop"` to remove violating rows
  or `action="cap"` to snap `column_a` onto `column_b`. It works on **datetime** columns,
  which is the common `visit_date >= enrollment_date` shape the prior toolkit path could
  not handle (its percentage-offset arithmetic only worked on numbers).
- `col_range` — `low_column <= column <= high_column`, clipping the middle column row-wise
  (`cap`) or dropping out-of-range rows (`drop`).

Rows with a null on either side are left untouched; the rules govern fully-populated pairs.

## Notes

This release makes the dict-schema contract a faithful surface over the engine's
constraint layer, which matters most for the MCP server: an AI agent can now declare
regulated-data integrity rules in plain JSON and trust they hold in the generated output.

Full changelog: https://github.com/rasinmuhammed/misata/blob/main/CHANGELOG.md
