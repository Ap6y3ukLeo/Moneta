"""Vercel Python-функция: /api/market, /api/deposits, /api/realty, /api/health, /api/ai."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        route = parse_qs(urlparse(self.path).query).get("route", [""])[0]
        try:
            if route == "market":
                payload = server.api_market()
            elif route == "deposits":
                payload = server.api_deposits()
            elif route == "realty":
                payload = server.api_realty()
            elif route == "health":
                payload = {"ok": True, "time": server.now_msk()}
            else:
                payload = {"error": "unknown route"}
                self._send(payload, 404)
                return
            self._send(payload)
        except Exception as exc:  # noqa: BLE001
            self._send({"error": str(exc)}, 502)

    def do_POST(self):  # noqa: N802
        route = parse_qs(urlparse(self.path).query).get("route", [""])[0]
        try:
            if route != "ai":
                self._send({"error": "unknown route"}, 404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > 32_000:
                raise ValueError("Слишком большой запрос")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            self._send(server.api_ai(payload))
        except ValueError as exc:
            self._send({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            self._send({"error": str(exc)}, 502)

    def _send(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
