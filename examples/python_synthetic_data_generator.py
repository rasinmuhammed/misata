"""
Example: Python synthetic data generator with Misata.

This is a simple rule-based example that starts from a story,
builds a schema, generates data, and writes CSV files.
"""

from misata import DataSimulator
from misata.story_parser import StoryParser


def main() -> None:
    story = "An ecommerce company with 5K customers, repeat orders, and a spike in November"

    config = StoryParser().parse(story)
    simulator = DataSimulator(config)

    result = simulator.generate_with_reports(sample_size=1000)
    simulator.export_to_csv("./examples/output/python_synthetic_data_generator")

    print("Generated tables:")
    for table_name, row_count in result.table_row_counts.items():
        print(f"  {table_name}: {row_count:,} rows")

    print()
    print(result.validation_report.summary())


if __name__ == "__main__":
    main()
