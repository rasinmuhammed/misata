"""Tests for declared entity lifecycles (misata/lifecycle.py).

The contract: for a row in state S, with P = path(initial → S),
  * every state in P that has a timestamp column has it populated,
  * those timestamps ascend in path order,
  * every state outside P has its timestamp NULL,
  * the whole chain postdates start_column.

That is what makes a status column trustworthy, and it is the thing a
per-pair when_then rule cannot express: a returned order must also carry the
shipment and completion it necessarily passed through.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata.coherence import coherence_audit
from misata.lifecycle import apply_lifecycle, _allocate_states
from misata.schema import (SchemaConfig, Table, Column, Relationship,
                           Lifecycle, LifecycleState)

warnings.filterwarnings("ignore")


def _order_lifecycle(**over):
    kwargs = dict(
        name="order_lifecycle",
        table="orders",
        state_column="status",
        start_column="order_date",
        initial="placed",
        states=[
            LifecycleState(name="placed", timestamp="placed_at"),
            LifecycleState(name="shipped", timestamp="shipped_at"),
            LifecycleState(name="completed", timestamp="completed_at"),
            LifecycleState(name="returned", terminal=True),
            LifecycleState(name="cancelled", timestamp="cancelled_at", terminal=True),
        ],
        transitions=[("placed", "shipped"), ("shipped", "completed"),
                     ("completed", "returned"), ("placed", "cancelled")],
        weights={"placed": 0.2, "shipped": 0.2, "completed": 0.3,
                 "returned": 0.2, "cancelled": 0.1},
    )
    kwargs.update(over)
    return Lifecycle(**kwargs)


def _schema(lifecycle=None, rows=400, seed=3):
    lc = [lifecycle] if lifecycle is not None else []
    return SchemaConfig(
        name="lc",
        tables=[Table(name="orders", row_count=rows)],
        columns={
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": rows}),
                Column(name="order_date", type="datetime",
                       distribution_params={"start": "2024-01-01", "end": "2024-06-30"}),
                Column(name="status", type="categorical",
                       distribution_params={"choices": [
                           "placed", "shipped", "completed", "returned", "cancelled"]}),
                Column(name="placed_at", type="datetime", nullable=True,
                       distribution_params={"start": "2024-01-01", "end": "2024-12-31"}),
                Column(name="shipped_at", type="datetime", nullable=True,
                       distribution_params={"start": "2024-01-01", "end": "2024-12-31",
                                            "null_probability": 0.3}),
                Column(name="completed_at", type="datetime", nullable=True,
                       distribution_params={"start": "2024-01-01", "end": "2024-12-31",
                                            "null_probability": 0.4}),
                Column(name="cancelled_at", type="datetime", nullable=True,
                       distribution_params={"start": "2024-01-01", "end": "2024-12-31",
                                            "null_probability": 0.9}),
            ],
        },
        lifecycles=lc,
        seed=seed,
    )


# --------------------------------------------------------------------------- #
# path derivation
# --------------------------------------------------------------------------- #

class TestPath:
    def test_initial_path_is_itself(self):
        assert _order_lifecycle().path_to("placed") == ["placed"]

    def test_multi_hop_path(self):
        assert _order_lifecycle().path_to("returned") == [
            "placed", "shipped", "completed", "returned"]

    def test_branch_path_is_direct(self):
        assert _order_lifecycle().path_to("cancelled") == ["placed", "cancelled"]

    def test_unreachable_state_returns_none(self):
        lc = _order_lifecycle(transitions=[("placed", "shipped")])
        assert lc.path_to("cancelled") is None

    def test_shortest_path_wins(self):
        lc = _order_lifecycle(transitions=[
            ("placed", "shipped"), ("shipped", "completed"),
            ("completed", "returned"), ("placed", "returned")])
        assert lc.path_to("returned") == ["placed", "returned"]

    def test_duplicate_state_names_rejected(self):
        with pytest.raises(ValueError, match="unique"):
            Lifecycle(name="x", table="t", state_column="s",
                      states=[LifecycleState(name="a"), LifecycleState(name="a")])


# --------------------------------------------------------------------------- #
# the four guarantees
# --------------------------------------------------------------------------- #

class TestGuarantees:
    def test_only_declared_states_appear(self):
        df = misata.generate_from_schema(_schema(_order_lifecycle()))["orders"]
        assert set(df["status"]) <= {"placed", "shipped", "completed",
                                     "returned", "cancelled"}

    def test_path_states_are_populated(self):
        df = misata.generate_from_schema(_schema(_order_lifecycle()))["orders"]
        # returned goes through shipped and completed, so both must be present
        ret = df[df["status"] == "returned"]
        assert len(ret) > 0
        assert ret["placed_at"].notna().all()
        assert ret["shipped_at"].notna().all()
        assert ret["completed_at"].notna().all()

    def test_off_path_states_are_null(self):
        df = misata.generate_from_schema(_schema(_order_lifecycle()))["orders"]
        cancelled = df[df["status"] == "cancelled"]
        assert len(cancelled) > 0
        # cancelled branches straight off placed: never shipped, never completed
        assert cancelled["shipped_at"].isna().all()
        assert cancelled["completed_at"].isna().all()
        # and only cancelled rows carry cancelled_at
        assert df.loc[df["status"] != "cancelled", "cancelled_at"].isna().all()

    def test_timestamps_ascend_in_path_order(self):
        df = misata.generate_from_schema(_schema(_order_lifecycle()))["orders"]
        done = df[df["status"].isin(["completed", "returned"])]
        assert len(done) > 0
        assert (done["shipped_at"] >= done["placed_at"]).all()
        assert (done["completed_at"] >= done["shipped_at"]).all()

    def test_chain_postdates_start_column(self):
        df = misata.generate_from_schema(_schema(_order_lifecycle()))["orders"]
        for col in ["placed_at", "shipped_at", "completed_at", "cancelled_at"]:
            sub = df[df[col].notna()]
            assert (sub[col] >= sub["order_date"]).all(), col

    def test_every_row_has_the_initial_timestamp(self):
        df = misata.generate_from_schema(_schema(_order_lifecycle()))["orders"]
        assert df["placed_at"].notna().all()


# --------------------------------------------------------------------------- #
# weights
# --------------------------------------------------------------------------- #

class TestWeights:
    def test_weights_allocated_by_largest_remainder(self):
        df = misata.generate_from_schema(_schema(_order_lifecycle(), rows=1000))["orders"]
        counts = df["status"].value_counts()
        assert counts["completed"] == 300
        assert counts["placed"] == 200
        assert counts["cancelled"] == 100

    def test_weights_normalised_with_warning(self):
        lc = _order_lifecycle(weights={"placed": 2.0, "completed": 2.0})
        with pytest.warns(UserWarning, match="normalising"):
            misata.generate_from_schema(_schema(lc))

    def test_no_weights_is_uniform(self):
        lc = _order_lifecycle(weights=None)
        df = misata.generate_from_schema(_schema(lc, rows=500))["orders"]
        counts = df["status"].value_counts()
        assert counts.max() - counts.min() <= 1

    def test_allocation_totals_exactly_n(self):
        rng = np.random.default_rng(0)
        got = _allocate_states(997, ["a", "b", "c"], {"a": .5, "b": .3, "c": .2}, rng)
        assert len(got) == 997
        assert set(got) == {"a", "b", "c"}


# --------------------------------------------------------------------------- #
# refusal and audit
# --------------------------------------------------------------------------- #

class TestRefusalAndAudit:
    def test_weighted_unreachable_state_is_refused_up_front(self):
        """A weight on a state no transition reaches is a contradiction, so it
        is refused before generation rather than warned about afterwards."""
        from misata.feasibility import InfeasibleSchema
        lc = _order_lifecycle(transitions=[("placed", "shipped")])
        with pytest.raises(InfeasibleSchema, match="cancelled|completed|returned"):
            misata.generate_from_schema(_schema(lc))

    def test_unreachable_state_warns_and_is_unused(self):
        """With no weight attached, an unreachable state is not a contradiction,
        only dead vocabulary: the run proceeds and warns."""
        lc = _order_lifecycle(transitions=[("placed", "shipped")], weights=None)
        with pytest.warns(UserWarning, match="not reachable"):
            df = misata.generate_from_schema(_schema(lc))["orders"]
        assert "cancelled" not in set(df["status"])

    def test_missing_state_column_warns(self):
        lc = _order_lifecycle(state_column="nope")
        with pytest.warns(UserWarning, match="state column"):
            misata.generate_from_schema(_schema(lc))

    def test_audit_clean_on_generated_data(self):
        schema = _schema(_order_lifecycle())
        tables = misata.generate_from_schema(schema)
        report = coherence_audit(tables, schema=schema)
        assert not [f for f in report.findings if f.kind.startswith("lifecycle")]

    def test_audit_catches_impossible_timestamp(self):
        schema = _schema(_order_lifecycle())
        tables = misata.generate_from_schema(schema)
        df = tables["orders"]
        idx = df[df["status"] == "cancelled"].index[:3]
        df.loc[idx, "shipped_at"] = pd.Timestamp("2024-05-01")
        report = coherence_audit(tables, schema=schema)
        assert any(f.kind == "lifecycle_impossible_timestamp" for f in report.findings)

    def test_audit_catches_missing_timestamp(self):
        schema = _schema(_order_lifecycle())
        tables = misata.generate_from_schema(schema)
        df = tables["orders"]
        idx = df[df["status"] == "returned"].index[:3]
        df.loc[idx, "completed_at"] = pd.NaT
        report = coherence_audit(tables, schema=schema)
        assert any(f.kind == "lifecycle_missing_timestamp" for f in report.findings)

    def test_audit_catches_out_of_order(self):
        schema = _schema(_order_lifecycle())
        tables = misata.generate_from_schema(schema)
        df = tables["orders"]
        idx = df[df["status"] == "completed"].index[:3]
        df.loc[idx, "completed_at"] = df.loc[idx, "placed_at"] - pd.Timedelta(days=5)
        report = coherence_audit(tables, schema=schema)
        assert any(f.kind in ("lifecycle_out_of_order", "lifecycle_precedes_start")
                   for f in report.findings)

    def test_audit_catches_illegal_state(self):
        schema = _schema(_order_lifecycle())
        tables = misata.generate_from_schema(schema)
        tables["orders"].loc[0, "status"] = "teleported"
        report = coherence_audit(tables, schema=schema)
        assert any(f.kind == "lifecycle_illegal_state" for f in report.findings)


# --------------------------------------------------------------------------- #
# interaction with the rest of the engine
# --------------------------------------------------------------------------- #

class TestInteractions:
    def test_no_lifecycle_declared_changes_nothing(self):
        """The default path must be untouched: same seed, identical bytes."""
        a = misata.generate_from_schema(_schema(None))["orders"]
        b = misata.generate_from_schema(_schema(None))["orders"]
        pd.testing.assert_frame_equal(a, b)

    def test_determinism_with_lifecycle(self):
        a = misata.generate_from_schema(_schema(_order_lifecycle()))["orders"]
        b = misata.generate_from_schema(_schema(_order_lifecycle()))["orders"]
        pd.testing.assert_frame_equal(a, b)

    def test_children_see_final_states(self):
        """A filtered relationship must match the post-lifecycle status.

        This is why the lifecycle runs during the parent's generation: if the
        context still held pre-rewrite states, shipments would attach to orders
        that were never shipped.
        """
        schema = _schema(_order_lifecycle(), rows=300)
        schema.tables.append(Table(name="shipments", row_count=120))
        schema.columns["shipments"] = [
            Column(name="shipment_id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 120}),
            Column(name="order_id", type="foreign_key",
                   distribution_params={"references": "orders.order_id"}),
        ]
        schema.relationships = [
            Relationship(parent_table="orders", child_table="shipments",
                         parent_key="order_id", child_key="order_id",
                         filters={"status": ["shipped", "completed", "returned"]}),
        ]
        t = misata.generate_from_schema(schema)
        merged = t["shipments"].merge(t["orders"][["order_id", "status"]], on="order_id")
        assert merged["status"].isin(["shipped", "completed", "returned"]).all()

    def test_states_without_timestamps_are_allowed(self):
        lc = _order_lifecycle(states=[
            LifecycleState(name="placed"),
            LifecycleState(name="shipped"),
            LifecycleState(name="cancelled", terminal=True),
        ], transitions=[("placed", "shipped"), ("placed", "cancelled")],
            weights={"placed": .4, "shipped": .4, "cancelled": .2})
        df = misata.generate_from_schema(_schema(lc))["orders"]
        assert set(df["status"]) == {"placed", "shipped", "cancelled"}

    def test_apply_lifecycle_on_empty_frame_is_safe(self):
        out = apply_lifecycle(pd.DataFrame(), _order_lifecycle(),
                              np.random.default_rng(1))
        assert out.empty

    def test_workflow_engine_event_stream_monotonic(self):
        from misata.workflows import WorkflowEngine
        engine = WorkflowEngine()
        events = engine.generate_event_stream(entity_ids=[1, 2], workflow_name="order", start_date="2024-01-01")
        assert not events.empty
        for _, group in events.groupby("entity_id"):
            assert group["timestamp"].is_monotonic_increasing



class TestLifecycleOnAChildTable:
    """A lifecycle on a table whose rows must postdate a parent."""

    SPEC = {
        "name": "subs", "seed": 404,
        "tables": {
            "customers": {"rows": 600, "columns": {
                "customer_id": {"type": "int", "unique": True, "min": 1, "max": 600},
                "signed_up_at": {"type": "date", "start": "2023-01-01", "end": "2025-09-30"}}},
            "subscriptions": {"rows": 600, "columns": {
                "subscription_id": {"type": "int", "unique": True, "min": 1, "max": 600},
                "customer_id": {"type": "foreign_key", "unique": True},
                "status": {"type": "categorical", "choices": ["trialing", "active", "churned"]},
                "started_at": {"type": "date", "start": "2023-01-01", "end": "2025-09-30"},
                "activated_at": {"type": "date", "nullable": True},
                "churned_at": {"type": "datetime", "nullable": True}}},
        },
        "relationships": ["customers.customer_id -> subscriptions.customer_id"],
        "lifecycles": [{
            "name": "subscription", "table": "subscriptions", "state_column": "status",
            "start_column": "started_at", "initial": "trialing",
            "states": [{"name": "trialing"}, {"name": "active", "timestamp": "activated_at"},
                       {"name": "churned", "timestamp": "churned_at", "terminal": True}],
            "transitions": [["trialing", "active"], ["active", "churned"]],
            "weights": {"trialing": 0.1, "active": 0.6, "churned": 0.3}}],
    }

    @pytest.fixture(scope="class")
    def generated(self, tmp_path_factory):
        import warnings

        import yaml

        from misata.yaml_schema import load_yaml_schema

        path = tmp_path_factory.mktemp("lc") / "misata.yaml"
        path.write_text(yaml.safe_dump(self.SPEC), encoding="utf-8")
        schema = load_yaml_schema(path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            tables = misata.generate_from_schema(schema)
        return schema, tables, caught

    def test_the_start_column_stays_inside_its_window_and_after_its_parent(self, generated):
        _, tables, caught = generated
        subs, customers = tables["subscriptions"], tables["customers"]
        started = pd.to_datetime(subs["started_at"])
        assert started.min() >= pd.Timestamp("2023-01-01")
        assert started.max() <= pd.Timestamp("2025-09-30")
        joined = subs.merge(customers, on="customer_id")
        assert (pd.to_datetime(joined["started_at"])
                >= pd.to_datetime(joined["signed_up_at"])).all()
        assert not [w for w in caught if "born at the edge" in str(w.message)]

    def test_state_timestamps_are_whole_days_or_whole_seconds(self, generated):
        _, tables, _ = generated
        activated = pd.to_datetime(tables["subscriptions"]["activated_at"]).dropna()
        churned = pd.to_datetime(tables["subscriptions"]["churned_at"]).dropna()
        assert (activated == activated.dt.normalize()).all()
        assert (churned == churned.dt.floor("s")).all()

    def test_the_audit_is_clean(self, generated):
        from misata.coherence import coherence_audit

        schema, tables, _ = generated
        report = coherence_audit(tables, schema=schema)
        assert report.clean, [f.message for f in report.findings]
