"""The Borough: a fourth conformance suite, shaped like a town's day.

The Gauntlet is a flat e-commerce star, the Warren multi-tenant and
event-sourced, the Ledger bitemporal and graph-shaped. All three are green,
and none of them has a notion of *where* anything is. A town does, and it is
awkward in three ways the others are not:

  * **Intervals.** A resident's day is a sequence of stays, and a person is in
    one place at a time. A café has seats, and at no instant does it seat more
    people than it has.
  * **Spans.** An order belongs to a visit, so it is placed after the visitor
    arrives and before they leave, not merely after the visit row exists.
  * **Bounded money under declared totals.** Every account spends within its
    means, while each day's takings and each merchant's share of them are
    declared exactly. A clamp that rescales spending quietly breaks the totals;
    totals that ignore the clamp quietly overdraw accounts.

Plus a pantry ledger that opens at declared levels, the way one day continues
from the previous day's close.

Written assertions-first. A red here names something the language cannot say.

Run:
    python -m benchmarks.borough
    python -m benchmarks.borough --json out.json
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from typing import Dict, List, Tuple

import duckdb

import misata
from misata.schema import (Capacity, Column, Constraint, GroupShares, NoOverlap, OutcomeCurve,
                           Relationship, SchemaConfig, StockFlowIdentity, Table, TimeGrid)

SEED = 31

KNOWN_RED: Dict[str, str] = {}

DAYS = {"2026-11-02": 61_250.00, "2026-11-03": 58_400.50, "2026-11-04": 70_125.25}
MERCHANTS = {"cafe": 0.35, "grocer": 0.40, "bakery": 0.15, "books": 0.10}
PANTRY = {"flour": 140, "eggs": 60, "milk": 85, "coffee": 40, "tea": 25, "sugar": 0}
PERIODS = ["2026-11-02", "2026-11-03", "2026-11-04"]

PK = {"residents": "resident_id", "accounts": "account_id", "places": "place_id",
      "visits": "visit_id", "orders": "order_id", "payments": "payment_id"}
FKS = [("accounts", "resident_id", "residents", "resident_id"),
       ("visits", "resident_id", "residents", "resident_id"),
       ("visits", "place_id", "places", "place_id"),
       ("orders", "visit_id", "visits", "visit_id"),
       ("payments", "account_id", "accounts", "account_id")]


def _int(name: str, lo: int, hi: int, unique: bool = False) -> Column:
    return Column(name=name, type="int", unique=unique, distribution_params={"min": lo, "max": hi})


def build_schema() -> SchemaConfig:
    kinds = ["cafe", "shop", "office"]
    return SchemaConfig(
        name="borough",
        seed=SEED,
        tables=[
            Table(name="residents", row_count=400),
            Table(name="accounts", row_count=400),
            Table(name="places", row_count=24),
            Table(name="visits", row_count=800, constraints=[
                Constraint(name="stays_forward", type="inequality", column_a="left_at",
                           operator=">", column_b="arrived_at")]),
            Table(name="orders", row_count=600),
            Table(name="payments", row_count=1800, constraints=[
                Constraint(name="within_means", type="sum_lte_parent", column="amount",
                           parent_table="accounts", parent_column="spendable")]),
            Table(name="pantry", row_count=len(PANTRY) * len(PERIODS)),
        ],
        columns={
            "residents": [_int("resident_id", 1, 400, unique=True), _int("age", 18, 90)],
            "accounts": [_int("account_id", 1, 400, unique=True),
                         Column(name="resident_id", type="foreign_key"),
                         _int("spendable", 0, 1500)],
            "places": [_int("place_id", 1, 24, unique=True),
                       Column(name="kind", type="categorical",
                              distribution_params={"choices": kinds}),
                       _int("seats", 25, 60)],
            "visits": [
                _int("visit_id", 1, 800, unique=True),
                Column(name="resident_id", type="foreign_key"),
                Column(name="kind", type="categorical", distribution_params={"choices": kinds}),
                Column(name="place_id", type="foreign_key"),
                Column(name="arrived_at", type="datetime",
                       distribution_params={"start": "2026-11-02 08:00:00",
                                            "end": "2026-11-02 12:00:00"}),
                Column(name="left_at", type="datetime",
                       distribution_params={"start": "2026-11-02 09:00:00",
                                            "end": "2026-11-02 14:00:00"}),
            ],
            "orders": [
                _int("order_id", 1, 600, unique=True),
                Column(name="visit_id", type="foreign_key"),
                Column(name="ordered_at", type="datetime",
                       distribution_params={"start": "2026-11-02 08:00:00",
                                            "end": "2026-11-02 21:00:00"}),
                Column(name="total", type="float",
                       distribution_params={"min": 2.5, "max": 40, "decimals": 2}),
            ],
            "payments": [
                _int("payment_id", 1, 1800, unique=True),
                Column(name="account_id", type="foreign_key"),
                Column(name="merchant", type="categorical",
                       distribution_params={"choices": list(MERCHANTS)}),
                Column(name="amount", type="float",
                       distribution_params={"min": 1, "max": 400, "decimals": 2}),
                Column(name="paid_on", type="date",
                       distribution_params={"start": PERIODS[0], "end": PERIODS[-1]}),
            ],
            "pantry": [
                Column(name="sku", type="categorical", distribution_params={"choices": list(PANTRY)}),
                Column(name="period", type="categorical", distribution_params={"choices": PERIODS}),
                _int("opening_stock", 0, 500), _int("received", 0, 500),
                _int("shipped", 0, 500), _int("closing_stock", 0, 500),
            ],
        },
        relationships=[
            Relationship(parent_table="residents", child_table="accounts",
                         parent_key="resident_id", child_key="resident_id"),
            Relationship(parent_table="residents", child_table="visits",
                         parent_key="resident_id", child_key="resident_id", min_children=2),
            Relationship(parent_table="places", child_table="visits",
                         parent_key="place_id", child_key="place_id", partition_by=["kind"]),
            Relationship(parent_table="visits", child_table="orders",
                         parent_key="visit_id", child_key="visit_id",
                         filters={"kind": "cafe"}, parent_time="arrived_at",
                         parent_end="left_at", child_time="ordered_at"),
            Relationship(parent_table="accounts", child_table="payments",
                         parent_key="account_id", child_key="account_id"),
        ],
        outcome_curves=[OutcomeCurve(
            table="payments", column="amount", time_column="paid_on", time_unit="day",
            value_mode="absolute",
            curve_points=[{"date": d, "target_value": v} for d, v in DAYS.items()])],
        group_shares=[GroupShares(table="payments", measure="amount",
                                  group_column="merchant", shares=MERCHANTS)],
        stock_flows=[StockFlowIdentity(table="pantry", periods=PERIODS, opening=PANTRY)],
        time_grids=[
            TimeGrid(table="visits", column="arrived_at", minute_grid=15, hours=(8, 22)),
            TimeGrid(table="visits", column="left_at", minute_grid=15, hours=(8, 23)),
            TimeGrid(table="orders", column="ordered_at", minute_grid=5),
        ],
        no_overlap=[NoOverlap(table="visits", key="resident_id",
                              start="arrived_at", end="left_at")],
        capacity=[Capacity(table="visits", resource="place_id", start="arrived_at",
                           end="left_at", capacity_column="seats")],
    )


def build_assertions() -> List[Tuple[str, str, str]]:
    a: List[Tuple[str, str, str]] = []

    # A -- structural
    for t, k in PK.items():
        a.append(("A", f"{t}.{k} unique",
                  f"SELECT count(*) FROM (SELECT {k} FROM {t} GROUP BY {k} HAVING count(*) > 1)"))
    for c, ck, p, pk in FKS:
        a.append(("A", f"{c}.{ck} -> {p}.{pk} no orphans",
                  f"SELECT count(*) FROM {c} c LEFT JOIN {p} p ON c.{ck} = p.{pk} "
                  f"WHERE c.{ck} IS NOT NULL AND p.{pk} IS NULL"))

    # I -- intervals: one place at a time, never over capacity
    a += [
        ("I", "nobody is in two places at once",
         "SELECT count(*) FROM visits a JOIN visits b ON a.resident_id = b.resident_id "
         "AND a.visit_id < b.visit_id AND a.arrived_at < b.left_at AND b.arrived_at < a.left_at"),
        ("I", "no place seats more people than it has, at any instant",
         "WITH ev AS (SELECT place_id, arrived_at AS t, 1 AS d FROM visits "
         "UNION ALL SELECT place_id, left_at, -1 FROM visits), "
         "occ AS (SELECT place_id, sum(d) OVER (PARTITION BY place_id ORDER BY t, d "
         "ROWS UNBOUNDED PRECEDING) AS o FROM ev) "
         "SELECT count(*) FROM (SELECT place_id, max(o) AS m FROM occ GROUP BY place_id) x "
         "JOIN places p USING (place_id) WHERE x.m > p.seats"),
        ("I", "a visit is to a place of its kind",
         "SELECT count(*) FROM visits v JOIN places p USING (place_id) WHERE v.kind <> p.kind"),
        ("I", "every stay ends after it starts",
         "SELECT count(*) FROM visits WHERE left_at <= arrived_at"),
        ("I", "arrivals sit on the quarter hour",
         "SELECT count(*) FROM visits WHERE minute(arrived_at) % 15 <> 0 "
         "OR second(arrived_at) <> 0"),
        ("I", "departures sit on the quarter hour",
         "SELECT count(*) FROM visits WHERE minute(left_at) % 15 <> 0 OR second(left_at) <> 0"),
        ("I", "nobody arrives before the town opens",
         "SELECT count(*) FROM visits WHERE hour(arrived_at) < 8"),
        ("I", "a stay keeps its town day",
         "SELECT count(*) FROM visits WHERE CAST(left_at AS DATE) <> DATE '2026-11-02'"),
    ]

    # S -- spans: an order belongs to its visit
    a += [
        ("S", "no order before its visitor arrived",
         "SELECT count(*) FROM orders o JOIN visits v USING (visit_id) "
         "WHERE o.ordered_at < v.arrived_at"),
        ("S", "no order after its visitor left",
         "SELECT count(*) FROM orders o JOIN visits v USING (visit_id) "
         "WHERE o.ordered_at > v.left_at"),
        ("S", "orders are only taken at cafés",
         "SELECT count(*) FROM orders o JOIN visits v USING (visit_id) WHERE v.kind <> 'cafe'"),
        ("S", "orders sit on a five-minute clock",
         "SELECT count(*) FROM orders WHERE minute(ordered_at) % 5 <> 0 "
         "OR second(ordered_at) <> 0"),
    ]

    # M -- money: within means, under exact totals
    a += [
        ("M", "no account spends more than it holds",
         "SELECT count(*) FROM (SELECT account_id, sum(amount) AS s FROM payments "
         "GROUP BY account_id) x JOIN accounts a USING (account_id) "
         "WHERE x.s > a.spendable + 0.005"),
        ("M", "payments are whole cents",
         "SELECT count(*) FROM payments WHERE abs(amount * 100 - round(amount * 100)) > 1e-6"),
        ("M", "no negative payment",
         "SELECT count(*) FROM payments WHERE amount < 0"),
    ]
    for day, total in DAYS.items():
        a.append(("M", f"{day} takings are exactly {total:,.2f}",
                  f"SELECT CASE WHEN abs(coalesce(sum(amount), 0) - {total!r}) > 0.005 "
                  f"THEN 1 ELSE 0 END FROM payments WHERE CAST(paid_on AS DATE) = DATE '{day}'"))
        for merchant, share in MERCHANTS.items():
            a.append(("M", f"{merchant} takes {share:.0%} of {day}",
                      f"SELECT CASE WHEN abs(coalesce(sum(amount), 0) - {round(total * share, 2)!r})"
                      f" > 0.015 THEN 1 ELSE 0 END FROM payments "
                      f"WHERE CAST(paid_on AS DATE) = DATE '{day}' AND merchant = '{merchant}'"))

    # K -- the pantry ledger
    first = PERIODS[0]
    a += [
        ("K", "every pantry row balances",
         "SELECT count(*) FROM pantry WHERE opening_stock + received - shipped <> closing_stock"),
        ("K", "each day opens where the last one closed",
         "SELECT count(*) FROM (SELECT opening_stock, lag(closing_stock) OVER "
         "(PARTITION BY sku ORDER BY period) AS prev FROM pantry) WHERE prev IS NOT NULL "
         "AND opening_stock <> prev"),
        ("K", "no shelf goes negative",
         "SELECT count(*) FROM pantry WHERE least(opening_stock, received, shipped, "
         "closing_stock) < 0"),
        ("K", "the pantry holds exactly the declared items",
         f"SELECT count(*) FROM (SELECT DISTINCT sku FROM pantry) WHERE sku NOT IN "
         f"({', '.join(repr(s) for s in PANTRY)})"),
    ]
    for sku, qty in PANTRY.items():
        a.append(("K", f"{sku} opens {first} at {qty}",
                  f"SELECT count(*) FROM (SELECT 1) LEFT JOIN pantry ON sku = '{sku}' "
                  f"AND period = '{first}' WHERE opening_stock IS DISTINCT FROM {qty}"))
    return a


CAT_NAMES = {"A": "structural", "I": "intervals", "S": "spans", "M": "money", "K": "pantry"}


def run(tables) -> List[dict]:
    con = duckdb.connect()
    for name, df in tables.items():
        con.register(name, df)
    results = []
    for cat, name, sql in build_assertions():
        try:
            violations = int(con.execute(sql).fetchone()[0] or 0)
            error = None
        except Exception as e:  # noqa: BLE001 - an assertion that errors is reported, not raised
            violations, error = -1, str(e)[:180]
        results.append({"category": cat, "name": name, "violations": violations,
                        "error": error, "known_red": name in KNOWN_RED})
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_path", default=None)
    args = ap.parse_args()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t0 = time.perf_counter()
        tables = misata.generate_from_schema(build_schema())
        gen_secs = time.perf_counter() - t0

    results = run(tables)
    passed = sum(1 for r in results if r["violations"] == 0)
    total = len(results)
    unexpected = [r for r in results if r["violations"] != 0 and not r["known_red"]]
    promotable = [r for r in results if r["violations"] == 0 and r["known_red"]]

    print(f"\nTHE BOROUGH  --  {len(tables)} tables, "
          f"{sum(len(t) for t in tables.values()):,} rows, {total} assertions, "
          f"generated in {gen_secs:.1f}s\n")
    for cat in CAT_NAMES:
        rs = [r for r in results if r["category"] == cat]
        ok = sum(1 for r in rs if r["violations"] == 0)
        print(f"  {cat}  {CAT_NAMES[cat]:<12} {ok}/{len(rs)}")
        for r in rs:
            if r["violations"] == 0:
                continue
            tag = "KNOWN-RED" if r["known_red"] else "FAIL"
            detail = (f"({r['violations']:,} violating rows)"
                      if r["violations"] >= 0 else f"(ERROR: {r['error']})")
            print(f"       {tag}  {r['name']}  {detail}")
            if r["known_red"]:
                print(f"                 roadmap: {KNOWN_RED[r['name']]}")

    print(f"\n  TOTAL  {passed}/{total} ({100 * passed // total}%)")
    for r in promotable:
        print(f"  PROMOTE: known-red '{r['name']}' now passes — remove it from KNOWN_RED.")
    if args.json_path:
        with open(args.json_path, "w") as f:
            json.dump({"passed": passed, "total": total, "results": results,
                       "known_red": KNOWN_RED, "generation_seconds": gen_secs}, f, indent=2)
    return 1 if (unexpected or promotable) else 0


if __name__ == "__main__":
    raise SystemExit(main())
