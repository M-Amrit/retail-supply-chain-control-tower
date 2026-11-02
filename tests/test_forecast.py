import numpy as np, pandas as pd
from src import forecast


def _weekly(n=84, seed=0, noise=2.0):
    rng = np.random.default_rng(seed)
    ds = pd.date_range("2026-07-01", periods=n, freq="D")
    y = 100 + np.array([0, 0, 5, 5, 15, 30, 20])[ds.dayofweek] + rng.normal(0, noise, n)
    return pd.DataFrame({"ds": ds, "y": y})


def test_runway_exact_and_fractional():
    assert forecast.net_inventory_runway(0, [10] * 7) == 0.0
    assert forecast.net_inventory_runway(25, [10] * 7) == 2.5
    assert forecast.net_inventory_runway(10, [10] * 7) == 1.0


def test_runway_beyond_horizon_extrapolates_and_caps():
    assert forecast.net_inventory_runway(140, [10] * 7) == 14.0
    assert forecast.net_inventory_runway(5, [0] * 7) == forecast.MAX_RUNWAY_DAYS
    assert forecast.net_inventory_runway(1e12, [1] * 7) == forecast.MAX_RUNWAY_DAYS


def test_forecast_shape_and_nonnegative():
    fc, model = forecast.forecast_daily(_weekly(), 7, use_prophet=False)
    assert len(fc) == 7 and (fc["yhat"] >= 0).all() and model == "seasonal_naive"
    assert fc["ds"].min() == _weekly()["ds"].max() + pd.Timedelta(days=1)


def test_seasonal_naive_accuracy_on_seasonal_series():
    assert forecast.backtest_wmape(_weekly(), 7, use_prophet=False) < 0.05


def test_prophet_failure_falls_back():
    fc, model = forecast.forecast_daily(_weekly(n=10), 7, use_prophet=True)   # too short for prophet
    assert model == "seasonal_naive" and len(fc) == 7
