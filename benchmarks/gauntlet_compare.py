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
# DDL-only: what a tool that reads your schema can possibly know
# --------------------------------------------------------------------------- #

# A SQL CHECK constraint sees exactly one row of one table. A FOREIGN KEY
# asserts that a parent exists, never that any value agrees with it. That is
# the entire expressive power of a CREATE TABLE statement, and it is the line
# this projection draws.
#
# So this is not a strawman competitor. It is Misata's own engine, given a
# schema reduced to what a database could have told it, run at the same seed.
# Anything the reduced run cannot satisfy was never recoverable from the schema
# by any tool, however well built: the information is not in the input. That
# makes the score an UPPER BOUND for schema-reading generators rather than a
# measurement of any particular product.
#
# The reduction is deliberately generous. Single-row declarations survive even
# when no real team would hand-write the CHECK, because the argument does not
# need them and a generous baseline is harder to dispute.

# Column params a CREATE TABLE can carry: types, ranges, enums, nullability,
# a single-row formula, and the column name itself (which is what "AI planner"
# features in these tools infer semantics from).
_DDL_COLUMN_PARAMS = {
    "min", "max", "choices", "references", "subtype", "formula",
    "start", "end", "null_probability", "decimals",
}

# Distribution shape is not in any DDL. A schema-reading tool knows the column
# is numeric and bounded; it does not know the values are lognormal, nor that
# the status split is 80/20.
_SHAPE_PARAMS = {"distribution", "mu", "sigma", "alpha", "sampling", "weights",
                 "rollup", "_distribution_is_default"}

# Table constraints: single-row CHECKs survive, cross-table ones cannot.
_DDL_CONSTRAINTS = {"inequality", "when_then"}

# Schema-level declarations. A lifecycle and a time grid are single-row facts a
# CHECK could state, so they stay. Everything else is either a distribution, a
# cross-partition behaviour, or an instruction to violate uniqueness, and no
# DDL can express any of those.
_DDL_SCHEMA_DECLS = {"lifecycles", "time_grids"}
_DROPPED_SCHEMA_DECLS = ["duplicates", "late_arrivals", "missingness",
                         "outcome_curves", "group_shares", "waterfalls",
                         "stock_flows", "retention", "typos", "outliers",
                         "noise_config", "events", "event_logs", "closures",
                         "dag_edges", "bitemporal", "degradations",
                         "vocabularies", "realism"]


def project_to_ddl(schema):
    """Reduce a SchemaConfig to what a CREATE TABLE statement could express.

    Returns (reduced_schema, dropped) where `dropped` lists every declaration
    removed, so the reduction is auditable rather than asserted.
    """
    s = schema.model_copy(deep=True)
    dropped: list[str] = []

    for table, cols in s.columns.items():
        for col in cols:
            params = col.distribution_params or {}
            if "rollup" in params:
                dropped.append(f"rollup {table}.{col.name}")
            for key in list(params):
                if key in _SHAPE_PARAMS:
                    params.pop(key)
                elif key not in _DDL_COLUMN_PARAMS:
                    dropped.append(f"param {table}.{col.name}.{key}")
                    params.pop(key)

    for t in s.tables:
        keep = []
        for c in (t.constraints or []):
            if c.type in _DDL_CONSTRAINTS:
                keep.append(c)
            else:
                dropped.append(f"constraint {t.name}.{c.name} ({c.type})")
        t.constraints = keep

    for decl in _DROPPED_SCHEMA_DECLS:
        v = getattr(s, decl, None)
        if v:
            dropped.append(f"schema.{decl} (x{len(v) if hasattr(v, '__len__') else 1})")
            setattr(s, decl, type(v)() if isinstance(v, (list, dict)) else None)

    return s, dropped


def generate_with_ddl_only():
    import misata
    schema, dropped = project_to_ddl(build_schema())
    print(f"DDL projection dropped {len(dropped)} declaration(s):")
    for d in dropped:
        print(f"    - {d}")
    return misata.generate_from_schema(schema)


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
    ap.add_argument("--tool", choices=["faker", "sdv", "ddl-only"], required=True)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    t0 = time.time()
    gen = {"faker": generate_with_faker, "sdv": generate_with_sdv,
           "ddl-only": generate_with_ddl_only}[args.tool]
    tables = gen()
    print(f"generated with {args.tool} in {time.time() - t0:.1f}s")
    score(tables, args.tool, args.json)


if __name__ == "__main__":
    main()
