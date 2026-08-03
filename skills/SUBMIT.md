# Where to submit the skill

Ordered by what it costs you against what it plausibly returns. The numbers were
measured on 3 Aug 2026, not recalled.

---

## 1. Your own repo. Already live, no gatekeeper.

`.claude-plugin/marketplace.json` is in the repository, so anyone can run:

```
/plugin marketplace add rasinmuhammed/misata
```

```
/plugin install misata@misata
```

This is the whole mechanism. `/plugin marketplace add` reads that file from any
public GitHub repo, which means you are already distributing. No review, no
queue, and the install line works the moment the commit lands.

Put those two lines in the main README. That is the highest-value edit available
here, because every other destination on this page ultimately just points people
back at your repo.

---

## 2. anthropics/skills. Do not bother yet.

The official repo, 166,000 stars, and the obvious place to want to be. The data
says otherwise:

- **750 open pull requests.**
- Of the **last 100 closed PRs, 18 were merged and 82 were closed unmerged.**
- Of those 18 merges, **14 came from one author**, and the rest are
  Anthropic-affiliated accounts.

So the realistic outcome for a third-party tool skill is a long wait followed by
a close. The repo reads as Anthropic's own examples rather than a community
index, and there is no `CONTRIBUTING.md` inviting otherwise.

Worth revisiting if that changes. Not worth an afternoon today.

---

## 3. The aggregator directories. Cheap, so do them.

Each takes a name, a description and a repository URL. Fifteen minutes for all
four. They exist to be indexed, which is the point: these are the third-party
pages an answer engine cites when someone asks how to generate test data.

- https://claudemarketplaces.com/ (reports 380,000 developer visits a month)
- https://lobehub.com/skills
- https://mcpmarket.com/tools/skills
- https://skillsmp.com/

**Set expectations honestly.** I have not verified traffic claims beyond what
each site states about itself, and directory listings are a slow burn, not a
launch. The reason to do them is cumulative citation, not a spike.

---

## What to paste

**Name:** `misata`

**Repository:** `https://github.com/rasinmuhammed/misata`

**Description** (the skill's own frontmatter, which is what agents trigger on):

```
Generate realistic multi-table test data, seed a development database, or build
fixtures whose joins and totals actually hold. Use when the user needs test data,
sample data, demo data, seed data, fixtures, a populated dev/staging database, or
a relational dataset shaped to specific numbers (a revenue curve, a churn rate,
exact monthly totals). Also use when asked to fill an existing Postgres or SQLite
database from its own schema.
```

**Requirement to state wherever there is a field for it:** `pip install misata`.
The skill drives a Python CLI. Someone who installs the plugin and nothing else
gets an agent confidently running a command that is not on their machine.

---

## Keeping it honest

`tests/test_skill.py` checks every command, flag and declaration key in
`SKILL.md` against the running package, and checks that every skill path in
`marketplace.json` resolves to a real directory. Run it before you submit
anywhere, because these listings are cached and a wrong command in a cached
description outlives the fix.
