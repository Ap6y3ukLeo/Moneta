import io
import os
import sys
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class CardTest(unittest.TestCase):
    def test_crypto_rows(self):
        items = [{"symbol": "BTC", "name": "Bitcoin", "price": 76254.1, "change24h": -2.01}]
        with patch.object(server, "_bot_crypto", return_value=(items, [], {})):
            rows, _ = server._card_rows("crypto", 5)
        self.assertEqual(rows[0], ("BTC", "Bitcoin", "$76 254,10", "-2,01%", "#e8564b"))

    def test_deposit_rows(self):
        payload = {"items": [{"bank": "Газпромбанк", "name": "Ключевой момент", "rate": 16.0,
                              "termText": "4 мес.", "min": 100000}], "meta": {}}
        with patch.object(server, "api_deposits", return_value=payload):
            rows, _ = server._card_rows("deposits", 5)
        self.assertEqual(rows[0], ("Газпромбанк", "Ключевой момент · 4 мес.", "16,00%", "от 100 000 ₽", "#7c899b"))

    def test_card_png_height_follows_rows(self):
        rows = [("BTC", "Bitcoin", "$76 121,80", "-2,18%", "#e8564b")] * 3
        with patch.object(server, "_card_rows", return_value=(rows, {"updated": "2026-11-06T11:58:32+03:00"})):
            body = server.api_card({"category": "crypto"})
        self.assertTrue(body.startswith(b"\x89PNG"))
        image = Image.open(io.BytesIO(body))
        self.assertEqual(image.width, server.CARD_WIDTH)
        self.assertEqual(image.height, 150 + 3 * server.CARD_ROW_HEIGHT + 70)

    def test_unknown_category_rejected(self):
        with self.assertRaises(ValueError):
            server.api_card({"category": "weather"})


if __name__ == "__main__":
    unittest.main()
