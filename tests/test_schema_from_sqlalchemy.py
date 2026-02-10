import pytest

from misata.introspect import schema_from_sqlalchemy


def test_schema_from_sqlalchemy():
    sqlalchemy = pytest.importorskip("sqlalchemy")

    from sqlalchemy import Column as SAColumn
    from sqlalchemy import ForeignKey, Integer, MetaData, String, Table

    metadata = MetaData()
    users = Table(
        "users",
        metadata,
        SAColumn("id", Integer, primary_key=True),
        SAColumn("name", String),
    )
    Table(
        "orders",
        metadata,
        SAColumn("id", Integer, primary_key=True),
        SAColumn("user_id", Integer, ForeignKey(users.c.id)),
    )

    schema = schema_from_sqlalchemy(metadata, default_rows=5)
    assert {t.name for t in schema.tables} == {"users", "orders"}
    assert any(r.child_table == "orders" and r.parent_table == "users" for r in schema.relationships)
