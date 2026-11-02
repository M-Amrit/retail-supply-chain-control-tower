"""Integration: real HTTP + SMTP round trips against local mock servers (no external accounts needed)."""
import json, socket, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from src import alerts, config

ALERTS = [{"alert_id": 1, "alert_type": "STOCKOUT_RISK", "severity": "high", "message": "Product 1 @ West: 1.0 days < lead 4.0d"}]


def _slack_server(status=200):
    got = []
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(status); self.end_headers(); self.wfile.write(b"ok")
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, got


def test_slack_webhook_delivery(monkeypatch):
    srv, got = _slack_server()
    monkeypatch.setattr(config, "SLACK_WEBHOOK_URL", f"http://127.0.0.1:{srv.server_port}/hook")
    monkeypatch.setattr(config, "SMTP_HOST", "")
    assert alerts.dispatch(ALERTS) is True
    assert "STOCKOUT_RISK" in got[0]["text"] and "1 new alert" in got[0]["text"]
    srv.shutdown()


def test_slack_failure_returns_false_so_alerts_stay_undispatched(monkeypatch):
    srv, got = _slack_server(status=500)
    monkeypatch.setattr(config, "SLACK_WEBHOOK_URL", f"http://127.0.0.1:{srv.server_port}/hook")
    monkeypatch.setattr(config, "SMTP_HOST", "")
    assert alerts.dispatch(ALERTS) is False          # not marked dispatched => retried next hour
    srv.shutdown()


def test_email_delivery_and_slack_failure_does_not_block_email(monkeypatch):
    aiosmtpd = pytest.importorskip("aiosmtpd.controller")
    box = []
    class Handler:
        async def handle_DATA(self, server, session, envelope):
            box.append(envelope); return "250 OK"
    sk = socket.socket(); sk.bind(("127.0.0.1", 0)); port = sk.getsockname()[1]; sk.close()
    ctl = aiosmtpd.Controller(Handler(), hostname="127.0.0.1", port=port); ctl.start()
    srv, _ = _slack_server(status=500)
    try:
        monkeypatch.setattr(config, "SLACK_WEBHOOK_URL", f"http://127.0.0.1:{srv.server_port}/hook")
        monkeypatch.setattr(config, "SMTP_HOST", "127.0.0.1"); monkeypatch.setattr(config, "SMTP_PORT", port)
        monkeypatch.setattr(config, "SMTP_STARTTLS", False); monkeypatch.setattr(config, "SMTP_USER", "")
        monkeypatch.setattr(config, "ALERT_EMAIL_TO", "mgr@example.com")
        assert alerts.dispatch(ALERTS) is True       # email succeeded even though Slack returned 500
        assert box and box[0].rcpt_tos == ["mgr@example.com"] and b"STOCKOUT_RISK" in box[0].content
    finally:
        ctl.stop(); srv.shutdown()
