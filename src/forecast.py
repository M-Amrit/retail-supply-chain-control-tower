"""Demand forecasting (Prophet, with a seasonal-naive fallback) and Net Inventory Runway."""
from __future__ import annotations
import numpy as np
import pandas as pd

MAX_RUNWAY_DAYS = 365.0


def seasonal_naive(history: pd.DataFrame, horizon: int = 7, weeks: int = 4) -> pd.DataFrame:
    """Baseline: mean of same weekday over the last `weeks` weeks. history: ds, y (daily, complete days)."""
    h = history.sort_values("ds").tail(weeks * 7).copy()
    h["dow"] = h["ds"].dt.dayofweek
    by_dow = h.groupby("dow")["y"].mean()
    overall, sd = float(h["y"].mean()), float(h["y"].std(ddof=1) if len(h) > 1 else 0.0)
    ds = pd.date_range(history["ds"].max() + pd.Timedelta(days=1), periods=horizon, freq="D")
    yhat = np.array([by_dow.get(d.dayofweek, overall) for d in ds], dtype=float)
    return pd.DataFrame({"ds": ds, "yhat": yhat, "yhat_lower": np.maximum(yhat - 1.28 * sd, 0), "yhat_upper": yhat + 1.28 * sd})


def prophet_forecast(history: pd.DataFrame, horizon: int = 7) -> pd.DataFrame:
    from prophet import Prophet  # heavy import kept local
    m = Prophet(daily_seasonality=False, weekly_seasonality=True, yearly_seasonality=len(history) >= 365)
    m.fit(history[["ds", "y"]])
    fc = m.predict(m.make_future_dataframe(periods=horizon, freq="D")).tail(horizon)
    out = fc[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    for c in ("yhat", "yhat_lower", "yhat_upper"):
        out[c] = out[c].clip(lower=0)
    return out.reset_index(drop=True)


def forecast_daily(history: pd.DataFrame, horizon: int = 7, use_prophet: bool = True, min_points: int = 28) -> tuple[pd.DataFrame, str]:
    """Returns (forecast, model_name). Falls back to seasonal-naive if Prophet is unavailable,
    history is too short, or fitting fails — the pipeline must never die on one bad series."""
    if use_prophet and len(history) >= min_points:
        try:
            return prophet_forecast(history, horizon), "prophet"
        except Exception:  # ImportError, stan failures, etc.
            pass
    if len(history) == 0:
        raise ValueError("empty history")
    return seasonal_naive(history, horizon), "seasonal_naive"


def net_inventory_runway(stock: float, daily_forecast: np.ndarray | list[float]) -> float:
    """Days until cumulative forecast demand exhausts `stock` (fractional). Beyond the horizon, extrapolates at
    the mean forecast rate. Zero demand -> MAX_RUNWAY_DAYS. Result is capped at MAX_RUNWAY_DAYS."""
    f = np.clip(np.asarray(daily_forecast, dtype=float), 0, None)
    if stock <= 0:
        return 0.0
    cum = np.cumsum(f)
    idx = np.searchsorted(cum, stock, side="left")
    if idx < len(f):
        prev = cum[idx - 1] if idx > 0 else 0.0
        return float(idx + (stock - prev) / f[idx])
    rate = f.mean() if len(f) else 0.0
    if rate <= 0:
        return MAX_RUNWAY_DAYS
    return float(min(len(f) + (stock - cum[-1]) / rate, MAX_RUNWAY_DAYS))


def backtest_wmape(history: pd.DataFrame, horizon: int = 7, use_prophet: bool = False) -> float:
    """Hold out the last `horizon` days; weighted MAPE = sum|err| / sum(actual). Lower is better."""
    h = history.sort_values("ds")
    train, test = h.iloc[:-horizon], h.iloc[-horizon:]
    fc, _ = forecast_daily(train, horizon, use_prophet=use_prophet)
    denom = test["y"].sum()
    return float(np.abs(test["y"].to_numpy() - fc["yhat"].to_numpy()).sum() / denom) if denom > 0 else float("nan")
