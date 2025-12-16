"""
Demo: Pharma Services Company (JMAN-style)

This example demonstrates generating pharma services data similar to
the JMAN Group project, including:
- Research projects
- Timesheet entries
- Project phases
- Resource allocation
"""

from misata import DataSimulator, SchemaConfig, Table, Column, Relationship

# Define the schema (simplified version of a real pharma services company)
config = SchemaConfig(
    name="Pharma Services Company",
    description="Realistic pharma services data with projects, timesheets, and resources",
    seed=42,
    tables=[
        Table(name="research_projects", row_count=500),
        Table(name="timesheets", row_count=50000),
        Table(name="employees", row_count=200),
    ],
    columns={
        "research_projects": [
            Column(
                name="project_id",
                type="int",
                distribution_params={"min": 1, "max": 500},
                unique=True,
            ),
            Column(
                name="project_name",
                type="text",
                distribution_params={"text_type": "company"},
            ),
            Column(
                name="therapeutic_area",
                type="categorical",
                distribution_params={
                    "choices": [
                        "Oncology",
                        "Cardiology",
                        "Neurology",
                        "Immunology",
                        "Infectious Disease",
                    ],
                    "probabilities": [0.3, 0.25, 0.2, 0.15, 0.1],
                },
            ),
            Column(
                name="start_date",
                type="date",
                distribution_params={"start": "2020-01-01", "end": "2023-12-31"},
            ),
            Column(
                name="status",
                type="categorical",
                distribution_params={
                    "choices": ["planning", "active", "completed", "on-hold"],
                    "probabilities": [0.1, 0.5, 0.3, 0.1],
                },
            ),
            Column(
                name="budget",
                type="float",
                distribution_params={
                    "distribution": "normal",
                    "mean": 500000.0,
                    "std": 150000.0,
                    "min": 100000.0,
                    "decimals": 2,
                },
            ),
            Column(
                name="phase",
                type="categorical",
                distribution_params={
                    "choices": ["Phase I", "Phase II", "Phase III", "Phase IV"],
                    "probabilities": [0.2, 0.3, 0.35, 0.15],
                },
            ),
        ],
        "employees": [
            Column(
                name="employee_id",
                type="int",
                distribution_params={"min": 1, "max": 200},
                unique=True,
            ),
            Column(
                name="name",
                type="text",
                distribution_params={"text_type": "name"},
            ),
            Column(
                name="email",
                type="text",
                distribution_params={"text_type": "email"},
            ),
            Column(
                name="role",
                type="categorical",
                distribution_params={
                    "choices": [
                        "Research Associate",
                        "Senior Scientist",
                        "Project Manager",
                        "Data Analyst",
                        "Clinical Coordinator",
                    ],
                    "probabilities": [0.35, 0.25, 0.15, 0.15, 0.1],
                },
            ),
            Column(
                name="hourly_rate",
                type="float",
                distribution_params={
                    "distribution": "normal",
                    "mean": 85.0,
                    "std": 25.0,
                    "min": 45.0,
                    "max": 200.0,
                    "decimals": 2,
                },
            ),
        ],
        "timesheets": [
            Column(
                name="entry_id",
                type="int",
                distribution_params={"min": 1, "max": 50000},
                unique=True,
            ),
            Column(
                name="project_id",
                type="foreign_key",
                distribution_params={},
            ),
            Column(
                name="employee_id",
                type="foreign_key",
                distribution_params={},
            ),
            Column(
                name="date",
                type="date",
                distribution_params={"start": "2020-01-01", "end": "2024-12-31"},
            ),
            Column(
                name="hours",
                type="float",
                distribution_params={
                    "distribution": "normal",
                    "mean": 7.5,
                    "std": 1.5,
                    "min": 0.5,
                    "max": 12.0,
                    "decimals": 1,
                },
            ),
            Column(
                name="billable",
                type="boolean",
                distribution_params={"probability": 0.85},
            ),
            Column(
                name="activity_type",
                type="categorical",
                distribution_params={
                    "choices": [
                        "Research",
                        "Analysis",
                        "Documentation",
                        "Meeting",
                        "Training",
                    ],
                    "probabilities": [0.4, 0.25, 0.2, 0.1, 0.05],
                },
            ),
        ],
    },
    relationships=[
        Relationship(
            parent_table="research_projects",
            child_table="timesheets",
            parent_key="project_id",
            child_key="project_id",
        ),
        Relationship(
            parent_table="employees",
            child_table="timesheets",
            parent_key="employee_id",
            child_key="employee_id",
        ),
    ],
)


def main():
    """Run the pharma demo."""
    print("=" * 70)
    print("Misata Demo: Pharma Services Company (JMAN-style)")
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
    
    print("\nResearch Projects (first 5 rows):")
    print(data["research_projects"].head())
    
    print("\nEmployees (first 5 rows):")
    print(data["employees"].head())
    
    print("\nTimesheets (first 5 rows):")
    print(data["timesheets"].head())
    
    # Analytics
    print("\n" + "=" * 70)
    print("Quick Analytics")
    print("=" * 70)
    
    projects = data["research_projects"]
    timesheets = data["timesheets"]
    
    print("\nProjects by Therapeutic Area:")
    print(projects["therapeutic_area"].value_counts())
    
    print("\nProjects by Phase:")
    print(projects["phase"].value_counts())
    
    # Merge for deeper analysis
    merged = timesheets.merge(
        projects[["project_id", "therapeutic_area", "phase"]],
        on="project_id"
    )
    
    print("\nTotal Hours by Therapeutic Area:")
    hours_by_area = merged.groupby("therapeutic_area")["hours"].sum().sort_values(ascending=False)
    print(hours_by_area)
    
    print("\nTotal Hours by Phase:")
    hours_by_phase = merged.groupby("phase")["hours"].sum().sort_values(ascending=False)
    print(hours_by_phase)
    
    # Export to CSV
    output_dir = "./examples/pharma_demo_output"
    print(f"\nExporting to {output_dir}...")
    simulator.export_to_csv(output_dir)
    
    print("\n✓ Demo complete!")
    print(f"  Check {output_dir} for CSV files")
    print("  This is similar to the JMAN Group pharma services project!")


if __name__ == "__main__":
    main()
