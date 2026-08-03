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
        # The exact wording moved when lint started running the same validation
        # generation runs: a rate outside the unit interval is now reported as a
        # blocking issue with a suggested fix, rather than as a lint finding.
        # Assert the substance, not the phrasing.
        out = " ".join(r.stdout.split())
        assert "1.7" in out
        assert "outside 0..1" in out or "outside [0, 1]" in out

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

class TestPublishedSchema:
    def test_public_schema_copy_matches_source(self):
        """schema/misata.schema.json is the URL editors fetch (SchemaStore,
        the yaml-language-server header); it must never drift from the
        source of truth in misata/_schemas/."""
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        public = (root / "schema" / "misata.schema.json").read_text()
        source = (root / "misata" / "_schemas" / "misata.schema.json").read_text()
        assert public == source


class TestSchemaCoversEveryDeclaration:
    """The JSON Schema must not fall behind the models.

    It silently had, for four releases: ``lifecycles``, ``retention``,
    ``missingness`` and ``late_arrivals`` all shipped between 0.8.9.4 and
    0.9.0, all reachable from ``SchemaConfig``, and none of them present here.
    Because the top level sets ``additionalProperties: false``, ``misata lint``
    rejected the exact YAML the docs told people to write. A test is the only
    thing that catches that, since nothing else reads both files.
    """

    # SchemaConfig fields that are engine internals rather than declarations.
    NOT_DECLARATIONS = {"tables", "columns", "events", "constraints"}

    def _declaration_fields(self):
        import typing
        from misata.schema import SchemaConfig
        out = set()
        for name, field in SchemaConfig.model_fields.items():
            if name in self.NOT_DECLARATIONS:
                continue
            ann = field.annotation
            if typing.get_origin(ann) is list:
                out.add(name)
        return out

    def test_every_declaration_list_is_lintable(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        schema = json.loads(
            (root / "misata" / "_schemas" / "misata.schema.json").read_text())
        assert schema.get("additionalProperties") is False, (
            "this test only means something while unknown keys are rejected")
        missing = sorted(self._declaration_fields() - set(schema["properties"]))
        assert not missing, (
            f"declarations reachable from SchemaConfig but rejected by "
            f"`misata lint`: {missing}. Add them to "
            f"misata/_schemas/misata.schema.json and schema/misata.schema.json.")

    def test_declarations_survive_the_dict_path(self):
        """Lintable is not enough; the dict path has to carry them through."""
        from misata.compat import from_dict_schema
        spec = {
            "name": "carry", "seed": 1,
            "tables": {"t": {"rows": 50, "columns": {
                "id": {"type": "int", "unique": True, "min": 1, "max": 50},
                "at": {"type": "datetime", "start": "2024-01-01",
                       "end": "2024-03-31"}}}},
            "time_grids": [{"table": "t", "column": "at", "minute_grid": 30}],
            "duplicates": [{"table": "t", "count": 4, "keys": ["id"]}],
        }
        cfg = from_dict_schema(spec)
        assert len(cfg.time_grids) == 1
        assert cfg.time_grids[0].minute_grid == 30
        assert len(cfg.duplicates) == 1
        assert cfg.duplicates[0].count == 4


class TestYamlLoaderCarriesEveryDeclaration:
    """The documented YAML form must not silently drop what it accepts.

    There are two dict paths into `SchemaConfig`: `compat.from_dict_schema` and
    `yaml_schema.load_yaml_schema`. 0.9.1 fixed the first. The second kept
    accepting `lifecycles`, `null_rate` and `pattern` and then discarding them,
    so a schema written exactly as the docs show was parsed, validated, and
    quietly stripped. Fixing one path and not the other is the failure mode
    this guards.
    """

    def _write(self, tmp_path, body):
        p = tmp_path / "s.yaml"
        p.write_text(body)
        return p

    def test_lifecycles_survive_the_documented_yaml_form(self, tmp_path):
        from misata.yaml_schema import load_yaml_schema
        path = self._write(tmp_path, """
name: lc_yaml
seed: 1
tables:
  t:
    rows: 40
    columns:
      id: {type: int, unique: true, min: 1, max: 40}
      created_at: {type: datetime, start: '2024-01-01', end: '2024-06-30'}
      state: {type: categorical, choices: [open, done]}
      done_at: {type: datetime, start: '2024-01-01', end: '2024-12-31'}
lifecycles:
  - name: lc
    table: t
    state_column: state
    start_column: created_at
    initial: open
    states:
      - {name: open}
      - {name: done, timestamp: done_at, terminal: true}
    transitions: [[open, done]]
    weights: {open: 0.5, done: 0.5}
""")
        cfg = load_yaml_schema(path, rows=40)
        assert len(cfg.lifecycles) == 1
        assert cfg.lifecycles[0].state_column == "state"

    def test_column_params_survive_the_documented_yaml_form(self, tmp_path):
        from misata.yaml_schema import load_yaml_schema
        path = self._write(tmp_path, """
name: params_yaml
seed: 1
tables:
  t:
    rows: 40
    columns:
      id: {type: int, unique: true, min: 1, max: 40}
      sku: {type: text, pattern: 'SKU-[0-9]{4}'}
      note: {type: text, null_rate: 0.4}
""")
        cfg = load_yaml_schema(path, rows=40)
        params = {c.name: c.distribution_params for c in cfg.columns["t"]}
        assert params["sku"].get("pattern") == "SKU-[0-9]{4}"
        assert params["note"].get("null_rate") == 0.4

    def test_every_declaration_list_survives_a_round_trip(self, tmp_path):
        """Any list on SchemaConfig must be loadable from YAML, not just some."""
        import typing
        from misata.yaml_schema import load_yaml_schema
        from misata.schema import SchemaConfig

        skip = {"tables", "columns", "events", "constraints"}
        declared = {
            name for name, f in SchemaConfig.model_fields.items()
            if name not in skip and typing.get_origin(f.annotation) is list
        }
        path = self._write(tmp_path, """
name: empty
seed: 1
tables:
  t:
    rows: 5
    columns:
      id: {type: int, unique: true, min: 1, max: 5}
""")
        cfg = load_yaml_schema(path, rows=5)
        missing = sorted(d for d in declared if not hasattr(cfg, d))
        assert not missing, f"SchemaConfig fields the loader cannot produce: {missing}"


class TestRelationshipSpellings:
    """The YAML loader accepts the names used everywhere else in the language.

    Its dict form only understood `parent`/`child`/`parent_col`/`child_col`.
    Every other surface -- the Python API, the JSON Schema, the dict path, every
    example in LANGUAGE.md -- uses `parent_table`/`child_table`/`parent_key`/
    `child_key`, so the names a reader would naturally reach for died on a bare
    `KeyError: 'parent'` with nothing to explain it. Found by writing a schema
    for the public sample datasets and watching it fail to parse.
    """

    def _load(self, tmp_path, rel_line):
        from misata.yaml_schema import load_yaml_schema
        p = tmp_path / "s.yaml"
        p.write_text(f"""
name: spellings
tables:
  orders:
    rows: 10
    columns:
      order_id: {{type: int, unique: true, min: 1, max: 10}}
  order_items:
    rows: 40
    columns:
      item_id: {{type: int, unique: true, min: 1, max: 40}}
      order_id: {{type: foreign_key}}
relationships:
  - {rel_line}
""")
        return load_yaml_schema(p, rows=10)

    def test_the_long_spelling_works(self, tmp_path):
        cfg = self._load(tmp_path, "{parent_table: orders, child_table: order_items, "
                                   "parent_key: order_id, child_key: order_id}")
        r = cfg.relationships[0]
        assert (r.parent_table, r.child_table) == ("orders", "order_items")
        assert (r.parent_key, r.child_key) == ("order_id", "order_id")

    def test_the_short_spelling_still_works(self, tmp_path):
        """Files already written against the old dialect must keep loading."""
        cfg = self._load(tmp_path, "{parent: orders, child: order_items, "
                                   "parent_col: order_id, child_col: order_id}")
        r = cfg.relationships[0]
        assert (r.parent_table, r.child_table) == ("orders", "order_items")
        assert (r.parent_key, r.child_key) == ("order_id", "order_id")

    def test_the_long_spelling_carries_its_extras(self, tmp_path):
        """Only the long form can say partition_by; it must not be dropped."""
        cfg = self._load(tmp_path, "{parent_table: orders, child_table: order_items, "
                                   "parent_key: order_id, child_key: order_id, "
                                   "partition_by: [tenant_id], min_children: 2}")
        r = cfg.relationships[0]
        assert r.partition_by == ["tenant_id"]
        assert r.min_children == 2

    def test_a_missing_table_says_what_to_write(self, tmp_path):
        """A bare KeyError is not an error message."""
        import pytest
        with pytest.raises(ValueError) as exc:
            self._load(tmp_path, "{parent_key: order_id, child_key: order_id}")
        assert "parent_table" in str(exc.value)


class TestTheFirstFiveMinutes:
    """`misata init` then `misata generate` is what the scaffold itself tells
    you to do. It did not work.

    The template's country probabilities summed to 0.85, so generation refused
    on the very first run, and `misata lint` called the same file clean because
    it never ran the check generation runs. Two failures in the shortest path a
    new user takes.
    """

    def _scaffold(self, tmp_path):
        from click.testing import CliRunner
        from misata.cli import main
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as fs:
            assert runner.invoke(main, ["init"]).exit_code == 0
            yield fs, runner, main

    def test_the_scaffold_generates(self, tmp_path):
        """Scaffold, generate. The path the scaffold's own comment prescribes."""
        for fs, runner, main in self._scaffold(tmp_path):
            result = runner.invoke(
                main, ["generate", "--config", "misata.yaml", "--output-dir", "out"])
            assert result.exit_code == 0, result.output

    def test_the_scaffold_lints_clean(self, tmp_path):
        for fs, runner, main in self._scaffold(tmp_path):
            result = runner.invoke(main, ["lint", "misata.yaml"])
            assert result.exit_code == 0, result.output

    def test_lint_refuses_what_generate_refuses(self, tmp_path):
        """Lint's promise is "will this generate?", so the answers must agree.

        Probabilities that do not sum to 1 are the case that shipped: lint
        passed, generate raised.
        """
        import pathlib
        for fs, runner, main in self._scaffold(tmp_path):
            path = pathlib.Path(fs) / "misata.yaml"
            path.write_text(path.read_text().replace(
                "probabilities: [0.45, 0.20, 0.15, 0.12, 0.08]",
                "probabilities: [0.40, 0.15, 0.12, 0.10, 0.08]", 1))

            lint = runner.invoke(main, ["lint", "misata.yaml"])
            gen = runner.invoke(
                main, ["generate", "--config", "misata.yaml", "--output-dir", "out"])

            assert gen.exit_code != 0, "generate should refuse this"
            assert lint.exit_code != 0, (
                "lint passed a schema generate refuses:\n" + lint.output)
            assert "0.8500" in lint.output

    def test_every_probability_list_in_the_scaffold_sums_to_one(self):
        """Guard the template itself, not just the one list that was wrong."""
        import re
        from misata import yaml_schema
        import pathlib

        src = pathlib.Path(yaml_schema.__file__).read_text()
        bad = []
        for m in re.finditer(r"probabilities: \[([0-9.,\s]+)\]", src):
            values = [float(v) for v in m.group(1).split(",")]
            if abs(sum(values) - 1.0) > 0.02:
                bad.append(f"{m.group(0)} sums to {sum(values):.4f}")
        assert not bad, "scaffolded probabilities must sum to 1.0:\n  " + "\n  ".join(bad)
