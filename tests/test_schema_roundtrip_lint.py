"""Epoch 2 item 9: lossless YAML round-trip and pre-generation lint.

The editable-schema contract: save any SchemaConfig to YAML, load it back,
and generation produces byte-identical data; every declaration survives the
trip. And `misata lint` runs the feasibility arithmetic against the schema
alone, before any rows exist, with the same messages generation would give.
"""

import subprocess
import sys

import pandas as pd
import pytest

import misata
from misata.lint import lint_schema
from misata.schema import (Column, GroupShares, OutcomeCurve, RateCurve,
                           RealismConfig, Relationship, SchemaConfig, Table,
                           WaterfallIdentity)
from misata.yaml_schema import load_yaml_schema, save_yaml_schema


def _full_schema():
    """One schema exercising every declaration type that must round-trip."""
    cols_c = [
        Column(name="customer_id", type="int", unique=True,
               distribution_params={"min": 1, "max": 99999}),
        Column(name="signup_date", type="datetime",
               distribution_params={"start": "2024-01-01", "end": "2025-05-31"}),
    ]
    cols_o = [
        Column(name="order_id", type="int", unique=True,
               distribution_params={"min": 1, "max": 999999}),
        Column(name="customer_id", type="foreign_key"),
        Column(name="order_date", type="datetime",
               distribution_params={"start": "2025-01-01", "end": "2025-06-30"}),
        Column(name="category", type="categorical",
               distribution_params={"choices": ["A", "B", "C"]}),
        Column(name="revenue", type="float",
               distribution_params={"min": 5, "max": 500, "decimals": 2}),
        Column(name="is_flagged", type="boolean"),
    ]
    cols_m = [
        Column(name="movement_id", type="int", unique=True,
               distribution_params={"min": 1, "max": 999999}),
        Column(name="period", type="text"),
        Column(name="movement_type", type="text"),
        Column(name="amount", type="float"),
    ]
    return SchemaConfig(
        name="roundtrip", seed=42,
        tables=[Table(name="customers", row_count=200),
                Table(name="orders", row_count=2000),
                Table(name="mrr_movements", row_count=900)],
        columns={"customers": cols_c, "orders": cols_o,
                 "mrr_movements": cols_m},
        relationships=[Relationship(parent_table="customers",
                                    child_table="orders",
                                    parent_key="customer_id",
                                    child_key="customer_id")],
        outcome_curves=[OutcomeCurve(
            table="orders", column="revenue", time_column="order_date",
            time_unit="month", value_mode="absolute",
            curve_points=[{"date": f"2025-{m:02d}-01",
                           "target_value": 40000.0 + m * 1000}
                          for m in range(1, 7)])],
        rate_curves=[RateCurve(
            table="orders", column="is_flagged", time_column="order_date",
            rate_points=[{"period": f"2025-{m:02d}", "rate": 0.05}
                         for m in range(1, 7)])],
        group_shares=[GroupShares(table="orders", measure="revenue",
                                  group_column="category",
                                  shares={"A": 0.5, "B": 0.3, "C": 0.2})],
        waterfalls=[WaterfallIdentity(
            table="mrr_movements", starting_value=80000.0,
            points=[{"period": f"2025-{m:02d}", "ending_value": 80000.0 + m * 4000}
                    for m in range(1, 7)])],
        vocabularies={"segment": ["smb", "mid", "ent"]},
        realism=RealismConfig(locale="de_DE"),
    )


class TestRoundTrip:
    def test_generation_is_byte_identical_after_round_trip(self, tmp_path):
        schema = _full_schema()
        path = tmp_path / "schema.yaml"
        save_yaml_schema(schema, path)
        loaded = load_yaml_schema(path)
        a = misata.generate_from_schema(schema)
        b = misata.generate_from_schema(loaded)
        assert set(a) == set(b)
        for name in a:
            pd.testing.assert_frame_equal(a[name], b[name])

    def test_every_declaration_survives(self, tmp_path):
        schema = _full_schema()
        path = tmp_path / "schema.yaml"
        save_yaml_schema(schema, path)
        loaded = load_yaml_schema(path)
        assert len(loaded.outcome_curves) == 1
        assert len(loaded.rate_curves) == 1
        assert loaded.group_shares[0].shares == {"A": 0.5, "B": 0.3, "C": 0.2}
        assert loaded.waterfalls[0].starting_value == 80000.0
        assert len(loaded.waterfalls[0].points) == 6
        assert loaded.vocabularies == {"segment": ["smb", "mid", "ent"]}
        assert loaded.realism is not None and loaded.realism.locale == "de_DE"

    def test_editor_schema_header_written(self, tmp_path):
        path = tmp_path / "schema.yaml"
        save_yaml_schema(_full_schema(), path)
        first = path.read_text().splitlines()[0]
        assert first.startswith("# yaml-language-server: $schema=")

    def test_top_level_locale_shorthand_folds_into_realism(self, tmp_path):
        path = tmp_path / "s.yaml"
        path.write_text(
            "name: loc\nlocale: ja_JP\ntables:\n  t:\n    rows: 10\n"
            "    columns:\n      id: {type: int, unique: true, min: 1, max: 999}\n")
        loaded = load_yaml_schema(path)
        assert loaded.realism is not None and loaded.realism.locale == "ja_JP"


def _one_table(row_count=100, extra_cols=None, **schema_kwargs):
    cols = [Column(name="id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 999999})]
    cols.extend(extra_cols or [])
    return SchemaConfig(
        name="lint", seed=1,
        tables=[Table(name="t", row_count=row_count)],
        columns={"t": cols}, relationships=[], **schema_kwargs)


class TestLint:
    def test_clean_schema_has_no_findings(self):
        assert lint_schema(_full_schema()) == []

    def test_reversed_date_range_warns(self):
        schema = _one_table(extra_cols=[
            Column(name="d", type="date",
                   distribution_params={"start": "2025-06-30",
                                        "end": "2025-01-01"})])
        f = [x for x in lint_schema(schema) if "swap" in x.message]
        assert f and f[0].severity == "warning"

    def test_unique_range_too_small_warns(self):
        schema = _one_table(row_count=1000)
        schema.columns["t"][0].distribution_params["max"] = 50
        f = [x for x in lint_schema(schema) if "unique range" in x.message]
        assert f and f[0].severity == "warning"

    def test_rate_outside_unit_interval_errors(self):
        schema = _one_table(
            extra_cols=[
                Column(name="flag", type="boolean"),
                Column(name="d", type="date",
                       distribution_params={"start": "2025-01-01",
                                            "end": "2025-06-30"})],
            rate_curves=[RateCurve(table="t", column="flag", time_column="d",
                                   rate_points=[{"period": "2025-01",
                                                 "rate": 1.7}])])
        f = [x for x in lint_schema(schema) if "outside 0..1" in x.message]
        assert f and f[0].severity == "error"

    def test_infeasible_bound_target_errors(self):
        schema = _one_table(
            row_count=10,
            extra_cols=[
                Column(name="amount", type="float",
                       distribution_params={"min": 100, "max": 200}),
                Column(name="d", type="date",
                       distribution_params={"start": "2025-01-01",
                                            "end": "2025-06-30"})],
            outcome_curves=[OutcomeCurve(
                table="t", column="amount", time_column="d",
                time_unit="month", value_mode="absolute",
                curve_points=[{"date": "2025-01-01",
                               "target_value": 99999.0}])])
        assert any(x.severity == "error" for x in lint_schema(schema))

    def test_group_share_bucket_infeasibility_errors(self):
        shares = {chr(65 + i): (0.084 if i < 10 else 0.08) for i in range(12)}
        schema = _one_table(
            row_count=10,
            extra_cols=[
                Column(name="cat", type="categorical",
                       distribution_params={"choices": list(shares)}),
                Column(name="rev", type="float",
                       distribution_params={"min": 1, "max": 10})],
            group_shares=[GroupShares(table="t", measure="rev",
                                      group_column="cat", shares=shares)])
        f = [x for x in lint_schema(schema) if "positive-share groups" in x.message]
        assert f and f[0].severity == "error"

    def test_unpaired_group_share_is_info_not_error(self):
        schema = _one_table(
            row_count=1000,
            extra_cols=[
                Column(name="cat", type="categorical",
                       distribution_params={"choices": ["A", "B"]}),
                Column(name="rev", type="float",
                       distribution_params={"min": 1, "max": 10})],
            group_shares=[GroupShares(table="t", measure="rev",
                                      group_column="cat",
                                      shares={"A": 0.6, "B": 0.4})])
        f = [x for x in lint_schema(schema) if "no exact-target curve" in x.message]
        assert f and f[0].severity == "info"

    def test_waterfall_cells_exceed_rows_errors(self):
        schema = _one_table(
            row_count=3,
            extra_cols=[
                Column(name="period", type="text"),
                Column(name="movement_type", type="text"),
                Column(name="amount", type="float")],
            waterfalls=[WaterfallIdentity(
                table="t", starting_value=1000.0,
                points=[{"period": f"2025-{m:02d}", "ending_value": 1000.0 + m}
                        for m in range(1, 7)])])
        f = [x for x in lint_schema(schema) if "cannot host" in x.message]
        assert f and f[0].severity == "error"

    def test_unsorted_waterfall_labels_is_info(self):
        schema = _one_table(
            row_count=500,
            extra_cols=[
                Column(name="period", type="text"),
                Column(name="movement_type", type="text"),
                Column(name="amount", type="float")],
            waterfalls=[WaterfallIdentity(
                table="t", starting_value=1000.0,
                points=[{"period": "march", "ending_value": 1100.0},
                        {"period": "april", "ending_value": 1200.0}])])
        f = [x for x in lint_schema(schema) if "lexicographically" in x.message]
        assert f and f[0].severity == "info"

    def test_missing_declared_column_errors(self):
        schema = _one_table(
            row_count=100,
            extra_cols=[Column(name="rev", type="float",
                               distribution_params={"min": 1, "max": 10})],
            group_shares=[GroupShares(table="t", measure="rev",
                                      group_column="nonexistent",
                                      shares={"A": 1.0})])
        f = [x for x in lint_schema(schema) if "does not exist" in x.message]
        assert f and f[0].severity == "error"


class TestLintCLI:
    def _run(self, path, *args):
        return subprocess.run(
            [sys.executable, "-m", "misata.cli", "lint", str(path), *args],
            capture_output=True, text=True)

    def test_clean_yaml_exits_zero(self, tmp_path):
        path = tmp_path / "clean.yaml"
        save_yaml_schema(_full_schema(), path)
        r = self._run(path)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Lint clean" in r.stdout

    def test_broken_yaml_exits_one(self, tmp_path):
        path = tmp_path / "broken.yaml"
        path.write_text(
            "name: broken\ntables:\n  t:\n    rows: 10\n    columns:\n"
            "      id: {type: int, unique: true, min: 1, max: 999}\n"
            "      flag: {type: boolean}\n"
            "      d: {type: date, start: '2025-01-01', end: '2025-06-30'}\n"
            "rate_curves:\n"
            "  - table: t\n    column: flag\n    time_column: d\n"
            "    rate_points:\n      - {period: '2025-01', rate: 1.7}\n")
        r = self._run(path)
        assert r.returncode == 1, r.stdout + r.stderr
        # Rich wraps table cells, so normalise whitespace before matching.
        assert "outside 0..1" in " ".join(r.stdout.split())

    def test_strict_fails_on_warnings(self, tmp_path):
        path = tmp_path / "warn.yaml"
        path.write_text(
            "name: warn\ntables:\n  t:\n    rows: 10\n    columns:\n"
            "      id: {type: int, unique: true, min: 1, max: 999}\n"
            "      d: {type: date, start: '2025-06-30', end: '2025-01-01'}\n")
        assert self._run(path).returncode == 0
        assert self._run(path, "--strict").returncode == 1

    def test_unparseable_exits_two(self, tmp_path):
        # Unknown column types are deliberately coerced to text (forgiving
        # parse), so "unparseable" means the file itself is broken.
        path = tmp_path / "bad.yaml"
        path.write_text("name: [unclosed\ntables: {{{{")
        assert self._run(path).returncode == 2
