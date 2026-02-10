import sqlite3
import tempfile

from misata.introspect import schema_from_db


def test_schema_from_db_sqlite():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/introspect.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        cur.execute(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, "
            "FOREIGN KEY(user_id) REFERENCES users(id))"
        )
        conn.commit()
        conn.close()

        schema = schema_from_db(f"sqlite:///{db_path}", default_rows=10)

        assert {t.name for t in schema.tables} == {"users", "orders"}
        assert "users" in schema.columns and "orders" in schema.columns
        assert any(r.child_table == "orders" and r.parent_table == "users" for r in schema.relationships)
