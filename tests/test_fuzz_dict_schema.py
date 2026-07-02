"""Property-based fuzzing of the from_dict_schema contract (Hypothesis).

The contract under test: for ANY structurally valid dict schema, the parser
must either parse it faithfully or fail loudly — never silently mis-parse.

Properties:
  P1  Every non-dunder table in the input appears in the SchemaConfig, and
      nothing else does.
  P2  Generation honours requested row counts (no curves involved).
  P3  Declared FK columns never produce orphans.
  P4  Declared numeric bounds hold on every generated row.
  P5  Same seed ⇒ byte-identical output (determinism).
  P6  The envelope format parses to the same tables as the flat format.
"""
import warnings

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

import misata

# ── Strategies ───────────────────────────────────────────────────────────────

_ident = st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True).filter(
    lambda s: not s.startswith("__") and s not in ("tables", "name", "seed",
                                                   "relationships", "constraints", "columns")
)

_numeric_col = st.fixed_dictionaries({
    "type": st.sampled_from(["integer", "float"]),
    "min": st.integers(min_value=0, max_value=50),
    "max": st.integers(min_value=60, max_value=1000),
})

_string_col = st.fixed_dictionaries({
    "type": st.just("string"),
})

_enum_col = st.builds(
    lambda choices: {"type": "categorical", "choices": choices},
    st.lists(st.sampled_from(["alpha", "beta", "gamma", "delta", "epsilon"]),
             min_size=2, max_size=4, unique=True),
)

_col_def = st.one_of(_numeric_col, _string_col, _enum_col)


@st.composite
def flat_schemas(draw):
    """1–3 tables, 1–4 value columns each, plus a PK per table."""
    n_tables = draw(st.integers(1, 3))
    table_names = draw(st.lists(_ident, min_size=n_tables, max_size=n_tables, unique=True))
    schema = {}
    for tname in table_names:
        col_names = draw(st.lists(_ident, min_size=1, max_size=4, unique=True).filter(
            lambda cs: "id" not in cs))
        cols = {"id": {"type": "integer", "primary_key": True}}
        for cn in col_names:
            cols[cn] = draw(_col_def)
        cols["__rows__"] = draw(st.integers(3, 40))
        schema[tname] = cols
    return schema


# ── Properties ───────────────────────────────────────────────────────────────

_SETTINGS = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)


@_SETTINGS
@given(flat_schemas())
def test_p1_tables_preserved(schema_dict):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        config = misata.from_dict_schema(schema_dict, seed=1)
    assert sorted(t.name for t in config.tables) == sorted(schema_dict)


@_SETTINGS
@given(flat_schemas())
def test_p2_row_counts_honoured(schema_dict):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tables = misata.generate_from_schema(misata.from_dict_schema(schema_dict, seed=2))
    for tname, tdef in schema_dict.items():
        assert len(tables[tname]) == tdef["__rows__"], tname


@_SETTINGS
@given(flat_schemas(), st.integers(0, 2**16))
def test_p5_determinism(schema_dict, seed):
    def run():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return misata.generate_from_schema(misata.from_dict_schema(schema_dict, seed=seed))
    a, b = run(), run()
    for k in a:
        pd.testing.assert_frame_equal(a[k], b[k])


@_SETTINGS
@given(flat_schemas())
def test_p4_numeric_bounds_hold(schema_dict):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tables = misata.generate_from_schema(misata.from_dict_schema(schema_dict, seed=3))
    for tname, tdef in schema_dict.items():
        df = tables[tname]
        for cname, cdef in tdef.items():
            if not isinstance(cdef, dict) or cdef.get("type") not in ("integer", "float"):
                continue
            if cdef.get("primary_key"):
                continue
            lo, hi = cdef.get("min"), cdef.get("max")
            vals = pd.to_numeric(df[cname], errors="coerce").dropna()
            if lo is not None:
                assert vals.min() >= lo - 1e-9, f"{tname}.{cname} below min"
            if hi is not None:
                assert vals.max() <= hi + 1e-9, f"{tname}.{cname} above max"


@_SETTINGS
@given(flat_schemas(), st.integers(2, 6))
def test_p3_fk_never_orphans(schema_dict, fanout):
    parent = sorted(schema_dict)[0]
    child_def = {
        "id": {"type": "integer", "primary_key": True},
        "parent_ref": {"type": "integer",
                       "foreign_key": {"table": parent, "column": "id"}},
        "__rows__": schema_dict[parent]["__rows__"] * fanout,
    }
    schema_dict = {**schema_dict, "child_fuzz": child_def}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tables = misata.generate_from_schema(misata.from_dict_schema(schema_dict, seed=4))
    child, par = tables["child_fuzz"], tables[parent]
    orphans = ~child["parent_ref"].isin(par["id"])
    assert int(orphans.sum()) == 0


@_SETTINGS
@given(flat_schemas())
def test_p6_envelope_equivalent_to_flat(schema_dict):
    envelope = {
        "name": "fuzz",
        "tables": {
            tname: {
                "rows": tdef["__rows__"],
                "columns": {c: d for c, d in tdef.items() if not c.startswith("__")},
            }
            for tname, tdef in schema_dict.items()
        },
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        flat_cfg = misata.from_dict_schema(schema_dict, seed=5)
        env_cfg = misata.from_dict_schema(envelope, seed=5)
    assert sorted(t.name for t in env_cfg.tables) == sorted(t.name for t in flat_cfg.tables)
    for t in flat_cfg.tables:
        flat_cols = sorted(c.name for c in flat_cfg.get_columns(t.name))
        env_cols = sorted(c.name for c in env_cfg.get_columns(t.name))
        assert env_cols == flat_cols, t.name
