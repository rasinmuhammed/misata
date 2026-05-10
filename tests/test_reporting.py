import pandas as pd

from misata.reporting import analyze_generation, build_oracle_report
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


def test_build_oracle_report_contains_guarantees_and_advisory_sections():
    schema = SchemaConfig(
        name="Oracle",
        seed=42,
        tables=[Table(name="users", row_count=3)],
        columns={
            "users": [
                Column(name="id", type="int", unique=True, distribution_params={"min": 1, "max": 4}),
                Column(name="age", type="int", distribution_params={"distribution": "uniform", "min": 18, "max": 65}),
            ]
        },
    )
    tables = {"users": pd.DataFrame({"id": [1, 2, 3], "age": [24, 33, 41]})}

    report = build_oracle_report(tables, schema, seed=42)

    assert report["misata_report"] == "oracle"
    assert report["passed"] is True
    assert report["guarantees"]["row_count_fulfillment"]["passed"] is True
    assert "privacy" in report["advisory"]
    assert report["reproducibility"]["seed"] == 42


def test_oracle_locale_fit_checks_country_city_phone_and_national_id():
    schema = SchemaConfig(
        name="Brazil Oracle",
        tables=[Table(name="customers", row_count=2)],
        columns={
            "customers": [
                Column(name="country", type="text", distribution_params={"text_type": "country"}),
                Column(name="city", type="text", distribution_params={"text_type": "city"}),
                Column(name="phone", type="text", distribution_params={"text_type": "phone"}),
                Column(name="national_id", type="text", distribution_params={"text_type": "national_id"}),
            ]
        },
        realism=RealismConfig(locale="pt_BR"),
    )
    tables = {
        "customers": pd.DataFrame(
            {
                "country": ["Brazil", "Brazil"],
                "city": ["São Paulo", "Rio de Janeiro"],
                "phone": ["+55 11999999999", "+55 21988888888"],
                "national_id": ["123.456.789-10", "987.654.321-99"],
            }
        )
    }

    report = build_oracle_report(tables, schema)

    locale_fit = report["advisory"]["locale_domain_fit"]
    assert locale_fit["passed"] is True
    assert locale_fit["locale"] == "pt_BR"
