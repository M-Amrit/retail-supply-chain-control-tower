"""What-If engine: 'what if supplier X is delayed by N days?' (pure, testable)."""
from __future__ import annotations
import numpy as np
import pandas as pd


def simulate_supplier_delay(inv: pd.DataFrame, supplier_id: int, delay_days: float, baseline_lead_days: float) -> pd.DataFrame:
    """inv columns: product_id, warehouse_id, category, supplier_id, current_stock_level, avg_daily_demand, unit_cost.

    Model: the next replenishment from the supplier is due in `baseline_lead_days`; the delay pushes it to
    baseline+delay. Stock runs dry at stock/demand days. Exposure = days with zero stock before arrival.
    Incremental exposure = exposure(with delay) - exposure(baseline). Value at risk = units x unit_cost
    (cost basis; no retail price in the dataset). Simplifying assumption: no safety/alternate sourcing."""
    d = inv[inv["supplier_id"] == supplier_id].copy()
    demand = d["avg_daily_demand"].to_numpy(dtype=float)
    days_cover = np.where(demand > 0, d["current_stock_level"].to_numpy(dtype=float) / np.where(demand > 0, demand, 1), np.inf)
    exp_base = np.clip(baseline_lead_days - days_cover, 0, None)
    exp_delay = np.clip(baseline_lead_days + delay_days - days_cover, 0, None)
    d["days_cover"] = days_cover
    d["stockout_days_baseline"] = exp_base
    d["stockout_days_delayed"] = exp_delay
    d["incremental_stockout_days"] = exp_delay - exp_base
    d["units_at_risk"] = d["incremental_stockout_days"] * demand
    d["value_at_risk"] = d["units_at_risk"] * d["unit_cost"].astype(float)
    d["newly_stocked_out"] = (exp_base == 0) & (exp_delay > 0)
    return d.sort_values("value_at_risk", ascending=False).reset_index(drop=True)


def summarize_by_category(sim: pd.DataFrame) -> pd.DataFrame:
    return (sim.groupby("category")
              .agg(skus_newly_stocked_out=("newly_stocked_out", "sum"), units_at_risk=("units_at_risk", "sum"),
                   value_at_risk=("value_at_risk", "sum"))
              .sort_values("value_at_risk", ascending=False).reset_index())
