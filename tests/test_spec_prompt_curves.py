"""A structured spec can declare what a total must come to.

The spec path parsed tables, row counts, keys, enums and ranges exactly and
had no way to state an aggregate, which is the one guarantee this engine
exists for. A spec carrying twelve months of declared revenue parsed as a
clean success with no curve and no complaint.

A curve naming something the spec never built is reported, not dropped.
"""

import warnings

import pytest

import misata

SPEC = """
Halcyon Freight is a B2B logistics SaaS.

Table 1: accounts
Rows: exactly 200
Columns:
  account_id
  company_name
  plan
plan must only be:
Starter
Professional

Table 2: invoices
Rows: exactly 900
Columns:
  invoice_id
  account_id
  amount
  issued_on
account_id must match values from accounts table
amount must be 100 to 9000

Revenue curve on invoices.amount by issued_on:
Jan 120000
Feb 135000
Mar 150000
"""

DECLARED = {1: 120_000, 2: 135_000, 3: 150_000}


@pytest.fixture(scope="module")
def built():
    schema = misata.parse(SPEC, rows=200)
    return schema, misata.generate_from_schema(schema)


def test_the_curve_is_parsed(built):
    schema, _ = built
    curves = schema.outcome_curves or []
    assert len(curves) == 1, "the declared curve was dropped"
    curve = curves[0]
    assert (curve.table, curve.column, curve.time_column) == \
        ("invoices", "amount", "issued_on")
    assert len(curve.curve_points) == 3


def test_every_declared_month_lands_exactly(built):
    _, data = built
    monthly = data["invoices"].set_index("issued_on")["amount"].resample("MS").sum()
    for stamp, got in monthly.items():
        expected = DECLARED.get(stamp.month)
        if expected is None:
            continue
        assert abs(got - expected) < 0.5, \
            f"{stamp:%b}: got {got:,.2f}, spec declared {expected:,}"


def test_the_curve_does_not_cost_the_other_guarantees(built):
    """Row counts, keys, enums and bounds must survive the curve."""
    _, data = built
    accounts, invoices = data["accounts"], data["invoices"]
    assert (len(accounts), len(invoices)) == (200, 900)
    assert invoices["account_id"].isin(accounts["account_id"]).all()
    assert set(accounts["plan"]) <= {"Starter", "Professional"}
    assert invoices["amount"].between(100, 9000).all()


@pytest.mark.parametrize("block,expected", [
    ("\nRevenue curve on payments.amount by paid_on:\nJan 100\nFeb 200\n",
     "no table named 'payments'"),
    ("\nRevenue curve on invoices.total by issued_on:\nJan 100\nFeb 200\n",
     "has no column 'total'"),
    ("\nRevenue curve on invoices.amount by issued_on:\nJan 100\n",
     "fewer than two month values"),
])
def test_a_curve_that_cannot_be_built_is_reported(block, expected):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        schema = misata.parse(SPEC.split("Revenue curve")[0] + block, rows=200)
    assert not (schema.outcome_curves or []), "an impossible curve was built anyway"
    said = " ".join(str(w.message) for w in caught)
    assert expected in said, f"not reported. Said: {said[:200]}"


def test_rules_written_after_every_table_reach_the_right_one():
    """A "Rules:" section at the end lands in the last table's text. Matching
    only against that table meant a spec with enums on two tables silently
    kept the last and lost the rest. The example shipped in the product hid
    this, because its one enum belongs to its last table."""
    spec = """
Table 1: accounts
Rows: exactly 100
Columns:
  account_id
  plan

Table 2: tickets
Rows: exactly 300
Columns:
  ticket_id
  account_id
  priority

Rules:

account_id must match values from accounts table

plan must only be:
Starter
Professional

priority must only be:
Low
Urgent
"""
    schema = misata.parse(spec, rows=100)
    pools = {(t, c.name): (c.distribution_params or {}).get("choices")
             for t, cols in schema.columns.items() for c in cols}
    assert pools.get(("accounts", "plan")) == ["Starter", "Professional"], \
        "an enum for the first table was lost to the last one"
    assert pools.get(("tickets", "priority")) == ["Low", "Urgent"]


def test_a_date_range_rule_is_honoured():
    """Without one, a spec could bound every number and not the dates, and the
    child's rows collided with the parent's. The documented example warned
    about 2,866 invoices it could not place inside their declared month."""
    import warnings as _w
    spec = """
Table 1: accounts
Rows: exactly 150
Columns:
  account_id
  signed_up_on
signed_up_on must be 2023-01-01 to 2023-12-31

Table 2: invoices
Rows: exactly 400
Columns:
  invoice_id
  account_id
  amount
  issued_on
account_id must match values from accounts table
issued_on must be 2024-01-01 to 2024-12-31
"""
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        data = misata.generate_from_schema(misata.parse(spec, rows=150))

    accounts, invoices = data["accounts"], data["invoices"]
    assert accounts["signed_up_on"].dt.year.eq(2023).all()
    assert invoices["issued_on"].dt.year.eq(2024).all()
    assert not [c for c in caught if "cannot both postdate" in str(c.message)], \
        "a child row could not be placed after its parent"


def test_the_readme_example_runs_clean():
    """The documented spec is executable and must stay that way."""
    import pathlib
    import warnings as _w
    readme = pathlib.Path(__file__).resolve().parents[1] / "README.md"
    block = readme.read_text().split("### 1b. A structured spec")[1] \
                              .split("```text")[1].split("```")[0]
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        data = misata.generate_from_schema(misata.parse(block, rows=600))

    accounts, invoices = data["accounts"], data["invoices"]
    assert (len(accounts), len(invoices)) == (600, 3200)
    assert invoices["account_id"].isin(accounts["account_id"]).all()
    assert not [c for c in caught if "cannot both postdate" in str(c.message)]

    monthly = invoices.set_index("issued_on")["amount"].resample("MS").sum()
    for month, declared in ((1, 180_000), (2, 195_000), (3, 210_000)):
        got = float(monthly[monthly.index.month == month].iloc[0])
        assert abs(got - declared) < 0.5, f"month {month}: {got:,.2f} vs {declared:,}"
