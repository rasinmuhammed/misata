"""Joint satisfaction: several declared margins holding at once, exactly.

Declaring "40% enterprise" and "15% APAC" separately used to yield both margins
and whatever relationship between them the sampler happened to produce, which
is a specification nobody wrote. These tests are about the relationship being
declarable, the margins surviving it, and contradictory margins being refused
with arithmetic rather than averaged.
"""
import collections

import numpy as np
import pytest

import misata
from misata.joint import (MarginsIncompatible, assign_rows, integerise_2d, ipf,
                          solve_joint)
from misata.schema import Column, JointDistribution, SchemaConfig, Table

MARGINS = {"plan": {"starter": .5, "team": .3, "enterprise": .2},
           "region": {"emea": .4, "amer": .45, "apac": .15}}


class TestMaximumEntropySolution:
    def test_margins_hold_to_floating_point(self):
        table, dims, _lv, diag = ipf(MARGINS)
        assert diag["max_margin_error"] < 1e-9
        assert np.allclose(table.sum(axis=1), [.5, .3, .2])
        assert np.allclose(table.sum(axis=0), [.4, .45, .15])

    def test_no_declared_dependency_gives_independence(self):
        """Max-entropy is the least-assuming answer: state only margins and
        you get exactly independence, never a correlation nobody asked for."""
        table, _d, _lv, _diag = ipf(MARGINS)
        assert np.allclose(table, np.outer([.5, .3, .2], [.4, .45, .15]))


class TestRoundingPreservesMargins:
    def test_two_way_integer_margins_are_exact(self):
        table, _d, _lv, _diag = ipf(MARGINS)
        counts = integerise_2d(table, 10_000)
        assert counts.sum() == 10_000
        assert list(counts.sum(axis=1)) == [5000, 3000, 2000]
        assert list(counts.sum(axis=0)) == [4000, 4500, 1500]

    def test_awkward_row_count_still_sums_exactly(self):
        table, _d, _lv, _diag = ipf(MARGINS)
        counts = integerise_2d(table, 9_973)
        assert counts.sum() == 9_973


class TestDeclaredDependency:
    def test_emphasis_moves_the_joint_without_moving_the_margins(self):
        counts, dims, levels, _d = solve_joint(
            MARGINS, 20_000, seed_weights={("enterprise", "apac"): 4.0})
        assert list(counts.sum(axis=1)) == [10_000, 6_000, 4_000]
        assert list(counts.sum(axis=0)) == [8_000, 9_000, 3_000]
        ent_apac = counts[levels[0].index("enterprise"), levels[1].index("apac")]
        assert ent_apac / counts.sum(axis=0)[2] > 0.35   # independence would be .20

    def test_forbidden_combination_is_empty_and_margins_survive(self):
        counts, _d, levels, _diag = solve_joint(
            MARGINS, 20_000, forbidden=[{"plan": "enterprise", "region": "emea"}])
        assert counts[levels[0].index("enterprise"), levels[1].index("emea")] == 0
        assert list(counts.sum(axis=1)) == [10_000, 6_000, 4_000]


class TestRefusal:
    def test_margin_not_accounting_for_all_rows_is_refused(self):
        with pytest.raises(MarginsIncompatible):
            ipf({"a": {"x": .5, "y": .4}, "b": {"p": .5, "q": .5}})

    def test_structural_zeros_that_starve_a_margin_are_refused(self):
        with pytest.raises(MarginsIncompatible):
            ipf({"a": {"x": .5, "y": .5}, "b": {"p": .5, "q": .5}},
                seed=np.array([[1., 0.], [1., 0.]]))

    def test_schema_refuses_a_margin_that_does_not_sum_to_one(self):
        with pytest.raises(Exception):
            JointDistribution(name="j", table="t",
                              margins={"a": {"x": .5, "y": .4}, "b": {"p": 1.0}})

    def test_schema_refuses_a_single_margin(self):
        with pytest.raises(Exception):
            JointDistribution(name="j", table="t", margins={"a": {"x": 1.0}})


class TestEndToEnd:
    def _schema(self, rows=20_000):
        return SchemaConfig(
            name="j", seed=5, tables=[Table(name="customers", row_count=rows)],
            columns={"customers": [
                Column(name="customer_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 10 ** 7}),
                Column(name="plan", type="categorical",
                       distribution_params={"choices": ["starter", "team", "enterprise"]}),
                Column(name="region", type="categorical",
                       distribution_params={"choices": ["emea", "amer", "apac"]})]},
            joint_distributions=[JointDistribution(
                name="plan_by_region", table="customers", margins=MARGINS,
                emphasis={"enterprise|apac": 4.0},
                forbidden=[{"plan": "enterprise", "region": "emea"}])])

    def test_emitted_rows_match_every_declared_margin(self):
        df = misata.generate_from_schema(self._schema())["customers"]
        plan = collections.Counter(df["plan"])
        region = collections.Counter(df["region"])
        assert [plan[k] for k in ("starter", "team", "enterprise")] == [10_000, 6_000, 4_000]
        assert [region[k] for k in ("emea", "amer", "apac")] == [8_000, 9_000, 3_000]

    def test_forbidden_combination_never_appears_in_the_output(self):
        df = misata.generate_from_schema(self._schema())["customers"]
        pairs = collections.Counter(zip(df["plan"], df["region"]))
        assert pairs[("enterprise", "emea")] == 0

    def test_reproducible(self):
        a = misata.generate_from_schema(self._schema(2_000))["customers"]
        b = misata.generate_from_schema(self._schema(2_000))["customers"]
        assert list(a["plan"]) == list(b["plan"])
