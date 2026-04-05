"""
Example: synthetic data for a BI demo with exact monthly revenue targets.
"""

from misata import Column, DataSimulator, OutcomeCurve, SchemaConfig, Table


def build_config() -> SchemaConfig:
    return SchemaConfig(
        name="BI Demo Dataset",
        description="Monthly sales data with exact revenue targets and a September dip",
        seed=42,
        tables=[Table(name="sales", row_count=6000)],
        columns={
            "sales": [
                Column(
                    name="id",
                    type="int",
                    distribution_params={"distribution": "uniform", "min": 1, "max": 6000},
                    unique=True,
                ),
                Column(
                    name="sale_date",
                    type="date",
                    distribution_params={"start": "2025-01-01", "end": "2025-12-31"},
                ),
                Column(
                    name="channel",
                    type="categorical",
                    distribution_params={"choices": ["Self Serve", "Sales Led", "Partner"]},
                ),
                Column(
                    name="revenue",
                    type="float",
                    distribution_params={"distribution": "uniform", "min": 25.0, "max": 500.0, "decimals": 2},
                ),
            ]
        },
        outcome_curves=[
            OutcomeCurve(
                table="sales",
                column="revenue",
                time_column="sale_date",
                time_unit="month",
                value_mode="absolute",
                avg_transaction_value=180.0,
                curve_points=[
                    {"month": 1, "target_value": 50000},
                    {"month": 2, "target_value": 65000},
                    {"month": 3, "target_value": 80000},
                    {"month": 4, "target_value": 90000},
                    {"month": 5, "target_value": 105000},
                    {"month": 6, "target_value": 115000},
                    {"month": 7, "target_value": 125000},
                    {"month": 8, "target_value": 135000},
                    {"month": 9, "target_value": 95000},
                    {"month": 10, "target_value": 150000},
                    {"month": 11, "target_value": 175000},
                    {"month": 12, "target_value": 200000},
                ],
            )
        ],
    )


def main() -> None:
    simulator = DataSimulator(build_config())
    result = simulator.generate_with_reports(sample_size=1500)
    simulator.export_to_csv("./examples/output/bi_demo_dataset")

    print("Row counts:")
    for table_name, row_count in result.table_row_counts.items():
        print(f"  {table_name}: {row_count:,}")

    print()
    print(result.validation_report.summary())


if __name__ == "__main__":
    main()
