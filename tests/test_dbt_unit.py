"""Tests for manifest-driven dbt unit test generation.

The manifest fixture below is a trimmed copy of real `dbt parse` output from
dbt-core 1.9.10, so the shapes asserted here are the shapes dbt actually
produces rather than an assumed schema.
"""

import json

import pandas as pd
import pytest
from click.testing import CliRunner

from misata.cli import main
from misata.dbt_unit import (
    ManifestError,
    build_plan,
    coerce_to_declared_types,
    coverage,
    extract_foreign_keys,
    find_manifest,
    fixture_csv,
    generate_fixtures,
    load_manifest,
    map_data_type,
    render_unit_test_yaml,
    resolve_model,
)


def _manifest() -> dict:
    """A two-staging-model + one-mart project with a relationships test."""
    return {
        "metadata": {"project_name": "jaffle"},
        "unit_tests": {},
        "sources": {
            "source.jaffle.raw.raw_customers": {
                "resource_type": "source",
                "source_name": "raw",
                "name": "raw_customers",
                "columns": {
                    "id": {"data_type": "integer"},
                    "first_name": {"data_type": "varchar"},
                },
            }
        },
        "nodes": {
            "model.jaffle.stg_customers": {
                "resource_type": "model",
                "name": "stg_customers",
                "language": "sql",
                "config": {"materialized": "view"},
                "depends_on": {"nodes": ["source.jaffle.raw.raw_customers"]},
                "columns": {
                    "customer_id": {"data_type": "integer"},
                    "first_name": {"data_type": "varchar"},
                },
            },
            "model.jaffle.stg_orders": {
                "resource_type": "model",
                "name": "stg_orders",
                "language": "sql",
                "config": {"materialized": "view"},
                "depends_on": {"nodes": ["source.jaffle.raw.raw_customers"]},
                "columns": {
                    "order_id": {"data_type": "integer"},
                    "customer_id": {"data_type": "integer"},
                    "order_date": {"data_type": "date"},
                    "shipped": {"data_type": "boolean"},
                },
            },
            "model.jaffle.customer_orders": {
                "resource_type": "model",
                "name": "customer_orders",
                "language": "sql",
                "config": {"materialized": "view"},
                "depends_on": {
                    "nodes": ["model.jaffle.stg_customers", "model.jaffle.stg_orders"]
                },
                "columns": {
                    "customer_id": {"data_type": "integer"},
                    "order_count": {"data_type": "bigint"},
                },
            },
            # A python model: dbt cannot unit test these.
            "model.jaffle.py_model": {
                "resource_type": "model",
                "name": "py_model",
                "language": "python",
                "config": {"materialized": "table"},
                "depends_on": {"nodes": ["model.jaffle.stg_orders"]},
                "columns": {},
            },
            # The relationships test that declares the real FK.
            "test.jaffle.relationships_stg_orders_customer_id.abc123": {
                "resource_type": "test",
                "name": "relationships_stg_orders_customer_id",
                "attached_node": "model.jaffle.stg_orders",
                "column_name": "customer_id",
                "depends_on": {"nodes": ["model.jaffle.stg_customers"]},
                "test_metadata": {
                    "name": "relationships",
                    "kwargs": {
                        "to": "ref('stg_customers')",
                        "field": "customer_id",
                        "column_name": "customer_id",
                    },
                },
            },
        },
    }


# ─── type mapping ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "declared,expected",
    [
        ("integer", "integer"),
        ("bigint", "integer"),
        ("varchar(255)", "string"),
        ("text", "string"),
        ("date", "date"),
        ("timestamp without time zone", "datetime"),
        ("boolean", "boolean"),
        ("numeric(10,2)", "float"),
        ("double precision", "float"),
        (None, "string"),          # undocumented falls back, never raises
        ("some_custom_type", "string"),
    ],
)
def test_data_type_mapping(declared, expected):
    assert map_data_type(declared) == expected


def test_timestamp_maps_before_time():
    """Ordering matters: 'timestamp' must not be caught by the 'time' pattern."""
    assert map_data_type("timestamp") == "datetime"
    assert map_data_type("time") == "time"


# ─── manifest reading ──────────────────────────────────────────────────────


def test_find_manifest_reports_missing_manifest_distinctly(tmp_path):
    (tmp_path / "dbt_project.yml").write_text("name: x\n")
    with pytest.raises(ManifestError, match="no target/manifest.json"):
        find_manifest(tmp_path)


def test_find_manifest_reports_missing_project(tmp_path):
    with pytest.raises(ManifestError, match="No dbt project found"):
        find_manifest(tmp_path)


def test_load_manifest_rejects_non_manifest(tmp_path):
    bad = tmp_path / "manifest.json"
    bad.write_text('{"not": "a manifest"}')
    with pytest.raises(ManifestError, match="does not look like a dbt manifest"):
        load_manifest(bad)


def test_resolve_model_lists_candidates_on_miss():
    with pytest.raises(ManifestError) as exc:
        resolve_model(_manifest(), "nope")
    assert "customer_orders" in str(exc.value)


# ─── FK extraction ─────────────────────────────────────────────────────────


def test_foreign_keys_come_from_relationships_tests():
    fks = extract_foreign_keys(_manifest())
    assert fks == [
        (
            "model.jaffle.stg_orders",
            "customer_id",
            "model.jaffle.stg_customers",
            "customer_id",
        )
    ]


# ─── planning ──────────────────────────────────────────────────────────────


def test_plan_resolves_refs_and_sources_correctly():
    plan = build_plan(_manifest(), "customer_orders", rows=4)
    assert plan.usable
    exprs = {i.ref_expr for i in plan.inputs}
    assert exprs == {"ref('stg_customers')", "ref('stg_orders')"}
    assert plan.model_columns == ["customer_id", "order_count"]


def test_plan_renders_source_calls_not_refs():
    plan = build_plan(_manifest(), "stg_customers")
    assert [i.ref_expr for i in plan.inputs] == ["source('raw', 'raw_customers')"]


def test_plan_attaches_fk_only_when_both_sides_are_inputs():
    plan = build_plan(_manifest(), "customer_orders")
    orders = next(i for i in plan.inputs if i.name == "stg_orders")
    assert orders.foreign_keys == [
        ("customer_id", "model.jaffle.stg_customers", "customer_id")
    ]
    # stg_orders' own test points at stg_customers, but when stg_orders is the
    # model under test its parent is not an input, so no FK is claimed.
    plan2 = build_plan(_manifest(), "stg_orders")
    assert all(not i.foreign_keys for i in plan2.inputs)


def test_plan_refuses_python_models():
    plan = build_plan(_manifest(), "py_model")
    assert not plan.usable
    assert "SQL models only" in plan.skipped


def test_plan_refuses_materialized_views():
    m = _manifest()
    m["nodes"]["model.jaffle.customer_orders"]["config"]["materialized"] = (
        "materialized_view"
    )
    plan = build_plan(m, "customer_orders")
    assert not plan.usable
    assert "materialized view" in plan.skipped


def test_plan_refuses_model_with_no_upstream():
    m = _manifest()
    m["nodes"]["model.jaffle.customer_orders"]["depends_on"]["nodes"] = []
    plan = build_plan(m, "customer_orders")
    assert not plan.usable
    assert "no upstream" in plan.skipped


def test_plan_will_not_guess_undocumented_columns():
    """Refusing beats guessing: a wrong column name produces a broken fixture."""
    m = _manifest()
    for uid in ("model.jaffle.stg_customers", "model.jaffle.stg_orders"):
        m["nodes"][uid]["columns"] = {}
    plan = build_plan(m, "customer_orders")
    assert not plan.usable
    assert "will not guess" in plan.skipped


def test_plan_flags_partially_undocumented_inputs():
    m = _manifest()
    m["nodes"]["model.jaffle.stg_orders"]["columns"] = {}
    plan = build_plan(m, "customer_orders")
    assert plan.usable  # one input is still documented
    assert any("no documented columns" in w for w in plan.warnings)


# ─── fixture generation ────────────────────────────────────────────────────


def test_fixtures_have_resolving_foreign_keys():
    """The core claim: keys agree across fixtures, so the model's join works."""
    plan = build_plan(_manifest(), "customer_orders", rows=6)
    fx = generate_fixtures(plan, seed=11)
    customers = fx["customer_orders__stg_customers"]
    orders = fx["customer_orders__stg_orders"]
    assert len(customers) == 6 and len(orders) == 6
    orphans = (~orders["customer_id"].isin(customers["customer_id"])).sum()
    assert orphans == 0
    assert customers["customer_id"].is_unique


def test_fixtures_are_deterministic():
    m = _manifest()
    a = generate_fixtures(build_plan(m, "customer_orders", rows=5), seed=3)
    b = generate_fixtures(build_plan(m, "customer_orders", rows=5), seed=3)
    for key in a:
        pd.testing.assert_frame_equal(a[key], b[key])


def test_fixture_columns_follow_manifest_order():
    plan = build_plan(_manifest(), "customer_orders", rows=3)
    fx = generate_fixtures(plan, seed=1)
    orders_input = next(i for i in plan.inputs if i.name == "stg_orders")
    assert list(fx["customer_orders__stg_orders"].columns) == list(orders_input.columns)


# ─── type-faithful serialisation ───────────────────────────────────────────


def test_date_columns_serialise_without_a_time_component():
    """The engine's `date` type yields a timestamp; a date column must not."""
    df = pd.DataFrame({"d": pd.to_datetime(["2024-03-05 13:45:12"])})
    out = coerce_to_declared_types(df, {"d": "date"})
    assert out["d"].iloc[0] == "2024-03-05"


def test_integer_columns_never_serialise_as_floats():
    df = pd.DataFrame({"n": [1.0, 2.0]})
    csv = fixture_csv(df, {"n": "integer"})
    assert "1.0" not in csv
    assert csv.splitlines()[1] == "1"


def test_boolean_columns_serialise_lowercase():
    df = pd.DataFrame({"b": [True, False]})
    csv = fixture_csv(df, {"b": "boolean"})
    assert csv.splitlines()[1:] == ["true", "false"]


def test_datetime_truncates_to_seconds():
    df = pd.DataFrame({"t": pd.to_datetime(["2024-01-01 10:20:30.123456789"])})
    out = coerce_to_declared_types(df, {"t": "datetime"})
    assert out["t"].iloc[0] == "2024-01-01 10:20:30"


def test_fixture_csv_has_header_and_no_index():
    plan = build_plan(_manifest(), "customer_orders", rows=2)
    fx = generate_fixtures(plan, seed=1)
    inp = next(i for i in plan.inputs if i.name == "stg_customers")
    csv = fixture_csv(fx[inp.fixture_name], inp.columns)
    assert csv.splitlines()[0] == "customer_id,first_name"


# ─── YAML rendering ────────────────────────────────────────────────────────


def test_yaml_declares_every_upstream_input():
    """dbt fails compilation if a ref the model uses is missing from `given`."""
    plan = build_plan(_manifest(), "customer_orders", rows=3)
    yaml_text = render_unit_test_yaml(plan)
    assert "unit_tests:" in yaml_text
    assert "model: customer_orders" in yaml_text
    assert "input: ref('stg_customers')" in yaml_text
    assert "input: ref('stg_orders')" in yaml_text


def test_yaml_parses_as_valid_yaml_and_matches_dbt_schema():
    yaml = pytest.importorskip("yaml")
    plan = build_plan(_manifest(), "customer_orders", rows=3)
    doc = yaml.safe_load(render_unit_test_yaml(plan))
    assert list(doc.keys()) == ["unit_tests"]
    test = doc["unit_tests"][0]
    assert set(test) >= {"name", "model", "given", "expect"}
    assert test["model"] == "customer_orders"
    for given in test["given"]:
        assert "input" in given
        assert given["format"] == "csv"
    assert test["expect"]["format"] == "csv"


def test_yaml_emits_real_expect_headers_but_no_invented_values():
    plan = build_plan(_manifest(), "customer_orders", rows=3)
    yaml_text = render_unit_test_yaml(plan)
    assert "customer_id,order_count" in yaml_text
    assert "TODO" in yaml_text  # values are the author's call, not ours


def test_yaml_states_the_build_prerequisite():
    """Learned from running real dbt: CSV fixtures need the relation to exist."""
    plan = build_plan(_manifest(), "customer_orders", rows=3)
    assert "dbt build" in render_unit_test_yaml(plan)


# ─── coverage ──────────────────────────────────────────────────────────────


def test_coverage_lists_models_and_flags_missing_tests():
    rows = coverage(_manifest())
    by_name = {r.name: r for r in rows}
    assert not by_name["customer_orders"].has_unit_test
    assert by_name["customer_orders"].upstream_count == 2
    assert by_name["py_model"].documented is False


def test_coverage_detects_an_existing_unit_test():
    m = _manifest()
    m["unit_tests"] = {
        "unit_test.jaffle.customer_orders.t": {
            "model": "customer_orders",
            "depends_on": {"nodes": ["model.jaffle.customer_orders"]},
        }
    }
    by_name = {r.name: r for r in coverage(m)}
    assert by_name["customer_orders"].has_unit_test


# ─── CLI ───────────────────────────────────────────────────────────────────


def _write_project(tmp_path) -> None:
    (tmp_path / "dbt_project.yml").write_text("name: jaffle\nversion: '1.0'\n")
    target = tmp_path / "target"
    target.mkdir()
    (target / "manifest.json").write_text(json.dumps(_manifest()))


def test_cli_coverage_runs(tmp_path):
    _write_project(tmp_path)
    r = CliRunner().invoke(
        main, ["dbt-unit-test", "--coverage", "--project-dir", str(tmp_path)]
    )
    assert r.exit_code == 0, r.output
    assert "customer_orders" in r.output


def test_cli_dry_run_writes_nothing(tmp_path):
    _write_project(tmp_path)
    r = CliRunner().invoke(
        main,
        ["dbt-unit-test", "--select", "customer_orders", "--project-dir", str(tmp_path)],
    )
    assert r.exit_code == 0, r.output
    assert "Dry run" in r.output
    assert not (tmp_path / "tests" / "fixtures").exists()


def test_cli_write_creates_fixtures_and_yaml(tmp_path):
    _write_project(tmp_path)
    r = CliRunner().invoke(
        main,
        ["dbt-unit-test", "--select", "customer_orders", "--write",
         "--project-dir", str(tmp_path)],
    )
    assert r.exit_code == 0, r.output
    fixtures = tmp_path / "tests" / "fixtures"
    assert (fixtures / "customer_orders__stg_customers.csv").is_file()
    assert (fixtures / "customer_orders__stg_orders.csv").is_file()
    assert (tmp_path / "models" / "_misata_unit_test_customer_orders.yml").is_file()


def test_cli_does_not_overwrite_without_force(tmp_path):
    _write_project(tmp_path)
    args = ["dbt-unit-test", "--select", "customer_orders", "--write",
            "--project-dir", str(tmp_path)]
    CliRunner().invoke(main, args)
    sentinel = tmp_path / "tests" / "fixtures" / "customer_orders__stg_customers.csv"
    sentinel.write_text("SENTINEL\n")
    r = CliRunner().invoke(main, args)
    assert r.exit_code == 0
    assert sentinel.read_text() == "SENTINEL\n"
    assert "--force" in r.output


def test_cli_errors_without_select_or_coverage(tmp_path):
    _write_project(tmp_path)
    r = CliRunner().invoke(main, ["dbt-unit-test", "--project-dir", str(tmp_path)])
    assert r.exit_code == 1
    assert "--coverage" in r.output


# ─── lessons from running against dbt-labs/jaffle_shop ─────────────────────
#
# Three defects only surfaced by running on a real project. jaffle_shop
# documents ONLY the columns that carry tests (stg_customers documents
# customer_id and nothing else, while the model selects three columns), it
# declares no data types at all, and it has no relationships tests anywhere.


def _partial_manifest() -> dict:
    """A manifest shaped like jaffle_shop: partial docs, no types, no FK tests."""
    return {
        "unit_tests": {},
        "sources": {},
        "nodes": {
            "model.jaffle_shop.stg_customers": {
                "resource_type": "model",
                "name": "stg_customers",
                "language": "sql",
                "config": {"materialized": "view"},
                "depends_on": {"nodes": ["model.jaffle_shop.raw_customers"]},
                "columns": {"customer_id": {}},          # no data_type, partial
            },
            "model.jaffle_shop.stg_orders": {
                "resource_type": "model",
                "name": "stg_orders",
                "language": "sql",
                "config": {"materialized": "view"},
                "depends_on": {"nodes": ["model.jaffle_shop.raw_orders"]},
                "columns": {"order_id": {}, "status": {}},
            },
            "model.jaffle_shop.raw_customers": {
                "resource_type": "model", "name": "raw_customers", "language": "sql",
                "config": {"materialized": "table"}, "depends_on": {"nodes": []},
                "columns": {"id": {}},
            },
            "model.jaffle_shop.raw_orders": {
                "resource_type": "model", "name": "raw_orders", "language": "sql",
                "config": {"materialized": "table"}, "depends_on": {"nodes": []},
                "columns": {"id": {}},
            },
            "model.jaffle_shop.customers": {
                "resource_type": "model",
                "name": "customers",
                "language": "sql",
                "config": {"materialized": "table"},
                "depends_on": {
                    "nodes": [
                        "model.jaffle_shop.stg_customers",
                        "model.jaffle_shop.stg_orders",
                    ]
                },
                "columns": {"customer_id": {}},
            },
        },
    }


def _catalog() -> dict:
    """The warehouse's real answer: every column, real types, real ordering."""
    return {
        "nodes": {
            "model.jaffle_shop.stg_customers": {
                "columns": {
                    "customer_id": {"type": "INTEGER", "index": 1},
                    "first_name": {"type": "VARCHAR", "index": 2},
                    "last_name": {"type": "VARCHAR", "index": 3},
                }
            },
            "model.jaffle_shop.stg_orders": {
                "columns": {
                    "order_id": {"type": "INTEGER", "index": 1},
                    "customer_id": {"type": "INTEGER", "index": 2},
                    "order_date": {"type": "DATE", "index": 3},
                    "status": {"type": "VARCHAR", "index": 4},
                }
            },
            "model.jaffle_shop.customers": {
                "columns": {
                    "customer_id": {"type": "INTEGER", "index": 1},
                    "amount_total": {"type": "DOUBLE", "index": 2},
                }
            },
        }
    }


def test_catalog_supplies_columns_the_manifest_omits():
    """Without this the fixture is missing columns the model actually selects."""
    plan = build_plan(_partial_manifest(), "customers", catalog=_catalog())
    stg_customers = next(i for i in plan.inputs if i.name == "stg_customers")
    # The manifest documents only customer_id; the catalog knows all three.
    assert list(stg_customers.columns) == ["customer_id", "first_name", "last_name"]
    assert stg_customers.columns["customer_id"] == "integer"


def test_catalog_column_order_follows_warehouse_ordinal():
    plan = build_plan(_partial_manifest(), "customers", catalog=_catalog())
    stg_orders = next(i for i in plan.inputs if i.name == "stg_orders")
    assert list(stg_orders.columns) == [
        "order_id", "customer_id", "order_date", "status",
    ]


def test_warns_when_no_catalog_is_available():
    plan = build_plan(_partial_manifest(), "customers")
    assert any("catalog.json" in w for w in plan.warnings)


def test_undeclared_id_columns_are_integers_not_text():
    """An id column full of prose is useless for a join."""
    plan = build_plan(_partial_manifest(), "customers")
    stg_customers = next(i for i in plan.inputs if i.name == "stg_customers")
    assert stg_customers.columns["customer_id"] == "integer"


def test_foreign_keys_are_inferred_when_no_relationships_test_exists():
    """jaffle_shop declares none, so without inference the join finds nothing."""
    plan = build_plan(_partial_manifest(), "customers", catalog=_catalog())
    stg_orders = next(i for i in plan.inputs if i.name == "stg_orders")
    assert stg_orders.foreign_keys == [
        ("customer_id", "model.jaffle_shop.stg_customers", "customer_id")
    ]
    assert any("inferred" in w for w in plan.warnings)


def test_inferred_fixtures_actually_join():
    plan = build_plan(_partial_manifest(), "customers", rows=5, catalog=_catalog())
    fx = generate_fixtures(plan, seed=5)
    customers = fx["customers__stg_customers"]
    orders = fx["customers__stg_orders"]
    assert set(orders["customer_id"]) <= set(customers["customer_id"])


def test_inference_requires_the_stem_to_name_the_parent():
    """Two tables sharing a column name is not a foreign key."""
    from misata.dbt_unit import UnitTestInput, infer_foreign_keys_by_name

    a = UnitTestInput("model.p.widgets", "widgets", "model", "ref('widgets')",
                      {"tenant_id": "integer"}, 3, "f_a")
    b = UnitTestInput("model.p.gadgets", "gadgets", "model", "ref('gadgets')",
                      {"tenant_id": "integer"}, 3, "f_b")
    # Neither table is named "tenant", so no key is claimed.
    assert infer_foreign_keys_by_name([a, b]) == []


def test_inference_never_self_references():
    from misata.dbt_unit import UnitTestInput, infer_foreign_keys_by_name

    orders = UnitTestInput("model.p.stg_orders", "stg_orders", "model",
                           "ref('stg_orders')", {"order_id": "integer"}, 3, "f")
    assert infer_foreign_keys_by_name([orders]) == []


def test_money_columns_round_to_two_places():
    """74.03978153304986 in an amount column is noise a reader must skip."""
    df = pd.DataFrame({"amount": [74.03978153304986], "ratio": [0.123456789]})
    out = coerce_to_declared_types(df, {"amount": "float", "ratio": "float"})
    assert out["amount"].iloc[0] == 74.04
    assert out["ratio"].iloc[0] == 0.1235
