import os
import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()
