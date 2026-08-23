"""A row count stated in the story is a declaration, not a hint.

Each domain template carries an assumed average transaction value, and the
FactEngine sizes a curved table from that and returns before it ever reads the
declared row count. So "4000 orders" alongside a revenue curve produced 24,797
orders: the guess said each was worth 75, and nothing said the number had been
changed.

There is no real conflict to resolve. 4,000 orders totalling 2,710,000 is an
average order of 677.50, which is simply what the average is. The count is
declared, so the average is derived from it.
"""

import warnings

import pytest

import misata

CURVE = ("Revenue curve: Jan 120000, Feb 140000, Mar 160000, Apr 180000, "
         "May 200000, Jun 220000, Jul 210000, Aug 230000, Sep 250000, "
         "Oct 280000, Nov 400000, Dec 320000.")
TOTAL = 2_710_000


def _orders(story, rows=1200):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        data = misata.generate_from_schema(misata.parse(story, rows=rows))
    orders = data["orders"]
    amount = next(c for c in ("amount", "total", "order_total") if c in orders.columns)
    return orders, amount


def test_a_declared_order_count_is_honoured_exactly():
    orders, _ = _orders(
        f"An ecommerce store with 1200 customers and 4000 orders in 2026. {CURVE}")
    assert len(orders) == 4000, \
        f"the story declared 4000 orders and got {len(orders)}"


def test_the_revenue_curve_still_lands_on_every_month():
    """Honouring the count must not cost the aggregate."""
    orders, amount = _orders(
        f"An ecommerce store with 1200 customers and 4000 orders in 2026. {CURVE}")
    assert orders[amount].sum() == pytest.approx(TOTAL, abs=1.0)

    stamp = next(c for c in ("order_date", "created_at", "date") if c in orders.columns)
    monthly = orders.set_index(stamp)[amount].resample("MS").sum()
    declared = [120_000, 140_000, 160_000, 180_000, 200_000, 220_000,
                210_000, 230_000, 250_000, 280_000, 400_000, 320_000]
    assert list(monthly.round(0)) == pytest.approx(declared, abs=1.0)


def test_without_a_declared_count_the_engine_still_sizes_the_table():
    """The assumed average is a reasonable default; it just must not outrank
    something the user actually said."""
    orders, _ = _orders(
        "An ecommerce store with 1200 customers in 2026. "
        "Revenue curve: Jan 120000, Feb 140000, Mar 160000.")
    assert len(orders) > 4000, \
        "with no declared count the average should still size the table"
