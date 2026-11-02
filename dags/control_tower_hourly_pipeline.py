from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from src import pipeline as P

default_args = {"owner": "data-eng", "retries": 2, "retry_delay": timedelta(minutes=2),
                "execution_timeout": timedelta(minutes=20)}

with DAG("control_tower_hourly_pipeline", start_date=datetime(2026, 10, 30), schedule="@hourly",
         catchup=False, max_active_runs=1, default_args=default_args, tags=["supply-chain"]) as dag:
    ts = "{{ data_interval_end.strftime('%Y-%m-%d %H:00:00') }}"   # snapshot hour = end of the interval
    extract = PythonOperator(task_id="extract_source_feed", python_callable=P.extract_source_feed, op_args=[ts])
    load = PythonOperator(task_id="load_postgres_staging", python_callable=P.load_postgres_staging,
                          op_args=["{{ ti.xcom_pull(task_ids='extract_source_feed') }}"])
    kpi = PythonOperator(task_id="run_kpi_transformation", python_callable=P.run_kpi_transformation, op_args=[ts])
    anom = PythonOperator(task_id="run_anomaly_detection", python_callable=P.run_anomaly_detection, op_args=[ts])
    fcst = PythonOperator(task_id="run_prophet_forecast", python_callable=P.run_prophet_forecast, op_args=[ts])
    alert = PythonOperator(task_id="dispatch_alerts", python_callable=P.dispatch_alerts, op_args=[ts],
                           trigger_rule="all_done")  # still alert if the forecast step failed
    extract >> load >> kpi >> [anom, fcst] >> alert
