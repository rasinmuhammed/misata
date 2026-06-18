"""Domain-aware validation pass.

Runs after generation to surface out-of-domain values without modifying data.
Integrated via ``__domain__: clinical_trial`` or ``__domain__: financial`` in
the dict schema, or called directly on a DataFrames dict.

Returns a ``ValidationReport`` with per-table, per-column findings. Severity
levels: WARNING (plausible but unusual), ERROR (physiologically/financially
impossible).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Domain range registries
# ---------------------------------------------------------------------------

_CLINICAL_RANGES: Dict[str, Dict[str, Any]] = {
    # column_name_fragment → {min, max, unit, severity}
    "hba1c":         {"min": 4.0,   "max": 14.0,  "unit": "%",       "severity": "ERROR"},
    "glucose":       {"min": 2.0,   "max": 40.0,  "unit": "mmol/L",  "severity": "ERROR"},
    "systolic_bp":   {"min": 60.0,  "max": 260.0, "unit": "mmHg",    "severity": "ERROR"},
    "diastolic_bp":  {"min": 30.0,  "max": 160.0, "unit": "mmHg",    "severity": "ERROR"},
    "bmi":           {"min": 10.0,  "max": 80.0,  "unit": "kg/m²",   "severity": "ERROR"},
    "age":           {"min": 0.0,   "max": 130.0, "unit": "years",   "severity": "ERROR"},
    "heart_rate":    {"min": 20.0,  "max": 300.0, "unit": "bpm",     "severity": "ERROR"},
    "temperature":   {"min": 30.0,  "max": 45.0,  "unit": "°C",      "severity": "ERROR"},
    "weight":        {"min": 0.5,   "max": 500.0, "unit": "kg",      "severity": "WARNING"},
    "height":        {"min": 30.0,  "max": 250.0, "unit": "cm",      "severity": "WARNING"},
    "creatinine":    {"min": 0.3,   "max": 20.0,  "unit": "mg/dL",   "severity": "ERROR"},
    "cholesterol":   {"min": 1.0,   "max": 20.0,  "unit": "mmol/L",  "severity": "WARNING"},
    "hemoglobin":    {"min": 3.0,   "max": 25.0,  "unit": "g/dL",    "severity": "ERROR"},
    "platelet":      {"min": 1.0,   "max": 2000.0,"unit": "10⁹/L",   "severity": "WARNING"},
    "alt":           {"min": 0.0,   "max": 5000.0,"unit": "U/L",     "severity": "WARNING"},
    "ast":           {"min": 0.0,   "max": 5000.0,"unit": "U/L",     "severity": "WARNING"},
}

_FINANCIAL_RANGES: Dict[str, Dict[str, Any]] = {
    "amount":        {"min": -1e9,  "max": 1e12,  "unit": "currency","severity": "WARNING"},
    "price":         {"min": 0.0,   "max": 1e9,   "unit": "currency","severity": "WARNING"},
    "revenue":       {"min": 0.0,   "max": 1e12,  "unit": "currency","severity": "WARNING"},
    "salary":        {"min": 0.0,   "max": 1e9,   "unit": "currency","severity": "WARNING"},
    "rate":          {"min": -1.0,  "max": 100.0, "unit": "%",       "severity": "WARNING"},
    "discount":      {"min": 0.0,   "max": 1.0,   "unit": "fraction","severity": "WARNING"},
    "quantity":      {"min": 0.0,   "max": 1e9,   "unit": "units",   "severity": "WARNING"},
    "score":         {"min": 0.0,   "max": 1000.0,"unit": "score",   "severity": "WARNING"},
}

_DOMAIN_REGISTRY: Dict[str, Dict[str, Dict[str, Any]]] = {
    "clinical_trial": _CLINICAL_RANGES,
    "clinical":       _CLINICAL_RANGES,
    "financial":      _FINANCIAL_RANGES,
    "fintech":        _FINANCIAL_RANGES,
}


# ---------------------------------------------------------------------------
# Report data classes
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    table: str
    column: str
    severity: str          # "WARNING" | "ERROR"
    message: str
    violating_count: int
    total_count: int

    @property
    def violation_rate(self) -> float:
        return self.violating_count / max(self.total_count, 1)

    def __str__(self) -> str:
        pct = f"{self.violation_rate:.1%}"
        return (
            f"[{self.severity}] {self.table}.{self.column}: "
            f"{self.violating_count}/{self.total_count} rows ({pct}) — {self.message}"
        )


@dataclass
class ValidationReport:
    domain: str
    findings: List[Finding] = field(default_factory=list)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "ERROR"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "WARNING"]

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        if not self.findings:
            return f"Domain validation ({self.domain}): all checks passed."
        lines = [f"Domain validation ({self.domain}): {len(self.errors)} errors, {len(self.warnings)} warnings."]
        for f in self.findings:
            lines.append(f"  {f}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "passed": self.passed,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [
                {
                    "table": f.table, "column": f.column,
                    "severity": f.severity, "message": f.message,
                    "violating_count": f.violating_count,
                    "total_count": f.total_count,
                    "violation_rate": round(f.violation_rate, 4),
                }
                for f in self.findings
            ],
        }


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate(
    tables: Dict[str, pd.DataFrame],
    domain: str,
    custom_ranges: Optional[Dict[str, Dict[str, Any]]] = None,
) -> ValidationReport:
    """Run domain validation over generated tables.

    Args:
        tables:        Dict returned by ``misata.generate_from_schema()``.
        domain:        One of ``clinical_trial``, ``clinical``, ``financial``, ``fintech``.
        custom_ranges: Additional column-name fragments to check, same format as built-in.

    Returns:
        ValidationReport with findings list; ``.passed`` is True when no ERRORs.
    """
    registry = dict(_DOMAIN_REGISTRY.get(domain, {}))
    if custom_ranges:
        registry.update(custom_ranges)

    report = ValidationReport(domain=domain)

    for table_name, df in tables.items():
        for col in df.columns:
            col_lower = col.lower().replace("_", "")
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if series.empty:
                continue

            # Match column to a known domain range by substring
            matched_key = None
            matched_spec = None
            for fragment, spec in registry.items():
                frag_stripped = fragment.replace("_", "")
                if frag_stripped in col_lower:
                    # Prefer longer / more specific match
                    if matched_key is None or len(fragment) > len(matched_key):
                        matched_key = fragment
                        matched_spec = spec

            if matched_spec is None:
                continue

            lo = matched_spec.get("min")
            hi = matched_spec.get("max")
            sev = matched_spec.get("severity", "WARNING")
            unit = matched_spec.get("unit", "")

            below = (series < lo).sum() if lo is not None else 0
            above = (series > hi).sum() if hi is not None else 0
            n_violating = int(below + above)

            if n_violating == 0:
                continue

            parts = []
            if below > 0 and lo is not None:
                parts.append(f"{int(below)} below min ({lo} {unit})")
            if above > 0 and hi is not None:
                parts.append(f"{int(above)} above max ({hi} {unit})")

            report.findings.append(Finding(
                table=table_name,
                column=col,
                severity=sev,
                message="; ".join(parts),
                violating_count=n_violating,
                total_count=len(series),
            ))

    return report
