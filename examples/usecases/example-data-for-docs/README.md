---
title: Example Data for Docs, SDK Tests and Mock APIs
description: Generate small, believable JSON fixtures for API docs, SDK tests and mock servers, with nested objects, ids that resolve across files, no cross-tenant references, and the same data available to pytest without files.
---

# Example data for docs, SDK tests and mock APIs

Docs examples and SDK fixtures are usually typed by hand: `user_123`,
`foo@example.com`, a task assigned to a user who does not exist. Readers
copy them, tests pass against them, and the first real payload breaks
something. Declare the resources once and every example, fixture and mock
response comes from the same consistent set.

**Who:** developer experience, API and SDK teams; anyone writing a
quickstart.
**Time:** well under a second.

## The resources

A tasks API: workspaces, their users, and tasks assigned to users.

```yaml
# misata.yaml
name: tasks_api
seed: 5
tables:
  workspaces:
    rows: 12
    columns:
      workspace_id: {type: int, unique: true, min: 1, max: 12}
      name: {type: text, semantic: company_name}
      plan: {type: categorical, choices: [free, team, business], probabilities: [0.5, 0.35, 0.15]}
  users:
    rows: 60
    columns:
      user_id: {type: int, unique: true, min: 1, max: 60}
      workspace_id: {type: foreign_key}
      email: {type: text, semantic: email}
      profile:
        type: json
        fields:
          full_name: text
          timezone: {type: string, enum: [Europe/London, America/New_York, Asia/Kolkata, Australia/Sydney]}
          notifications: {type: json, fields: {email: boolean, push: boolean}}
        optional: [notifications]
        optional_rate: 0.2
  tasks:
    rows: 400
    columns:
      task_id: {type: int, unique: true, min: 1, max: 400}
      workspace_id: {type: foreign_key}
      assignee_id: {type: foreign_key}
      status: {type: categorical, choices: [todo, in_progress, done], probabilities: [0.35, 0.25, 0.4]}
      labels: {type: array, items: {type: string, enum: [bug, feature, docs, urgent, design]}, max_items: 3, unique_items: true}
      created_at: {type: datetime, start: "2025-09-01", end: "2025-10-31"}
relationships:
  - workspaces.workspace_id -> users.workspace_id
  - workspaces.workspace_id -> tasks.workspace_id
  - {parent: users.user_id, child: tasks.assignee_id, partition_by: [workspace_id]}
```

- `profile` is a nested object and `labels` an array, the shapes an API
  returns. 20% of profiles leave out `notifications`, the way optional
  fields are missing in real payloads.
- `partition_by: [workspace_id]` keeps every assignee inside the task's own
  workspace. Without it, most tasks would point at a user from another
  tenant, which no real API would return.

## Write the fixtures

```bash
misata generate -c misata.yaml -o fixtures --format jsonl --attest
```

```text
{"user_id":47,"workspace_id":4,"email":"aiyer@outlook.com","profile":{"full_name":"Aarti Iyer","timezone":"Europe/London","notifications":{"email":true,"push":true}}}
{"task_id":392,"workspace_id":4,"assignee_id":50,"status":"done","labels":["design"],"created_at":"2025-09-30T10:08:21"}
```

One file per resource, one object per line, nested values as objects and
lists. Point a mock server at them, paste a line into the docs, or load
them as SDK test fixtures: every `workspace_id` and `assignee_id` resolves.

## The check

```bash
python fixtures/verify.py
```

```text
ok    3 file(s) match their attested sha256
ok    9 of 9 invariant(s) hold
```

The nine are the three keys resolving, the assignee's workspace matching
the task's (`partition_by`), three ids unique, and `plan` and `status`
holding only declared values. Commit the fixtures with their attestation,
and a reviewer can see in the diff whether a regenerated set still holds.

## The same data in pytest, without files

With Misata installed, its pytest plugin generates the declared data once
per session. `test_tasks_api.py` in this folder uses both fixtures:

```python
pytestmark = pytest.mark.misata(schema="misata.yaml")

def test_open_tasks_leave_out_finished_work(misata_sqlite):
    tasks = open_tasks(misata_sqlite, workspace_id=2)   # the code under test
    assert all(status in ("todo", "in_progress") for _, status in tasks)

def test_every_assignee_works_in_the_task_workspace(misata_tables):
    workspace_of = misata_tables["users"].set_index("user_id")["workspace_id"]
    tasks = misata_tables["tasks"]
    assert (tasks["assignee_id"].map(workspace_of) == tasks["workspace_id"]).all()
```

```bash
pytest test_tasks_api.py
```

`misata_tables` hands each test its own copy of the frames, and
`misata_sqlite` a fresh SQLite database seeded with the same rows. A
relative schema path is found beside the test file.
