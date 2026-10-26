# Use cases

Twelve recipes, each a folder with the schema, the commands, and the check
that proves the declaration held. Every command on every page runs on each
release (`tools/stranger.py`), so the numbers on the pages are what you
will see.

| Recipe | For | What you get | Proof |
|---|---|---|---|
| [Seed a dev database](seed-a-dev-database/) | app developers, coding agents | a database filled straight from its DDL | 22 invariants from the DDL alone |
| [Known-answer tests for dbt](dbt-known-answer-tests/) | analytics engineers | seeds whose correct model output is declared first | a dbt test that catches the last-day bug |
| [A warehouse before users](warehouse-before-users/) | founders, data leads | 291,000 rows of partitioned Parquet with declared revenue | 80 invariants |
| [A demo tenant](demo-tenant/) | sales engineers, PMs | churned and healthy accounts, a few whales, a story | realism 0.96, audit clean |
| [An eval database](eval-database/) | AI labs, eval teams | text-to-SQL questions with answers verified on three databases | near-miss study in the manifest |
| [An agent sandbox](agent-sandbox/) | agent builders | a SQLite sandbox over MCP and a grader for the agent's SQL | the sandbox and the grader agree row for row |
| [Load testing](load-testing/) | platform engineers | millions of requests with hot keys and a daily curve | keys checked before replay; 10M rows in 36 s |
| [Fraud and AML](fraud-aml/) | risk and ML teams | a transfer network where every ring was declared | acyclic background and exact motif counts, by SQL |
| [Ledgers that reconcile](ledgers-that-reconcile/) | finance engineering, audit | two fiscal years of balanced books and an AR roll-forward | 52 invariants, trial balance zero |
| [Take-home exercises](take-home-exercises/) | hiring teams, course authors | the same questions with a different answer key per candidate | every key verified before it ships |
| [PII-free environments](pii-free-environments/) | regulated teams | staging data from production DDL, never production rows | provenance plus a byte-for-byte regeneration |
| [Example data for docs](example-data-for-docs/) | DX, API and SDK teams | nested JSON fixtures with ids that resolve across files | 9 invariants, and the same data in pytest |
