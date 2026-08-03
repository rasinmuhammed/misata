# Agent Skills

`misata/SKILL.md` teaches an agent to use Misata well: which entry point fits
which request, what is worth declaring, and when to refuse rather than guess.

Install it into Claude Code, Codex, or anything else that reads `SKILL.md`:

```bash
mkdir -p ~/.claude/skills
cp -r skills/misata ~/.claude/skills/
```

## Keeping it true

The skill names commands and declaration keys, so it can drift into describing a
tool that no longer exists. `tests/test_skill.py` checks every command and every
top-level key it mentions against the running package.

That test was written after the first draft, which claimed `misata generate
--from-project` (the flag lives on `dbt-seed`) and a top-level `rollups:` key
(roll-ups are inferred from the shape, never declared). Both read perfectly
plausibly. Neither existed.

## Directories

Submission is a name, a description and this repository's URL:

- https://lobehub.com/skills
- https://mcpmarket.com/tools/skills
- https://skillsmp.com/
- https://claudeskills.info/

Copy for those forms is in `mcpb/FORM.md`, which the desktop extension uses too.
