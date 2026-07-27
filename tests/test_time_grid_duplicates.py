"""Tests for TimeGrid and Duplicates (0.9.1).

Both existed before as behaviour and neither could be asserted. Timestamps were
snapped onto a grid by guessing from the column name, and duplicates were
sprayed at a probability, so a test written against either could only check
that something roughly happened.

These are the declared forms. The contract:

  * TimeGrid — every value sits on the declared grid, inside the declared
    hours, and no value ever moved earlier than it was.
  * Duplicates — ``len(df) - len(df[subset].drop_duplicates())`` is exactly
    the declared number, the keys stay distinct, and the row count is unmoved.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import misata
from misata.coherence import coherence_audit
from misata.dynamics import apply_duplicates, apply_time_grid
from misata.schema import (SchemaConfig, Table, Column, Relationship,
                           TimeGrid, Duplicates)

warnings.filterwarnings("ignore")


def _tickets(row_count=400, **over):
    kwargs = dict(
        name="grid", seed=3,
        tables=[Table(name="tickets", row_count=row_count)],
        columns={
            "tickets": [
                Column(name="ticket_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": row_count}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-06-30"}),
                Column(name="priority", type="categorical",
                       distribution_params={"choices": ["low", "high"]}),
            ],
        },
    )
    kwargs.update(over)
    return SchemaConfig(**kwargs)


# --------------------------------------------------------------------------- #
# TimeGrid
# --------------------------------------------------------------------------- #

class TestTimeGrid:

    def test_every_value_sits_on_the_declared_grid(self):
        cfg = _tickets(time_grids=[
            TimeGrid(table="tickets", column="created_at", minute_grid=15)])
        col = pd.to_datetime(misata.generate_from_schema(cfg)["tickets"]["created_at"])
        assert (col.dt.minute % 15 == 0).all()
        assert (col.dt.second == 0).all()
        assert (col.dt.microsecond == 0).all()

    def test_hours_window_is_respected(self):
        cfg = _tickets(time_grids=[
            TimeGrid(table="tickets", column="created_at",
                     minute_grid=30, hours=(9, 17))])
        col = pd.to_datetime(misata.generate_from_schema(cfg)["tickets"]["created_at"])
        assert col.dt.hour.between(9, 16).all()
        assert (col.dt.minute % 30 == 0).all()

    def test_a_value_is_never_moved_earlier(self):
        """The property the whole design rests on.

        Causality is enforced before this pass runs and every causal guarantee
        is a lower bound, so a grid that could lower a timestamp could silently
        undo one. The first version could, and did, by 56 seconds.
        """
        before = misata.generate_from_schema(_tickets())["tickets"]
        cfg = _tickets(time_grids=[
            TimeGrid(table="tickets", column="created_at",
                     minute_grid=60, hours=(9, 17))])
        after = misata.generate_from_schema(cfg)["tickets"]
        assert (pd.to_datetime(after["created_at"])
                >= pd.to_datetime(before["created_at"])).all()

    def test_seconds_uniform_keeps_seconds(self):
        cfg = _tickets(time_grids=[
            TimeGrid(table="tickets", column="created_at",
                     minute_grid=15, seconds="uniform")])
        col = pd.to_datetime(misata.generate_from_schema(cfg)["tickets"]["created_at"])
        assert (col.dt.second != 0).any()

    def test_more_than_one_slot_is_used(self):
        """A grid that collapsed every row onto one slot would also pass."""
        cfg = _tickets(time_grids=[
            TimeGrid(table="tickets", column="created_at", minute_grid=15)])
        col = pd.to_datetime(misata.generate_from_schema(cfg)["tickets"]["created_at"])
        assert col.dt.minute.nunique() == 4
        assert col.dt.hour.nunique() > 4

    def test_row_ordering_survives_the_grid(self):
        """Moving one column forward must not push it past a later one."""
        cfg = SchemaConfig(
            name="pair", seed=4,
            tables=[Table(name="tickets", row_count=500)],
            columns={"tickets": [
                Column(name="ticket_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 500}),
                Column(name="created_at", type="datetime",
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-01-31"}),
                Column(name="resolved_at", type="datetime",
                       distribution_params={"start": "2024-01-01",
                                            "end": "2024-01-31",
                                            "after_column": "created_at"}),
            ]},
            time_grids=[TimeGrid(table="tickets", column="created_at",
                                 minute_grid=60, hours=(9, 17))],
        )
        df = misata.generate_from_schema(cfg)["tickets"]
        pair = df[df["resolved_at"].notna()]
        assert (pd.to_datetime(pair["resolved_at"])
                >= pd.to_datetime(pair["created_at"])).all()

    def test_nulls_stay_null(self):
        df = pd.DataFrame({"t": pd.to_datetime(
            ["2024-01-01 10:03:22", None, "2024-01-02 23:58:01"])})
        tables = {"x": df}
        spec = TimeGrid(table="x", column="t", minute_grid=15)
        out = apply_time_grid(tables, spec, np.random.default_rng(0))["x"]
        assert pd.isna(out["t"].iloc[1])
        assert out["t"].iloc[0] == pd.Timestamp("2024-01-01 10:15:00")
        # 23:58 has no slot left in the day, so it opens the next one.
        assert out["t"].iloc[2] == pd.Timestamp("2024-01-03 00:00:00")

    @pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"])
    def test_result_does_not_depend_on_datetime_resolution(self, unit):
        """Caught by CI, not by this machine.

        `Series.astype("int64")` returns the column's integers in the column's
        own unit, and newer pandas builds hand back `datetime64[us]` where
        older ones gave `datetime64[ns]`. Reading microseconds as nanoseconds
        is wrong by a factor of 1000, which put a 2024 timestamp in January
        1970 on three interpreters and none locally.
        """
        base = pd.to_datetime(["2024-01-01 10:03:22", "2024-03-15 14:47:09"])
        df = pd.DataFrame({"t": pd.Series(base).astype(f"datetime64[{unit}]")})
        spec = TimeGrid(table="x", column="t", minute_grid=15)
        out = apply_time_grid({"x": df}, spec, np.random.default_rng(0))["x"]
        got = pd.to_datetime(out["t"]).tolist()
        assert got == [pd.Timestamp("2024-01-01 10:15:00"),
                       pd.Timestamp("2024-03-15 15:00:00")]

    def test_grid_with_no_slot_in_the_window_warns_and_leaves_it_alone(self):
        df = pd.DataFrame({"t": pd.to_datetime(["2024-01-01 10:03:22"])})
        spec = TimeGrid(table="x", column="t", minute_grid=1440, hours=(9, 10))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = apply_time_grid({"x": df}, spec, np.random.default_rng(0))["x"]
        assert any("no slot inside" in str(w.message) for w in caught)
        assert out["t"].iloc[0] == pd.Timestamp("2024-01-01 10:03:22")

    def test_audit_catches_an_off_grid_value(self):
        cfg = _tickets(time_grids=[
            TimeGrid(table="tickets", column="created_at",
                     minute_grid=15, hours=(9, 17))])
        tables = misata.generate_from_schema(cfg)
        assert not [f for f in coherence_audit(tables, schema=cfg).findings
                    if f.kind == "time_grid"]

        tables["tickets"].loc[0, "created_at"] = pd.Timestamp("2024-03-01 03:07:13")
        kinds = [f for f in coherence_audit(tables, schema=cfg).findings
                 if f.kind == "time_grid"]
        assert len(kinds) == 2   # off the grid, and outside the window
        assert sum(f.rows_affected for f in kinds) >= 2

    def test_invalid_hour_window_is_rejected_at_declaration_time(self):
        with pytest.raises(ValueError):
            TimeGrid(table="t", column="c", hours=(17, 9))
        with pytest.raises(ValueError):
            TimeGrid(table="t", column="c", hours=(9, 25))


# --------------------------------------------------------------------------- #
# Duplicates
# --------------------------------------------------------------------------- #

class TestDuplicates:

    def _cfg(self, **over):
        kw = dict(duplicates=[
            Duplicates(table="tickets", count=20, keys=["ticket_id"])])
        kw.update(over)
        return _tickets(**kw)

    def test_exactly_the_declared_count(self):
        cfg = self._cfg()
        df = misata.generate_from_schema(cfg)["tickets"]
        subset = [c for c in df.columns if c != "ticket_id"]
        assert len(df) - len(df[subset].drop_duplicates()) == 20

    def test_fraction_is_a_count_not_a_probability(self):
        cfg = self._cfg(duplicates=[
            Duplicates(table="tickets", fraction=0.05, keys=["ticket_id"])])
        df = misata.generate_from_schema(cfg)["tickets"]
        subset = [c for c in df.columns if c != "ticket_id"]
        assert len(df) - len(df[subset].drop_duplicates()) == 20   # 5% of 400

    def test_keys_stay_distinct(self):
        df = misata.generate_from_schema(self._cfg())["tickets"]
        assert df["ticket_id"].is_unique

    def test_row_count_is_unmoved(self):
        assert len(misata.generate_from_schema(self._cfg())["tickets"]) == 400

    def test_dtypes_survive(self):
        """Copying through a 2-D block would widen every int column to object."""
        plain = misata.generate_from_schema(_tickets())["tickets"]
        duped = misata.generate_from_schema(self._cfg())["tickets"]
        assert duped.dtypes.to_dict() == plain.dtypes.to_dict()

    def test_explicit_subset_is_honoured(self):
        cfg = self._cfg(duplicates=[
            Duplicates(table="tickets", count=10, keys=["ticket_id"],
                       subset=["created_at"])])
        df = misata.generate_from_schema(cfg)["tickets"]
        assert len(df) - len(df[["created_at"]].drop_duplicates()) == 10

    def test_a_subset_too_coarse_to_control_warns_and_changes_nothing(self):
        df = pd.DataFrame({"id": range(50), "flag": ["a"] * 25 + ["b"] * 25})
        spec = Duplicates(table="x", count=3, keys=["id"], subset=["flag"])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = apply_duplicates({"x": df.copy()}, spec,
                                   np.random.default_rng(0))["x"]
        assert any("not distinct enough" in str(w.message) for w in caught)
        pd.testing.assert_frame_equal(out, df)

    def test_declaring_neither_count_nor_fraction_is_rejected(self):
        with pytest.raises(ValueError):
            Duplicates(table="t")

    def test_audit_catches_a_wrong_count(self):
        cfg = self._cfg()
        tables = misata.generate_from_schema(cfg)
        assert not [f for f in coherence_audit(tables, schema=cfg).findings
                    if f.kind == "duplicate_count"]

        # Break one duplicate pair by hand. It has to be a row that actually
        # is a copy, or the count would still be right and there would be
        # nothing for the audit to find.
        df = tables["tickets"]
        subset = [c for c in df.columns if c != "ticket_id"]
        victim = df.index[df.duplicated(subset=subset, keep=False)][0]
        df.loc[victim, "created_at"] = pd.Timestamp("1999-01-01")
        findings = [f for f in coherence_audit(tables, schema=cfg).findings
                    if f.kind == "duplicate_count"]
        assert findings and "found" in findings[0].message

    def test_deterministic_under_the_same_seed(self):
        a = misata.generate_from_schema(self._cfg())["tickets"]
        b = misata.generate_from_schema(self._cfg())["tickets"]
        pd.testing.assert_frame_equal(a, b)
