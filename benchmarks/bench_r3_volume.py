"""Gate R3 (studio realism program): a million rows across fourteen related tables, timed, with every foreign key checked.

    python benchmarks/bench_r3_volume.py [--scale 1.0] [--seed 7]
    python benchmarks/bench_r3_volume.py --scale 10 --stream /tmp/r3   # 10M rows to Parquet

Keys are named after their table (order_id, not id), and order lines must cover every order, because those were the two
paths that broke past one batch and past the context cap (tests/test_order_items_at_scale.py). The time is
generate_from_schema end to end; the checks run after the clock stops.

With --stream, the tables are generated batch by batch into Parquet files (the path `misata generate --format
parquet` takes), peak memory is recorded, and the same checks run as DuckDB SQL over the files, so the checker
shares no code with the generator.
"""
from __future__ import annotations

import argparse
import resource
import sys
import time
from pathlib import Path

import misata
from misata.schema import Column, Relationship, SchemaConfig, Table

ROWS = {  # 1,000,000 in all
    "regions": 12, "stores": 240, "employees": 4_800, "suppliers": 600, "categories": 48, "products": 12_000,
    "customers": 105_000, "promotions": 300, "orders": 150_000, "order_items": 375_000, "payments": 150_000,
    "shipments": 140_000, "returns": 12_000, "reviews": 50_000,
}
PARENTS = {  # child: [(parent, key, unique on the child)]
    "stores": [("regions", "region_id", False)],
    "employees": [("stores", "store_id", False)],
    "products": [("suppliers", "supplier_id", False), ("categories", "category_id", False)],
    "orders": [("customers", "customer_id", False), ("stores", "store_id", False), ("promotions", "promotion_id", False)],
    "order_items": [("orders", "order_id", False), ("products", "product_id", False)],
    "payments": [("orders", "order_id", True)],
    "shipments": [("orders", "order_id", True)],
    "returns": [("order_items", "order_item_id", True)],
    "reviews": [("customers", "customer_id", False), ("products", "product_id", False)],
}
PK = {t: t[:-1] + "_id" if t != "categories" else "category_id" for t in ROWS}
PK.update({"order_items": "order_item_id", "returns": "return_id", "reviews": "review_id", "shipments": "shipment_id"})


def schema(scale: float = 1.0, seed: int = 7) -> SchemaConfig:
    n = {t: max(1, int(r * scale)) for t, r in ROWS.items()}
    n["payments"] = n["orders"]  # one payment per order, a unique key
    cols: dict[str, list[Column]] = {}
    for t, rows in n.items():
        cols[t] = [Column(name=PK[t], type="int", unique=True, distribution_params={"min": 1, "max": rows + 1})]
        cols[t] += [Column(name=key, type="foreign_key", unique=uniq) for _p, key, uniq in PARENTS.get(t, [])]
    cols["regions"].append(Column(name="name", type="text", distribution_params={"text_type": "city"}))
    cols["stores"].append(Column(name="opened", type="date", distribution_params={"start": "2015-01-01", "end": "2023-12-31"}))
    cols["employees"] += [Column(name="name", type="text", distribution_params={"text_type": "name"}),
                          Column(name="hourly_rate", type="float", distribution_params={"distribution": "lognormal", "mu": 2.9, "sigma": 0.25, "min": 12, "max": 60, "decimals": 2})]
    cols["suppliers"].append(Column(name="company", type="text", distribution_params={"text_type": "company"}))
    cols["categories"].append(Column(name="name", type="categorical", distribution_params={"choices": ["grocery", "home", "garden", "toys", "apparel", "electronics"]}))
    cols["products"] += [Column(name="name", type="text", distribution_params={"text_type": "product_name"}),
                         Column(name="price", type="float", distribution_params={"distribution": "lognormal", "mu": 3.0, "sigma": 0.9, "min": 0.5, "max": 900, "decimals": 2})]
    cols["customers"] += [Column(name="email", type="text", unique=True, distribution_params={"text_type": "email"}),
                          Column(name="signup_date", type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"})]
    cols["promotions"].append(Column(name="discount_pct", type="categorical", distribution_params={"choices": [0, 5, 10, 15, 20, 25], "probabilities": [0.4, 0.2, 0.2, 0.1, 0.06, 0.04]}))
    cols["orders"] += [Column(name="order_date", type="date", distribution_params={"start": "2023-01-01", "end": "2024-12-31"}),
                       Column(name="amount", type="float", distribution_params={"rollup": {"from_table": "order_items", "fk": "order_id", "agg": "sum", "column": "line_total"}})]
    cols["order_items"] += [Column(name="quantity", type="int", distribution_params={"distribution": "lognormal", "mu": 0.2, "sigma": 0.5, "min": 1, "max": 10, "decimals": 0}),
                            Column(name="unit_price", type="float", distribution_params={"formula": "@products.price"}),
                            Column(name="line_total", type="float", distribution_params={"formula": "quantity * unit_price"})]
    cols["payments"].append(Column(name="method", type="categorical", distribution_params={"choices": ["card", "cash", "wallet"], "probabilities": [0.6, 0.25, 0.15]}))
    cols["shipments"].append(Column(name="carrier", type="categorical", distribution_params={"choices": ["DHL", "UPS", "FedEx", "Royal Mail"]}))
    cols["returns"].append(Column(name="reason", type="categorical", distribution_params={"choices": ["damaged", "wrong size", "not as described", "changed mind"]}))
    cols["reviews"].append(Column(name="stars", type="int", distribution_params={"distribution": "beta", "a": 5.0, "b": 1.6, "min": 1, "max": 5, "decimals": 0}))
    rels = [Relationship(parent_table=p, child_table=c, parent_key=PK[p], child_key=key, min_children=1 if (p, c) == ("orders", "order_items") else 0)
            for c, ps in PARENTS.items() for p, key, _u in ps]
    return SchemaConfig(name="R3 retail", tables=[Table(name=t, row_count=r) for t, r in n.items()], columns=cols,
                        relationships=rels, seed=seed)


def check(sc: SchemaConfig, tables: dict) -> dict:
    """Tables present and full, every foreign key resolving, every order with a line, order totals equal to their lines."""
    missing = [t.name for t in sc.tables if t.name not in tables or len(tables[t.name]) != t.row_count]
    bad = {f"{r.child_table}.{r.child_key}": float((~tables[r.child_table][r.child_key].isin(tables[r.parent_table][r.parent_key])).mean())
           for r in sc.relationships if not tables[r.child_table][r.child_key].isin(tables[r.parent_table][r.parent_key]).all()}
    o, oi = tables["orders"], tables["order_items"]
    sums = oi.groupby("order_id").line_total.sum()
    return {"tables": len(tables), "rows": sum(len(v) for v in tables.values()), "short_or_missing": missing, "fk_failures": bad,
            "orders_without_lines": float((~o.order_id.isin(oi.order_id)).mean()),
            "totals_match": float(((o.set_index("order_id").amount.reindex(sums.index) - sums).abs() < 0.05).mean())}


def stream(sc: SchemaConfig, out: Path) -> dict:
    """Generate into Parquet batch by batch; return seconds and peak resident memory."""
    from misata.simulator import DataSimulator
    from misata.sinks import open_sink

    t0 = time.perf_counter()
    with open_sink("parquet", out, sc) as sink:
        for table, batch in DataSimulator(sc).generate_all(bounded_memory=True):
            sink.write(table, batch)
    secs = time.perf_counter() - t0
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mb = peak / 1e6 if sys.platform == "darwin" else peak / 1e3  # bytes on macOS, KiB on Linux
    return {"seconds": round(secs, 1), "peak_rss_mb": round(peak_mb)}


def check_files(sc: SchemaConfig, out: Path) -> dict:
    """The checks of `check`, as DuckDB SQL over the written Parquet files."""
    import duckdb

    con = duckdb.connect()
    for t in sc.tables:
        con.execute(f'CREATE VIEW "{t.name}" AS SELECT * FROM read_parquet(\'{out / (t.name + ".parquet")}\')')
    count = {t.name: con.execute(f'SELECT COUNT(*) FROM "{t.name}"').fetchone()[0] for t in sc.tables}
    missing = [t.name for t in sc.tables if count[t.name] != t.row_count]
    bad = {}
    for r in sc.relationships:
        orphans = con.execute(
            f'SELECT COUNT(*) FROM "{r.child_table}" c LEFT JOIN "{r.parent_table}" p '
            f'ON c."{r.child_key}" = p."{r.parent_key}" WHERE p."{r.parent_key}" IS NULL').fetchone()[0]
        if orphans:
            bad[f"{r.child_table}.{r.child_key}"] = orphans / count[r.child_table]
    lineless = con.execute('SELECT AVG(CASE WHEN l.order_id IS NULL THEN 1.0 ELSE 0 END) FROM orders o '
                           'LEFT JOIN (SELECT DISTINCT order_id FROM order_items) l USING (order_id)').fetchone()[0]
    totals = con.execute('SELECT AVG(CASE WHEN ABS(o.amount - s.total) < 0.05 THEN 1.0 ELSE 0 END) FROM orders o '
                         'JOIN (SELECT order_id, SUM(line_total) AS total FROM order_items GROUP BY 1) s '
                         'USING (order_id)').fetchone()[0]
    return {"tables": len(count), "rows": sum(count.values()), "short_or_missing": missing, "fk_failures": bad,
            "orders_without_lines": float(lineless), "totals_match": float(totals)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--stream", type=Path, default=None,
                    help="generate into Parquet files in this folder and check them with DuckDB")
    args = ap.parse_args()
    sc = schema(args.scale, args.seed)
    if args.stream is not None:
        print({**stream(sc, args.stream), **check_files(sc, args.stream)})
        raise SystemExit(0)
    t0 = time.perf_counter()
    out = misata.generate_from_schema(sc)
    secs = time.perf_counter() - t0
    tables = out if isinstance(out, dict) else out.tables
    print({"seconds": round(secs, 1), **check(sc, tables)})
