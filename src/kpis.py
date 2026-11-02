"""KPI definitions as pure functions over DataFrames (unit-testable, no DB).

SKU definition: one product at one warehouse (product_id, warehouse_id).
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def stockout_rate(latest_stock: pd.DataFrame) -> float:
    """% of SKUs whose latest current_stock_level == 0. Expects one row per SKU."""
    if latest_stock.empty:
        return 0.0
    return float((latest_stock["current_stock_level"] == 0).mean() * 100.0)


def otd_rate(shipments: pd.DataFrame, since: pd.Timestamp | None = None) -> tuple[float, int]:
    """(OTD %, n delivered). Delivered = actual_delivery_date not null (optionally delivered since `since`).
    On time = actual <= scheduled. Returns (nan, 0) if nothing delivered."""
    d = shipments[shipments["actual_delivery_date"].notna()]
    if since is not None:
        d = d[d["actual_delivery_date"] >= since]
    n = len(d)
    if n == 0:
        return float("nan"), 0
    on_time = (d["actual_delivery_date"] <= d["scheduled_delivery_date"]).sum()
    return float(on_time / n * 100.0), n


def supplier_lead_time(shipments: pd.DataFrame) -> pd.DataFrame:
    """Average days from order creation to goods receipt, per supplier."""
    d = shipments[shipments["actual_delivery_date"].notna()].copy()
    d["lead_days"] = (d["actual_delivery_date"] - d["order_date"]).dt.total_seconds() / 86400.0
    out = d.groupby("supplier_id")["lead_days"].agg(avg_lead_time_days="mean", std_lead_time_days="std", n="count")
    return out.reset_index()


def days_of_inventory(latest_stock: pd.DataFrame, sales: pd.DataFrame, asof: pd.Timestamp,
                      window_days: int = 30) -> pd.DataFrame:
    """DOI = current stock / average daily demand over the trailing `window_days`.
    latest_stock: product_id, warehouse_id, current_stock_level
    sales: ts, product_id, store_id, units_sold (store_id == warehouse_id in this model)
    Zero-demand SKUs get DOI = NaN (undefined, not 'infinite risk')."""
    s = sales[(sales["ts"] > asof - pd.Timedelta(days=window_days)) & (sales["ts"] <= asof)]
    dem = (s.groupby(["product_id", "store_id"])["units_sold"].sum() / window_days).rename("avg_daily_demand").reset_index()
    dem = dem.rename(columns={"store_id": "warehouse_id"})
    m = latest_stock.merge(dem, on=["product_id", "warehouse_id"], how="left")
    m["avg_daily_demand"] = m["avg_daily_demand"].fillna(0.0)
    m["doi"] = np.where(m["avg_daily_demand"] > 0, m["current_stock_level"] / m["avg_daily_demand"].replace(0, np.nan), np.nan)
    return m
