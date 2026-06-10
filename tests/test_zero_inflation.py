"""Tests for zero-inflated distributions (structural zeros).

Real monetary/usage columns often have a spike at 0 (free-tier, no-spend periods) on top of
a positive tail. The `zero_inflate` param injects that spike for any base distribution,
applied after the min clamp so structural zeros are not lifted to `min`.
"""
import warnings
import numpy as np
import misata
from misata.schema import SchemaConfig, Table, Column

warnings.filterwarnings("ignore")


def _zi_schema(p, seed=1, mn=1):
    return SchemaConfig(name="z", tables=[Table(name="t", row_count=5000)],
        columns={"t": [Column(name="spend", type="float", distribution_params={
            "distribution": "lognormal", "mu": 4, "sigma": 0.6, "min": mn,
            "zero_inflate": p, "decimals": 2})]}, seed=seed)


def test_zero_fraction_matches_target():
    t = misata.generate_from_schema(_zi_schema(0.3))
    frac = (t["t"]["spend"] == 0).mean()
    assert abs(frac - 0.3) < 0.03


def test_structural_zeros_bypass_min_clamp():
    t = misata.generate_from_schema(_zi_schema(0.3, mn=5))
    s = t["t"]["spend"]
    assert (s == 0).any()            # zeros exist
    assert s[s > 0].min() >= 5       # positives respect the min clamp


def test_keeps_positive_tail():
    t = misata.generate_from_schema(_zi_schema(0.3))
    s = t["t"]["spend"]
    assert (s > 10).any()            # tail survives


def test_dict_form_p():
    schema = SchemaConfig(name="z", tables=[Table(name="t", row_count=3000)],
        columns={"t": [Column(name="x", type="float", distribution_params={
            "distribution": "lognormal", "mu": 3, "sigma": 0.5,
            "zero_inflate": {"p": 0.5}})]}, seed=2)
    t = misata.generate_from_schema(schema)
    assert abs((t["t"]["x"] == 0).mean() - 0.5) < 0.04


def test_zero_p_is_noop():
    t = misata.generate_from_schema(_zi_schema(0.0))
    assert (t["t"]["spend"] == 0).mean() == 0.0


def test_deterministic():
    a = misata.generate_from_schema(_zi_schema(0.3, seed=9))
    b = misata.generate_from_schema(_zi_schema(0.3, seed=9))
    assert (a["t"]["spend"].values == b["t"]["spend"].values).all()
