# Demo script (about 7 minutes)

## Before you start (5 minutes, do it once, off camera)
Fast way (untested helper; it starts Docker, waits for services, prints the Airflow password and opens the tabs):
`powershell -ExecutionPolicy Bypass -File scripts\demo_prep.ps1`  (add `-InsertTestAlert` to queue a demo alert for Slack).
If it misbehaves, follow the manual list below.

1. Open Docker Desktop and wait for "Engine running". Run `docker compose up -d` and wait about 3 minutes.
2. `docker compose ps`: postgres and superset should say `(healthy)`.
3. Airflow: `docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt`, sign in as `admin` in a **private
   window** at http://localhost:8080, switch the DAG on, trigger it once and wait for six green tasks.
4. Open in separate tabs: Superset dashboard (`admin` / `admin`), What-If (http://localhost:8501), Slack #alerts.
5. What-If: Supplier-01, slider at 14 days. Optional: insert a TEST alert row so the next run posts to Slack.
6. Close notifications. Zoom the browser to about 80%.

If anything is down, use the screenshots in `docs/screenshots` and say so.

## Script
| Time | Show | Say |
|---|---|---|
| 0:00 | Title slide | Teams learn about stock-outs after the sales are lost. This gives an hourly view that flags risk early. |
| 0:40 | Architecture slide, then Airflow graph | Source, PostgreSQL, six hourly tasks, outputs. The anomaly and forecast tasks run in parallel and alerts still go out if the forecast fails. |
| 1:30 | Data slide | 180,519 real DataCo shipments. DataCo has no suppliers or inventory, so suppliers are derived and stock is simulated. I say this up front because it limits what the supplier results mean. |
| 2:15 | Superset Executive Overview | Stock-out rate, on-time delivery, lead time, active alerts. On-time near 43% is DataCo's own late rule. The supplier bars look alike because suppliers are derived. |
| 3:15 | Slack #alerts | Detections arrive within the hour: shipments taking 12 to 14 days against a 3.5 day mean, z-scores above 5. These shipments are simulated hourly deliveries. |
| 4:15 | What-If | Drag the delay from 0 to 14 days. Two SKUs are affected, with value at risk at cost basis. Assumes no alternate sourcing. |
| 5:15 | Terminal: `python -m pytest -q` | 26 tests: KPI edge cases, anomaly thresholds, forecast runway, alert delivery against mock Slack and SMTP. |
| 6:00 | Challenges slide | Four things that changed the design: data mismatch, Airflow dependency conflict, alert noise from a fixed 90% rule, and a Slack failure that looked like success. |
| 6:45 | Next steps | Real supplier data, more dashboards, better forecasts, scale testing. |

## Questions you may get
* Why is on-time delivery so low? DataCo's late-delivery definition; the alert compares against the 30-day baseline instead of a fixed 90%.
* Are the suppliers real? No. They are derived from products, so rankings are illustrative.
* How accurate is the forecast? Not measured on the real data yet; an earlier backtest on synthetic data showed a small gain over a seasonal baseline.
