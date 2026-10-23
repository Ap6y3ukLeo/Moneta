import os
import sys
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


if __name__ == "__main__":
    unittest.main()
