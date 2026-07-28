"""Directed acyclic edge tables and the closures that must agree with them.

0.9.2 made a self-referential *column* acyclic by construction. An edge table is
the same guarantee in a different shape, and it needs a different construction:
there is no insertion order to point backwards along, because the thing being
ordered lives in another table.

The answer is the same idea one level up. Nodes get a topological rank, edges are
only ever drawn from lower rank to higher, and a cycle cannot close at any depth
without a check. A closure table is then not generated at all: it is *computed*
from the edges, because a closure that disagrees with its own edges is the defect,
and the only way to be sure it agrees is to derive it.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def apply_dag_edges(
    tables: Dict[str, pd.DataFrame],
    spec: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Rewrite an edge table so its edges form a DAG with no duplicate pairs."""
    edges = tables.get(spec.table)
    nodes = tables.get(spec.node_table)
    if edges is None or nodes is None or edges.empty or nodes.empty:
        return tables
    for col, df, name in ((spec.from_column, edges, spec.table),
                          (spec.to_column, edges, spec.table),
                          (spec.node_key, nodes, spec.node_table)):
        if col not in df.columns:
            warnings.warn(
                f"DagEdges '{spec.name}': column '{col}' missing from '{name}'. "
                f"Skipping.")
            return tables

    ids = nodes[spec.node_key].dropna().to_numpy()
    if len(ids) < 2:
        return tables
    # A random topological order. Every edge runs low rank -> high rank, so the
    # graph is acyclic by construction rather than by rejection.
    order = rng.permutation(len(ids))
    ranked = ids[order]

    n_nodes = len(ranked)
    max_pairs = n_nodes * (n_nodes - 1) // 2
    want = len(edges)
    if want > max_pairs:
        warnings.warn(
            f"DagEdges '{spec.name}': {want} distinct edges declared but "
            f"{n_nodes} nodes admit only {max_pairs} acyclic pairs. Raise "
            f"{spec.node_table}.row_count, or lower {spec.table}.row_count.")
        want = max_pairs

    # Sample distinct (i < j) pairs without materialising all of them: draw an
    # index into the upper triangle and invert it. Retries only on collision,
    # which is rare while `want` stays well under `max_pairs`.
    chosen: set = set()
    attempts = 0
    limit = max(want * 20, 1000)
    while len(chosen) < want and attempts < limit:
        need = want - len(chosen)
        i = rng.integers(0, n_nodes - 1, size=need)
        j = i + 1 + (rng.random(need) * (n_nodes - 1 - i)).astype("int64")
        j = np.minimum(j, n_nodes - 1)
        chosen.update(zip(i.tolist(), j.tolist()))
        attempts += need
    pairs = sorted(chosen)[:want]
    if len(pairs) < len(edges):
        # Not enough distinct pairs: keep the table's declared length by
        # trimming rather than by repeating an edge, since duplicate pairs are
        # exactly what this declaration promises not to emit.
        warnings.warn(
            f"DagEdges '{spec.name}': emitting {len(pairs)} distinct edges "
            f"instead of the declared {len(edges)}; the graph cannot hold more "
            f"without repeating a pair.")

    out = edges.iloc[: len(pairs)].copy()
    out[spec.from_column] = [ranked[i] for i, _ in pairs]
    out[spec.to_column] = [ranked[j] for _, j in pairs]
    tables[spec.table] = out.reset_index(drop=True)
    return tables


def _closure_of(
    frm: np.ndarray, to: np.ndarray, max_depth: int = 32
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Transitive closure with shortest-path depth, by breadth-first layers.

    One frontier expansion per depth, each a vectorised join, so the cost is
    O(depth x edges) rather than a recursive walk per node.
    """
    seen: Dict[Tuple[Any, Any], int] = {}
    frontier = list(zip(frm.tolist(), to.tolist()))
    for a, d in frontier:
        seen.setdefault((a, d), 1)

    adjacency: Dict[Any, List[Any]] = {}
    for a, d in zip(frm.tolist(), to.tolist()):
        adjacency.setdefault(a, []).append(d)

    depth = 1
    while frontier and depth < max_depth:
        nxt = []
        for a, d in frontier:
            for nd in adjacency.get(d, ()):
                key = (a, nd)
                if key not in seen:
                    seen[key] = depth + 1
                    nxt.append(key)
        frontier = nxt
        depth += 1

    if not seen:
        return (np.array([], dtype=object), np.array([], dtype=object),
                np.array([], dtype="int64"))
    items = sorted(seen.items(), key=lambda kv: (kv[1], str(kv[0])))
    anc = np.array([k[0] for k, _ in items], dtype=object)
    des = np.array([k[1] for k, _ in items], dtype=object)
    dep = np.array([v for _, v in items], dtype="int64")
    return anc, des, dep


def apply_closure(
    tables: Dict[str, pd.DataFrame],
    spec: Any,
    rng: np.random.Generator,
    config: Any = None,
) -> Dict[str, pd.DataFrame]:
    """Replace a closure table with the actual closure of its edge table.

    The row count is whatever the closure is. A declared ``row_count`` on a
    closure table is a guess about a graph that had not been generated yet, so it
    is advisory: the table is resized, and any other column keeps its generated
    values, recycled if the closure is larger than the guess.
    """
    closure = tables.get(spec.table)
    edges = tables.get(spec.edge_table)
    if closure is None or edges is None or edges.empty:
        return tables
    for col, df, name in ((spec.edge_from, edges, spec.edge_table),
                          (spec.edge_to, edges, spec.edge_table),
                          (spec.ancestor_column, closure, spec.table),
                          (spec.descendant_column, closure, spec.table)):
        if col not in df.columns:
            warnings.warn(
                f"TransitiveClosure '{spec.name}': column '{col}' missing from "
                f"'{name}'. Skipping.")
            return tables

    anc, des, dep = _closure_of(edges[spec.edge_from].to_numpy(),
                                edges[spec.edge_to].to_numpy())
    n = len(anc)
    if n == 0:
        tables[spec.table] = closure.iloc[:0].copy()
        return tables

    # Recycle the generated rows so unrelated columns keep plausible values, and
    # keep any unique column unique by rebuilding it as a run of integers.
    idx = np.arange(n) % max(len(closure), 1)
    out = closure.iloc[idx].reset_index(drop=True).copy()
    out[spec.ancestor_column] = anc
    out[spec.descendant_column] = des
    if spec.depth_column and spec.depth_column in out.columns:
        out[spec.depth_column] = dep

    # Recycling rows repeats their keys. Any column the schema declared unique
    # is rebuilt as a fresh run, because a closure that fixes reachability by
    # breaking the primary key has traded one defect for a worse one.
    unique_cols = [c.name for c in ((config.columns.get(spec.table, []) or [])
                                    if config is not None else [])
                   if getattr(c, "unique", False) and c.name in out.columns]
    for c in unique_cols:
        base = pd.to_numeric(closure[c], errors="coerce")
        start = int(base.min()) if base.notna().any() else 1
        out[c] = np.arange(start, start + n, dtype="int64")
    tables[spec.table] = out
    return tables


def apply_graphs(
    tables: Dict[str, pd.DataFrame],
    config: Any,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    """Edges first, then closures, because a closure is derived from its edges."""
    for spec in (getattr(config, "dag_edges", None) or []):
        try:
            apply_dag_edges(tables, spec, rng)
        except Exception as e:
            warnings.warn(f"DagEdges '{spec.name}' failed ({e}); table left as "
                          f"generated.")
    for spec in (getattr(config, "closures", None) or []):
        try:
            apply_closure(tables, spec, rng, config)
        except Exception as e:
            warnings.warn(f"TransitiveClosure '{spec.name}' failed ({e}); table "
                          f"left as generated.")
    return tables


def graph_tables(config: Any) -> set:
    out: set = set()
    for spec in (getattr(config, "dag_edges", None) or []):
        out.add(spec.table)
        out.add(spec.node_table)
    for spec in (getattr(config, "closures", None) or []):
        out.add(spec.table)
        out.add(spec.edge_table)
    return out
