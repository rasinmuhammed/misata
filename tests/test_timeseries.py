"""Time-series noise: independent by default, stationary AR(1) when asked."""
import hashlib

import numpy as np
import pytest

import misata
from misata.timeseries import (
    Anomaly,
    Seasonality,
    TimeSeriesConfig,
    TimeSeriesGenerator,
    Trend,
)


def _gen(**kw):
    return TimeSeriesGenerator().generate(TimeSeriesConfig(**kw))


def _flat_noise(phi, seed, n=200_000, std=0.1):
    # Hourly so 200k periods stay inside pandas' Timestamp range.
    df = _gen(periods=n, freq="h", start_value=1000.0, noise_std=std,
              noise_ar=phi, seed=seed)
    return (df["value"].to_numpy() - 1000.0) / 1000.0


def test_zero_ar_is_the_independent_recipe():
    df = _gen(periods=500, start_value=1000.0, noise_std=0.05, seed=7)
    rng = np.random.default_rng(7)
    expected = np.round(1000.0 + rng.normal(0, 0.05, 500) * 1000.0, 2)
    np.testing.assert_array_equal(df["value"].to_numpy(), expected)


def test_zero_ar_output_unchanged_from_before_the_option():
    # Recorded with 0.9.7.1, before noise_ar existed.
    df = _gen(seed=3, trend=Trend("exponential", 0.003),
              seasonality=[Seasonality("weekly", 0.25, 4)],
              anomalies=[Anomaly(100, 4.0, 3)])
    digest = hashlib.sha256(df["value"].to_numpy().tobytes()).hexdigest()[:16]
    assert digest == "9d64456e9d905a87"
    assert df.equals(_gen(seed=3, noise_ar=0.0, trend=Trend("exponential", 0.003),
                          seasonality=[Seasonality("weekly", 0.25, 4)],
                          anomalies=[Anomaly(100, 4.0, 3)]))


def test_ar1_lag1_autocorrelation_and_marginal_std():
    e = _flat_noise(0.9, seed=11)
    lag1 = np.corrcoef(e[:-1], e[1:])[0, 1]
    assert lag1 == pytest.approx(0.9, abs=0.01)
    assert e.std() == pytest.approx(0.1, abs=0.003)


def test_ar1_first_value_is_already_stationary():
    # Without the stationary start, e_0 would have std sqrt(1 - 0.99^2) ~ 0.14.
    e0 = [(_gen(periods=2, start_value=1000.0, noise_std=0.1, noise_ar=0.99,
                min_value=None, seed=k)["value"][0] - 1000.0) / 100.0
          for k in range(2000)]
    assert np.std(e0) == pytest.approx(1.0, abs=0.05)


def test_ar1_is_seeded():
    a = _gen(periods=1000, noise_ar=0.8, seed=5)
    b = _gen(periods=1000, noise_ar=0.8, seed=5)
    c = _gen(periods=1000, noise_ar=0.8, seed=6)
    assert a.equals(b)
    assert not np.array_equal(a["value"].to_numpy(), c["value"].to_numpy())


@pytest.mark.parametrize("phi", [1.0, 1.5, -0.1])
def test_ar_outside_unit_interval_raises(phi):
    with pytest.raises(ValueError, match="noise_ar"):
        TimeSeriesConfig(noise_ar=phi)


def test_ar_with_poisson_raises():
    with pytest.raises(ValueError, match="poisson"):
        TimeSeriesConfig(noise_ar=0.5, noise_type="poisson")


def test_reassigned_field_is_checked_at_generate():
    cfg = TimeSeriesConfig()
    cfg.noise_ar = 1.0
    with pytest.raises(ValueError, match="noise_ar"):
        TimeSeriesGenerator().generate(cfg)


def test_story_and_kwarg_set_ar():
    from misata.timeseries import _parse_timeseries_story

    assert _parse_timeseries_story("sensor readings with persistent noise").noise_ar == 0.9
    assert _parse_timeseries_story("daily revenue for a year").noise_ar == 0.0
    ts = misata.generate_timeseries(periods=5000, freq="h", noise_ar=0.7, seed=1)
    e = ts["value"].to_numpy() / 1000.0 - 1.0
    assert np.corrcoef(e[:-1], e[1:])[0, 1] == pytest.approx(0.7, abs=0.05)
