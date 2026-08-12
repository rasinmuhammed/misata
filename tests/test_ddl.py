"""
Tests for the SQL DDL reader.

`from_ddl` had one test before this file existed, which is why it could not
handle the single most common shape in real SQL: a plural table whose primary
key is singular. `CREATE TABLE customers (customer_id INT PRIMARY KEY, ...)`
produced a schema that refused to generate, because the key was read as a
reference to a `customer` table nobody had written.
"""

import warnings

import pytest

import misata
from misata.ddl import from_ddl


def rels(schema):
    return {(r.parent_table, r.parent_key, r.child_table, r.child_key)
            for r in schema.relationships}


def column(schema, table, name):
    return next(c for c in schema.get_columns(table) if c.name == name)


# ── A table's own key is not a foreign key ────────────────────────────────────

def test_singular_key_on_plural_table_is_not_a_foreign_key():
    schema = from_ddl(
        "CREATE TABLE customers (customer_id INT PRIMARY KEY, name VARCHAR(80));"
    )
    assert rels(schema) == set()
    assert column(schema, "customers", "customer_id").type != "foreign_key"


def test_table_level_primary_key_is_respected():
    schema = from_ddl("""
        CREATE TABLE customers (
            customer_id INT,
            name VARCHAR(80),
            PRIMARY KEY (customer_id)
        );
    """)
    assert rels(schema) == set()
    assert column(schema, "customers", "customer_id").type != "foreign_key"


def test_named_primary_key_constraint_is_respected():
    schema = from_ddl("""
        CREATE TABLE customers (
            customer_id INT,
            CONSTRAINT pk_customers PRIMARY KEY (customer_id)
        );
    """)
    assert rels(schema) == set()


def test_composite_primary_key_columns_are_all_guarded():
    schema = from_ddl("""
        CREATE TABLE order_items (
            order_id INT,
            item_id INT,
            PRIMARY KEY (order_id, item_id)
        );
    """)
    assert rels(schema) == set()


# ── Inference still works where it should ─────────────────────────────────────

def test_singular_reference_resolves_to_the_plural_table():
    schema = from_ddl("""
        CREATE TABLE categories (category_id INT PRIMARY KEY, title VARCHAR(50));
        CREATE TABLE products (product_id INT PRIMARY KEY, category_id INT);
    """)
    assert ("categories", "category_id", "products", "category_id") in rels(schema)


def test_y_to_ies_plural_resolves():
    schema = from_ddl("""
        CREATE TABLE companies (company_id INT PRIMARY KEY, name VARCHAR(50));
        CREATE TABLE staff (staff_id INT PRIMARY KEY, company_id INT);
    """)
    assert ("companies", "company_id", "staff", "company_id") in rels(schema)


def test_inferred_key_points_at_a_column_that_exists():
    """The `_id` rule guesses a parent key of `id`, which is usually wrong."""
    schema = from_ddl("""
        CREATE TABLE categories (category_id INT PRIMARY KEY);
        CREATE TABLE products (product_id INT PRIMARY KEY, category_id INT);
    """)
    parent_keys = {r.parent_key for r in schema.relationships}
    assert parent_keys == {"category_id"}


def test_rails_style_id_column_still_infers():
    schema = from_ddl("""
        CREATE TABLE categories (id INT PRIMARY KEY, title VARCHAR(50));
        CREATE TABLE products (id INT PRIMARY KEY, category_id INT);
    """)
    assert ("categories", "id", "products", "category_id") in rels(schema)


def test_infer_fks_false_disables_the_rule():
    schema = from_ddl("""
        CREATE TABLE categories (category_id INT PRIMARY KEY);
        CREATE TABLE products (product_id INT PRIMARY KEY, category_id INT);
    """, infer_fks=False)
    assert rels(schema) == set()


# ── Explicit constraints win, and bad ones do not corrupt the schema ──────────

def test_explicit_references_is_used_as_written():
    schema = from_ddl("""
        CREATE TABLE customers (customer_id INT PRIMARY KEY);
        CREATE TABLE orders (
            order_id INT PRIMARY KEY,
            buyer_id INT REFERENCES customers(customer_id)
        );
    """)
    assert ("customers", "customer_id", "orders", "buyer_id") in rels(schema)


def test_standalone_foreign_key_constraint_is_used():
    schema = from_ddl("""
        CREATE TABLE customers (customer_id INT PRIMARY KEY);
        CREATE TABLE orders (
            order_id INT PRIMARY KEY,
            buyer_id INT,
            FOREIGN KEY (buyer_id) REFERENCES customers(customer_id)
        );
    """)
    assert ("customers", "customer_id", "orders", "buyer_id") in rels(schema)


def test_reference_to_a_missing_table_demotes_the_column():
    """
    Dropping the relationship but leaving the column typed foreign_key produced
    a schema that could not generate, and an error message telling the caller to
    add a relationship to a table that does not exist.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        schema = from_ddl("""
            CREATE TABLE orders (
                order_id INT PRIMARY KEY,
                buyer_id INT REFERENCES people(person_id)
            );
        """)
    assert rels(schema) == set()
    assert column(schema, "orders", "buyer_id").type != "foreign_key"
    misata.generate_from_schema(schema)  # must not raise


# ── End to end ────────────────────────────────────────────────────────────────

def test_a_plain_schema_generates_with_every_key_resolving():
    schema = from_ddl("""
        CREATE TABLE customers (customer_id INT PRIMARY KEY, name VARCHAR(80));
        CREATE TABLE categories (category_id INT PRIMARY KEY, title VARCHAR(50));
        CREATE TABLE orders (
            order_id INT PRIMARY KEY,
            customer_id INT REFERENCES customers(customer_id),
            category_id INT,
            amount DECIMAL(10,2),
            order_date DATE
        );
    """, default_rows=120)

    tables = misata.generate_from_schema(schema)
    assert set(tables) == {"customers", "categories", "orders"}

    for parent, key, child in [("customers", "customer_id", "orders"),
                               ("categories", "category_id", "orders")]:
        valid = set(tables[parent][key])
        orphans = [v for v in tables[child][key] if v not in valid]
        assert orphans == [], f"{child}.{key} has {len(orphans)} orphans"


@pytest.mark.parametrize("ddl", [
    "CREATE TABLE t (id SERIAL PRIMARY KEY, v INT);",
    'CREATE TABLE "users" ("user_id" INTEGER PRIMARY KEY, "email" TEXT);',
    "CREATE TABLE IF NOT EXISTS public.events (event_id BIGINT PRIMARY KEY, ts TIMESTAMP);",
])
def test_common_dialect_spellings_generate(ddl):
    misata.generate_from_schema(from_ddl(ddl, default_rows=20))
