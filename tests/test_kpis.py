import numpy as np, pandas as pd
from src import kpis

T = pd.Timestamp("2026-11-01")


def test_stockout_rate():
    df = pd.DataFrame({"current_stock_level": [0, 5, 0, 10]})
    assert kpis.stockout_rate(df) == 50.0
    assert kpis.stockout_rate(df.iloc[0:0]) == 0.0


def _ship(rows):
    return pd.DataFrame(rows, columns=["supplier_id", "order_date", "scheduled_delivery_date", "actual_delivery_date"]).astype(
        {"order_date": "datetime64[ns]", "scheduled_delivery_date": "datetime64[ns]", "actual_delivery_date": "datetime64[ns]"})


def test_otd_boundaries_and_undelivered_excluded():
    s = _ship([(1, "2026-10-01", "2026-10-05", "2026-10-05"),   # exactly on schedule -> on time
               (1, "2026-10-01", "2026-10-05", "2026-10-06"),   # late
               (1, "2026-10-01", "2026-10-05", None)])          # not delivered -> excluded
    pct, n = kpis.otd_rate(s)
    assert (pct, n) == (50.0, 2)
    assert np.isnan(kpis.otd_rate(s.iloc[2:])[0])


def test_supplier_lead_time():
    s = _ship([(1, "2026-10-01", "2026-10-05", "2026-10-05"), (1, "2026-10-01", "2026-10-05", "2026-10-07"),
               (2, "2026-10-01", "2026-10-05", "2026-10-02")])
    lt = kpis.supplier_lead_time(s).set_index("supplier_id")
    assert lt.loc[1, "avg_lead_time_days"] == 5.0 and lt.loc[2, "avg_lead_time_days"] == 1.0


def test_doi_and_zero_demand():
    stock = pd.DataFrame({"product_id": [1, 2], "warehouse_id": ["W", "W"], "current_stock_level": [60, 10]})
    sales = pd.DataFrame({"ts": [T - pd.Timedelta(days=d) for d in (1, 2, 40)], "product_id": [1, 1, 1],
                          "store_id": ["W"] * 3, "units_sold": [30, 30, 999]})   # 40d-old sale must be excluded
    r = kpis.days_of_inventory(stock, sales, T).set_index("product_id")
    assert r.loc[1, "doi"] == 60 / (60 / 30)           # 30 days
    assert np.isnan(r.loc[2, "doi"])                  # no demand -> undefined
