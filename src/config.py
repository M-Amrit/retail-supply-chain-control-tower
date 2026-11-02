"""Central configuration (env-overridable)."""
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://tower:tower@localhost:5432/control_tower")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")

DATACO_CSV = os.getenv("DATACO_CSV", "data/DataCoSupplyChainDataset.csv")
N_SUPPLIERS = int(os.getenv("N_SUPPLIERS", "12"))

DELAY_SIGMA = 2.0            # delivery delay anomaly threshold (std devs over supplier mean lead time)
SPIKE_SIGMA = 3.0            # demand spike threshold
OTD_THRESHOLD_PCT = 90.0     # alert when OTD in window falls below this
OTD_WINDOW_HOURS = int(os.getenv("OTD_WINDOW_HOURS", "1"))
OTD_MIN_SAMPLE = int(os.getenv("OTD_MIN_SAMPLE", "5"))   # avoid alerting on 1-2 shipments
FORECAST_HORIZON_DAYS = 7
FORECAST_TOP_N_PROPHET = int(os.getenv("FORECAST_TOP_N_PROPHET", "40"))
FORECAST_REFRESH_HOURS = int(os.getenv("FORECAST_REFRESH_HOURS", "24"))
MAX_STOCKOUT_ALERTS_PER_RUN = 25
DEMO_ANOMALIES = os.getenv("DEMO_ANOMALIES", "0") == "1"   # inject spikes/delays so alerts fire in a demo
