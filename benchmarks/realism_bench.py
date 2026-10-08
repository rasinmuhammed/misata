"""Realism benchmark: blind generators against held-out real data.

Misata's default mode never sees real data, so its realism cannot be shown the
usual way (fit to a dataset, then compare to that dataset). This benchmark
asks the question a user actually faces: knowing only the shape of a business
(its tables, its columns, roughly how many rows), how close does each tool
get to what real data of that kind looks like?

Contestants
-----------
- ``misata_story``   blind: one sentence naming the business and its row counts.
- ``misata_schema``  blind: tables, column names and types, no parameters.
- ``faker_script``   blind: the script people write (Faker dates, numpy
                     uniform amounts, uniform foreign keys).
- ``misata_mimic``   fitted on the TRAIN half of the real data (reference).
- ``sdv_copula``     fitted on the TRAIN half (reference; needs ``sdv``).
- ``real_train``     the train half itself: the noise floor every metric is
                     measured against.

Everything is scored against the held-out TEST half. Blind contestants never
see either half; the only facts they get are the row counts and, for the
schema variant, the category labels (not their shares).

Metrics (lower is better unless noted)
--------------------------------------
- ``amount_ks``      KS distance between log(amount / median): the shape of
                     money, independent of its currency and scale.
- ``hour_tvd``       total variation distance between hour-of-day profiles.
- ``weekday_tvd``    the same over days of the week.
- ``customer_gini``  |Gini difference| of orders per customer.
- ``product_gini``   |Gini difference| of orders per product.
- ``category_gap``   |difference in normalised entropy| of the category column
                     (how balanced it is, not which labels it uses).
- ``detect_auc``     ROC AUC of a gradient-boosted classifier telling real
                     from synthetic rows on scale-free features; 0.5 means
                     indistinguishable.
- ``tells``          realism_report score of the synthetic tables (higher is
                     better; the real data's own score calibrates it).

Run::

    python -m benchmarks.realism_bench --cache .bench_cache --out benchmarks/results

The datasets (Olist's public e-commerce sample and the seaborn NYC taxi
sample) are downloaded into the cache on first run.
"""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

import misata
from misata.schema import Column, Relationship, SchemaConfig, Table
from misata.tells import _gini, realism_report

OLIST = "https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/"
TAXIS = "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/taxis.csv"


# ---------------------------------------------------------------------------
# Canonical event frame: one row per order / trip
#   amount (float), ts (datetime), customer (id or NaN), product (id or NaN),
#   category (str)
# ---------------------------------------------------------------------------

@dataclass
class Dataset:
    name: str
    description: str
    events: pd.DataFrame          # canonical frame of the real data
    tables: Dict[str, pd.DataFrame]  # real tables, for the tells calibration
    n_customers: int
    n_products: int
    categories: List[str]
    start: str
    end: str
    story: str
    has_customers: bool
    has_products: bool


def _fetch(url: str, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / url.rsplit("/", 1)[-1]
    if not path.exists():
        print(f"  downloading {path.name}")
        urllib.request.urlretrieve(url, path)
    return path


def load_olist(cache: Path, max_orders: int, seed: int) -> Dataset:
    orders = pd.read_csv(_fetch(OLIST + "olist_orders_dataset.csv", cache),
                         parse_dates=["order_purchase_timestamp"])
    customers = pd.read_csv(_fetch(OLIST + "olist_customers_dataset.csv", cache))
    items = pd.read_csv(_fetch(OLIST + "olist_order_items_dataset.csv", cache))
    pays = pd.read_csv(_fetch(OLIST + "olist_order_payments_dataset.csv", cache))
    # Olist's customer_id is per order; customer_unique_id is the person.
    orders = orders.merge(customers[["customer_id", "customer_unique_id"]], on="customer_id")
    first_item = items.sort_values("order_item_id").drop_duplicates("order_id")
    pay = pays.groupby("order_id").agg(amount=("payment_value", "sum"),
                                       category=("payment_type", "first"))
    ev = (orders.merge(first_item[["order_id", "product_id"]], on="order_id")
          .merge(pay, left_on="order_id", right_index=True))
    ev = ev[ev["amount"] > 0]
    ev = ev.sample(n=min(max_orders, len(ev)), random_state=seed)
    events = pd.DataFrame({
        "amount": ev["amount"].to_numpy(float),
        "ts": ev["order_purchase_timestamp"].to_numpy(),
        "customer": ev["customer_unique_id"].to_numpy(),
        "product": ev["product_id"].to_numpy(),
        "category": ev["category"].astype(str).to_numpy(),
    })
    tables = {
        "customers": pd.DataFrame({"customer_id": events["customer"].unique()}),
        "products": pd.DataFrame({"product_id": events["product"].unique()}),
        "orders": pd.DataFrame({
            "order_id": np.arange(len(events)), "customer_id": events["customer"],
            "product_id": events["product"], "amount": events["amount"],
            "ordered_at": events["ts"], "payment_method": events["category"]}),
    }
    nc, npr = events["customer"].nunique(), events["product"].nunique()
    return Dataset(
        name="olist", description="Olist Brazilian e-commerce, real orders 2016-2018",
        events=events, tables=tables, n_customers=nc, n_products=npr,
        categories=sorted(events["category"].unique()),
        start="2017-01-01", end="2018-08-31",
        story=(f"A Brazilian e-commerce marketplace with {nc} customers, {npr} products "
               f"and {len(events)} orders"),
        has_customers=True, has_products=True)


def load_taxis(cache: Path, max_orders: int, seed: int) -> Dataset:
    t = pd.read_csv(_fetch(TAXIS, cache), parse_dates=["pickup"])
    t = t.dropna(subset=["payment"])
    t = t[t["total"] > 0].sample(n=min(max_orders, len(t)), random_state=seed)
    events = pd.DataFrame({
        "amount": t["total"].to_numpy(float), "ts": t["pickup"].to_numpy(),
        "customer": np.nan, "product": np.nan,
        "category": t["payment"].astype(str).to_numpy(),
    })
    tables = {"trips": pd.DataFrame({
        "trip_id": np.arange(len(events)), "pickup_at": events["ts"],
        "total": events["amount"], "payment": events["category"]})}
    return Dataset(
        name="taxis", description="NYC yellow/green taxi trips, March 2019 (seaborn sample)",
        events=events, tables=tables, n_customers=0, n_products=0,
        categories=sorted(events["category"].unique()),
        start="2019-03-01", end="2019-03-31",
        story=f"A New York taxi company with {len(events)} taxi rides, fares and payment types",
        has_customers=False, has_products=False)


# ---------------------------------------------------------------------------
# Contestants
# ---------------------------------------------------------------------------

def _pick(df: pd.DataFrame, *needles: str, kind: str) -> Optional[str]:
    for col in df.columns:
        low = col.lower()
        s = df[col]
        ok = {
            "num": pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s),
            "time": low.endswith(("_at", "date", "time", "timestamp")) or "date" in low,
            "text": (s.dtype == object or pd.api.types.is_string_dtype(s)
                     or isinstance(s.dtype, pd.CategoricalDtype)),
        }[kind]
        if ok and any(n in low for n in needles):
            return col
    return None


def _events_from_tables(tables: Dict[str, pd.DataFrame], ds: Dataset) -> pd.DataFrame:
    """Map a generated multi-table dataset onto the canonical frame by
    column-name heuristics, the way a person would read it."""
    fact = max(tables.values(), key=len)
    amt = _pick(fact, "amount", "total", "fare", "price", "value", kind="num")
    ts = _pick(fact, "order", "pickup", "created", "date", "time", kind="time")
    cat = _pick(fact, "payment", "method", "type", kind="text")
    cust = next((c for c in fact.columns if c in ("customer_id", "user_id", "buyer_id")), None)
    prod = next((c for c in fact.columns if c in ("product_id", "listing_id", "item_id")), None)
    n = len(fact)
    return pd.DataFrame({
        "amount": fact[amt].to_numpy(float) if amt else np.full(n, np.nan),
        "ts": pd.to_datetime(fact[ts], errors="coerce").to_numpy() if ts else pd.NaT,
        "customer": fact[cust].to_numpy() if cust else np.nan,
        "product": fact[prod].to_numpy() if prod else np.nan,
        "category": fact[cat].astype(str).to_numpy() if cat else "n/a",
    })


def misata_story(ds: Dataset, n: int, seed: int):
    tables = misata.generate(ds.story, seed=seed)
    return _events_from_tables(tables, ds), tables


def _blind_schema(ds: Dataset, n: int, seed: int) -> SchemaConfig:
    """What a user writes without looking at the data: names and types only."""
    if ds.name == "taxis":
        return SchemaConfig(name="taxis", seed=seed, domain="transport",
            tables=[Table(name="trips", row_count=n)],
            columns={"trips": [
                Column(name="trip_id", type="int", unique=True),
                Column(name="pickup_at", type="datetime",
                       distribution_params={"start": ds.start, "end": ds.end}),
                Column(name="total", type="float"),
                Column(name="payment", type="categorical",
                       distribution_params={"choices": ds.categories}),
            ]})
    return SchemaConfig(name="olist", seed=seed, domain="marketplace",
        tables=[Table(name="customers", row_count=ds.n_customers),
                Table(name="products", row_count=ds.n_products),
                Table(name="orders", row_count=n)],
        columns={
            "customers": [Column(name="customer_id", type="int", unique=True)],
            "products": [Column(name="product_id", type="int", unique=True),
                         Column(name="price", type="float")],
            "orders": [
                Column(name="order_id", type="int", unique=True),
                Column(name="customer_id", type="foreign_key"),
                Column(name="product_id", type="foreign_key"),
                Column(name="ordered_at", type="datetime",
                       distribution_params={"start": ds.start, "end": ds.end}),
                Column(name="amount", type="float"),
                Column(name="payment_method", type="categorical",
                       distribution_params={"choices": ds.categories}),
            ]},
        relationships=[
            Relationship(parent_table="customers", child_table="orders",
                         parent_key="customer_id", child_key="customer_id"),
            Relationship(parent_table="products", child_table="orders",
                         parent_key="product_id", child_key="product_id")])


def misata_schema(ds: Dataset, n: int, seed: int):
    tables = misata.generate_from_schema(_blind_schema(ds, n, seed))
    return _events_from_tables(tables, ds), tables


def faker_script(ds: Dataset, n: int, seed: int):
    """The script: Faker for dates, numpy for the rest."""
    from faker import Faker
    fk = Faker()
    Faker.seed(seed)
    rng = np.random.default_rng(seed)
    start, end = pd.Timestamp(ds.start), pd.Timestamp(ds.end)
    ts = [fk.date_time_between(start_date=start, end_date=end) for _ in range(n)]
    ev = pd.DataFrame({
        "amount": rng.uniform(5, 500, n).round(2),
        "ts": pd.to_datetime(ts),
        "customer": rng.integers(0, ds.n_customers, n) if ds.has_customers else np.nan,
        "product": rng.integers(0, ds.n_products, n) if ds.has_products else np.nan,
        "category": rng.choice(ds.categories, n),
    })
    tables = {"events": ev.assign(event_id=np.arange(n), email=[fk.email() for _ in range(n)])}
    return ev, tables


def _flat(events: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"amount": events["amount"], "ts": pd.to_datetime(events["ts"]),
                         "category": events["category"]})


def misata_mimic(ds: Dataset, n: int, seed: int, train: pd.DataFrame):
    out = misata.mimic(_flat(train), rows=n, seed=seed)
    syn = next(iter(out.values())) if isinstance(out, dict) else out
    ev = pd.DataFrame({"amount": syn["amount"].to_numpy(float),
                       "ts": pd.to_datetime(syn["ts"], errors="coerce").to_numpy(),
                       "customer": np.nan, "product": np.nan,
                       "category": syn["category"].astype(str).to_numpy()})
    return ev, {"mimic": syn}


def sdv_copula(ds: Dataset, n: int, seed: int, train: pd.DataFrame):
    from sdv.metadata import Metadata
    from sdv.single_table import GaussianCopulaSynthesizer
    flat = _flat(train)
    md = Metadata.detect_from_dataframe(flat)
    synth = GaussianCopulaSynthesizer(md)
    synth.fit(flat)
    syn = synth.sample(num_rows=n)
    ev = pd.DataFrame({"amount": syn["amount"].to_numpy(float),
                       "ts": pd.to_datetime(syn["ts"]).to_numpy(),
                       "customer": np.nan, "product": np.nan,
                       "category": syn["category"].astype(str).to_numpy()})
    return ev, {"sdv": syn}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _log_rel(x: pd.Series) -> np.ndarray:
    x = pd.to_numeric(x, errors="coerce").dropna().to_numpy(float)
    x = x[x > 0]
    return np.log(x / np.median(x)) if len(x) else x


def _profile(ts: pd.Series, attr: str, bins: int) -> Optional[np.ndarray]:
    t = pd.to_datetime(ts, errors="coerce").dropna()
    if t.empty:
        return None
    if attr == "hour" and ((t.dt.hour == 0) & (t.dt.minute == 0) & (t.dt.second == 0)).all():
        return None  # dates only: no time of day to compare
    v = getattr(t.dt, attr).to_numpy()
    h = np.bincount(v, minlength=bins).astype(float)
    return h / h.sum()


def _fanout_gini(ids: pd.Series) -> Optional[float]:
    ids = pd.Series(ids).dropna()
    if ids.empty:
        return None
    return _gini(ids.value_counts().to_numpy())


def _norm_entropy(cat: pd.Series) -> Optional[float]:
    p = pd.Series(cat).value_counts(normalize=True).to_numpy()
    if len(p) < 2:
        return None
    return float(-(p * np.log(p)).sum() / math.log(len(p)))


def _detect_auc(real: pd.DataFrame, syn: pd.DataFrame, seed: int) -> Optional[float]:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import cross_val_score

    def feats(ev: pd.DataFrame) -> pd.DataFrame:
        t = pd.to_datetime(ev["ts"], errors="coerce")
        amt = pd.to_numeric(ev["amount"], errors="coerce")
        out = pd.DataFrame({
            # Scale-free, and on a 10% log grid: amounts are often discrete
            # (fares like 14.16), and dividing by each sample's own median
            # shifts every value by a tiny constant when two medians differ by
            # a cent. Unrounded, that shift alone let the classifier tell two
            # halves of the same real data apart (AUC 0.89 on some seeds).
            "log_rel_amount": np.round(np.log(amt.clip(lower=1e-9) / amt[amt > 0].median()), 1),
            "hour": t.dt.hour + t.dt.minute / 60.0,
            "weekday": t.dt.dayofweek,
        })
        return out

    a, b = feats(real), feats(syn)
    m = min(len(a), len(b), 20_000)
    a = a.sample(m, random_state=seed)
    b = b.sample(m, random_state=seed)
    X = pd.concat([a, b], ignore_index=True)
    y = np.r_[np.zeros(m), np.ones(m)]
    keep = X.notna().all(axis=0)
    X = X.loc[:, keep]
    if X.empty:
        return None
    X = X.fillna(-1)
    clf = HistGradientBoostingClassifier(max_iter=150, random_state=seed)
    return float(cross_val_score(clf, X, y, cv=5, scoring="roc_auc").mean())


def score(test: pd.DataFrame, syn: pd.DataFrame, seed: int) -> Dict[str, Optional[float]]:
    from scipy.stats import ks_2samp
    out: Dict[str, Optional[float]] = {}
    ra, sa = _log_rel(test["amount"]), _log_rel(syn["amount"])
    out["amount_ks"] = float(ks_2samp(ra, sa).statistic) if len(sa) > 10 else None
    for attr, bins, key in (("hour", 24, "hour_tvd"), ("dayofweek", 7, "weekday_tvd")):
        pr, ps = _profile(test["ts"], attr, bins), _profile(syn["ts"], attr, bins)
        out[key] = float(0.5 * np.abs(pr - ps).sum()) if pr is not None and ps is not None else None
    for col, key in (("customer", "customer_gini"), ("product", "product_gini")):
        gr, gs = _fanout_gini(test[col]), _fanout_gini(syn[col])
        out[key] = abs(gr - gs) if gr is not None and gs is not None else None
    er, es = _norm_entropy(test["category"]), _norm_entropy(syn["category"])
    out["category_gap"] = abs(er - es) if er is not None and es is not None else None
    out["detect_auc"] = _detect_auc(test, syn, seed)
    return out


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

BLIND: Dict[str, Callable] = {
    "misata_story": misata_story, "misata_schema": misata_schema, "faker_script": faker_script,
}
FITTED: Dict[str, Callable] = {"misata_mimic": misata_mimic, "sdv_copula": sdv_copula}


def run(cache: Path, max_orders: int = 30_000, seed: int = 7) -> Dict:
    results: Dict = {"seed": seed, "misata_version": misata.__version__, "datasets": {}}
    for loader in (load_olist, load_taxis):
        ds = loader(cache, max_orders, seed)
        ev = ds.events.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        half = len(ev) // 2
        train, test = ev.iloc[:half].reset_index(drop=True), ev.iloc[half:].reset_index(drop=True)
        # Fan-out is a whole-dataset property: halving rows halves every
        # count. Compare it at full size; everything else on the test half.
        n = len(test)
        print(f"{ds.name}: {len(ev)} real rows, scoring on {n} held out")
        real_tells = realism_report(ds.tables).score
        rows: Dict[str, Dict] = {"real_train": {**score(test, train, seed), "tells": real_tells}}
        for cid, fn in {**BLIND, **FITTED}.items():
            t0 = time.time()
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    if cid in FITTED:
                        syn, tables = fn(ds, n, seed, train)
                    else:
                        full_n = len(ev)
                        syn, tables = fn(ds, full_n, seed)
                full = cid in BLIND
                m = score(ev if full else test, syn, seed)
                if not full:
                    m["customer_gini"] = m["product_gini"] = None
                m["tells"] = realism_report(tables).score
                m["seconds"] = round(time.time() - t0, 1)
            except ImportError as e:
                m = {"skipped": str(e)}
            rows[cid] = m
            print(f"  {cid:<14} {json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()})}")
        results["datasets"][ds.name] = {"description": ds.description, "rows": len(ev),
                                        "story": ds.story, "results": rows}
    return results


METRICS = [("amount_ks", "Amount shape (KS)"), ("hour_tvd", "Hour profile (TVD)"),
           ("weekday_tvd", "Weekday profile (TVD)"), ("customer_gini", "Customer fan-out (ΔGini)"),
           ("product_gini", "Product fan-out (ΔGini)"), ("category_gap", "Category balance (Δ)"),
           ("detect_auc", "Detection AUC"), ("tells", "Tells score ↑")]


def to_markdown(results: Dict) -> str:
    lines = [f"Misata {results['misata_version']}, seed {results['seed']}.", ""]
    for name, block in results["datasets"].items():
        lines += [f"### {name}: {block['description']} ({block['rows']:,} rows)", "",
                  f"Story given to `misata_story`: *\"{block['story']}\"*", ""]
        cols = list(block["results"])
        lines.append("| Metric | " + " | ".join(f"`{c}`" for c in cols) + " |")
        lines.append("|---|" + "---|" * len(cols))
        for key, label in METRICS:
            cells = []
            for c in cols:
                v = block["results"][c].get(key)
                cells.append("n/a" if v is None else f"{v:.3f}")
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache", default=".bench_cache")
    ap.add_argument("--out", default="benchmarks/results")
    ap.add_argument("--max-orders", type=int, default=30_000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    res = run(Path(args.cache), args.max_orders, args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "realism_benchmark.json").write_text(json.dumps(res, indent=2, default=str))
    (out / "realism_benchmark.md").write_text(to_markdown(res))
    print(f"\nwrote {out / 'realism_benchmark.md'}")


if __name__ == "__main__":
    main()
