-- Control Tower schema. Deviation from brief: dim_products.supplier_id added so
-- supplier -> product dependency (needed by the What-If panel) is modelled explicitly.
CREATE TABLE IF NOT EXISTS dim_suppliers (
  supplier_id INT PRIMARY KEY,
  supplier_name TEXT NOT NULL,
  base_lead_time_days NUMERIC(6,2) NOT NULL,
  reliability_score NUMERIC(5,4) NOT NULL CHECK (reliability_score BETWEEN 0 AND 1)
);
CREATE TABLE IF NOT EXISTS dim_products (
  product_id INT PRIMARY KEY,
  product_name TEXT,
  category TEXT NOT NULL,
  unit_cost NUMERIC(12,2) NOT NULL,
  safety_stock_threshold INT NOT NULL,
  supplier_id INT NOT NULL REFERENCES dim_suppliers(supplier_id)
);
CREATE TABLE IF NOT EXISTS fact_inventory_hourly (
  ts TIMESTAMP NOT NULL,
  product_id INT NOT NULL REFERENCES dim_products(product_id),
  warehouse_id TEXT NOT NULL,
  current_stock_level INT NOT NULL CHECK (current_stock_level >= 0),
  incoming_shipment_qty INT NOT NULL DEFAULT 0,
  PRIMARY KEY (ts, product_id, warehouse_id)
);
CREATE TABLE IF NOT EXISTS fact_shipments (
  shipment_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  supplier_id INT NOT NULL REFERENCES dim_suppliers(supplier_id),
  product_id INT REFERENCES dim_products(product_id),
  order_date TIMESTAMP NOT NULL,
  scheduled_delivery_date TIMESTAMP NOT NULL,
  actual_delivery_date TIMESTAMP,
  status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_sales_history (
  ts TIMESTAMP NOT NULL,
  product_id INT NOT NULL REFERENCES dim_products(product_id),
  store_id TEXT NOT NULL,
  units_sold INT NOT NULL,
  PRIMARY KEY (ts, product_id, store_id)
);
-- Staging mirrors (hourly delta lands here before merge)
CREATE TABLE IF NOT EXISTS stg_inventory_hourly (LIKE fact_inventory_hourly INCLUDING DEFAULTS);
CREATE TABLE IF NOT EXISTS stg_shipments        (LIKE fact_shipments INCLUDING DEFAULTS);
CREATE TABLE IF NOT EXISTS stg_sales_history    (LIKE fact_sales_history INCLUDING DEFAULTS);

CREATE TABLE IF NOT EXISTS alerts_log (
  alert_id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  alert_type TEXT NOT NULL,      -- DELIVERY_DELAY | DEMAND_SPIKE | STOCKOUT_RISK | OTD_BREACH
  severity TEXT NOT NULL,
  entity_type TEXT, entity_id TEXT,
  metric_value DOUBLE PRECISION, threshold_value DOUBLE PRECISION,
  message TEXT,
  dispatched BOOLEAN NOT NULL DEFAULT FALSE,
  dedup_key TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS kpi_snapshot (
  ts TIMESTAMP PRIMARY KEY, stockout_rate_pct DOUBLE PRECISION, otd_pct DOUBLE PRECISION,
  avg_supplier_lead_time_days DOUBLE PRECISION, active_alerts INT
);
CREATE TABLE IF NOT EXISTS kpi_doi (
  ts TIMESTAMP NOT NULL, product_id INT NOT NULL, warehouse_id TEXT NOT NULL,
  current_stock INT, avg_daily_demand DOUBLE PRECISION, doi DOUBLE PRECISION,
  PRIMARY KEY (ts, product_id, warehouse_id)
);
CREATE TABLE IF NOT EXISTS demand_forecast (
  generated_at TIMESTAMP NOT NULL, category TEXT NOT NULL, store_id TEXT NOT NULL,
  forecast_date DATE NOT NULL, yhat DOUBLE PRECISION, yhat_lower DOUBLE PRECISION, yhat_upper DOUBLE PRECISION,
  model TEXT, PRIMARY KEY (generated_at, category, store_id, forecast_date)
);
CREATE TABLE IF NOT EXISTS inventory_runway (
  generated_at TIMESTAMP NOT NULL, category TEXT NOT NULL, warehouse_id TEXT NOT NULL,
  current_stock INT, runway_days DOUBLE PRECISION,
  PRIMARY KEY (generated_at, category, warehouse_id)
);
CREATE INDEX IF NOT EXISTS ix_inv_ts ON fact_inventory_hourly (ts DESC);
CREATE INDEX IF NOT EXISTS ix_inv_prod ON fact_inventory_hourly (product_id, warehouse_id, ts DESC);
CREATE INDEX IF NOT EXISTS ix_ship_supplier ON fact_shipments (supplier_id, order_date);
CREATE INDEX IF NOT EXISTS ix_ship_actual ON fact_shipments (actual_delivery_date);
CREATE INDEX IF NOT EXISTS ix_sales_ts ON fact_sales_history (ts);
CREATE INDEX IF NOT EXISTS ix_sales_prod ON fact_sales_history (product_id, store_id, ts);
CREATE INDEX IF NOT EXISTS ix_prod_supplier ON dim_products (supplier_id);
CREATE INDEX IF NOT EXISTS ix_alerts_created ON alerts_log (created_at DESC);
