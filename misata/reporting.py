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


class ReportBundle(dict):
    """Dict of advisory reports with attribute access.

    ``bundle["privacy"]`` and ``bundle.privacy`` are equivalent;
    ``bundle.privacy_report`` / ``bundle.fidelity_report`` are accepted
    aliases so both naming styles in the docs resolve.
    """

    _ALIASES = {"privacy_report": "privacy", "fidelity_report": "fidelity"}

    def __getattr__(self, item: str) -> Any:
        key = self._ALIASES.get(item, item)
        try:
            return self[key]
        except KeyError:
            raise AttributeError(
                f"ReportBundle has no report {item!r}; available: {sorted(self)}"
            ) from None


def analyze_generation(
    tables: Dict[str, pd.DataFrame],
    schema_config: Any,
    reports: Optional[List[str]] = None,
    *,
    row_counts: Optional[Dict[str, int]] = None,
    sampled: bool = False,
) -> "ReportBundle":
    """Run advisory reports for generated data.

    ``reports=None`` (the default) runs all three: ``privacy``, ``fidelity``,
    and ``data_card``. Pass an explicit list to run a subset (or ``[]`` for
    none). Returns a :class:`ReportBundle`, a dict that also supports
    attribute access (``bundle.fidelity.overall_score``).
    """
    requested_reports = (
        ["privacy", "fidelity", "data_card"] if reports is None else reports
    )
    output: "ReportBundle" = ReportBundle()

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
    # None here keeps this bundle's historical meaning: no extra advisory
    # reports unless explicitly requested (analyze_generation's None = all).
    extra_reports = analyze_generation(
        tables,
        schema_config,
        reports=reports if reports is not None else [],
        row_counts=row_counts,
        sampled=sampled,
    )
    return GenerationReportBundle(validation=resolved_validation, reports=extra_reports)


def _table_row_fulfillment(
    tables: Dict[str, pd.DataFrame],
    schema_config: Any,
    row_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Compare requested table sizes with generated table sizes.

    Tables governed by an exact outcome curve derive their row count from the
    curve plan (target ÷ avg transaction value per period), not from the
    requested ``row_count`` — for those, the check verifies non-emptiness and
    records the derivation instead of failing the Oracle on a number the
    engine was *supposed* to override. KPI conformance is checked separately.
    """
    checks: Dict[str, Any] = {}
    all_passed = True
    counts = row_counts or {table_name: len(df) for table_name, df in tables.items()}

    curve_tables = {
        getattr(curve, "table", None)
        for curve in getattr(schema_config, "outcome_curves", []) or []
    }

    for table in getattr(schema_config, "tables", []):
        expected = int(getattr(table, "row_count", 0) or 0)
        actual = int(counts.get(table.name, len(tables.get(table.name, []))))
        if table.name in curve_tables:
            passed = actual > 0
            checks[table.name] = {
                "expected_rows": expected,
                "actual_rows": actual,
                "row_count_derived_from_outcome_curve": True,
                "passed": passed,
            }
        else:
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


def _curve_tolerance(schema_config: Any, table_name: str, column_name: str) -> float:
    """Return an absolute tolerance for monetary/numeric KPI checks."""
    try:
        column = next(
            col for col in schema_config.get_columns(table_name)
            if getattr(col, "name", None) == column_name
        )
    except Exception:
        return 0.0

    params = getattr(column, "distribution_params", {}) or {}
    decimals = params.get("decimals")
    if isinstance(decimals, int) and decimals > 0:
        return 10 ** (-decimals)
    return 0.01 if getattr(column, "type", None) == "float" else 0.0


def _relative_error(observed: float, target: float) -> float:
    denom = abs(target) if abs(target) > 1e-12 else 1.0
    return abs(observed - target) / denom


def _outcome_curve_conformance(tables: Dict[str, pd.DataFrame], schema_config: Any) -> List[Dict[str, Any]]:
    """Evaluate exact OutcomeCurve targets against generated tables."""
    curves = list(getattr(schema_config, "outcome_curves", []) or [])
    if not curves:
        return []

    from misata.engines import FactEngine

    engine = FactEngine()
    results: List[Dict[str, Any]] = []
    tables_by_name = {getattr(table, "name", None): table for table in getattr(schema_config, "tables", [])}

    for curve in curves:
        table_name = getattr(curve, "table", None)
        column_name = getattr(curve, "column", None)
        time_column = getattr(curve, "time_column", "date")
        result: Dict[str, Any] = {
            "type": "outcome_curve",
            "table": table_name,
            "column": column_name,
            "time_column": time_column,
            "time_unit": getattr(curve, "time_unit", "month"),
            "checked": False,
            "passed": True,
            "periods": [],
        }

        if not engine.curve_has_exact_targets(curve):
            result["reason"] = "relative_or_missing_exact_targets"
            results.append(result)
            continue

        table = tables_by_name.get(table_name)
        if table is None:
            result.update({"checked": True, "passed": False, "reason": "missing_schema_table"})
            results.append(result)
            continue

        df = tables.get(table_name)
        if df is None:
            result.update({"checked": True, "passed": False, "reason": "missing_output_table"})
            results.append(result)
            continue
        if column_name not in df.columns or time_column not in df.columns:
            result.update({"checked": True, "passed": False, "reason": "missing_output_column"})
            results.append(result)
            continue

        plan = engine.build_plan(table, schema_config.get_columns(table_name), [curve])
        if plan is None:
            result.update({"checked": True, "passed": False, "reason": "incompatible_curve_plan"})
            results.append(result)
            continue

        timestamps = pd.to_datetime(df[time_column], errors="coerce")
        values = pd.to_numeric(df[column_name], errors="coerce").fillna(0)
        tolerance = _curve_tolerance(schema_config, table_name, column_name)
        period_results: List[Dict[str, Any]] = []

        for resolved in plan.curves:
            if resolved.column != column_name:
                continue
            for bucket, target in zip(resolved.buckets, resolved.targets):
                mask = (timestamps >= bucket.start) & (timestamps < bucket.end)
                observed = float(values.loc[mask].sum())
                target_float = float(target)
                abs_error = abs(observed - target_float)
                period_passed = abs_error <= tolerance
                period_results.append({
                    "period": bucket.label,
                    "target": target_float,
                    "observed": observed,
                    "absolute_error": abs_error,
                    "relative_error": _relative_error(observed, target_float),
                    "tolerance": tolerance,
                    "rows": int(mask.sum()),
                    "passed": period_passed,
                })

        result["checked"] = True
        result["periods"] = period_results
        result["passed"] = all(period["passed"] for period in period_results)
        results.append(result)

    return results


def _rate_period_key(period: Any) -> Optional[int]:
    """Parse a RateCurve short period into a 1-based running period index."""
    period_str = str(period).strip()
    if not period_str or period_str.lower() == "all":
        return None
    if len(period_str) == 7 and period_str[4] == "-" and period_str[5:].isdigit():
        return int(period_str[5:])
    if len(period_str) == 7 and period_str[4:6].upper() == "-Q" and period_str[6].isdigit():
        quarter = int(period_str[6])
        if 1 <= quarter <= 4:
            return (quarter - 1) * 3 + 1
    if period_str.isdigit():
        return int(period_str)
    return None


def _rate_curve_targets(rate_curve: Any, observed_periods: List[int]) -> Dict[int, float]:
    """Resolve RateCurve targets for observed running periods."""
    anchors: Dict[int, float] = {}
    all_rate: Optional[float] = None

    for point in getattr(rate_curve, "rate_points", []) or []:
        period = point.get("period")
        rate = float(point.get("rate", 0.0))
        if str(period).strip().lower() == "all":
            all_rate = rate
            continue
        key = _rate_period_key(period)
        if key is not None:
            anchors[key] = rate

    if all_rate is not None:
        for period in observed_periods:
            anchors.setdefault(period, all_rate)

    if not anchors or not observed_periods:
        return {}

    if getattr(rate_curve, "interpolate", True) and len(anchors) >= 2:
        max_period = max(max(observed_periods), max(anchors))
        xs = np.array(sorted(anchors), dtype=float)
        ys = np.array([anchors[int(x)] for x in xs], dtype=float)
        grid = np.arange(1, max_period + 1, dtype=float)
        rates = np.clip(np.interp(grid, xs, ys), 0.0, 1.0)
        return {period: float(rates[period - 1]) for period in observed_periods if 1 <= period <= max_period}

    return {period: float(anchors[period]) for period in observed_periods if period in anchors}


def _rate_curve_conformance(tables: Dict[str, pd.DataFrame], schema_config: Any) -> List[Dict[str, Any]]:
    """Evaluate exact RateCurve targets against generated tables."""
    results: List[Dict[str, Any]] = []
    for rate_curve in getattr(schema_config, "rate_curves", []) or []:
        table_name = getattr(rate_curve, "table", None)
        column_name = getattr(rate_curve, "column", None)
        time_column = getattr(rate_curve, "time_column", "date")
        result: Dict[str, Any] = {
            "type": "rate_curve",
            "table": table_name,
            "column": column_name,
            "time_column": time_column,
            "time_unit": getattr(rate_curve, "time_unit", "month"),
            "checked": True,
            "passed": True,
            "periods": [],
        }

        df = tables.get(table_name)
        if df is None:
            result.update({"passed": False, "reason": "missing_output_table"})
            results.append(result)
            continue
        if column_name not in df.columns or time_column not in df.columns:
            result.update({"passed": False, "reason": "missing_output_column"})
            results.append(result)
            continue

        timestamps = pd.to_datetime(df[time_column], errors="coerce")
        valid = timestamps.dropna()
        if valid.empty:
            result.update({"passed": False, "reason": "no_valid_timestamps"})
            results.append(result)
            continue

        start_year = int(valid.dt.year.min())
        start_month = int(valid.dt.month.min())
        running_period = (
            (timestamps.dt.year - start_year) * 12
            + (timestamps.dt.month - start_month)
            + 1
        ).fillna(-1).astype(int)
        observed_periods = sorted(period for period in running_period.unique() if period > 0)
        targets = _rate_curve_targets(rate_curve, observed_periods)

        true_value = getattr(rate_curve, "true_value", True)
        period_results: List[Dict[str, Any]] = []
        for period, target_rate in targets.items():
            mask = running_period == period
            row_count = int(mask.sum())
            if row_count <= 0:
                continue
            positive_count = int((df.loc[mask, column_name] == true_value).sum())
            observed_rate = positive_count / row_count
            expected_count = int(round(row_count * target_rate))
            tolerance = 0.5 / row_count + 1e-12
            period_results.append({
                "period": str(period).zfill(2) if period <= 12 else str(period),
                "target_rate": float(target_rate),
                "observed_rate": float(observed_rate),
                "target_count": expected_count,
                "observed_count": positive_count,
                "absolute_error": abs(observed_rate - target_rate),
                "tolerance": tolerance,
                "rows": row_count,
                "passed": positive_count == expected_count or abs(observed_rate - target_rate) <= tolerance,
            })

        result["periods"] = period_results
        result["passed"] = all(period["passed"] for period in period_results)
        if not period_results:
            result["reason"] = "no_matching_period_targets"
        results.append(result)

    return results


def _kpi_conformance(tables: Dict[str, pd.DataFrame], schema_config: Any) -> Dict[str, Any]:
    """Summarize hard KPI conformance checks for the Oracle report."""
    outcome_results = _outcome_curve_conformance(tables, schema_config)
    rate_results = _rate_curve_conformance(tables, schema_config)
    checked_results = [
        result for result in outcome_results + rate_results
        if result.get("checked", True)
    ]
    return {
        "passed": all(result.get("passed", False) for result in checked_results) if checked_results else True,
        "checked": len(checked_results),
        "outcome_curves": outcome_results,
        "rate_curves": rate_results,
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
    kpi_conformance = _kpi_conformance(tables, schema_config)
    locale_fit = _locale_domain_fit(tables, schema_config)

    hard_passed = (
        not getattr(validation, "has_errors", True)
        and bool(getattr(quality, "passed", False))
        and row_fulfillment["passed"]
        and constraint_summary["passed"]
        and kpi_conformance["passed"]
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
            "kpi_conformance": kpi_conformance,
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
            "Validation, row counts, referential integrity, KPI conformance, and configured constraints are hard checks.",
            "Privacy, fidelity, locale fit, and quality scores are advisory heuristics.",
        ],
    }
    return _json_safe(oracle)
