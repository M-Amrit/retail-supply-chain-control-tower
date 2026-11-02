"""BEST-EFFORT, UNVERIFIED: create the Superset database, datasets, charts and an 'Executive Overview' dashboard
through Superset's REST API. Written from the API docs; it was NOT run against a live Superset. If a call fails it
prints the response so you can finish that piece by hand in the UI (README lists the views to use).
Usage: python scripts/superset_bootstrap.py [--url http://localhost:8088] [--user admin] [--password admin]"""
import argparse, json, sys
import requests

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://localhost:8088"); ap.add_argument("--user", default="admin")
ap.add_argument("--password", default="admin")
ap.add_argument("--db-uri", default="postgresql+psycopg2://tower:tower@postgres:5432/control_tower")
a = ap.parse_args()
S = requests.Session()


def call(method, path, **kw):
    r = S.request(method, a.url + path, timeout=30, **kw)
    if not r.ok:
        print(f"!! {method} {path} -> {r.status_code}: {r.text[:300]}"); return None
    return r.json()


tok = call("POST", "/api/v1/security/login", json={"username": a.user, "password": a.password, "provider": "db", "refresh": True})
if not tok: sys.exit("login failed")
S.headers.update({"Authorization": f"Bearer {tok['access_token']}", "Referer": a.url})
csrf = call("GET", "/api/v1/security/csrf_token/")
if csrf: S.headers["X-CSRFToken"] = csrf["result"]

db = call("POST", "/api/v1/database/", json={"database_name": "control_tower", "sqlalchemy_uri": a.db_uri, "expose_in_sqllab": True})
db_id = db["id"] if db else sys.exit("database create failed (may already exist: check Settings > Database Connections)")
ds = {}
for t in ["v_exec_overview", "v_kpi_trend", "v_supplier_performance", "v_inventory_health", "v_active_alerts"]:
    r = call("POST", "/api/v1/dataset/", json={"database": db_id, "schema": "public", "table_name": t})
    if r: ds[t] = r["id"]


def metric(expr, label):
    return {"expressionType": "SQL", "sqlExpression": expr, "label": label}


charts = [
    ("Stock-out rate %", "big_number_total", "v_exec_overview", {"metric": metric("MAX(stockout_rate_pct)", "stock-out %")}),
    ("On-time delivery % (24h)", "big_number_total", "v_exec_overview", {"metric": metric("MAX(otd_pct)", "OTD %")}),
    ("Avg supplier lead time (days)", "big_number_total", "v_exec_overview", {"metric": metric("MAX(avg_supplier_lead_time_days)", "lead days")}),
    ("Active alerts (24h)", "big_number_total", "v_exec_overview", {"metric": metric("MAX(active_alerts)", "alerts")}),
    ("OTD % trend", "echarts_timeseries_line", "v_kpi_trend",
     {"x_axis": "ts", "metrics": [metric("AVG(otd_pct)", "OTD %")], "time_grain_sqla": "PT1H"}),
    ("Supplier OTD %", "echarts_timeseries_bar", "v_supplier_performance",
     {"x_axis": "supplier_name", "metrics": [metric("AVG(otd_pct)", "OTD %")], "orientation": "vertical"}),
]
dash = call("POST", "/api/v1/dashboard/", json={"dashboard_title": "Executive Overview", "published": True})
dash_id = dash["id"] if dash else None
for name, viz, table, params in charts:
    if table not in ds: continue
    params = {**params, "viz_type": viz, "datasource": f"{ds[table]}__table", "adhoc_filters": [], "row_limit": 1000}
    body = {"slice_name": name, "viz_type": viz, "datasource_id": ds[table], "datasource_type": "table", "params": json.dumps(params)}
    if dash_id: body["dashboards"] = [dash_id]
    r = call("POST", "/api/v1/chart/", json=body)
    print(("created " if r else "FAILED  ") + name)
print(f"Done. Open {a.url}/superset/dashboard/{dash_id}/ — if charts are missing from the layout, add them via Edit dashboard.")
