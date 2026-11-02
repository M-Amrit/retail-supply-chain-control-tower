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

CREATE OR REPLACE VIEW v_inventory_health AS
WITH latest AS (
  SELECT DISTINCT ON (product_id, warehouse_id) product_id, warehouse_id, ts, current_stock_level
  FROM fact_inventory_hourly ORDER BY product_id, warehouse_id, ts DESC)
SELECT l.warehouse_id, p.product_id, p.product_name, p.category, l.current_stock_level,
       p.safety_stock_threshold, (l.current_stock_level < p.safety_stock_threshold) AS below_safety_stock,
       (l.current_stock_level = 0) AS stocked_out, l.ts
FROM latest l JOIN dim_products p USING (product_id);

CREATE OR REPLACE VIEW v_active_alerts AS
SELECT * FROM alerts_log WHERE created_at > now() - interval '24 hours' ORDER BY created_at DESC;
