import io
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot
import server
from api import index as vercel_api


class _FakeResponse:
    def __init__(self, body=b'{"ok":true}', status=200, ctype="application/json"):
        self._body = body
        self.status = status
        self.headers = {"Content-Type": ctype}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class VercelProxySecurityTest(unittest.TestCase):
    def _make_handler(self, path, body=b""):
        h = vercel_api.handler.__new__(vercel_api.handler)
        h.path = path
        h.headers = {"Content-Length": str(len(body))}
        h.rfile = io.BytesIO(body)
        h.sent = []
        h._send = lambda payload, status=200: h.sent.append(("json", status, payload))
        h._send_raw = lambda data, status=200, ctype="", location=None: h.sent.append(("raw", status, data))
        return h

    def test_blocks_admin_post_routes_from_proxying(self):
        proxied = []

        def fake_open(req, timeout=90):
            proxied.append((req.get_method(), req.full_url))
            return _FakeResponse()

        with patch.object(vercel_api, "_backend_urls", return_value=["https://backend.example"]), \
             patch.object(vercel_api._opener, "open", side_effect=fake_open):
            for route in ("cards", "card_update", "card_delete", "links", "order", "texts",
                          "push_send", "realty_import", "../secret"):
                h = self._make_handler(f"/api/index?route={route}", b'{"x":1}')
                h.do_POST()
                self.assertEqual(h.sent[-1][1], 404, f"POST {route} must be rejected")
        self.assertEqual(proxied, [])

    def test_blocks_admin_get_routes_from_proxying(self):
        proxied = []

        def fake_open(req, timeout=90):
            proxied.append((req.get_method(), req.full_url))
            return _FakeResponse()

        with patch.object(vercel_api, "_backend_urls", return_value=["https://backend.example"]), \
             patch.object(vercel_api._opener, "open", side_effect=fake_open):
            for route in ("clicks", "visits", "links", "../etc"):
                h = self._make_handler(f"/api/index?route={route}")
                h.do_GET()
                self.assertEqual(h.sent[-1][1], 404, f"GET {route} must be rejected")
        self.assertEqual(proxied, [])

    def test_allows_public_routes_and_maps_paths(self):
        proxied = []

        def fake_open(req, timeout=90):
            proxied.append((req.get_method(), req.full_url, req.get_header("Content-type")))
            return _FakeResponse()

        with patch.object(vercel_api, "_backend_urls", return_value=["https://backend.example"]), \
             patch.object(vercel_api._opener, "open", side_effect=fake_open):
            h_get = self._make_handler("/api/index?route=realty_photos&id=yandex:1")
            h_get.do_GET()
            self.assertEqual(h_get.sent[-1][1], 200)

            h_post = self._make_handler("/api/index?route=push_subscribe", b'{"subscription":{}}')
            h_post.do_POST()
            self.assertEqual(h_post.sent[-1][1], 200)

        self.assertEqual(proxied[0][:2], ("GET", "https://backend.example/api/realty-photos?id=yandex%3A1"))
        self.assertEqual(proxied[1], ("POST", "https://backend.example/api/push/subscribe", "application/json"))


class BackendReliabilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_images_only_import_preserves_manual_flag(self):
        cache = os.path.join(self.tmp.name, "cache")
        os.makedirs(cache)
        with patch.object(server, "CACHE_DIR", cache), patch.object(server, "MEM", {}):
            row = {
                "id": "yandex:1",
                "url": "https://realty.yandex.ru/offer/1/",
                "title": "1-комн. квартира, 38 м²",
                "price": 8_000_000,
                "city": "Москва",
            }
            server.api_realty_import({"source": "yandex", "items": [row], "reset": True})
            server.api_realty_import({"source": "yandex", "images": {"yandex:1": "https://img.example/1.jpg"}})
            with open(os.path.join(cache, "realty_yandex.json"), encoding="utf-8") as file:
                saved = json.load(file)
            self.assertTrue(saved["meta"].get("manual"))

    def test_concurrent_clicks_no_lost_updates(self):
        clicks_file = os.path.join(self.tmp.name, "clicks.json")
        errors = []

        def worker():
            try:
                for _ in range(10):
                    server.api_click({"key": "cards:a", "title": "A"})
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        with patch.object(server, "CLICKS_FILE", clicks_file):
            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            self.assertEqual(server.api_clicks()["total"], 50)


class BotRbacTest(unittest.TestCase):
    def test_cards_only_editor_cannot_edit_url(self):
        instance = bot.Bot("token", "http://api", "secret")
        calls = []
        instance.send = lambda chat_id, text, keyboard=None: calls.append((text, keyboard))
        instance.editors = lambda: {"10": ["cards"]}
        instance.products = lambda: [{"id": "c1", "bank": "B", "name": "N"}]
        posted = []
        instance.post = lambda path, payload: posted.append((path, payload)) or {"ok": True}

        instance.admin_edit(10, "c1")
        callbacks = [btn["callback_data"] for row in calls[-1][1]["inline_keyboard"] for btn in row]
        self.assertNotIn("adm:field:c1:url", callbacks)

        instance.admin_edit_field(10, "c1", "url")
        self.assertNotIn(10, instance.pending)
        self.assertIn("Нет доступа", calls[-1][0])

        instance.edit_step(10, {"mode": "edit", "id": "c1", "field": "url"}, "https://evil.example")
        self.assertEqual(posted, [])


if __name__ == "__main__":
    unittest.main()
