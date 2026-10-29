"""Tiny HTTP server: /health (JSON) and /metrics (Prometheus text)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

SNAPSHOT = {"alerts": [], "metrics": {}}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({"ok": not any(a["severity"] == "critical" for a in SNAPSHOT["alerts"]),
                               "alerts": SNAPSHOT["alerts"]}).encode()
            ctype = "application/json"
        elif self.path == "/metrics":
            body = "".join(f"dhg_{k} {v}\n" for k, v in SNAPSHOT["metrics"].items()).encode()
            ctype = "text/plain; version=0.0.4"
        else:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def start(port=9100):
    srv = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
