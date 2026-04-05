"""Advisory privacy, fidelity, and data-card reporting for generated data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
