"""A declared value is never replaced by a realism pass.

Geography coherence, foreign-key sampling and the importers all used to
substitute their own idea of a plausible value for one the schema stated.
Each test below declares a value and checks it survives generation, and
that the undeclared columns around it are brought into agreement with it.
"""

from __future__ import annotations

import warnings

import pandas as pd
import pytest

import misata
from misata.feasibility import InfeasibleSchema
from misata.simulator import DataSimulator


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


def _trips(state: dict, *, country: bool) -> pd.DataFrame:
    columns = {
        "id": {"type": "integer", "primary_key": True},
        "tr_state": state,
        "tr_city": {"type": "string"},
        "tr_zip": {"type": "string"},
    }
    if country:
        columns["tr_country"] = {"type": "string"}
        columns["tr_phone"] = {"type": "string"}
    schema = misata.from_dict_schema({"trips": {"__rows__": 300, **columns}}, seed=1)
    return misata.generate_from_schema(schema)["trips"]


@pytest.mark.parametrize("country", [False, True], ids=["us_chain", "with_country"])
@pytest.mark.parametrize("key", ["choices", "enum"])
def test_declared_state_codes_survive_geo_coherence(key, country):
    trips = _trips({"type": "categorical", key: ["CA", "NY"]}, country=country)
    assert set(trips["tr_state"]) == {"CA", "NY"}


@pytest.mark.parametrize("country", [False, True], ids=["us_chain", "with_country"])
def test_city_country_and_zip_follow_a_declared_state(country):
    from misata.vocab_seeds import US_CITY_GEO

    trips = _trips({"type": "categorical", "choices": ["CA", "NY"]}, country=country)
    for state, city, zip_code in trips[["tr_state", "tr_city", "tr_zip"]].itertuples(index=False):
        assert US_CITY_GEO[city][1] == state
        assert zip_code.startswith(US_CITY_GEO[city][2])
    if country:
        assert set(trips["tr_country"]) == {"United States"}
        assert trips["tr_phone"].str.startswith("+1 ").all()


def test_ddl_check_in_list_survives_geo_coherence():
    schema = misata.from_ddl(
        "CREATE TABLE trips (id INT PRIMARY KEY, "
        "tr_state VARCHAR(2) CHECK (tr_state IN ('CA')), tr_city TEXT, tr_zip TEXT);",
        default_rows=200,
    )
    trips = misata.generate_from_schema(schema)["trips"]
    assert set(trips["tr_state"]) == {"CA"}


def test_geo_columns_hold_plain_strings():
    """A column mixing str and numpy.str_ is rejected by DuckDB's Arrow scan."""
    duckdb = pytest.importorskip("duckdb")
    trips = _trips({"type": "categorical", "choices": ["CA", "NY"], "nullable": True,
                    "null_rate": 0.2}, country=True)
    for column in ("tr_state", "tr_city", "tr_zip", "tr_country", "tr_phone"):
        assert {type(v) for v in trips[column].dropna()} == {str}, column
    con = duckdb.connect()
    con.register("trips", trips)
    assert len(con.sql("SELECT * FROM trips").fetchall()) == len(trips)


def test_undeclared_state_still_follows_its_city():
    from misata.vocab_seeds import US_CITY_GEO

    trips = _trips({"type": "string"}, country=False)
    for state, city in trips[["tr_state", "tr_city"]].itertuples(index=False):
        assert state in US_CITY_GEO[city][:2]


def test_coherence_repair_leaves_a_declared_city_alone():
    schema = misata.from_dict_schema({"shops": {
        "__rows__": 50,
        "id": {"type": "integer", "primary_key": True},
        "city": {"type": "categorical", "choices": ["Paris"]},
        "country": {"type": "categorical", "choices": ["Japan"]},
    }}, seed=2)
    tables = {"shops": pd.DataFrame({"id": range(3), "city": ["Paris"] * 3, "country": ["Japan"] * 3})}
    report = misata.coherence_audit(tables, repair=True, schema=schema)
    assert set(tables["shops"]["city"]) == {"Paris"}
    geo = [f for f in report.findings if f.kind == "geo_contradiction"]
    assert geo and not geo[0].repaired


def _profiles(children: int) -> misata.SchemaConfig:
    return misata.from_dict_schema({
        "users": {"__rows__": 300, "id": {"type": "integer", "primary_key": True}},
        "profiles": {
            "__rows__": children,
            "id": {"type": "integer", "primary_key": True},
            "user_id": {"type": "foreign_key", "unique": True,
                        "foreign_key": {"table": "users", "column": "id"}},
        },
    }, seed=3)


def test_dict_schema_keeps_unique_on_a_foreign_key():
    column = next(c for c in _profiles(300).get_columns("profiles") if c.name == "user_id")
    assert column.unique


def test_unique_foreign_key_is_one_to_one():
    profiles = misata.generate_from_schema(_profiles(300))["profiles"]
    assert profiles["user_id"].is_unique
    assert len(profiles) == 300


def test_unique_foreign_key_holds_across_batches():
    simulator = DataSimulator(_profiles(300), batch_size=70)
    batches = [batch for name, batch in simulator.generate_all() if name == "profiles"]
    assert len(batches) > 1
    assert pd.concat(batches)["user_id"].is_unique


def test_unique_foreign_key_with_too_few_parents_is_refused():
    with pytest.raises(InfeasibleSchema) as caught:
        misata.generate_from_schema(_profiles(301))
    assert [c.kind for c in caught.value.conflicts] == ["unique_fk_exceeds_parents"]
    assert "300 users rows" in str(caught.value)


def test_ddl_unique_foreign_key_is_one_to_one():
    schema = misata.from_ddl(
        "CREATE TABLE users (id INT PRIMARY KEY);"
        "CREATE TABLE profiles (id INT PRIMARY KEY, "
        "user_id INT UNIQUE NOT NULL REFERENCES users(id));",
        default_rows=200,
    )
    assert misata.generate_from_schema(schema)["profiles"]["user_id"].is_unique


@pytest.mark.parametrize("country", [False, True], ids=["us_chain", "with_country"])
def test_nullable_declared_state_keeps_its_nulls_and_values(country):
    trips = _trips({"type": "categorical", "choices": ["CA"], "nullable": True, "null_rate": 0.3},
                   country=country)
    present = trips["tr_state"].dropna()
    assert set(present) == {"CA"}
    assert 0 < trips["tr_state"].isna().sum() < len(trips)
    assert {type(v) for v in trips["tr_city"]} == {str}


def _curved_orders(time_type: str, grid: "misata.schema.TimeGrid | None" = None):
    from misata import OutcomeCurveBuilder
    from misata.schema import Column, SchemaConfig, Table

    schema = SchemaConfig(
        name="curved",
        seed=3,
        tables=[Table(name="orders", row_count=1500)],
        columns={"orders": [
            Column(name="order_id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 1_000_000}),
            Column(name="amount", type="float", distribution_params={"min": 5, "max": 50_000}),
            Column(name="ordered_on", type=time_type,
                   distribution_params={"start": "2024-01-01", "end": "2024-06-30"}),
        ]},
    )
    curve = (OutcomeCurveBuilder("orders", column="amount", time_column="ordered_on")
             .anchor("2024-01", 10_000).anchor("2024-06", 30_000)
             .avg_value(80.0).row_bounds(1, 10_000).build())
    schema = OutcomeCurveBuilder.attach(schema, curve)
    if grid is not None:
        schema.time_grids = [grid]
    return schema


def _monthly_totals(df: pd.DataFrame) -> pd.Series:
    month = pd.to_datetime(df["ordered_on"]).dt.to_period("M")
    return df.groupby(month)["amount"].sum().round(2)


def test_curve_on_a_date_column_holds_whole_days():
    schema = _curved_orders("date")
    orders = misata.generate_from_schema(schema)["orders"]
    stamps = pd.to_datetime(orders["ordered_on"])
    assert (stamps == stamps.dt.normalize()).all()
    assert stamps.min() == pd.Timestamp("2024-01-01")
    plan = _monthly_totals(misata.generate_from_schema(_curved_orders("datetime"))["orders"])
    assert _monthly_totals(orders).tolist() == plan.tolist()


def test_time_grid_on_a_curve_time_column_is_refused():
    from misata.schema import TimeGrid

    grid = TimeGrid(table="orders", column="ordered_on", minute_grid=1440)
    with pytest.raises(InfeasibleSchema, match="time_grids on orders.ordered_on"):
        misata.generate_from_schema(_curved_orders("datetime", grid))


def test_time_grid_on_a_date_curve_column_keeps_every_period():
    from misata.schema import TimeGrid

    grid = TimeGrid(table="orders", column="ordered_on", minute_grid=60, hours=(9, 17))
    orders = misata.generate_from_schema(_curved_orders("date", grid))["orders"]
    stamps = pd.to_datetime(orders["ordered_on"])
    assert (stamps.dt.hour == 9).all() and (stamps.dt.minute == 0).all()
    plan = _monthly_totals(misata.generate_from_schema(_curved_orders("datetime"))["orders"])
    assert _monthly_totals(orders).tolist() == plan.tolist()
