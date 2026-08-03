"""The agent skill has to describe the tool that exists.

`skills/misata/SKILL.md` names CLI commands and declaration keys. An agent reads
it and acts on it directly, so a wrong name there is worse than no skill at all:
the agent runs a command that does not exist and reports the failure as Misata
being broken.

The first draft of that file claimed `misata generate --from-project` (the flag
lives on `dbt-seed`) and a top-level `rollups:` key (roll-ups are inferred from
the shape and never declared). Both read as entirely plausible. Neither existed.
Hence checking the text against the running package rather than re-reading it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "skills" / "misata" / "SKILL.md"


def skill_text() -> str:
    return SKILL.read_text()


class TestFrontmatter:
    def test_it_has_a_name_and_a_description(self):
        text = skill_text()
        assert text.startswith("---\n"), "SKILL.md needs YAML frontmatter"
        front = text.split("---")[1]
        assert re.search(r"^name:\s*misata\s*$", front, re.M)
        assert re.search(r"^description:\s*\S", front, re.M)

    def test_the_description_says_when_to_use_it(self):
        """Directories rank on this, and agents trigger on it."""
        front = skill_text().split("---")[1]
        description = re.search(r"^description:\s*(.+)$", front, re.M).group(1)
        assert len(description) > 80, "too thin to trigger on"
        assert "test data" in description.lower()


class TestEveryCommandExists:
    def _registered(self) -> set:
        from misata.cli import main
        return set(main.commands)

    def test_named_commands_are_real(self):
        text = skill_text()
        named = set(re.findall(r"`misata ([a-z][a-z-]*)", text))
        named.discard("yaml")  # `misata.yaml`, not a command
        missing = sorted(named - self._registered())
        assert not missing, (
            f"SKILL.md tells an agent to run commands that do not exist: {missing}. "
            f"Real ones: {sorted(self._registered())}")

    def test_the_flag_is_documented_on_the_right_command(self):
        """`--from-project` was documented on `generate`. It is on `dbt-seed`,
        so an agent following the skill got "no such option" and reported
        Misata as broken."""
        assert re.search(r"`misata dbt-seed --from-project", skill_text())
        assert not re.search(r"`misata generate --from-project", skill_text())

    @pytest.mark.parametrize("command,flag", [
        ("generate", "--config"),
        ("generate", "--story"),
        ("generate", "--output-dir"),
        ("seed", "--dry-run"),
        ("seed", "--truncate"),
        ("seed", "--append"),
        ("dbt-seed", "--from-project"),
    ])
    def test_named_flags_are_real(self, command, flag):
        """`--from-project` was documented on the wrong command."""
        from misata.cli import main
        params = {opt for p in main.commands[command].params for opt in p.opts}
        assert flag in params, f"`misata {command} {flag}` does not exist"


class TestEveryDeclarationExists:
    def test_top_level_keys_are_real(self):
        """The skill lists these as top-level keys in misata.yaml."""
        from misata.schema import SchemaConfig

        claimed = {
            "outcome_curves", "group_shares", "waterfalls", "stock_flows",
            "lifecycles", "duplicates", "outliers", "typos", "missingness",
            "retention", "late_arrivals", "time_grids", "event_logs",
            "bitemporal", "dag_edges", "closures", "seed",
        }
        text = skill_text()
        for key in claimed:
            assert f"`{key}`" in text, f"test claims the skill documents {key}"

        missing = sorted(claimed - set(SchemaConfig.model_fields))
        assert not missing, f"documented as top-level but is not: {missing}"

    def test_partition_by_is_on_a_relationship(self):
        """It is a relationship field. The skill has to say so, because an
        agent that writes it at the top level gets a schema that silently
        ignores the isolation it asked for."""
        from misata.schema import Relationship, SchemaConfig

        assert "partition_by" in Relationship.model_fields
        assert "partition_by" not in SchemaConfig.model_fields
        assert re.search(r"`partition_by`.{0,80}relationship", skill_text(), re.S)

    def test_rollups_are_not_claimed_as_a_declaration(self):
        """They are inferred from the shape. Saying otherwise sends an agent
        looking for a key that has never existed."""
        from misata.schema import SchemaConfig

        assert "rollups" not in SchemaConfig.model_fields
        assert "`rollups`" not in skill_text()
        assert "inferred" in skill_text()


class TestSafetyInstructions:
    def test_it_forbids_unprompted_truncation(self):
        """`--truncate` destroys data. An agent must not reach for it alone."""
        text = skill_text()
        assert "--truncate" in text
        assert re.search(r"[Nn]ever pass `--truncate`", text)

    def test_it_requires_a_dry_run_before_seeding(self):
        assert re.search(r"`--dry-run` first", skill_text())
