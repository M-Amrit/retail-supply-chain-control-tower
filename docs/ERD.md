# Entity-Relationship Diagram
```mermaid
erDiagram
  dim_suppliers ||--o{ dim_products : supplies
  dim_suppliers ||--o{ fact_shipments : ships
  dim_products  ||--o{ fact_shipments : "shipped item"
  dim_products  ||--o{ fact_inventory_hourly : stocked
  dim_products  ||--o{ fact_sales_history : sold
  dim_suppliers { int supplier_id PK
    text supplier_name
    numeric base_lead_time_days
    numeric reliability_score }
  dim_products { int product_id PK
    text category
    numeric unit_cost
    int safety_stock_threshold
    int supplier_id FK }
  fact_inventory_hourly { timestamp ts PK
    int product_id PK
    text warehouse_id PK
    int current_stock_level
    int incoming_shipment_qty }
  fact_shipments { text shipment_id PK
    text order_id
    int supplier_id FK
    int product_id FK
    timestamp order_date
    timestamp scheduled_delivery_date
    timestamp actual_delivery_date
    text status }
  fact_sales_history { timestamp ts PK
    int product_id PK
    text store_id PK
    int units_sold }
```
Derived/output tables (no FKs): `alerts_log`, `kpi_snapshot`, `kpi_doi`, `demand_forecast`, `inventory_runway`.
`store_id` and `warehouse_id` share one value space (DataCo `Order Region`) so demand joins to inventory.

# Pipeline flow
```mermaid
flowchart LR
  A[extract_source_feed<br/>CSV delta] --> B[load_postgres_staging<br/>stg_* -> fact_*] --> C[run_kpi_transformation]
  C --> D[run_anomaly_detection] --> F[dispatch_alerts]
  C --> E[run_prophet_forecast] --> F
  F --> S[Slack / SMTP]
  C & D & E --> P[(PostgreSQL)] --> U[Superset dashboards]
  P --> W[Streamlit What-If]
```
