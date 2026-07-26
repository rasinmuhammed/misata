"""Run the Gauntlet's 99 assertions against other generators.

Methodology, stated plainly because fairness is the whole point:

- **Faker**: a careful but ordinary Faker script. Foreign keys are kept valid
  (sampled from parent ids, the way every Faker tutorial does it), formats are
  real (faker.city(), faker.zipcode(), real status enums), quantities and
  prices live in the same ranges as the Misata schema, and line_total is
  computed as quantity * unit_price because a careful developer would. What the
  script does NOT do is hand-build a constraint solver: aggregates, status
  gates, temporal ordering and geo consistency are drawn like any other column,
  because Faker has no concept of them. If you wrote all of that by hand you
  would not be benchmarking Faker any more — you would be writing the
  correctness layer yourself, which is the point being measured.

- **SDV (HMA)**: the code path below is written and ready, using SDV's own
  intended workflow (fit HMASynthesizer on the Misata output, which passes
  98/99 so the training data genuinely contains the invariants, then sample a
  synthetic copy). **It has not been run here**, so no SDV score is published.
  Anyone with SDV installed can run `--tool sdv` and get one. The question the
  score would answer: how many invariants present in its training data does the
  synthetic copy preserve?

- **Seedfast**: not scored, and cannot be. It is a closed-source CLI requiring
  an account and a live Postgres database; there is nothing to run offline. The
  harness is public — anyone with a subscription can load its output into these
  table names and score it.

**Only published numbers are ones actually measured on this machine.** An
unrun tool gets no number, not an estimated one.

Usage:
    python -m benchmarks.gauntlet_compare --tool faker
    python -m benchmarks.gauntlet_compare --tool sdv
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Dict

import numpy as np
import pandas as pd

from benchmarks.gauntlet import (build_assertions, build_schema, KNOWN_RED,
                                 ORDER_STATUSES, SUB_STATUSES, TICKET_STATUSES)

SEED = 7
ROWS = {"categories": 8, "products": 120, "customers": 500, "addresses": 700,
        "subscriptions": 600, "orders": 2500, "order_items": 6000,
        "payments": 2800, "shipments": 1800, "returns": 300,
        "support_tickets": 800}


# --------------------------------------------------------------------------- #
# Faker
# --------------------------------------------------------------------------- #

def _state(fake) -> str:
    """Faker's fairest US state code: no territories, no freely associated
    states. Without both flags it emits FM/MH/PW, which are not US states and
    would be an unfair mark against Faker rather than a real limitation."""
    return fake.state_abbr(include_territories=False,
                           include_freely_associated_states=False)


def generate_with_faker() -> Dict[str, pd.DataFrame]:
    from faker import Faker

    fake = Faker()
    Faker.seed(SEED)
    rng = np.random.default_rng(SEED)

    def dt(start: str, end: str, n: int) -> pd.Series:
        s, e = pd.Timestamp(start).value, pd.Timestamp(end).value
        return pd.to_datetime(rng.integers(s, e, size=n))

    t: Dict[str, pd.DataFrame] = {}

    t["categories"] = pd.DataFrame({
        "category_id": np.arange(1, ROWS["categories"] + 1),
        "category_name": ["Electronics", "Home & Kitchen", "Sports", "Books",
                          "Toys", "Beauty", "Garden", "Automotive"],
        "margin_pct": rng.uniform(0.05, 0.60, ROWS["categories"]),
    })

    n = ROWS["products"]
    cost = np.exp(rng.normal(3.0, 0.6, n)).clip(1.0)
    t["products"] = pd.DataFrame({
        "product_id": np.arange(1, n + 1),
        "category_id": rng.choice(t["categories"]["category_id"], n),
        "product_name": [fake.catch_phrase() for _ in range(n)],
        "cost": cost,
        # The spec declares price = cost * 1.65; a careful dev implements a
        # one-line formula, so Faker gets it.
        "price": cost * 1.65,
        "created_at": dt("2022-01-01", "2023-06-30", n),
    })

    n = ROWS["customers"]
    t["customers"] = pd.DataFrame({
        "customer_id": np.arange(1, n + 1),
        "full_name": [fake.name() for _ in range(n)],
        "email": [fake.unique.email() for _ in range(n)],
        "city": [fake.city() for _ in range(n)],
        "state": [_state(fake) for _ in range(n)],
        "zip": [fake.zipcode() for _ in range(n)],
        "signup_date": dt("2022-06-01", "2024-06-30", n),
        "status": rng.choice(["active", "churned"], n, p=[0.8, 0.2]),
        # Faker has no concept of a roll-up; these are columns like any other.
        "order_count": rng.integers(0, 15, n),
        "lifetime_value": np.round(np.exp(rng.normal(5.0, 1.0, n)), 2),
    })

    n = ROWS["addresses"]
    t["addresses"] = pd.DataFrame({
        "address_id": np.arange(1, n + 1),
        "customer_id": rng.choice(t["customers"]["customer_id"], n),
        "address_type": rng.choice(["shipping", "billing"], n),
        "city": [fake.city() for _ in range(n)],
        "state": [_state(fake) for _ in range(n)],
        "zip": [fake.zipcode() for _ in range(n)],
    })

    n = ROWS["subscriptions"]
    t["subscriptions"] = pd.DataFrame({
        "subscription_id": np.arange(1, n + 1),
        "customer_id": rng.choice(t["customers"]["customer_id"], n),
        "plan": rng.choice(["starter", "pro", "enterprise"], n,
                           p=[0.5, 0.35, 0.15]),
        "mrr": np.round(rng.uniform(9, 499, n), 2),
        "start_date": dt("2022-06-01", "2024-12-31", n),
        "status": rng.choice(SUB_STATUSES, n, p=[0.7, 0.1, 0.2]),
        "cancelled_at": dt("2022-07-01", "2025-06-30", n).where(
            rng.random(n) > 0.7, pd.NaT),
    })

    n = ROWS["orders"]
    t["orders"] = pd.DataFrame({
        "order_id": np.arange(1, n + 1),
        "customer_id": rng.choice(t["customers"]["customer_id"], n),
        "order_date": dt("2022-07-01", "2025-06-30", n),
        "status": rng.choice(ORDER_STATUSES, n,
                             p=[0.10, 0.15, 0.60, 0.03, 0.07, 0.05]),
        "total_amount": np.round(np.exp(rng.normal(4.5, 0.8, n)), 2),
        # The four per-state timestamps the schema calls for. Faker has no
        # concept of a state machine, so each is drawn independently with a
        # plausible null rate, which is exactly what a careful script does when
        # the tool offers nothing better. Including them keeps the comparison
        # on the same 110 assertions rather than scoring Faker on columns it
        # was never asked to produce.
        "placed_at": dt("2022-07-01", "2025-06-30", n),
        "shipped_at": dt("2022-07-01", "2025-06-30", n).where(rng.random(n) > 0.3, pd.NaT),
        "completed_at": dt("2022-07-01", "2025-06-30", n).where(rng.random(n) > 0.4, pd.NaT),
        "cancelled_at": dt("2022-07-01", "2025-06-30", n).where(rng.random(n) > 0.9, pd.NaT),
    })

    n = ROWS["order_items"]
    qty = rng.integers(1, 6, n)
    prod_idx = rng.integers(0, ROWS["products"], n)
    unit_price = t["products"]["price"].to_numpy()[prod_idx]
    t["order_items"] = pd.DataFrame({
        "item_id": np.arange(1, n + 1),
        "order_id": rng.choice(t["orders"]["order_id"], n),
        "product_id": t["products"]["product_id"].to_numpy()[prod_idx],
        "quantity": qty,
        "unit_price": unit_price,           # a careful dev joins the price in
        "line_total": qty * unit_price,     # and computes the line
    })

    n = ROWS["payments"]
    t["payments"] = pd.DataFrame({
        "payment_id": np.arange(1, n + 1),
        "order_id": rng.choice(t["orders"]["order_id"], n),
        "payment_date": dt("2022-07-01", "2025-06-30", n),
        "method": rng.choice(["credit_card", "debit_card", "bank_transfer",
                              "gift_card"], n),
        "amount": np.round(np.exp(rng.normal(4.0, 0.7, n)).clip(1.0), 2),
    })

    n = ROWS["shipments"]
    t["shipments"] = pd.DataFrame({
        "shipment_id": np.arange(1, n + 1),
        "order_id": rng.choice(t["orders"]["order_id"], n),
        "carrier": rng.choice(["UPS", "FedEx", "USPS", "DHL"], n),
        "shipped_date": dt("2022-07-01", "2025-06-30", n),
    })

    n = ROWS["returns"]
    t["returns"] = pd.DataFrame({
        "return_id": np.arange(1, n + 1),
        "order_id": rng.choice(t["orders"]["order_id"], n),
        "return_date": dt("2022-07-15", "2025-06-30", n),
        "refund_amount": np.round(np.exp(rng.normal(3.5, 0.7, n)).clip(1.0), 2),
        "reason": rng.choice(["damaged", "wrong_item", "not_as_described",
                              "changed_mind"], n),
    })

    n = ROWS["support_tickets"]
    t["support_tickets"] = pd.DataFrame({
        "ticket_id": np.arange(1, n + 1),
        "customer_id": rng.choice(t["customers"]["customer_id"], n),
        "created_at": dt("2022-07-01", "2025-06-30", n),
        "status": rng.choice(TICKET_STATUSES, n, p=[0.2, 0.15, 0.45, 0.2]),
        "resolved_at": dt("2022-07-02", "2025-06-30", n).where(
            rng.random(n) > 0.35, pd.NaT),
    })
    return t


# --------------------------------------------------------------------------- #
# SDV (HMA): fit on Misata's output, sample a synthetic copy
# --------------------------------------------------------------------------- #

def generate_with_sdv() -> Dict[str, pd.DataFrame]:
    import misata
    from sdv.metadata import MultiTableMetadata
    from sdv.multi_table import HMASynthesizer

    real = misata.generate_from_schema(build_schema())

    metadata = MultiTableMetadata()
    for name, df in real.items():
        metadata.detect_table_from_dataframe(name, df)
    pk = {"categories": "category_id", "products": "product_id",
          "customers": "customer_id", "addresses": "address_id",
          "subscriptions": "subscription_id", "orders": "order_id",
          "order_items": "item_id", "payments": "payment_id",
          "shipments": "shipment_id", "returns": "return_id",
          "support_tickets": "ticket_id"}
    for name, key in pk.items():
        metadata.update_column(name, key, sdtype="id")
        metadata.set_primary_key(name, key)
    rels = [("categories", "products", "category_id"),
            ("customers", "addresses", "customer_id"),
            ("customers", "subscriptions", "customer_id"),
            ("customers", "orders", "customer_id"),
            ("orders", "order_items", "order_id"),
            ("products", "order_items", "product_id"),
            ("orders", "payments", "order_id"),
            ("orders", "shipments", "order_id"),
            ("orders", "returns", "order_id"),
            ("customers", "support_tickets", "customer_id")]
    for parent, child, key in rels:
        metadata.update_column(child, key, sdtype="id")
        metadata.add_relationship(parent_table_name=parent,
                                  child_table_name=child,
                                  parent_primary_key=key,
                                  child_foreign_key=key)

    synth = HMASynthesizer(metadata)
    synth.fit(real)
    return synth.sample(scale=1.0)


# --------------------------------------------------------------------------- #
# Runner: same assertions, different generator
# --------------------------------------------------------------------------- #

def score(tables: Dict[str, pd.DataFrame], label: str,
          json_path: str | None) -> int:
    import duckdb
    con = duckdb.connect()
    for name, df in tables.items():
        con.register(name, df)
    results = []
    for cat, name, sql in build_assertions():
        try:
            violations = int(con.sql(sql).fetchone()[0] or 0)
            error = None
        except Exception as e:
            violations, error = -1, str(e).split("\n")[0]
        results.append({"category": cat, "name": name,
                        "violations": violations, "error": error})
    passed = sum(1 for r in results if r["violations"] == 0)
    total = len(results)
    by_cat = {}
    for r in results:
        ok, n = by_cat.get(r["category"], (0, 0))
        by_cat[r["category"]] = (ok + (r["violations"] == 0), n + 1)
    print(f"\n{label}: {passed}/{total} "
          f"({100.0 * passed / total:.0f}%)")
    for cat in sorted(by_cat):
        ok, n = by_cat[cat]
        print(f"  {cat}  {ok:>3}/{n}")
    if json_path:
        with open(json_path, "w") as f:
            json.dump({"tool": label, "passed": passed, "total": total,
                       "results": results}, f, indent=2)
        print(f"  report written to {json_path}")
    return passed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", choices=["faker", "sdv"], required=True)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    t0 = time.time()
    tables = generate_with_faker() if args.tool == "faker" else generate_with_sdv()
    print(f"generated with {args.tool} in {time.time() - t0:.1f}s")
    score(tables, args.tool, args.json)


if __name__ == "__main__":
    main()
