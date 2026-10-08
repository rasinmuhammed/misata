# Where to submit the skill

Ordered by what it costs you against what it plausibly returns. The numbers were
measured on 3 Aug 2026, not recalled.

---

## 1. Your own repo. Already live, no gatekeeper.

`.claude-plugin/marketplace.json` is in the repository and points at `plugin/`, so anyone can run:

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

## 2. The Claude directory. Do this one.

Anthropic opened a submission portal on 25 Sep 2026 at
https://claude.ai/directory/manage. Any Pro or Max account can submit; no partner
programme. A listing shows in Claude Code, Claude Desktop and claude.ai, and the
portal shows installs and usage afterwards. Two submissions, from the same account:

**a. MCP connector.** Submit new > MCP connector.

- URL: `https://api.misata.studio/mcp` (Streamable HTTP, OAuth through the Studio
  sign-in; schema builds work without signing in).
- Test credentials: a Studio account that already holds a few datasets
  (reviewers want a "fully populated account").
- Public docs: https://www.misata.studio/mcp
- Allowed link URIs: `https://www.misata.studio`, `https://api.misata.studio`
  (export download links).
- Before submitting, add it as a custom connector in Claude and call every tool
  once; the portal asks you to confirm that.

Connectors are scanned automatically and listed as Community; Anthropic may
escalate to Verified on its own.

**b. Plugin bundle.** Submit new > Plugin bundle.

- Repository: `rasinmuhammed/misata`, plugin path `plugin`, branch `main`.
- Press Validate; `claude plugin validate ./plugin` passes locally and
  `tests/test_skill.py` checks the directory's blocking rules.
- Then pair it with the connector listing above (same account).

A person reviews a new plugin before it goes live. Desktop extensions (`mcpb/`)
are no longer accepted by the directory; the plugin replaces them there.

anthropics/skills (the GitHub repo) is still not worth a pull request: most
third-party PRs close unmerged.

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
`plugin/skills/misata/SKILL.md` against the running package, and checks that every skill path in
`marketplace.json` resolves to a real directory. Run it before you submit
anywhere, because these listings are cached and a wrong command in a cached
description outlives the fix.
