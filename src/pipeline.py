"""Hourly pipeline tasks. Each function is idempotent per `ts` and callable outside Airflow."""
from __future__ import annotations
import logging, os
import numpy as np
import pandas as pd
from src import alerts as A, anomaly, config, forecast, kpis
from src.db import execute, get_engine, read_sql

log = logging.getLogger("pipeline")
FEED_DIR = os.getenv("FEED_DIR", "data/feed")


def _hour(ts) -> pd.Timestamp:
    return pd.Timestamp(ts).tz_localize(None).floor("h") if pd.Timestamp(ts).tzinfo else pd.Timestamp(ts).floor("h")


# 1. extract ---------------------------------------------------------------------------------------------
def extract_source_feed(ts, seed: int | None = None) -> str:
    """Simulate the hourly delta (sales, replenishment shipments, inventory snapshot) from current DB state.
    Writes CSVs to FEED_DIR/<ts>/ and returns that directory (XCom-friendly)."""
    ts = _hour(ts)
    rng = np.random.default_rng(seed if seed is not None else int(ts.value // 3_600_000_000_000) % 2**32)
    inv = read_sql("""SELECT DISTINCT ON (product_id, warehouse_id) product_id, warehouse_id, current_stock_level
                      FROM fact_inventory_hourly WHERE ts < :ts ORDER BY product_id, warehouse_id, ts DESC""", {"ts": ts})
    if inv.empty:
        raise RuntimeError("fact_inventory_hourly is empty; run `python -m src.ingest_data` first")
    rate = read_sql("""SELECT product_id, store_id AS warehouse_id, SUM(units_sold)/30.0 AS daily FROM fact_sales_history
                       WHERE ts > :ts - interval '30 days' GROUP BY 1,2""", {"ts": ts})
    prods = read_sql("SELECT product_id, supplier_id, safety_stock_threshold FROM dim_products")
    sup = read_sql("SELECT supplier_id, base_lead_time_days, reliability_score FROM dim_suppliers")
    m = inv.merge(rate, on=["product_id", "warehouse_id"], how="left").merge(prods, on="product_id").merge(sup, on="supplier_id")
    m["daily"] = m["daily"].fillna(0.0)

    dow_f = [0.9, 0.9, 0.95, 1.0, 1.1, 1.2, 1.0][ts.dayofweek]
    lam = m["daily"].to_numpy() / 24.0 * dow_f
    demand = rng.poisson(lam)
    if config.DEMO_ANOMALIES and rng.random() < 0.5:                       # demo: inject a demand spike
        i = rng.choice(np.flatnonzero(m["daily"].to_numpy() > 1))
        demand[i] = int(m["daily"].iloc[i] * 8)

    # replenishment: SKUs under 2x safety stock reorder with p=0.12/h (qty ~ 14 days of demand)
    low = (m["current_stock_level"] < 2 * m["safety_stock_threshold"]).to_numpy()
    repl = low & (rng.random(len(m)) < 0.12)
    qty = np.where(repl, np.ceil(m["daily"].to_numpy() * 14).clip(min=5), 0).astype(int)

    sched = m["base_lead_time_days"].round().clip(lower=1).to_numpy()
    late = rng.random(len(m)) < (1 - m["reliability_score"].to_numpy())
    delay = np.where(late, rng.integers(1, 4, len(m)), 0) + (rng.random(len(m)) < 0.01) * rng.integers(6, 12, len(m))
    if config.DEMO_ANOMALIES and repl.any() and rng.random() < 0.5:        # demo: force one extreme delay
        delay[np.flatnonzero(repl)[0]] += 12
    lead = sched + delay

    stock_before = m["current_stock_level"].to_numpy()
    fulfilled = np.minimum(demand, stock_before + qty)
    stock_after = stock_before + qty - fulfilled
    n = ts.strftime("%Y%m%d%H")

    d = os.path.join(FEED_DIR, ts.strftime("%Y%m%dT%H")); os.makedirs(d, exist_ok=True)
    pd.DataFrame({"ts": ts, "product_id": m["product_id"], "warehouse_id": m["warehouse_id"],
                  "current_stock_level": stock_after, "incoming_shipment_qty": qty}).to_csv(f"{d}/inventory.csv", index=False)
    s = m.assign(fulfilled=fulfilled)[fulfilled > 0]
    pd.DataFrame({"ts": ts, "product_id": s["product_id"], "store_id": s["warehouse_id"], "units_sold": s["fulfilled"]}) \
        .to_csv(f"{d}/sales.csv", index=False)
    r = np.flatnonzero(repl)
    pd.DataFrame({"shipment_id": [f"SIM-{n}-{i}" for i in r], "order_id": [f"PO-{n}-{i}" for i in r],
                  "supplier_id": m["supplier_id"].to_numpy()[r], "product_id": m["product_id"].to_numpy()[r],
                  "order_date": ts - pd.to_timedelta(lead[r], "D"), "scheduled_delivery_date": ts - pd.to_timedelta(delay[r], "D"),
                  "actual_delivery_date": ts, "status": "Delivered"}).to_csv(f"{d}/shipments.csv", index=False)
    log.info("feed %s: %d sales rows, %d deliveries", ts, len(s), len(r))
    return d


# 2. load -------------------------------------------------------------------------------------------------
def load_postgres_staging(feed_dir: str) -> dict:
    """Load CSVs into stg_* then merge into fact_* (ON CONFLICT DO NOTHING => reruns are safe)."""
    eng = get_engine()
    cfg = {"inventory.csv": ("stg_inventory_hourly", "fact_inventory_hourly", "(ts, product_id, warehouse_id)", ["ts"]),
           "sales.csv": ("stg_sales_history", "fact_sales_history", "(ts, product_id, store_id)", ["ts"]),
           "shipments.csv": ("stg_shipments", "fact_shipments", "(shipment_id)",
                             ["order_date", "scheduled_delivery_date", "actual_delivery_date"])}
    counts = {}
    for fname, (stg, fact, key, dates) in cfg.items():
        df = pd.read_csv(os.path.join(feed_dir, fname), parse_dates=dates)
        with eng.begin() as c:
            from sqlalchemy import text
            c.execute(text(f"TRUNCATE {stg}"))
            df.to_sql(stg, c, if_exists="append", index=False, method="multi", chunksize=5000)
            cols = ", ".join(df.columns)
            res = c.execute(text(f"INSERT INTO {fact} ({cols}) SELECT {cols} FROM {stg} ON CONFLICT {key} DO NOTHING"))
            counts[fact] = res.rowcount
    return counts


# 3. KPIs -------------------------------------------------------------------------------------------------
def run_kpi_transformation(ts) -> dict:
    ts = _hour(ts)
    stock = read_sql("""SELECT DISTINCT ON (product_id, warehouse_id) product_id, warehouse_id, current_stock_level
                        FROM fact_inventory_hourly WHERE ts <= :ts ORDER BY product_id, warehouse_id, ts DESC""", {"ts": ts})
    ship = read_sql("SELECT * FROM fact_shipments WHERE order_date > :ts - interval '180 days'", {"ts": ts})
    for c in ("order_date", "scheduled_delivery_date", "actual_delivery_date"):
        ship[c] = pd.to_datetime(ship[c])
    sales = read_sql("SELECT * FROM fact_sales_history WHERE ts > :ts - interval '31 days'", {"ts": ts}); sales["ts"] = pd.to_datetime(sales["ts"])
    ship = ship[(ship["actual_delivery_date"].isna()) | (ship["actual_delivery_date"] <= ts)]

    so = kpis.stockout_rate(stock)
    otd24, _ = kpis.otd_rate(ship, since=ts - pd.Timedelta(hours=24))
    otd_all, _ = kpis.otd_rate(ship)
    lt = kpis.supplier_lead_time(ship)
    avg_lt = float(lt["avg_lead_time_days"].mean()) if not lt.empty else float("nan")
    doi = kpis.days_of_inventory(stock, sales, ts)
    n_alerts = int(read_sql("SELECT COUNT(*) n FROM alerts_log WHERE created_at > :ts - interval '24 hours'", {"ts": ts})["n"][0])

    execute("""INSERT INTO kpi_snapshot VALUES (:ts,:so,:otd,:lt,:na)
               ON CONFLICT (ts) DO UPDATE SET stockout_rate_pct=:so, otd_pct=:otd, avg_supplier_lead_time_days=:lt, active_alerts=:na""",
            {"ts": ts, "so": so, "otd": None if np.isnan(otd24) else (otd24), "lt": None if np.isnan(avg_lt) else avg_lt, "na": n_alerts})
    execute("DELETE FROM kpi_doi WHERE ts = :ts", {"ts": ts})
    out = doi.assign(ts=ts).rename(columns={"current_stock_level": "current_stock"})[
        ["ts", "product_id", "warehouse_id", "current_stock", "avg_daily_demand", "doi"]]
    out = out.replace([np.inf, -np.inf], np.nan)
    out.to_sql("kpi_doi", get_engine(), if_exists="append", index=False, method="multi", chunksize=5000)
    return {"stockout_rate_pct": so, "otd_24h_pct": otd24, "otd_all_pct": otd_all, "avg_lead_time_days": avg_lt}


# 4. anomalies --------------------------------------------------------------------------------------------
def run_anomaly_detection(ts) -> int:
    ts = _hour(ts)
    ship = read_sql("SELECT * FROM fact_shipments WHERE actual_delivery_date IS NOT NULL AND actual_delivery_date <= :ts "
                    "AND order_date > :ts - interval '365 days'", {"ts": ts})
    for c in ("order_date", "scheduled_delivery_date", "actual_delivery_date"):
        ship[c] = pd.to_datetime(ship[c])
    found = A.delay_alerts(anomaly.detect_delivery_delays(ship, config.DELAY_SIGMA, since=ts - pd.Timedelta(hours=1)), ts)

    sales = read_sql("SELECT ts, product_id, store_id, units_sold FROM fact_sales_history WHERE ts > :ts - interval '30 days'", {"ts": ts})
    sales["ts"] = pd.to_datetime(sales["ts"])
    found += A.spike_alerts(anomaly.detect_demand_spikes(anomaly.bucket_sales(sales, ts), config.SPIKE_SIGMA), ts)
    return _insert_alerts(found)


def _insert_alerts(rows: list[dict]) -> int:
    n = 0
    for r in rows:
        from sqlalchemy import text
        with get_engine().begin() as c:
            n += c.execute(text("""INSERT INTO alerts_log (alert_type,severity,entity_type,entity_id,metric_value,threshold_value,message,dedup_key)
                                   VALUES (:alert_type,:severity,:entity_type,:entity_id,:metric_value,:threshold_value,:message,:dedup_key)
                                   ON CONFLICT (dedup_key) DO NOTHING"""), r).rowcount
    return n


# 5. forecast ---------------------------------------------------------------------------------------------
def run_prophet_forecast(ts) -> dict:
    """Refresh category x store forecasts if stale (>FORECAST_REFRESH_HOURS), always recompute runway.
    Prophet for the top-N series by volume, seasonal-naive for the long tail (keeps the hourly run bounded)."""
    ts = _hour(ts)
    last = read_sql("SELECT MAX(generated_at) g FROM demand_forecast")["g"][0]
    if pd.isna(last) or (ts - pd.Timestamp(last)) >= pd.Timedelta(hours=config.FORECAST_REFRESH_HOURS):
        s = read_sql("""SELECT date_trunc('day', f.ts) AS ds, p.category, f.store_id, SUM(f.units_sold) AS y
                        FROM fact_sales_history f JOIN dim_products p USING (product_id)
                        WHERE f.ts >= :ts - interval '365 days' AND f.ts < date_trunc('day', CAST(:ts AS timestamp))
                        GROUP BY 1,2,3""", {"ts": ts})
        s["ds"] = pd.to_datetime(s["ds"])
        vol = s.groupby(["category", "store_id"])["y"].sum().sort_values(ascending=False)
        top = set(vol.head(config.FORECAST_TOP_N_PROPHET).index)
        rows = []
        for (cat, st), g in s.groupby(["category", "store_id"]):
            h = g.set_index("ds")["y"].asfreq("D", fill_value=0).reset_index()
            try:
                fc, model = forecast.forecast_daily(h, config.FORECAST_HORIZON_DAYS, use_prophet=(cat, st) in top)
            except Exception as e:
                log.error("forecast failed for %s/%s: %s", cat, st, e); continue
            rows.append(fc.assign(generated_at=ts, category=cat, store_id=st, model=model).rename(columns={"ds": "forecast_date"}))
        if rows:
            pd.concat(rows).to_sql("demand_forecast", get_engine(), if_exists="append", index=False, method="multi", chunksize=5000)
        last = ts
    fc = read_sql("SELECT category, store_id, forecast_date, yhat FROM demand_forecast WHERE generated_at = :g ORDER BY forecast_date", {"g": last})
    stock = read_sql("""SELECT p.category, l.warehouse_id, SUM(l.current_stock_level) AS stock FROM (
                          SELECT DISTINCT ON (product_id, warehouse_id) product_id, warehouse_id, current_stock_level
                          FROM fact_inventory_hourly WHERE ts <= :ts ORDER BY product_id, warehouse_id, ts DESC) l
                        JOIN dim_products p USING (product_id) GROUP BY 1,2""", {"ts": ts})
    runway = []
    for r in stock.itertuples():
        f = fc[(fc["category"] == r.category) & (fc["store_id"] == r.warehouse_id)]["yhat"].to_numpy()
        if len(f):
            runway.append((ts, r.category, r.warehouse_id, int(r.stock), forecast.net_inventory_runway(r.stock, f)))
    rdf = pd.DataFrame(runway, columns=["generated_at", "category", "warehouse_id", "current_stock", "runway_days"])
    execute("DELETE FROM inventory_runway WHERE generated_at = :ts", {"ts": ts})
    rdf.to_sql("inventory_runway", get_engine(), if_exists="append", index=False, method="multi")
    return {"series_forecasted": int(fc[["category", "store_id"]].drop_duplicates().shape[0]), "runway_rows": len(rdf),
            "short_runway": int((rdf["runway_days"] < config.FORECAST_HORIZON_DAYS).sum())}


# 6. alerts -----------------------------------------------------------------------------------------------
def dispatch_alerts(ts) -> dict:
    ts = _hour(ts)
    doi = read_sql("SELECT product_id, warehouse_id, current_stock AS current_stock_level, doi FROM kpi_doi WHERE ts = :ts", {"ts": ts})
    prods = read_sql("SELECT product_id, product_name, supplier_id FROM dim_products")
    ship = read_sql("SELECT * FROM fact_shipments WHERE actual_delivery_date > :ts - interval '180 days' AND actual_delivery_date <= :ts", {"ts": ts})
    for c in ("order_date", "scheduled_delivery_date", "actual_delivery_date"):
        ship[c] = pd.to_datetime(ship[c])
    lt = kpis.supplier_lead_time(ship)
    otd, n = kpis.otd_rate(ship, since=ts - pd.Timedelta(hours=config.OTD_WINDOW_HOURS))
    new = A.stockout_risk_alerts(doi, lt, prods, ts, config.MAX_STOCKOUT_ALERTS_PER_RUN) + A.otd_breach_alert(otd, n, ts)
    _insert_alerts(new)
    pending = read_sql("SELECT alert_id, alert_type, severity, message FROM alerts_log WHERE NOT dispatched ORDER BY created_at")
    rows = pending.to_dict("records")
    if rows and A.dispatch(rows):
        from sqlalchemy import text
        with get_engine().begin() as c:
            c.execute(text("UPDATE alerts_log SET dispatched = TRUE WHERE alert_id = ANY(:ids)"), {"ids": [r["alert_id"] for r in rows]})
    return {"new_rule_alerts": len(new), "dispatched": len(rows)}
