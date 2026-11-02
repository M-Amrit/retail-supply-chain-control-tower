"""Load DataCo Smart Supply Chain data into PostgreSQL.

IMPORTANT data-fit notes (see README):
  * DataCo has NO supplier table and NO inventory feed. Suppliers are *derived* (deterministic bucketing of
    Product Card Id into N_SUPPLIERS) and inventory is *simulated* from observed demand.
  * DataCo dates are 2015-2018; they are rebased so the history ends the day before `--end` (default: today).
If the CSV is missing, a synthetic dataset with the same columns is generated so the pipeline still runs.
Usage: python -m src.ingest_data [--csv PATH] [--end YYYY-MM-DD] [--synthetic]
"""
from __future__ import annotations
import argparse, logging, os
import numpy as np
import pandas as pd
from src import config

log = logging.getLogger("ingest")
REQUIRED = ["Order Id", "order date (DateOrders)", "Days for shipment (scheduled)", "Days for shipping (real)",
            "Product Card Id", "Product Name", "Category Name", "Product Price", "Order Item Quantity",
            "Order Region", "Delivery Status"]


def load_dataco(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="latin-1", usecols=lambda c: c in REQUIRED)
    missing = set(REQUIRED) - set(df.columns)
    if missing:
        raise ValueError(f"DataCo CSV missing columns: {sorted(missing)} (found {len(df.columns)} columns; "
                         "is this the original 53-column DataCoSupplyChainDataset.csv?)")
    col = "order date (DateOrders)"                      # native format e.g. '1/31/2018 22:56'
    parsed = pd.to_datetime(df[col], format="%m/%d/%Y %H:%M", errors="coerce")
    if parsed.isna().mean() > 0.5:                       # other export formats: fall back to inference
        parsed = pd.to_datetime(df[col], errors="coerce")
    df[col] = parsed
    return df


def generate_synthetic_dataco(n_orders: int = 60000, days: int = 540, seed: int = 42,
                              end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Synthetic data in DataCo's column layout (weekly seasonality, ~15% late, rare long delays)."""
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(end or pd.Timestamp.today().normalize())
    cats = [f"Category-{i:02d}" for i in range(10)]
    regions = ["West", "East", "South", "Central", "Canada"]
    prod_ids = np.arange(1000, 1120)
    prod_cat = {p: cats[i % 10] for i, p in enumerate(prod_ids)}
    prod_price = {p: float(rng.uniform(8, 250)) for p in prod_ids}
    pop = rng.dirichlet(np.ones(len(prod_ids)) * 0.6)
    pid = rng.choice(prod_ids, n_orders, p=pop)
    day = rng.integers(0, days, n_orders)
    dow_w = np.array([1.0, 1.0, 1.0, 1.05, 1.15, 1.3, 1.2])
    keep = rng.random(n_orders) < dow_w[((end - pd.to_timedelta(day + 1, "D")).dayofweek.to_numpy())] / dow_w.max()
    pid, day = pid[keep], day[keep]
    n = len(pid)
    sched = rng.choice([2, 4, 5], n, p=[0.2, 0.5, 0.3])
    sup_delay_p = 0.02 + 0.10 * ((pid % 12) / 11)         # supplier-specific lateness
    late = rng.random(n) < sup_delay_p
    real = sched + np.where(late, rng.integers(1, 4, n), 0) - (rng.random(n) < 0.15) * (sched > 2)
    real = real + (rng.random(n) < 0.01) * rng.integers(6, 12, n)   # rare extreme delays
    od = end - pd.to_timedelta(day + 1, "D") + pd.to_timedelta(rng.integers(0, 86400, n), "s")
    return pd.DataFrame({
        "Order Id": np.arange(1, n + 1), "order date (DateOrders)": od,
        "Days for shipment (scheduled)": sched, "Days for shipping (real)": real,
        "Product Card Id": pid, "Product Name": [f"Product {p}" for p in pid],
        "Category Name": [prod_cat[p] for p in pid], "Product Price": [prod_price[p] for p in pid],
        "Order Item Quantity": rng.integers(1, 6, n), "Order Region": rng.choice(regions, n, p=[.3, .25, .2, .15, .1]),
        "Delivery Status": np.where(late, "Late delivery", "Advance shipping"),
    })


def rebase_dates(raw: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    """Shift order dates so the latest order lands on end-1 day (DataCo's native 2015-2018 range is stale)."""
    raw = raw.copy()
    raw["order date (DateOrders)"] = pd.to_datetime(raw["order date (DateOrders)"], errors="coerce")
    delta = (pd.Timestamp(end).normalize() - pd.Timedelta(days=1)) - raw["order date (DateOrders)"].max().normalize()
    raw["order date (DateOrders)"] = raw["order date (DateOrders)"] + delta
    return raw


def transform(raw: pd.DataFrame, n_suppliers: int = config.N_SUPPLIERS, seed: int = 7) -> dict[str, pd.DataFrame]:
    """Clean + map raw DataCo rows to the star schema. Pure function (testable)."""
    rng = np.random.default_rng(seed)
    df = raw.copy()
    df["order_date"] = pd.to_datetime(df["order date (DateOrders)"], errors="coerce")
    n0 = len(df)
    df = df.dropna(subset=["order_date", "Product Card Id", "Order Region"])
    df["sched_days"] = pd.to_numeric(df["Days for shipment (scheduled)"], errors="coerce")
    df["real_days"] = pd.to_numeric(df["Days for shipping (real)"], errors="coerce")
    df = df.dropna(subset=["sched_days", "real_days"])
    df = df[(df["Order Item Quantity"] > 0) & (df["Product Price"] > 0)]
    log.info("cleaning dropped %d of %d rows", n0 - len(df), n0)

    df["product_id"] = df["Product Card Id"].astype(int)
    df["supplier_id"] = df["product_id"] % n_suppliers + 1          # DERIVED supplier assignment
    df["store_id"] = df["Order Region"].astype(str).str.strip()
    canceled = df["Delivery Status"].astype(str).str.contains("cancel", case=False)

    ship = pd.DataFrame({
        "shipment_id": "DC-" + df["Order Id"].astype(str) + "-" + df.groupby("Order Id").cumcount().astype(str),
        "order_id": df["Order Id"].astype(str), "supplier_id": df["supplier_id"], "product_id": df["product_id"],
        "order_date": df["order_date"],
        "scheduled_delivery_date": df["order_date"] + pd.to_timedelta(df["sched_days"], "D"),
        "actual_delivery_date": (df["order_date"] + pd.to_timedelta(df["real_days"], "D")).where(~canceled),
        "status": np.where(canceled, "Canceled", "Delivered"),
    }).drop_duplicates("shipment_id")

    sales = (df.assign(ts=df["order_date"].dt.floor("D"))
               .groupby(["ts", "product_id", "store_id"], as_index=False)["Order Item Quantity"].sum()
               .rename(columns={"Order Item Quantity": "units_sold"}))

    delivered = ship[ship["actual_delivery_date"].notna()].copy()
    delivered["late"] = delivered["actual_delivery_date"] > delivered["scheduled_delivery_date"]
    delivered["lead"] = (delivered["actual_delivery_date"] - delivered["order_date"]).dt.total_seconds() / 86400
    g = delivered.groupby("supplier_id")
    suppliers = pd.DataFrame({
        "supplier_name": [f"Supplier-{i:02d}" for i in sorted(df["supplier_id"].unique())],
        "supplier_id": sorted(df["supplier_id"].unique()),
    }).merge(g["lead"].median().round(2).rename("base_lead_time_days").reset_index(), on="supplier_id", how="left") \
      .merge((1 - g["late"].mean()).clip(0, 1).round(4).rename("reliability_score").reset_index(), on="supplier_id", how="left")
    suppliers = suppliers.fillna({"base_lead_time_days": 4.0, "reliability_score": 0.9})[
        ["supplier_id", "supplier_name", "base_lead_time_days", "reliability_score"]]

    span_days = max((df["order_date"].max() - df["order_date"].min()).days, 1)
    avg_daily = df.groupby("product_id")["Order Item Quantity"].sum() / span_days
    prod = (df.groupby("product_id").agg(product_name=("Product Name", "first"), category=("Category Name", "first"),
                                         price=("Product Price", "mean"), supplier_id=("supplier_id", "first")).reset_index())
    prod["unit_cost"] = (prod["price"] * 0.7).round(2)                       # ASSUMPTION: cost = 70% of list price
    prod["safety_stock_threshold"] = np.ceil(prod["product_id"].map(avg_daily) * 3).clip(lower=5).astype(int)  # 3 days cover
    products = prod[["product_id", "product_name", "category", "unit_cost", "safety_stock_threshold", "supplier_id"]]

    # Simulated opening inventory per SKU (product x warehouse): 5-45 days of cover, skewed so some SKUs start low.
    pair = (sales.groupby(["product_id", "store_id"])["units_sold"].sum() / span_days).rename("rate").reset_index()
    cover = rng.gamma(shape=2.0, scale=10.0, size=len(pair)).clip(0.5, 60)
    inv = pd.DataFrame({
        "ts": df["order_date"].max().floor("h") + pd.Timedelta(hours=1), "product_id": pair["product_id"],
        "warehouse_id": pair["store_id"], "current_stock_level": np.ceil(pair["rate"] * cover).astype(int),
        "incoming_shipment_qty": 0})
    return {"dim_suppliers": suppliers, "dim_products": products, "fact_shipments": ship,
            "fact_sales_history": sales, "fact_inventory_hourly": inv}


def load_to_postgres(tables: dict[str, pd.DataFrame], engine) -> None:
    from sqlalchemy import text
    order = ["dim_suppliers", "dim_products", "fact_shipments", "fact_sales_history", "fact_inventory_hourly"]
    with engine.begin() as c:
        c.execute(text("TRUNCATE fact_inventory_hourly, fact_sales_history, fact_shipments, dim_products, dim_suppliers, "
                       "alerts_log, kpi_snapshot, kpi_doi, demand_forecast, inventory_runway RESTART IDENTITY CASCADE"))
        for name in order:
            tables[name].to_sql(name, c, if_exists="append", index=False, method="multi", chunksize=5000)
            log.info("loaded %-22s %9d rows", name, len(tables[name]))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=config.DATACO_CSV)
    ap.add_argument("--end", default=str(pd.Timestamp.today().normalize().date()))
    ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()
    if a.synthetic or not os.path.exists(a.csv):
        log.warning("Using SYNTHETIC data (csv=%s %s)", a.csv, "not found" if not os.path.exists(a.csv) else "overridden")
        raw = generate_synthetic_dataco(end=pd.Timestamp(a.end))
    else:
        raw = rebase_dates(load_dataco(a.csv), pd.Timestamp(a.end))
    from src.db import get_engine
    load_to_postgres(transform(raw), get_engine())


if __name__ == "__main__":
    main()
