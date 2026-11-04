# Data dictionary
SKU = one product at one warehouse. All timestamps are naive UTC.

| Table | Column | Meaning |
|---|---|---|
| dim_suppliers | supplier_id, supplier_name | **Derived**: `product_id % N_SUPPLIERS + 1` (DataCo has no supplier entity) |
| | base_lead_time_days | Median order->delivery days of delivered shipments |
| | reliability_score | 1 - share of deliveries later than scheduled (0-1) |
| dim_products | category, unit_cost | DataCo category; unit_cost = **70% of mean list price (assumption)** |
| | safety_stock_threshold | ceil(3 x the product's total average daily demand across all warehouses), min 5. Product-wide, so the Inventory Health view compares it with the product's stock summed over all warehouses |
| fact_inventory_hourly | current_stock_level | Units on hand at `ts` (>=0). **Simulated** from observed demand |
| | incoming_shipment_qty | Units received in that hour |
| fact_shipments | scheduled/actual_delivery_date | order_date + DataCo scheduled / real shipping days. NULL actual => canceled |
| fact_sales_history | units_sold | Daily (history) or hourly (feed) units per product x region |
| alerts_log | alert_type | DELIVERY_DELAY (>2 sigma), DEMAND_SPIKE (>3 sigma), STOCKOUT_RISK (DOI < lead time), OTD_BREACH (<90%) |
| | dedup_key | Unique; makes alerting idempotent |
| kpi_snapshot | stockout_rate_pct, otd_pct (trailing 24h), avg_supplier_lead_time_days, active_alerts (24h) | One row per hour |
| kpi_doi | doi | stock / avg daily demand (trailing 30d); NULL if no demand |
| demand_forecast | yhat(_lower/_upper), model | 7-day daily forecast per category x region; model = prophet or seasonal_naive |
| inventory_runway | runway_days | Days until forecast demand exhausts category stock at a warehouse (cap 365) |
