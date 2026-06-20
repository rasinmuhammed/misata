"""
Synthetic-vs-real fidelity scoring.

Most synthetic data tools can tell you whether the data they produced matches
the *schema* you declared. They cannot tell you how close it is to a *real*
dataset. This module does exactly that: hand it the synthetic data and the real
data it was meant to resemble, and it returns a single fidelity score plus a
per-column breakdown.

What it measures:

  - **Marginals** — per-column distributional similarity. Numeric columns use
    the two-sample Kolmogorov-Smirnov statistic; categorical columns use total
    variation distance over the category frequencies. Reported as
    ``1 - distance`` so 1.0 is a perfect match.
  - **Correlations** — the difference between the two correlation matrices over
    shared numeric columns. This is the joint-structure check: a twin can match
    every column on its own and still get the relationships between them wrong.
  - **ML efficacy (TSTR)** — optional. Train a model on the synthetic data,
    test it on the real data, and compare against a real-trained baseline. If
    a model learns as well from the synthetic data as from real data, the
    synthetic data carries the same signal. Requires scikit-learn.

Usage::

    import misata
    real = pd.read_csv("customers.csv")
    syn  = misata.mimic(real, rows=len(real))["table"]

    report = misata.fidelity_report(syn, real, target_column="churned")
    print(report.summary())
    print(report.overall_score)   # 0.0 - 1.0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class ColumnFidelity:
    """Per-column distributional similarity (1.0 = identical)."""

    column: str
    kind: str                 # "numeric" | "categorical"
    metric: str               # "ks" | "tvd"
    distance: float           # raw distance (0 = identical)
    similarity: float         # 1 - distance, clipped to [0, 1]


@dataclass
class FidelityReport:
    """Synthetic-vs-real fidelity, overall and per component."""

    columns: List[ColumnFidelity] = field(default_factory=list)
    marginal_score: float = 0.0
    correlation_score: Optional[float] = None
    ml_efficacy: Optional[Dict[str, Any]] = None
    overall_score: float = 0.0

    def summary(self) -> str:
        lines: List[str] = []
        lines.append(f"Overall fidelity: {self.overall_score:.3f}  (1.000 = identical to real)")
        lines.append("")
        lines.append(f"  Marginals (per-column shape) : {self.marginal_score:.3f}")
        if self.correlation_score is not None:
            lines.append(f"  Correlations (joint structure): {self.correlation_score:.3f}")
        if self.ml_efficacy is not None:
            me = self.ml_efficacy
            if me.get("available"):
                lines.append(
                    f"  ML efficacy (TSTR/TRTR)      : {me['efficacy_ratio']:.3f}  "
                    f"(synthetic-trained {me['tstr_score']:.3f} vs real-trained {me['trtr_score']:.3f}, "
                    f"{me['task']} on '{me['target']}')"
                )
            else:
                lines.append(f"  ML efficacy                  : skipped ({me.get('reason')})")
        lines.append("")
        worst = sorted(self.columns, key=lambda c: c.similarity)[:5]
        if worst:
            lines.append("  Lowest-fidelity columns:")
            for c in worst:
                lines.append(f"    {c.column:<24} {c.similarity:.3f}  ({c.metric})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Column-level metrics
# ---------------------------------------------------------------------------

def _numeric_similarity(real: pd.Series, syn: pd.Series) -> ColumnFidelity:
    from scipy.stats import ks_2samp

    r = pd.to_numeric(real, errors="coerce").dropna()
    s = pd.to_numeric(syn, errors="coerce").dropna()
    if len(r) < 2 or len(s) < 2:
        return ColumnFidelity(real.name, "numeric", "ks", 1.0, 0.0)
    stat, _ = ks_2samp(r.values, s.values)
    dist = float(stat)
    return ColumnFidelity(real.name, "numeric", "ks", dist, max(0.0, 1.0 - dist))


def _categorical_similarity(real: pd.Series, syn: pd.Series) -> ColumnFidelity:
    r = real.dropna().astype(str).value_counts(normalize=True)
    s = syn.dropna().astype(str).value_counts(normalize=True)
    cats = r.index.union(s.index)
    r = r.reindex(cats, fill_value=0.0)
    s = s.reindex(cats, fill_value=0.0)
    # Total variation distance: 0.5 * sum|p - q|, in [0, 1].
    tvd = float(0.5 * np.abs(r.values - s.values).sum())
    return ColumnFidelity(real.name, "categorical", "tvd", tvd, max(0.0, 1.0 - tvd))


def _is_numeric_col(real: pd.Series, syn: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(real) and pd.api.types.is_numeric_dtype(syn)


# ---------------------------------------------------------------------------
# Correlation-matrix similarity
# ---------------------------------------------------------------------------

def _correlation_similarity(real: pd.DataFrame, syn: pd.DataFrame, numeric_cols: List[str]) -> Optional[float]:
    cols = [c for c in numeric_cols if c in real.columns and c in syn.columns]
    # Need at least 2 columns with variance in both frames.
    usable = [
        c for c in cols
        if pd.to_numeric(real[c], errors="coerce").std() > 0
        and pd.to_numeric(syn[c], errors="coerce").std() > 0
    ]
    if len(usable) < 2:
        return None

    rc = real[usable].apply(pd.to_numeric, errors="coerce").corr().values
    sc = syn[usable].apply(pd.to_numeric, errors="coerce").corr().values

    # Compare the upper triangle (off-diagonal) only.
    iu = np.triu_indices_from(rc, k=1)
    diffs = np.abs(rc[iu] - sc[iu])
    diffs = diffs[~np.isnan(diffs)]
    if diffs.size == 0:
        return None
    # Pairwise correlations live in [-1, 1]; max possible abs diff is 2.
    mean_abs_diff = float(diffs.mean())
    return max(0.0, 1.0 - mean_abs_diff / 2.0)


# ---------------------------------------------------------------------------
# ML efficacy (train-on-synthetic, test-on-real)
# ---------------------------------------------------------------------------

def _ml_efficacy(
    real: pd.DataFrame,
    syn: pd.DataFrame,
    target_column: str,
) -> Dict[str, Any]:
    try:
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, r2_score
        from sklearn.preprocessing import LabelEncoder
    except ImportError:
        return {"available": False, "reason": "scikit-learn not installed"}

    if target_column not in real.columns or target_column not in syn.columns:
        return {"available": False, "reason": f"target '{target_column}' missing"}

    feature_cols = [c for c in real.columns if c != target_column and c in syn.columns]
    if not feature_cols:
        return {"available": False, "reason": "no shared feature columns"}

    # Decide task type from the real target.
    real_target = real[target_column].dropna()
    is_classification = (
        not pd.api.types.is_numeric_dtype(real_target)
        or real_target.nunique() <= 20
    )

    def _class_labels(series: pd.Series) -> pd.Series:
        """Canonical string labels so numeric 1.0 and 1 collapse to the same class."""
        if pd.api.types.is_numeric_dtype(series):
            num = pd.to_numeric(series, errors="coerce")
            # Integer-valued floats render as ints ("1" not "1.0").
            if (num.dropna() % 1 == 0).all():
                return num.round().astype("Int64").astype(str)
            return num.astype(str)
        return series.astype(str)

    try:
        real_X = pd.get_dummies(real[feature_cols], dummy_na=True)
        syn_X = pd.get_dummies(syn[feature_cols], dummy_na=True)
        # Align one-hot columns across both frames.
        all_cols = real_X.columns.union(syn_X.columns)
        real_X = real_X.reindex(columns=all_cols, fill_value=0)
        syn_X = syn_X.reindex(columns=all_cols, fill_value=0)
        real_y = real[target_column]
        syn_y = syn[target_column]

        # Drop rows with missing target.
        rmask = real_y.notna()
        smask = syn_y.notna()
        real_X, real_y = real_X[rmask.values], real_y[rmask.values]
        syn_X, syn_y = syn_X[smask.values], syn_y[smask.values]

        if len(real_X) < 20 or len(syn_X) < 20:
            return {"available": False, "reason": "too few rows for ML efficacy"}

        if is_classification:
            real_lab = _class_labels(real_y)
            syn_lab = _class_labels(syn_y)
            le = LabelEncoder()
            le.fit(pd.concat([real_lab, syn_lab]))
            real_y_enc = le.transform(real_lab)
            syn_y_enc = le.transform(syn_lab)

            r_tr, r_te, ry_tr, ry_te = train_test_split(
                real_X, real_y_enc, test_size=0.4, random_state=0
            )
            # TRTR baseline: train real, test real.
            base = RandomForestClassifier(n_estimators=80, random_state=0)
            base.fit(r_tr, ry_tr)
            trtr = accuracy_score(ry_te, base.predict(r_te))
            # TSTR: train synthetic, test on the held-out real set.
            synm = RandomForestClassifier(n_estimators=80, random_state=0)
            synm.fit(syn_X, syn_y_enc)
            tstr = accuracy_score(ry_te, synm.predict(r_te))
            task = "classification"
        else:
            real_y_v = pd.to_numeric(real_y, errors="coerce")
            syn_y_v = pd.to_numeric(syn_y, errors="coerce")
            r_tr, r_te, ry_tr, ry_te = train_test_split(
                real_X, real_y_v, test_size=0.4, random_state=0
            )
            base = RandomForestRegressor(n_estimators=80, random_state=0)
            base.fit(r_tr, ry_tr)
            trtr = r2_score(ry_te, base.predict(r_te))
            synm = RandomForestRegressor(n_estimators=80, random_state=0)
            synm.fit(syn_X, syn_y_v)
            tstr = r2_score(ry_te, synm.predict(r_te))
            task = "regression"

        # Efficacy ratio: how much of the real-trained performance the
        # synthetic-trained model recovers. Clipped to [0, 1].
        denom = trtr if abs(trtr) > 1e-6 else 1e-6
        ratio = max(0.0, min(1.0, tstr / denom)) if denom > 0 else 0.0
        return {
            "available": True,
            "task": task,
            "target": target_column,
            "tstr_score": round(float(tstr), 4),
            "trtr_score": round(float(trtr), 4),
            "efficacy_ratio": round(float(ratio), 4),
        }
    except Exception as e:
        return {"available": False, "reason": f"error: {e}"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fidelity_report(
    synthetic: pd.DataFrame,
    real: pd.DataFrame,
    target_column: Optional[str] = None,
    ml_efficacy: bool = True,
) -> FidelityReport:
    """Score how closely *synthetic* matches *real*.

    Parameters
    ----------
    synthetic, real:
        Single-table DataFrames with the same columns. Columns present in only
        one frame are ignored.
    target_column:
        If given (and scikit-learn is installed), runs the train-on-synthetic,
        test-on-real ML efficacy check against this column.
    ml_efficacy:
        Set ``False`` to skip the ML check even when a target is given.

    Returns
    -------
    FidelityReport
        ``.overall_score`` in ``[0, 1]`` plus per-component and per-column detail.
    """
    shared = [c for c in real.columns if c in synthetic.columns]
    columns: List[ColumnFidelity] = []
    numeric_cols: List[str] = []

    for col in shared:
        if _is_numeric_col(real[col], synthetic[col]):
            columns.append(_numeric_similarity(real[col], synthetic[col]))
            numeric_cols.append(col)
        else:
            columns.append(_categorical_similarity(real[col], synthetic[col]))

    marginal_score = float(np.mean([c.similarity for c in columns])) if columns else 0.0
    correlation_score = _correlation_similarity(real, synthetic, numeric_cols)

    ml: Optional[Dict[str, Any]] = None
    if target_column is not None and ml_efficacy:
        ml = _ml_efficacy(real, synthetic, target_column)

    # Overall: marginals always count; correlations and ML efficacy fold in
    # when available. Equal weight across whatever components exist.
    parts = [marginal_score]
    if correlation_score is not None:
        parts.append(correlation_score)
    if ml is not None and ml.get("available"):
        parts.append(ml["efficacy_ratio"])
    overall = float(np.mean(parts))

    return FidelityReport(
        columns=columns,
        marginal_score=round(marginal_score, 4),
        correlation_score=round(correlation_score, 4) if correlation_score is not None else None,
        ml_efficacy=ml,
        overall_score=round(overall, 4),
    )
