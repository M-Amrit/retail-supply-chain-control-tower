# 6-minute demo script (screen recording)
Set `DEMO_ANOMALIES=1` and run 12+ hours of data first so every panel has content:
`python -m src.run_local --hours 12 --start "<hour after last inventory row>"`

| Time | Show | Say |
|---|---|---|
| 0:00 | README architecture diagram | Problem: managers learn about stock-outs after sales are lost. Goal: hourly visibility + early warning. |
| 0:45 | `docker compose ps`; Airflow UI -> DAG graph | Six tasks, hourly, retries, alerts run even if forecasting fails (`trigger_rule=all_done`). |
| 1:30 | Trigger the DAG; show tasks going green; logs of `run_kpi_transformation` | Idempotent: rerunning the same hour inserts nothing new. |
| 2:15 | psql: `select * from alerts_log order by created_at desc limit 5` | Four alert types, each with metric, threshold and a dedup key. |
| 3:00 | Superset: Executive Overview, Supplier Performance, Inventory Health | KPIs: stock-out rate, OTD, lead time, DOI. Point at a supplier with low OTD. |
| 4:00 | Slack channel with the alert digest (and the email) | One digest per run; a failing channel doesn't block the other. |
| 4:45 | Streamlit What-If: pick a supplier, drag delay 0 -> 14 days | Cascading stock-out impact by category, in cost-basis value. State the assumptions. |
| 5:30 | `pytest -q` output | 24 tests: KPI edge cases, anomaly thresholds, forecast runway, alert delivery against mock Slack/SMTP. |
Be upfront on camera: suppliers are derived and inventory is simulated (DataCo lacks both).
