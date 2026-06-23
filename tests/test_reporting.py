import pandas as pd

from misata.reporting import analyze_generation, build_oracle_report
from misata.schema import Column, OutcomeCurve, RateCurve, RealismConfig, SchemaConfig, Table


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


def test_oracle_reports_outcome_curve_conformance_as_hard_guarantee():
    schema = SchemaConfig(
        name="Outcome Oracle",
        seed=42,
        tables=[Table(name="orders", row_count=4)],
        columns={
            "orders": [
                Column(name="id", type="int", unique=True, distribution_params={"min": 1, "max": 5}),
                Column(name="order_date", type="date", distribution_params={"start": "2024-01-01", "end": "2024-02-29"}),
                Column(name="amount", type="float", distribution_params={"decimals": 2}),
            ]
        },
        outcome_curves=[
            OutcomeCurve(
                table="orders",
                column="amount",
                time_column="order_date",
                time_unit="month",
                value_mode="absolute",
                curve_points=[
                    {"month": 1, "target_value": 100.0},
                    {"month": 2, "target_value": 200.0},
                ],
            )
        ],
    )
    tables = {
        "orders": pd.DataFrame(
            {
                "id": [1, 2, 3, 4],
                "order_date": pd.to_datetime(["2024-01-05", "2024-01-20", "2024-02-03", "2024-02-18"]),
                "amount": [40.0, 60.0, 75.0, 125.0],
            }
        )
    }

    report = build_oracle_report(tables, schema, seed=42)

    conformance = report["guarantees"]["kpi_conformance"]
    assert report["passed"] is True
    assert conformance["passed"] is True
    assert conformance["checked"] == 1
    assert conformance["outcome_curves"][0]["passed"] is True
    assert [period["observed"] for period in conformance["outcome_curves"][0]["periods"]] == [100.0, 200.0]


def test_oracle_reports_rate_curve_conformance_as_hard_guarantee():
    schema = SchemaConfig(
        name="Rate Oracle",
        seed=42,
        tables=[Table(name="transactions", row_count=4)],
        columns={
            "transactions": [
                Column(name="id", type="int", unique=True, distribution_params={"min": 1, "max": 5}),
                Column(name="tx_date", type="date", distribution_params={"start": "2024-01-01", "end": "2024-01-31"}),
                Column(name="is_fraud", type="boolean", distribution_params={"probability": 0.5}),
            ]
        },
        rate_curves=[
            RateCurve(
                table="transactions",
                column="is_fraud",
                time_column="tx_date",
                interpolate=False,
                rate_points=[{"period": "all", "rate": 0.5}],
            )
        ],
    )
    tables = {
        "transactions": pd.DataFrame(
            {
                "id": [1, 2, 3, 4],
                "tx_date": pd.to_datetime(["2024-01-05", "2024-01-06", "2024-01-07", "2024-01-08"]),
                "is_fraud": [True, False, True, False],
            }
        )
    }

    report = build_oracle_report(tables, schema, seed=42)

    conformance = report["guarantees"]["kpi_conformance"]
    assert report["passed"] is True
    assert conformance["passed"] is True
    assert conformance["checked"] == 1
    rate_check = conformance["rate_curves"][0]["periods"][0]
    assert rate_check["target_rate"] == 0.5
    assert rate_check["observed_rate"] == 0.5
    assert rate_check["target_count"] == 2
    assert rate_check["observed_count"] == 2


def test_oracle_fails_when_declared_kpi_conformance_fails():
    schema = SchemaConfig(
        name="Broken Outcome Oracle",
        seed=42,
        tables=[Table(name="orders", row_count=2)],
        columns={
            "orders": [
                Column(name="id", type="int", unique=True, distribution_params={"min": 1, "max": 3}),
                Column(name="order_date", type="date", distribution_params={"start": "2024-01-01", "end": "2024-01-31"}),
                Column(name="amount", type="float", distribution_params={"decimals": 2}),
            ]
        },
        outcome_curves=[
            OutcomeCurve(
                table="orders",
                column="amount",
                time_column="order_date",
                time_unit="month",
                value_mode="absolute",
                curve_points=[{"month": 1, "target_value": 100.0}],
            )
        ],
    )
    tables = {
        "orders": pd.DataFrame(
            {
                "id": [1, 2],
                "order_date": pd.to_datetime(["2024-01-05", "2024-01-20"]),
                "amount": [40.0, 50.0],
            }
        )
    }

    report = build_oracle_report(tables, schema, seed=42)

    conformance = report["guarantees"]["kpi_conformance"]
    assert report["passed"] is False
    assert conformance["passed"] is False
    assert conformance["outcome_curves"][0]["periods"][0]["target"] == 100.0
    assert conformance["outcome_curves"][0]["periods"][0]["observed"] == 90.0
