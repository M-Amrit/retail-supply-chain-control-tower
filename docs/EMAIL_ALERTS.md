# Email alerts (optional)
Slack already covers the alerting requirement. Email is a second channel: when both are configured, each hourly digest
goes to both, and one failing does not block the other. Delivery to a real provider has **not** been tested by the
author; the code path was tested against a mock SMTP server.

## Gmail
1. Turn on 2-Step Verification for the account (myaccount.google.com, Security).
2. Create an **App password** (myaccount.google.com/apppasswords) and copy the 16 characters, without spaces.
3. In `.env` (never commit it; `.gitignore` already excludes it):
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=<the 16-character app password>
ALERT_EMAIL_TO=you@gmail.com
```
4. Recreate Airflow so it reads `.env`: `docker compose up -d --force-recreate airflow` (the login resets; see README).
5. Test from the container (prints `True` when the server accepted the message):
```
docker compose exec -w /app -e PYTHONPATH=/app airflow /opt/pipeline-venv/bin/python -c "from src import alerts; print(alerts.send_email('Control Tower test', 'hello'))"
```
Check Spam if nothing arrives. Then insert a TEST alert and trigger the DAG as for Slack.

## Outlook / Microsoft 365
Use `SMTP_HOST=smtp.office365.com`, port 587. Many organisations disable SMTP sign-in for mailboxes, so this may be
refused; Gmail with an app password is the easier route.

## Troubleshooting
* `False` printed: `SMTP_HOST` or `ALERT_EMAIL_TO` is empty in the container, so `.env` was not read. Recreate Airflow.
* Authentication error: the app password is wrong or contains spaces.
* Local mock servers without TLS: set `SMTP_STARTTLS=0`. Keep it on for real providers.
