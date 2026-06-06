"""Small HTTP health endpoint for Railway worker services."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return

        payload = json.dumps({
            "status": "healthy",
            "service": "contract-risk-worker",
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()
