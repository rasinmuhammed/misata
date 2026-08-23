"""A date column in a structured spec must produce dates.

The spec parser recognised `_date` and `_at` and nothing else, so the way
English actually writes these (`issued_on`, `hired_on`, `scheduled_for`) fell
through to free text. A spec declaring four date columns produced four columns
of business-note prose, with no warning, and the run otherwise looked perfect:
row counts exact, foreign keys intact, enums clean.
"""

import pytest

import misata

SPEC = """
Meridian Field Services is a B2B SaaS platform for HVAC contractors.

Table 1: accounts
Rows: exactly 120
Columns:
  account_id
  company_name
  plan
  signed_up_on
plan must only be:
Starter
Professional
Enterprise

Table 2: work_orders
Rows: exactly 300
Columns:
  work_order_id
  account_id
  scheduled_for
  completed_on
  issued_on
account_id must match values from accounts table
"""


@pytest.fixture(scope="module")
def built():
    schema = misata.parse(SPEC, rows=120)
    return schema, misata.generate_from_schema(schema)


@pytest.mark.parametrize("table,column", [
    ("accounts", "signed_up_on"),
    ("work_orders", "scheduled_for"),
    ("work_orders", "completed_on"),
    ("work_orders", "issued_on"),
])
def test_date_shaped_names_are_dates(built, table, column):
    schema, data = built
    declared = next(c for c in schema.columns[table] if c.name == column)
    assert declared.type == "date", f"{table}.{column} typed as {declared.type}"
    assert str(data[table][column].dtype).startswith("datetime"), \
        f"{table}.{column} came back as {data[table][column].dtype}"


def test_the_rest_of_the_spec_still_holds(built):
    """The date fix must not disturb counts, keys or enumerations."""
    _, data = built
    accounts, orders = data["accounts"], data["work_orders"]
    assert len(accounts) == 120 and len(orders) == 300
    assert orders["account_id"].isin(accounts["account_id"]).all()
    assert set(accounts["plan"]) <= {"Starter", "Professional", "Enterprise"}
