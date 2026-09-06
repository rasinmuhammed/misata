"""A declaration that cannot fit is refused, not quietly resized.

Each of these was measured emitting something other than what was asked for,
with no error and no warning:

  * 60,000 edges declared over 200 nodes emitted 19,900, because a DAG over n
    nodes holds at most n(n-1)/2 distinct edges and the engine silently stopped
    at the ceiling.
  * 50,000 rows on a unique timestamp column restricted to hourly slots inside
    business hours emitted 10,494 distinct values and 39,506 duplicates, in a
    column declared unique.
  * Waterfall inflow shares of 0.7 and 0.9 were accepted and normalised, so the
    emitted mix was not the mix written down.

A resized declaration looks exactly like an honoured one from the outside,
which is the whole reason these exist.
"""

import pytest

import misata
from misata.feasibility import InfeasibleSchema, find_conflicts


def _conflicts(schema):
    return find_conflicts(misata.from_dict_schema(schema, seed=1))


def _kinds(schema):
    return {c.kind for c in _conflicts(schema)}


DAG = {
    "nodes": {"__rows__": 200, "id": {"type": "integer", "primary_key": True}},
    "edges": {"__rows__": 60000, "parent": {"type": "integer"},
              "child": {"type": "integer"}},
    "__dag_edges__": [{"name": "t", "table": "edges", "node_table": "nodes",
                       "node_key": "id", "from_column": "parent",
                       "to_column": "child"}],
}


class TestDagCapacity:
    def test_more_edges_than_a_dag_can_hold_is_refused(self):
        assert "dag_edges_exceed_capacity" in _kinds(DAG)

    def test_the_arithmetic_names_the_ceiling(self):
        """A refusal that does not show its working is a wall, not an error."""
        conflict = next(c for c in _conflicts(DAG)
                        if c.kind == "dag_edges_exceed_capacity")
        assert "19,900" in conflict.arithmetic
        assert "60,000" in conflict.arithmetic
        assert conflict.remedy

    def test_an_edge_count_that_fits_is_left_alone(self):
        ok = {**DAG, "edges": {**DAG["edges"], "__rows__": 5000}}
        assert "dag_edges_exceed_capacity" not in _kinds(ok)


GRID = {
    "appt": {"__rows__": 50000,
             "slot": {"type": "datetime", "unique": True,
                      "start": "2026-01-01", "end": "2026-12-31"}},
    "__time_grids__": [{"table": "appt", "column": "slot",
                        "minute_grid": 60, "hours": [9, 17]}],
}


class TestGridCapacity:
    def test_more_unique_rows_than_slots_is_refused(self):
        assert "time_grid_exceeds_slots" in _kinds(GRID)

    def test_it_counts_the_slots_the_grid_actually_leaves(self):
        conflict = next(c for c in _conflicts(GRID)
                        if c.kind == "time_grid_exceeds_slots")
        # 365 days, 8 business hours, one slot an hour.
        assert "2,920" in conflict.arithmetic

    def test_a_column_that_is_not_unique_may_repeat(self):
        """Repetition is only a contradiction when uniqueness was declared."""
        loose = {**GRID, "appt": {"__rows__": 50000,
                                  "slot": {"type": "datetime",
                                           "start": "2026-01-01",
                                           "end": "2026-12-31"}}}
        assert "time_grid_exceeds_slots" not in _kinds(loose)

    def test_an_undated_column_uses_the_range_the_engine_will_actually_use(self):
        """Writing no dates does not mean no dates. The engine fills in
        2020-01-01 to 2024-12-31, generates inside that window, and the slots
        are just as countable, so the refusal is right rather than a guess.

        I expected the opposite when writing this and the check was correct."""
        undated = {"appt": {"__rows__": 50000,
                            "slot": {"type": "datetime", "unique": True}},
                   "__time_grids__": [{"table": "appt", "column": "slot",
                                       "minute_grid": 60, "hours": [9, 17]}]}
        conflict = next(c for c in _conflicts(undated)
                        if c.kind == "time_grid_exceeds_slots")
        # Five default years of business hours, one slot an hour.
        assert "14,616" in conflict.arithmetic, conflict.arithmetic

    def test_a_range_that_cannot_be_read_is_not_guessed_at(self):
        """A check that cannot be computed says nothing rather than inventing a
        number and refusing a schema that is perfectly fine."""
        broken = {"appt": {"__rows__": 50000,
                           "slot": {"type": "datetime", "unique": True,
                                    "start": "not-a-date", "end": "also-not"}},
                  "__time_grids__": [{"table": "appt", "column": "slot",
                                      "minute_grid": 60, "hours": [9, 17]}]}
        assert "time_grid_exceeds_slots" not in _kinds(broken)


class TestIdentityShapes:
    def _waterfall(self, inflow):
        return {"m": {"__rows__": 300, "period": {"type": "string"},
                      "movement_type": {"type": "string"},
                      "amount": {"type": "float"}},
                "__waterfalls__": [{"table": "m", "starting_value": 1000,
                                    "points": [{"period": "2026-01",
                                                "ending_value": 1200}],
                                    "inflow_shares": inflow,
                                    "outflow_shares": {"churn": 1.0}}]}

    def test_shares_that_do_not_split_the_whole_are_refused(self):
        assert "waterfall_shares_not_a_split" in _kinds(
            self._waterfall({"new": 0.7, "expansion": 0.9}))

    def test_a_real_split_passes(self):
        assert "waterfall_shares_not_a_split" not in _kinds(
            self._waterfall({"new": 0.7, "expansion": 0.3}))

    def _ledger(self, rows, lo=50, hi=500, periods=("2026-01", "2026-02", "2026-03")):
        return {"inv": {"__rows__": rows, "sku": {"type": "string"},
                        "period": {"type": "string"}, "o": {"type": "float"},
                        "r": {"type": "float"}, "s": {"type": "float"},
                        "c": {"type": "float"}},
                "__stock_flows__": [{"table": "inv", "sku_column": "sku",
                                     "period_column": "period", "open_column": "o",
                                     "received_column": "r", "shipped_column": "s",
                                     "close_column": "c", "periods": list(periods),
                                     "starting_min": lo, "starting_max": hi}]}

    def test_fewer_rows_than_periods_cannot_chain(self):
        assert "stock_flow_rows_below_periods" in _kinds(self._ledger(2))

    def test_enough_rows_for_one_chain_is_enough(self):
        assert "stock_flow_rows_below_periods" not in _kinds(self._ledger(10))

    def test_an_inverted_opening_range_is_refused(self):
        assert "stock_flow_inverted_start" in _kinds(self._ledger(50, lo=900, hi=100))


def test_generation_raises_rather_than_resizing():
    """The point of all of it: the caller finds out before the data exists."""
    with pytest.raises(InfeasibleSchema) as excinfo:
        misata.generate_from_schema(misata.from_dict_schema(DAG, seed=1))
    assert "19,900" in str(excinfo.value)
