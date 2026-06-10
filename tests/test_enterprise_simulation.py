"""Enterprise simulation: deeply interconnected, coherent multi-table datasets.

Proves the 0.8.0.3 breakthrough — a complete company dataset where every value ties
together: cross-table formulas (billed = hours * employee.rate), multi-hop roll-ups
(project.revenue = sum of billed), capacity constraints that recompute derived columns,
and dates that fall within parent windows. All exact, all FK-safe.
"""
import warnings
import pandas as pd
import misata
from misata.schema import SchemaConfig, Table, Column, Relationship, Constraint

warnings.filterwarnings("ignore")


def _pharma(seed=3, cap_value=24):
    cap = Constraint(name="daily_cap", type="sum_limit", column="hours",
                     group_by=["employee_id", "work_date"], value=cap_value, action="cap")
    return SchemaConfig(
        name="pharma",
        tables=[Table(name="clients", row_count=15),
                Table(name="employees", row_count=80),
                Table(name="projects", row_count=25),
                Table(name="timesheets", row_count=4000, constraints=[cap])],
        columns={
            "clients": [Column(name="client_id", type="int", unique=True,
                               distribution_params={"min": 1, "max": 15})],
            "employees": [
                Column(name="employee_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 80}),
                Column(name="hourly_rate", type="float",
                       distribution_params={"distribution": "normal", "mean": 95, "std": 25,
                                            "min": 45, "decimals": 2})],
            "projects": [
                Column(name="project_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 25}),
                Column(name="client_id", type="foreign_key",
                       distribution_params={"references": "clients.client_id"}),
                Column(name="start_date", type="date",
                       distribution_params={"start": "2023-01-01", "end": "2023-09-30"}),
                Column(name="revenue_usd", type="float", distribution_params={
                    "rollup": {"from_table": "timesheets", "fk": "project_id",
                               "agg": "sum", "column": "billed_usd"}}),
                Column(name="total_hours", type="float", distribution_params={
                    "rollup": {"from_table": "timesheets", "fk": "project_id",
                               "agg": "sum", "column": "hours"}})],
            "timesheets": [
                Column(name="timesheet_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 4000}),
                Column(name="employee_id", type="foreign_key",
                       distribution_params={"references": "employees.employee_id"}),
                Column(name="project_id", type="foreign_key",
                       distribution_params={"references": "projects.project_id"}),
                Column(name="work_date", type="date",
                       distribution_params={"relative_to": "projects.start_date",
                                            "min_delta_days": 0, "max_delta_days": 120}),
                Column(name="hours", type="float",
                       distribution_params={"distribution": "normal", "mean": 6, "std": 2,
                                            "min": 1, "max": 10, "decimals": 1}),
                Column(name="billed_usd", type="float",
                       distribution_params={"formula": "hours * @employees.hourly_rate"})]},
        relationships=[
            Relationship(parent_table="clients", child_table="projects",
                         parent_key="client_id", child_key="client_id"),
            Relationship(parent_table="employees", child_table="timesheets",
                         parent_key="employee_id", child_key="employee_id"),
            Relationship(parent_table="projects", child_table="timesheets",
                         parent_key="project_id", child_key="project_id")],
        seed=seed,
    )


class TestEnterpriseChain:
    def setup_method(self):
        self.t = misata.generate_from_schema(_pharma())

    def test_fk_integrity_all_edges(self):
        t = self.t
        for parent, child, key in [("clients", "projects", "client_id"),
                                   ("employees", "timesheets", "employee_id"),
                                   ("projects", "timesheets", "project_id")]:
            assert (~t[child][key].isin(set(t[parent][key]))).sum() == 0

    def test_cross_table_formula_exact(self):
        ts = self.t["timesheets"]
        m = ts.merge(self.t["employees"][["employee_id", "hourly_rate"]], on="employee_id")
        assert (m["billed_usd"] - m["hours"] * m["hourly_rate"]).abs().max() < 0.01

    def test_revenue_rollup_exact(self):
        ts, proj = self.t["timesheets"], self.t["projects"]
        rev = ts.groupby("project_id")["billed_usd"].sum()
        pm = proj.set_index("project_id")
        assert (pm["revenue_usd"] - rev.reindex(pm.index).fillna(0)).abs().max() < 0.01

    def test_hours_rollup_exact(self):
        ts, proj = self.t["timesheets"], self.t["projects"]
        hrs = ts.groupby("project_id")["hours"].sum()
        pm = proj.set_index("project_id")
        assert (pm["total_hours"] - hrs.reindex(pm.index).fillna(0)).abs().max() < 0.01

    def test_dates_within_parent_window(self):
        d = self.t["timesheets"].merge(self.t["projects"][["project_id", "start_date"]],
                                       on="project_id")
        delta = (pd.to_datetime(d["work_date"]) - pd.to_datetime(d["start_date"])).dt.days
        assert (delta >= 0).all()


class TestCapacityCapRecomputesDerived:
    """When a capacity cap reduces a base column, derived formula/rollup columns must
    recompute from the constrained value (the ordering bug fixed in 0.8.0.3)."""

    def test_binding_cap_keeps_billed_consistent(self):
        # tight cap that WILL bind, then verify billed = (capped) hours * rate
        t = misata.generate_from_schema(_pharma(seed=1, cap_value=12))
        ts = t["timesheets"]
        daily = ts.groupby(["employee_id", "work_date"])["hours"].sum()
        assert daily.max() <= 12.01, "cap did not bind"
        m = ts.merge(t["employees"][["employee_id", "hourly_rate"]], on="employee_id")
        assert (m["billed_usd"] - m["hours"] * m["hourly_rate"]).abs().max() < 0.01
        # and revenue rolls up the recomputed billed
        rev = ts.groupby("project_id")["billed_usd"].sum()
        pm = t["projects"].set_index("project_id")
        assert (pm["revenue_usd"] - rev.reindex(pm.index).fillna(0)).abs().max() < 0.01


class TestEnterpriseViaDict:
    """The whole chain must work from a plain dict (LLM / non-Python entry point)."""

    def test_full_chain_from_dict(self):
        schema = misata.from_dict_schema({
            "employees": {
                "employee_id": {"type": "integer", "primary_key": True},
                "hourly_rate": {"type": "float", "distribution": "normal",
                                "mean": 90, "std": 20, "min": 40},
            },
            "projects": {
                "project_id": {"type": "integer", "primary_key": True},
                "revenue_usd": {"type": "float", "rollup": {
                    "from_table": "timesheets", "fk": "project_id",
                    "agg": "sum", "column": "billed_usd"}},
            },
            "timesheets": {
                "timesheet_id": {"type": "integer", "primary_key": True},
                "employee_id": {"type": "integer",
                                "foreign_key": {"table": "employees", "column": "employee_id"}},
                "project_id": {"type": "integer",
                               "foreign_key": {"table": "projects", "column": "project_id"}},
                "hours": {"type": "float", "distribution": "normal",
                          "mean": 6, "std": 2, "min": 1, "max": 12},
                "billed_usd": {"type": "float", "formula": "hours * @employees.hourly_rate"},
            },
        }, row_count=2000)
        t = misata.generate_from_schema(schema)
        m = t["timesheets"].merge(t["employees"][["employee_id", "hourly_rate"]], on="employee_id")
        assert (m["billed_usd"] - m["hours"] * m["hourly_rate"]).abs().max() < 0.01
        rev = t["timesheets"].groupby("project_id")["billed_usd"].sum()
        pm = t["projects"].set_index("project_id")
        assert (pm["revenue_usd"] - rev.reindex(pm.index).fillna(0)).abs().max() < 0.01


class TestPharmaDomainFromOneSentence:
    """The flagship: a full, coherent pharma CRO from a single natural-language sentence."""

    def setup_method(self):
        self.t = misata.generate(
            "A pharmaceutical CRO with 60 employees, 20 clinical research projects, and clients",
            rows=3000, seed=5)

    def test_produces_full_company(self):
        for tbl in ("clients", "employees", "research_projects", "timesheets"):
            assert tbl in self.t and len(self.t[tbl]) > 0

    def test_fk_integrity(self):
        t = self.t
        for parent, child, key in [("clients", "research_projects", "client_id"),
                                   ("employees", "timesheets", "employee_id"),
                                   ("research_projects", "timesheets", "project_id")]:
            assert (~t[child][key].isin(set(t[parent][key]))).sum() == 0

    def test_billed_and_revenue_reconcile(self):
        t = self.t
        m = t["timesheets"].merge(t["employees"][["employee_id", "hourly_rate"]], on="employee_id")
        assert (m["billed_usd"] - m["hours"] * m["hourly_rate"]).abs().max() < 0.01
        rev = t["timesheets"].groupby("project_id")["billed_usd"].sum()
        pm = t["research_projects"].set_index("project_id")
        assert (pm["revenue_usd"] - rev.reindex(pm.index).fillna(0)).abs().max() < 0.01

    def test_timesheets_within_project_window(self):
        d = self.t["timesheets"].merge(
            self.t["research_projects"][["project_id", "start_date"]], on="project_id")
        delta = (pd.to_datetime(d["date"]) - pd.to_datetime(d["start_date"])).dt.days
        assert (delta >= 0).all()

    def test_daily_hours_capped(self):
        daily = self.t["timesheets"].groupby(["employee_id", "date"])["hours"].sum()
        assert daily.max() <= 24.01
