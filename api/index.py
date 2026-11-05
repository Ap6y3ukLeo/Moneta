"""Vercel Python-функция: /api/market, /api/deposits, /api/realty, /api/realty-photos, /api/history, /api/health, /api/ai, /api/forecast."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _proxy(self, method="GET", body=None):
        backend = os.environ.get("MONETKA_BACKEND_URL", "").rstrip("/")
        if not backend:
            return False
        params = parse_qs(urlparse(self.path).query)
        route = params.get("route", [""])[0]
        if not route:
            return False
        query = {key: values[0] for key, values in params.items() if key != "route"}
        url = f"{backend}/api/{route}"
        if query:
            url += "?" + urlencode(query)
        headers = {
            "Accept": "application/json",
            "X-Monetka-Token": os.environ.get("MONETKA_TOKEN", ""),
        }
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=90) as response:
                data = response.read()
                ctype = response.headers.get("Content-Type") or "application/json; charset=utf-8"
                self._send_raw(data, response.status, ctype)
            return True
        except HTTPError as exc:
            data = exc.read()
            ctype = exc.headers.get("Content-Type") or "application/json; charset=utf-8"
            self._send_raw(data, exc.code, ctype)
            return True
        except Exception:
            return False

    def do_GET(self):  # noqa: N802
        if self._proxy():
            return
        params = parse_qs(urlparse(self.path).query)
        route = params.get("route", [""])[0]
        try:
            if route == "market":
                # Кнопка и автообновление должны получать свежие котировки,
                # а не снапшот из репозитория.
                fx_only = str((params.get("fx") or ["0"])[0]).lower() in ("1", "true", "yes")
                payload = server.api_market(force=True, fx_only=fx_only)
            elif route == "deposits":
                payload = server.api_deposits()
            elif route == "realty":
                payload = server.api_realty()
            elif route == "history":
                payload = server.api_history({key: values[0] for key, values in params.items()})
            elif route == "realty_photos":
                payload = server.api_realty_photos({key: values[0] for key, values in params.items()})
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
        length = int(self.headers.get("Content-Length") or 0)
        if length > 32_000:
            self._send({"error": "Слишком большой запрос"}, 400)
            return
        body = self.rfile.read(length) if length else None
        if self._proxy("POST", body):
            return
        route = parse_qs(urlparse(self.path).query).get("route", [""])[0]
        try:
            if route not in ("ai", "forecast"):
                self._send({"error": "unknown route"}, 404)
                return
            payload = json.loads((body or b"{}").decode("utf-8"))
            self._send(server.api_ai(payload) if route == "ai" else server.api_forecast(payload))
        except ValueError as exc:
            self._send({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            self._send({"error": str(exc)}, 502)

    def _send_raw(self, body, status=200, ctype="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
