"""The Borough as a release gate.

The fourth conformance suite: intervals, spans, and bounded money under exact
totals. Same ``KNOWN_RED`` contract as the Gauntlet, the Warren and the Ledger,
enforced in pytest so it cannot rot quietly.
"""

import warnings

import pytest

pytest.importorskip("duckdb")

from benchmarks.borough import KNOWN_RED, build_schema, run  # noqa: E402

import misata  # noqa: E402


def _generate(cfg):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return misata.generate_from_schema(cfg)


@pytest.fixture(scope="module")
def results():
    return run(_generate(build_schema()))


class TestBoroughGate:

    def test_no_unexpected_failures(self, results):
        bad = [r for r in results if r["violations"] != 0 and r["name"] not in KNOWN_RED]
        detail = "\n".join(
            f"  [{r['category']}] {r['name']}: "
            + (f"{r['violations']:,} violating rows" if r["violations"] >= 0
               else f"ERROR {r['error']}")
            for r in bad)
        assert not bad, f"{len(bad)} Borough assertion(s) regressed:\n{detail}"

    def test_known_reds_are_still_red(self, results):
        promotable = [r["name"] for r in results
                      if r["violations"] == 0 and r["name"] in KNOWN_RED]
        assert not promotable, (
            f"these now pass and must leave benchmarks/borough.py KNOWN_RED: {promotable}")

    def test_every_new_shape_is_covered(self, results):
        """The reasons this suite exists must not quietly empty out."""
        by_cat = {c: [r for r in results if r["category"] == c] for c in "ISMK"}
        assert len(by_cat["I"]) >= 6 and len(by_cat["S"]) >= 4
        assert len(by_cat["M"]) >= 12 and len(by_cat["K"]) >= 6

    def test_the_declarations_are_load_bearing(self):
        """Without them the suite must fail, or it is proving nothing."""
        cfg = build_schema()
        cfg.no_overlap, cfg.capacity = [], []
        cfg.relationships = [r.model_copy(update={"parent_end": None}) for r in cfg.relationships]
        for table in cfg.tables:
            table.constraints = [c for c in table.constraints if c.type != "sum_lte_parent"]
        cfg.stock_flows = [s.model_copy(update={"opening": None}) for s in cfg.stock_flows]
        failing = {r["name"] for r in run(_generate(cfg)) if r["violations"] != 0}
        for name in ("nobody is in two places at once",
                     "no order after its visitor left",
                     "no account spends more than it holds",
                     "flour opens 2026-11-02 at 140"):
            assert name in failing, f"{name!r} passes without its declaration"

    def test_the_seats_are_load_bearing(self):
        cfg = build_schema()
        cfg.capacity = []
        for col in cfg.columns["places"]:
            if col.name == "seats":
                col.distribution_params = {"min": 2, "max": 3}
        failing = {r["name"] for r in run(_generate(cfg)) if r["violations"] != 0}
        assert "no place seats more people than it has, at any instant" in failing
