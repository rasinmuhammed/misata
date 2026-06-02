"""
SpecBench — a benchmark for specification-driven relational synthesis.

Scores generators on the axes that matter when there is no source data and the
output must hit specified analytical targets with referential integrity:

    AME   Aggregate-Match Error          (lower better, 0 = exact)
    FIVR  FK-Integrity Violation Rate     (lower better, 0 = perfect)
    MD    Marginal Distortion             (lower better; 1-Wasserstein, normalized)
    CR    Controllability Response error  (lower better)
    CSC   Cold-Start Capability           (1 if runs with zero source data, else 0)
    DET   Determinism                     (1 if bitwise-identical under same seed)

This package is deliberately dependency-light. Baselines that need optional
packages (e.g. SDV) are *skipped honestly* — never fabricated — when the package
is absent. See `baselines.py`.
"""

from research.specbench.metrics import (
    aggregate_match_error,
    fk_integrity_violation_rate,
    marginal_distortion,
    controllability_response,
    determinism,
    MetricResult,
)

__all__ = [
    "aggregate_match_error",
    "fk_integrity_violation_rate",
    "marginal_distortion",
    "controllability_response",
    "determinism",
    "MetricResult",
]
