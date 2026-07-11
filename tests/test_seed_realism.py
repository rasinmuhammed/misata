"""Obvious-case realism: the invariants a developer eyeballs in seed data.

These are the contradictions that make a synthetic users+orders database look
fake on sight — an order that shipped before it was placed, an age that does
not match the birth date, a cancelled order carrying a ship date. Each must
hold with no per-column hand-declaration; naming the columns is enough.
"""

import pandas as pd
import pytest

import misata
from misata.schema import Column, Relationship, SchemaConfig, Table


@pytest.fixture(scope="module")
def app_db():
    schema = SchemaConfig(
        name="app_seed", seed=7,
        tables=[
            Table(name="users", row_count=200),
            Table(name="orders", row_count=600),
        ],
        columns={
            "users": [
                Column(name="user_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 100000}),
                Column(name="first_name", type="text"),
                Column(name="last_name", type="text"),
                Column(name="email", type="text"),
                Column(name="date_of_birth", type="date",
                       distribution_params={"start": "1950-01-01", "end": "2006-01-01"}),
                Column(name="age", type="int",
                       distribution_params={"min": 18, "max": 75}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2023-01-01", "end": "2025-01-01"}),
                Column(name="updated_at", type="datetime",
                       distribution_params={"start": "2023-01-01", "end": "2025-06-01"}),
            ],
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 1000000}),
                Column(name="user_id", type="foreign_key"),
                Column(name="status", type="categorical",
                       distribution_params={"choices": ["pending", "shipped",
                                                        "delivered", "cancelled"]}),
                Column(name="order_date", type="datetime",
                       distribution_params={"start": "2024-01-01", "end": "2025-01-01"}),
                Column(name="shipped_date", type="datetime",
                       distribution_params={"start": "2024-01-01", "end": "2025-02-01"}),
            ],
        },
        relationships=[Relationship(parent_table="users", child_table="orders",
                                    parent_key="user_id", child_key="user_id")],
    )
    return misata.generate_from_schema(schema)


class TestTemporalOrdering:
    def test_created_before_updated(self, app_db):
        u = app_db["users"]
        assert (pd.to_datetime(u["created_at"]) <= pd.to_datetime(u["updated_at"])).all()

    def test_order_before_ship(self, app_db):
        o = app_db["orders"]
        present = o[o["shipped_date"].notna()]
        assert (pd.to_datetime(present["order_date"])
                <= pd.to_datetime(present["shipped_date"])).all()


class TestStatusCoherence:
    def test_only_shipped_statuses_carry_a_ship_date(self, app_db):
        o = app_db["orders"]
        shipped_states = {"shipped", "delivered", "completed", "fulfilled",
                          "returned", "refunded", "dispatched", "in_transit"}
        with_date = o[o["shipped_date"].notna()]
        assert with_date["status"].str.lower().isin(shipped_states).all()

    def test_cancelled_orders_have_no_ship_date(self, app_db):
        o = app_db["orders"]
        assert o[o["status"] == "cancelled"]["shipped_date"].isna().all()


class TestIdentityCoherence:
    def test_age_matches_date_of_birth(self, app_db):
        u = app_db["users"]
        dob = pd.to_datetime(u["date_of_birth"])
        # Reference is the dataset's latest timestamp (see _fix_age_from_dob).
        ref = max(pd.to_datetime(u["updated_at"]).max(),
                  pd.to_datetime(u["created_at"]).max())
        implied = ((ref - dob).dt.days / 365.25).round()
        assert (abs(u["age"].astype(float) - implied) <= 1).all()

    def test_email_contains_the_name(self, app_db):
        u = app_db["users"]
        def matches(r):
            e = str(r["email"]).lower()
            return (str(r["first_name"]).lower() in e
                    or str(r["last_name"]).lower() in e)
        assert u.apply(matches, axis=1).mean() >= 0.95


def test_lifecycle_ordering_generalizes_to_saas():
    """A different lifecycle vocabulary (signup/trial/paid) must also order."""
    schema = SchemaConfig(
        name="saas", seed=3,
        tables=[Table(name="accounts", row_count=300)],
        columns={"accounts": [
            Column(name="account_id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 100000}),
            Column(name="signup_date", type="datetime",
                   distribution_params={"start": "2024-01-01", "end": "2024-12-31"}),
            Column(name="paid_date", type="datetime",
                   distribution_params={"start": "2024-01-01", "end": "2025-01-31"}),
            Column(name="cancelled_date", type="datetime",
                   distribution_params={"start": "2024-01-01", "end": "2025-03-31"}),
        ]},
    )
    a = misata.generate_from_schema(schema)["accounts"]
    s, p, c = (pd.to_datetime(a["signup_date"]), pd.to_datetime(a["paid_date"]),
               pd.to_datetime(a["cancelled_date"]))
    assert (s <= p).all() and (p <= c).all()


class TestGeographicCoherence:
    @pytest.fixture(scope="class")
    def addresses(self):
        schema = SchemaConfig(
            name="addr", seed=11,
            tables=[Table(name="people", row_count=150)],
            columns={"people": [
                Column(name="person_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 100000}),
                Column(name="city", type="text"),
                Column(name="state", type="text"),
                Column(name="zip_code", type="text"),
                Column(name="country", type="text"),
            ]},
        )
        return misata.generate_from_schema(schema)["people"]

    def test_state_is_not_an_order_status(self, addresses):
        statuses = {"pending", "active", "inactive", "cancelled"}
        assert not addresses["state"].astype(str).str.lower().isin(statuses).any()

    def test_state_belongs_to_country(self, addresses):
        from misata.realism import COUNTRY_STATES
        def ok(r):
            pool = COUNTRY_STATES.get(str(r["country"]))
            return pool is None or str(r["state"]) in pool
        assert addresses.apply(ok, axis=1).mean() >= 0.95

    def test_zip_matches_country_format(self, addresses):
        import re
        fmt = {
            "United States": r"^\d{5}$", "Germany": r"^\d{5}$",
            "France": r"^\d{5}$", "Australia": r"^\d{4}$",
            "India": r"^\d{6}$", "Japan": r"^\d{3}-\d{4}$",
            "Netherlands": r"^\d{4} [A-Z]{2}$", "Brazil": r"^\d{5}-\d{3}$",
        }
        def ok(r):
            pat = fmt.get(str(r["country"]))
            return pat is None or bool(re.match(pat, str(r["zip_code"])))
        assert addresses.apply(ok, axis=1).mean() >= 0.95

    def test_phone_matches_country_calling_code(self):
        schema = SchemaConfig(
            name="ph", seed=4, tables=[Table(name="p", row_count=200)],
            columns={"p": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 99999}),
                Column(name="phone", type="text"),
                Column(name="country", type="text"),
            ]},
        )
        d = misata.generate_from_schema(schema)["p"]
        codes = {"United States": "+1", "Canada": "+1", "United Kingdom": "+44",
                 "Germany": "+49", "France": "+33", "India": "+91",
                 "Japan": "+81", "Netherlands": "+31", "Australia": "+61",
                 "Brazil": "+55", "Mexico": "+52"}
        def ok(r):
            cc = codes.get(str(r["country"]))
            return cc is None or str(r["phone"]).startswith(cc)
        assert d.apply(ok, axis=1).mean() >= 0.95


class TestDistributionRealism:
    def test_salary_is_right_skewed(self):
        schema = SchemaConfig(
            name="emp", seed=4, tables=[Table(name="e", row_count=3000)],
            columns={"e": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 99999}),
                Column(name="salary", type="float",
                       distribution_params={"min": 30000, "max": 250000}),
            ]},
        )
        salary = misata.generate_from_schema(schema)["e"]["salary"]
        assert salary.skew() > 0.7, f"salary skew {salary.skew():.2f} too symmetric"
        assert salary.median() < salary.mean(), "income should have mean > median"
        assert salary.min() >= 30000 and salary.max() <= 250000

    def test_explicit_distribution_is_respected(self):
        """A user who declares a distribution must not be overridden by skew."""
        schema = SchemaConfig(
            name="emp2", seed=4, tables=[Table(name="e", row_count=2000)],
            columns={"e": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 99999}),
                Column(name="revenue", type="float",
                       distribution_params={"distribution": "normal",
                                            "mean": 100000, "std": 5000}),
            ]},
        )
        rev = misata.generate_from_schema(schema)["e"]["revenue"]
        assert abs(rev.skew()) < 0.5, "explicit normal must stay symmetric"


class TestCountIntegrity:
    def test_count_columns_never_negative(self):
        schema = SchemaConfig(
            name="cnt", seed=9, tables=[Table(name="t", row_count=3000)],
            columns={"t": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 99999}),
                Column(name="num_items", type="int", distribution_params={"mean": 2}),
                Column(name="session_count", type="int", distribution_params={"mean": 5}),
                Column(name="quantity", type="int", distribution_params={"mean": 3}),
            ]},
        )
        d = misata.generate_from_schema(schema)["t"]
        for c in ("num_items", "session_count", "quantity"):
            assert (d[c] >= 0).all(), f"{c} went negative"
        # Small-mean counts must stay small (sqrt-scale std, not flat 20).
        assert d["num_items"].max() < 30

    def test_non_count_signed_columns_keep_negatives(self):
        schema = SchemaConfig(
            name="temp", seed=9, tables=[Table(name="t", row_count=2000)],
            columns={"t": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 99999}),
                Column(name="temperature_c", type="int", distribution_params={"mean": -3}),
            ]},
        )
        d = misata.generate_from_schema(schema)["t"]
        assert (d["temperature_c"] < 0).any(), "temperature must allow negatives"
