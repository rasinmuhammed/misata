"""Tests for correlation-aware mimic() and the fidelity_report scorer."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

import misata


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _correlated_frame(n: int = 3000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    age = rng.normal(40, 10, n).clip(18, 80)
    salary = 20000 + age * 1200 + rng.normal(0, 8000, n)   # strong +corr with age
    years_exp = (age - 18) * 0.7 + rng.normal(0, 3, n)     # strong +corr with age
    lucky = rng.uniform(0, 100, n)                          # independent
    return pd.DataFrame({
        "age": age.round(1),
        "salary": salary.round(0),
        "years_exp": years_exp.round(1),
        "lucky": lucky.round(1),
    })


# ---------------------------------------------------------------------------
# Correlation-aware mimic
# ---------------------------------------------------------------------------

def test_mimic_preserves_strong_correlations():
    """The synthetic twin must reproduce the real correlation structure."""
    real = _correlated_frame()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        syn = misata.mimic(real, rows=len(real), seed=42)["table"]

    real_r = real["age"].corr(real["salary"])
    syn_r = syn["age"].corr(syn["salary"])
    assert real_r > 0.7, "fixture sanity: age/salary should be strongly correlated"
    assert abs(syn_r - real_r) < 0.15, (
        f"mimic lost the age/salary correlation: real {real_r:.2f}, synthetic {syn_r:.2f}"
    )


def test_mimic_keeps_independent_columns_independent():
    """An uncorrelated column must not pick up spurious correlation."""
    real = _correlated_frame()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        syn = misata.mimic(real, rows=len(real), seed=42)["table"]

    syn_r = abs(syn["age"].corr(syn["lucky"]))
    assert syn_r < 0.15, f"independent column gained spurious correlation: {syn_r:.2f}"


def test_mimic_profile_emits_correlations():
    """The profiler must attach detected correlations to the Table."""
    from misata.profiler import DataProfiler

    real = _correlated_frame()
    schema = DataProfiler().profile(real, table_name="t")
    corrs = schema.tables[0].correlations
    assert corrs, "profiler emitted no correlations for a correlated frame"
    pairs = {frozenset((c["col_a"], c["col_b"])) for c in corrs}
    assert frozenset(("age", "salary")) in pairs


def test_mimic_no_real_row_leakage():
    """No synthetic row may be an exact copy of a real row."""
    real = _correlated_frame(n=1500)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        syn = misata.mimic(real, rows=len(real), seed=42)["table"]
    leaks = real.merge(syn, how="inner")
    assert len(leaks) == 0, f"{len(leaks)} real rows leaked into the synthetic copy"


# ---------------------------------------------------------------------------
# fidelity_report
# ---------------------------------------------------------------------------

def test_fidelity_identical_data_scores_near_one():
    """A frame compared with itself must score ~1.0 on marginals and correlations."""
    real = _correlated_frame()
    rep = misata.fidelity_report(real, real, ml_efficacy=False)
    assert rep.marginal_score > 0.99
    assert rep.correlation_score is not None and rep.correlation_score > 0.99
    assert rep.overall_score > 0.99


def test_fidelity_detects_marginal_mismatch():
    """A frame with shifted/scaled columns must score lower on marginals."""
    real = _correlated_frame()
    wrong = real.copy()
    wrong["salary"] = wrong["salary"] * 5 + 100000   # very different distribution
    rep = misata.fidelity_report(wrong, real, ml_efficacy=False)
    assert rep.marginal_score < 0.95, "fidelity failed to flag a shifted column"


def test_fidelity_detects_broken_correlations():
    """Shuffling one column destroys joint structure; correlation score must drop."""
    real = _correlated_frame()
    broken = real.copy()
    broken["salary"] = broken["salary"].sample(frac=1.0, random_state=1).values
    rep_good = misata.fidelity_report(real, real, ml_efficacy=False)
    rep_bad = misata.fidelity_report(broken, real, ml_efficacy=False)
    assert rep_bad.correlation_score < rep_good.correlation_score - 0.1


def test_fidelity_mimic_twin_scores_high():
    """End to end: a mimic twin should score well against its source."""
    real = _correlated_frame()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        syn = misata.mimic(real, rows=len(real), seed=42)["table"]
    rep = misata.fidelity_report(syn, real, ml_efficacy=False)
    assert rep.overall_score > 0.85, f"twin fidelity unexpectedly low: {rep.overall_score}"


def test_fidelity_no_target_skips_ml():
    """Without a target column, ml_efficacy must be None."""
    real = _correlated_frame()
    rep = misata.fidelity_report(real, real)
    assert rep.ml_efficacy is None


def test_fidelity_summary_renders():
    """summary() must produce a non-empty string."""
    real = _correlated_frame()
    rep = misata.fidelity_report(real, real, ml_efficacy=False)
    text = rep.summary()
    assert "Overall fidelity" in text and len(text) > 0


@pytest.mark.skipif(
    pytest.importorskip("sklearn", reason="scikit-learn not installed") is None,
    reason="needs scikit-learn",
)
def test_fidelity_ml_efficacy_runs_when_sklearn_present():
    """When sklearn is available, the TSTR path returns a usable ratio."""
    real = _correlated_frame()
    # add a learnable binary target derived from the features
    real = real.copy()
    real["high_earner"] = (real["salary"] > real["salary"].median()).astype(int)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        syn = misata.mimic(real, rows=len(real), seed=42)["table"]
    rep = misata.fidelity_report(syn, real, target_column="high_earner")
    assert rep.ml_efficacy is not None and rep.ml_efficacy.get("available")
    assert 0.0 <= rep.ml_efficacy["efficacy_ratio"] <= 1.0
