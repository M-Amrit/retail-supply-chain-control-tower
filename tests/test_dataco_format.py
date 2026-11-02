"""Exercises the loader on a file that mimics the REAL DataCo layout (latin-1, m/d/Y H:M, 53-col superset)."""
import pandas as pd
from src import ingest_data

HEADER = ["Type", "Days for shipping (real)", "Days for shipment (scheduled)", "Delivery Status", "Late_delivery_risk",
          "Category Name", "Customer City", "Order Id", "order date (DateOrders)", "Order Item Quantity", "Order Region",
          "Product Card Id", "Product Name", "Product Price", "shipping date (DateOrders)"]
ROWS = [
    ["DEBIT", 3, 4, "Advance shipping", 0, "Sporting Goods", "Caguas", 1, "1/31/2018 22:56", 1, "Southeast Asia", 1360, "Smart watch", 327.75, "2/3/2018 22:56"],
    ["TRANSFER", 5, 4, "Late delivery", 1, "Cleats", "Chicago", 2, "1/13/2018 12:27", 2, "South Asia", 1360, "Café Boots", 327.75, "1/18/2018 12:27"],
    ["CASH", 0, 4, "Shipping canceled", 0, "Cleats", "Chicago", 3, "1/13/2018 12:24", 1, "South Asia", 1014, "Nike", 50.0, "1/13/2018 12:24"],
    ["DEBIT", 4, 4, "Shipping on time", 0, "Cleats", "Chicago", 4, "12/31/2017 1:03", 3, "Western Europe", 1014, "Nike", 50.0, "1/4/2018 1:03"],
]


def _write(tmp_path, header=HEADER):
    p = tmp_path / "DataCoSupplyChainDataset.csv"
    pd.DataFrame(ROWS, columns=HEADER).to_csv(p, index=False, encoding="latin-1")
    return str(p)


def test_load_parse_rebase_transform(tmp_path):
    raw = ingest_data.load_dataco(_write(tmp_path))
    assert raw["order date (DateOrders)"].notna().all()
    assert raw["order date (DateOrders)"].iloc[0] == pd.Timestamp("2018-01-31 22:56")      # m/d, not d/m
    raw = ingest_data.rebase_dates(raw, pd.Timestamp("2026-11-02"))
    assert raw["order date (DateOrders)"].max().normalize() == pd.Timestamp("2026-11-01")
    t = ingest_data.transform(raw)
    s = t["fact_shipments"].set_index("order_id")
    assert s.loc["3", "status"] == "Canceled" and pd.isna(s.loc["3", "actual_delivery_date"])
    assert s.loc["2", "actual_delivery_date"] > s.loc["2", "scheduled_delivery_date"]       # 5d real vs 4d scheduled
    assert s.loc["1", "actual_delivery_date"] <= s.loc["1", "scheduled_delivery_date"]


def test_missing_columns_gives_actionable_error(tmp_path):
    p = tmp_path / "bad.csv"; pd.DataFrame({"Order Id": [1]}).to_csv(p, index=False)
    try:
        ingest_data.load_dataco(str(p)); assert False
    except ValueError as e:
        assert "missing columns" in str(e) and "53-column" in str(e)
