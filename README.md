# Retail & Supply Chain Control Tower

Near-real-time visibility into inventory, deliveries and suppliers: hourly Airflow pipeline on PostgreSQL,
KPIs, anomaly detection, Prophet demand forecasting + inventory runway, Superset dashboards, a Streamlit What-If
panel, and Slack/Email alerting. See `docs/ERD.md` (ERD + flow diagram) and `docs/DATA_DICTIONARY.md`.

## Dataset decision (read this)
**DataCo Smart Supply Chain** is the primary dataset, but it does **not** contain a supplier entity or an inventory
feed. This project therefore: (a) *derives* suppliers by deterministic bucketing of products, (b) *simulates*
inventory + hourly deltas from observed demand, (c) *rebases* DataCo's 2015-18 dates to end yesterday.
Treat supplier-level conclusions as a demonstration of the system, not as findings about real suppliers.
If `data/DataCoSupplyChainDataset.csv` is absent (or `--synthetic`), a synthetic dataset with DataCo's columns is used.
Download DataCo from Mendeley/Kaggle (needs your login) and place it in `data/`.

## Quick start
```bash
cp .env.example .env
docker compose up -d postgres                 # applies sql/schema.sql + superset views
docker compose run --rm ingest                # python -m src.ingest_data  (add --synthetic if no CSV)
docker compose up -d airflow superset whatif  # Airflow :8080, Superset :8088 (admin/admin), What-If :8501
```
Without Docker: `pip install -r requirements.txt`, point `DATABASE_URL` at a Postgres with `sql/schema.sql` applied,
`python -m src.ingest_data`, then `python -m src.run_local --hours 24 --start "<ts after last inventory row>"` to
run the six tasks without Airflow. `DEMO_ANOMALIES=1` injects delays/spikes so alerts fire.
Tests: `python -m pytest -q`.

## Design choices
* SKU = product x warehouse. KPI formulas live in `src/kpis.py` as pure functions; SQL only fetches data.
* Delay anomalies: per-supplier mean/std from deliveries *before* the current hour, so a fresh outlier can't mask itself.
* Demand spikes: 24h buckets aligned to the run time (trailing 24h vs prior 28 buckets), so hourly runs never compare a
  partial calendar day to full days. Requires mean >= 3 and lift >= 8 units: pure 3-sigma on low-count Poisson demand
  produced ~5x more false alerts in testing.
* Forecast: Prophet for the top-N series by volume, seasonal-naive for the long tail and as a fallback if Prophet fails;
  re-fit every 24h, runway recomputed hourly from the stored forecast.
* Alerts: `dedup_key` unique constraint => reruns/retries never double-alert; one digest per run; a failing channel
  doesn't block the other.
* Added `dim_products.supplier_id` (not in the brief) to model supplier->product dependency for the What-If panel.

## Superset dashboards
Add Postgres (`postgresql://tower:tower@postgres:5432/control_tower`) as a database, then create datasets from:
`v_exec_overview` (big-number tiles), `v_kpi_trend` (time series), `v_supplier_performance` (bar/table:
lead time variance, OTD, reliability), `v_inventory_health` (filter `below_safety_stock`), `v_active_alerts`.
Dashboards are **not** pre-exported; build them from these views (≈30 min).
The What-If panel is the Streamlit app (`app/whatif.py`), embeddable in Superset via iframe/Markdown chart.

## Verified vs. not verified
Verified in an authoring sandbox (Postgres 16, Python 3.12): schema/views apply; ingestion; all six task functions
for 24 consecutive simulated hours; idempotent reruns; 19 unit tests.
**Not verified**: Docker Compose, the Airflow DAG executing under Airflow (only compiled), Prophet fitting, Superset,
the Streamlit UI (its SQL was run), and Slack/SMTP delivery (only the no-channel console path).
