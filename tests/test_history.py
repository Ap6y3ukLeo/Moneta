import os
import sys
import unittest
from datetime import datetime, timedelta
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
        self.assertEqual(result["source"], "Bybit / CoinGecko")

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

    def test_snapshot_fallback(self):
        points = [{"t": "2026-10-01", "c": 100.0}, {"t": "2026-10-02", "c": 101.0}]
        with patch.object(server, "_crypto_history", side_effect=RuntimeError("network")), patch.object(
            server, "_history_snapshot", return_value=points
        ):
            result = server.api_history({"kind": "crypto", "id": "bitcoin", "range": "1m"})
        self.assertEqual(result["points"], points)
        self.assertEqual(result["source"], "снимок")

    def test_vercel_prefers_snapshot(self):
        points = [{"t": "2026-10-01", "c": 100.0}, {"t": "2026-10-02", "c": 101.0}]
        with patch.dict(os.environ, {"VERCEL": "1"}, clear=True), patch.object(
            server, "_history_snapshot", return_value=points
        ), patch.object(server, "_crypto_history") as live:
            result = server.api_history({"kind": "crypto", "id": "bitcoin", "range": "1m"})
        live.assert_not_called()
        self.assertEqual(result["source"], "снимок")

    def test_slice_history_by_date(self):
        today = datetime.now(server.MSK).date()
        points = [
            {"t": (today - timedelta(days=index)).isoformat(), "c": index}
            for index in range(60)
        ]
        sliced = server._slice_history(points, "1m")
        self.assertGreaterEqual(len(sliced), 30)
        self.assertLessEqual(len(sliced), 32)


if __name__ == "__main__":
    unittest.main()
