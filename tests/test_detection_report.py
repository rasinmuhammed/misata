"""Tests for the StoryParser detection report — the structured account
of what was understood from a story, used by the no-code studio and
the CLI to confirm interpretation before generation."""

from __future__ import annotations

import pytest

import misata
from misata import DetectionReport, StoryParser


def test_report_is_returned_after_parse():
    parser = StoryParser()
    parser.parse("A SaaS company with 5k users")
    report = parser.detection_report()
    assert isinstance(report, DetectionReport)
    assert report.domain == "saas"


def test_report_records_matched_keywords():
    parser = StoryParser()
    parser.parse("A SaaS company with churn and MRR")
    report = parser.detection_report()
    assert "saas" in report.matched_keywords
    assert any(kw in report.matched_keywords for kw in ("churn", "mrr"))


def test_report_low_vs_high_confidence():
    """Single keyword → low; multiple keywords → high."""
    p1 = StoryParser()
    p1.parse("A SaaS app")
    assert p1.detection_report().domain_confidence == "low"

    p2 = StoryParser()
    p2.parse("A SaaS company with subscription churn and MRR")
    assert p2.detection_report().domain_confidence == "high"


def test_report_surfaces_near_misses():
    """When a story matches multiple domains, the runner-up domains are reported."""
    parser = StoryParser()
    parser.parse("A crypto exchange with payments and fraud detection")
    report = parser.detection_report()
    # crypto wins (precedence order); fintech matched too via "payments"/"fraud"
    assert report.domain == "crypto"
    assert "fintech" in report.near_misses


def test_report_includes_table_preview():
    parser = StoryParser()
    parser.parse("A SaaS company with 1000 users")
    report = parser.detection_report()
    assert report.table_preview, "Expected at least one table previewed"
    assert all("name" in t and "rows" in t and "columns" in t for t in report.table_preview)
    assert report.total_rows == sum(t["rows"] for t in report.table_preview)


def test_report_warns_on_no_domain_match():
    parser = StoryParser()
    parser.parse("Some random data with no domain keywords")
    report = parser.detection_report()
    assert report.domain is None
    assert report.domain_confidence == "none"
    assert any("No domain detected" in w for w in report.warnings)


def test_report_warns_on_ambiguous_story():
    parser = StoryParser()
    parser.parse("A crypto exchange with fintech payments")
    report = parser.detection_report()
    assert report.near_misses
    assert any("also matched" in w for w in report.warnings)


def test_report_extracts_scale():
    parser = StoryParser()
    parser.parse("A SaaS company with 50k users and 1M transactions")
    report = parser.detection_report()
    assert report.scale_params.get("users") == 50_000
    assert report.scale_params.get("transactions") == 1_000_000


def test_summary_renders_without_error():
    """summary() must produce a string for every common code path."""
    for story in [
        "A SaaS company",
        "A fintech with crypto wallets",
        "Random gibberish text",
        "A travel platform with hotels and flights",
    ]:
        parser = StoryParser()
        parser.parse(story)
        out = parser.detection_report().summary()
        assert isinstance(out, str)
        assert len(out) > 0


def test_detection_report_exported_from_top_level():
    """misata.DetectionReport must be importable for downstream tooling."""
    assert misata.DetectionReport is DetectionReport
