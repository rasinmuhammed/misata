import sqlite3
import tempfile

from misata.db import seed_database
from misata.schema import Column, Relationship, SchemaConfig, Table


def _sample_config() -> SchemaConfig:
    tables = [
        Table(name="users", row_count=10),
        Table(name="orders", row_count=20),
    ]

    columns = {
        "users": [
            Column(name="id", type="int", unique=True),
            Column(name="name", type="text", distribution_params={"text_type": "name"}),
            Column(name="created_at", type="date"),
        ],
        "orders": [
            Column(name="id", type="int", unique=True),
            Column(name="user_id", type="foreign_key"),
            Column(name="quantity", type="int", distribution_params={"min": 1, "max": 5}),
            Column(name="unit_price", type="float", distribution_params={"min": 5, "max": 50}),
            Column(name="total", type="float", distribution_params={"min": 5, "max": 250}),
        ],
    }

    relationships = [
        Relationship(
            parent_table="users",
            child_table="orders",
            parent_key="id",
            child_key="user_id",
        )
    ]

    return SchemaConfig(
        name="TestDBSeed",
        tables=tables,
        columns=columns,
        relationships=relationships,
    )


def test_seed_database_sqlite():
    config = _sample_config()
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/test.db"
        db_url = f"sqlite:///{db_path}"

        report = seed_database(config, db_url, create=True, truncate=False, batch_size=5)

        assert report.total_rows == 30
        assert report.table_rows["users"] == 10
        assert report.table_rows["orders"] == 20

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        assert cur.fetchone()[0] == 10
        cur.execute("SELECT COUNT(*) FROM orders")
        assert cur.fetchone()[0] == 20

        cur.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id NOT IN (SELECT id FROM users)"
        )
        assert cur.fetchone()[0] == 0
        conn.close()
