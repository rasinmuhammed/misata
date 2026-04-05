"""
Example: multi-table synthetic data with foreign keys.
"""

from misata import Column, DataSimulator, RealismConfig, Relationship, SchemaConfig, Table


def build_config() -> SchemaConfig:
    return SchemaConfig(
        name="Retail Multi Table Demo",
        description="Customers, orders, and order items with realism planning enabled",
        seed=42,
        tables=[
            Table(name="customers", row_count=1000),
            Table(name="orders", row_count=1000),
            Table(name="order_items", row_count=1000),
        ],
        columns={
            "customers": [
                Column(
                    name="id",
                    type="int",
                    distribution_params={"distribution": "uniform", "min": 1, "max": 1000},
                    unique=True,
                ),
                Column(name="first_name", type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name", type="text", distribution_params={"text_type": "last_name"}),
                Column(name="email", type="text", distribution_params={"text_type": "email"}),
                Column(name="country", type="categorical", distribution_params={"choices": ["United States", "United Kingdom", "Canada"]}),
            ],
            "orders": [
                Column(
                    name="id",
                    type="int",
                    distribution_params={"distribution": "uniform", "min": 1, "max": 5000},
                    unique=True,
                ),
                Column(name="customer_id", type="foreign_key", distribution_params={}),
                Column(
                    name="order_date",
                    type="date",
                    distribution_params={"start": "2025-01-01", "end": "2025-12-31"},
                ),
                Column(
                    name="status",
                    type="categorical",
                    distribution_params={"choices": ["pending", "processing", "shipped", "delivered", "cancelled"]},
                ),
            ],
            "order_items": [
                Column(
                    name="id",
                    type="int",
                    distribution_params={"distribution": "uniform", "min": 1, "max": 15000},
                    unique=True,
                ),
                Column(name="order_id", type="foreign_key", distribution_params={}),
                Column(name="category", type="categorical", distribution_params={"choices": ["Electronics", "Home", "Accessories"]}),
                Column(name="product_name", type="text", distribution_params={"text_type": "product_name"}),
                Column(name="quantity", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 4}),
                Column(name="unit_price", type="float", distribution_params={"distribution": "uniform", "min": 15.0, "max": 400.0, "decimals": 2}),
            ],
        },
        relationships=[
            Relationship(parent_table="customers", child_table="orders", parent_key="id", child_key="customer_id"),
            Relationship(parent_table="orders", child_table="order_items", parent_key="id", child_key="order_id"),
        ],
        realism=RealismConfig(
            row_planning="heuristic",
            coherence="standard",
            text_mode="realistic_catalog",
        ),
    )


def main() -> None:
    simulator = DataSimulator(build_config())
    result = simulator.generate_with_reports(sample_size=1000)

    print("Row counts:")
    for table_name, row_count in result.table_row_counts.items():
        print(f"  {table_name}: {row_count:,}")

    print()
    print("Sampled tables returned:", result.tables_are_samples)
    print(result.validation_report.summary())


if __name__ == "__main__":
    main()
