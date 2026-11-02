"""Run the six pipeline tasks N times without Airflow (smoke test / demo / latency benchmark).
python -m src.run_local --hours 24 --start "2026-11-02 01:00" """
import argparse, json, logging, time
import pandas as pd
from src import pipeline as P

TASKS = ["extract_source_feed", "load_postgres_staging", "run_kpi_transformation", "run_anomaly_detection",
         "run_prophet_forecast", "dispatch_alerts"]


def run_once(ts) -> dict:
    out, timings = {}, {}
    def t(name, fn, *a):
        s = time.perf_counter(); r = fn(*a); timings[name] = round(time.perf_counter() - s, 2); return r
    feed = t(TASKS[0], P.extract_source_feed, ts)
    out["loaded"] = t(TASKS[1], P.load_postgres_staging, feed)
    out["kpi"] = t(TASKS[2], P.run_kpi_transformation, ts)
    out["anomalies_inserted"] = t(TASKS[3], P.run_anomaly_detection, ts)
    out["forecast"] = t(TASKS[4], P.run_prophet_forecast, ts)
    out["alerts"] = t(TASKS[5], P.dispatch_alerts, ts)
    out["timings_s"] = timings; out["total_s"] = round(sum(timings.values()), 2)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    ap = argparse.ArgumentParser(); ap.add_argument("--hours", type=int, default=3); ap.add_argument("--start", required=True)
    a = ap.parse_args()
    for h in range(a.hours):
        ts = pd.Timestamp(a.start) + pd.Timedelta(hours=h)
        print(ts, json.dumps(run_once(ts), default=str))
