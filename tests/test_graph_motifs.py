"""Declared motifs: the patterns exist, and nothing else does.

The contract under test is not "motifs appear". It is the negative one, which
is the only reason this primitive is worth having: after generation, the
subgraph of edges carrying no case id must be acyclic. Every cycle in the
emitted table therefore belongs to a case somebody declared, so a detector run
against the data cannot produce an unexplained hit.
"""

import numpy as np
import pytest

import misata
from misata.schema import (Column, DagEdges, GraphMotifs, Relationship,
                           SchemaConfig, Table)

scipy_sparse = pytest.importorskip("scipy.sparse")
from scipy.sparse import coo_matrix                     # noqa: E402
from scipy.sparse.csgraph import connected_components   # noqa: E402


def _schema(seed=7, n_nodes=1200, n_edges=20_000, rate=0.01, benign=0.005):
    return SchemaConfig(
        name="motif_graph", seed=seed,
        tables=[Table(name="accounts", row_count=n_nodes),
                Table(name="transfers", row_count=n_edges)],
        columns={
            "accounts": [
                Column(name="account_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 10_000_000}),
                Column(name="holder", type="text"),
            ],
            "transfers": [
                Column(name="transfer_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 90_000_000}),
                Column(name="src", type="int",
                       distribution_params={"min": 1, "max": 10_000_000}),
                Column(name="dst", type="int",
                       distribution_params={"min": 1, "max": 10_000_000}),
                Column(name="amount", type="float",
                       distribution_params={"min": 5, "max": 50_000}),
            ],
        },
        dag_edges=[DagEdges(name="transfer_dag", table="transfers",
                            node_table="accounts", node_key="account_id",
                            from_column="src", to_column="dst")],
        graph_motifs=[GraphMotifs(
            name="laundering", table="transfers", node_table="accounts",
            node_key="account_id", from_column="src", to_column="dst",
            rate=rate,
            shares={"cycle": 0.4, "fan_out": 0.2, "fan_in": 0.2,
                    "scatter_gather": 0.1, "chain": 0.1},
            benign_shares={"cycle": 1.0}, benign_rate=benign,
            flag_column="is_flagged")],
    )


@pytest.fixture(scope="module")
def tables():
    return misata.generate_from_schema(_schema())


def _largest_scc(edges):
    ids = np.unique(np.concatenate([edges["src"].to_numpy(),
                                    edges["dst"].to_numpy()]))
    pos = {v: i for i, v in enumerate(ids)}
    r = edges["src"].map(pos).to_numpy()
    c = edges["dst"].map(pos).to_numpy()
    m = coo_matrix((np.ones(len(edges), dtype=np.int8), (r, c)),
                   shape=(len(ids), len(ids)))
    _, labels = connected_components(m, directed=True, connection="strong")
    return int(np.bincount(labels).max()) if len(ids) else 0


class TestTheNegativeGuarantee:
    def test_uncased_subgraph_is_acyclic(self, tables):
        """The whole point: no cycle exists outside a declared case."""
        t = tables["transfers"]
        background = t[t["motif_case"].astype(str) == ""]
        assert len(background) > 0
        assert _largest_scc(background) == 1, (
            "an un-cased cycle exists, so an accidental pattern is possible "
            "and the false-positive guarantee is void")

    def test_motifs_do_create_cycles(self, tables):
        """Control: the guarantee would be trivial on a graph with no cycles."""
        t = tables["transfers"]
        cyc = t[t["motif"] == "cycle"]
        assert len(cyc) > 0
        assert _largest_scc(cyc) >= 3


class TestDeclaredCountsAreExact:
    def test_flagged_edge_count_matches_rate(self, tables):
        t = tables["transfers"]
        assert int(t["is_flagged"].sum()) == round(0.01 * len(t))

    def test_motif_mix_matches_declared_shares(self, tables):
        t = tables["transfers"]
        flagged = t[t["is_flagged"]]
        counts = flagged["motif"].value_counts().to_dict()
        total = len(flagged)
        assert counts.get("cycle", 0) == round(0.4 * total)
        assert counts.get("fan_out", 0) == round(0.2 * total)
        assert counts.get("fan_in", 0) == round(0.2 * total)

    def test_every_cycle_case_is_a_real_ring(self, tables):
        t = tables["transfers"]
        rings = t[t["motif"] == "cycle"]
        assert rings["motif_case"].nunique() > 0
        for _cid, g in rings.groupby("motif_case"):
            assert set(g["src"]) == set(g["dst"]), "ring does not close"
            assert g["src"].nunique() == len(g), "node repeats inside a ring"


class TestHardNegatives:
    def test_benign_motifs_are_labeled_but_not_flagged(self, tables):
        t = tables["transfers"]
        benign = t[t["motif_case"].astype(str).str.startswith("B")]
        assert len(benign) == round(0.005 * len(t))
        assert not benign["is_flagged"].any(), (
            "a declared hard negative was flagged as a positive")
        assert _largest_scc(benign) >= 3, "hard negatives must be real cycles"


class TestReproducibility:
    def test_same_seed_same_graph(self):
        a = misata.generate_from_schema(_schema(seed=99))["transfers"]
        b = misata.generate_from_schema(_schema(seed=99))["transfers"]
        assert a[["src", "dst", "motif", "motif_case"]].equals(
            b[["src", "dst", "motif", "motif_case"]])

    def test_different_seed_different_graph(self):
        a = misata.generate_from_schema(_schema(seed=1))["transfers"]
        b = misata.generate_from_schema(_schema(seed=2))["transfers"]
        assert not a[["src", "dst"]].equals(b[["src", "dst"]])
