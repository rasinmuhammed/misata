"""Solving against pipelines Misata did not write.

Each proof declares a number that only an external engine computes, and
checks that ``misata.solve`` moves the data until that engine produces it.
The engines are real and unmodified; the tests skip when they are not
installed (``pip install taxcalc``).
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

import misata

TAX_YEAR = 2024


def _filing_units(wages: float, filers: int = 300) -> dict:
    """Households as Tax-Calculator reads them: status, dependents, wages, deductions."""
    month = f"{TAX_YEAR}-01-01"
    money = {"type": "float", "min": 0.0, "decimals": 2, "nullable": True}
    return {
        "__seed__": 42,
        "__outcome_curves__": [{
            "table": "filing_units", "column": "wage_unit", "time_column": "filed_date",
            "time_unit": "month", "value_mode": "absolute", "start_date": month,
            "curve_points": [{"month": 1, "target_value": wages}],
        }],
        "filing_units": {
            "__rows__": filers,
            "recid": {"type": "integer", "primary_key": True},
            "mars": {"type": "integer", "enum": [1, 2, 4], "probabilities": [0.45, 0.43, 0.12]},
            "n24": {"type": "integer", "enum": [0, 1, 2, 3],
                    "probabilities": [0.55, 0.20, 0.15, 0.10]},
            "wage_split": {"type": "float", "min": 0.5, "max": 0.9, "decimals": 3},
            "wage_unit": {"type": "float", "min": 15_000.0, "max": 260_000.0, "decimals": 2},
            "ltcg": {**money, "max": 45_000.0},
            "dividends": {**money, "max": 9_000.0},
            "state_local_tax": {**money, "max": 12_000.0},
            "real_estate_tax": {**money, "max": 9_000.0},
            "charitable_cash": {**money, "max": 6_000.0},
            "mortgage_interest": {**money, "max": 15_000.0},
            "filed_date": {"type": "datetime", "start": month, "end": f"{TAX_YEAR}-01-31"},
        },
    }


def _records(units: pd.DataFrame) -> pd.DataFrame:
    """Tax-Calculator's input variables (IRS form lines) for each household."""
    mars = pd.to_numeric(units["mars"]).to_numpy()
    n24 = pd.to_numeric(units["n24"]).to_numpy()
    wage = units["wage_unit"].to_numpy()
    joint = mars == 2
    primary = np.where(joint, wage * units["wage_split"].to_numpy(), wage)

    def line(column: str) -> np.ndarray:
        return units[column].fillna(0.0).to_numpy()

    return pd.DataFrame({
        "RECID": units["recid"].to_numpy(), "MARS": mars,
        "XTOT": 1 + joint.astype(int) + n24, "n24": n24,
        "e00200": wage, "e00200p": primary, "e00200s": wage - primary,
        "p23250": line("ltcg"), "e00600": line("dividends"), "e00650": line("dividends"),
        "e18400": line("state_local_tax"), "e18500": line("real_estate_tax"),
        "e19800": line("charitable_cash"), "e19200": line("mortgage_interest"),
    })


def federal_income_tax(tables):
    """Aggregate 2024 federal income tax, computed by Tax-Calculator under current law."""
    import taxcalc as tc

    records = tc.Records(data=_records(tables["filing_units"]), start_year=TAX_YEAR,
                         gfactors=None, weights=None)
    calc = tc.Calculator(policy=tc.Policy(), records=records, verbose=False)
    calc.advance_to_year(TAX_YEAR)
    calc.calc_all()
    return {"iitax": {f"{TAX_YEAR}-01": float(calc.dataframe(["iitax"])["iitax"].sum())}}


class TestTaxCalculator:
    """The U.S. federal income tax code: brackets, credits and phase-outs, none linear."""

    @pytest.fixture(scope="class")
    def result(self):
        pytest.importorskip("taxcalc")
        schema = misata.from_dict_schema(_filing_units(wages=16_000_000.0))
        target = misata.Target("iitax", "filing_units.wage_unit", {f"{TAX_YEAR}-01": 2_450_000.0})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return misata.solve(schema, misata.PythonRunner(federal_income_tax), [target],
                                tolerance="0.5%", max_iterations=20)

    def test_converges_on_the_declared_liability(self, result):
        assert result.converged, result.summary()
        assert result.reason == "converged"

    def test_the_tax_code_is_not_linear_in_wages(self, result):
        """Doubling wages more than doubles tax, so a proportional step would overshoot."""
        first, last = result.steps[0], result.steps[-1]
        wages = [next(iter(step.fed["filing_units.wage_unit"].values())) for step in (first, last)]
        taxes = [next(iter(step.measured["iitax"].values())) for step in (first, last)]
        assert taxes[1] / taxes[0] > wages[1] / wages[0] > 1

    def test_the_solved_data_reproduces_the_liability(self, result):
        tax = federal_income_tax(misata.generate_from_schema(result.schema))
        assert tax["iitax"][f"{TAX_YEAR}-01"] == pytest.approx(2_450_000.0, rel=0.005)
