import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class WarmTest(unittest.TestCase):
    def test_warm_continues_after_failure(self):
        calls = []

        def boom():
            raise RuntimeError("источник упал")

        with patch.object(server, "api_market", side_effect=boom), \
                patch.object(server, "api_deposits", side_effect=lambda: calls.append("deposits")), \
                patch.object(server, "api_realty", side_effect=lambda: calls.append("realty")):
            server._warm_once()

        self.assertEqual(calls, ["deposits", "realty"])


if __name__ == "__main__":
    unittest.main()
