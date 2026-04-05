import pandas as pd

from misata.reporting import analyze_generation
from misata.schema import Column, RealismConfig, SchemaConfig, Table


def test_analyze_generation_returns_requested_reports():
    schema = SchemaConfig(
        name="Reporting",
        tables=[Table(name="users", row_count=3)],
        columns={
            "users": [
                Column(name="age", type="int", distribution_params={"distribution": "uniform", "min": 18, "max": 65}),
                Column(name="status", type="categorical", distribution_params={"choices": ["A", "B"]}),
            ]
        },
        realism=RealismConfig(reports=["privacy", "fidelity", "data_card"]),
    )

    tables = {
        "users": pd.DataFrame(
            {
                "age": [24, 33, 41],
                "status": ["A", "A", "B"],
            }
        )
    }

    reports = analyze_generation(tables, schema, reports=schema.realism.reports)

    assert set(reports.keys()) == {"privacy", "fidelity", "data_card"}
    assert reports["data_card"].name == "Reporting"
