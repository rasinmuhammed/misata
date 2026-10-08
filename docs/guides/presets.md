# Use-case presets

"Realistic" means different things to different jobs, so name the job:

```python
misata.generate_from_schema(schema, preset="demo")
```

```bash
misata generate --config misata.yaml --preset load
```

or in the schema itself: `preset: ml` in YAML, `"__preset__": "ml"` in a dict.

| Preset | For | What it does |
|---|---|---|
| `demo` | sales demos, dashboards, screenshots | shifts declared date ranges so the latest ends today; coherence repairs on; no deliberate mess |
| `test` | unit and integration tests | caps every table at 200 rows; seed 0 if none is set; no mess |
| `load` | load and performance tests | multiplies row counts (x10; `apply_preset(..., scale=)`); turns expensive coherence passes off; keeps popularity skew |
| `ml` | ML pipelines and feature code | about 3% nulls, 1% outliers, 0.5% typos, 0.2% duplicates, with keys protected; correlations inferred from column names |
| `eval` | agent and text-to-SQL evaluation | `demo` dates plus 2% nulls, typos and duplicates |

A preset only fills in what the schema did not say: a declared `noise` block,
row count or realism setting is kept. `demo` and `eval` leave dates alone when
curves or processes carry their own, because moving the columns without them
would break the declaration. `misata.apply_preset(schema, name)` returns the
adjusted copy if you want to inspect it before generating.
