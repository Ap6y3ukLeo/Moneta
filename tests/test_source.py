import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class SourceTest(unittest.TestCase):
    def test_vercel_uses_bundled_snapshot(self):
        def boom():
            raise AssertionError("live builder must not run")

        with patch.dict(os.environ, {"VERCEL": "1"}, clear=True), patch.object(server, "MEM", {}):
            value, meta = server.source("crypto", 0, boom)

        self.assertTrue(value.get("items"))
        self.assertTrue(meta.get("stale"))

    def test_force_skips_bundled_snapshot(self):
        def builder():
            return {"items": [{"id": "fresh"}]}

        with tempfile.TemporaryDirectory() as cache, \
                patch.dict(os.environ, {"VERCEL": "1"}, clear=True), \
                patch.object(server, "MEM", {}), \
                patch.object(server, "CACHE_DIR", cache):
            value, meta = server.source("crypto", 3600, builder, force=True)

        self.assertEqual(value["items"][0]["id"], "fresh")
        self.assertFalse(meta["stale"])


    def test_stale_cache_returns_immediately_and_refreshes_in_background(self):
        done = threading.Event()

        def builder():
            done.set()
            return {"items": [{"id": "fresh"}]}

        with tempfile.TemporaryDirectory() as cache:
            path = os.path.join(cache, "crypto-stale-test.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"value": {"items": [{"id": "old"}]},
                           "meta": {"ok": True, "updated": "2020-01-01T00:00:00+03:00"}}, f)
            os.utime(path, (0, 0))
            with patch.dict(os.environ, {}, clear=True), \
                    patch.object(server, "MEM", {}), \
                    patch.object(server, "REFRESHING", set()), \
                    patch.object(server, "CACHE_DIR", cache):
                value, meta = server.source("crypto-stale-test", 3600, builder)
                self.assertEqual(value["items"][0]["id"], "old")
                self.assertTrue(meta["stale"])
                self.assertTrue(done.wait(5))
                for _ in range(50):
                    if server.MEM.get("crypto-stale-test", {}).get("meta", {}).get("stale") is False:
                        break
                    time.sleep(0.05)
                for _ in range(50):  # ждём, пока фоновый поток допишет файл кэша
                    if not server.REFRESHING:
                        break
                    time.sleep(0.05)
                self.assertEqual(server.MEM["crypto-stale-test"]["value"]["items"][0]["id"], "fresh")


if __name__ == "__main__":
    unittest.main()
