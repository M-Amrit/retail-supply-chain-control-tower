"""Anomaly detection: rolling z-score (primary, explainable) + Isolation Forest (secondary)."""
from __future__ import annotations
import numpy as np
import pandas as pd


def detect_delivery_delays(shipments: pd.DataFrame, sigma: float = 2.0, since: pd.Timestamp | None = None,
                           min_history: int = 10) -> pd.DataFrame:
    """Flag deliveries whose lead time exceeds the supplier's historical mean by > `sigma` std devs.

    If `since` is given, the baseline is built only from deliveries BEFORE `since` (so a fresh outlier
    can't inflate its own baseline) and candidates are deliveries at/after `since`."""
    d = shipments[shipments["actual_delivery_date"].notna()].copy()
    d["lead_days"] = (d["actual_delivery_date"] - d["order_date"]).dt.total_seconds() / 86400.0
    if since is not None:
        base, cand = d[d["actual_delivery_date"] < since], d[d["actual_delivery_date"] >= since]
    else:
        base, cand = d, d
    stats = base.groupby("supplier_id")["lead_days"].agg(mean_lead="mean", std_lead="std", n_hist="count").reset_index()
    m = cand.merge(stats, on="supplier_id", how="inner")
    m = m[(m["n_hist"] >= min_history) & (m["std_lead"] > 0)]
    m["z"] = (m["lead_days"] - m["mean_lead"]) / m["std_lead"]
    cols = ["shipment_id", "supplier_id", "lead_days", "mean_lead", "std_lead", "z"]
    return m.loc[m["z"] > sigma, cols].reset_index(drop=True)


def bucket_sales(sales: pd.DataFrame, asof: pd.Timestamp, bucket_hours: int = 24, n_buckets: int = 29) -> pd.DataFrame:
    """Aggregate to fixed-width buckets ALIGNED TO `asof` (bucket 0 = trailing 24h) so spike detection
    can run hourly without comparing a partial calendar day to full days. Returns
    index=bucket (0=latest), columns=(product_id, store_id)."""
    s = sales[(sales["ts"] <= asof) & (sales["ts"] > asof - pd.Timedelta(hours=bucket_hours * n_buckets))].copy()
    s["bucket"] = ((asof - s["ts"]).dt.total_seconds() // (bucket_hours * 3600)).astype(int)
    p = s.pivot_table(index="bucket", columns=["product_id", "store_id"], values="units_sold", aggfunc="sum", fill_value=0)
    return p.reindex(range(n_buckets), fill_value=0)


def detect_demand_spikes(buckets: pd.DataFrame, sigma: float = 3.0, min_mean: float = 3.0, min_lift: float = 8.0) -> pd.DataFrame:
    """Latest bucket (index 0) vs mean/std of the older buckets.
    `min_mean` ignores near-zero-volume SKUs and `min_lift` requires an absolute increase (units): for low-count
    Poisson-like demand, 3 sigma is exceeded by pure noise far more often than a Gaussian z-score implies."""
    if buckets.empty or len(buckets) < 8:
        return pd.DataFrame(columns=["product_id", "store_id", "units_latest", "mean", "std", "z"])
    latest = buckets.loc[0]
    hist = buckets.drop(index=0)
    mean, std = hist.mean(), hist.std(ddof=1)
    z = (latest - mean) / std.replace(0, np.nan)
    out = pd.DataFrame({"units_latest": latest, "mean": mean, "std": std, "z": z}).reset_index()
    return out[(out["z"] > sigma) & (out["mean"] >= min_mean) & ((out["units_latest"] - out["mean"]) >= min_lift)].reset_index(drop=True)


def isolation_forest_flags(df: pd.DataFrame, features: list[str], contamination: float = 0.01, seed: int = 42) -> pd.Series:
    """Multivariate complement to z-scores (e.g. lead_days + qty + z). Returns boolean Series (True = anomaly)."""
    from sklearn.ensemble import IsolationForest
    X = df[features].fillna(0.0).to_numpy()
    if len(X) < 20:
        return pd.Series(False, index=df.index)
    return pd.Series(IsolationForest(contamination=contamination, random_state=seed).fit_predict(X) == -1, index=df.index)
