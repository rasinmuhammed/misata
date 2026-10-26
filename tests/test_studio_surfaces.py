"""The web API and the studio warehouse generator: endpoints that resolve,
and columns that generate from partial specs."""

from __future__ import annotations

import numpy as np
import pytest

from misata.studio.constraint_generator import (ColumnSpec, ConstrainedWarehouseGenerator,
                                                TableSpec, WarehouseSpec)


def _generator() -> ConstrainedWarehouseGenerator:
    return ConstrainedWarehouseGenerator(WarehouseSpec(tables=[TableSpec(name="t", row_count=1, columns=[])]))


class TestIntColumns:
    def test_normal_without_bounds_uses_the_default_range(self):
        values = _generator()._generate_column(ColumnSpec(name="n", type="int",
                                                          distribution="normal"), 500)
        assert values.min() >= 0 and values.max() <= 100

    def test_declared_bounds_are_inclusive(self):
        values = _generator()._generate_column(ColumnSpec(name="n", type="int",
                                                          min_val=5, max_val=5), 50)
        assert set(np.unique(values)) == {5}

    def test_a_declared_mean_of_zero_is_kept(self):
        values = _generator()._generate_column(
            ColumnSpec(name="n", type="int", distribution="normal", min_val=-50, max_val=50,
                       mean=0, std=5), 2_000)
        assert abs(values.mean()) < 1


def test_enhance_schema_endpoint_enriches_the_schema(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import misata.api as api

    seen = {}

    def enrich(self, schema, prompt=None, temperature=0.3):
        seen["prompt"] = prompt
        return schema

    monkeypatch.setattr(api.LLMSchemaGenerator, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(api.LLMSchemaGenerator, "enrich_schema", enrich)
    config = {"name": "shop", "tables": [{"name": "orders", "row_count": 10}],
              "columns": {"orders": [{"name": "id", "type": "int"}]}}
    response = TestClient(api.app).post("/api/enhance-schema",
                                        json={"schema_config": config,
                                              "enhancement": "skew order values"})
    assert response.status_code == 200, response.text
    assert response.json()["tables_count"] == 1
    assert seen["prompt"] == "skew order values"
