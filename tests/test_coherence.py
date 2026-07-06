"""0.8.1.22: coherence_audit() — detect + repair reader-visible contradictions."""
import numpy as np
import pandas as pd
import pytest

import misata
from misata.coherence import coherence_audit


def _rng(n, seed=0):
    return np.random.default_rng(seed).uniform(1, 100, n)


class TestDetection:
    def test_clean_dataset_has_no_findings(self):
        t = misata.generate_from_schema(misata.from_dict_schema({
            "customers": {"__rows__": 400,
                "id": {"type": "integer", "primary_key": True},
                "name": {"type": "string"},
                "age": {"type": "integer", "min": 18, "max": 75}},
        }, seed=3))
        assert coherence_audit(t).clean

    def test_near_constant_numeric_flagged(self):
        t = {"trips": pd.DataFrame({"id": range(100), "fare": [12.5] * 100})}
        r = coherence_audit(t)
        kinds = {f.kind for f in r.findings}
        assert "near_constant" in kinds

    def test_label_filler_flagged(self):
        t = {"x": pd.DataFrame({
            "id": range(100),
            "status": ["Designed for everyday use with reliable performance and clean design."] * 100,
        })}
        r = coherence_audit(t)
        assert any(f.kind == "label_filler" for f in r.findings)

    def test_scale_absurdity_flagged(self):
        t = {"people": pd.DataFrame({"id": range(50), "age": [4000] + [30] * 49})}
        r = coherence_audit(t)
        assert any(f.kind == "scale_absurdity" and f.column == "age" for f in r.findings)

    def test_temporal_disorder_flagged(self):
        t = {"trips": pd.DataFrame({
            "id": range(30),
            "pickup_time": pd.to_datetime("2025-01-01 10:00:00"),
            "dropoff_time": pd.to_datetime("2025-01-01 09:00:00"),
        })}
        r = coherence_audit(t)
        assert any(f.kind == "temporal_disorder" for f in r.findings)

    def test_geo_contradiction_flagged(self):
        t = {"riders": pd.DataFrame({
            "id": range(20), "city": ["Toronto"] * 20, "country": ["United States"] * 20})}
        r = coherence_audit(t)
        assert any(f.kind == "geo_contradiction" for f in r.findings)

    def test_broken_derived_math_flagged(self):
        t = {"orders": pd.DataFrame({
            "id": range(100),
            "quantity": [2] * 100, "unit_price": [10.0] * 100,
            "total": [999.0] * 100})}
        r = coherence_audit(t)
        assert any(f.kind == "broken_derived_math" for f in r.findings)


class TestRepair:
    def test_repair_reorders_temporal(self):
        t = {"trips": pd.DataFrame({
            "id": range(30),
            "pickup_time": pd.to_datetime("2025-01-01 10:00:00"),
            "dropoff_time": pd.to_datetime("2025-01-01 09:00:00"),
        })}
        coherence_audit(t, repair=True)
        assert (pd.to_datetime(t["trips"]["dropoff_time"])
                >= pd.to_datetime(t["trips"]["pickup_time"])).all()

    def test_repair_fixes_geo(self):
        t = {"riders": pd.DataFrame({
            "id": range(40), "city": ["Toronto"] * 40, "country": ["United States"] * 40})}
        coherence_audit(t, repair=True)
        from misata.vocab_seeds import CITIES_BY_COUNTRY
        us = set(CITIES_BY_COUNTRY["United States"])
        assert all(c in us for c in t["riders"]["city"])

    def test_repair_recomputes_derived_math(self):
        t = {"orders": pd.DataFrame({
            "id": range(100),
            "quantity": [2] * 100, "unit_price": [10.0] * 100,
            "total": [999.0] * 100})}
        coherence_audit(t, repair=True)
        assert (t["orders"]["total"] == 20.0).all()

    def test_repaired_findings_marked_and_dont_penalize_score(self):
        t = {"trips": pd.DataFrame({
            "id": range(30),
            "pickup_time": pd.to_datetime("2025-01-01 10:00:00"),
            "dropoff_time": pd.to_datetime("2025-01-01 09:00:00"),
        })}
        r = coherence_audit(t, repair=True)
        temporal = [f for f in r.findings if f.kind == "temporal_disorder"]
        assert temporal and all(f.repaired for f in temporal)


class TestReportShape:
    def test_to_dict_is_json_serializable(self):
        import json
        t = {"x": pd.DataFrame({"id": range(50), "price": [1.0] * 50})}
        d = coherence_audit(t).to_dict()
        json.loads(json.dumps(d))  # must not raise
        assert d["misata_report"] == "coherence"
        assert "findings" in d and "score" in d

    def test_oracle_report_includes_coherence(self):
        from misata.reporting import build_oracle_report
        cfg = misata.from_dict_schema({
            "x": {"__rows__": 100, "id": {"type": "integer", "primary_key": True},
                  "v": {"type": "float", "min": 1, "max": 100}}}, seed=2)
        t = misata.generate_from_schema(cfg)
        oracle = build_oracle_report(t, cfg, seed=2)
        assert "coherence" in oracle["advisory"]
        assert oracle["advisory"]["coherence"]["misata_report"] == "coherence"


class TestFraudFieldReport:
    """0.8.1.26: defects from the credit-card fraud field report."""

    def test_pattern_leak_detected(self):
        t = {"merchants": pd.DataFrame({
            "id": range(50),
            "merchant_name": ["Et+( Sj+){1,2}"] * 50})}
        r = coherence_audit(t)
        assert any(f.kind == "pattern_leak" for f in r.findings)

    def test_denormalized_mismatch_detected(self):
        parent = pd.DataFrame({"id": [1, 2], "merchant_city": ["Tokyo", "Lille"]})
        child = pd.DataFrame({
            "id": range(100),
            "merchant_id": [1, 2] * 50,
            "merchant_city": ["Boston"] * 100})
        r = coherence_audit({"merchants": parent, "transactions": child})
        assert any(f.kind == "denormalized_mismatch" for f in r.findings)

    def test_agreeing_denormalized_columns_pass(self):
        parent = pd.DataFrame({"id": [1, 2], "merchant_city": ["Tokyo", "Lille"]})
        child = pd.DataFrame({
            "id": range(100),
            "merchant_id": [1, 2] * 50,
            "merchant_city": ["Tokyo", "Lille"] * 50})
        r = coherence_audit({"merchants": parent, "transactions": child})
        assert not any(f.kind == "denormalized_mismatch" for f in r.findings)
