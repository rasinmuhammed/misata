"""Tests for mutation coverage (misata/mutate.py).

The subprocess/dbt parts are exercised by hand against real projects
(jaffle-shop and fivetran/dbt_stripe, both recorded in the changelog); what is
unit-tested here is everything that decides whether a report is *honest*: the
rewrite rules, the scoring, the errored-mutation exclusion, and the guarantee
that a model file is restored no matter what happens.
"""

import re

import pytest

from misata.mutate import (RULES, RULES_BY_KEY, ModelReport, MutationReport,
                           MutationResult, model_sql_path, mutate_model,
                           resolve_dbt_bin)


class TestRules:
    def test_join_type_rewrites_left_to_inner(self):
        r = RULES_BY_KEY["join_type"]
        sql = "select * from a left join b on a.id = b.id"
        assert "inner join b" in r.apply(sql, 0)

    def test_join_type_matches_left_outer_join(self):
        r = RULES_BY_KEY["join_type"]
        assert r.count("a LEFT OUTER JOIN b") == 1

    def test_join_type_ignores_inner_and_right(self):
        r = RULES_BY_KEY["join_type"]
        assert r.count("a inner join b right join c") == 0

    def test_window_partition_drop_keeps_valid_sql(self):
        r = RULES_BY_KEY["window_partition"]
        sql = "sum(x) over (partition by account_id order by day rows unbounded preceding)"
        out = r.apply(sql, 0)
        assert "partition by" not in out
        assert "over (order by day rows unbounded preceding)" in out

    def test_window_partition_requires_an_order_by(self):
        # Without ORDER BY, dropping the partition would change the shape of
        # the window in a way that is not the mistake being modelled.
        r = RULES_BY_KEY["window_partition"]
        assert r.count("sum(x) over (partition by a)") == 0

    def test_comparison_boundary_does_not_touch_gte(self):
        r = RULES_BY_KEY["comparison_boundary"]
        assert r.count("a >= 1") == 0
        assert r.count("a > 1") == 1

    def test_comparison_boundary_leaves_arrows_alone(self):
        # `->` and `->>` are JSON operators, not comparisons.
        r = RULES_BY_KEY["comparison_boundary"]
        assert r.count("payload->'a'") == 0

    def test_aggregate_swap_min_to_max(self):
        r = RULES_BY_KEY["aggregate_swap"]
        assert "max(" in r.apply("select min( x ) from t", 0)

    def test_count_distinct_collapses(self):
        r = RULES_BY_KEY["count_distinct"]
        out = r.apply("count(distinct order_id)", 0)
        assert out == "count(order_id)"

    def test_occurrence_targets_one_match_at_a_time(self):
        r = RULES_BY_KEY["join_type"]
        sql = "a left join b left join c"
        first, second = r.apply(sql, 0), r.apply(sql, 1)
        assert first.count("inner join") == 1 and second.count("inner join") == 1
        assert first != second

    def test_apply_past_the_end_returns_none(self):
        assert RULES_BY_KEY["join_type"].apply("select 1", 0) is None

    def test_every_rule_has_a_reason(self):
        # The `why` text is shown next to every survived mutation. A rule
        # without one produces a report the reader cannot act on.
        for rule in RULES:
            assert rule.why.strip()
            assert rule.label.strip()

    def test_rule_keys_are_unique(self):
        assert len({r.key for r in RULES}) == len(RULES)

    def test_rules_compile(self):
        for rule in RULES:
            re.compile(rule.pattern)


class TestScoring:
    def _res(self, outcome, key="join_type"):
        return MutationResult("m", RULES_BY_KEY[key], 0, outcome)

    def test_errored_mutations_are_excluded_from_the_score(self):
        # A mutation the warehouse rejects was not "caught" by the data;
        # counting it as caught would inflate the score.
        m = ModelReport("m", "m.sql", [
            self._res("caught"), self._res("survived"), self._res("errored"),
        ])
        assert (m.caught, m.total) == (1, 2)

    def test_survived_list_excludes_errors(self):
        m = ModelReport("m", "m.sql", [self._res("errored"), self._res("survived")])
        assert len(m.survived) == 1

    def test_report_aggregates_across_models(self):
        a = ModelReport("a", "a.sql", [self._res("caught"), self._res("survived")])
        b = ModelReport("b", "b.sql", [self._res("caught")])
        rep = MutationReport([a, b])
        assert (rep.caught, rep.total) == (2, 3)
        assert rep.score == pytest.approx(66.67, abs=0.01)

    def test_empty_report_scores_100_not_zero(self):
        # Nothing measured must not read as total failure.
        assert MutationReport([]).score == 100.0

    def test_to_dict_is_json_serialisable_and_complete(self):
        import json
        rep = MutationReport([ModelReport("a", "a.sql", [self._res("survived")])])
        d = json.loads(json.dumps(rep.to_dict()))
        assert d["total"] == 1 and d["caught"] == 0
        assert d["models"][0]["results"][0]["why"]


class TestFileSafety:
    def test_model_file_is_restored_when_a_build_raises(self, tmp_path):
        """The strongest guarantee this tool makes: your repo is never left
        holding a mutated model, even when everything goes wrong."""
        sql = "select * from a left join b on a.id = b.id"
        f = tmp_path / "m.sql"
        f.write_text(sql)

        class Exploding:
            def run_model(self, model):
                raise RuntimeError("warehouse on fire")

        with pytest.raises(RuntimeError):
            mutate_model(Exploding(), "m", f)
        assert f.read_text() == sql

    def test_model_file_is_restored_after_a_normal_run(self, tmp_path):
        sql = "select min(x) from t left join u on t.id = u.id"
        f = tmp_path / "m.sql"
        f.write_text(sql)

        class Fake:
            def __init__(self):
                self.n = 0

            def run_model(self, model):
                return True, ""

            def checksum(self, model):
                self.n += 1
                # Baseline, then a changing digest so everything is "caught".
                return f"d{self.n}", ""

        report = mutate_model(Fake(), "m", f)
        assert f.read_text() == sql
        assert report.total >= 2

    def test_survived_when_checksum_is_unchanged(self, tmp_path):
        f = tmp_path / "m.sql"
        f.write_text("select * from a left join b on a.id = b.id")

        class Blind:
            def run_model(self, model):
                return True, ""

            def checksum(self, model):
                return "same", ""

        report = mutate_model(Blind(), "m", f)
        assert report.total == 1
        assert report.caught == 0
        assert report.survived[0].rule.key == "join_type"

    def test_baseline_failure_reports_and_skips(self, tmp_path):
        f = tmp_path / "m.sql"
        f.write_text("select * from a left join b on a.id = b.id")

        class Broken:
            def run_model(self, model):
                return False, "relation does not exist"

            def checksum(self, model):
                return None, "unreachable"

        report = mutate_model(Broken(), "m", f)
        assert report.baseline_error and "relation does not exist" in report.baseline_error
        assert report.total == 0


class TestPathResolution:
    def test_root_project_model(self, tmp_path):
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "m.sql").write_text("select 1")
        node = {"original_file_path": "models/m.sql", "package_name": "proj"}
        assert model_sql_path(tmp_path, node) == (tmp_path / "models" / "m.sql").resolve()

    def test_installed_package_model(self, tmp_path):
        pkg = tmp_path / "dbt_packages" / "stripe" / "models"
        pkg.mkdir(parents=True)
        (pkg / "m.sql").write_text("select 1")
        node = {"original_file_path": "models/m.sql", "package_name": "stripe"}
        assert model_sql_path(tmp_path, node) == (pkg / "m.sql").resolve()

    def test_missing_file_returns_none(self, tmp_path):
        node = {"original_file_path": "models/nope.sql", "package_name": "p"}
        assert model_sql_path(tmp_path, node) is None


def test_resolve_dbt_bin_returns_something():
    assert resolve_dbt_bin()
