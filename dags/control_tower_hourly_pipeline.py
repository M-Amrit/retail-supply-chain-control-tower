"""Hourly Control Tower DAG.

Tasks run in a SEPARATE virtualenv (PIPELINE_PYTHON) via ExternalPythonOperator because Airflow pins
SQLAlchemy 1.4 while the pipeline needs 2.x (pandas/Prophet/scikit-learn also stay out of Airflow's env).
"""
import os
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import ExternalPythonOperator

PY = os.getenv("PIPELINE_PYTHON", "/opt/pipeline-venv/bin/python")
PROJECT = os.getenv("PROJECT_DIR", "/app")
ENV = {k: os.environ[k] for k in os.environ if k in (
    "DATABASE_URL", "SLACK_WEBHOOK_URL", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "ALERT_EMAIL_TO",
    "DEMO_ANOMALIES", "FEED_DIR", "OTD_ALERT_MODE", "OTD_THRESHOLD_PCT", "OTD_DROP_POINTS", "OTD_MIN_SAMPLE", "OTD_WINDOW_HOURS", "FORECAST_TOP_N_PROPHET", "FORECAST_REFRESH_HOURS")}
ENV["PYTHONPATH"] = PROJECT


def run_task(task, ts, upstream=None):
    """Runs inside PIPELINE_PYTHON. Must be self-contained: Airflow ships this function's SOURCE to the venv,
    so no closures / module-level names (imports live inside)."""
    import os, sys
    sys.path.insert(0, os.environ.get("PYTHONPATH", "/app"))
    from src import pipeline as P
    if task == "load_postgres_staging":
        return P.load_postgres_staging(upstream)
    return getattr(P, task)(ts)


default_args = {"owner": "data-eng", "retries": int(os.getenv("TASK_RETRIES", "2")), "retry_delay": timedelta(minutes=2), "execution_timeout": timedelta(minutes=20)}

with DAG("control_tower_hourly_pipeline", start_date=datetime(2026, 10, 30), schedule="@hourly", catchup=False,
         max_active_runs=1, default_args=default_args, tags=["supply-chain"]) as dag:
    TS = "{{ data_interval_end.strftime('%Y-%m-%d %H:00:00') }}"
    def op(name, **kw):
        return ExternalPythonOperator(task_id=name, python=PY, python_callable=run_task, env_vars=ENV, expect_airflow=False,
                                      op_kwargs={"task": name, "ts": TS, **kw})
    extract = op("extract_source_feed")
    load = op("load_postgres_staging", upstream="{{ ti.xcom_pull(task_ids='extract_source_feed') }}")
    kpi = op("run_kpi_transformation")
    anom = op("run_anomaly_detection")
    fcst = op("run_prophet_forecast")
    alert = ExternalPythonOperator(task_id="dispatch_alerts", python=PY, python_callable=run_task, env_vars=ENV, expect_airflow=False,
                                   op_kwargs={"task": "dispatch_alerts", "ts": TS}, trigger_rule="all_done")  # alert even if forecast failed
    extract >> load >> kpi >> [anom, fcst] >> alert
