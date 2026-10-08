"""
Gaussian copula fitted to a sample, in plain NumPy.

Each column is mapped to a standard normal through its own empirical
distribution (numbers and dates through their quantiles, categories through
their frequency intervals), the correlation of those normal scores is
estimated, and new rows are drawn from that multivariate normal and mapped
back. Marginals and pairwise rank correlations are kept; nothing else about
the sample is.

This replaces the SDV-backed generator: SDV is under the Business Source
License, which Misata, as MIT software, should not depend on.

Fitting to real rows is not a privacy guarantee. The marginals are the
sample's own quantiles and categories, so rare values come back as they were.
Use differential privacy for data that must not leak.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Kept so older code that checked for SDV keeps working; the copula no longer
# needs it.
SDV_AVAILABLE = True

_QUANTILES = 512


def _ndtri(p: np.ndarray) -> np.ndarray:
    """Inverse of the standard normal CDF (Acklam's rational approximation,
    relative error under 1.2e-9), so SciPy is not required."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    out = np.empty_like(p)
    lo, hi = p < 0.02425, p > 1 - 0.02425
    mid = ~(lo | hi)
    q = np.sqrt(-2 * np.log(p[lo]))
    out[lo] = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
              ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = np.sqrt(-2 * np.log(1 - p[hi]))
    out[hi] = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p[mid] - 0.5
    r = q * q
    out[mid] = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    return out


def _ndtr(x: np.ndarray) -> np.ndarray:
    """Standard normal CDF."""
    from math import erf, sqrt
    return 0.5 * (1.0 + np.vectorize(erf)(np.asarray(x, dtype=float) / sqrt(2.0)))


class _Column:
    """One column's marginal: how to map it to a normal score and back."""

    def __init__(self, name: str, s: pd.Series):
        self.name = name
        self.null_share = float(s.isna().mean())
        v = s.dropna()
        self.kind = "categorical"
        if pd.api.types.is_bool_dtype(s):
            self.kind = "categorical"
        elif pd.api.types.is_datetime64_any_dtype(s):
            self.kind, self.tz = "datetime", getattr(s.dt, "tz", None)
            v = v.astype("int64")
        elif pd.api.types.is_numeric_dtype(s) and v.nunique() > 12:
            self.kind = "integer" if pd.api.types.is_integer_dtype(s) else "float"
        if self.kind == "categorical":
            vc = v.astype(object).value_counts()
            self.cats = list(vc.index)
            self.cum = np.concatenate([[0.0], np.cumsum(vc.to_numpy(dtype=float)) / max(vc.sum(), 1)])
        else:
            x = v.to_numpy(dtype=float)
            if len(x) == 0:
                x = np.zeros(1)
            self.q = np.quantile(x, np.linspace(0, 1, _QUANTILES))
            self.decimals = 2 if self.kind == "float" and np.allclose(x, np.round(x, 2)) else None

    def to_normal(self, s: pd.Series, rng: np.random.Generator) -> np.ndarray:
        if self.kind == "categorical":
            idx = {c: i for i, c in enumerate(self.cats)}
            codes = s.astype(object).map(idx)
            u = np.full(len(s), np.nan)
            ok = codes.notna().to_numpy()
            k = codes[ok].astype(int).to_numpy()
            # a uniform draw inside the category's interval keeps ties apart
            u[ok] = self.cum[k] + rng.random(ok.sum()) * (self.cum[k + 1] - self.cum[k])
            return np.where(np.isnan(u), np.nan, _ndtri(np.nan_to_num(u, nan=0.5)))
        x = s.astype("int64") if self.kind == "datetime" else s
        x = pd.to_numeric(x, errors="coerce").to_numpy(dtype=float)
        u = np.interp(x, self.q, np.linspace(0, 1, _QUANTILES), left=0.0, right=1.0)
        z = _ndtri(np.clip(u, 0.5 / len(s), 1 - 0.5 / len(s)))
        return np.where(np.isnan(x), np.nan, z)

    def from_normal(self, z: np.ndarray, rng: np.random.Generator) -> pd.Series:
        u = _ndtr(z)
        if self.kind == "categorical":
            k = np.clip(np.searchsorted(self.cum, u, side="right") - 1, 0, len(self.cats) - 1)
            out = pd.Series(np.asarray(self.cats, dtype=object)[k], name=self.name)
        else:
            x = np.interp(u, np.linspace(0, 1, _QUANTILES), self.q)
            if self.kind == "integer":
                out = pd.Series(np.round(x).astype("int64"), name=self.name)
            elif self.kind == "datetime":
                out = pd.Series(pd.to_datetime(x.astype("int64")), name=self.name)
                if self.tz is not None:
                    out = out.dt.tz_localize("UTC").dt.tz_convert(self.tz)
            else:
                out = pd.Series(np.round(x, self.decimals) if self.decimals is not None else x,
                                name=self.name)
        if self.null_share > 0:
            out = out.astype(object) if self.kind in ("integer", "categorical") else out
            out[rng.random(len(out)) < self.null_share] = None
        return out


class CopulaGenerator:
    """
    Gaussian copula over a sample's columns.

    Keeps each column's distribution and the rank correlations between
    columns; mixed types (numbers, categories, dates, nulls) are supported.
    """

    def __init__(self, seed: Optional[int] = None):
        self.seed = seed
        self.columns: List[_Column] = []
        self.corr: Optional[np.ndarray] = None
        self.metadata: Optional[Dict[str, Any]] = None
        self._is_fitted = False

    def fit(self, df: pd.DataFrame, metadata: Optional[Dict] = None) -> None:
        """Learn the marginals and the normal-score correlation of ``df``.

        ``metadata`` may force a column to ``{"sdtype": "categorical"}``."""
        rng = np.random.default_rng(self.seed)
        df = df.copy()
        for col, meta in (metadata or {}).items():
            if col in df and meta.get("sdtype") == "categorical":
                df[col] = df[col].astype(object)
        self.columns = [_Column(c, df[c]) for c in df.columns]
        z = np.column_stack([c.to_normal(df[c.name], rng) for c in self.columns]) if len(self.columns) else np.zeros((len(df), 0))
        if z.shape[1] > 1 and len(df) > 2:
            # pairwise-complete, so missing values do not pull correlations to zero
            corr = pd.DataFrame(z).corr().to_numpy()
            corr = np.nan_to_num(corr, nan=0.0)
            np.fill_diagonal(corr, 1.0)
            # nearest positive-definite matrix, so sampling never fails
            w, v = np.linalg.eigh((corr + corr.T) / 2)
            corr = (v * np.clip(w, 1e-6, None)) @ v.T
            d = np.sqrt(np.diag(corr))
            self.corr = corr / np.outer(d, d)
        else:
            self.corr = np.eye(z.shape[1])
        self.metadata = {c.name: {"sdtype": c.kind} for c in self.columns}
        self._is_fitted = True

    def sample(self, n: int, seed: Optional[int] = None) -> pd.DataFrame:
        """``n`` new rows."""
        if not self._is_fitted:
            raise ValueError("Must call fit() before sample()")
        rng = np.random.default_rng(self.seed if seed is None else seed)
        k = len(self.columns)
        z = rng.standard_normal((n, k)) @ np.linalg.cholesky(self.corr).T if k else np.zeros((n, 0))
        return pd.DataFrame({c.name: c.from_normal(z[:, i], rng) for i, c in enumerate(self.columns)})

    def get_quality_report(self, real: pd.DataFrame, synthetic: pd.DataFrame) -> Dict[str, Any]:
        """Column shapes (1 - KS or 1 - total variation) and pair trends
        (1 - half the absolute difference in rank correlation), averaged."""
        shapes = {}
        for c in self.columns:
            if c.name not in real or c.name not in synthetic:
                continue
            r, s = real[c.name].dropna(), synthetic[c.name].dropna()
            if c.kind == "categorical":
                p = r.astype(object).value_counts(normalize=True)
                q = s.astype(object).value_counts(normalize=True)
                shapes[c.name] = 1 - 0.5 * float(p.subtract(q, fill_value=0).abs().sum())
            else:
                a = np.sort(pd.to_numeric(r.astype("int64") if c.kind == "datetime" else r, errors="coerce").dropna().to_numpy(float))
                b = np.sort(pd.to_numeric(s.astype("int64") if c.kind == "datetime" else s, errors="coerce").dropna().to_numpy(float))
                if len(a) and len(b):
                    grid = np.concatenate([a, b])
                    ks = np.max(np.abs(np.searchsorted(a, grid, side="right") / len(a)
                                       - np.searchsorted(b, grid, side="right") / len(b)))
                    shapes[c.name] = 1 - float(ks)
        num = [c.name for c in self.columns if c.kind in ("integer", "float")]
        pairs = {}
        if len(num) > 1:
            rc = real[num].rank().corr().to_numpy()
            sc = synthetic[num].rank().corr().to_numpy()
            for i in range(len(num)):
                for j in range(i + 1, len(num)):
                    if np.isfinite(rc[i, j]) and np.isfinite(sc[i, j]):
                        pairs[(num[i], num[j])] = 1 - abs(rc[i, j] - sc[i, j]) / 2
        parts = [np.mean(list(shapes.values()))] if shapes else []
        if pairs:
            parts.append(np.mean(list(pairs.values())))
        return {"overall_score": float(np.mean(parts)) if parts else float("nan"),
                "column_shapes": shapes, "column_pair_trends": pairs}


class ConstraintAwareCopulaGenerator(CopulaGenerator):
    """Copula generator that can rescale a value column by monthly targets."""

    def sample_with_constraints(
        self,
        n: int,
        outcome_curves: Optional[List[Dict]] = None,
        date_column: Optional[str] = None,
        value_column: Optional[str] = None,
    ) -> pd.DataFrame:
        df = self.sample(n)
        if not outcome_curves or not date_column or not value_column:
            return df
        if date_column not in df.columns or value_column not in df.columns:
            return df
        for curve in outcome_curves:
            df = self._apply_curve(df, curve, date_column, value_column)
        return df

    def _apply_curve(self, df: pd.DataFrame, curve: Dict, date_column: str,
                     value_column: str) -> pd.DataFrame:
        points = curve.get("curve_points", [])
        if not points:
            return df
        if not pd.api.types.is_datetime64_any_dtype(df[date_column]):
            df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
        targets = {}
        for p in points:
            month = p.get("month") if isinstance(p, dict) else getattr(p, "month", None)
            value = p.get("relative_value") if isinstance(p, dict) else getattr(p, "relative_value", None)
            if month and value:
                targets[month] = value
        for month, relative in targets.items():
            mask = df[date_column].dt.month == month
            if mask.any() and df.loc[mask, value_column].mean() > 0:
                df.loc[mask, value_column] = df.loc[mask, value_column] * relative
        return df


def create_copula_generator(with_constraints: bool = True, seed: Optional[int] = None) -> CopulaGenerator:
    """Create a copula generator instance."""
    if with_constraints:
        return ConstraintAwareCopulaGenerator(seed=seed)
    return CopulaGenerator(seed=seed)
