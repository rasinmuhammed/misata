"""The Warren: a second conformance suite, deliberately the wrong shape.

The Gauntlet reached 126/126, and a suite at 100% has stopped being able to
find anything. It is also one shape: a flat-ish e-commerce star with a junction
table. Everything the engine learned, it learned from that shape.

This suite is built to be awkward in the ways the Gauntlet is not:

  * **Multi-tenant.** Every table carries a tenant, and *nothing may reference
    across tenants*. This is the exact class of defect found in
    `fivetran/dbt_stripe` (a window with no `partition by`): correct-looking on
    single-tenant data, silently wrong the moment a second tenant exists.
  * **Self-referential hierarchy.** Orgs nest into orgs, arbitrary depth. No
    cycles, no self-parents, roots have no parent.
  * **Event-sourced.** Task state is not stored independently, it is whatever
    the task's own event log implies. Sequences must be contiguous and
    timestamps must ascend with them.
  * **Two-hop money.** Invoice totals reconcile to lines, and lines reconcile
    to logged time.

Written assertions-first, as `FOCUS.md` §7 requires, and the reds are the point:
an assertion here that fails names something the language cannot yet say.

Run:
    python -m benchmarks.warren
    python -m benchmarks.warren --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from typing import Any, Dict, List, Tuple

import duckdb

import misata
from misata.schema import (SchemaConfig, Table, Column, Relationship,
                           Constraint, Lifecycle, LifecycleState, EventLog,
                           Outliers, Typos)

SEED = 19

# Assertions the engine is not expected to pass yet, each with the reason.
# Same contract as the Gauntlet: an unexpected failure fails the build, and so
# does a known-red that starts passing without being promoted out of here.
KNOWN_RED: Dict[str, str] = {}

TASK_STATES = "'open','in_progress','blocked','done','cancelled'"
EVENT_TYPES = "'created','started','blocked','unblocked','completed','cancelled'"


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #

def build_schema() -> SchemaConfig:
    return SchemaConfig(
        name="warren",
        seed=SEED,
        tables=[
            Table(name="tenants", row_count=6),
            Table(name="orgs", row_count=48),
            # A status gates its dependent column, declared rather than hoped
            # for. The first run of this suite failed both directions because
            # the schema simply did not say so.
            Table(name="users", row_count=600, constraints=[
                Constraint(name="deactivated_has_timestamp", type="when_then",
                           when_column="status", when_op="==",
                           when_value="deactivated",
                           then_column="deactivated_at", then="not_null"),
                Constraint(name="active_has_no_timestamp", type="when_then",
                           when_column="status", when_op="in",
                           when_value=["active", "invited"],
                           then_column="deactivated_at", then="null"),
            ]),
            Table(name="projects", row_count=240),
            Table(name="tasks", row_count=3000, constraints=[
                Constraint(name="estimate_under_cap", type="inequality",
                           column_a="estimate_hours", operator="<=",
                           column_b="cap_hours"),
            ]),
            Table(name="task_events", row_count=9000),
            Table(name="time_entries", row_count=6000),
            Table(name="invoices", row_count=360),
            Table(name="invoice_lines", row_count=1440),
            Table(name="audit_log", row_count=4000),
        ],
        columns={
            "tenants": [
                Column(name="tenant_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 6}),
                Column(name="plan", type="categorical",
                       distribution_params={
                           "choices": ["free", "team", "business", "enterprise"],
                           "probabilities": [0.2, 0.3, 0.3, 0.2]}),
                Column(name="region", type="categorical",
                       distribution_params={"choices": ["us", "eu", "apac"]}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2022-01-01",
                                            "end": "2022-06-30"}),
            ],
            "orgs": [
                Column(name="org_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 48}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
                # Self-referential: an org nests inside another org.
                Column(name="parent_org_id", type="foreign_key", nullable=True,
                       distribution_params={"references": "orgs.org_id",
                                            "null_rate": 0.25}),
                Column(name="org_name", type="text",
                       distribution_params={"pattern": "ORG-[A-Z]{3}"}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2022-02-01",
                                            "end": "2023-06-30"}),
            ],
            "users": [
                Column(name="user_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 600}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
                Column(name="org_id", type="foreign_key",
                       distribution_params={"references": "orgs.org_id"}),
                Column(name="signup_date", type="datetime",
                       distribution_params={"start": "2022-03-01",
                                            "end": "2025-01-31"}),
                Column(name="status", type="categorical",
                       distribution_params={
                           "choices": ["active", "invited", "deactivated"],
                           "probabilities": [0.7, 0.15, 0.15]}),
                Column(name="deactivated_at", type="datetime", nullable=True,
                       distribution_params={"start": "2022-04-01",
                                            "end": "2025-06-30",
                                            "null_rate": 0.85}),
            ],
            "projects": [
                Column(name="project_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 240}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
                Column(name="owner_user_id", type="foreign_key",
                       distribution_params={"references": "users.user_id"}),
                Column(name="started_at", type="datetime",
                       distribution_params={"start": "2022-06-01",
                                            "end": "2025-03-31"}),
                Column(name="billable", type="boolean",
                       distribution_params={"true_probability": 0.75}),
            ],
            "tasks": [
                Column(name="task_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 3000}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
                Column(name="project_id", type="foreign_key",
                       distribution_params={"references": "projects.project_id"}),
                Column(name="assignee_user_id", type="foreign_key", nullable=True,
                       distribution_params={"references": "users.user_id",
                                            "null_rate": 0.15}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2022-07-01",
                                            "end": "2025-05-31"}),
                Column(name="state", type="categorical",
                       distribution_params={
                           "choices": ["open", "in_progress", "blocked",
                                       "done", "cancelled"],
                           "probabilities": [0.2, 0.2, 0.1, 0.4, 0.1]}),
                Column(name="started_at", type="datetime", nullable=True,
                       distribution_params={"start": "2022-07-01",
                                            "end": "2025-06-30",
                                            "null_rate": 0.3}),
                Column(name="completed_at", type="datetime", nullable=True,
                       distribution_params={"start": "2022-07-01",
                                            "end": "2025-06-30",
                                            "null_rate": 0.6}),
                Column(name="cancelled_at", type="datetime", nullable=True,
                       distribution_params={"start": "2022-07-01",
                                            "end": "2025-06-30",
                                            "null_rate": 0.9}),
                Column(name="cap_hours", type="int",
                       distribution_params={"min": 8, "max": 80}),
                Column(name="estimate_hours", type="int",
                       distribution_params={"min": 1, "max": 40}),
            ],
            "task_events": [
                Column(name="event_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 9000}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
                Column(name="task_id", type="foreign_key",
                       distribution_params={"references": "tasks.task_id"}),
                Column(name="event_type", type="categorical",
                       distribution_params={
                           "choices": ["created", "started", "blocked",
                                       "unblocked", "completed", "cancelled"],
                           "probabilities": [0.34, 0.24, 0.08, 0.07, 0.22, 0.05]}),
                Column(name="occurred_at", type="datetime",
                       distribution_params={"start": "2022-07-01",
                                            "end": "2025-06-30"}),
                Column(name="actor_user_id", type="foreign_key",
                       distribution_params={"references": "users.user_id"}),
            ],
            "time_entries": [
                Column(name="entry_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 6000}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
                Column(name="task_id", type="foreign_key",
                       distribution_params={"references": "tasks.task_id"}),
                Column(name="user_id", type="foreign_key",
                       distribution_params={"references": "users.user_id"}),
                Column(name="entry_date", type="datetime",
                       distribution_params={"start": "2022-07-01",
                                            "end": "2025-06-30"}),
                Column(name="hours", type="float",
                       distribution_params={"distribution": "uniform",
                                            "min": 0.25, "max": 8.0}),
            ],
            "invoices": [
                Column(name="invoice_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 360}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
                Column(name="project_id", type="foreign_key",
                       distribution_params={"references": "projects.project_id"}),
                Column(name="issued_at", type="datetime",
                       distribution_params={"start": "2022-08-01",
                                            "end": "2025-06-30"}),
                Column(name="status", type="categorical",
                       distribution_params={"choices": ["draft", "sent", "paid"],
                                            "probabilities": [0.2, 0.3, 0.5]}),
                Column(name="paid_at", type="datetime", nullable=True,
                       distribution_params={"start": "2022-08-01",
                                            "end": "2025-07-31",
                                            "null_rate": 0.5}),
                # Two-hop money: reconciles with its own lines.
                Column(name="amount", type="float",
                       distribution_params={"rollup": {
                           "from_table": "invoice_lines", "fk": "invoice_id",
                           "agg": "sum", "column": "line_total"}}),
            ],
            "invoice_lines": [
                Column(name="line_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 1440}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
                Column(name="invoice_id", type="foreign_key",
                       distribution_params={"references": "invoices.invoice_id"}),
                Column(name="hours", type="float",
                       distribution_params={"distribution": "uniform",
                                            "min": 0.5, "max": 40.0}),
                Column(name="rate", type="float",
                       distribution_params={"distribution": "uniform",
                                            "min": 60.0, "max": 250.0}),
                Column(name="line_total", type="float",
                       distribution_params={"formula": "hours * rate"}),
            ],
            "audit_log": [
                Column(name="audit_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 4000}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
                Column(name="actor_user_id", type="foreign_key",
                       distribution_params={"references": "users.user_id"}),
                Column(name="action", type="categorical",
                       distribution_params={"choices": ["create", "update",
                                                        "delete", "login"]}),
                Column(name="occurred_at", type="datetime",
                       distribution_params={"start": "2022-07-01",
                                            "end": "2025-06-30"}),
            ],
        },
        relationships=[
            Relationship(parent_table="tenants", child_table="orgs",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="orgs", child_table="orgs",
                         parent_key="org_id", child_key="parent_org_id",
                         partition_by=["tenant_id"]),
            Relationship(parent_table="tenants", child_table="users",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="orgs", child_table="users",
                         parent_key="org_id", child_key="org_id",
                         partition_by=["tenant_id"]),
            Relationship(parent_table="tenants", child_table="projects",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="users", child_table="projects",
                         parent_key="user_id", child_key="owner_user_id",
                         partition_by=["tenant_id"]),
            Relationship(parent_table="tenants", child_table="tasks",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="projects", child_table="tasks",
                         parent_key="project_id", child_key="project_id",
                         partition_by=["tenant_id"], min_children=1),
            Relationship(parent_table="users", child_table="tasks",
                         parent_key="user_id", child_key="assignee_user_id",
                         partition_by=["tenant_id"]),
            Relationship(parent_table="tenants", child_table="task_events",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="tasks", child_table="task_events",
                         parent_key="task_id", child_key="task_id",
                         partition_by=["tenant_id"], min_children=1),
            Relationship(parent_table="users", child_table="task_events",
                         parent_key="user_id", child_key="actor_user_id",
                         partition_by=["tenant_id"],
                         parent_time="signup_date", child_time="occurred_at"),
            Relationship(parent_table="tenants", child_table="time_entries",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="tasks", child_table="time_entries",
                         parent_key="task_id", child_key="task_id",
                         partition_by=["tenant_id"]),
            Relationship(parent_table="users", child_table="time_entries",
                         parent_key="user_id", child_key="user_id",
                         partition_by=["tenant_id"]),
            Relationship(parent_table="tenants", child_table="invoices",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="projects", child_table="invoices",
                         parent_key="project_id", child_key="project_id",
                         partition_by=["tenant_id"]),
            Relationship(parent_table="tenants", child_table="invoice_lines",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="invoices", child_table="invoice_lines",
                         parent_key="invoice_id", child_key="invoice_id",
                         partition_by=["tenant_id"], min_children=1),
            Relationship(parent_table="tenants", child_table="audit_log",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="users", child_table="audit_log",
                         parent_key="user_id", child_key="actor_user_id",
                         partition_by=["tenant_id"]),
        ],
        # Dirt with an answer key: an anomaly detector and a data-cleaning
        # pipeline can both be scored against these numbers.
        outliers=[
            Outliers(table="time_entries", column="hours", count=30,
                     sigma=6.0, direction="high"),
        ],
        typos=[
            Typos(table="invoices", column="status", count=18),
        ],
        event_logs=[
            # The log must say the same thing the task's own state says. Before
            # this declaration existed the two disagreed on 1,862 rows.
            EventLog(
                name="task_event_log", table="task_events",
                entity_table="tasks", entity_key="task_id",
                event_type_column="event_type",
                event_time_column="occurred_at",
                state_events={"open": "created", "in_progress": "started",
                              "blocked": "blocked", "done": "completed",
                              "cancelled": "cancelled"},
                filler_events=["unblocked"],
            ),
        ],
        lifecycles=[
            Lifecycle(
                name="task_lifecycle",
                table="tasks", state_column="state", start_column="created_at",
                initial="open",
                states=[
                    LifecycleState(name="open"),
                    LifecycleState(name="in_progress", timestamp="started_at"),
                    LifecycleState(name="blocked"),
                    LifecycleState(name="done", timestamp="completed_at",
                                   terminal=True),
                    LifecycleState(name="cancelled", timestamp="cancelled_at",
                                   terminal=True),
                ],
                transitions=[
                    ("open", "in_progress"),
                    ("in_progress", "blocked"),
                    ("blocked", "in_progress"),
                    ("in_progress", "done"),
                    ("open", "cancelled"),
                ],
                weights={"open": 0.20, "in_progress": 0.20, "blocked": 0.10,
                         "done": 0.40, "cancelled": 0.10},
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# assertions
# --------------------------------------------------------------------------- #

PK = {"tenants": "tenant_id", "orgs": "org_id", "users": "user_id",
      "projects": "project_id", "tasks": "task_id", "task_events": "event_id",
      "time_entries": "entry_id", "invoices": "invoice_id",
      "invoice_lines": "line_id", "audit_log": "audit_id"}

# (child_table, child_key, parent_table, parent_key)
FKS = [
    ("orgs", "tenant_id", "tenants", "tenant_id"),
    ("orgs", "parent_org_id", "orgs", "org_id"),
    ("users", "tenant_id", "tenants", "tenant_id"),
    ("users", "org_id", "orgs", "org_id"),
    ("projects", "tenant_id", "tenants", "tenant_id"),
    ("projects", "owner_user_id", "users", "user_id"),
    ("tasks", "tenant_id", "tenants", "tenant_id"),
    ("tasks", "project_id", "projects", "project_id"),
    ("tasks", "assignee_user_id", "users", "user_id"),
    ("task_events", "tenant_id", "tenants", "tenant_id"),
    ("task_events", "task_id", "tasks", "task_id"),
    ("task_events", "actor_user_id", "users", "user_id"),
    ("time_entries", "tenant_id", "tenants", "tenant_id"),
    ("time_entries", "task_id", "tasks", "task_id"),
    ("time_entries", "user_id", "users", "user_id"),
    ("invoices", "tenant_id", "tenants", "tenant_id"),
    ("invoices", "project_id", "projects", "project_id"),
    ("invoice_lines", "tenant_id", "tenants", "tenant_id"),
    ("invoice_lines", "invoice_id", "invoices", "invoice_id"),
    ("audit_log", "tenant_id", "tenants", "tenant_id"),
    ("audit_log", "actor_user_id", "users", "user_id"),
]

# Child tables whose tenant must equal the tenant of the thing they hang off.
# (child, child_fk, parent, parent_key) -- both carry tenant_id.
TENANT_CHAIN = [
    ("orgs", "parent_org_id", "orgs", "org_id"),
    ("users", "org_id", "orgs", "org_id"),
    ("projects", "owner_user_id", "users", "user_id"),
    ("tasks", "project_id", "projects", "project_id"),
    ("tasks", "assignee_user_id", "users", "user_id"),
    ("task_events", "task_id", "tasks", "task_id"),
    ("task_events", "actor_user_id", "users", "user_id"),
    ("time_entries", "task_id", "tasks", "task_id"),
    ("time_entries", "user_id", "users", "user_id"),
    ("invoices", "project_id", "projects", "project_id"),
    ("invoice_lines", "invoice_id", "invoices", "invoice_id"),
    ("audit_log", "actor_user_id", "users", "user_id"),
]


def build_assertions() -> List[Tuple[str, str, str]]:
    a: List[Tuple[str, str, str]] = []

    # A -- structural
    for t, k in PK.items():
        a.append(("A", f"{t}.{k} unique",
                  f"SELECT count(*) FROM (SELECT {k} FROM {t} "
                  f"GROUP BY {k} HAVING count(*) > 1)"))
        a.append(("A", f"{t}.{k} not null",
                  f"SELECT count(*) FROM {t} WHERE {k} IS NULL"))
    for c, ck, p, pk in FKS:
        a.append(("A", f"{c}.{ck} -> {p}.{pk} no orphans",
                  f"SELECT count(*) FROM {c} c LEFT JOIN {p} p "
                  f"ON c.{ck} = p.{pk} WHERE c.{ck} IS NOT NULL "
                  f"AND p.{pk} IS NULL"))

    # T -- tenant isolation. Nothing may reference across tenants.
    for c, ck, p, pk in TENANT_CHAIN:
        a.append(("T", f"{c}.{ck} stays inside its own tenant",
                  f"SELECT count(*) FROM {c} c JOIN {p} p ON c.{ck} = p.{pk} "
                  f"WHERE c.tenant_id <> p.tenant_id"))

    # H -- hierarchy
    a += [
        ("H", "no org is its own parent",
         "SELECT count(*) FROM orgs WHERE parent_org_id = org_id"),
        ("H", "no two orgs are each other's parent",
         "SELECT count(*) FROM orgs a JOIN orgs b ON a.parent_org_id = b.org_id "
         "AND b.parent_org_id = a.org_id"),
        ("H", "no cycle within four hops",
         "SELECT count(*) FROM orgs a "
         "JOIN orgs b ON a.parent_org_id = b.org_id "
         "JOIN orgs c ON b.parent_org_id = c.org_id "
         "JOIN orgs d ON c.parent_org_id = d.org_id "
         "WHERE d.parent_org_id = a.org_id"),
        ("H", "at least one root org exists",
         "SELECT CASE WHEN (SELECT count(*) FROM orgs "
         "WHERE parent_org_id IS NULL) > 0 THEN 0 ELSE 1 END"),
        ("H", "not every org is a root (the hierarchy is real)",
         "SELECT CASE WHEN (SELECT count(*) FROM orgs "
         "WHERE parent_org_id IS NOT NULL) > 0 THEN 0 ELSE 1 END"),
        ("H", "a child org never predates its parent",
         "SELECT count(*) FROM orgs c JOIN orgs p ON c.parent_org_id = p.org_id "
         "WHERE c.created_at < p.created_at"),
        ("H", "every user's org exists and is not null",
         "SELECT count(*) FROM users WHERE org_id IS NULL"),
    ]

    # S -- event log / state
    a += [
        ("S", "every task has at least one event",
         "SELECT count(*) FROM tasks t LEFT JOIN "
         "(SELECT DISTINCT task_id FROM task_events) e USING (task_id) "
         "WHERE e.task_id IS NULL"),
        ("S", "no event predates the task it belongs to",
         "SELECT count(*) FROM task_events e JOIN tasks t USING (task_id) "
         "WHERE e.occurred_at < t.created_at"),
        ("S", "a done task has a completed event",
         "SELECT count(*) FROM tasks t WHERE t.state = 'done' AND NOT EXISTS "
         "(SELECT 1 FROM task_events e WHERE e.task_id = t.task_id "
         "AND e.event_type = 'completed')"),
        ("S", "a cancelled task has a cancelled event",
         "SELECT count(*) FROM tasks t WHERE t.state = 'cancelled' AND NOT EXISTS "
         "(SELECT 1 FROM task_events e WHERE e.task_id = t.task_id "
         "AND e.event_type = 'cancelled')"),
        ("S", "an open task has no completed or cancelled event",
         "SELECT count(*) FROM tasks t WHERE t.state = 'open' AND EXISTS "
         "(SELECT 1 FROM task_events e WHERE e.task_id = t.task_id "
         "AND e.event_type IN ('completed','cancelled'))"),
        ("S", "a completed event never precedes the task's started_at",
         "SELECT count(*) FROM task_events e JOIN tasks t USING (task_id) "
         "WHERE e.event_type = 'completed' AND t.started_at IS NOT NULL "
         "AND e.occurred_at < t.started_at"),
        ("S", "an event's actor belongs to the event's tenant",
         "SELECT count(*) FROM task_events e JOIN users u "
         "ON e.actor_user_id = u.user_id WHERE e.tenant_id <> u.tenant_id"),
        ("S", "event_type is always a known type",
         f"SELECT count(*) FROM task_events WHERE event_type NOT IN ({EVENT_TYPES})"),
    ]

    # J -- lifecycle (the declared one)
    a += [
        ("J", "task state is always a known state",
         f"SELECT count(*) FROM tasks WHERE state NOT IN ({TASK_STATES})"),
        ("J", "done tasks carry started_at and completed_at",
         "SELECT count(*) FROM tasks WHERE state = 'done' "
         "AND (started_at IS NULL OR completed_at IS NULL)"),
        ("J", "open tasks carry no started_at",
         "SELECT count(*) FROM tasks WHERE state = 'open' "
         "AND started_at IS NOT NULL"),
        ("J", "open tasks carry no completed_at",
         "SELECT count(*) FROM tasks WHERE state = 'open' "
         "AND completed_at IS NOT NULL"),
        ("J", "cancelled tasks carry cancelled_at",
         "SELECT count(*) FROM tasks WHERE state = 'cancelled' "
         "AND cancelled_at IS NULL"),
        ("J", "non-cancelled tasks carry no cancelled_at",
         "SELECT count(*) FROM tasks WHERE state <> 'cancelled' "
         "AND cancelled_at IS NOT NULL"),
        ("J", "started_at never precedes created_at",
         "SELECT count(*) FROM tasks WHERE started_at IS NOT NULL "
         "AND started_at < created_at"),
        ("J", "completed_at never precedes started_at",
         "SELECT count(*) FROM tasks WHERE completed_at IS NOT NULL "
         "AND started_at IS NOT NULL AND completed_at < started_at"),
    ]

    # R -- reconciliation
    a += [
        ("R", "invoices.amount = sum(invoice_lines.line_total), to the cent",
         "SELECT count(*) FROM invoices i JOIN "
         "(SELECT invoice_id, sum(line_total) s FROM invoice_lines "
         "GROUP BY invoice_id) l USING (invoice_id) "
         "WHERE abs(i.amount - l.s) > 0.01"),
        ("R", "invoice_lines.line_total = hours * rate",
         "SELECT count(*) FROM invoice_lines "
         "WHERE abs(line_total - hours * rate) > 0.01"),
        ("R", "grand total: sum(invoices.amount) = sum(lines.line_total)",
         "SELECT CASE WHEN abs((SELECT sum(amount) FROM invoices) - "
         "(SELECT sum(line_total) FROM invoice_lines)) > 0.05 THEN 1 ELSE 0 END"),
        ("R", "every invoice has at least one line",
         "SELECT count(*) FROM invoices i LEFT JOIN "
         "(SELECT DISTINCT invoice_id FROM invoice_lines) l USING (invoice_id) "
         "WHERE l.invoice_id IS NULL"),
        ("R", "every project has at least one task",
         "SELECT count(*) FROM projects p LEFT JOIN "
         "(SELECT DISTINCT project_id FROM tasks) t USING (project_id) "
         "WHERE t.project_id IS NULL"),
        ("R", "estimate_hours never exceeds cap_hours",
         "SELECT count(*) FROM tasks WHERE estimate_hours > cap_hours"),
    ]

    # B -- domain
    a += [
        # Bounded below always; the upper bound is deliberately breached by the
        # 30 declared outliers, and category N asserts that count exactly. An
        # assertion that contradicts a declaration is the assertion's mistake.
        ("B", "time_entries.hours is always positive",
         "SELECT count(*) FROM time_entries WHERE hours <= 0"),
        ("B", "invoice_lines.rate is positive",
         "SELECT count(*) FROM invoice_lines WHERE rate <= 0"),
        ("B", "invoice_lines.hours is positive",
         "SELECT count(*) FROM invoice_lines WHERE hours <= 0"),
        ("B", "tenants.plan is a known plan",
         "SELECT count(*) FROM tenants WHERE plan NOT IN "
         "('free','team','business','enterprise')"),
        ("B", "tenants.region is a known region",
         "SELECT count(*) FROM tenants WHERE region NOT IN ('us','eu','apac')"),
        ("B", "org_name matches ORG-XXX",
         "SELECT count(*) FROM orgs WHERE org_name NOT SIMILAR TO 'ORG-[A-Z]{3}'"),
        ("B", "users.status is a known status",
         "SELECT count(*) FROM users WHERE status NOT IN "
         "('active','invited','deactivated')"),
        ("B", "deactivated users carry deactivated_at",
         "SELECT count(*) FROM users WHERE status = 'deactivated' "
         "AND deactivated_at IS NULL"),
        ("B", "active users carry no deactivated_at",
         "SELECT count(*) FROM users WHERE status = 'active' "
         "AND deactivated_at IS NOT NULL"),
        # Same again: 18 statuses are declared typos. What must hold is that
        # nothing ELSE is unknown, which category N pins to the exact count.
        ("B", "no invoice status is null or blank",
         "SELECT count(*) FROM invoices WHERE status IS NULL "
         "OR length(trim(status)) = 0"),
    ]

    # C -- temporal causality across tables
    a += [
        ("C", "no user predates their tenant",
         "SELECT count(*) FROM users u JOIN tenants t USING (tenant_id) "
         "WHERE u.signup_date < t.created_at"),
        ("C", "no project predates its owner's signup",
         "SELECT count(*) FROM projects p JOIN users u "
         "ON p.owner_user_id = u.user_id WHERE p.started_at < u.signup_date"),
        ("C", "no task predates its project",
         "SELECT count(*) FROM tasks t JOIN projects p USING (project_id) "
         "WHERE t.created_at < p.started_at"),
        ("C", "no time entry predates its task",
         "SELECT count(*) FROM time_entries e JOIN tasks t USING (task_id) "
         "WHERE e.entry_date < t.created_at"),
        ("C", "no invoice predates its project",
         "SELECT count(*) FROM invoices i JOIN projects p USING (project_id) "
         "WHERE i.issued_at < p.started_at"),
        ("C", "no audit entry predates its actor's signup",
         "SELECT count(*) FROM audit_log a JOIN users u "
         "ON a.actor_user_id = u.user_id WHERE a.occurred_at < u.signup_date"),
        ("C", "no org predates its tenant",
         "SELECT count(*) FROM orgs o JOIN tenants t USING (tenant_id) "
         "WHERE o.created_at < t.created_at"),
    ]

    # N -- dirt with an answer key
    a += [
        ("N", "exactly 30 time entries are high outliers, as declared",
         "SELECT CASE WHEN (SELECT count(*) FROM time_entries "
         "WHERE hours > 24) = 30 THEN 0 ELSE 1 END"),
        ("N", "every outlier is on the high side, as declared",
         "SELECT count(*) FROM time_entries WHERE hours < 0"),
        ("N", "exactly 18 invoice statuses are typos, as declared",
         "SELECT CASE WHEN (SELECT count(*) FROM invoices WHERE status NOT IN "
         "('draft','sent','paid')) = 18 THEN 0 ELSE 1 END"),
        ("N", "typos are corruptions, not empty",
         "SELECT count(*) FROM invoices WHERE status IS NULL "
         "OR length(status) = 0"),
        ("N", "the clean majority is untouched",
         "SELECT CASE WHEN (SELECT count(*) FROM invoices WHERE status IN "
         "('draft','sent','paid')) = 342 THEN 0 ELSE 1 END"),
    ]

    # I -- distribution sanity
    a += [
        ("I", "every tenant has at least one user",
         "SELECT count(*) FROM tenants t LEFT JOIN "
         "(SELECT DISTINCT tenant_id FROM users) u USING (tenant_id) "
         "WHERE u.tenant_id IS NULL"),
        ("I", "every tenant has at least one task",
         "SELECT count(*) FROM tenants t LEFT JOIN "
         "(SELECT DISTINCT tenant_id FROM tasks) k USING (tenant_id) "
         "WHERE k.tenant_id IS NULL"),
        ("I", "task states are not degenerate (4+ present)",
         "SELECT CASE WHEN (SELECT count(DISTINCT state) FROM tasks) >= 4 "
         "THEN 0 ELSE 1 END"),
        ("I", "some tasks carry more than one event",
         "SELECT CASE WHEN (SELECT max(n) FROM (SELECT count(*) n "
         "FROM task_events GROUP BY task_id)) > 1 THEN 0 ELSE 1 END"),
        ("I", "time_entries.hours has spread",
         "SELECT CASE WHEN (SELECT count(DISTINCT round(hours,2)) "
         "FROM time_entries) > 50 THEN 0 ELSE 1 END"),
        ("I", "more than one org has children",
         "SELECT CASE WHEN (SELECT count(*) FROM (SELECT parent_org_id "
         "FROM orgs WHERE parent_org_id IS NOT NULL "
         "GROUP BY parent_org_id)) > 1 THEN 0 ELSE 1 END"),
    ]
    return a


# --------------------------------------------------------------------------- #
# harness
# --------------------------------------------------------------------------- #

CAT_NAMES = {"A": "structural", "B": "domain", "C": "temporal",
             "T": "tenant isolation", "H": "hierarchy",
             "S": "event log", "J": "lifecycle",
             "R": "reconciliation", "I": "distribution",
             "N": "dirt with an answer key"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_path", default=None)
    args = ap.parse_args()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t0 = time.perf_counter()
        tables = misata.generate_from_schema(build_schema())
        gen_secs = time.perf_counter() - t0

    con = duckdb.connect()
    for name, df in tables.items():
        con.register(name, df)

    results = []
    for cat, name, sql in build_assertions():
        try:
            violations = int(con.execute(sql).fetchone()[0] or 0)
            error = None
        except Exception as e:                      # a broken assertion is a fail
            violations, error = -1, str(e)[:180]
        results.append({"category": cat, "name": name, "violations": violations,
                        "error": error, "known_red": name in KNOWN_RED})

    passed = sum(1 for r in results if r["violations"] == 0)
    total = len(results)
    unexpected = [r for r in results
                  if r["violations"] != 0 and not r["known_red"]]
    promotable = [r for r in results if r["violations"] == 0 and r["known_red"]]

    print(f"\nTHE WARREN  --  {len(tables)} tables, "
          f"{sum(len(t) for t in tables.values()):,} rows, {total} assertions, "
          f"generated in {gen_secs:.1f}s\n")
    for cat in sorted({r["category"] for r in results}):
        rs = [r for r in results if r["category"] == cat]
        ok = sum(1 for r in rs if r["violations"] == 0)
        print(f"  {cat}  {CAT_NAMES.get(cat, cat):<18} {ok}/{len(rs)}")
        for r in rs:
            if r["violations"] == 0:
                continue
            tag = "KNOWN-RED" if r["known_red"] else "FAIL"
            detail = (f"({r['violations']:,} violating rows)"
                      if r["violations"] >= 0 else f"(ERROR: {r['error']})")
            print(f"       {tag}  {r['name']}  {detail}")
            if r["known_red"]:
                print(f"                 roadmap: {KNOWN_RED[r['name']]}")

    print(f"\n  TOTAL  {passed}/{total} ({100 * passed // total}%)")
    if promotable:
        for r in promotable:
            print(f"  PROMOTE: known-red '{r['name']}' now passes "
                  f"— remove it from KNOWN_RED.")
    if args.json_path:
        with open(args.json_path, "w") as f:
            json.dump({"passed": passed, "total": total, "results": results,
                       "known_red": KNOWN_RED,
                       "generation_seconds": gen_secs}, f, indent=2)
    return 1 if (unexpected or promotable) else 0


if __name__ == "__main__":
    raise SystemExit(main())
