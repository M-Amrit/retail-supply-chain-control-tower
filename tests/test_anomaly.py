import numpy as np, pandas as pd
from src import anomaly

T = pd.Timestamp("2026-11-01 12:00")


def test_delay_flagged_only_when_over_2_sigma():
    rng = np.random.default_rng(0)
    n = 200
    od = pd.Timestamp("2026-06-01") + pd.to_timedelta(np.arange(n), "D")
    lead = 5 + rng.normal(0, 0.5, n)
    s = pd.DataFrame({"shipment_id": [f"h{i}" for i in range(n)], "supplier_id": 1, "order_date": od,
                      "actual_delivery_date": od + pd.to_timedelta(lead, "D")})
    new = pd.DataFrame({"shipment_id": ["bad", "ok"], "supplier_id": 1, "order_date": [T - pd.Timedelta(days=12), T - pd.Timedelta(days=5)],
                        "actual_delivery_date": [T - pd.Timedelta(minutes=10)] * 2})   # leads: ~12d (bad), ~5d (ok)
    out = anomaly.detect_delivery_delays(pd.concat([s, new]), sigma=2.0, since=T - pd.Timedelta(hours=1))
    assert list(out["shipment_id"]) == ["bad"] and out.loc[0, "z"] > 2


def test_delay_needs_history():
    s = pd.DataFrame({"shipment_id": ["a"], "supplier_id": 1, "order_date": [T - pd.Timedelta(days=9)], "actual_delivery_date": [T]})
    assert anomaly.detect_delivery_delays(s, since=T - pd.Timedelta(hours=1)).empty


def _sales(latest_units):
    rng = np.random.default_rng(1)
    rows = []
    for b in range(1, 29):                       # 28 older 24h-buckets, ~20 +- 3 units
        rows.append((T - pd.Timedelta(hours=24 * b + 3), 1, "W", int(rng.normal(20, 3))))
    rows.append((T - pd.Timedelta(hours=2), 1, "W", latest_units))
    return pd.DataFrame(rows, columns=["ts", "product_id", "store_id", "units_sold"])


def test_spike_detected_and_normal_ignored():
    hit = anomaly.detect_demand_spikes(anomaly.bucket_sales(_sales(80), T), sigma=3)
    assert len(hit) == 1 and hit.loc[0, "z"] > 3
    assert anomaly.detect_demand_spikes(anomaly.bucket_sales(_sales(22), T), sigma=3).empty


def test_isolation_forest_flags_outlier():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"a": np.r_[rng.normal(0, 1, 300), [25.0]], "b": np.r_[rng.normal(0, 1, 300), [25.0]]})
    flags = anomaly.isolation_forest_flags(df, ["a", "b"], contamination=0.01)
    assert flags.iloc[-1]
