"""Every command speaks one envelope with --json, with one set of exit codes."""

from __future__ import annotations

import json
import warnings
from importlib import resources
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

jsonschema = pytest.importorskip("jsonschema")

from misata.cli import main
from misata.cli_output import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_USAGE,
    MisataGroup,
    emit,
    fail,
)
from misata.exceptions import ConformanceWarning

SCHEMA = json.loads(resources.files("misata._schemas")
                    .joinpath("cli-envelope.schema.json").read_text(encoding="utf-8"))

#: Commands whose stdout belongs to something else: a protocol or a server log.
NO_ENVELOPE = {"misata serve", "misata studio", "misata mcp run"}

INFEASIBLE = """\
name: refused
seed: 1
tables:
  a:
    rows: 10
    columns:
      code: {type: int, unique: true, min: 1, max: 5}
"""

FEASIBLE = """\
name: fine
seed: 1
tables:
  a:
    rows: 20
    columns:
      code: {type: int, unique: true, min: 1, max: 500}
"""


def _envelope(result) -> dict:
    payload = json.loads(result.stdout)
    jsonschema.validate(payload, SCHEMA)
    assert payload["ok"] is (payload["exit_code"] == EXIT_OK)
    return payload


def _commands(group: click.Group, prefix: str = "misata"):
    for name, command in sorted(group.commands.items()):
        path = f"{prefix} {name}"
        if isinstance(command, click.Group):
            yield from _commands(command, path)
        else:
            yield path, command


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def schemas(tmp_path):
    bad = tmp_path / "refused.yaml"
    bad.write_text(INFEASIBLE)
    good = tmp_path / "fine.yaml"
    good.write_text(FEASIBLE)
    return good, bad


class TestEveryCommand:
    @pytest.mark.parametrize("path,command", list(_commands(main)), ids=lambda v: str(v))
    def test_accepts_json_unless_its_stdout_is_a_protocol(self, path, command):
        flags = {opt for p in command.params for opt in getattr(p, "opts", [])}
        assert ("--json" in flags) is (path not in NO_ENVELOPE), path

    def test_the_root_group_hands_the_envelope_to_subgroups(self):
        groups = [c for c in main.commands.values() if isinstance(c, click.Group)]
        assert groups and all(isinstance(g, MisataGroup) for g in groups)


class TestRealCommands:
    def test_generate_reports_its_tables(self, runner, schemas, tmp_path):
        good, _ = schemas
        out = tmp_path / "out"
        result = runner.invoke(main, ["generate", "-c", str(good), "-o", str(out), "--json"])
        envelope = _envelope(result)
        assert result.exit_code == EXIT_OK and envelope["code"] == "ok"
        assert envelope["data"]["tables"]["a"]["rows"] == 20
        assert Path(envelope["data"]["tables"]["a"]["files"][0]).is_file()

    def test_generate_refuses_with_exit_3_and_writes_nothing(self, runner, schemas, tmp_path):
        _, bad = schemas
        out = tmp_path / "out"
        result = runner.invoke(main, ["generate", "-c", str(bad), "-o", str(out), "--json"])
        envelope = _envelope(result)
        assert result.exit_code == EXIT_REFUSED and envelope["code"] == "infeasible"
        assert envelope["conflicts"][0]["kind"] == "unique_range_too_narrow"
        assert envelope["hint"]
        assert not list(out.glob("*.csv"))

    def test_people_get_the_conflict_on_stderr_and_no_traceback(self, runner, schemas, tmp_path):
        _, bad = schemas
        result = runner.invoke(main, ["generate", "-c", str(bad), "-o", str(tmp_path / "o")])
        assert result.exit_code == EXIT_REFUSED
        assert "raise max to at least 10" in result.stderr
        assert "Traceback" not in result.output

    def test_bad_option_is_a_usage_envelope(self, runner, schemas):
        good, _ = schemas
        result = runner.invoke(main, ["explain", str(good), "--json", "--no-such-flag"])
        envelope = _envelope(result)
        assert result.exit_code == EXIT_USAGE and "no-such-flag" in envelope["message"]

    def test_environment_variable_turns_it_on(self, runner, schemas):
        good, _ = schemas
        result = runner.invoke(main, ["explain", str(good)], env={"MISATA_JSON": "1"})
        assert _envelope(result)["data"]["explanation"]["will_generate"] is True

    def test_explain_refusal_carries_the_plan_and_the_conflicts(self, runner, schemas):
        _, bad = schemas
        result = runner.invoke(main, ["explain", str(bad), "--json"])
        envelope = _envelope(result)
        assert result.exit_code == EXIT_REFUSED
        assert envelope["data"]["explanation"]["will_generate"] is False
        assert envelope["conflicts"] == envelope["data"]["explanation"]["conflicts"]

    def test_missing_input_is_usage_with_a_message(self, runner, tmp_path):
        result = runner.invoke(main, ["audit", str(tmp_path), "--json"])
        envelope = _envelope(result)
        assert result.exit_code == EXIT_USAGE
        assert envelope["message"] == f"No CSV files found in {tmp_path}"

    @pytest.mark.parametrize("fmt", ["jsonl", "parquet", "duckdb"])
    def test_generate_writes_each_format_and_attests_it(self, runner, schemas, tmp_path, fmt):
        pytest.importorskip("pyarrow")
        good, _ = schemas
        out = tmp_path / fmt
        result = runner.invoke(main, ["generate", "-c", str(good), "-o", str(out),
                                      "--format", fmt, "--attest", "--json"])
        envelope = _envelope(result)
        assert result.exit_code == EXIT_OK, envelope["message"]
        assert envelope["data"]["format"] == fmt
        assert envelope["data"]["attestation"]["result"] == "PASSED"

    def test_partition_by_needs_parquet(self, runner, schemas, tmp_path):
        good, _ = schemas
        result = runner.invoke(main, ["generate", "-c", str(good), "-o", str(tmp_path / "o"),
                                      "--partition-by", "code", "--json"])
        envelope = _envelope(result)
        assert result.exit_code == EXIT_USAGE
        assert envelope["message"] == "--partition-by needs --format parquet"

    def test_lint_reports_findings(self, runner, schemas):
        _, bad = schemas
        result = runner.invoke(main, ["lint", str(bad), "--json"])
        envelope = _envelope(result)
        assert result.exit_code == EXIT_FAILED
        assert any(f["severity"] == "error" for f in envelope["data"]["findings"])


@click.group(cls=MisataGroup)
def toy() -> None:
    """A group for exercising the envelope in isolation."""


@toy.command()
def ok() -> None:
    click.echo("for people")
    emit(answer=42)


@toy.command()
def warns() -> None:
    for _ in range(3):
        warnings.warn("declaration bent", ConformanceWarning, stacklevel=1)


@toy.command()
def refuses() -> None:
    fail("input was unreadable", EXIT_USAGE)


@toy.command()
def crashes() -> None:
    raise KeyError("lost")


@toy.command()
def exits_with_text() -> None:
    raise SystemExit("stopped for a reason")


@toy.command(json_output=False)
def protocol() -> None:
    click.echo("raw")


class TestEnvelopeContract:
    def test_stdout_is_one_document_and_text_keeps_the_human_output(self, runner):
        result = runner.invoke(toy, ["ok", "--json"])
        envelope = _envelope(result)
        assert envelope["data"] == {"answer": 42}
        assert envelope["text"] == "for people"
        assert envelope["command"] == "toy ok"

    def test_warnings_are_collected_once_each(self, runner):
        envelope = _envelope(runner.invoke(toy, ["warns", "--json"]))
        assert envelope["warnings"] == [{"category": "ConformanceWarning",
                                         "message": "declaration bent"}]

    def test_fail_sets_the_message_and_the_code(self, runner):
        result = runner.invoke(toy, ["refuses", "--json"])
        envelope = _envelope(result)
        assert (result.exit_code, envelope["code"]) == (EXIT_USAGE, "usage")
        assert envelope["message"] == "input was unreadable"

    def test_fail_for_people_goes_to_stderr(self, runner):
        result = runner.invoke(toy, ["refuses"])
        assert result.exit_code == EXIT_USAGE
        assert result.stdout == "" and "input was unreadable" in result.stderr

    def test_an_unexpected_error_names_its_type(self, runner):
        result = runner.invoke(toy, ["crashes", "--json"])
        envelope = _envelope(result)
        assert result.exit_code == EXIT_FAILED
        assert envelope["message"] == "KeyError: 'lost'"

    def test_system_exit_with_text_is_a_failure_with_that_message(self, runner):
        envelope = _envelope(runner.invoke(toy, ["exits-with-text", "--json"]))
        assert envelope["exit_code"] == EXIT_FAILED
        assert envelope["message"] == "stopped for a reason"

    def test_opted_out_command_ignores_the_environment(self, runner):
        result = runner.invoke(toy, ["protocol"], env={"MISATA_JSON": "1"})
        assert result.stdout == "raw\n"
