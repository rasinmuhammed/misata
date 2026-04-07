"""Regression tests for recently fixed public breakages."""

import pandas as pd

from misata.agents.pipeline import SimplePipeline, SchemaArchitectAgent
from misata.formulas import FormulaEngine
from misata.streaming import StreamingExporter
from misata.studio.inference import infer_schema_from_sample, schema_to_dict


def test_simple_pipeline_generates_data(monkeypatch):
    """The fallback pipeline should now produce generated data."""
    schema = {
        "name": "Pipeline Test",
        "tables": [
            {"name": "users", "row_count": 5},
        ],
        "columns": {
            "users": [
                {
                    "name": "id",
                    "type": "int",
                    "distribution_params": {"distribution": "sequence", "start": 1},
                    "unique": True,
                },
                {
                    "name": "status",
                    "type": "categorical",
                    "distribution_params": {"choices": ["active", "inactive"]},
                },
            ]
        },
        "relationships": [],
        "outcome_curves": [],
        "events": [],
    }

    monkeypatch.setattr(SchemaArchitectAgent, "extract_schema", lambda self, story: schema)

    pipeline = SimplePipeline()
    state = pipeline.run("A tiny user table")

    assert state.current_step == "complete"
    assert state.errors == []
    assert state.data is not None
    assert "users" in state.data
    assert len(state.data["users"]) == 5


def test_infer_schema_from_sample_builds_valid_schema():
    """Studio inference should build real Column/Table objects without crashing."""
    sample = pd.DataFrame(
        {
            "customer_id": [1, 2, 3],
            "segment": ["pro", "free", "pro"],
            "is_active": [True, False, True],
        }
    )

    schema = infer_schema_from_sample(sample, table_name="customers", row_count=300)
    payload = schema_to_dict(schema)

    assert schema.tables[0].name == "customers"
    assert schema.tables[0].columns == ["customer_id", "segment", "is_active"]
    assert payload["tables"][0]["columns"] == ["customer_id", "segment", "is_active"]


def test_formula_engine_evaluate_supports_cross_table_refs():
    """The generic evaluate() path should resolve lookup variables correctly."""
    tables = {
        "exercises": pd.DataFrame(
            {
                "id": [1, 2, 3],
                "calories_per_minute": [10, 8, 3],
            }
        )
    }
    df = pd.DataFrame(
        {
            "exercise_id": [1, 2, 3],
            "duration_minutes": [30, 45, 60],
        }
    )

    result = FormulaEngine(tables).evaluate(
        df,
        "duration_minutes * @exercises.calories_per_minute",
        fk_column="exercise_id",
    )

    assert result.tolist() == [300, 360, 180]


def test_streaming_exporter_appends_csv_batches(tmp_path):
    """CSV streaming should append efficiently without duplicating headers."""
    exporter = StreamingExporter(str(tmp_path), format="csv")

    exporter.write_batch("users", pd.DataFrame({"id": [1, 2], "name": ["A", "B"]}))
    exporter.write_batch("users", pd.DataFrame({"id": [3], "name": ["C"]}))
    exporter.finalize()

    output = (tmp_path / "users.csv").read_text(encoding="utf-8").strip().splitlines()
    assert output == [
        "id,name",
        "1,A",
        "2,B",
        "3,C",
    ]
