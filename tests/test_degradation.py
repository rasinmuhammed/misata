"""Units that wear out, and a remaining-life label that is exact.

The public predictive-maintenance datasets mostly draw every row independently,
so a machine has no history: in AI4I 2020 tool wear falls as often as it rises
between consecutive readings for the same machine, and there is no
remaining-life label at all. These tests pin the properties that make the
difference.
"""

import numpy as np
import pytest

from misata.degradation import defect_frequencies, generate, verify
from misata.schema import Degradation, SensorResponse


def spec(**kw):
    base = dict(
        table="readings", units=40, life_mean=150, life_std=30,
        life_min=60, life_max=300,
        responses=[
            SensorResponse(column="tool_wear_min", baseline=0, at_failure=250,
                           noise=1.0, decimals=0, monotonic=True),
            SensorResponse(column="vibration_mm_s", baseline=0.8, at_failure=5.2,
                           shape="exponential", noise=0.05),
        ],
    )
    base.update(kw)
    return Degradation(**base)


class TestBearingPhysics:
    """Fault frequencies follow from geometry. Nothing here is fitted, so the
    numbers are checkable against any vibration handbook."""

    def test_skf_6205_matches_the_published_value(self):
        """The bearing on the Case Western rig, at its documented speed."""
        f = defect_frequencies(1797)
        assert f["BPFO"] == pytest.approx(107.36, abs=0.01)
        assert f["BPFI"] == pytest.approx(162.19, abs=0.01)
        assert f["shaft"] == pytest.approx(29.95, abs=0.01)

    def test_inner_race_always_rings_faster_than_outer(self):
        """BPFI carries a (1 + ratio) where BPFO carries (1 - ratio), so the
        ordering holds for any bearing rather than just this one."""
        for rpm in (600, 1200, 1797, 3600):
            f = defect_frequencies(rpm)
            assert f["BPFI"] > f["BPFO"] > f["FTF"]

    def test_frequencies_scale_linearly_with_speed(self):
        a, b = defect_frequencies(900), defect_frequencies(1800)
        for k in ("BPFO", "BPFI", "BSF", "FTF"):
            assert b[k] == pytest.approx(2 * a[k], rel=1e-9)

    def test_impossible_geometry_is_refused(self):
        with pytest.raises(ValueError):
            defect_frequencies(1797, pitch_diameter=0)
        with pytest.raises(ValueError):
            defect_frequencies(1797, n_elements=0)


class TestRemainingLifeIsExact:
    def test_the_verifier_agrees(self):
        s = spec()
        report = verify(generate(s, seed=1), s)
        assert report["rul_exact"], report["findings"]
        assert report["units"] == 40

    def test_rul_is_life_minus_cycle_for_every_row(self):
        s = spec()
        df = generate(s, seed=2)
        for _, g in df.groupby("unit_id"):
            life = g.cycle.max()
            assert np.array_equal(g.rul_cycles.to_numpy(), life - g.cycle.to_numpy())

    def test_each_unit_fails_exactly_once_at_rul_zero(self):
        df = generate(spec(), seed=3)
        per_unit = df.groupby("unit_id").machine_failure.sum()
        assert (per_unit == 1).all()
        assert (df.loc[df.machine_failure == 1, "rul_cycles"] == 0).all()

    def test_row_count_is_the_sum_of_the_lives(self):
        """Not a number anyone chose. Truncating a history at a round number
        would throw away the end of the life, which is the part that matters."""
        df = generate(spec(), seed=4)
        assert len(df) == df.groupby("unit_id").cycle.max().sum()


class TestDegradationIsReal:
    def test_damage_rises_to_exactly_one(self):
        df = generate(spec(), seed=5)
        for _, g in df.groupby("unit_id"):
            d = g.sort_values("cycle").damage.to_numpy()
            assert (np.diff(d) > 0).all(), "damage must be strictly increasing"
            assert d[-1] == pytest.approx(1.0, abs=1e-6)

    def test_a_cumulative_measurement_never_falls(self):
        """Material does not come back. Noise alone made wear decrease on about
        a third of consecutive readings, which is the exact criticism aimed at
        AI4I, so `monotonic` has to hold under noise."""
        df = generate(spec(), seed=6)
        drops = df.groupby("unit_id").tool_wear_min.apply(
            lambda s: (s.diff().dropna() < 0).sum()).sum()
        assert drops == 0

    def test_wear_tracks_time_rather_than_wandering(self):
        """AI4I scores -0.024 here."""
        df = generate(spec(), seed=7)
        assert df.cycle.corr(df.tool_wear_min) > 0.85

    def test_sensors_carry_the_damage_signature(self):
        df = generate(spec(), seed=8)
        assert df.damage.corr(df.vibration_mm_s) > 0.8

    def test_an_exponential_response_stays_flat_then_climbs(self):
        """A health indicator that rises linearly is not what a spall does."""
        df = generate(spec(units=1, life_mean=200, life_std=0), seed=9)
        v = df.sort_values("cycle").vibration_mm_s.to_numpy()
        first_half = v[: len(v) // 2].max() - v[0]
        second_half = v[-1] - v[len(v) // 2]
        assert second_half > 3 * first_half


class TestTheLabelIsLearnable:
    def test_a_model_beats_guessing_the_mean_on_unseen_units(self):
        """The point of an exact label is that something can learn it. Held-out
        units, so this is generalisation across machines rather than
        interpolation within one."""
        pytest.importorskip("sklearn")
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import mean_absolute_error

        df = generate(spec(units=60), seed=10)
        units = df.unit_id.unique()
        tr = df[df.unit_id.isin(units[:45])]
        te = df[df.unit_id.isin(units[45:])]
        X = ["tool_wear_min", "vibration_mm_s"]

        model = RandomForestRegressor(n_estimators=60, random_state=0).fit(
            tr[X], tr.rul_cycles)
        mae = mean_absolute_error(te.rul_cycles, model.predict(te[X]))
        naive = mean_absolute_error(
            te.rul_cycles, np.full(len(te), tr.rul_cycles.mean()))
        assert mae < naive * 0.6, f"MAE {mae:.1f} vs naive {naive:.1f}"


class TestRefusals:
    def test_an_impossible_life_range_is_refused(self):
        with pytest.raises(ValueError, match="life_min"):
            generate(spec(life_min=300, life_max=100), seed=1)

    def test_an_empty_fleet_is_refused(self):
        with pytest.raises(ValueError, match="at least one unit"):
            generate(spec(units=0), seed=1)

    def test_failure_mode_weights_must_be_positive(self):
        with pytest.raises(ValueError, match="sum to more than zero"):
            generate(spec(failure_mode_column="mode",
                          failure_modes={"A": 0.0, "B": 0.0}), seed=1)


class TestItIsDeclarable:
    def test_a_degradation_survives_the_yaml_file(self, tmp_path):
        """Three defects this week were a declaration that loaded empty."""
        import misata
        path = tmp_path / "misata.yaml"
        path.write_text("""
name: fleet
seed: 7
tables:
  readings:
    rows: 10
    columns:
      quality: {type: categorical, choices: [L, M, H]}
degradations:
  - table: readings
    units: 12
    life_mean: 100
    life_std: 10
    life_min: 50
    life_max: 200
    failure_mode_column: failure_mode
    failure_modes: {TWF: 0.6, HDF: 0.4}
    responses:
      - {column: tool_wear_min, baseline: 0, at_failure: 200, monotonic: true, decimals: 0}
""")
        schema = misata.load_yaml_schema(path)
        assert len(schema.degradations) == 1
        d = schema.degradations[0]
        assert d.units == 12
        assert d.responses and d.responses[0].monotonic is True

        tables = misata.generate_from_schema(schema)["readings"]
        assert "rul_cycles" in tables.columns
        assert tables.unit_id.nunique() == 12
        # Columns the table declares itself still arrive.
        assert "quality" in tables.columns

    def test_a_degradation_survives_the_dict_path_too(self):
        """Registering the envelope key is not the same as building the object.

        The key was accepted by `from_dict_schema` and nothing was constructed,
        so the contract test passed while the declaration did nothing. Both
        schema entry points have to build it, because wiring one is how four
        earlier defects shipped.
        """
        import misata
        cfg = misata.from_dict_schema({
            "readings": {"__rows__": 5,
                         "quality": {"type": "categorical", "choices": ["L", "H"]}},
            "__degradations__": [{
                "table": "readings", "units": 6,
                "life_mean": 40, "life_std": 5, "life_min": 20, "life_max": 80,
                "responses": [{"column": "wear", "baseline": 0, "at_failure": 100,
                               "monotonic": True, "decimals": 0}],
            }],
        })
        assert len(cfg.degradations) == 1, "envelope key registered but inert"
        table = misata.generate_from_schema(cfg)["readings"]
        assert table.unit_id.nunique() == 6
        assert "rul_cycles" in table.columns
