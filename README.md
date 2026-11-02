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
docker compose up -d --build airflow superset whatif  # Airflow :8080 (password in `docker compose logs airflow`), Superset :8088 (admin/admin), What-If :8501
python scripts/superset_bootstrap.py          # optional, UNVERIFIED: creates datasets/charts/dashboard via REST API
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

## Airflow design note
Airflow pins SQLAlchemy 1.4; the pipeline needs 2.x, pandas and Prophet. Installing them into Airflow's own
environment risks breaking Airflow, so tasks run in an isolated venv (`PIPELINE_PYTHON`) through
`ExternalPythonOperator` (see `Dockerfile.airflow`). Harmless `pendulum`/`apache-airflow` metadata tracebacks may
appear in task logs; the tasks still succeed (`expect_airflow=False`).

## Alert tuning knobs (env)
`OTD_THRESHOLD_PCT` (default 90), `OTD_WINDOW_HOURS`, `OTD_MIN_SAMPLE`. On real DataCo data a large share of orders are
late by DataCo's own definition, so the 90% OTD alert may fire every hour: decide on a baseline-relative rule first.

## Verified vs. not verified
**Verified** (authoring sandbox: Ubuntu, Python 3.12, PostgreSQL 16, Airflow 2.10.5, Prophet 1.5, Streamlit 1.66):
* schema + views apply; ingestion; all six task functions for 24+ consecutive simulated hours; idempotent reruns
* the DAG imports and a full `airflow dags test` run finished with all 6 tasks SUCCESS (Prophet used for top-N series)
* the Streamlit What-If app runs headlessly with no exceptions and reacts to its controls
* Slack webhook and SMTP delivery against local mock servers (incl. Slack failing while email still succeeds)
* 24 automated tests; the loader against a fixture in the real DataCo format (latin-1, m/d/Y dates, cancellations)

**Not verified**
* the **official DataCo CSV itself** (needs your Kaggle/Mendeley login) — all runs used the synthetic fallback
* Docker Compose / Dockerfile.airflow builds (no Docker in the sandbox)
* Superset, including `scripts/superset_bootstrap.py` (written from API docs, never run)
* real Slack workspace / real SMTP provider
