"""Interval guarantees: no_overlap, capacity, and temporal containment.

Each guarantee is checked three ways: the generated rows obey it, the
coherence audit reports a violation planted by hand, and the attestation's SQL
agrees with both on the written files.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata.coherence import coherence_audit
from misata.feasibility import InfeasibleSchema, find_conflicts
from misata.intervals import apply_no_overlap
from misata.schema import (Capacity, Column, Constraint, NoOverlap, OutcomeCurve,
                           Relationship, SchemaConfig, Table, TimeGrid)

warnings.filterwarnings("ignore")

DAY = {"start": "2026-11-02 08:00:00", "end": "2026-11-02 18:00:00"}


def _visits_schema(*, no_overlap=True, capacity=None, seed=5, rows=900,
                   places=12, place_capacity=(4, 12)):
    """Residents visiting places of a few kinds over one day."""
    caps = list(capacity or [])
    return SchemaConfig(
        name="visits",
        tables=[Table(name="residents", row_count=300),
                Table(name="places", row_count=places),
                Table(name="visits", row_count=rows)],
        columns={
            "residents": [Column(name="resident_id", type="int", unique=True,
                                 distribution_params={"min": 1, "max": 300})],
            "places": [
                Column(name="place_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": places}),
                Column(name="kind", type="categorical",
                       distribution_params={"choices": ["cafe", "shop", "office"]}),
                Column(name="seats", type="int",
                       distribution_params={"min": place_capacity[0], "max": place_capacity[1]}),
            ],
            "visits": [
                Column(name="visit_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": rows}),
                Column(name="resident_id", type="foreign_key"),
                Column(name="kind", type="categorical",
                       distribution_params={"choices": ["cafe", "shop", "office"]}),
                Column(name="place_id", type="foreign_key"),
                Column(name="arrived_at", type="datetime", distribution_params=DAY),
                Column(name="left_at", type="datetime",
                       distribution_params={"start": "2026-11-02 08:30:00",
                                            "end": "2026-11-02 19:00:00"}),
            ],
        },
        relationships=[
            Relationship(parent_table="residents", child_table="visits",
                         parent_key="resident_id", child_key="resident_id"),
            Relationship(parent_table="places", child_table="visits",
                         parent_key="place_id", child_key="place_id",
                         partition_by=["kind"]),
        ],
        no_overlap=[NoOverlap(table="visits", key="resident_id",
                              start="arrived_at", end="left_at")] if no_overlap else [],
        capacity=caps,
        seed=seed,
    )


def _overlaps(df, key, start, end):
    iv = df[[key, start, end]].sort_values([key, start, end])
    prev = iv.groupby(key)[end].cummax().groupby(iv[key]).shift()
    return int((iv[start] < prev).sum())


def _peaks(df, resource, start, end):
    iv = df[df[end] > df[start]]
    ev = pd.concat([iv.assign(t=iv[start], d=1), iv.assign(t=iv[end], d=-1)])
    ev = ev.sort_values([resource, "t", "d"], kind="mergesort")
    ev["o"] = ev.groupby(resource)["d"].cumsum()
    return ev.groupby(resource)["o"].max()


def _attest(tables, schema, tmp_path):
    misata.to_parquet(tables, str(tmp_path))
    return misata.attest(tmp_path, schema, write=False)


def _invariant(attestation, kind):
    found = [i for i in attestation.invariants if i["kind"] == kind]
    assert found, f"no {kind} invariant in the attestation"
    return found


class TestNoOverlap:
    def test_an_entity_is_in_one_place_at_a_time(self):
        t = misata.generate_from_schema(_visits_schema())
        assert _overlaps(t["visits"], "resident_id", "arrived_at", "left_at") == 0

    def test_without_the_declaration_overlaps_exist(self):
        """The control: random intervals overlap, so the pass is doing the work."""
        t = misata.generate_from_schema(_visits_schema(no_overlap=False))
        assert _overlaps(t["visits"], "resident_id", "arrived_at", "left_at") > 0

    def test_overlaps_are_laid_end_to_end_keeping_durations(self):
        hour = pd.Timedelta(hours=1)
        t0 = pd.Timestamp("2026-11-02 09:00")
        df = pd.DataFrame({
            "who": [1, 1, 1, 2],
            "s": [t0, t0 + 0.5 * hour, t0 + 5 * hour, t0],
            "e": [t0 + hour, t0 + 2 * hour, t0 + 6 * hour, t0 + 3 * hour],
        })
        tables = {"t": df}
        schema = SchemaConfig(name="x", tables=[Table(name="t", row_count=4)],
                              columns={"t": [Column(name="who", type="int"),
                                             Column(name="s", type="datetime"),
                                             Column(name="e", type="datetime")]})
        apply_no_overlap(tables, NoOverlap(table="t", key="who", start="s", end="e"), schema)
        out = tables["t"]
        assert out["s"].tolist() == [t0, t0 + hour, t0 + 5 * hour, t0]
        assert out["e"].tolist() == [t0 + hour, t0 + 2.5 * hour, t0 + 6 * hour, t0 + 3 * hour]

    def test_audit_and_attestation_catch_a_planted_overlap(self, tmp_path):
        schema = _visits_schema()
        t = misata.generate_from_schema(schema)
        v = t["visits"]
        first = v.sort_values("arrived_at").groupby("resident_id").head(2)
        rid = first["resident_id"].value_counts().idxmax()
        rows = first.index[first["resident_id"] == rid]
        v.loc[rows[1], "arrived_at"] = v.loc[rows[0], "arrived_at"]
        report = coherence_audit(t, schema=schema)
        assert any(f.kind == "no_overlap" for f in report.findings)
        assert not _invariant(_attest(t, schema, tmp_path), "no_overlap")[0]["passed"]

    def test_attestation_passes_on_generated_rows(self, tmp_path):
        schema = _visits_schema()
        a = _attest(misata.generate_from_schema(schema), schema, tmp_path)
        assert all(i["passed"] for i in _invariant(a, "no_overlap"))


class TestCapacity:
    def _schema(self, **kw):
        cap = Capacity(table="visits", resource="place_id", start="arrived_at",
                       end="left_at", capacity_column="seats")
        return _visits_schema(no_overlap=False, capacity=[cap], places=30,
                              place_capacity=(20, 40), **kw)

    def test_no_resource_exceeds_its_capacity(self):
        schema = self._schema()
        t = misata.generate_from_schema(schema)
        peaks = _peaks(t["visits"], "place_id", "arrived_at", "left_at")
        seats = t["places"].set_index("place_id")["seats"]
        assert (peaks <= seats.reindex(peaks.index)).all()

    def test_moves_respect_the_relationship_partition(self):
        t = misata.generate_from_schema(self._schema())
        merged = t["visits"].merge(t["places"], on="place_id", suffixes=("", "_p"))
        assert (merged["kind"] == merged["kind_p"]).all()

    def test_times_never_change(self):
        free = misata.generate_from_schema(_visits_schema(no_overlap=False, places=30,
                                                          place_capacity=(20, 40)))["visits"]
        held = misata.generate_from_schema(self._schema())["visits"]
        assert free["arrived_at"].equals(held["arrived_at"])
        assert free["left_at"].equals(held["left_at"])

    def test_constant_capacity(self):
        cap = Capacity(table="visits", resource="place_id", start="arrived_at",
                       end="left_at", capacity=30)
        t = misata.generate_from_schema(_visits_schema(no_overlap=False, capacity=[cap],
                                                       places=30))
        assert _peaks(t["visits"], "place_id", "arrived_at", "left_at").max() <= 30

    def test_audit_and_attestation_catch_overflow(self, tmp_path):
        schema = self._schema()
        t = misata.generate_from_schema(schema)
        t["places"]["seats"] = 1
        report = coherence_audit(t, schema=schema)
        assert any(f.kind == "capacity_exceeded" for f in report.findings)
        assert not _invariant(_attest(t, schema, tmp_path), "capacity")[0]["passed"]

    def test_attestation_passes_on_generated_rows(self, tmp_path):
        schema = self._schema()
        a = _attest(misata.generate_from_schema(schema), schema, tmp_path)
        assert all(i["passed"] for i in _invariant(a, "capacity"))

    def test_exactly_one_capacity_source(self):
        with pytest.raises(ValueError):
            Capacity(table="visits", resource="place_id", start="arrived_at",
                     end="left_at", capacity=3, capacity_column="seats")
        with pytest.raises(ValueError):
            Capacity(table="visits", resource="place_id", start="arrived_at", end="left_at")


class TestIntervalRefusals:
    def test_capacity_without_a_relationship_is_refused(self):
        schema = _visits_schema(no_overlap=False, capacity=[Capacity(
            table="visits", resource="kind", start="arrived_at", end="left_at", capacity=3)])
        assert any(c.kind == "capacity_wiring" for c in find_conflicts(schema))

    def test_zero_capacity_is_refused(self):
        schema = _visits_schema(no_overlap=False, capacity=[Capacity(
            table="visits", resource="place_id", start="arrived_at", end="left_at", capacity=0)])
        with pytest.raises(InfeasibleSchema, match="capacity"):
            misata.generate_from_schema(schema)

    def test_a_non_timestamp_bound_is_refused(self):
        schema = _visits_schema(no_overlap=False)
        schema.no_overlap = [NoOverlap(table="visits", key="resident_id",
                                       start="kind", end="left_at")]
        assert any(c.kind == "no_overlap_wiring" for c in find_conflicts(schema))

    def test_parent_end_without_its_start_is_refused(self):
        schema = _visits_schema(no_overlap=False)
        schema.relationships[0] = schema.relationships[0].model_copy(
            update={"parent_end": "left_at"})
        assert any(c.kind == "containment_wiring" for c in find_conflicts(schema))


def _orders_schema(*, grid=False, during=True, curve=False, seed=9):
    """Orders placed during restaurant visits."""
    rel = Relationship(parent_table="visits", child_table="orders",
                       parent_key="visit_id", child_key="visit_id",
                       parent_time="arrived_at", child_time="ordered_at",
                       parent_end="left_at" if during else None)
    grids = [TimeGrid(table="visits", column="arrived_at", minute_grid=15, hours=(8, 20))]
    if grid:
        grids.append(TimeGrid(table="orders", column="ordered_at", minute_grid=5))
    curves = []
    if curve:
        curves.append(OutcomeCurve(table="orders", column="total", time_column="ordered_at",
                                   time_unit="day", value_mode="absolute",
                                   curve_points=[{"date": "2026-11-02", "target_value": 90000.0}]))
    return SchemaConfig(
        name="orders",
        tables=[Table(name="visits", row_count=200,
                      constraints=[Constraint(name="ordered", type="inequality",
                                              column_a="left_at", operator=">",
                                              column_b="arrived_at")]),
                Table(name="orders", row_count=600)],
        columns={
            "visits": [
                Column(name="visit_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 200}),
                Column(name="arrived_at", type="datetime", distribution_params=DAY),
                Column(name="left_at", type="datetime",
                       distribution_params={"start": "2026-11-02 09:00:00",
                                            "end": "2026-11-02 21:00:00"}),
            ],
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 600}),
                Column(name="visit_id", type="foreign_key"),
                Column(name="ordered_at", type="datetime",
                       distribution_params={"start": "2026-11-02 08:00:00",
                                            "end": "2026-11-02 21:00:00"}),
                Column(name="total", type="float", distribution_params={"min": 5, "max": 400}),
            ],
        },
        relationships=[rel],
        time_grids=grids,
        outcome_curves=curves,
        seed=seed,
    )


def _span_violations(t, *, upper=True):
    m = t["orders"].merge(t["visits"], on="visit_id")
    bad = m["ordered_at"] < m["arrived_at"]
    if upper:
        bad |= m["ordered_at"] > m["left_at"]
    return int(bad.sum())


class TestContainment:
    def test_every_child_lies_inside_its_parents_span(self):
        assert _span_violations(misata.generate_from_schema(_orders_schema())) == 0

    def test_a_grid_on_the_parent_no_longer_breaks_eligibility(self):
        """The parent's start is gridded forward after children are placed; a
        child that sat between the raw and the gridded start used to be left
        before its parent."""
        for seed in range(6):
            t = misata.generate_from_schema(_orders_schema(during=False, seed=seed))
            assert _span_violations(t, upper=False) == 0, seed

    def test_a_gridded_child_stays_on_its_grid(self):
        t = misata.generate_from_schema(_orders_schema(grid=True))
        assert _span_violations(t) == 0
        assert (t["orders"]["ordered_at"].dt.minute % 5 == 0).all()
        assert (t["orders"]["ordered_at"].dt.second == 0).all()

    def test_a_declared_curve_keeps_its_total(self):
        t = misata.generate_from_schema(_orders_schema(curve=True))
        assert _span_violations(t) == 0
        assert t["orders"]["total"].sum() == pytest.approx(90000.0, abs=0.005)

    def test_audit_and_attestation_catch_an_order_after_the_visit(self, tmp_path):
        schema = _orders_schema()
        t = misata.generate_from_schema(schema)
        first = t["orders"].index[0]
        visit = t["visits"].set_index("visit_id").loc[t["orders"].loc[first, "visit_id"]]
        t["orders"].loc[first, "ordered_at"] = visit["left_at"] + pd.Timedelta(hours=1)
        report = coherence_audit(t, schema=schema)
        assert any(f.kind == "temporal_containment" for f in report.findings)
        assert not _invariant(_attest(t, schema, tmp_path), "temporal_containment")[0]["passed"]

    def test_attestation_passes_on_generated_rows(self, tmp_path):
        schema = _orders_schema(grid=True)
        a = _attest(misata.generate_from_schema(schema), schema, tmp_path)
        assert all(i["passed"] for i in _invariant(a, "temporal_containment"))
        assert all(i["passed"] for i in _invariant(a, "time_grid"))


class TestDeterminism:
    def test_same_seed_same_bytes(self):
        cap = Capacity(table="visits", resource="place_id", start="arrived_at",
                       end="left_at", capacity_column="seats")
        a = misata.generate_from_schema(_visits_schema(capacity=[cap], places=30,
                                                       place_capacity=(20, 40)))
        b = misata.generate_from_schema(_visits_schema(capacity=[cap], places=30,
                                                       place_capacity=(20, 40)))
        assert misata.fingerprint(a)["__all__"] == misata.fingerprint(b)["__all__"]

    def test_yaml_and_dict_forms_reach_the_declarations(self, tmp_path):
        spec = tmp_path / "misata.yaml"
        spec.write_text(
            "name: v\nseed: 1\ntables:\n"
            "  rooms:\n    rows: 5\n    columns:\n"
            "      room_id: {type: int, unique: true, min: 1, max: 5}\n"
            "      beds: {type: int, min: 2, max: 2}\n"
            "  stays:\n    rows: 40\n    columns:\n"
            "      stay_id: {type: int, unique: true, min: 1, max: 40}\n"
            "      room_id: {type: foreign_key}\n"
            "      guest: {type: int, min: 1, max: 10}\n"
            "      checked_in: {type: datetime, start: '2026-01-01', end: '2026-01-03'}\n"
            "      checked_out: {type: datetime, start: '2026-01-04', end: '2026-01-06'}\n"
            "relationships:\n  - rooms.room_id -> stays.room_id\n"
            "no_overlap:\n  - {table: stays, key: guest, start: checked_in, end: checked_out}\n"
            "capacity:\n  - {table: stays, resource: room_id, start: checked_in, end: checked_out,"
            " capacity_column: beds}\n")
        from misata.yaml_schema import load_yaml_schema
        schema = load_yaml_schema(spec)
        assert schema.no_overlap[0].key == "guest"
        assert schema.capacity[0].capacity_column == "beds"
        np.testing.assert_equal(len(schema.capacity), 1)
