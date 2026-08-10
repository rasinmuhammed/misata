"""Tests for `misata seed`: introspect a live database, fill it with
referentially-intact data, and verify every foreign key against the DB itself.

SQLite is used as the live database (stdlib, no server needed); the code path
is identical to Postgres apart from the driver.
"""

import sqlite3

import pandas as pd

import pytest
from click.testing import CliRunner

from misata.cli import main, _prune_config_for_skip
from misata.db import (
    table_row_counts,
    verify_referential_integrity,
)
from misata.introspect import schema_from_db


SCHEMA = """
CREATE TABLE customers (
  id INTEGER PRIMARY KEY,
  name TEXT,
  email TEXT,
  country TEXT
);
CREATE TABLE products (
  id INTEGER PRIMARY KEY,
  name TEXT,
  price REAL,
  category TEXT
);
CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER REFERENCES customers(id),
  product_id INTEGER REFERENCES products(id),
  quantity INTEGER,
  amount REAL,
  status TEXT
);
CREATE TABLE schema_migrations (
  version TEXT PRIMARY KEY
);
"""


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "app.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO schema_migrations VALUES ('20240101_init')")
    conn.commit()
    conn.close()
    return f"sqlite:///{path}"


def test_introspection_finds_foreign_keys(db):
    config = schema_from_db(db, default_rows=20)
    names = {t.name for t in config.tables}
    assert {"customers", "products", "orders"} <= names
    rels = {(r.child_table, r.child_key, r.parent_table) for r in config.relationships}
    assert ("orders", "customer_id", "customers") in rels
    assert ("orders", "product_id", "products") in rels


def test_seed_fills_db_and_verifies_integrity(db):
    result = CliRunner().invoke(
        main,
        ["seed", db, "--rows", "40", "--skip", "schema_migrations", "--yes"],
    )
    assert result.exit_code == 0, result.output
    # The success line now states how many keys were actually checked. It used
    # to read "Every foreign key resolves" even when none had been.
    assert "foreign key(s) resolve in the database" in result.output
    assert "All 2 foreign key(s)" in result.output

    counts = table_row_counts(db, ["customers", "products", "orders", "schema_migrations"])
    assert counts["customers"] == 40
    assert counts["products"] > 0
    assert counts["orders"] > 0
    # A skipped table is left exactly as it was.
    assert counts["schema_migrations"] == 1

    config = schema_from_db(db, default_rows=40, include_tables=["customers", "products", "orders"])
    integrity = verify_referential_integrity(config, db)
    assert integrity.verified
    assert integrity.total_orphans == 0
    assert len(integrity.relationships) == 2


def test_dry_run_writes_nothing(db):
    result = CliRunner().invoke(
        main, ["seed", db, "--rows", "40", "--skip", "schema_migrations", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert "Dry run: nothing was written" in result.output
    assert table_row_counts(db, ["customers"])["customers"] == 0


def test_refuses_nonempty_without_truncate(db):
    args = ["seed", db, "--rows", "20", "--skip", "schema_migrations", "--yes"]
    first = CliRunner().invoke(main, args)
    assert first.exit_code == 0, first.output
    # Second run must refuse rather than double-seed or silently skip.
    second = CliRunner().invoke(main, args)
    assert second.exit_code == 1
    assert "already contain data" in second.output


def test_truncate_reseeds_deterministically(db):
    args = ["seed", db, "--rows", "20", "--skip", "schema_migrations", "--truncate", "--yes"]
    CliRunner().invoke(main, args)
    counts = table_row_counts(db, ["customers", "products", "orders"])
    assert counts["customers"] == 20
    # A second truncate+reseed lands on the same row counts (seed is fixed).
    CliRunner().invoke(main, args)
    counts2 = table_row_counts(db, ["customers", "products", "orders"])
    assert counts == counts2


def test_append_references_existing_parent_rows(db, tmp_path):
    # Pre-populate parents with distinctive ids; append must draw child FKs
    # from those exact rows and leave the parents untouched.
    import sqlite3
    path = str(tmp_path / "app.db")
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO customers(id,name,email,country) VALUES (?,?,?,?)",
        [(101, "Alice", "a@x.com", "US"), (102, "Bob", "b@x.com", "UK")],
    )
    conn.executemany(
        "INSERT INTO products(id,name,price,category) VALUES (?,?,?,?)",
        [(9001, "Widget", 9.99, "A"), (9002, "Gadget", 19.99, "B")],
    )
    conn.commit()
    conn.close()

    result = CliRunner().invoke(
        main, ["seed", db, "--rows", "30", "--skip", "schema_migrations", "--append", "--yes"]
    )
    assert result.exit_code == 0, result.output

    counts = table_row_counts(db, ["customers", "products", "orders"])
    assert counts["customers"] == 2  # untouched
    assert counts["products"] == 2   # untouched
    assert counts["orders"] > 0      # seeded

    conn = sqlite3.connect(db.replace("sqlite:///", ""))
    cust = {r[0] for r in conn.execute("SELECT DISTINCT customer_id FROM orders")}
    prod = {r[0] for r in conn.execute("SELECT DISTINCT product_id FROM orders")}
    conn.close()
    assert cust <= {101, 102}
    assert prod <= {9001, 9002}


def test_append_refused_message_when_no_flag(db, tmp_path):
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "app.db"))
    conn.execute("INSERT INTO customers(id,name) VALUES (1,'x')")
    conn.commit()
    conn.close()
    result = CliRunner().invoke(
        main, ["seed", db, "--rows", "10", "--skip", "schema_migrations", "--yes"]
    )
    assert result.exit_code == 1
    assert "--append" in result.output  # the option is offered


class TestMcpSeedTool:
    """The MCP seed_database tool is the only Misata tool that writes to a
    user's database, so its guardrails are part of the contract.

    `mcp` ships in the dev extra so these run in CI; a minimal install skips
    them rather than erroring.
    """

    @pytest.fixture()
    def tool(self):
        pytest.importorskip("mcp", reason='needs: pip install "misata[mcp]"')
        # `mcp` being importable does not mean FastMCP is: mcp 2.0.0 removed it.
        try:
            from misata.mcp.server import seed_database
        except ImportError as exc:
            pytest.skip(f"misata.mcp.server is not importable here: {exc}")
        return seed_database

    def test_plans_by_default_and_writes_nothing(self, db, tool):
        r = tool(db_url=db, rows=20, skip_tables=["schema_migrations"])
        assert r["applied"] is False
        assert r["insert_order"][0] == "customers"  # parents first
        assert table_row_counts(db, ["customers"])["customers"] == 0

    def test_apply_writes_and_verifies_integrity(self, db, tool):
        r = tool(db_url=db, rows=20, apply=True, skip_tables=["schema_migrations"])
        assert r["applied"] is True
        assert r["total_rows"] > 0
        assert r["integrity"]["verified"] is True
        assert r["integrity"]["total_orphans"] == 0

    def test_refuses_nonempty_rather_than_guessing(self, db, tool):
        tool(db_url=db, rows=20, apply=True, skip_tables=["schema_migrations"])
        r = tool(db_url=db, rows=20, apply=True, skip_tables=["schema_migrations"])
        assert r["ok"] is False
        assert r["error"] == "TablesNotEmpty"
        # It must offer the choice, never pick a destructive default.
        assert "truncate" in r["suggestion"] and "append" in r["suggestion"]

    def test_truncate_and_append_are_mutually_exclusive(self, db, tool):
        r = tool(db_url=db, apply=True, truncate=True, append=True)
        assert r["ok"] is False
        assert r["error"] == "ConflictingOptions"

    def test_never_echoes_credentials(self, db, tool):
        import json
        r = tool(db_url=db, rows=20, skip_tables=["schema_migrations"])
        # The plan reports a database label; it must not carry a password.
        assert "SUPERSECRET" not in json.dumps(r)
        label = r["database"]
        assert "://" not in label or label.count("@") == 0


def test_skip_cascades_to_dependent_children(db):
    # Skipping a parent (customers) must also skip its child (orders), because
    # orders.customer_id could not resolve without referencing existing rows.
    config = schema_from_db(db, default_rows=10)
    pruned, effective = _prune_config_for_skip(config, {"customers"})
    assert "customers" in effective
    assert "orders" in effective  # cascaded
    assert "products" not in effective
    kept = {t.name for t in pruned.tables}
    assert "orders" not in kept and "products" in kept


def test_inferred_rollup_never_overwrites_a_declared_outcome_curve():
    """The canonical orders/order_items schema: a child with quantity+unit_price
    makes Misata infer parent.order_total = sum(line items). That roll-up runs
    after generation and used to silently clobber a declared monthly revenue
    curve (23% off, no warning). The declared target must win."""
    import warnings
    import misata

    targets = [120000.0, 118000.0, 135000.0]
    schema = {
        "name": "t", "seed": 7,
        "tables": {
            "orders": {"rows": 3000, "columns": {
                "order_id": {"type": "integer", "unique": True, "min": 1, "max": 99999},
                "order_date": {"type": "date", "min_date": "2025-01-01",
                               "max_date": "2025-03-31"},
                "order_total": {"type": "float", "min": 5.0, "max": 3000.0, "decimals": 2},
            }},
            "order_items": {"rows": 7000, "columns": {
                "order_item_id": {"type": "integer", "unique": True, "min": 1, "max": 99999},
                "order_id": {"type": "foreign_key",
                             "foreign_key": {"table": "orders", "column": "order_id"}},
                "quantity": {"type": "integer", "min": 1, "max": 5},
                "unit_price": {"type": "float", "min": 4.99, "max": 899.99, "decimals": 2},
            }},
        },
        "outcome_curves": [{
            "table": "orders", "column": "order_total", "time_column": "order_date",
            "time_unit": "month", "value_mode": "absolute", "start_date": "2025-01-01",
            "curve_points": [{"month": i + 1, "target_value": v}
                             for i, v in enumerate(targets)],
        }],
    }
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        orders = misata.generate_from_schema(misata.from_dict_schema(schema))["orders"]
        notes = [str(w.message) for w in caught if "outcome curve" in str(w.message)]

    orders["order_date"] = pd.to_datetime(orders["order_date"])
    got = orders.groupby(orders.order_date.dt.month)["order_total"].sum()
    for i, target in enumerate(targets):
        assert abs(got.get(i + 1, 0.0) - target) < 0.01, (
            f"month {i+1}: declared {target}, got {got.get(i+1, 0.0)}"
        )
    # and it must say so rather than dropping the roll-up silently
    assert notes, "dropping the roll-up should emit a warning"


class TestPostgresWritePath:
    """The Postgres path was never exercised against a real Postgres.

    Every test here covers a defect found by pointing `misata seed` at a live
    database shaped like a Supabase project. The suite ran green throughout,
    because it only ever seeded SQLite, where none of these code paths run.
    """

    def test_copy_is_entered_as_a_context_manager(self):
        """`cur.copy(sql, buf)` writes nothing and raises nothing.

        psycopg3's second positional argument is query *parameters*, not data,
        and the return value must be entered before a byte moves. Called the
        wrong way it silently inserted zero rows, the `except` fallback never
        fired, and the caller was told every row landed. `misata seed` reported
        success against Postgres while leaving the tables empty.
        """
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "misata" / "db.py"
        tree = ast.parse(src.read_text())

        bare_calls = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "copy"):
                continue
            if len(node.args) > 1:
                bare_calls.append(
                    f"line {node.lineno}: copy() given {len(node.args)} positional "
                    f"args; the second is query parameters, not data")

        entered = {
            id(item.context_expr)
            for node in ast.walk(tree) if isinstance(node, ast.With)
            for item in node.items
        }
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "copy"
                    and id(node) not in entered):
                bare_calls.append(
                    f"line {node.lineno}: copy() result never entered as a "
                    f"context manager, so nothing is written")

        assert not bare_calls, "\n  ".join(bare_calls)

    def test_an_empty_integrity_report_is_not_a_pass(self):
        """`all([])` is True. That is how it claimed to verify nothing."""
        from misata.db import IntegrityReport, RelationshipIntegrity

        assert IntegrityReport().verified is False
        assert IntegrityReport().complete is False

        checked = IntegrityReport(relationships=[
            RelationshipIntegrity(parent_table="a", parent_key="id",
                                  child_table="b", child_key="a_id", orphans=0)])
        assert checked.verified is True
        assert checked.complete is True

    def test_a_skipped_check_is_not_a_complete_one(self):
        from misata.db import IntegrityReport, RelationshipIntegrity

        partial = IntegrityReport(
            relationships=[RelationshipIntegrity(
                parent_table="a", parent_key="id",
                child_table="b", child_key="a_id", orphans=0)],
            skipped=["c.a_id -> a.id: could not query"])
        assert partial.verified is True     # what ran, passed
        assert partial.complete is False    # but not everything ran


class TestUniqueForeignKey:
    """A unique FK is one-to-one, so it must be drawn without replacement.

    Supabase's `profiles.id -> auth.users.id` is the shape: the foreign key IS
    the primary key. Sampling with replacement produced duplicate ids and
    Postgres rejected the insert on `profiles_pkey`.
    """

    def _schema(self, child_rows: int):
        from misata.schema import Column, Relationship, SchemaConfig, Table
        return SchemaConfig(
            name="one_to_one",
            tables=[Table(name="users", row_count=25),
                    Table(name="profiles", row_count=child_rows)],
            columns={
                "users": [Column(name="id", type="int", distribution_params={},
                                 unique=True)],
                "profiles": [
                    Column(name="id", type="foreign_key", unique=True,
                           distribution_params={"references": "users.id"}),
                    Column(name="username", type="text", distribution_params={}),
                ],
            },
            relationships=[Relationship(parent_table="users", child_table="profiles",
                                        parent_key="id", child_key="id")],
            seed=7,
        )

    def test_values_are_distinct(self):
        import misata
        tables = misata.generate_from_schema(self._schema(25))
        ids = tables["profiles"]["id"]
        assert ids.is_unique, f"{len(ids) - ids.nunique()} duplicate(s)"
        assert set(ids).issubset(set(tables["users"]["id"]))

    def test_fewer_children_than_parents_still_distinct(self):
        import misata
        ids = misata.generate_from_schema(self._schema(10))["profiles"]["id"]
        assert len(ids) == 10 and ids.is_unique

    def test_asking_for_more_than_exist_is_refused(self):
        """There is no valid answer, so inventing one would be the bug."""
        import pytest
        import misata
        with pytest.raises(ValueError, match="at most one row per parent"):
            misata.generate_from_schema(self._schema(40))


class TestUniqueTextColumns:
    """A column declared unique must hold that through every pass.

    Found by seeding a Rails-shaped schema: `tags.name varchar UNIQUE` filled
    from a finite pool of company names, and Postgres rejected the insert on
    `tags_name_key`. Two separate defects were behind it.
    """

    def _schema(self, rows=1500):
        from misata.schema import Column, SchemaConfig, Table
        return SchemaConfig(
            name="unique_text", seed=5,
            tables=[Table(name="users", row_count=rows)],
            columns={"users": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 9_999_999}),
                Column(name="name", type="text", unique=True,
                       distribution_params={"text_type": "name"}),
                Column(name="email", type="text", unique=True,
                       distribution_params={"text_type": "email"}),
                Column(name="company", type="text", unique=True,
                       distribution_params={"text_type": "company"}),
            ]},
        )

    def test_every_unique_text_column_is_actually_unique(self):
        """The text branch checked `unique` last, after four earlier returns
        (reference pools, conditional vocab, capsule vocab, patterns) that each
        ignored it. A finite pool then collides as rows approach pool size."""
        import misata
        df = misata.generate_from_schema(self._schema())["users"]
        for col in ("id", "name", "email", "company"):
            dupes = len(df[col]) - df[col].nunique()
            assert dupes == 0, f"{col}: {dupes} duplicate(s) in a unique column"

    def test_uniqueness_survives_the_realism_pass(self):
        """`_fix_email_from_name` derives the address from the person's name,
        which is correct and which reintroduces duplicates the generator had
        already resolved. Enforcing it at generation alone was not enough."""
        import misata
        emails = misata.generate_from_schema(self._schema())["users"]["email"]
        assert emails.is_unique
        assert all("@" in str(v) for v in emails), (
            "deduplication must not stop an email looking like an email")

    def test_it_holds_across_batches(self):
        """A table generated in several passes must be unique over the whole
        table, not within each chunk."""
        import misata
        from misata.simulator import DataSimulator
        import pandas as pd

        sim = DataSimulator(self._schema(rows=2500), batch_size=500)
        frames = {}
        for name, batch in sim.generate_all():
            frames.setdefault(name, []).append(batch)
        users = pd.concat(frames["users"], ignore_index=True)
        assert users["email"].is_unique, (
            f"{len(users) - users['email'].nunique()} duplicate(s) across batches")


class TestUniqueConstraintIntrospection:
    """A UNIQUE constraint is not a PRIMARY KEY.

    Only primary keys were read, so `tags.name varchar UNIQUE` was introspected
    as an ordinary column. Every Rails, Laravel and Django schema is full of
    these (email, slug, name), which is why seeding failed on most real
    applications rather than on an exotic one.
    """

    def _db(self, tmp_path, ddl):
        import sqlite3
        path = tmp_path / "app.db"
        con = sqlite3.connect(path)
        con.executescript(ddl)
        con.commit()
        con.close()
        return f"sqlite:///{path}"

    def test_a_unique_column_is_marked_unique(self, tmp_path):
        from misata.introspect import schema_from_db
        url = self._db(tmp_path, """
            CREATE TABLE tags (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL UNIQUE,
              blurb TEXT
            );
        """)
        cols = {c.name: c for c in schema_from_db(url).columns["tags"]}
        assert cols["id"].unique, "primary key"
        assert cols["name"].unique, "declared UNIQUE but introspected as ordinary"
        assert not cols["blurb"].unique, "must not mark everything unique"
