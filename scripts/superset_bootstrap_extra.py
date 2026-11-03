"""BEST-EFFORT, UNVERIFIED against a live Superset: adds the 'Inventory Health' and 'Supplier Performance' dashboards.

Run AFTER scripts/superset_bootstrap.py (it reuses that script's database and datasets). Safe to re-run: existing
dashboards and charts are skipped. If any call fails the server's message is printed so you can finish that chart by
hand from the v_inventory_health / v_supplier_performance datasets.
Usage: python scripts/superset_bootstrap_extra.py [--url http://localhost:8088] [--user admin] [--password admin]"""
import argparse, json, sys
import requests

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://localhost:8088"); ap.add_argument("--user", default="admin")
ap.add_argument("--password", default="admin")
a = ap.parse_args()
S = requests.Session()


def call(method, path, **kw):
    r = S.request(method, a.url + path, timeout=30, **kw)
    if not r.ok:
        print(f"!! {method} {path} -> {r.status_code}: {r.text[:300]}")
        return None
    return r.json()


def find(resource, col, value):
    """First row of /api/v1/<resource>/ whose <col> equals value, or None."""
    v = f"'{value}'" if " " in value else value
    r = call("GET", f"/api/v1/{resource}/", params={"q": f"(filters:!((col:{col},opr:eq,value:{v})))"})
    return (r or {}).get("result", [None])[0] if r and r.get("result") else None


def metric(expr, label):
    return {"expressionType": "SQL", "sqlExpression": expr, "label": label}


tok = call("POST", "/api/v1/security/login", json={"username": a.user, "password": a.password, "provider": "db", "refresh": True})
if not tok:
    sys.exit("login failed")
S.headers.update({"Authorization": f"Bearer {tok['access_token']}", "Referer": a.url})
csrf = call("GET", "/api/v1/security/csrf_token/")
if csrf:
    S.headers["X-CSRFToken"] = csrf["result"]

BELOW = "SUM(CASE WHEN below_safety_stock THEN 1 ELSE 0 END)"
OUT = "SUM(CASE WHEN stocked_out THEN 1 ELSE 0 END)"
DASHBOARDS = {
    "Inventory Health": ("v_inventory_health", [
        ("SKUs below safety stock", "big_number_total", {"metric": metric(BELOW, "below safety stock")}),
        ("SKUs stocked out", "big_number_total", {"metric": metric(OUT, "stocked out")}),
        ("SKUs tracked", "big_number_total", {"metric": metric("COUNT(*)", "SKUs")}),
        ("Below safety stock by category", "echarts_timeseries_bar",
         {"x_axis": "category", "metrics": [metric(BELOW, "below safety stock")], "orientation": "vertical"}),
        ("Stock vs safety threshold by category", "table",
         {"query_mode": "aggregate", "groupby": ["category"], "all_columns": [], "order_desc": True,
          "metrics": [metric("SUM(current_stock_level)", "stock"), metric("SUM(safety_stock_threshold)", "safety threshold")]}),
    ]),
    "Supplier Performance": ("v_supplier_performance", [
        ("Average lead time by supplier (days)", "echarts_timeseries_bar",
         {"x_axis": "supplier_name", "metrics": [metric("AVG(avg_lead_time_days)", "lead time (days)")], "orientation": "vertical"}),
        ("Lead-time variability by supplier (std dev, days)", "echarts_timeseries_bar",
         {"x_axis": "supplier_name", "metrics": [metric("AVG(lead_time_stddev_days)", "std dev (days)")], "orientation": "vertical"}),
        ("Reliability score by supplier", "echarts_timeseries_bar",
         {"x_axis": "supplier_name", "metrics": [metric("AVG(reliability_score)", "reliability")], "orientation": "vertical"}),
        ("Supplier ranking", "table",
         {"query_mode": "aggregate", "groupby": ["supplier_name"], "all_columns": [], "order_desc": True,
          "timeseries_limit_metric": metric("AVG(otd_pct)", "OTD %"),
          "metrics": [metric("AVG(otd_pct)", "OTD %"), metric("AVG(avg_lead_time_days)", "lead time (days)"),
                      metric("AVG(reliability_score)", "reliability"), metric("SUM(shipments)", "shipments")]}),
    ]),
}

failures = 0
for title, (table, charts) in DASHBOARDS.items():
    ds = find("dataset", "table_name", table)
    if not ds:
        print(f"!! dataset {table} not found. Run scripts/superset_bootstrap.py first, or add it in Datasets."); failures += 1
        continue
    if find("dashboard", "dashboard_title", title):
        print(f"skip dashboard '{title}' (already exists)")
        continue
    dash = call("POST", "/api/v1/dashboard/", json={"dashboard_title": title, "published": True})
    if not dash:
        failures += 1
        continue
    for name, viz, params in charts:
        if find("chart", "slice_name", name):
            print(f"skip chart '{name}' (already exists)")
            continue
        p = {**params, "viz_type": viz, "datasource": f"{ds['id']}__table", "adhoc_filters": [], "row_limit": 1000}
        body = {"slice_name": name, "viz_type": viz, "datasource_id": ds["id"], "datasource_type": "table",
                "params": json.dumps(p), "dashboards": [dash["id"]]}
        ok = call("POST", "/api/v1/chart/", json=body)
        failures += 0 if ok else 1
        print(("created " if ok else "FAILED  ") + name)
    print(f"Dashboard '{title}': {a.url}/superset/dashboard/{dash['id']}/")
sys.exit(1 if failures else 0)
