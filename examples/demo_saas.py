"""
Demo: SaaS Company with Q3 Churn

This example demonstrates generating a realistic SaaS dataset with:
- User signups over time
- Subscription data
- High churn rate in Q3 2023
- Recovery in Q4
"""

from misata import DataSimulator, SchemaConfig, Table, Column, Relationship, ScenarioEvent

# Define the schema
config = SchemaConfig(
    name="SaaS Company - Q3 Churn Demo",
    description="Realistic SaaS data with seasonal churn pattern",
    seed=42,
    tables=[
        Table(name="users", row_count=50000, description="User accounts"),
        Table(name="subscriptions", row_count=60000, description="Subscription records"),
    ],
    columns={
        "users": [
            Column(
                name="user_id",
                type="int",
                distribution_params={"min": 1, "max": 50000},
                unique=True,
            ),
            Column(
                name="email",
                type="text",
                distribution_params={"text_type": "email"},
            ),
            Column(
                name="name",
                type="text",
                distribution_params={"text_type": "name"},
            ),
            Column(
                name="signup_date",
                type="date",
                distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
            ),
            Column(
                name="plan",
                type="categorical",
                distribution_params={
                    "choices": ["free", "starter", "pro", "enterprise"],
                    "probabilities": [0.4, 0.3, 0.25, 0.05],
                },
            ),
            Column(
                name="churned",
                type="boolean",
                distribution_params={"probability": 0.10},  # Base 10% churn
            ),
            Column(
                name="lifetime_value",
                type="float",
                distribution_params={
                    "distribution": "exponential",
                    "scale": 500.0,
                    "min": 0.0,
                    "decimals": 2,
                },
            ),
        ],
        "subscriptions": [
            Column(
                name="subscription_id",
                type="int",
                distribution_params={"min": 1, "max": 60000},
                unique=True,
            ),
            Column(
                name="user_id",
                type="foreign_key",
                distribution_params={},
            ),
            Column(
                name="start_date",
                type="date",
                distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
            ),
            Column(
                name="mrr",
                type="float",
                distribution_params={
                    "distribution": "normal",
                    "mean": 150.0,
                    "std": 50.0,
                    "min": 29.0,  # Minimum plan price
                    "decimals": 2,
                },
            ),
            Column(
                name="status",
                type="categorical",
                distribution_params={
                    "choices": ["active", "cancelled", "paused"],
                    "probabilities": [0.75, 0.20, 0.05],
                },
            ),
        ],
    },
    relationships=[
        Relationship(
            parent_table="users",
            child_table="subscriptions",
            parent_key="user_id",
            child_key="user_id",
        ),
    ],
    events=[
        ScenarioEvent(
            name="Q3_High_Churn",
            table="users",
            column="churned",
            condition="(signup_date >= '2023-07-01') and (signup_date < '2023-10-01')",
            modifier_type="set",
            modifier_value=True,
            description="20% of users who signed up in Q3 churned",
        ),
        ScenarioEvent(
            name="Premium_Plan_Growth",
            table="subscriptions",
            column="mrr",
            condition="(start_date >= '2024-01-01') and (status == 'active')",
            modifier_type="multiply",
            modifier_value=1.3,
            description="30% MRR increase for new subscriptions in 2024",
        ),
    ],
)


def main():
    """Run the demo."""
    print("=" * 70)
    print("Misata Demo: SaaS Company with Q3 Churn")
    print("=" * 70)
    print()
    
    # Initialize simulator
    print("Initializing DataSimulator...")
    simulator = DataSimulator(config)
    
    # Generate data
    print("Generating data...")
    print()
    data = simulator.generate_all()
    
    # Display summary
    print()
    print(simulator.get_summary())
    
    # Show sample data
    print("\n" + "=" * 70)
    print("Sample Data Preview")
    print("=" * 70)
    
    print("\nUsers (first 5 rows):")
    print(data["users"].head())
    
    print("\nSubscriptions (first 5 rows):")
    print(data["subscriptions"].head())
    
    # Analyze churn
    print("\n" + "=" * 70)
    print("Churn Analysis")
    print("=" * 70)
    
    users = data["users"]
    users["signup_quarter"] = users["signup_date"].dt.to_period("Q")
    churn_by_quarter = users.groupby("signup_quarter")["churned"].mean()
    
    print("\nChurn Rate by Signup Quarter:")
    print(churn_by_quarter)
    
    # Export to CSV
    output_dir = "./examples/saas_demo_output"
    print(f"\nExporting to {output_dir}...")
    simulator.export_to_csv(output_dir)
    
    print("\n✓ Demo complete!")
    print(f"  Check {output_dir} for CSV files")
    print("  Load them into Tableau/PowerBI to visualize the churn pattern")


if __name__ == "__main__":
    main()
