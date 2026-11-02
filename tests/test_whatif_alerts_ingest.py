import numpy as np, pandas as pd
from src import alerts, ingest_data, whatif

T = pd.Timestamp("2026-11-01 12:00")


def test_whatif_delay_creates_incremental_exposure():
    inv = pd.DataFrame({"product_id": [1, 2, 3], "warehouse_id": "W", "category": ["A", "A", "B"], "supplier_id": [1, 1, 2],
                        "current_stock_level": [100, 20, 5], "avg_daily_demand": [10.0, 10.0, 1.0], "unit_cost": [2.0, 2.0, 9.0]})
    sim = whatif.simulate_supplier_delay(inv, supplier_id=1, delay_days=7, baseline_lead_days=5)
    assert set(sim["product_id"]) == {1, 2}                       # other suppliers untouched
    p1, p2 = sim.set_index("product_id").loc[1], sim.set_index("product_id").loc[2]
    assert p1["days_cover"] == 10 and p1["incremental_stockout_days"] == 2        # runs dry day 10, arrival day 12
    assert p2["days_cover"] == 2 and p2["incremental_stockout_days"] == 7         # already short at baseline: +delay
    assert bool(p1["newly_stocked_out"]) and not bool(p2["newly_stocked_out"])    # p2 was stocked out anyway
    assert whatif.simulate_supplier_delay(inv, 1, 0, 5)["incremental_stockout_days"].sum() == 0


def test_stockout_alert_rule_and_cap():
    doi = pd.DataFrame({"product_id": [1, 2, 3], "warehouse_id": "W", "current_stock_level": [1, 50, 5], "doi": [0.5, 20.0, np.nan]})
    prods = pd.DataFrame({"product_id": [1, 2, 3], "product_name": list("abc"), "supplier_id": 1})
    lt = pd.DataFrame({"supplier_id": [1], "avg_lead_time_days": [5.0]})
    out = alerts.stockout_risk_alerts(doi, lt, prods, T)
    assert [a["entity_id"] for a in out] == ["1@W"] and out[0]["severity"] == "critical"   # DOI<lead only; NaN ignored
    assert alerts.stockout_risk_alerts(doi, lt, prods, T, max_alerts=0) == []


def test_otd_alert_needs_min_sample_and_threshold():
    assert alerts.otd_breach_alert(80.0, 2, T) == []        # too few shipments
    assert alerts.otd_breach_alert(95.0, 50, T) == []       # healthy
    assert len(alerts.otd_breach_alert(85.0, 50, T)) == 1


def test_dispatch_without_channels_does_not_raise():
    assert alerts.dispatch([{"severity": "high", "alert_type": "X", "message": "m"}]) is True


def test_transform_schema_integrity():
    t = ingest_data.transform(ingest_data.generate_synthetic_dataco(n_orders=8000, days=120, end=pd.Timestamp("2026-10-30")))
    assert set(t) == {"dim_suppliers", "dim_products", "fact_shipments", "fact_sales_history", "fact_inventory_hourly"}
    assert set(t["fact_shipments"]["supplier_id"]) <= set(t["dim_suppliers"]["supplier_id"])       # FK
    assert set(t["fact_shipments"]["product_id"]) <= set(t["dim_products"]["product_id"])
    assert set(t["fact_sales_history"]["product_id"]) <= set(t["dim_products"]["product_id"])
    assert t["fact_shipments"]["shipment_id"].is_unique
    assert (t["fact_inventory_hourly"]["current_stock_level"] >= 0).all()
    assert t["dim_suppliers"]["reliability_score"].between(0, 1).all()


def test_transform_drops_dirty_rows_and_flags_cancellations():
    raw = ingest_data.generate_synthetic_dataco(n_orders=500, days=30, end=pd.Timestamp("2026-10-30"))
    raw.loc[0, "order date (DateOrders)"] = pd.NaT
    raw.loc[1, "Days for shipping (real)"] = np.nan
    raw.loc[2, "Delivery Status"] = "Shipping canceled"
    t = ingest_data.transform(raw)
    s = t["fact_shipments"]
    assert len(s) == len(raw) - 2
    canceled = s[s["status"] == "Canceled"]
    assert len(canceled) >= 1 and canceled["actual_delivery_date"].isna().all()
