"""
Example: database seeding with PostgreSQL.

Update the DB URL before running this script.
"""

from misata import seed_database
from misata.story_parser import StoryParser


def main() -> None:
    config = StoryParser().parse(
        "A SaaS company with users, subscriptions, invoices, and support tickets"
    )

    db_url = "postgresql://user:password@localhost:5432/misata_demo"

    report = seed_database(
        config,
        db_url,
        create=True,
        truncate=True,
        batch_size=5000,
    )

    print(f"Seeded {report.total_rows:,} rows into {report.db_url}")
    for table_name, row_count in report.table_rows.items():
        print(f"  {table_name}: {row_count:,}")


if __name__ == "__main__":
    main()
