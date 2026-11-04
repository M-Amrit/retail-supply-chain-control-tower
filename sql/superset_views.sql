-- Datasets for Superset charts (see README "Dashboards").
CREATE OR REPLACE VIEW v_exec_overview AS
SELECT ts, stockout_rate_pct, otd_pct, avg_supplier_lead_time_days, active_alerts
FROM kpi_snapshot ORDER BY ts DESC LIMIT 1;

CREATE OR REPLACE VIEW v_kpi_trend AS SELECT * FROM kpi_snapshot;

CREATE OR REPLACE VIEW v_supplier_performance AS
SELECT s.supplier_id, s.supplier_name, s.reliability_score,
       COUNT(*) AS shipments,
       AVG(EXTRACT(EPOCH FROM (f.actual_delivery_date - f.order_date))/86400) AS avg_lead_time_days,
       STDDEV(EXTRACT(EPOCH FROM (f.actual_delivery_date - f.order_date))/86400) AS lead_time_stddev_days,
       100.0*AVG((f.actual_delivery_date <= f.scheduled_delivery_date)::int) AS otd_pct
FROM fact_shipments f JOIN dim_suppliers s USING (supplier_id)
WHERE f.actual_delivery_date IS NOT NULL
GROUP BY 1,2,3;

-- Inventory health is judged PER PRODUCT: stock summed over all warehouses vs the product-wide safety threshold
-- (dim_products.safety_stock_threshold = 3 days of the product's total demand, minimum 5 units). Comparing that
-- product-wide threshold with ONE warehouse's stock overstated shortages, and judging each product x warehouse SKU by its
-- own demand fails because DataCo's per-SKU sales are far too sparse (about 31 selling days per SKU over ~3 years).
-- Column names and types are kept so existing Superset charts keep working.
CREATE OR REPLACE VIEW v_inventory_health AS
WITH latest AS (
  SELECT DISTINCT ON (product_id, warehouse_id) product_id, warehouse_id, ts, current_stock_level
  FROM fact_inventory_hourly ORDER BY product_id, warehouse_id, ts DESC),
agg AS (
  SELECT product_id, SUM(current_stock_level)::int AS stock, MAX(ts) AS ts FROM latest GROUP BY product_id)
SELECT 'All warehouses'::text AS warehouse_id, p.product_id, p.product_name, p.category, a.stock AS current_stock_level,
       p.safety_stock_threshold, (a.stock < p.safety_stock_threshold) AS below_safety_stock,
       (a.stock = 0) AS stocked_out, a.ts
FROM agg a JOIN dim_products p USING (product_id);

CREATE OR REPLACE VIEW v_active_alerts AS
SELECT * FROM alerts_log WHERE created_at > now() - interval '24 hours' ORDER BY created_at DESC;
