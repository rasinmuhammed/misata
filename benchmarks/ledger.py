"""The Ledger: a third conformance suite, bitemporal and graph-shaped.

The Gauntlet is a flat e-commerce star. The Warren is multi-tenant, hierarchical
and event-sourced. Both are green, which means both have stopped being able to
find anything, and the rule established when the Warren was built says the next
move is a new shape rather than more assertions on an old one.

This one is awkward in two further ways:

  * **Bitemporal.** A fact has two independent time axes: when it was true of the
    world (`valid_from`/`valid_to`) and when the system was told
    (`recorded_at`/`superseded_at`). Corrections arrive late and rewrite history
    without destroying it. `scd2` handles one axis; nothing handled two, and
    "as of last Tuesday, what did we think the position was?" is the query the
    whole shape exists to answer.
  * **Graph-shaped.** Dependencies are a separate edge table rather than a
    self-referential column: a many-to-many DAG plus its transitive closure. The
    forest logic added in 0.9.2 keeps a *column* acyclic; it says nothing about a
    join table, and a closure table that disagrees with its own edges is a class
    of bug no row-level check finds.

Written assertions-first. A red here names something the language cannot say.

Run:
    python -m benchmarks.ledger
    python -m benchmarks.ledger --json out.json
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from typing import Any, Dict, List, Tuple

import duckdb

import misata
from misata.schema import (SchemaConfig, Table, Column, Relationship,
                           Constraint, Bitemporal, DagEdges, TransitiveClosure,
                           Typos)

SEED = 23

KNOWN_RED: Dict[str, str] = {}


def build_schema() -> SchemaConfig:
    return SchemaConfig(
        name="ledger",
        seed=SEED,
        tables=[
            Table(name="parties", row_count=40),
            Table(name="instruments", row_count=25),
            Table(name="positions", row_count=1800),
            Table(name="tasks", row_count=160),
            Table(name="dependencies", row_count=420),
            Table(name="closure", row_count=1400),
        ],
        columns={
            "parties": [
                Column(name="party_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 40}),
                Column(name="party_name", type="text",
                       distribution_params={"pattern": "P-[A-Z]{4}"}),
                Column(name="onboarded_at", type="datetime",
                       distribution_params={"start": "2021-01-01",
                                            "end": "2021-12-31"}),
            ],
            "instruments": [
                Column(name="instrument_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 25}),
                Column(name="symbol", type="text",
                       distribution_params={"pattern": "[A-Z]{4}"}),
                Column(name="listed_on", type="datetime",
                       distribution_params={"start": "2020-01-01",
                                            "end": "2021-06-30"}),
            ],
            "positions": [
                Column(name="position_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 1800}),
                Column(name="party_id", type="foreign_key",
                       distribution_params={"references": "parties.party_id"}),
                Column(name="instrument_id", type="foreign_key",
                       distribution_params={
                           "references": "instruments.instrument_id"}),
                Column(name="valid_from", type="datetime",
                       distribution_params={"start": "2022-01-01",
                                            "end": "2024-12-31"}),
                Column(name="valid_to", type="datetime", nullable=True,
                       distribution_params={"start": "2022-01-01",
                                            "end": "2025-12-31"}),
                Column(name="recorded_at", type="datetime",
                       distribution_params={"start": "2022-01-01",
                                            "end": "2025-06-30"}),
                Column(name="superseded_at", type="datetime", nullable=True,
                       distribution_params={"start": "2022-01-01",
                                            "end": "2025-12-31"}),
                Column(name="quantity", type="float",
                       distribution_params={"distribution": "uniform",
                                            "min": 1.0, "max": 5000.0}),
            ],
            "tasks": [
                Column(name="task_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 160}),
                Column(name="party_id", type="foreign_key",
                       distribution_params={"references": "parties.party_id"}),
                Column(name="label", type="text",
                       distribution_params={"pattern": "T-[0-9]{4}"}),
            ],
            "dependencies": [
                Column(name="edge_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 420}),
                Column(name="from_task_id", type="foreign_key",
                       distribution_params={"references": "tasks.task_id"}),
                Column(name="to_task_id", type="foreign_key",
                       distribution_params={"references": "tasks.task_id"}),
            ],
            "closure": [
                Column(name="closure_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 1400}),
                Column(name="ancestor_id", type="foreign_key",
                       distribution_params={"references": "tasks.task_id"}),
                Column(name="descendant_id", type="foreign_key",
                       distribution_params={"references": "tasks.task_id"}),
                Column(name="depth", type="int",
                       distribution_params={"min": 1, "max": 6}),
            ],
        },
        relationships=[
            Relationship(parent_table="parties", child_table="positions",
                         parent_key="party_id", child_key="party_id"),
            Relationship(parent_table="instruments", child_table="positions",
                         parent_key="instrument_id", child_key="instrument_id"),
            Relationship(parent_table="parties", child_table="tasks",
                         parent_key="party_id", child_key="party_id"),
            Relationship(parent_table="tasks", child_table="dependencies",
                         parent_key="task_id", child_key="from_task_id"),
            Relationship(parent_table="tasks", child_table="dependencies",
                         parent_key="task_id", child_key="to_task_id"),
            Relationship(parent_table="tasks", child_table="closure",
                         parent_key="task_id", child_key="ancestor_id"),
            Relationship(parent_table="tasks", child_table="closure",
                         parent_key="task_id", child_key="descendant_id"),
        ],
        bitemporal=[
            Bitemporal(
                name="position_history", table="positions",
                entity_columns=["party_id", "instrument_id"],
                valid_from="valid_from", valid_to="valid_to",
                recorded_at="recorded_at", superseded_at="superseded_at",
                avg_versions=3.0,
            ),
        ],
        # Typos in a PATTERNED column: legality is described rather than
        # enumerated, and the pattern doubles as the checker.
        typos=[Typos(table="instruments", column="symbol", count=4)],
        dag_edges=[
            DagEdges(name="task_dag", table="dependencies",
                     node_table="tasks", node_key="task_id",
                     from_column="from_task_id", to_column="to_task_id"),
        ],
        closures=[
            TransitiveClosure(
                name="task_closure", table="closure", edge_table="dependencies",
                edge_from="from_task_id", edge_to="to_task_id",
                ancestor_column="ancestor_id", descendant_column="descendant_id",
                depth_column="depth",
            ),
        ],
    )


PK = {"parties": "party_id", "instruments": "instrument_id",
      "positions": "position_id", "tasks": "task_id",
      "dependencies": "edge_id", "closure": "closure_id"}

FKS = [
    ("positions", "party_id", "parties", "party_id"),
    ("positions", "instrument_id", "instruments", "instrument_id"),
    ("tasks", "party_id", "parties", "party_id"),
    ("dependencies", "from_task_id", "tasks", "task_id"),
    ("dependencies", "to_task_id", "tasks", "task_id"),
    ("closure", "ancestor_id", "tasks", "task_id"),
    ("closure", "descendant_id", "tasks", "task_id"),
]


def build_assertions() -> List[Tuple[str, str, str]]:
    a: List[Tuple[str, str, str]] = []

    # A -- structural
    for t, k in PK.items():
        a.append(("A", f"{t}.{k} unique",
                  f"SELECT count(*) FROM (SELECT {k} FROM {t} GROUP BY {k} "
                  f"HAVING count(*) > 1)"))
        a.append(("A", f"{t}.{k} not null",
                  f"SELECT count(*) FROM {t} WHERE {k} IS NULL"))
    for c, ck, p, pk in FKS:
        a.append(("A", f"{c}.{ck} -> {p}.{pk} no orphans",
                  f"SELECT count(*) FROM {c} c LEFT JOIN {p} p ON c.{ck} = p.{pk} "
                  f"WHERE c.{ck} IS NOT NULL AND p.{pk} IS NULL"))

    # V -- bitemporal: two independent axes on the same row
    a += [
        ("V", "valid_to always follows valid_from",
         "SELECT count(*) FROM positions WHERE valid_to IS NOT NULL "
         "AND valid_to <= valid_from"),
        ("V", "superseded_at always follows recorded_at",
         "SELECT count(*) FROM positions WHERE superseded_at IS NOT NULL "
         "AND superseded_at <= recorded_at"),
        ("V", "exactly one current version per entity",
         "SELECT count(*) FROM (SELECT party_id, instrument_id, "
         "count(*) FILTER (WHERE superseded_at IS NULL) n "
         "FROM positions GROUP BY 1,2 HAVING n <> 1)"),
        ("V", "current versions leave valid time open",
         "SELECT count(*) FROM positions "
         "WHERE superseded_at IS NULL AND valid_to IS NOT NULL"),
        ("V", "no two current versions of an entity overlap in valid time",
         "SELECT count(*) FROM positions a JOIN positions b "
         "ON a.party_id = b.party_id AND a.instrument_id = b.instrument_id "
         "AND a.position_id < b.position_id "
         "WHERE a.superseded_at IS NULL AND b.superseded_at IS NULL"),
        ("V", "a superseded version was recorded before its successor",
         "SELECT count(*) FROM positions a JOIN positions b "
         "ON a.party_id = b.party_id AND a.instrument_id = b.instrument_id "
         "WHERE a.superseded_at IS NOT NULL AND b.recorded_at = a.superseded_at "
         "AND b.recorded_at < a.recorded_at"),
        ("V", "system time tiles: every supersede hands over to a successor",
         "SELECT count(*) FROM positions a WHERE a.superseded_at IS NOT NULL "
         "AND NOT EXISTS (SELECT 1 FROM positions b "
         "WHERE b.party_id = a.party_id AND b.instrument_id = a.instrument_id "
         "AND b.recorded_at = a.superseded_at)"),
        ("V", "nothing was recorded before the party existed",
         "SELECT count(*) FROM positions p JOIN parties t USING (party_id) "
         "WHERE p.recorded_at < t.onboarded_at"),
        ("V", "nothing is valid before the instrument was listed",
         "SELECT count(*) FROM positions p JOIN instruments i USING (instrument_id) "
         "WHERE p.valid_from < i.listed_on"),
        ("V", "every entity has at least one version",
         "SELECT CASE WHEN (SELECT count(DISTINCT (party_id, instrument_id)) "
         "FROM positions) > 0 THEN 0 ELSE 1 END"),
        ("V", "corrections exist (the second axis is exercised)",
         "SELECT CASE WHEN (SELECT count(*) FROM positions "
         "WHERE superseded_at IS NOT NULL) > 0 THEN 0 ELSE 1 END"),
        ("V", "as-of query returns exactly one row per entity",
         "SELECT count(*) FROM (SELECT party_id, instrument_id, count(*) n "
         "FROM positions WHERE recorded_at <= TIMESTAMP '2024-06-01' "
         "AND (superseded_at IS NULL OR superseded_at > TIMESTAMP '2024-06-01') "
         "GROUP BY 1,2 HAVING n <> 1)"),
    ]

    # G -- the DAG and its closure
    a += [
        ("G", "no task depends on itself",
         "SELECT count(*) FROM dependencies WHERE from_task_id = to_task_id"),
        ("G", "no two tasks depend on each other",
         "SELECT count(*) FROM dependencies a JOIN dependencies b "
         "ON a.from_task_id = b.to_task_id AND a.to_task_id = b.from_task_id"),
        ("G", "no cycle within four hops",
         "SELECT count(*) FROM dependencies a "
         "JOIN dependencies b ON a.to_task_id = b.from_task_id "
         "JOIN dependencies c ON b.to_task_id = c.from_task_id "
         "JOIN dependencies d ON c.to_task_id = d.from_task_id "
         "WHERE d.to_task_id = a.from_task_id"),
        ("G", "edges are distinct pairs",
         "SELECT count(*) FROM (SELECT from_task_id, to_task_id "
         "FROM dependencies GROUP BY 1,2 HAVING count(*) > 1)"),
        ("G", "the graph is not degenerate (many tasks have dependents)",
         "SELECT CASE WHEN (SELECT count(DISTINCT from_task_id) "
         "FROM dependencies) > 20 THEN 0 ELSE 1 END"),
        ("G", "closure contains every direct edge at depth 1",
         "SELECT count(*) FROM dependencies d WHERE NOT EXISTS "
         "(SELECT 1 FROM closure c WHERE c.ancestor_id = d.from_task_id "
         "AND c.descendant_id = d.to_task_id AND c.depth = 1)"),
        ("G", "closure contains no pair that is not reachable",
         "WITH RECURSIVE reach(a, d) AS ("
         "  SELECT from_task_id, to_task_id FROM dependencies"
         "  UNION"
         "  SELECT r.a, e.to_task_id FROM reach r "
         "  JOIN dependencies e ON r.d = e.from_task_id) "
         "SELECT count(*) FROM closure c WHERE NOT EXISTS "
         "(SELECT 1 FROM reach r WHERE r.a = c.ancestor_id "
         "AND r.d = c.descendant_id)"),
        ("G", "closure contains every reachable pair",
         "WITH RECURSIVE reach(a, d) AS ("
         "  SELECT from_task_id, to_task_id FROM dependencies"
         "  UNION"
         "  SELECT r.a, e.to_task_id FROM reach r "
         "  JOIN dependencies e ON r.d = e.from_task_id) "
         "SELECT count(*) FROM reach r WHERE NOT EXISTS "
         "(SELECT 1 FROM closure c WHERE c.ancestor_id = r.a "
         "AND c.descendant_id = r.d)"),
        ("G", "closure depth is the true shortest path",
         "WITH RECURSIVE reach(a, d, k) AS ("
         "  SELECT from_task_id, to_task_id, 1 FROM dependencies"
         "  UNION ALL"
         "  SELECT r.a, e.to_task_id, r.k + 1 FROM reach r "
         "  JOIN dependencies e ON r.d = e.from_task_id WHERE r.k < 8) "
         "SELECT count(*) FROM closure c JOIN "
         "(SELECT a, d, min(k) mk FROM reach GROUP BY 1,2) t "
         "ON t.a = c.ancestor_id AND t.d = c.descendant_id "
         "WHERE c.depth <> t.mk"),
        ("G", "no row is its own ancestor in the closure",
         "SELECT count(*) FROM closure WHERE ancestor_id = descendant_id"),
        ("G", "closure rows are distinct pairs",
         "SELECT count(*) FROM (SELECT ancestor_id, descendant_id "
         "FROM closure GROUP BY 1,2 HAVING count(*) > 1)"),
        ("G", "closure reaches beyond one hop (it is a real closure)",
         "SELECT CASE WHEN (SELECT count(*) FROM closure WHERE depth > 1) > 0 "
         "THEN 0 ELSE 1 END"),
    ]

    # B -- domain
    a += [
        ("B", "positions.quantity is positive",
         "SELECT count(*) FROM positions WHERE quantity <= 0"),
        # 4 symbols are declared typos, so what must hold is the exact count,
        # not universal cleanliness.
        ("B", "exactly 4 symbols are typos, as declared",
         "SELECT CASE WHEN (SELECT count(*) FROM instruments "
         "WHERE symbol NOT SIMILAR TO '[A-Z]{4}') = 4 THEN 0 ELSE 1 END"),
        ("B", "no symbol is null or blank",
         "SELECT count(*) FROM instruments WHERE symbol IS NULL "
         "OR length(trim(symbol)) = 0"),
        ("B", "party names match P-XXXX",
         "SELECT count(*) FROM parties WHERE party_name NOT SIMILAR TO 'P-[A-Z]{4}'"),
        ("B", "closure depth is at least 1",
         "SELECT count(*) FROM closure WHERE depth < 1"),
    ]
    return a


CAT_NAMES = {"A": "structural", "B": "domain", "V": "bitemporal",
             "G": "dag + closure"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_path", default=None)
    args = ap.parse_args()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t0 = time.perf_counter()
        tables = misata.generate_from_schema(build_schema())
        gen_secs = time.perf_counter() - t0

    con = duckdb.connect()
    for name, df in tables.items():
        con.register(name, df)

    results = []
    for cat, name, sql in build_assertions():
        try:
            violations = int(con.execute(sql).fetchone()[0] or 0)
            error = None
        except Exception as e:
            violations, error = -1, str(e)[:180]
        results.append({"category": cat, "name": name, "violations": violations,
                        "error": error, "known_red": name in KNOWN_RED})

    passed = sum(1 for r in results if r["violations"] == 0)
    total = len(results)
    unexpected = [r for r in results
                  if r["violations"] != 0 and not r["known_red"]]
    promotable = [r for r in results if r["violations"] == 0 and r["known_red"]]

    print(f"\nTHE LEDGER  --  {len(tables)} tables, "
          f"{sum(len(t) for t in tables.values()):,} rows, {total} assertions, "
          f"generated in {gen_secs:.1f}s\n")
    for cat in sorted({r["category"] for r in results}):
        rs = [r for r in results if r["category"] == cat]
        ok = sum(1 for r in rs if r["violations"] == 0)
        print(f"  {cat}  {CAT_NAMES.get(cat, cat):<16} {ok}/{len(rs)}")
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
        print(f"  PROMOTE: known-red '{r['name']}' now passes "
              f"— remove it from KNOWN_RED.")
    if args.json_path:
        with open(args.json_path, "w") as f:
            json.dump({"passed": passed, "total": total, "results": results,
                       "known_red": KNOWN_RED,
                       "generation_seconds": gen_secs}, f, indent=2)
    return 1 if (unexpected or promotable) else 0


if __name__ == "__main__":
    raise SystemExit(main())
