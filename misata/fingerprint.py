"""A canonical hash of generated tables, for checking reproducibility.

    fp = misata.fingerprint(tables)
    fp["__all__"]          # one hash for the whole dataset
    fp["orders"]           # one per table

The hash does not depend on file formats, pandas versions or column dtypes
that print the same: every value is written in one canonical text form
(floats to 10 significant digits, timestamps in ISO 8601, nulls as one
token) before hashing, in column order and row order. Two runs that produce
the same data produce the same fingerprint, on any machine.

Floats are rounded so that a last-bit difference in a platform's math
library does not change the hash; a value that sits exactly on a rounding
boundary can still differ, which is rare and shows up as one table's hash
changing, not silently.
"""
from __future__ import annotations

import hashlib
from typing import Dict, Mapping

import numpy as np
import pandas as pd

_NULL = "∅"


def _canon_column(s: pd.Series) -> np.ndarray:
    if pd.api.types.is_bool_dtype(s):
        out = s.map({True: "1", False: "0"})
    elif pd.api.types.is_integer_dtype(s):
        out = s.astype("Int64").astype(str)
    elif pd.api.types.is_float_dtype(s):
        out = s.map(lambda v: _NULL if pd.isna(v) else
                    ("0" if v == 0 else format(float(v), ".10g")))
    elif pd.api.types.is_datetime64_any_dtype(s):
        out = s.map(lambda v: _NULL if pd.isna(v) else v.isoformat())
    else:
        def one(v):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return _NULL
            if isinstance(v, float):
                return format(v, ".10g")
            if isinstance(v, (pd.Timestamp,)):
                return v.isoformat()
            return str(v)
        out = s.map(one)
    return out.fillna(_NULL).astype(str).to_numpy()


def table_fingerprint(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    h.update(("\x1f".join(map(str, df.columns)) + "\n").encode("utf-8"))
    h.update(f"rows={len(df)}\n".encode("utf-8"))
    for col in df.columns:
        vals = _canon_column(df[col])
        h.update(f"col={col}\n".encode("utf-8"))
        h.update("\x1e".join(vals).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()[:16]


def fingerprint(tables: Mapping[str, pd.DataFrame]) -> Dict[str, str]:
    """Per-table and whole-dataset hashes of ``tables``."""
    out = {name: table_fingerprint(tables[name]) for name in sorted(tables)}
    h = hashlib.sha256("".join(f"{k}={v};" for k, v in out.items()).encode("utf-8"))
    out["__all__"] = h.hexdigest()[:16]
    return out
