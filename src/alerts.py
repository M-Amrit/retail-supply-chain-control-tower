"""Alert rule evaluation (pure) + Slack/SMTP delivery."""
from __future__ import annotations
import logging, smtplib
from email.message import EmailMessage
import pandas as pd
from src import config

log = logging.getLogger("alerts")


def stockout_risk_alerts(doi: pd.DataFrame, supplier_lead: pd.DataFrame, products: pd.DataFrame,
                         ts: pd.Timestamp, max_alerts: int = 25) -> list[dict]:
    """Trigger: DOI < supplier lead time. doi: product_id, warehouse_id, current_stock_level, doi.
    Ranked by the size of the gap (lead - DOI), capped to avoid alert floods; dedup per SKU per day."""
    m = (doi.dropna(subset=["doi"]).merge(products[["product_id", "supplier_id", "product_name"]], on="product_id")
            .merge(supplier_lead[["supplier_id", "avg_lead_time_days"]], on="supplier_id"))
    m = m[m["doi"] < m["avg_lead_time_days"]].copy()
    m["gap"] = m["avg_lead_time_days"] - m["doi"]
    out = []
    for r in m.sort_values("gap", ascending=False).head(max_alerts).itertuples():
        out.append(dict(alert_type="STOCKOUT_RISK", severity="critical" if r.doi < 1 else "high", entity_type="sku",
                        entity_id=f"{r.product_id}@{r.warehouse_id}", metric_value=float(r.doi),
                        threshold_value=float(r.avg_lead_time_days),
                        message=f"{r.product_name} @ {r.warehouse_id}: {r.doi:.1f} days of inventory < supplier lead time {r.avg_lead_time_days:.1f}d",
                        dedup_key=f"STOCKOUT_RISK:{r.product_id}:{r.warehouse_id}:{ts.date()}"))
    return out


def otd_breach_alert(otd_pct: float, n: int, ts: pd.Timestamp, baseline_pct: float | None = None,
                     mode: str | None = None) -> list[dict]:
    """OTD alert. mode="fixed": alert when window OTD < OTD_THRESHOLD_PCT.
    mode="baseline" (default): alert only when window OTD is BOTH >= OTD_DROP_POINTS below the trailing baseline
    AND statistically unlikely under it (binomial z >= OTD_Z). Fixed thresholds are meaningless when the normal
    level is already low (real DataCo data sits near 40%), and small hourly samples are very noisy."""
    mode = mode or config.OTD_ALERT_MODE
    if n < config.OTD_MIN_SAMPLE or pd.isna(otd_pct):
        return []
    key = f"OTD_BREACH:{ts.floor('h')}"
    if mode == "fixed":
        if otd_pct >= config.OTD_THRESHOLD_PCT:
            return []
        thr, msg = config.OTD_THRESHOLD_PCT, f"On-time delivery {otd_pct:.1f}% over last {config.OTD_WINDOW_HOURS}h (n={n}) < {config.OTD_THRESHOLD_PCT:.0f}%"
    else:
        if baseline_pct is None or pd.isna(baseline_pct):
            return []
        b = baseline_pct / 100.0
        se = (b * (1 - b) / n) ** 0.5
        drop = baseline_pct - otd_pct
        if drop < config.OTD_DROP_POINTS or se == 0 or (drop / 100.0) / se < config.OTD_Z:
            return []
        thr = baseline_pct - config.OTD_DROP_POINTS
        msg = (f"On-time delivery {otd_pct:.1f}% over last {config.OTD_WINDOW_HOURS}h (n={n}) is {drop:.1f} points "
               f"below the {config.OTD_BASELINE_DAYS}-day baseline of {baseline_pct:.1f}%")
    return [dict(alert_type="OTD_BREACH", severity="high", entity_type="network", entity_id="all",
                 metric_value=float(otd_pct), threshold_value=float(thr), message=msg, dedup_key=key)]


def delay_alerts(df: pd.DataFrame, ts: pd.Timestamp) -> list[dict]:
    return [dict(alert_type="DELIVERY_DELAY", severity="high" if r.z < 4 else "critical", entity_type="shipment",
                 entity_id=str(r.shipment_id), metric_value=float(r.lead_days), threshold_value=float(r.mean_lead + config.DELAY_SIGMA * r.std_lead),
                 message=f"Shipment {r.shipment_id} (supplier {r.supplier_id}) took {r.lead_days:.1f}d vs mean {r.mean_lead:.1f}d (z={r.z:.1f})",
                 dedup_key=f"DELIVERY_DELAY:{r.shipment_id}") for r in df.itertuples()]


def spike_alerts(df: pd.DataFrame, ts: pd.Timestamp) -> list[dict]:
    return [dict(alert_type="DEMAND_SPIKE", severity="medium", entity_type="sku", entity_id=f"{r.product_id}@{r.store_id}",
                 metric_value=float(r.units_latest), threshold_value=float(r.mean + config.SPIKE_SIGMA * r.std),
                 message=f"Demand spike {r.product_id}@{r.store_id}: {r.units_latest:.0f} units/24h vs mean {r.mean:.1f} (z={r.z:.1f})",
                 dedup_key=f"DEMAND_SPIKE:{r.product_id}:{r.store_id}:{ts.floor('h')}") for r in df.itertuples()]


def format_digest(alerts: list[dict]) -> str:
    lines = [f"*Control Tower: {len(alerts)} new alert(s)*"]
    lines += [f"• [{a['severity'].upper()}] {a['alert_type']}: {a['message']}" for a in alerts[:30]]
    if len(alerts) > 30:
        lines.append(f"…and {len(alerts) - 30} more (see alerts_log)")
    return "\n".join(lines)


def send_slack(text: str, url: str | None = None) -> bool:
    import requests
    url = url or config.SLACK_WEBHOOK_URL
    if not url:
        return False
    r = requests.post(url, json={"text": text}, timeout=10)
    r.raise_for_status()
    return True


def send_email(subject: str, body: str) -> bool:
    if not (config.SMTP_HOST and config.ALERT_EMAIL_TO):
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, config.SMTP_USER or "control-tower@localhost", config.ALERT_EMAIL_TO
    msg.set_content(body)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
        if config.SMTP_STARTTLS:
            s.starttls()
        if config.SMTP_USER:
            s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        s.send_message(msg)
    return True


def dispatch(alerts: list[dict]) -> bool:
    """Send one digest to every configured channel. Returns True if delivered somewhere, or if no channel is
    configured (console fallback) so alerts don't pile up undispatched in local/dev runs."""
    if not alerts:
        return True
    text = format_digest(alerts)
    sent, configured = False, bool(config.SLACK_WEBHOOK_URL or (config.SMTP_HOST and config.ALERT_EMAIL_TO))
    for fn in (lambda: send_slack(text), lambda: send_email(f"[Control Tower] {len(alerts)} new alerts", text)):
        try:
            sent = fn() or sent
        except Exception as e:  # one failing channel must not block the other
            log.error("alert channel failed: %s", e)
    if not configured:
        log.warning("No alert channel configured; console only:\n%s", text)
        return True
    return sent
