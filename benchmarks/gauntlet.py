"""The Gauntlet: an 11-table relational schema and ~100 independent SQL assertions.

This is the engine's hostile acceptance test. The schema declares everything the
engine claims to support (FKs, rollups, formulas, inequalities, curves-free so
runs stay fast), and DuckDB — which had no part in generating the data — runs
every assertion against the emitted frames. A pass means the data would survive
a reviewer running arbitrary JOINs and GROUP BYs against it.

Run:
    python -m benchmarks.gauntlet            # scorecard on stdout
    python -m benchmarks.gauntlet --json out.json

Assertion contract: every check is a SQL query returning a single integer,
the number of violating rows. 0 is a pass. Aggregate-equality checks embed a
one-cent tolerance in the SQL itself, so "exact" means exact to the cent, in
SQL, not in the generator's own bookkeeping.

Categories:
    A  structural        PKs unique + not null, FK orphans
    B  domain            value ranges, formats, enum membership
    C  temporal          child events never precede the parent's existence
    D  status-implies    a status gates its dependent columns (G1)
    E  reconciliation    parent aggregates equal child facts, incl. multi-hop (G2)
    F  diamond           denormalized copies agree with their source (order_items.unit_price)
    G  geo               city/state/zip are internally consistent (G4)
    H  arithmetic        derived columns satisfy their formula
    I  distribution      the data is not degenerate (spread, degrees, zeros)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List, Tuple

import duckdb

import misata
from misata.schema import SchemaConfig, Table, Column, Relationship, Constraint

SEED = 7

# A state column is valid as a 2-letter code OR a full name — both are common
# in real tables. What is NEVER valid is 'Bavaria' or 'Tokyo' in a US chain.
US_STATES = (
    "'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY',"
    "'LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND',"
    "'OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC',"
    "'Alabama','Alaska','Arizona','Arkansas','California','Colorado','Connecticut',"
    "'Delaware','Florida','Georgia','Hawaii','Idaho','Illinois','Indiana','Iowa',"
    "'Kansas','Kentucky','Louisiana','Maine','Maryland','Massachusetts','Michigan',"
    "'Minnesota','Mississippi','Missouri','Montana','Nebraska','Nevada','New Hampshire',"
    "'New Jersey','New Mexico','New York','North Carolina','North Dakota','Ohio',"
    "'Oklahoma','Oregon','Pennsylvania','Rhode Island','South Carolina','South Dakota',"
    "'Tennessee','Texas','Utah','Vermont','Virginia','Washington','West Virginia',"
    "'Wisconsin','Wyoming','District of Columbia'"
)

ORDER_STATUSES = ["placed", "shipped", "completed", "return_pending", "returned", "cancelled"]
SUB_STATUSES = ["active", "past_due", "cancelled"]
TICKET_STATUSES = ["open", "pending", "resolved", "closed"]

# Assertions the engine does not pass YET. Each is a named roadmap item, shown
# red in every report rather than dropped — an acceptance test that quietly
# shrinks to fit is not an acceptance test. CI treats these as expected
# failures; an UNEXPECTED failure (a regression) still fails the build, and a
# known-red that starts passing is flagged for promotion out of this set.
KNOWN_RED = {
    "order_items never reference a product created after the order":
        "FK sampling with temporal eligibility (planned)",
}


# --------------------------------------------------------------------------- #
# The schema: 11 tables, M:N junction, diamond dependency, multi-hop rollup
# --------------------------------------------------------------------------- #

def build_schema() -> SchemaConfig:
    return SchemaConfig(
        name="gauntlet",
        seed=SEED,
        tables=[
            Table(name="categories", row_count=8),
            Table(name="products", row_count=120, constraints=[
                Constraint(name="price_above_cost", type="inequality",
                           column_a="price", operator=">", column_b="cost"),
            ]),
            Table(name="customers", row_count=500),
            Table(name="addresses", row_count=700),
            Table(name="subscriptions", row_count=600, constraints=[
                Constraint(name="cancelled_needs_date", type="when_then",
                           when_column="status", when_op="==",
                           when_value="cancelled",
                           then_column="cancelled_at", then="not_null"),
                Constraint(name="live_subs_have_no_cancel_date", type="when_then",
                           when_column="status", when_op="in",
                           when_value=["active", "past_due"],
                           then_column="cancelled_at", then="null"),
            ]),
            Table(name="orders", row_count=2500),
            Table(name="order_items", row_count=6000),
            Table(name="payments", row_count=2800, constraints=[
                Constraint(name="payments_bounded_by_order", type="sum_lte_parent",
                           column="amount",
                           parent_table="orders", parent_column="total_amount"),
            ]),
            Table(name="shipments", row_count=1800),
            Table(name="returns", row_count=300, constraints=[
                Constraint(name="refund_bounded_by_order", type="lte_parent",
                           column="refund_amount",
                           parent_table="orders", parent_column="total_amount"),
            ]),
            Table(name="support_tickets", row_count=800, constraints=[
                Constraint(name="resolution_needs_date", type="when_then",
                           when_column="status", when_op="in",
                           when_value=["resolved", "closed"],
                           then_column="resolved_at", then="not_null"),
                Constraint(name="open_tickets_have_no_resolution", type="when_then",
                           when_column="status", when_op="in",
                           when_value=["open", "pending"],
                           then_column="resolved_at", then="null"),
            ]),
        ],
        columns={
            "categories": [
                Column(name="category_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 8}),
                Column(name="category_name", type="categorical",
                       distribution_params={"choices": [
                           "Electronics", "Home & Kitchen", "Sports", "Books",
                           "Toys", "Beauty", "Garden", "Automotive"]}),
                Column(name="margin_pct", type="float",
                       distribution_params={"min": 0.05, "max": 0.60}),
            ],
            "products": [
                Column(name="product_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 120}),
                Column(name="category_id", type="foreign_key",
                       distribution_params={"references": "categories.category_id"}),
                Column(name="product_name", type="text",
                       distribution_params={"subtype": "product_name"}),
                Column(name="cost", type="float",
                       distribution_params={"distribution": "lognormal",
                                            "mu": 3.0, "sigma": 0.6, "min": 1.0}),
                Column(name="price", type="float",
                       distribution_params={"formula": "cost * 1.65"}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2022-01-01", "end": "2023-06-30"}),
            ],
            "customers": [
                Column(name="customer_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 500}),
                Column(name="full_name", type="text",
                       distribution_params={"subtype": "name"}),
                Column(name="email", type="text",
                       distribution_params={"subtype": "email"}),
                Column(name="city", type="text", distribution_params={"subtype": "city"}),
                Column(name="state", type="text", distribution_params={"subtype": "state"}),
                Column(name="zip", type="text", distribution_params={"subtype": "zipcode"}),
                Column(name="signup_date", type="datetime",
                       distribution_params={"start": "2022-06-01", "end": "2024-06-30"}),
                Column(name="status", type="categorical",
                       distribution_params={"choices": ["active", "churned"],
                                            "weights": [0.8, 0.2]}),
                # Single-hop rollup: reconciles with orders.
                Column(name="order_count", type="int",
                       distribution_params={"rollup": {
                           "from_table": "orders", "fk": "customer_id", "agg": "count"}}),
                # MULTI-HOP rollup (G2): payments reached through orders.
                Column(name="lifetime_value", type="float",
                       distribution_params={"rollup": {
                           "from_table": "payments", "via": ["orders"],
                           "fk": "customer_id", "agg": "sum", "column": "amount"}}),
            ],
            "addresses": [
                Column(name="address_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 700}),
                Column(name="customer_id", type="foreign_key",
                       distribution_params={"references": "customers.customer_id"}),
                Column(name="address_type", type="categorical",
                       distribution_params={"choices": ["shipping", "billing"]}),
                Column(name="city", type="text", distribution_params={"subtype": "city"}),
                Column(name="state", type="text", distribution_params={"subtype": "state"}),
                Column(name="zip", type="text", distribution_params={"subtype": "zipcode"}),
            ],
            "subscriptions": [
                Column(name="subscription_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 600}),
                Column(name="customer_id", type="foreign_key",
                       distribution_params={"references": "customers.customer_id"}),
                Column(name="plan", type="categorical",
                       distribution_params={"choices": ["starter", "pro", "enterprise"],
                                            "weights": [0.5, 0.35, 0.15]}),
                Column(name="mrr", type="float",
                       distribution_params={"min": 9.0, "max": 499.0}),
                Column(name="start_date", type="datetime",
                       distribution_params={"start": "2022-06-01", "end": "2024-12-31"}),
                Column(name="status", type="categorical",
                       distribution_params={"choices": SUB_STATUSES,
                                            "weights": [0.7, 0.1, 0.2]}),
                Column(name="cancelled_at", type="datetime", nullable=True,
                       distribution_params={"start": "2022-07-01", "end": "2025-06-30",
                                            "null_probability": 0.7}),
            ],
            # (constraints for subscriptions/support_tickets/returns/payments are
            #  declared on their Table entries below — status gates its dependent
            #  columns, child money is bounded by the parent order.)
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 2500}),
                Column(name="customer_id", type="foreign_key",
                       distribution_params={"references": "customers.customer_id",
                                            # Real order counts are heavy-tailed:
                                            # a few whales, a long tail, and some
                                            # customers who never buy at all.
                                            "sampling": "pareto", "alpha": 1.2}),
                Column(name="order_date", type="datetime",
                       distribution_params={"start": "2022-07-01", "end": "2025-06-30"}),
                Column(name="status", type="categorical",
                       distribution_params={"choices": ORDER_STATUSES,
                                            "weights": [0.10, 0.15, 0.60, 0.03, 0.07, 0.05]}),
                # Reconciles with its own order_items rows.
                Column(name="total_amount", type="float",
                       distribution_params={"rollup": {
                           "from_table": "order_items", "fk": "order_id",
                           "agg": "sum", "column": "line_total"}}),
            ],
            "order_items": [
                Column(name="item_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 6000}),
                Column(name="order_id", type="foreign_key",
                       distribution_params={"references": "orders.order_id"}),
                Column(name="product_id", type="foreign_key",
                       distribution_params={"references": "products.product_id"}),
                Column(name="quantity", type="int",
                       distribution_params={"min": 1, "max": 5}),
                # Diamond: the price on the line must be the price of the product.
                Column(name="unit_price", type="float",
                       distribution_params={"formula": "@products.price"}),
                Column(name="line_total", type="float",
                       distribution_params={"formula": "quantity * unit_price"}),
            ],
            "payments": [
                Column(name="payment_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 2800}),
                Column(name="order_id", type="foreign_key",
                       distribution_params={"references": "orders.order_id"}),
                Column(name="payment_date", type="datetime",
                       distribution_params={"start": "2022-07-01", "end": "2025-06-30"}),
                Column(name="method", type="categorical",
                       distribution_params={"choices": [
                           "credit_card", "debit_card", "bank_transfer", "gift_card"]}),
                Column(name="amount", type="float",
                       distribution_params={"distribution": "lognormal",
                                            "mu": 4.0, "sigma": 0.7, "min": 1.0}),
            ],
            "shipments": [
                Column(name="shipment_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 1800}),
                Column(name="order_id", type="foreign_key",
                       distribution_params={"references": "orders.order_id"}),
                Column(name="carrier", type="categorical",
                       distribution_params={"choices": ["UPS", "FedEx", "USPS", "DHL"]}),
                Column(name="shipped_date", type="datetime",
                       distribution_params={"start": "2022-07-01", "end": "2025-06-30"}),
            ],
            "returns": [
                Column(name="return_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 300}),
                Column(name="order_id", type="foreign_key",
                       distribution_params={"references": "orders.order_id"}),
                Column(name="return_date", type="datetime",
                       distribution_params={"start": "2022-07-15", "end": "2025-06-30"}),
                Column(name="refund_amount", type="float",
                       distribution_params={"distribution": "lognormal",
                                            "mu": 3.5, "sigma": 0.7, "min": 1.0}),
                Column(name="reason", type="categorical",
                       distribution_params={"choices": [
                           "damaged", "wrong_item", "not_as_described", "changed_mind"]}),
            ],
            "support_tickets": [
                Column(name="ticket_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 800}),
                Column(name="customer_id", type="foreign_key",
                       distribution_params={"references": "customers.customer_id"}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2022-07-01", "end": "2025-06-30"}),
                Column(name="status", type="categorical",
                       distribution_params={"choices": TICKET_STATUSES,
                                            "weights": [0.2, 0.15, 0.45, 0.2]}),
                Column(name="resolved_at", type="datetime", nullable=True,
                       distribution_params={"start": "2022-07-02", "end": "2025-06-30",
                                            "null_probability": 0.35}),
            ],
        },
        relationships=[
            Relationship(parent_table="categories", child_table="products",
                         parent_key="category_id", child_key="category_id"),
            Relationship(parent_table="customers", child_table="addresses",
                         parent_key="customer_id", child_key="customer_id"),
            Relationship(parent_table="customers", child_table="subscriptions",
                         parent_key="customer_id", child_key="customer_id"),
            Relationship(parent_table="customers", child_table="orders",
                         parent_key="customer_id", child_key="customer_id"),
            Relationship(parent_table="orders", child_table="order_items",
                         parent_key="order_id", child_key="order_id",
                         min_children=1),   # an order with zero items is not an order
            Relationship(parent_table="products", child_table="order_items",
                         parent_key="product_id", child_key="product_id"),
            # Status-gated children: a payment/shipment/return only ever
            # references an order whose status makes it possible.
            Relationship(parent_table="orders", child_table="payments",
                         parent_key="order_id", child_key="order_id",
                         filters={"status": ["placed", "shipped", "completed",
                                             "return_pending", "returned"]}),
            Relationship(parent_table="orders", child_table="shipments",
                         parent_key="order_id", child_key="order_id",
                         filters={"status": ["shipped", "completed",
                                             "return_pending", "returned"]}),
            Relationship(parent_table="orders", child_table="returns",
                         parent_key="order_id", child_key="order_id",
                         filters={"status": ["returned", "return_pending"]}),
            Relationship(parent_table="customers", child_table="support_tickets",
                         parent_key="customer_id", child_key="customer_id"),
        ],
    )


# --------------------------------------------------------------------------- #
# The assertions
# --------------------------------------------------------------------------- #

def _pk(table: str, col: str) -> List[Tuple[str, str, str]]:
    return [
        ("A", f"{table}.{col} unique",
         f"SELECT count(*) - count(DISTINCT {col}) FROM {table}"),
        ("A", f"{table}.{col} not null",
         f"SELECT count(*) FROM {table} WHERE {col} IS NULL"),
    ]


def _fk(child: str, col: str, parent: str, pcol: str) -> List[Tuple[str, str, str]]:
    return [
        ("A", f"{child}.{col} -> {parent}.{pcol} no orphans",
         f"SELECT count(*) FROM {child} c LEFT JOIN {parent} p "
         f"ON c.{col} = p.{pcol} WHERE p.{pcol} IS NULL"),
    ]


def build_assertions() -> List[Tuple[str, str, str]]:
    a: List[Tuple[str, str, str]] = []

    # ---- A. structural -----------------------------------------------------
    for t, c in [("categories", "category_id"), ("products", "product_id"),
                 ("customers", "customer_id"), ("addresses", "address_id"),
                 ("subscriptions", "subscription_id"), ("orders", "order_id"),
                 ("order_items", "item_id"), ("payments", "payment_id"),
                 ("shipments", "shipment_id"), ("returns", "return_id"),
                 ("support_tickets", "ticket_id")]:
        a += _pk(t, c)
    a += _fk("products", "category_id", "categories", "category_id")
    a += _fk("addresses", "customer_id", "customers", "customer_id")
    a += _fk("subscriptions", "customer_id", "customers", "customer_id")
    a += _fk("orders", "customer_id", "customers", "customer_id")
    a += _fk("order_items", "order_id", "orders", "order_id")
    a += _fk("order_items", "product_id", "products", "product_id")
    a += _fk("payments", "order_id", "orders", "order_id")
    a += _fk("shipments", "order_id", "orders", "order_id")
    a += _fk("returns", "order_id", "orders", "order_id")
    a += _fk("support_tickets", "customer_id", "customers", "customer_id")

    # ---- B. domain ---------------------------------------------------------
    a += [
        ("B", "products.price > 0",
         "SELECT count(*) FROM products WHERE price <= 0"),
        ("B", "products.cost > 0",
         "SELECT count(*) FROM products WHERE cost <= 0"),
        ("B", "products.price > cost (declared inequality)",
         "SELECT count(*) FROM products WHERE price <= cost"),
        ("B", "categories.margin_pct in [0.05, 0.60]",
         "SELECT count(*) FROM categories WHERE margin_pct < 0.05 OR margin_pct > 0.60"),
        ("B", "order_items.quantity in [1, 5]",
         "SELECT count(*) FROM order_items WHERE quantity < 1 OR quantity > 5"),
        ("B", "order_items.unit_price > 0",
         "SELECT count(*) FROM order_items WHERE unit_price <= 0"),
        ("B", "payments.amount > 0",
         "SELECT count(*) FROM payments WHERE amount <= 0"),
        ("B", "returns.refund_amount > 0",
         "SELECT count(*) FROM returns WHERE refund_amount <= 0"),
        ("B", "subscriptions.mrr in [9, 499]",
         "SELECT count(*) FROM subscriptions WHERE mrr < 9 OR mrr > 499"),
        ("B", "orders.status in enum",
         "SELECT count(*) FROM orders WHERE status NOT IN "
         "('placed','shipped','completed','return_pending','returned','cancelled')"),
        ("B", "subscriptions.status in enum",
         "SELECT count(*) FROM subscriptions WHERE status NOT IN "
         "('active','past_due','cancelled')"),
        ("B", "support_tickets.status in enum",
         "SELECT count(*) FROM support_tickets WHERE status NOT IN "
         "('open','pending','resolved','closed')"),
        ("B", "customers.email has an @ and a dot",
         "SELECT count(*) FROM customers WHERE email NOT LIKE '%@%.%'"),
        ("B", "customers.email unique",
         "SELECT count(*) - count(DISTINCT email) FROM customers"),
        ("B", "customers.state is a real US state",
         f"SELECT count(*) FROM customers WHERE state NOT IN ({US_STATES})"),
        ("B", "addresses.state is a real US state",
         f"SELECT count(*) FROM addresses WHERE state NOT IN ({US_STATES})"),
        ("B", "customers.zip is 5 digits",
         "SELECT count(*) FROM customers WHERE NOT regexp_matches(zip, '^[0-9]{5}$')"),
        ("B", "addresses.zip is 5 digits",
         "SELECT count(*) FROM addresses WHERE NOT regexp_matches(zip, '^[0-9]{5}$')"),
        ("B", "customers.full_name is two-plus words, no filler",
         "SELECT count(*) FROM customers WHERE full_name NOT LIKE '% %' "
         "OR lower(full_name) IN ('test','unknown','n/a','none','user','name')"),
        ("B", "products.product_name not filler",
         "SELECT count(*) FROM products WHERE lower(product_name) IN "
         "('test','unknown','n/a','none','product','item') OR length(product_name) < 3"),
    ]

    # ---- C. temporal causality --------------------------------------------
    a += [
        ("C", "orders never precede customer signup",
         "SELECT count(*) FROM orders o JOIN customers c USING (customer_id) "
         "WHERE o.order_date < c.signup_date"),
        ("C", "subscriptions never precede customer signup",
         "SELECT count(*) FROM subscriptions s JOIN customers c USING (customer_id) "
         "WHERE s.start_date < c.signup_date"),
        ("C", "support tickets never precede customer signup",
         "SELECT count(*) FROM support_tickets t JOIN customers c USING (customer_id) "
         "WHERE t.created_at < c.signup_date"),
        ("C", "payments never precede their order",
         "SELECT count(*) FROM payments p JOIN orders o USING (order_id) "
         "WHERE p.payment_date < o.order_date"),
        ("C", "shipments never precede their order",
         "SELECT count(*) FROM shipments s JOIN orders o USING (order_id) "
         "WHERE s.shipped_date < o.order_date"),
        ("C", "returns never precede their order",
         "SELECT count(*) FROM returns r JOIN orders o USING (order_id) "
         "WHERE r.return_date < o.order_date"),
        ("C", "order_items never reference a product created after the order",
         "SELECT count(*) FROM order_items i JOIN orders o USING (order_id) "
         "JOIN products p USING (product_id) WHERE o.order_date < p.created_at"),
        ("C", "tickets resolved after they were created",
         "SELECT count(*) FROM support_tickets "
         "WHERE resolved_at IS NOT NULL AND resolved_at < created_at"),
        ("C", "subscriptions cancelled after they started",
         "SELECT count(*) FROM subscriptions "
         "WHERE cancelled_at IS NOT NULL AND cancelled_at < start_date"),
        ("C", "no order predates the shop's first customer",
         "SELECT count(*) FROM orders WHERE order_date < "
         "(SELECT min(signup_date) FROM customers)"),
    ]

    # ---- D. status implies (G1) -------------------------------------------
    a += [
        ("D", "cancelled subscriptions have cancelled_at",
         "SELECT count(*) FROM subscriptions "
         "WHERE status = 'cancelled' AND cancelled_at IS NULL"),
        ("D", "active subscriptions have no cancelled_at",
         "SELECT count(*) FROM subscriptions "
         "WHERE status = 'active' AND cancelled_at IS NOT NULL"),
        ("D", "past_due subscriptions have no cancelled_at",
         "SELECT count(*) FROM subscriptions "
         "WHERE status = 'past_due' AND cancelled_at IS NOT NULL"),
        ("D", "resolved tickets have resolved_at",
         "SELECT count(*) FROM support_tickets "
         "WHERE status = 'resolved' AND resolved_at IS NULL"),
        ("D", "closed tickets have resolved_at",
         "SELECT count(*) FROM support_tickets "
         "WHERE status = 'closed' AND resolved_at IS NULL"),
        ("D", "open tickets have no resolved_at",
         "SELECT count(*) FROM support_tickets "
         "WHERE status = 'open' AND resolved_at IS NOT NULL"),
        ("D", "pending tickets have no resolved_at",
         "SELECT count(*) FROM support_tickets "
         "WHERE status = 'pending' AND resolved_at IS NOT NULL"),
        ("D", "shipments only for shipped/completed/returned orders",
         "SELECT count(*) FROM shipments s JOIN orders o USING (order_id) "
         "WHERE o.status IN ('placed','cancelled')"),
        ("D", "returns only for returned/return_pending orders",
         "SELECT count(*) FROM returns r JOIN orders o USING (order_id) "
         "WHERE o.status NOT IN ('returned','return_pending')"),
        ("D", "cancelled orders have no payments",
         "SELECT count(*) FROM payments p JOIN orders o USING (order_id) "
         "WHERE o.status = 'cancelled'"),
    ]

    # ---- E. reconciliation (incl. multi-hop, G2) ---------------------------
    a += [
        ("E", "orders.total_amount = sum(order_items.line_total), to the cent",
         "SELECT count(*) FROM orders o LEFT JOIN "
         "(SELECT order_id, sum(line_total) s FROM order_items GROUP BY order_id) i "
         "USING (order_id) WHERE abs(coalesce(i.s, 0) - o.total_amount) > 0.01"),
        ("E", "customers.order_count = count(orders), exactly",
         "SELECT count(*) FROM customers c LEFT JOIN "
         "(SELECT customer_id, count(*) n FROM orders GROUP BY customer_id) o "
         "USING (customer_id) WHERE coalesce(o.n, 0) != c.order_count"),
        ("E", "customers.lifetime_value = sum(payments via orders), to the cent",
         "SELECT count(*) FROM customers c LEFT JOIN "
         "(SELECT o.customer_id, sum(p.amount) s FROM payments p "
         " JOIN orders o USING (order_id) GROUP BY o.customer_id) x "
         "USING (customer_id) WHERE abs(coalesce(x.s, 0) - c.lifetime_value) > 0.01"),
        ("E", "grand total: sum(orders.total_amount) = sum(order_items.line_total)",
         "SELECT CASE WHEN abs((SELECT sum(total_amount) FROM orders) - "
         "(SELECT sum(line_total) FROM order_items)) > 0.05 THEN 1 ELSE 0 END"),
        ("E", "grand total: sum(customers.lifetime_value) = sum(payments.amount)",
         "SELECT CASE WHEN abs((SELECT sum(lifetime_value) FROM customers) - "
         "(SELECT sum(amount) FROM payments)) > 0.05 THEN 1 ELSE 0 END"),
        ("E", "grand total: sum(customers.order_count) = count(orders)",
         "SELECT CASE WHEN (SELECT sum(order_count) FROM customers) != "
         "(SELECT count(*) FROM orders) THEN 1 ELSE 0 END"),
        ("E", "refund never exceeds the order total",
         "SELECT count(*) FROM returns r JOIN orders o USING (order_id) "
         "WHERE r.refund_amount > o.total_amount + 0.01"),
        ("E", "payments per order never exceed the order total",
         "SELECT count(*) FROM (SELECT p.order_id, sum(p.amount) s, any_value(o.total_amount) t "
         "FROM payments p JOIN orders o USING (order_id) GROUP BY p.order_id) "
         "WHERE s > t + 0.01"),
    ]

    # ---- F. diamond / denormalized copies ----------------------------------
    a += [
        ("F", "order_items.unit_price equals its product's price",
         "SELECT count(*) FROM order_items i JOIN products p USING (product_id) "
         "WHERE abs(i.unit_price - p.price) > 0.01"),
        ("F", "every product's price is one value everywhere it appears",
         "SELECT count(*) FROM (SELECT product_id FROM order_items "
         "GROUP BY product_id HAVING count(DISTINCT round(unit_price, 2)) > 1)"),
    ]

    # ---- G. geo internal consistency (G4) ----------------------------------
    a += [
        ("G", "customers: one state per city",
         "SELECT count(*) FROM (SELECT city FROM customers "
         "GROUP BY city HAVING count(DISTINCT state) > 1)"),
        ("G", "customers: one city per zip",
         "SELECT count(*) FROM (SELECT zip FROM customers "
         "GROUP BY zip HAVING count(DISTINCT city) > 1)"),
        ("G", "addresses: one state per city",
         "SELECT count(*) FROM (SELECT city FROM addresses "
         "GROUP BY city HAVING count(DISTINCT state) > 1)"),
        ("G", "addresses: one city per zip",
         "SELECT count(*) FROM (SELECT zip FROM addresses "
         "GROUP BY zip HAVING count(DISTINCT city) > 1)"),
        ("G", "city/state pairs agree across customers and addresses",
         "SELECT count(*) FROM (SELECT city, state FROM customers "
         "INTERSECT SELECT city, s2.state FROM addresses a "
         "JOIN (SELECT city c2, state FROM customers) s2 ON a.city = s2.c2 "
         "WHERE a.state != s2.state)"),
    ]

    # ---- H. derived arithmetic ---------------------------------------------
    a += [
        ("H", "order_items.line_total = quantity * unit_price",
         "SELECT count(*) FROM order_items "
         "WHERE abs(line_total - quantity * unit_price) > 0.01"),
        ("H", "products.price = cost * 1.65 (declared formula)",
         "SELECT count(*) FROM products WHERE abs(price - cost * 1.65) > 0.01"),
    ]

    # ---- I. distribution sanity --------------------------------------------
    a += [
        ("I", "some customers have zero orders (1%-60%)",
         "SELECT CASE WHEN (SELECT count(*) FROM customers WHERE order_count = 0) "
         "BETWEEN 5 AND 300 THEN 0 ELSE 1 END"),
        ("I", "top customer has 3+ orders (degree spread)",
         "SELECT CASE WHEN (SELECT max(order_count) FROM customers) >= 3 THEN 0 ELSE 1 END"),
        ("I", "order dates span at least 300 days",
         "SELECT CASE WHEN date_diff('day', (SELECT min(order_date) FROM orders), "
         "(SELECT max(order_date) FROM orders)) >= 300 THEN 0 ELSE 1 END"),
        ("I", "payment amounts are not near-constant",
         "SELECT CASE WHEN (SELECT stddev(amount) FROM payments) > 5 THEN 0 ELSE 1 END"),
        ("I", "at least 60 distinct product names",
         "SELECT CASE WHEN (SELECT count(DISTINCT product_name) FROM products) >= 60 "
         "THEN 0 ELSE 1 END"),
        ("I", "at least 300 distinct customer names",
         "SELECT CASE WHEN (SELECT count(DISTINCT full_name) FROM customers) >= 300 "
         "THEN 0 ELSE 1 END"),
        # Degeneracy check, not a richness quota: it exists to catch a
        # single-state collapse, and 10 distinct states is comfortably alive.
        ("I", "customers span 10+ states",
         "SELECT CASE WHEN (SELECT count(DISTINCT state) FROM customers) >= 10 "
         "THEN 0 ELSE 1 END"),
        ("I", "every category has a product",
         "SELECT count(*) FROM categories c LEFT JOIN products p USING (category_id) "
         "WHERE p.product_id IS NULL"),
        ("I", "order status mix is not degenerate (3+ statuses present)",
         "SELECT CASE WHEN (SELECT count(DISTINCT status) FROM orders) >= 3 "
         "THEN 0 ELSE 1 END"),
        ("I", "multi-line orders exist (junction is a real M:N)",
         "SELECT CASE WHEN (SELECT max(n) FROM (SELECT count(*) n FROM order_items "
         "GROUP BY order_id)) >= 2 THEN 0 ELSE 1 END"),
    ]
    return a


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

def run(json_path: str | None = None) -> int:
    t0 = time.time()
    schema = build_schema()
    tables = misata.generate_from_schema(schema)
    gen_secs = time.time() - t0

    con = duckdb.connect()
    for name, df in tables.items():
        con.register(name, df)

    assertions = build_assertions()
    results: List[Dict[str, Any]] = []
    for cat, name, sql in assertions:
        try:
            violations = int(con.sql(sql).fetchone()[0] or 0)
            error = None
        except Exception as e:  # a failing query is a failing assertion
            violations, error = -1, str(e).split("\n")[0]
        results.append({"category": cat, "name": name,
                        "violations": violations, "error": error,
                        "known_red": name in KNOWN_RED})

    cats = sorted({r["category"] for r in results})
    cat_names = {"A": "structural", "B": "domain", "C": "temporal",
                 "D": "status-implies", "E": "reconciliation", "F": "diamond",
                 "G": "geo", "H": "arithmetic", "I": "distribution"}
    passed = sum(1 for r in results if r["violations"] == 0)
    total = len(results)

    unexpected = [r for r in results if r["violations"] != 0 and not r["known_red"]]
    promotable = [r for r in results if r["violations"] == 0 and r["known_red"]]

    print(f"\nTHE GAUNTLET  --  11 tables, {sum(len(t) for t in tables.values()):,} rows, "
          f"{total} assertions, generated in {gen_secs:.1f}s\n")
    for cat in cats:
        rs = [r for r in results if r["category"] == cat]
        ok = sum(1 for r in rs if r["violations"] == 0)
        print(f"  {cat}  {cat_names.get(cat, cat):<15} {ok:>3}/{len(rs)}")
        for r in rs:
            if r["violations"] != 0:
                detail = r["error"] or f"{r['violations']} violating rows"
                tag = "KNOWN-RED" if r["known_red"] else "FAIL"
                print(f"       {tag}  {r['name']}  ({detail})")
                if r["known_red"]:
                    print(f"                 roadmap: {KNOWN_RED[r['name']]}")
    print(f"\n  TOTAL  {passed}/{total} "
          f"({100.0 * passed / total:.0f}%)")
    if unexpected:
        print(f"  REGRESSION: {len(unexpected)} assertion(s) failed that "
              "previously passed — the build fails.")
    for r in promotable:
        print(f"  PROMOTE: known-red '{r['name']}' now passes — "
              "remove it from KNOWN_RED.")
    print()

    if json_path:
        with open(json_path, "w") as f:
            json.dump({"passed": passed, "total": total, "results": results,
                       "known_red": KNOWN_RED,
                       "generation_seconds": round(gen_secs, 2)}, f, indent=2)
        print(f"  report written to {json_path}")
    # Exit contract for CI: only an UNEXPECTED failure (or a stale known-red
    # entry that should be promoted) is fatal.
    return len(unexpected) + len(promotable)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the Misata gauntlet")
    ap.add_argument("--json", default=None, help="write a JSON report here")
    args = ap.parse_args()
    sys.exit(1 if run(args.json) else 0)


if __name__ == "__main__":
    main()
