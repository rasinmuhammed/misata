---
title: "Ways to Generate Synthetic Data: Story, YAML, Database, Dict, LLM"
description: "Six ways to describe the data Misata generates: a plain-English story, a YAML schema, an existing database, a Python dict, an LLM-designed schema, or incremental growth of a dataset."
---

# Generation Methods

Misata supports six ways to get data, choose the one that fits your workflow.

| Method | Best for | API key needed? |
|:--|:--|:--:|
| [Plain English](story.md) | Prototyping, demos, one-offs | No |
| [YAML schema](yaml.md) | Repeatable, team-shared schemas in git | No |
| [From a database](database.md) | Seeding a real app's dev/staging DB | No |
| [Python dict](dict.md) | Programmatic schema from existing code | No |
| [LLM-assisted](llm.md) | Complex domains with rich semantics | Yes |
| [Incremental](incremental.md) | Growing a dataset without re-seeding | No |
