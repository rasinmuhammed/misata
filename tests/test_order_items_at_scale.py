"""An ecommerce story that names order items gets them, and they stay right past one batch and past the context cap.

Gate R3 (studio realism program, 2026-10-09): asked for customers, products, orders and order items at a million
customers, the builder planned three tables, and two defects showed only at scale. A child of a parent keyed other
than "id" drew only from the first MAX_CONTEXT_ROWS parents (half the customers never ordered at 100k), and
min_children was enforced per batch, so the same first parents got the rows again and again (83% of orders empty).
"""
import pandas as pd

from misata.simulator import DataSimulator
from misata.story_parser import StoryParser

ITEMS = "An ecommerce store with customers, products, orders and order items"


def _tables(story, rows, monkeypatch=None, batch=10_000, cap=None):
    if cap is not None:
        monkeypatch.setattr(DataSimulator, "MAX_CONTEXT_ROWS", cap)
    schema = StoryParser().parse(story, default_rows=rows)
    schema.seed = 7
    out = {}
    for name, df in DataSimulator(schema, batch_size=batch).generate_all():
        out[name] = pd.concat([out[name], df], ignore_index=True) if name in out else df
    return out


def test_a_story_naming_order_items_gets_lines_priced_from_the_product_and_orders_that_sum_them():
    t = _tables(ITEMS, 400)
    o, oi, p = t["orders"], t["order_items"], t["products"]
    assert oi.order_id.isin(o.order_id).all() and oi.product_id.isin(p.product_id).all()
    assert o.order_id.isin(oi.order_id).all()  # no order without a line
    m = oi.merge(p[["product_id", "price"]], on="product_id")
    assert ((m.unit_price - m.price).abs() < 0.01).all()
    assert ((oi.line_total - oi.quantity * oi.unit_price).abs() < 0.02).all()
    sums = oi.groupby("order_id").line_total.sum()
    assert ((o.set_index("order_id").amount.reindex(sums.index) - sums).abs() < 0.05).all()
    assert "product_id" not in o.columns and "quantity" not in o.columns


def test_a_story_without_items_keeps_its_three_tables():
    t = _tables("An ecommerce store with customers, products and orders", 400)
    assert set(t) == {"customers", "products", "orders"} and "product_id" in t["orders"].columns
    assert "India" not in set(t["customers"].country)


def test_every_parent_is_reachable_and_covered_past_one_batch_and_past_the_context_cap(monkeypatch):
    t = _tables(ITEMS, 2000, monkeypatch, batch=1000, cap=500)  # 6,000 orders, 15,000 lines in 15 batches
    c, o, oi = t["customers"], t["orders"], t["order_items"]
    assert o.order_id.isin(oi.order_id).all()  # every order has a line, not the first 500 many times over
    per = oi.groupby("order_id").size()
    assert per.mean() < 3.5 and per.max() <= 15
    # Customers past the context cap order as often as those inside it (before the
    # fix none of them did). Repeat-buyer skew keeps the overall share below 1.
    reached = c.customer_id.isin(o.customer_id)
    assert reached[500:].mean() > 0.6 and abs(reached[:500].mean() - reached[500:].mean()) < 0.1
