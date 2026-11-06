import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class BotApiTest(unittest.TestCase):
    def test_empty_category_lists_categories(self):
        data = server.api_bot({})
        keys = [item["key"] for item in data["categories"]]
        self.assertEqual(keys, ["crypto", "stocks", "metals", "fx", "deposits", "realty"])

    def test_unknown_category_rejected(self):
        with self.assertRaises(ValueError):
            server.api_bot({"category": "weather"})

    def test_crypto_text_and_items(self):
        payload = ({"items": [
            {"symbol": "BTC", "name": "Bitcoin", "price": 75695.4, "change24h": -5.96},
            {"symbol": "ETH", "name": "Ethereum", "price": 2500, "change24h": 1.5},
        ]}, {"ok": True, "updated": "2026-11-06T11:58:32+03:00"})
        with patch.object(server, "source", return_value=payload):
            data = server.api_bot({"category": "crypto", "limit": "1"})
        self.assertEqual(len(data["items"]), 1)
        self.assertIn("BTC — $75 695,40 (-5,96%)", data["text"])
        self.assertNotIn("ETH", data["text"])
        self.assertIn("Обновлено: 06.11.2026 11:58", data["text"])

    def test_deposit_line(self):
        with patch.object(server, "api_deposits", return_value={"items": [
            {"bank": "Газпромбанк", "name": "Вклад", "rate": 16.0, "termText": "4 мес.", "min": 100000},
        ], "meta": {}}):
            data = server.api_bot({"category": "deposits"})
        self.assertIn("Газпромбанк · Вклад · 16,00% · 4 мес. · от 100 000 ₽", data["text"])

    def test_limit_must_be_a_number(self):
        with self.assertRaises(ValueError):
            server.api_bot({"category": "crypto", "limit": "abc"})


if __name__ == "__main__":
    unittest.main()
