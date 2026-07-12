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


class TestBoundedAndSemanticDefaults:
    def test_percent_columns_bounded_0_to_100(self):
        schema = SchemaConfig(
            name="pct", seed=6, tables=[Table(name="m", row_count=1000)],
            columns={"m": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 9999}),
                Column(name="discount_percent", type="float"),
                Column(name="conversion_pct", type="float"),
            ]},
        )
        d = misata.generate_from_schema(schema)["m"]
        for c in ("discount_percent", "conversion_pct"):
            assert d[c].min() >= 0 and d[c].max() <= 100

    def test_rate_columns_bounded_0_to_1(self):
        schema = SchemaConfig(
            name="rate", seed=6, tables=[Table(name="m", row_count=1000)],
            columns={"m": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 9999}),
                Column(name="completion_rate", type="float"),
                Column(name="churn_ratio", type="float"),
            ]},
        )
        d = misata.generate_from_schema(schema)["m"]
        for c in ("completion_rate", "churn_ratio"):
            assert d[c].min() >= 0 and d[c].max() <= 1

    def test_boolean_base_rates_are_semantic(self):
        schema = SchemaConfig(
            name="bool", seed=6, tables=[Table(name="t", row_count=3000)],
            columns={"t": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 99999}),
                Column(name="is_fraud", type="boolean"),
                Column(name="is_active", type="boolean"),
                Column(name="is_deleted", type="boolean"),
            ]},
        )
        d = misata.generate_from_schema(schema)["t"]
        assert d["is_fraud"].mean() < 0.15, "fraud should be rare"
        assert d["is_deleted"].mean() < 0.15, "deletion should be rare"
        assert d["is_active"].mean() > 0.7, "active should be common"

    def test_explicit_probability_is_respected(self):
        schema = SchemaConfig(
            name="bp", seed=6, tables=[Table(name="t", row_count=3000)],
            columns={"t": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 99999}),
                Column(name="is_fraud", type="boolean",
                       distribution_params={"probability": 0.5}),
            ]},
        )
        d = misata.generate_from_schema(schema)["t"]
        assert 0.4 < d["is_fraud"].mean() < 0.6, "explicit 0.5 must be honored"


class TestCorporateEmail:
    def test_work_email_uses_company_domain(self):
        schema = SchemaConfig(
            name="corp", seed=6, tables=[Table(name="emp", row_count=100)],
            columns={"emp": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 9999}),
                Column(name="first_name", type="text"),
                Column(name="last_name", type="text"),
                Column(name="company_name", type="text"),
                Column(name="work_email", type="text"),
            ]},
        )
        d = misata.generate_from_schema(schema)["emp"]
        free = ("gmail.com", "outlook.com", "hotmail.com", "yahoo.com",
                "icloud.com", "protonmail.com")
        assert not d["work_email"].str.contains("|".join(free)).any()
        assert d["work_email"].str.contains("@").all()


class TestReferenceCodes:
    @pytest.fixture(scope="class")
    def orders(self):
        schema = SchemaConfig(
            name="oc", seed=6, tables=[Table(name="orders", row_count=1000)],
            columns={"orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 99999}),
                Column(name="status", type="categorical",
                       distribution_params={"choices": ["pending", "shipped",
                                                        "delivered", "cancelled"]}),
                Column(name="tracking_number", type="text"),
                Column(name="invoice_number", type="text"),
            ]},
        )
        return misata.generate_from_schema(schema)["orders"]

    def test_reference_codes_are_codes_not_prose(self, orders):
        # A code has no spaces and is short; prose has spaces and length.
        inv = orders["invoice_number"].dropna().astype(str)
        assert (~inv.str.contains(" ")).all()
        assert (inv.str.len() < 20).all()

    def test_tracking_only_present_when_shipped(self, orders):
        shipped = {"shipped", "delivered", "completed", "fulfilled",
                   "returned", "refunded", "dispatched", "in_transit"}
        with_tracking = orders[orders["tracking_number"].notna()]
        assert with_tracking["status"].str.lower().isin(shipped).all()


class TestCrossTableCausality:
    """A child event cannot predate the parent it belongs to. This is the
    hardest correctness property: it needs a per-row FK lookup of the parent's
    birth date, retained across context trimming, applied so the child's own
    internal ordering survives."""

    @pytest.fixture(scope="class")
    def chained(self):
        schema = SchemaConfig(
            name="chain", seed=7,
            tables=[Table(name="customers", row_count=150),
                    Table(name="orders", row_count=600),
                    Table(name="reviews", row_count=300)],
            columns={
                "customers": [
                    Column(name="customer_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 99999}),
                    Column(name="signup_date", type="datetime",
                           distribution_params={"start": "2022-01-01", "end": "2024-12-31"})],
                "orders": [
                    Column(name="order_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 999999}),
                    Column(name="customer_id", type="foreign_key"),
                    Column(name="order_date", type="datetime",
                           distribution_params={"start": "2022-01-01", "end": "2025-06-30"}),
                    Column(name="shipped_date", type="datetime",
                           distribution_params={"start": "2022-01-01", "end": "2025-07-30"})],
                "reviews": [
                    Column(name="review_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 999999}),
                    Column(name="order_id", type="foreign_key"),
                    Column(name="review_date", type="datetime",
                           distribution_params={"start": "2022-01-01", "end": "2025-12-31"})],
            },
            relationships=[
                Relationship(parent_table="customers", child_table="orders",
                             parent_key="customer_id", child_key="customer_id"),
                Relationship(parent_table="orders", child_table="reviews",
                             parent_key="order_id", child_key="order_id")],
        )
        return misata.generate_from_schema(schema)

    def test_order_postdates_customer_signup(self, chained):
        m = chained["orders"].merge(chained["customers"], on="customer_id")
        assert (pd.to_datetime(m["order_date"])
                >= pd.to_datetime(m["signup_date"])).all()

    def test_review_postdates_its_order_two_levels_deep(self, chained):
        m = chained["reviews"].merge(chained["orders"], on="order_id")
        assert (pd.to_datetime(m["review_date"])
                >= pd.to_datetime(m["order_date"])).all()

    def test_intra_row_order_survives_the_shift(self, chained):
        o = chained["orders"]
        assert (pd.to_datetime(o["order_date"])
                <= pd.to_datetime(o["shipped_date"])).all()


class TestCrossTableValueCoherence:
    """A multi-table story must reconcile across joins: a line item's price is
    the product's price, and an order's total is the sum of its line items."""

    @pytest.fixture(scope="class")
    def shop(self):
        schema = SchemaConfig(
            name="shop", seed=13,
            tables=[Table(name="products", row_count=60),
                    Table(name="orders", row_count=400),
                    Table(name="order_items", row_count=1200)],
            columns={
                "products": [
                    Column(name="product_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 9999}),
                    Column(name="unit_price", type="float",
                           distribution_params={"min": 5, "max": 500, "decimals": 2})],
                "orders": [
                    Column(name="order_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 999999}),
                    Column(name="order_total", type="float",
                           distribution_params={"min": 5, "max": 5000, "decimals": 2})],
                "order_items": [
                    Column(name="item_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 9999999}),
                    Column(name="order_id", type="foreign_key"),
                    Column(name="product_id", type="foreign_key"),
                    Column(name="quantity", type="int",
                           distribution_params={"min": 1, "max": 5}),
                    Column(name="unit_price", type="float",
                           distribution_params={"min": 5, "max": 500, "decimals": 2}),
                    Column(name="line_total", type="float",
                           distribution_params={"min": 5, "max": 2500, "decimals": 2})],
            },
            relationships=[
                Relationship(parent_table="orders", child_table="order_items",
                             parent_key="order_id", child_key="order_id"),
                Relationship(parent_table="products", child_table="order_items",
                             parent_key="product_id", child_key="product_id")],
        )
        return misata.generate_from_schema(schema)

    def test_line_item_price_matches_product(self, shop):
        m = shop["order_items"].merge(
            shop["products"].rename(columns={"unit_price": "p"}), on="product_id")
        assert (abs(m["unit_price"] - m["p"]) < 0.01).mean() >= 0.99

    def test_line_total_is_quantity_times_price(self, shop):
        oi = shop["order_items"]
        assert (abs(oi["line_total"] - (oi["quantity"] * oi["unit_price"]).round(2))
                < 0.01).mean() >= 0.99

    def test_order_total_is_sum_of_line_items(self, shop):
        sums = shop["order_items"].groupby("order_id")["line_total"].sum().round(2)
        ot = shop["orders"].set_index("order_id")["order_total"]
        j = ot.to_frame("t").join(sums.to_frame("s")).dropna()
        assert (abs(j["t"] - j["s"]) < 0.01).mean() >= 0.99

    def test_generation_does_not_crash_without_discount_column(self, shop):
        # Regression: _fix_line_total crashed on df.get("discount", 0).fillna.
        assert len(shop["order_items"]) > 0


class TestStoryAudit:
    """The self-check layer: generation grades its own output against the full
    invariant catalog, so a dataset that contradicts itself cannot pass
    silently. Both directions matter: clean data must audit clean, and each
    sabotaged invariant must be caught by name."""

    @pytest.fixture(scope="class")
    def story(self):
        schema = SchemaConfig(
            name="shop", seed=13,
            tables=[Table(name="customers", row_count=150),
                    Table(name="orders", row_count=450),
                    Table(name="order_items", row_count=1100)],
            columns={
                "customers": [
                    Column(name="customer_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 99999}),
                    Column(name="signup_date", type="datetime",
                           distribution_params={"start": "2022-01-01", "end": "2024-12-31"})],
                "orders": [
                    Column(name="order_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 999999}),
                    Column(name="customer_id", type="foreign_key"),
                    Column(name="order_date", type="datetime",
                           distribution_params={"start": "2022-01-01", "end": "2025-06-30"}),
                    Column(name="order_total", type="float",
                           distribution_params={"min": 5, "max": 5000, "decimals": 2})],
                "order_items": [
                    Column(name="item_id", type="int", unique=True,
                           distribution_params={"min": 1, "max": 9999999}),
                    Column(name="order_id", type="foreign_key"),
                    Column(name="quantity", type="int",
                           distribution_params={"min": 1, "max": 5}),
                    Column(name="unit_price", type="float",
                           distribution_params={"min": 5, "max": 500, "decimals": 2}),
                    Column(name="line_total", type="float",
                           distribution_params={"min": 5, "max": 2500, "decimals": 2})],
            },
            relationships=[
                Relationship(parent_table="customers", child_table="orders",
                             parent_key="customer_id", child_key="customer_id"),
                Relationship(parent_table="orders", child_table="order_items",
                             parent_key="order_id", child_key="order_id")],
        )
        return schema, misata.generate_from_schema(schema)

    def test_clean_generation_audits_clean(self, story):
        schema, tables = story
        report = misata.story_audit(tables, schema)
        assert report.clean, report.summary()

    def test_fk_orphans_are_caught(self, story):
        schema, tables = story
        bad = {k: v.copy() for k, v in tables.items()}
        bad["order_items"].loc[bad["order_items"].index[:20], "order_id"] = -1
        kinds = {f.kind for f in misata.story_audit(bad, schema).findings}
        assert "fk_orphans" in kinds

    def test_causality_violations_are_caught(self, story):
        schema, tables = story
        bad = {k: v.copy() for k, v in tables.items()}
        bad["orders"].loc[bad["orders"].index[:30], "order_date"] = \
            pd.Timestamp("2019-01-01")
        kinds = {f.kind for f in misata.story_audit(bad, schema).findings}
        assert "temporal_causality" in kinds

    def test_rollup_mismatch_is_caught(self, story):
        schema, tables = story
        bad = {k: v.copy() for k, v in tables.items()}
        bad["orders"]["order_total"] = bad["orders"]["order_total"] + 500.0
        kinds = {f.kind for f in misata.story_audit(bad, schema).findings}
        assert "rollup_mismatch" in kinds

    def test_negative_counts_are_caught(self, story):
        schema, tables = story
        bad = {k: v.copy() for k, v in tables.items()}
        bad["order_items"].loc[bad["order_items"].index[:15], "quantity"] = -3
        kinds = {f.kind for f in misata.story_audit(bad, schema).findings}
        assert "bounds" in kinds


def test_city_gets_its_actual_state():
    """A known city carries its real state: Amsterdam is in North Holland,
    never a random Dutch province."""
    from misata.vocab_seeds import CITY_STATE
    schema = SchemaConfig(
        name="cs", seed=7, tables=[Table(name="u", row_count=120)],
        columns={"u": [
            Column(name="id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 9999}),
            Column(name="city", type="text"),
            Column(name="state", type="text"),
            Column(name="country", type="text"),
        ]},
    )
    d = misata.generate_from_schema(schema)["u"]
    known = d[d["city"].isin(CITY_STATE)]
    if len(known):
        assert (known.apply(lambda r: CITY_STATE[str(r["city"])] == str(r["state"]),
                            axis=1)).all()


class TestStatisticalPriors:
    """The priors knowledge base: a recognised column name draws its real-world
    shape automatically. Explicit user shapes always win; declared bounds clip."""

    @pytest.fixture(scope="class")
    def shapes(self):
        schema = SchemaConfig(
            name="priors", seed=6, tables=[Table(name="t", row_count=4000)],
            columns={"t": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 99999}),
                Column(name="rating", type="float"),
                Column(name="quantity", type="int"),
                Column(name="unit_price", type="float"),
                Column(name="age", type="int"),
                Column(name="conversion_rate", type="float"),
            ]},
        )
        return misata.generate_from_schema(schema)["t"]

    def test_quantity_is_mostly_one(self, shapes):
        p1 = (shapes["quantity"] == 1).mean()
        assert p1 > 0.4, f"P(quantity=1)={p1:.0%}; real order quantities are mostly 1"

    def test_prices_snap_to_retail_endings(self, shapes):
        cents = (shapes["unit_price"] * 100 % 100).round().astype(int)
        ending_99 = (cents == 99).mean()
        assert ending_99 > 0.25, f".99 endings only {ending_99:.0%}"

    def test_age_is_adult_pyramid_not_uniform(self, shapes):
        age = shapes["age"]
        assert age.min() >= 18 and age.max() <= 100
        # A population pyramid concentrates 25-55; uniform 18-80 puts ~48% there.
        assert ((age >= 25) & (age <= 55)).mean() > 0.55

    def test_rating_skews_high(self, shapes):
        assert shapes["rating"].mean() > 3.2
        assert shapes["rating"].min() >= 1 and shapes["rating"].max() <= 5

    def test_conversion_rate_is_low_fraction(self, shapes):
        cr = shapes["conversion_rate"]
        assert cr.max() <= 1.0, "rate columns live in 0-1"
        assert cr.median() < 0.10, "typical conversion is a few percent"

    def test_explicit_shape_beats_the_prior(self):
        schema = SchemaConfig(
            name="explicit", seed=6, tables=[Table(name="t", row_count=2000)],
            columns={"t": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 99999}),
                Column(name="rating", type="float",
                       distribution_params={"distribution": "uniform",
                                            "min": 1, "max": 5}),
            ]},
        )
        r = misata.generate_from_schema(schema)["t"]["rating"]
        # A uniform draw has no high-skew: mean stays near the midpoint.
        assert 2.7 < r.mean() < 3.3

    def test_declared_bounds_clip_the_prior(self):
        schema = SchemaConfig(
            name="clip", seed=6, tables=[Table(name="t", row_count=2000)],
            columns={"t": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 99999}),
                Column(name="unit_price", type="float",
                       distribution_params={"min": 10, "max": 50}),
            ]},
        )
        p = misata.generate_from_schema(schema)["t"]["unit_price"]
        assert p.min() >= 10 and p.max() <= 50
