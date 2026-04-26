"""
CSV/DataFrame profiler — infers column distributions and generates a
matching SchemaConfig so Misata can produce privacy-safe synthetic twins.

Usage::

    from misata import mimic
    tables = mimic("customers.csv", rows=50_000)

    # or multi-table from a folder
    tables = mimic(["orders.csv", "customers.csv"], rows=10_000)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from misata.schema import Column, SchemaConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE   = re.compile(r"^https?://")
_PHONE_RE = re.compile(r"^[\+\d\(\)\-\s\.]{7,20}$")

_NAME_HINTS    = {"name", "first_name", "last_name", "full_name", "fname", "lname"}
_EMAIL_HINTS   = {"email", "email_address", "e_mail"}
_PHONE_HINTS   = {"phone", "mobile", "cell", "telephone", "contact"}
_CITY_HINTS    = {"city", "town", "municipality"}
_STATE_HINTS   = {"state", "province", "region"}
_COUNTRY_HINTS = {"country", "nation", "country_code"}
_USERNAME_HINTS = {"username", "user_name", "handle", "screen_name", "login"}
_COMPANY_HINTS = {"company", "organization", "employer", "brand", "firm"}
_LAT_HINTS     = {"lat", "latitude"}
_LON_HINTS     = {"lon", "lng", "longitude"}
_ZIP_HINTS     = {"zip", "postal", "postcode", "zip_code", "postal_code"}


def _sample_non_null(series: pd.Series, n: int = 200) -> pd.Series:
    s = series.dropna()
    return s.sample(min(n, len(s))) if len(s) > 0 else s


def _is_email(series: pd.Series) -> bool:
    sample = _sample_non_null(series.astype(str))
    if len(sample) == 0:
        return False
    return (sample.str.match(_EMAIL_RE)).mean() > 0.8


def _is_url(series: pd.Series) -> bool:
    sample = _sample_non_null(series.astype(str))
    return len(sample) > 0 and (sample.str.match(_URL_RE)).mean() > 0.7


def _is_phone(series: pd.Series) -> bool:
    sample = _sample_non_null(series.astype(str))
    return len(sample) > 0 and (sample.str.match(_PHONE_RE)).mean() > 0.7


def _detect_text_semantic(col_name: str, series: pd.Series) -> str:
    name = col_name.lower().strip()
    if name in _EMAIL_HINTS or _is_email(series):
        return "email"
    if name in _USERNAME_HINTS:
        return "username"
    if name in _COMPANY_HINTS:
        return "company"
    if name in _NAME_HINTS or "name" in name:
        return "name"
    if name in _CITY_HINTS:
        return "city"
    if name in _STATE_HINTS:
        return "state"
    if name in _COUNTRY_HINTS:
        return "country"
    if name in _LAT_HINTS:
        return "latitude"
    if name in _LON_HINTS:
        return "longitude"
    if name in _ZIP_HINTS:
        return "postal_code"
    if _is_url(series):
        return "url"
    if _is_phone(series):
        return "phone"
    return "description"


def _fit_numeric(series: pd.Series, is_int: bool) -> Dict[str, Any]:
    s = series.dropna().astype(float)
    if len(s) == 0:
        return {"distribution": "uniform", "min": 0, "max": 100}

    mn, mx = float(s.min()), float(s.max())
    mean, std = float(s.mean()), float(s.std())

    # Choose distribution: lognormal if all-positive and right-skewed
    if mn > 0 and s.skew() > 1.0:
        log_s = np.log(s)
        mu    = float(log_s.mean())
        sigma = float(log_s.std())
        params: Dict[str, Any] = {
            "distribution": "lognormal",
            "mu": round(mu, 4),
            "sigma": round(max(sigma, 0.01), 4),
            "min": round(mn, 4),
            "max": round(mx, 4),
        }
    elif std < 0.01:
        # Constant column — just use uniform with tiny range
        params = {"distribution": "uniform", "min": round(mn, 4), "max": round(max(mx, mn + 1), 4)}
    else:
        params = {
            "distribution": "normal",
            "mean": round(mean, 4),
            "std": round(std, 4),
            "min": round(mn, 4),
            "max": round(mx, 4),
        }

    if is_int:
        params["decimals"] = 0
        params["min"] = int(params["min"])
        params["max"] = int(params["max"])
    else:
        decimals = _infer_decimals(s)
        params["decimals"] = decimals
    return params


def _infer_decimals(s: pd.Series) -> int:
    sample = s.dropna().head(100).astype(str)
    dots = sample[sample.str.contains(r"\.", regex=False)]
    if dots.empty:
        return 0
    return int(dots.str.split(".").str[1].str.len().median())


def _fit_categorical(series: pd.Series) -> Dict[str, Any]:
    counts = series.dropna().value_counts(normalize=True)
    choices = [str(c) for c in counts.index.tolist()[:50]]
    probs   = counts.values[:50].tolist()
    # Re-normalize in case we truncated
    total = sum(probs)
    probs = [round(p / total, 6) for p in probs]
    return {"choices": choices, "probabilities": probs}


def _fit_date(series: pd.Series) -> Dict[str, Any]:
    s = pd.to_datetime(series, errors="coerce").dropna()
    if len(s) == 0:
        return {"start": "2020-01-01", "end": "2024-12-31"}
    return {
        "start": s.min().strftime("%Y-%m-%d"),
        "end":   s.max().strftime("%Y-%m-%d"),
    }


def _is_date_col(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    sample = _sample_non_null(series.astype(str), 50)
    if len(sample) == 0:
        return False
    parsed = pd.to_datetime(sample, errors="coerce")
    return parsed.notna().mean() > 0.7


def _cardinality_ratio(series: pd.Series) -> float:
    n = len(series.dropna())
    return series.nunique() / n if n > 0 else 1.0


# ---------------------------------------------------------------------------
# Core profiler
# ---------------------------------------------------------------------------

class DataProfiler:
    """
    Analyzes a DataFrame and produces a Misata ``SchemaConfig`` that mirrors
    its statistical properties — without retaining any real values.

    The profiler:
    - Detects column types (numeric, categorical, date, boolean, text)
    - Fits the best distribution for each numeric column
    - Captures category frequencies for low-cardinality columns
    - Infers date ranges
    - Detects semantic types for text (email, name, city, …)
    """

    # Columns with cardinality below this fraction are treated as categorical
    CATEGORICAL_RATIO = 0.05
    # Absolute cardinality ceiling before switching to text
    CATEGORICAL_MAX   = 200

    def profile(self, df: pd.DataFrame, table_name: str = "table") -> "SchemaConfig":
        """Return a SchemaConfig that statistically mirrors *df*."""
        from misata.schema import Column, Table, SchemaConfig

        columns: List[Column] = []
        for col_name in df.columns:
            series = df[col_name]
            col_def = self._profile_column(col_name, series)
            columns.append(col_def)

        return SchemaConfig(
            name=f"{table_name} (mimic)",
            description=f"Synthetic twin of {table_name} — {len(df)} source rows",
            domain="generic",
            tables=[Table(name=table_name, row_count=len(df))],
            columns={table_name: columns},
            relationships=[],
            events=[],
        )

    def _profile_column(self, col_name: str, series: pd.Series) -> "Column":
        from misata.schema import Column

        null_rate = series.isna().mean()
        params: Dict[str, Any] = {}

        # --- boolean ---
        if pd.api.types.is_bool_dtype(series):
            p = float(series.dropna().mean())
            return Column(name=col_name, type="boolean",
                          distribution_params={"probability": round(p, 4)})

        non_null = series.dropna()

        # --- date ---
        if _is_date_col(series):
            params = _fit_date(series)
            col = Column(name=col_name, type="date", distribution_params=params)
            return col

        # --- numeric ---
        if pd.api.types.is_numeric_dtype(series):
            is_int = pd.api.types.is_integer_dtype(series) or (
                non_null.dropna().apply(lambda x: x == int(x)).all()
                if len(non_null) > 0 else False
            )
            n_unique = series.nunique()
            ratio = _cardinality_ratio(series)

            # Low-cardinality numeric → categorical
            if n_unique <= 20 and ratio < self.CATEGORICAL_RATIO:
                params = _fit_categorical(series)
                params["choices"] = [int(c) if is_int else float(c) for c in params["choices"]]
                col_type = "int" if is_int else "float"
                col = Column(name=col_name, type=col_type, distribution_params=params)
            else:
                params = _fit_numeric(series, is_int)
                col_type = "int" if is_int else "float"
                col = Column(name=col_name, type=col_type, distribution_params=params)
            return col

        # --- text / object ---
        series_str = series.astype(str)
        n_unique = series.nunique()
        ratio = _cardinality_ratio(series)

        # Low-cardinality string → categorical
        if n_unique <= self.CATEGORICAL_MAX and ratio < self.CATEGORICAL_RATIO:
            params = _fit_categorical(series)
            col = Column(name=col_name, type="categorical", distribution_params=params)
        else:
            # High-cardinality text — detect semantic type
            semantic = _detect_text_semantic(col_name, series_str)
            params = {"text_type": semantic}
            col = Column(name=col_name, type="text", distribution_params=params)

        if null_rate > 0.005:
            params["null_rate"] = round(float(null_rate), 4)

        return col


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def mimic(
    source: Union[str, Path, pd.DataFrame, List[Union[str, Path, pd.DataFrame]]],
    rows: Optional[int] = None,
    seed: Optional[int] = None,
    table_name: str = "table",
) -> Dict[str, pd.DataFrame]:
    """
    Generate a privacy-safe synthetic twin of a CSV file or DataFrame.

    Misata analyzes every column's statistical fingerprint — distribution
    shape, cardinality, value range, semantic type — and produces a fresh
    dataset that matches the original's structure without reusing any real
    values.

    Parameters
    ----------
    source:
        A CSV path, ``pd.DataFrame``, or a list of either for multi-table
        mimicry.  For a list, each item becomes its own table; table names
        are inferred from file names or ``"table_0"``, ``"table_1"``, etc.
    rows:
        How many rows to generate.  Defaults to the same count as the source.
    seed:
        Random seed for reproducibility.
    table_name:
        Table name used when *source* is a single DataFrame (not a path).

    Returns
    -------
    Dict[str, pd.DataFrame]
        One DataFrame per table, keyed by table name.

    Examples
    --------
    Basic usage::

        import misata
        tables = misata.mimic("customers.csv")

    Scale up to 100 k rows::

        tables = misata.mimic("customers.csv", rows=100_000)

    Mimic a DataFrame you already have in memory::

        import pandas as pd
        df = pd.read_csv("orders.csv")
        synthetic = misata.mimic(df, rows=50_000)

    Multi-table — keeps relationships implicit::

        tables = misata.mimic(["customers.csv", "orders.csv"])
        # tables["customers"], tables["orders"]
    """
    from misata.simulator import DataSimulator

    profiler = DataProfiler()

    # Normalise input to list of (name, DataFrame)
    sources: List[tuple[str, pd.DataFrame]] = []
    if isinstance(source, (str, Path)):
        p = Path(source)
        sources = [(p.stem, pd.read_csv(p))]
    elif isinstance(source, pd.DataFrame):
        sources = [(table_name, source)]
    elif isinstance(source, list):
        for idx, item in enumerate(source):
            if isinstance(item, (str, Path)):
                p = Path(item)
                sources.append((p.stem, pd.read_csv(p)))
            elif isinstance(item, pd.DataFrame):
                sources.append((f"table_{idx}", item))
            else:
                raise TypeError(f"Unsupported source type: {type(item)}")
    else:
        raise TypeError(f"Unsupported source type: {type(source)}")

    results: Dict[str, pd.DataFrame] = {}
    for tname, df in sources:
        n_rows = rows if rows is not None else len(df)
        schema = profiler.profile(df, table_name=tname)
        # Override row count
        from misata.schema import Table
        object.__setattr__(schema, "tables", [Table(name=tname, row_count=n_rows)])
        sim = DataSimulator(schema)
        if seed is not None:
            sim.rng = np.random.default_rng(seed)
        for out_name, out_df in sim.generate_all():
            results[out_name] = out_df

    return results
