"""Tests for partition isolation, forest hierarchies, event logs, and exact dirt.

All four were found by the Warren conformance suite, which exists because the
Gauntlet reached 100% and a suite at 100% has stopped being able to find
anything. Each test below pairs the guarantee with a control showing the
undeclared version genuinely fails, so none of them can quietly become vacuous.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata.coherence import coherence_audit
from misata.dynamics import apply_outliers, apply_typos, robust_scale
from misata.schema import (SchemaConfig, Table, Column, Relationship,
                           Lifecycle, LifecycleState, EventLog, Outliers, Typos)

warnings.filterwarnings("ignore")


# --------------------------------------------------------------------------- #
# partition isolation
# --------------------------------------------------------------------------- #

def _tenanted(partition=True, **over):
    part = ["tenant_id"] if partition else []
    kwargs = dict(
        name="tenanted", seed=5,
        tables=[Table(name="tenants", row_count=5),
                Table(name="projects", row_count=60),
                Table(name="tasks", row_count=900)],
        columns={
            "tenants": [
                Column(name="tenant_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 5}),
                Column(name="plan", type="categorical",
                       distribution_params={"choices": ["free", "paid"]}),
            ],
            "projects": [
                Column(name="project_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 60}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
            ],
            "tasks": [
                Column(name="task_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 900}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
                Column(name="project_id", type="foreign_key",
                       distribution_params={"references": "projects.project_id"}),
            ],
        },
        relationships=[
            Relationship(parent_table="tenants", child_table="projects",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="tenants", child_table="tasks",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="projects", child_table="tasks",
                         parent_key="project_id", child_key="project_id",
                         partition_by=part),
        ],
    )
    kwargs.update(over)
    return SchemaConfig(**kwargs)


def _leaks(tables):
    projects = tables["projects"].set_index("project_id")["tenant_id"]
    mapped = tables["tasks"]["project_id"].map(projects)
    return int((tables["tasks"]["tenant_id"] != mapped).sum())


class TestPartitionIsolation:

    def test_no_key_crosses_its_partition(self):
        assert _leaks(misata.generate_from_schema(_tenanted())) == 0

    def test_without_the_declaration_it_leaks(self):
        """The control. This is the Fivetran defect in miniature."""
        assert _leaks(misata.generate_from_schema(_tenanted(partition=False))) > 0

    def test_referential_integrity_survives(self):
        tables = misata.generate_from_schema(_tenanted())
        valid = set(tables["projects"]["project_id"])
        assert set(tables["tasks"]["project_id"]) <= valid

    def test_more_than_one_parent_per_partition_is_used(self):
        """Collapsing every tenant onto one project would also pass above."""
        tables = misata.generate_from_schema(_tenanted())
        per_tenant = tables["tasks"].groupby("tenant_id")["project_id"].nunique()
        assert (per_tenant > 1).all()

    def test_min_children_does_not_leak(self):
        cfg = _tenanted()
        cfg.relationships[2].min_children = 1
        assert _leaks(misata.generate_from_schema(cfg)) == 0

    def test_audit_catches_an_injected_leak(self):
        cfg = _tenanted()
        tables = misata.generate_from_schema(cfg)
        assert not [f for f in coherence_audit(tables, schema=cfg).findings
                    if f.kind == "partition_leak"]
        # Move every task into one tenant while leaving its project alone.
        tables["tasks"]["tenant_id"] = tables["tenants"]["tenant_id"].iloc[0]
        found = [f for f in coherence_audit(tables, schema=cfg).findings
                 if f.kind == "partition_leak"]
        assert found and found[0].rows_affected > 0

    def test_deterministic_under_the_same_seed(self):
        a = misata.generate_from_schema(_tenanted())["tasks"]["project_id"]
        b = misata.generate_from_schema(_tenanted())["tasks"]["project_id"]
        pd.testing.assert_series_equal(a, b)


# --------------------------------------------------------------------------- #
# self-referential hierarchies
# --------------------------------------------------------------------------- #

def _orgs(null_rate=0.25, partition=False):
    part = ["tenant_id"] if partition else []
    return SchemaConfig(
        name="orgs", seed=3,
        tables=[Table(name="tenants", row_count=3),
                Table(name="orgs", row_count=60)],
        columns={
            "tenants": [Column(name="tenant_id", type="int", unique=True,
                               distribution_params={"min": 1, "max": 3})],
            "orgs": [
                Column(name="org_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 60}),
                Column(name="tenant_id", type="foreign_key",
                       distribution_params={"references": "tenants.tenant_id"}),
                Column(name="parent_org_id", type="foreign_key", nullable=True,
                       distribution_params={"references": "orgs.org_id",
                                            "null_rate": null_rate}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2022-01-01",
                                            "end": "2024-12-31"}),
            ],
        },
        relationships=[
            Relationship(parent_table="tenants", child_table="orgs",
                         parent_key="tenant_id", child_key="tenant_id"),
            Relationship(parent_table="orgs", child_table="orgs",
                         parent_key="org_id", child_key="parent_org_id",
                         partition_by=part),
        ],
    )


def _cycles(df):
    parent = dict(zip(df["org_id"], df["parent_org_id"]))
    bad = 0
    for start in parent:
        seen, node = {start}, parent.get(start)
        while node is not None and not pd.isna(node):
            if node in seen:
                bad += 1
                break
            seen.add(node)
            node = parent.get(node)
    return bad


class TestHierarchy:

    def test_the_hierarchy_is_a_forest(self):
        df = misata.generate_from_schema(_orgs())["orgs"]
        assert _cycles(df) == 0

    def test_roots_exist(self):
        """A hierarchy with no root cannot be acyclic, so this is load-bearing."""
        df = misata.generate_from_schema(_orgs())["orgs"]
        assert int(df["parent_org_id"].isna().sum()) > 0

    def test_a_declared_null_rate_on_an_optional_fk_is_honoured(self):
        """Foreign keys used to be exempt from nulling, which forced cycles."""
        df = misata.generate_from_schema(_orgs(null_rate=0.5))["orgs"]
        roots = int(df["parent_org_id"].isna().sum())
        assert 15 <= roots <= 45          # ~50% of 60, allowing sampling noise

    def test_no_row_is_its_own_parent(self):
        df = misata.generate_from_schema(_orgs())["orgs"]
        assert int((df["parent_org_id"] == df["org_id"]).sum()) == 0

    def test_a_child_never_predates_its_parent(self):
        df = misata.generate_from_schema(_orgs())["orgs"]
        ts = df.set_index("org_id")["created_at"]
        mapped = pd.to_datetime(df["parent_org_id"].map(ts))
        assert int((pd.to_datetime(df["created_at"]) < mapped).sum()) == 0

    def test_the_hierarchy_stays_inside_its_partition(self):
        df = misata.generate_from_schema(_orgs(partition=True))["orgs"]
        tmap = df.set_index("org_id")["tenant_id"]
        mapped = df["parent_org_id"].map(tmap)
        bad = (df["tenant_id"] != mapped) & mapped.notna()
        assert int(bad.sum()) == 0

    def test_audit_catches_an_injected_cycle(self):
        cfg = _orgs()
        tables = misata.generate_from_schema(cfg)
        assert not [f for f in coherence_audit(tables, schema=cfg).findings
                    if f.kind == "hierarchy_cycle"]
        df = tables["orgs"]
        a, b = df["org_id"].iloc[0], df["org_id"].iloc[1]
        df.loc[df.index[0], "parent_org_id"] = b
        df.loc[df.index[1], "parent_org_id"] = a
        found = [f for f in coherence_audit(tables, schema=cfg).findings
                 if f.kind == "hierarchy_cycle"]
        assert found


# --------------------------------------------------------------------------- #
# event logs
# --------------------------------------------------------------------------- #

def _logged(with_log=True):
    kwargs = dict(
        name="logged", seed=8,
        tables=[Table(name="tasks", row_count=300),
                Table(name="task_events", row_count=1200)],
        columns={
            "tasks": [
                Column(name="task_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 300}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-06-30"}),
                Column(name="state", type="categorical",
                       distribution_params={"choices": ["open", "started", "done"],
                                            "probabilities": [0.3, 0.3, 0.4]}),
                Column(name="started_at", type="datetime", nullable=True,
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-12-31"}),
                Column(name="completed_at", type="datetime", nullable=True,
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-12-31"}),
            ],
            "task_events": [
                Column(name="event_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 1200}),
                Column(name="task_id", type="foreign_key",
                       distribution_params={"references": "tasks.task_id"}),
                Column(name="event_type", type="categorical",
                       distribution_params={"choices": ["created", "started",
                                                        "completed", "noted"]}),
                Column(name="occurred_at", type="datetime",
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-12-31"}),
            ],
        },
        relationships=[
            Relationship(parent_table="tasks", child_table="task_events",
                         parent_key="task_id", child_key="task_id",
                         min_children=1),
        ],
        lifecycles=[Lifecycle(
            name="task_lc", table="tasks", state_column="state",
            start_column="created_at", initial="open",
            states=[LifecycleState(name="open"),
                    LifecycleState(name="started", timestamp="started_at"),
                    LifecycleState(name="done", timestamp="completed_at",
                                   terminal=True)],
            transitions=[("open", "started"), ("started", "done")],
            weights={"open": 0.3, "started": 0.3, "done": 0.4},
        )],
    )
    if with_log:
        kwargs["event_logs"] = [EventLog(
            name="log", table="task_events", entity_table="tasks",
            entity_key="task_id", event_type_column="event_type",
            event_time_column="occurred_at",
            state_events={"open": "created", "started": "started",
                          "done": "completed"},
            filler_events=["noted"])]
    return SchemaConfig(**kwargs)


def _log_gaps(tables):
    """(entities missing a required event, entities carrying an impossible one)."""
    req = {"open": {"created"}, "started": {"created", "started"},
           "done": {"created", "started", "completed"}}
    have = tables["task_events"].groupby("task_id")["event_type"].agg(set)
    missing = extra = 0
    for tid, st in zip(tables["tasks"]["task_id"], tables["tasks"]["state"]):
        got = have.get(tid, set())
        if req[st] - got:
            missing += 1
        if got - (req[st] | {"noted"}):
            extra += 1
    return missing, extra


class TestEventLog:

    def test_the_log_says_what_the_state_says(self):
        missing, extra = _log_gaps(misata.generate_from_schema(_logged()))
        assert (missing, extra) == (0, 0)

    def test_without_the_declaration_the_two_disagree(self):
        missing, extra = _log_gaps(
            misata.generate_from_schema(_logged(with_log=False)))
        assert missing > 0 and extra > 0

    def test_events_never_precede_their_entity(self):
        tables = misata.generate_from_schema(_logged())
        created = tables["tasks"].set_index("task_id")["created_at"]
        mapped = pd.to_datetime(tables["task_events"]["task_id"].map(created))
        assert int((pd.to_datetime(tables["task_events"]["occurred_at"])
                    < mapped).sum()) == 0

    def test_a_completion_never_precedes_its_start(self):
        tables = misata.generate_from_schema(_logged())
        ev, tk = tables["task_events"], tables["tasks"]
        started = tk.set_index("task_id")["started_at"]
        done = ev[ev["event_type"] == "completed"]
        mapped = pd.to_datetime(done["task_id"].map(started))
        pair = mapped.notna()
        assert int((pd.to_datetime(done["occurred_at"])[pair]
                    < mapped[pair]).sum()) == 0

    def test_referential_integrity_and_row_count_survive(self):
        tables = misata.generate_from_schema(_logged())
        assert len(tables["task_events"]) == 1200
        assert set(tables["task_events"]["task_id"]) <= set(tables["tasks"]["task_id"])

    def test_audit_catches_an_impossible_event(self):
        cfg = _logged()
        tables = misata.generate_from_schema(cfg)
        assert not [f for f in coherence_audit(tables, schema=cfg).findings
                    if f.kind == "event_log"]
        open_task = tables["tasks"].loc[
            tables["tasks"]["state"] == "open", "task_id"].iloc[0]
        ev = tables["task_events"]
        ev.loc[ev.index[0], "task_id"] = open_task
        ev.loc[ev.index[0], "event_type"] = "completed"
        assert [f for f in coherence_audit(tables, schema=cfg).findings
                if f.kind == "event_log"]

    def test_too_few_rows_is_refused_before_generating(self):
        """Measured, not assumed: the refusal beats the warning I had written.

        The first version of this test expected a runtime warning. Feasibility
        caught it first, with better arithmetic and before any rows existed,
        which is the behaviour the language is supposed to have. So the check
        moved into `feasibility` and this test asserts the refusal.
        """
        from misata.feasibility import InfeasibleSchema, find_conflicts
        cfg = _logged()
        cfg.tables[1].row_count = 200        # 300 tasks need far more than 200
        kinds = {c.kind for c in find_conflicts(cfg)}
        assert "event_log_capacity" in kinds
        with pytest.raises(InfeasibleSchema):
            misata.generate_from_schema(cfg)

    def test_enough_rows_is_not_refused(self):
        """False refusals are worse than the warnings they replace."""
        from misata.feasibility import find_conflicts
        assert not [c for c in find_conflicts(_logged())
                    if c.kind == "event_log_capacity"]


# --------------------------------------------------------------------------- #
# exact dirt
# --------------------------------------------------------------------------- #

def _dirty(**over):
    kwargs = dict(
        name="dirty", seed=11,
        tables=[Table(name="readings", row_count=500)],
        columns={"readings": [
            Column(name="reading_id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 500}),
            Column(name="value", type="float",
                   distribution_params={"distribution": "normal",
                                        "mean": 100.0, "std": 10.0}),
            Column(name="grade", type="categorical",
                   distribution_params={"choices": ["a", "b", "c"]}),
        ]},
    )
    kwargs.update(over)
    return SchemaConfig(**kwargs)


class TestOutliers:

    def test_exactly_the_declared_count(self):
        cfg = _dirty(outliers=[Outliers(table="readings", column="value",
                                        count=12, sigma=6.0)])
        df = misata.generate_from_schema(cfg)["readings"]
        med, sigma = robust_scale(df["value"].to_numpy())
        z = np.abs(df["value"].to_numpy() - med) / sigma
        assert int((z >= 6.0).sum()) == 12

    def test_direction_is_honoured(self):
        cfg = _dirty(outliers=[Outliers(table="readings", column="value",
                                        count=10, sigma=6.0, direction="high")])
        df = misata.generate_from_schema(cfg)["readings"]
        med, sigma = robust_scale(df["value"].to_numpy())
        far = df["value"][np.abs(df["value"] - med) / sigma >= 6.0]
        assert (far > med).all()

    def test_fraction_is_a_count(self):
        cfg = _dirty(outliers=[Outliers(table="readings", column="value",
                                        fraction=0.02, sigma=6.0)])
        df = misata.generate_from_schema(cfg)["readings"]
        med, sigma = robust_scale(df["value"].to_numpy())
        z = np.abs(df["value"].to_numpy() - med) / sigma
        assert int((z >= 6.0).sum()) == 10          # 2% of 500

    def test_the_clean_majority_keeps_its_shape(self):
        plain = misata.generate_from_schema(_dirty())["readings"]
        cfg = _dirty(outliers=[Outliers(table="readings", column="value",
                                        count=12, sigma=6.0)])
        dirty = misata.generate_from_schema(cfg)["readings"]
        assert abs(plain["value"].median() - dirty["value"].median()) < 1.0

    def test_audit_catches_a_wrong_count(self):
        cfg = _dirty(outliers=[Outliers(table="readings", column="value",
                                        count=12, sigma=6.0)])
        tables = misata.generate_from_schema(cfg)
        assert not [f for f in coherence_audit(tables, schema=cfg).findings
                    if f.kind == "outlier_count"]
        med, sigma = robust_scale(tables["readings"]["value"].to_numpy())
        tables["readings"].loc[tables["readings"].index[0], "value"] = med + 40 * sigma
        assert [f for f in coherence_audit(tables, schema=cfg).findings
                if f.kind == "outlier_count"]


class TestTypos:

    def test_exactly_the_declared_count_fall_outside_the_vocabulary(self):
        cfg = _dirty(typos=[Typos(table="readings", column="grade", count=9)])
        df = misata.generate_from_schema(cfg)["readings"]
        assert int((~df["grade"].isin(["a", "b", "c"])).sum()) == 9

    def test_typos_are_corruptions_not_blanks(self):
        cfg = _dirty(typos=[Typos(table="readings", column="grade", count=9)])
        df = misata.generate_from_schema(cfg)["readings"]
        bad = df.loc[~df["grade"].isin(["a", "b", "c"]), "grade"]
        assert bad.notna().all() and (bad.str.len() > 0).all()

    def test_a_column_with_no_vocabulary_is_refused_rather_than_faked(self):
        """A typo nobody can verify is not a guarantee."""
        cfg = _dirty(typos=[Typos(table="readings", column="value", count=5)])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            misata.generate_from_schema(cfg)
        assert any("neither 'choices' nor 'pattern'" in str(w.message)
                   for w in caught)

    def test_a_patterned_column_is_verifiable_and_accepted(self):
        """`pattern` describes legality where `choices` enumerates it."""
        import re
        cfg = SchemaConfig(
            name="patterned", seed=6,
            tables=[Table(name="items", row_count=300)],
            columns={"items": [
                Column(name="item_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 300}),
                Column(name="sku", type="text",
                       distribution_params={"pattern": "SKU-[0-9]{4}"}),
            ]},
            typos=[Typos(table="items", column="sku", count=7)],
        )
        df = misata.generate_from_schema(cfg)["items"]
        pat = re.compile("SKU-[0-9]{4}")
        bad = [v for v in df["sku"] if not pat.fullmatch(str(v))]
        assert len(bad) == 7
        assert all(v and str(v).strip() for v in bad)
        assert not [f for f in coherence_audit({"items": df}, schema=cfg).findings
                    if f.kind == "typo_count"]

    def test_audit_catches_a_wrong_count(self):
        cfg = _dirty(typos=[Typos(table="readings", column="grade", count=9)])
        tables = misata.generate_from_schema(cfg)
        assert not [f for f in coherence_audit(tables, schema=cfg).findings
                    if f.kind == "typo_count"]
        tables["readings"].loc[tables["readings"].index[0], "grade"] = "zzz"
        assert [f for f in coherence_audit(tables, schema=cfg).findings
                if f.kind == "typo_count"]
