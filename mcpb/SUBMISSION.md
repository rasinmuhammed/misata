# Connectors Directory submission dossier

**For the desktop extension, use [FORM.md](FORM.md).** The real form is six
fields and this document is far longer than it needs. Keep this one: it holds
the long-form copy the REMOTE server submission asks for, which is a separate
listing at `api.misata.studio/mcp` and needs a Team or Enterprise organisation.

Everything the submission asks for, drafted and ready to paste. Answer copy is
final; the one blocker at the bottom is yours.

Sources for the requirements:
[submission guide](https://claude.com/docs/connectors/building/submission),
[directory FAQ](https://support.claude.com/en/articles/11596036-anthropic-connectors-directory-faq).

---

## Which path to take

There are two, and they have different entry costs.

| | Remote MCP server | Desktop extension (MCPB) |
| --- | --- | --- |
| Where | `claude.ai/admin-settings/directory/submissions/new` | [desktop extension form](https://clau.de/desktop-extention-submission) |
| Needs a Team/Enterprise org | **yes** | no |
| What is listed | `https://api.misata.studio/mcp` | the bundled local server |
| Ready today | yes, if you have the org | yes |

**Recommendation: submit the desktop extension first.** It needs no paid
organisation, the local server is the better product anyway (your database
credentials never leave your machine), and it gets Misata into the catalogue
while the remote listing waits on a Team plan. Nothing stops you submitting the
remote server later; they are separate listings.

---

## Listing copy

**Server name** (max 100)

```
Misata
```

**Tagline** (max 55 characters, this one is 54)

```
Realistic test data whose joins and totals hold up
```

**Description** (max 2,000)

```
Misata generates realistic multi-table test data from a description, and
guarantees the things that usually break.

Most sample data falls apart on the second join: keys point at rows that do not
exist, child rows do not add up to their parent's total, and a status column
says "delivered" on an order with no shipment date. Misata is declarative. You
state what must be true of the data, the engine solves for rows that satisfy it,
and an independent verifier proves it held before you ever see it.

Things you can declare and have hold exactly:

- exact totals per period, and exact shares across groups
- parent aggregates that reconcile with their child rows, through several joins
- ledgers that balance to the cent
- a status that implies a legal, ordered, fully timestamped history
- foreign keys that may never cross a tenant boundary
- an exact number of duplicates or outliers, so deduplication and anomaly
  detection have something real to find

Nothing is sampled from real data and no model is fitted on it, so there is no
personal information in the output and nothing to anonymise. Generation is
seeded: the same schema and the same seed produce identical bytes, which makes
the data safe to commit and diff.

Ask for a dataset in plain English and see how it was understood before anything
is generated. Point it at a development database and it will show you the plan
before it writes a row.

The engine is open source (MIT) and its guarantees are tested by three
conformance suites totalling 284 SQL assertions, executed by DuckDB, which
shares no code with the generator.
```

**Categories** (pick one to five)

```
Developer Tools
Data & Analytics
Productivity
```

**Documentation URL** — `https://www.misata.studio/docs`
**Privacy policy URL** — `https://www.misata.studio/privacy`
**Support contact** — `rasinbinabdulla@gmail.com`
**URL slug** (permanent once published) — `misata`

**Icon** — `mcpb/icon.png`, the studio's own mark: 1024x1024, PNG, genuinely
transparent background. One thing to weigh: the strokes are dark, so it reads
well on a light card and loses contrast on a dark one. If you would rather it
held up in both, the fix is the mark on its own solid rounded tile, and that is
a design call rather than a packaging one. Replace the file and re-run
`python mcpb/pack.py`.

---

## Use cases

**Primary use cases**

```
Seeding a development or staging database with data that behaves like
production without containing anyone's real information.

Producing fixtures for tests where the assertions depend on the data being
internally consistent, not merely present.

Building a demo or a portfolio dataset that survives a reviewer running
arbitrary joins and group-bys against it.

Generating an evaluation set with a known answer key, so an analytics pipeline
or a SQL agent can be scored rather than eyeballed.
```

**What a user needs before connecting**

```
Python 3.10 or newer, and `pip install "misata[mcp]"`. No account, no API key and no
signup. To use the AI schema-design step you supply your own LLM API key; every
other tool works without one.
```

**Does the connector read data, write data, or both** — **Both.** Six tools read
and compute. `seed_database` writes, and only into a database the user names.

---

## Authentication

**Mode: no authentication.** The desktop extension runs locally over stdio.
There is no Misata account, no OAuth flow and no API key. The user's database
credentials are passed to `seed_database` at call time and go straight to their
own database.

If you later submit the remote server at `https://api.misata.studio/mcp`, that
one is also currently unauthenticated, with per-IP rate limits.

---

## Data handling

- **Is the underlying API your own?** Yes. Misata is our own software; the
  extension runs it locally.
- **Personal health data?** No. The engine never ingests real data of any kind.
- **Sponsored content?** No.
- **Conversation data collection?** None. The package contains no telemetry,
  analytics or crash reporting.

---

## Tool annotations

Shipped in 0.9.6 and verified by `tests/test_mcp_server.py`. Every tool declares
a title and an honest hint:

| tool | readOnlyHint | destructiveHint |
| --- | --- | --- |
| `list_domains` | true | false |
| `preview_story` | true | false |
| `inspect_schema` | true | false |
| `generate_dataset` | true | false |
| `generate_from_schema` | true | false |
| `validate_yaml` | true | false |
| `seed_database` | **false** | **true** |

`seed_database` is marked destructive deliberately. It inserts into a database
the user points it at and can be asked to truncate existing tables, so a client
that trusted a softer hint would be trusting the wrong thing. It plans by
default and applies only on an explicit second call.

---

## Test instructions for the reviewer

```
No account or credentials are needed. The extension runs entirely locally.

Setup:
  1. Python 3.10 or newer must be available.
  2. pip install "misata[mcp]"
  3. Install the extension. It launches `misata-mcp` over stdio.

To exercise the read-only tools, ask Claude:

  "List the domains Misata can generate."
      -> list_domains

  "Show me how Misata would interpret: a B2B SaaS company with 1,200
   accounts, seats that fit the plan, and 8% monthly churn."
      -> preview_story, then inspect_schema

  "Now generate it, 1,200 accounts, and show me the integrity report."
      -> generate_dataset or generate_from_schema. The response includes a
         per-relationship orphan count; every one should read 0.

  "Will this generate?

     name: shares
     tables:
       orders:
         rows: 100
         columns:
           order_id: {type: int, unique: true}
           segment: {type: categorical, choices: [a, b, c]}
           revenue: {type: float, min: 10, max: 500}
     group_shares:
       - table: orders
         measure: revenue
         group_column: segment
         shares: {a: 0.6, b: 0.6, c: 0.3}"

      -> validate_yaml. It should REFUSE at stage "feasibility" and show the
         arithmetic: the shares sum to 1.500, and a share of a whole cannot
         exceed 1.0. It also says what to change. Refusing an impossible
         declaration rather than quietly renormalising it into a spec the user
         did not write is the intended behaviour and the thing worth seeing.

To exercise the one writing tool without a database, ask:

  "Plan how you would seed postgres://localhost:5432/nonexistent."
      -> seed_database returns a PLAN and writes nothing. It only applies when
         called again with apply=true. If you would rather see it write, any
         local Postgres or SQLite database works; it creates nothing it was not
         asked to.
```

---

## Compliance acknowledgements

Seven are required, all straightforward here:

1. **Directory guidelines** — agreed.
2. **First-party API usage** — the extension runs our own open-source software
   locally; no third-party API is proxied.
3. **Financial transactions** — none. The extension takes no payments.
4. **AI media generation** — none. Output is tabular data generated from rules,
   not model output.
5. **Prompt injection** — the tools accept a schema or a description and return
   data. They do not fetch or execute untrusted remote content. `seed_database`
   is the only side-effecting tool and it plans before it writes.
6. **Conversation data collection** — none.
7. **Public documentation** — `https://www.misata.studio/docs`.

---

## Still blocked on you

1. **Read the privacy policy.** It is live at
   `https://www.misata.studio/privacy`, source in the studio repo at
   `apps/web/src/app/(marketing)/privacy/page.tsx`. **Read it.** It describes your data handling
   It describes your data handling and it is the one document here that carries
   legal weight, so it should say what you mean rather than what I inferred from
   the code. Anthropic's own wording: *"Missing or incomplete privacy policies
   result in immediate rejection."*

2. **Decide the path.** Desktop extension needs neither an org nor a paid plan.
   The remote listing needs a Team or Enterprise organisation.

Nothing else is outstanding. Review times are not published; community reports
range from about two weeks to several months.
