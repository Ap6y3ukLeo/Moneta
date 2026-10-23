import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class HistoryTest(unittest.TestCase):
    def test_crypto_history(self):
        points = [{"t": "2026-10-01", "c": 100.0}, {"t": "2026-10-02", "c": 101.0}]
        with patch.object(server, "_bybit_history", return_value=points):
            result = server.api_history({"kind": "crypto", "id": "bitcoin", "range": "1m"})
        self.assertEqual(result["points"], points)
        self.assertEqual(result["unit"], "USD")
        self.assertEqual(result["source"], "Bybit")

    def test_metal_history(self):
        points = [{"t": "2026-10-01", "c": 100.0}, {"t": "2026-10-02", "c": 101.0}]
        with patch.object(server, "_metal_history", return_value=points):
            result = server.api_history({"kind": "metal", "id": "XAU", "range": "1y"})
        self.assertEqual(result["points"], points)
        self.assertEqual(result["unit"], "RUB/g")

    def test_fx_history(self):
        points = [{"t": "2026-10-01", "c": 81.0}, {"t": "2026-10-02", "c": 81.1}]
        with patch.object(server, "_fx_history_points", return_value=points):
            result = server.api_history({"kind": "fx", "id": "USD", "range": "1y"})
        self.assertEqual(result["points"], points)
        self.assertEqual(result["unit"], "RUB")

    def test_fx_history_only_major(self):
        with self.assertRaises(ValueError):
            server.api_history({"kind": "fx", "id": "CHF", "range": "1m"})


if __name__ == "__main__":
    unittest.main()
