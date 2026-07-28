"""The Ledger as a release gate, plus tests for the composition audit.

The Ledger is the third conformance suite: bitemporal and graph-shaped. Same
`KNOWN_RED` contract as the Gauntlet and the Warren, enforced in pytest so it
cannot rot quietly.

`misata.composition` is the other half of this release: every declaration is
verified individually, and nothing checked that several on one table compose.
Four ordering defects had already been found by accident before it existed.
"""

import warnings

import pytest

duckdb = pytest.importorskip("duckdb")

from benchmarks.ledger import KNOWN_RED, build_assertions, build_schema  # noqa: E402

import misata  # noqa: E402
from misata.composition import (PASS_ORDER, composition_report,  # noqa: E402
                                find_overlaps)


@pytest.fixture(scope="module")
def results():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tables = misata.generate_from_schema(build_schema())
    con = duckdb.connect()
    for name, df in tables.items():
        con.register(name, df)
    out = []
    for cat, name, sql in build_assertions():
        try:
            violations = int(con.execute(sql).fetchone()[0] or 0)
            error = None
        except Exception as e:
            violations, error = -1, str(e)[:200]
        out.append({"category": cat, "name": name, "violations": violations,
                    "error": error})
    return out


class TestLedgerGate:

    def test_no_unexpected_failures(self, results):
        bad = [r for r in results
               if r["violations"] != 0 and r["name"] not in KNOWN_RED]
        detail = "\n".join(
            f"  [{r['category']}] {r['name']}: "
            + (f"{r['violations']:,} violating rows" if r["violations"] >= 0
               else f"ERROR {r['error']}")
            for r in bad)
        assert not bad, f"{len(bad)} Ledger assertion(s) regressed:\n{detail}"

    def test_known_reds_are_still_red(self, results):
        promotable = [r["name"] for r in results
                      if r["violations"] == 0 and r["name"] in KNOWN_RED]
        assert not promotable, (
            f"these now pass and must leave benchmarks/ledger.py KNOWN_RED: "
            f"{promotable}")

    def test_both_new_shapes_are_covered(self, results):
        """The two reasons this suite exists must not quietly empty out."""
        bitemporal = [r for r in results if r["category"] == "V"]
        graph = [r for r in results if r["category"] == "G"]
        assert len(bitemporal) >= 10 and len(graph) >= 10
        assert all(r["violations"] == 0 for r in bitemporal + graph)

    def test_the_declarations_are_load_bearing(self):
        """Without them the suite must fail, or it is proving nothing.

        A conformance suite that passes with the feature switched off is
        decorative. This is the control, asserted rather than assumed.
        """
        cfg = build_schema()
        cfg.bitemporal, cfg.dag_edges, cfg.closures = [], [], []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tables = misata.generate_from_schema(cfg)
        con = duckdb.connect()
        for name, df in tables.items():
            con.register(name, df)
        failing = 0
        for _, _, sql in build_assertions():
            try:
                if int(con.execute(sql).fetchone()[0] or 0) != 0:
                    failing += 1
            except Exception:
                failing += 1
        assert failing >= 10, (
            f"only {failing} assertion(s) fail without the declarations; the "
            f"suite is not testing what it claims to")


class TestComposition:

    def test_pass_order_has_no_duplicates(self):
        assert len(PASS_ORDER) == len(set(PASS_ORDER))

    def test_a_clean_schema_reports_nothing(self):
        """False alarms are the failure mode of a tool like this."""
        from misata.schema import SchemaConfig, Table, Column
        cfg = SchemaConfig(
            name="plain", seed=1,
            tables=[Table(name="t", row_count=10)],
            columns={"t": [Column(name="id", type="int", unique=True,
                                  distribution_params={"min": 1, "max": 10})]},
        )
        assert find_overlaps(cfg) == []
        assert "No column is written by more than one" in composition_report(cfg)

    def test_it_finds_a_real_double_writer(self):
        """A lifecycle timestamp that also declares a null_rate."""
        from misata.schema import (SchemaConfig, Table, Column, Lifecycle,
                                   LifecycleState)
        cfg = SchemaConfig(
            name="clash", seed=1,
            tables=[Table(name="t", row_count=50)],
            columns={"t": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 50}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-06-30"}),
                Column(name="state", type="categorical",
                       distribution_params={"choices": ["open", "done"]}),
                Column(name="done_at", type="datetime", nullable=True,
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-12-31",
                                            "null_rate": 0.5}),
            ]},
            lifecycles=[Lifecycle(
                name="lc", table="t", state_column="state",
                start_column="created_at", initial="open",
                states=[LifecycleState(name="open"),
                        LifecycleState(name="done", timestamp="done_at",
                                       terminal=True)],
                transitions=[("open", "done")],
                weights={"open": 0.5, "done": 0.5})],
        )
        overlaps = find_overlaps(cfg)
        cols = {o.column for o in overlaps}
        assert "done_at" in cols
        clash = next(o for o in overlaps if o.column == "done_at")
        assert "lifecycle" in clash.later

    def test_it_reports_order_not_breakage(self):
        """The tool is static and must not claim what it cannot know.

        Its first version announced that three declared null rates "will not
        hold" on a schema where all three held exactly, because they had been
        chosen to match the lifecycle's weights. Overlap is a fact about order;
        whether the result is wrong is the audit's job, not this one's.
        """
        from misata.schema import (SchemaConfig, Table, Column, Lifecycle,
                                   LifecycleState)
        cfg = SchemaConfig(
            name="wording", seed=1,
            tables=[Table(name="t", row_count=20)],
            columns={"t": [
                Column(name="id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 20}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-06-30"}),
                Column(name="state", type="categorical",
                       distribution_params={"choices": ["open", "done"]}),
                Column(name="done_at", type="datetime", nullable=True,
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-12-31",
                                            "null_rate": 0.5}),
            ]},
            lifecycles=[Lifecycle(
                name="lc", table="t", state_column="state",
                start_column="created_at", initial="open",
                states=[LifecycleState(name="open"),
                        LifecycleState(name="done", timestamp="done_at",
                                       terminal=True)],
                transitions=[("open", "done")],
                weights={"open": 0.5, "done": 0.5})],
        )
        note = next(o for o in find_overlaps(cfg) if o.column == "done_at").note
        assert "only holds if" in note
        for forbidden in ("will not hold", "breaks", "destroys"):
            assert forbidden not in note

    def test_every_shipped_suite_is_reportable(self):
        """The report must not crash on any schema the repo actually ships."""
        from benchmarks.gauntlet import build_schema as gauntlet
        from benchmarks.warren import build_schema as warren
        for build in (gauntlet, warren, build_schema):
            text = composition_report(build())
            assert isinstance(text, str) and text
