import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class WorldStocksTest(unittest.TestCase):
    def test_number_parsing(self):
        self.assertEqual(server._money_num("$178.67"), 178.67)
        self.assertEqual(server._pct_num("-4.27%"), -4.27)
        self.assertIsNone(server._money_num("N/A"))
        self.assertIsNone(server._pct_num(None))

    def test_stocks_survive_moex_failure(self):
        world = [{"id": "NVDA", "ticker": "NVDA", "price": 178.67, "currency": "USD"}]
        with patch.object(server, "_moex_stocks", side_effect=RuntimeError("SSL timeout")), \
                patch.object(server, "_cached_moex_items", return_value=[]), \
                patch.object(server, "_world_stocks", return_value=world):
            data = server.build_stocks()
        self.assertEqual([item["id"] for item in data["items"]], ["NVDA"])
        self.assertEqual(data["provider"], "MOEX + NASDAQ")
        self.assertTrue(data["errors"])

    def test_moex_failure_falls_back_to_cache(self):
        cached = [{"id": "SBER", "ticker": "SBER", "price": 300.0, "stale": True}]
        world = [{"id": "NVDA", "ticker": "NVDA", "price": 178.67, "currency": "USD"}]
        with patch.object(server, "_moex_stocks", side_effect=RuntimeError("SSL")), \
                patch.object(server, "_cached_moex_items", return_value=cached), \
                patch.object(server, "_world_stocks", return_value=world):
            data = server.build_stocks()
        self.assertEqual([item["id"] for item in data["items"]], ["SBER", "NVDA"])

    def test_stocks_survive_nasdaq_failure(self):
        moex = [{"id": "SBER", "ticker": "SBER", "price": 300.0, "currency": "RUB"}]
        with patch.object(server, "_moex_stocks", return_value=moex), \
                patch.object(server, "_world_stocks", side_effect=RuntimeError("429")):
            data = server.build_stocks()
        self.assertEqual([item["id"] for item in data["items"]], ["SBER"])

    def test_both_failing_raises(self):
        with patch.object(server, "_moex_stocks", side_effect=RuntimeError("ssl")), \
                patch.object(server, "_cached_moex_items", return_value=[]), \
                patch.object(server, "_world_stocks", side_effect=RuntimeError("429")):
            with self.assertRaises(RuntimeError):
                server.build_stocks()


if __name__ == "__main__":
    unittest.main()
