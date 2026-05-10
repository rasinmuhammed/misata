"""Advisory privacy, fidelity, data-card, and Oracle reporting for generated data."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from misata.validation import validate_data


@dataclass
class PrivacyReport:
    """Heuristic privacy report for generated tables."""

    k_anonymity: Dict[str, int] = field(default_factory=dict)
    singling_out_risk: Dict[str, float] = field(default_factory=dict)
    overall_risk_score: float = 0.0
    issues: List[str] = field(default_factory=list)
    heuristic: bool = True


@dataclass
class FidelityResult:
    """One fidelity metric result."""

    name: str
    test: str
    score: float
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FidelityReport:
    """Schema-vs-output fidelity report."""

    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    overall_score: float = 0.0
    grade: str = "N/A"
    results: List[FidelityResult] = field(default_factory=list)
    heuristic: bool = True

    def add_result(self, result: FidelityResult) -> None:
        self.results.append(result)
        if not self.results:
            return
        self.overall_score = round(sum(item.score for item in self.results) / len(self.results), 1)
        if self.overall_score >= 90:
            self.grade = "A"
        elif self.overall_score >= 80:
            self.grade = "B"
        elif self.overall_score >= 70:
            self.grade = "C"
        else:
            self.grade = "D"


@dataclass
class DataCard:
    """Compact machine-readable dataset card."""

    name: str
    generated_at: str
    tables: Dict[str, Dict[str, Any]]
    notes: List[str] = field(default_factory=list)


@dataclass
class GenerationReportBundle:
    """Optional post-generation report bundle."""

    validation: Any
    reports: Dict[str, Any] = field(default_factory=dict)


def _json_safe(value: Any) -> Any:
    """Convert report objects and numpy/pandas values into JSON-safe structures."""
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, Enum):
        return value.value
    return value


def _serialize_validation_report(report: Any) -> Dict[str, Any]:
    """Serialize Misata's validation report into the Oracle payload."""
    return {
        "is_clean": bool(getattr(report, "is_clean", False)),
        "has_errors": bool(getattr(report, "has_errors", False)),
        "has_warnings": bool(getattr(report, "has_warnings", False)),
        "tables_checked": int(getattr(report, "tables_checked", 0)),
        "columns_checked": int(getattr(report, "columns_checked", 0)),
        "total_rows": int(getattr(report, "total_rows", 0)),
        "summary": report.summary() if hasattr(report, "summary") else "",
        "issues": [
            {
                "severity": getattr(getattr(issue, "severity", ""), "value", getattr(issue, "severity", "")),
                "table": getattr(issue, "table", None),
                "column": getattr(issue, "column", None),
                "message": getattr(issue, "message", ""),
                "affected_rows": getattr(issue, "affected_rows", None),
                "sample_values": _json_safe(getattr(issue, "sample_values", [])),
            }
            for issue in getattr(report, "issues", [])
        ],
    }


def _serialize_quality_report(report: Any) -> Dict[str, Any]:
    """Serialize DataQualityChecker output into the Oracle payload."""
    return {
        "score": float(getattr(report, "score", 0.0)),
        "passed": bool(getattr(report, "passed", False)),
        "summary": report.summary() if hasattr(report, "summary") else "",
        "stats": _json_safe(getattr(report, "stats", {})),
        "issues": [
            {
                "severity": getattr(issue, "severity", ""),
                "category": getattr(issue, "category", ""),
                "table": getattr(issue, "table", ""),
                "column": getattr(issue, "column", None),
                "message": getattr(issue, "message", ""),
                "details": _json_safe(getattr(issue, "details", {})),
            }
            for issue in getattr(report, "issues", [])
        ],
    }


class ReservoirTableSampler:
    """Bounded in-memory sampler for large streaming generations."""

    PRIORITY_COLUMN = "__misata_sample_priority__"

    def __init__(self, sample_size: int = 5000, rng: Optional[np.random.Generator] = None):
        self.sample_size = max(0, int(sample_size))
        self.rng = rng or np.random.default_rng(42)
        self._samples: Dict[str, pd.DataFrame] = {}
        self.row_counts: Dict[str, int] = {}

    def consume(self, table_name: str, df: pd.DataFrame) -> None:
        """Consume a batch and keep only a bounded sample."""
        self.row_counts[table_name] = self.row_counts.get(table_name, 0) + len(df)
        if self.sample_size <= 0 or df.empty:
            return

        candidate = df.copy()
        candidate[self.PRIORITY_COLUMN] = self.rng.random(len(candidate))
        existing = self._samples.get(table_name)
        if existing is None:
            combined = candidate
        else:
            combined = pd.concat([existing, candidate], ignore_index=True)

        self._samples[table_name] = combined.nsmallest(self.sample_size, self.PRIORITY_COLUMN).reset_index(drop=True)

    def get_tables(self) -> Dict[str, pd.DataFrame]:
        """Return sampled tables without internal sampling metadata."""
        output = {}
        for table_name, sample in self._samples.items():
            output[table_name] = sample.drop(columns=[self.PRIORITY_COLUMN], errors="ignore").copy()
        return output


class PrivacyAnalyzer:
    """Simple heuristic privacy analyzer."""

    QUASI_IDENTIFIER_PATTERNS = [
        "age", "birth", "zip", "postal", "city", "state", "country",
        "gender", "sex", "race", "ethnicity", "occupation", "job",
        "income", "salary", "education", "degree",
    ]

    def __init__(self, k_threshold: int = 5):
        self.k_threshold = k_threshold

    def analyze(self, tables: Dict[str, pd.DataFrame]) -> PrivacyReport:
        report = PrivacyReport()
        risk_scores: List[float] = []

        for table_name, df in tables.items():
            quasi_identifiers = [
                column for column in df.columns
                if any(pattern in column.lower() for pattern in self.QUASI_IDENTIFIER_PATTERNS)
            ]
            if not quasi_identifiers:
                continue

            group_sizes = df.groupby(quasi_identifiers).size()
            if group_sizes.empty:
                continue

            k_value = int(group_sizes.min())
            unique_fraction = float((group_sizes == 1).sum()) / max(len(df), 1)
            report.k_anonymity[table_name] = k_value
            report.singling_out_risk[table_name] = round(unique_fraction * 100, 1)

            if k_value < self.k_threshold:
                report.issues.append(
                    f"{table_name}: k-anonymity={k_value} below heuristic threshold {self.k_threshold}"
                )
                risk_scores.append(8.0)
            else:
                risk_scores.append(max(1.0, 5.0 - (k_value / 2)))

        report.overall_risk_score = round(
            min(10.0, sum(risk_scores) / max(len(risk_scores), 1)),
            1,
        )
        return report


class FidelityChecker:
    """Schema-based fidelity checking."""

    def check_against_schema(self, tables: Dict[str, pd.DataFrame], schema_config: Any) -> FidelityReport:
        report = FidelityReport()

        for table_name, df in tables.items():
            for column in schema_config.get_columns(table_name):
                if column.name not in df.columns:
                    continue

                series = df[column.name]
                if column.type in ("int", "float"):
                    report.add_result(self._numeric_result(table_name, column, series))
                elif column.type == "categorical":
                    report.add_result(self._categorical_result(table_name, column, series))
                elif column.type == "date":
                    report.add_result(self._date_result(table_name, column, series))
                elif column.type == "foreign_key":
                    report.add_result(self._fk_result(table_name, column, series))

        return report

    def _numeric_result(self, table_name: str, column: Any, series: pd.Series) -> FidelityResult:
        params = column.distribution_params
        clean = pd.to_numeric(series, errors="coerce").dropna()
        if clean.empty:
            return FidelityResult(name=f"{table_name}.{column.name}", test="numeric", score=0.0)

        score = 100.0
        details: Dict[str, Any] = {}
        if "min" in params:
            violations = int((clean < params["min"]).sum())
            if violations:
                score -= min(30.0, (violations / len(clean)) * 100)
                details["min_violations"] = violations
        if "max" in params:
            violations = int((clean > params["max"]).sum())
            if violations:
                score -= min(30.0, (violations / len(clean)) * 100)
                details["max_violations"] = violations
        return FidelityResult(
            name=f"{table_name}.{column.name}",
            test="numeric distribution",
            score=round(max(0.0, score), 1),
            details=details,
        )

    def _categorical_result(self, table_name: str, column: Any, series: pd.Series) -> FidelityResult:
        params = column.distribution_params
        choices = params.get("choices", [])
        probabilities = params.get("probabilities")
        if not choices:
            return FidelityResult(name=f"{table_name}.{column.name}", test="categorical", score=80.0)

        actual = series.value_counts(normalize=True)
        if probabilities:
            expected = dict(zip(choices, probabilities))
        else:
            expected = {choice: 1 / len(choices) for choice in choices}

        total_variation_distance = sum(abs(actual.get(choice, 0) - probability) for choice, probability in expected.items()) / 2
        return FidelityResult(
            name=f"{table_name}.{column.name}",
            test="categorical distribution",
            score=round(max(0.0, 100 * (1 - total_variation_distance * 2)), 1),
            details={"total_variation_distance": round(total_variation_distance, 3)},
        )

    def _date_result(self, table_name: str, column: Any, series: pd.Series) -> FidelityResult:
        params = column.distribution_params
        dates = pd.to_datetime(series, errors="coerce").dropna()
        if dates.empty:
            return FidelityResult(name=f"{table_name}.{column.name}", test="date range", score=0.0)

        score = 100.0
        details: Dict[str, Any] = {}
        if "start" in params:
            start = pd.to_datetime(params["start"])
            before_start = int((dates < start).sum())
            if before_start:
                score -= min(40.0, (before_start / len(dates)) * 100)
                details["before_start"] = before_start
        if "end" in params:
            end = pd.to_datetime(params["end"])
            after_end = int((dates > end).sum())
            if after_end:
                score -= min(40.0, (after_end / len(dates)) * 100)
                details["after_end"] = after_end
        return FidelityResult(
            name=f"{table_name}.{column.name}",
            test="date range",
            score=round(max(0.0, score), 1),
            details=details,
        )

    def _fk_result(self, table_name: str, column: Any, series: pd.Series) -> FidelityResult:
        if series.empty:
            return FidelityResult(name=f"{table_name}.{column.name}", test="fk distribution", score=50.0)
        counts = series.value_counts()
        cv = float(counts.std() / (counts.mean() + 1e-10)) if len(counts) > 1 else 0.0
        score = max(0.0, 100 * (1 - min(cv / 3, 1)))
        return FidelityResult(
            name=f"{table_name}.{column.name}",
            test="fk distribution",
            score=round(score, 1),
            details={"unique_fk_values": int(len(counts)), "cv": round(cv, 2)},
        )


def build_data_card(tables: Dict[str, pd.DataFrame], schema_config: Any) -> DataCard:
    """Create a compact data card."""
    table_info = {
        table_name: {
            "rows": int(len(df)),
            "columns": list(df.columns),
            "dtypes": {column: str(dtype) for column, dtype in df.dtypes.items()},
        }
        for table_name, df in tables.items()
    }
    notes = ["Heuristic metadata summary for generated synthetic data."]
    if getattr(schema_config, "realism", None):
        notes.append("Includes explicit realism configuration.")
    return DataCard(
        name=getattr(schema_config, "name", "Misata Dataset"),
        generated_at=datetime.now().isoformat(),
        tables=table_info,
        notes=notes,
    )


def build_data_card_with_metadata(
    tables: Dict[str, pd.DataFrame],
    schema_config: Any,
    *,
    row_counts: Optional[Dict[str, int]] = None,
    sampled: bool = False,
) -> DataCard:
    """Create a data card with optional exact row counts and sampling notes."""
    card = build_data_card(tables, schema_config)
    if row_counts:
        for table_name, count in row_counts.items():
            entry = card.tables.setdefault(table_name, {})
            entry["rows"] = int(count)
            if sampled and table_name in tables:
                entry["sample_rows"] = int(len(tables[table_name]))
    if sampled:
        card.notes.append("Advisory reports were computed from bounded reservoir samples, not full tables.")
    return card


def analyze_generation(
    tables: Dict[str, pd.DataFrame],
    schema_config: Any,
    reports: Optional[List[str]] = None,
    *,
    row_counts: Optional[Dict[str, int]] = None,
    sampled: bool = False,
) -> Dict[str, Any]:
    """Run selected advisory reports for generated data."""
    requested_reports = reports or []
    output: Dict[str, Any] = {}

    if "privacy" in requested_reports:
        output["privacy"] = PrivacyAnalyzer().analyze(tables)
    if "fidelity" in requested_reports:
        output["fidelity"] = FidelityChecker().check_against_schema(tables, schema_config)
    if "data_card" in requested_reports:
        output["data_card"] = build_data_card_with_metadata(
            tables,
            schema_config,
            row_counts=row_counts,
            sampled=sampled,
        )
    return output


def build_generation_report_bundle(
    tables: Dict[str, pd.DataFrame],
    schema_config: Any,
    reports: Optional[List[str]] = None,
    *,
    validation_report: Optional[Any] = None,
    row_counts: Optional[Dict[str, int]] = None,
    sampled: bool = False,
) -> GenerationReportBundle:
    """Build validation plus optional advisory reports."""
    resolved_validation = validation_report or validate_data(tables, schema_config)
    extra_reports = analyze_generation(
        tables,
        schema_config,
        reports=reports,
        row_counts=row_counts,
        sampled=sampled,
    )
    return GenerationReportBundle(validation=resolved_validation, reports=extra_reports)


def _table_row_fulfillment(
    tables: Dict[str, pd.DataFrame],
    schema_config: Any,
    row_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Compare requested table sizes with generated table sizes."""
    checks: Dict[str, Any] = {}
    all_passed = True
    counts = row_counts or {table_name: len(df) for table_name, df in tables.items()}

    for table in getattr(schema_config, "tables", []):
        expected = int(getattr(table, "row_count", 0) or 0)
        actual = int(counts.get(table.name, len(tables.get(table.name, []))))
        passed = actual == expected
        checks[table.name] = {
            "expected_rows": expected,
            "actual_rows": actual,
            "passed": passed,
        }
        all_passed = all_passed and passed

    return {"passed": all_passed, "tables": checks}


def _constraint_summary(validation_report: Any, quality_report: Any) -> Dict[str, Any]:
    """Summarize hard-rule signals from validation and quality reports."""
    validation_issues = [
        issue for issue in getattr(validation_report, "issues", [])
        if getattr(getattr(issue, "severity", ""), "value", getattr(issue, "severity", "")) == "error"
    ]
    quality_errors = [
        issue for issue in getattr(quality_report, "issues", [])
        if getattr(issue, "severity", "") == "error"
    ]
    return {
        "passed": not validation_issues and not quality_errors,
        "validation_errors": len(validation_issues),
        "quality_errors": len(quality_errors),
    }


def _locale_domain_fit(tables: Dict[str, pd.DataFrame], schema_config: Any) -> Dict[str, Any]:
    """Heuristic locale/domain fit checks for identity and geography columns."""
    realism = getattr(schema_config, "realism", None)
    locale = getattr(realism, "locale", None) or "en_US"
    domain = getattr(schema_config, "domain", None) or getattr(realism, "domain_hint", None)

    checks: List[Dict[str, Any]] = []
    try:
        from misata.locales.registry import LocaleRegistry
        pack = LocaleRegistry.global_instance().get_pack(locale)
    except Exception:
        pack = None

    for table_name, df in tables.items():
        lower_columns = {column.lower(): column for column in df.columns}

        country_col = lower_columns.get("country")
        if pack and locale != "en_US" and country_col:
            non_matching = int((df[country_col].astype(str) != pack.country_name).sum())
            checks.append({
                "name": f"{table_name}.{country_col}",
                "test": "locale country",
                "passed": non_matching == 0,
                "details": {
                    "expected": pack.country_name,
                    "non_matching_rows": non_matching,
                },
            })

        city_col = lower_columns.get("city")
        if pack and city_col and pack.top_cities:
            sample = df[city_col].astype(str)
            matching = int(sample.isin(pack.top_cities).sum())
            ratio = matching / max(len(sample), 1)
            checks.append({
                "name": f"{table_name}.{city_col}",
                "test": "locale city",
                "passed": ratio >= 0.8,
                "details": {
                    "expected_pool": pack.top_cities[:10],
                    "match_ratio": round(ratio, 3),
                },
            })

        phone_col = next((col for key, col in lower_columns.items() if "phone" in key or "mobile" in key), None)
        if pack and phone_col:
            prefix = pack.phone_prefix
            matching = int(df[phone_col].astype(str).str.startswith(prefix).sum())
            ratio = matching / max(len(df), 1)
            checks.append({
                "name": f"{table_name}.{phone_col}",
                "test": "locale phone prefix",
                "passed": ratio >= 0.95,
                "details": {"expected_prefix": prefix, "match_ratio": round(ratio, 3)},
            })

        national_id_col = next(
            (
                col for key, col in lower_columns.items()
                if key in {"national_id", "ssn", "cpf", "aadhaar", "tax_id", "nid"}
                or "national_id" in key
            ),
            None,
        )
        if pack and national_id_col:
            pattern = "^" + pack.national_id_pattern + "$"
            matching = int(df[national_id_col].astype(str).str.match(pattern).sum())
            ratio = matching / max(len(df), 1)
            checks.append({
                "name": f"{table_name}.{national_id_col}",
                "test": f"locale {pack.national_id_label} format",
                "passed": ratio >= 0.95,
                "details": {"pattern": pack.national_id_pattern, "match_ratio": round(ratio, 3)},
            })

    passed = all(check["passed"] for check in checks) if checks else True
    return {
        "passed": passed,
        "locale": locale,
        "domain": domain,
        "checks": checks,
    }


def build_oracle_report(
    tables: Dict[str, pd.DataFrame],
    schema_config: Any,
    *,
    seed: Optional[int] = None,
    row_counts: Optional[Dict[str, int]] = None,
    sampled: bool = False,
    validation_report: Optional[Any] = None,
    quality_report: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build Misata Oracle: a proof-oriented, shareable generation report.

    The Oracle combines hard validation signals with advisory realism, privacy,
    fidelity, locale, and reproducibility metadata. It is intentionally
    machine-readable so CLI, notebooks, CI, and docs can all use the same shape.
    """
    from misata.quality import check_quality

    validation = validation_report or validate_data(tables, schema_config)
    quality = quality_report or check_quality(
        tables,
        relationships=getattr(schema_config, "relationships", []),
        schema=schema_config,
    )
    advisory_reports = analyze_generation(
        tables,
        schema_config,
        reports=["privacy", "fidelity", "data_card"],
        row_counts=row_counts,
        sampled=sampled,
    )

    row_fulfillment = _table_row_fulfillment(tables, schema_config, row_counts)
    constraint_summary = _constraint_summary(validation, quality)
    locale_fit = _locale_domain_fit(tables, schema_config)

    hard_passed = (
        not getattr(validation, "has_errors", True)
        and bool(getattr(quality, "passed", False))
        and row_fulfillment["passed"]
        and constraint_summary["passed"]
    )

    oracle = {
        "name": getattr(schema_config, "name", "Misata Dataset"),
        "generated_at": datetime.now().isoformat(),
        "misata_report": "oracle",
        "version": 1,
        "passed": bool(hard_passed),
        "summary": {
            "tables": len(tables),
            "total_rows": int(sum(row_counts.values()) if row_counts else sum(len(df) for df in tables.values())),
            "hard_guarantees_passed": bool(hard_passed),
            "locale_domain_fit_passed": bool(locale_fit["passed"]),
            "quality_score": float(getattr(quality, "score", 0.0)),
            "fidelity_score": float(getattr(advisory_reports["fidelity"], "overall_score", 0.0)),
        },
        "guarantees": {
            "validation": _serialize_validation_report(validation),
            "row_count_fulfillment": row_fulfillment,
            "constraints": constraint_summary,
        },
        "advisory": {
            "quality": _serialize_quality_report(quality),
            "privacy": _json_safe(advisory_reports["privacy"]),
            "fidelity": _json_safe(advisory_reports["fidelity"]),
            "locale_domain_fit": locale_fit,
            "data_card": _json_safe(advisory_reports["data_card"]),
        },
        "reproducibility": {
            "seed": seed if seed is not None else getattr(schema_config, "seed", None),
            "schema_name": getattr(schema_config, "name", None),
            "domain": getattr(schema_config, "domain", None),
            "locale": getattr(getattr(schema_config, "realism", None), "locale", None) or "en_US",
            "sampled": sampled,
        },
        "notes": [
            "Validation, row counts, referential integrity, and configured constraints are hard checks.",
            "Privacy, fidelity, locale fit, and quality scores are advisory heuristics.",
        ],
    }
    return _json_safe(oracle)
