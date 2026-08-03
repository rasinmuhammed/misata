# Misata for Claude Desktop

Generate realistic multi-table test data by asking for it, with foreign keys
that resolve and totals that reconcile.

Ask Claude for "a year of orders for an ecommerce store, about 2,000 customers,
with a Q4 peak" and you get five joined tables where every key points at a row
that exists and every order total is exactly the sum of its own line items.
Ask it to seed your local Postgres and it will show you the plan first.

## What makes it different from a faker script

Most test data falls apart on the second join. Misata is **declarative**: you
state what must be true of the data, the engine solves for rows that satisfy it,
and an independent verifier proves it held. Things you can declare and have
guaranteed exactly:

- exact totals per period, and exact shares across groups
- parent aggregates that reconcile with child rows, through several joins
- ledgers that balance to the cent
- a status that implies a legal, ordered, fully timestamped history
- keys that may never cross a tenant boundary
- an exact number of duplicates or outliers, so dedupe and anomaly logic have
  something real to find

Nothing is sampled from real data and no model is fitted, so there is no
personal information in the output and nothing to anonymise.

## Tools

| tool | what it does | writes anything? |
| --- | --- | --- |
| `list_domains` | lists the built-in domains | no |
| `preview_story` | shows how your description was understood | no |
| `inspect_schema` | returns the tables and relationships implied | no |
| `generate_dataset` | generates from a sentence | no |
| `generate_from_schema` | generates from an explicit schema, with an integrity report | no |
| `validate_yaml` | refuses declarations that cannot all hold, with the arithmetic | no |
| `seed_database` | inserts rows into a database you point it at | **yes** |

`seed_database` is the only tool that writes anything anywhere. It plans by
default and applies only when you explicitly tell it to, and it never truncates
a table unless you ask.

## Example prompts

- "Show me what a SaaS company with 1,200 accounts and 8% monthly churn would
  look like as tables, before you generate it."
- "Generate an ecommerce dataset: 2,000 customers, a 300-product catalogue,
  a year of orders with a Q4 peak, and order totals that reconcile to the cent."
- "I have a Postgres database at postgres://localhost:5432/dev. Plan how you
  would seed it with realistic data matching its existing schema."
- "Here is my misata.yaml. Are any of these declarations impossible together?"
- "Generate 50,000 support tickets where resolved tickets always have a
  resolution timestamp and open ones never do."

## Requirements

- Python 3.10 or newer on your machine
- `pip install misata`

The extension runs `misata-mcp`, which is installed with the package.

## Privacy Policy

**The software sends us nothing.** There is no telemetry, no analytics and no
crash reporting in the Misata package or in this MCP server. Installing and
running it produces no network traffic to us, and we have no way of knowing you
are using it.

Three things reach the network, and each is something you ask for:

1. **Seeding a database.** `seed_database` connects to the database you name,
   using the connection string you supply. That connection is between your
   machine and your database. The connection string and the data never leave
   your machine.
2. **Vocabulary enrichment**, if you enable it, fetches public reference lists
   from Wikidata to make generated values more realistic. It sends a category
   name and nothing about your schema or your data.
3. **AI schema design**, if you supply your own LLM API key, sends your prompt
   text to that provider under your own account and their terms. This is off by
   default. No key, no request.

Generated data stays on your machine. It is written where you tell it to be
written and nowhere else.

Full policy, including how the misata.studio website is handled:
**https://www.misata.studio/privacy**

Questions, corrections, or a data request: rasinbinabdulla@gmail.com

## Links

- Documentation: https://www.misata.studio/docs
- How the guarantees are tested: https://www.misata.studio/gauntlet
- Source and issues: https://github.com/rasinmuhammed/misata
- Licence: MIT
