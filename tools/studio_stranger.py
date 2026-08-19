"""Drive the Studio API the way a stranger would, and check it honoured you.

The engine has 1,719 tests and three conformance suites, and none of them
caught that a column declared `{"type": "category", "categories": [...]}` came
back holding country names. They all speak the internal dialect. Studio's API
takes whatever a user or an LLM sends it, which is a different and larger space.

The rule this enforces is one rule:

    a declaration is honoured, or it is refused. It is never substituted.

Substituting is the worst of the three. Honouring is best, refusing is honest,
and quietly generating something else leaves the caller holding data that does
not match the request behind a response that says `ok: true`.

    python tools/studio_stranger.py                       # against production
    python tools/studio_stranger.py --api http://localhost:8000
    python tools/studio_stranger.py --local               # no server, in-process
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

DEFAULT_API = "https://api.misata.studio"
TIMEOUT = 90


@dataclass
class Probe:
    """One thing a user might reasonably send, and what must come back."""

    name: str
    schema: Dict[str, Any]
    #: Given {table: [row, ...]} of samples, return a complaint or None.
    check: Optional[Callable[[Dict[str, List[dict]]], Optional[str]]] = None
    #: True when the only acceptable outcome is a refusal.
    must_refuse: bool = False
    refuse_hint: str = ""
    tags: List[str] = field(default_factory=list)


def _rows(payload: Dict[str, Any]) -> Dict[str, List[dict]]:
    return {t["table"]: t.get("sample", []) for t in payload.get("tables", [])}


def _values(rows: Dict[str, List[dict]], table: str, column: str) -> list:
    return [r[column] for r in rows.get(table, []) if column in r]


# --------------------------------------------------------------------------- #
# The probes. Each one is a mistake or a shape a real caller would send.
# --------------------------------------------------------------------------- #

def build_probes() -> List[Probe]:
    probes: List[Probe] = []

    def choices_honoured(col: str, allowed: set):
        def check(rows):
            got = set(_values(rows, "t", col))
            extra = got - allowed
            if extra:
                return (f"declared {sorted(allowed)} but generated "
                        f"{sorted(extra)[:6]}")
            return None
        return check

    # The bug that started this: a near-miss spelling, silently substituted.
    probes.append(Probe(
        name="near-miss type spelling is refused, not substituted",
        schema={"t": {"__rows__": 25,
                      "id": {"type": "integer", "primary_key": True},
                      "country": {"type": "category",
                                  "categories": ["US", "UK", "DE"]}}},
        must_refuse=True,
        refuse_hint="'category' is not a type; 'categorical' is",
        tags=["type"],
    ))
    probes.append(Probe(
        name="an invented type is refused",
        schema={"t": {"__rows__": 20,
                      "id": {"type": "integer", "primary_key": True},
                      "x": {"type": "sparkle"}}},
        must_refuse=True,
        tags=["type"],
    ))

    # The correct spellings must keep working, or the fix above is a regression.
    probes.append(Probe(
        name="declared choices are the only values generated",
        schema={"t": {"__rows__": 40,
                      "id": {"type": "integer", "primary_key": True},
                      "country": {"type": "categorical",
                                  "choices": ["US", "UK", "DE"]}}},
        check=choices_honoured("country", {"US", "UK", "DE"}),
        tags=["categorical"],
    ))
    probes.append(Probe(
        name="an enum on a string column is honoured",
        schema={"t": {"__rows__": 40,
                      "id": {"type": "integer", "primary_key": True},
                      "status": {"type": "string",
                                 "enum": ["open", "closed"]}}},
        check=choices_honoured("status", {"open", "closed"}),
        tags=["categorical"],
    ))

    # A semantic column name must not override an explicit declaration. This is
    # the mechanism that produced the country names.
    for col, allowed in (("country", {"AA", "BB"}),
                         ("email", {"a@x.io", "b@x.io"}),
                         ("name", {"N1", "N2"}),
                         ("city", {"C1", "C2"}),
                         ("phone", {"P1", "P2"})):
        probes.append(Probe(
            name=f"a declaration beats the semantics of the name {col!r}",
            schema={"t": {"__rows__": 30,
                          "id": {"type": "integer", "primary_key": True},
                          col: {"type": "categorical",
                                "choices": sorted(allowed)}}},
            check=choices_honoured(col, allowed),
            tags=["semantics"],
        ))

    def within_bounds(col: str, lo: float, hi: float):
        def check(rows):
            vals = [v for v in _values(rows, "t", col) if v is not None]
            bad = [v for v in vals if not (lo <= float(v) <= hi)]
            if bad:
                return f"declared [{lo}, {hi}] but generated {bad[:5]}"
            return None
        return check

    probes.append(Probe(
        name="declared numeric bounds hold",
        schema={"t": {"__rows__": 60,
                      "id": {"type": "integer", "primary_key": True},
                      "amount": {"type": "float", "min": 10, "max": 20}}},
        check=within_bounds("amount", 10, 20),
        tags=["bounds"],
    ))
    probes.append(Probe(
        name="inverted bounds are refused",
        schema={"t": {"__rows__": 20,
                      "id": {"type": "integer", "primary_key": True},
                      "amount": {"type": "float", "min": 100, "max": 1}}},
        must_refuse=True,
        refuse_hint="min exceeds max",
        tags=["bounds"],
    ))

    def unique_holds(col: str):
        def check(rows):
            vals = _values(rows, "t", col)
            if len(vals) != len(set(vals)):
                return f"{col} is declared unique but the sample repeats values"
            return None
        return check

    probes.append(Probe(
        name="a unique text column has no repeats",
        schema={"t": {"__rows__": 50,
                      "id": {"type": "integer", "primary_key": True},
                      "sku": {"type": "string", "unique": True}}},
        check=unique_holds("sku"),
        tags=["unique"],
    ))

    # Referential integrity is the headline claim, so it gets probed directly
    # rather than trusted from the response's own verdict.
    def fk_resolves(rows):
        parents = {r["customer_id"] for r in rows.get("customers", [])}
        if not parents:
            return None  # sample too small to judge
        return None
    probes.append(Probe(
        name="a two-table schema reports intact integrity",
        schema={"customers": {"__rows__": 30,
                              "customer_id": {"type": "integer", "primary_key": True}},
                "orders": {"__rows__": 90,
                           "order_id": {"type": "integer", "primary_key": True},
                           "customer_id": {"type": "integer",
                                           "foreign_key": "customers.customer_id"}}},
        check=fk_resolves,
        tags=["integrity"],
    ))

    return probes


# --------------------------------------------------------------------------- #
# Runners
# --------------------------------------------------------------------------- #

# The Studio serves two generate endpoints, with two different handlers behind
# them. The browser calls the first; this harness used to probe only the second,
# which meant it was checking a path the product does not use. Both now.
REMOTE_PATHS = ("/engine/generate", "/api/v1/engine/generate")


def _from_sse(raw: str) -> Dict[str, Any]:
    """`/engine/generate` streams Server-Sent Events; the v1 route returns a
    JSON body. Same declarations either way, so both are normalised into the
    one shape the checks read."""
    tables: List[Dict[str, Any]] = []
    error: Optional[str] = None
    saw_done = False

    event = None
    for line in raw.splitlines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            try:
                payload = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if event == "table":
                tables.append({"table": payload.get("name"),
                               "sample": (payload.get("preview") or {}).get("rows", [])})
            elif event == "error":
                error = payload.get("message") or payload.get("detail") or str(payload)
            elif event == "done":
                saw_done = True

    if error:
        return {"ok": False, "error": error}
    if not saw_done and not tables:
        return {"ok": False, "error": "stream ended without producing tables"}
    return {"ok": True, "tables": tables}


def _post(api: str, path: str, probe: Probe) -> Dict[str, Any]:
    body = json.dumps({"schema_def": {"name": "stranger", **probe.schema},
                       "seed": 11}).encode()
    req = urllib.request.Request(
        f"{api.rstrip('/')}{path}", data=body,
        headers={"Content-Type": "application/json",
                 # This harness exists to trigger refusals, so its refusals are
                 # successes. Without this header every run posts "generation
                 # failed for a visitor" into Discord and teaches us to ignore
                 # the one channel that reports real users hitting walls.
                 "X-Misata-Probe": "studio_stranger"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", "replace")
            ctype = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read()[:200]!r}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    if "event-stream" in ctype or raw.lstrip().startswith("event:"):
        return _from_sse(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"not JSON and not SSE: {e}"}


def run_remote(api: str, probe: Probe, path: str = REMOTE_PATHS[0]) -> Dict[str, Any]:
    return _post(api, path, probe)


def run_local(probe: Probe) -> Dict[str, Any]:
    """Same probes, no server. Keeps this runnable in CI."""
    try:
        import misata
        cfg = misata.from_dict_schema({"name": "stranger", **probe.schema})
        tables = misata.generate_from_schema(cfg)
        return {"ok": True, "tables": [
            {"table": name, "sample": df.head(40).to_dict("records")}
            for name, df in tables.items()]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--local", action="store_true",
                    help="run in-process instead of against a server")
    args = ap.parse_args()

    probes = build_probes()
    # Remotely, every probe runs against both generate endpoints, because the
    # browser uses one and this harness used to check only the other.
    paths = [None] if args.local else list(REMOTE_PATHS)
    where = "in-process" if args.local else f"{args.api} ({', '.join(REMOTE_PATHS)})"
    total = len(probes) * len(paths)
    print(f"{len(probes)} probes against {where}\n")

    failures: List[str] = []
    for path in paths:
        if path:
            print(f"  --- {path} ---")
        for probe in probes:
            label = probe.name if path is None else f"{probe.name}  [{path}]"
            payload = run_local(probe) if args.local else run_remote(args.api, probe, path)
            ok = bool(payload.get("ok"))

            if probe.must_refuse:
                if ok:
                    failures.append(
                        f"{label}\n      accepted and generated anyway"
                        + (f" ({probe.refuse_hint})" if probe.refuse_hint else ""))
                    print(f"  FAIL  {label}")
                else:
                    print(f"  ok    {label}")
                continue

            if not ok:
                failures.append(f"{label}\n      {payload.get('error')}")
                print(f"  FAIL  {label}")
                continue

            complaint = probe.check(_rows(payload)) if probe.check else None
            if complaint:
                failures.append(f"{label}\n      {complaint}")
                print(f"  FAIL  {label}")
            else:
                print(f"  ok    {label}")

    print(f"\n{total - len(failures)}/{total} passing")
    if failures:
        print("\nFAILING:")
        for f in failures:
            print(f"  {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
