"""Golden fingerprints: the same schema and seed give the same data.

Each case is generated and fingerprinted with ``misata.fingerprint``; the
result is compared with ``benchmarks/golden_fingerprints.json``, recorded
for this Misata version. CI runs this on Linux, macOS and Windows, so a
pass means identical data on all three, not only on the machine that
recorded it.

    python -m benchmarks.golden            # check
    python -m benchmarks.golden --update   # record (only when output is meant to change)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Callable, Dict

import misata

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden_fingerprints.json"

_DDL = """
CREATE TABLE accounts (id SERIAL PRIMARY KEY, name VARCHAR(80) NOT NULL, created_at TIMESTAMP NOT NULL);
CREATE TABLE users (id SERIAL PRIMARY KEY, account_id INT NOT NULL REFERENCES accounts(id),
  email VARCHAR(200) NOT NULL UNIQUE, role VARCHAR(10) NOT NULL CHECK (role IN ('owner','admin','member')));
CREATE TABLE invoices (id SERIAL PRIMARY KEY, account_id INT NOT NULL REFERENCES accounts(id),
  amount NUMERIC(10,2) NOT NULL CHECK (amount >= 0), issued_on DATE NOT NULL, due_on DATE NOT NULL,
  CHECK (due_on > issued_on));
"""

_DICT = {
    "customers": {"rows": 400, "columns": {
        "customer_id": {"type": "integer", "primary_key": True},
        "first_name": {"type": "string"}, "last_name": {"type": "string"},
        "email": {"type": "email"}, "city": {"type": "string"}, "country": {"type": "string"},
        "signup_date": {"type": "date"}}},
    "products": {"rows": 150, "columns": {
        "product_id": {"type": "integer", "primary_key": True},
        "product_name": {"type": "string"},
        "category": {"type": "string", "choices": ["Electronics", "Home", "Clothing"]},
        "price": {"type": "float", "min": 5, "max": 400}, "description": {"type": "text"}}},
    "orders": {"rows": 1500, "columns": {
        "order_id": {"type": "integer", "primary_key": True},
        "customer_id": {"type": "foreign_key", "foreign_key": {"table": "customers", "column": "customer_id"}},
        "product_id": {"type": "foreign_key", "foreign_key": {"table": "products", "column": "product_id"}},
        "amount": {"type": "float", "min": 1, "max": 900}, "ordered_at": {"type": "datetime"},
        "status": {"type": "string", "choices": ["paid", "refunded", "pending"]}}},
    "reviews": {"rows": 600, "columns": {
        "review_id": {"type": "integer", "primary_key": True},
        "product_id": {"type": "foreign_key", "foreign_key": {"table": "products", "column": "product_id"}},
        "rating": {"type": "integer", "min": 1, "max": 5}, "review_text": {"type": "text"}}},
}


def _quiet(fn: Callable[[], Dict]) -> Dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return fn()


def _dict_case(seed: int):
    return lambda: misata.generate_from_schema(dict(_DICT, __seed__=seed))


def _ddl_case(seed: int):
    def run():
        cfg = misata.from_ddl(_DDL, default_rows=500)
        cfg.seed = seed
        return misata.generate_from_schema(cfg)
    return run


def _story_case(story: str, rows: int, seed: int):
    return lambda: misata.generate(story, rows=rows, seed=seed)


CASES: Dict[str, Callable[[], Dict]] = {
    "dict_ecommerce_seed1": _dict_case(1),
    "dict_ecommerce_seed2": _dict_case(2),
    "ddl_saas_seed7": _ddl_case(7),
    "story_saas_seed3": _story_case("A SaaS company with customers, subscriptions and invoices", 500, 3),
    "story_shop_seed4": _story_case("An online shop with customers, products, orders and reviews", 500, 4),
}


def compute() -> Dict[str, Dict[str, str]]:
    return {name: misata.fingerprint(_quiet(fn)) for name, fn in CASES.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="record the current fingerprints")
    args = ap.parse_args(argv)
    os.environ.setdefault("PYTHONHASHSEED", "0")
    got = compute()
    if args.update:
        GOLDEN.write_text(json.dumps({"misata": misata.__version__, "cases": got}, indent=2) + "\n")
        print(f"recorded {len(got)} cases for misata {misata.__version__}")
        return 0
    want = json.loads(GOLDEN.read_text())
    if want.get("misata") != misata.__version__:
        print(f"golden fingerprints are for misata {want.get('misata')}, this is {misata.__version__}; "
              f"output may change between versions (see STABILITY.md). Re-record with --update.")
        return 1
    bad = 0
    for case, fp in got.items():
        exp = want["cases"].get(case, {})
        diff = [t for t in sorted(set(fp) | set(exp)) if fp.get(t) != exp.get(t)]
        status = "ok" if not diff else "CHANGED: " + ", ".join(diff)
        bad += bool(diff)
        print(f"{case:24s} {fp['__all__']}  {status}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
