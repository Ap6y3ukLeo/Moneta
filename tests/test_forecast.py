import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

MARKET = {
    "crypto": {
        "items": [{
            "id": "bitcoin", "symbol": "BTC", "name": "Bitcoin",
            "price": 100.0, "change24h": 2.5, "spark": [80 + i for i in range(20)],
        }],
    },
    "metals": {
        "items": [{
            "id": "XAU", "code": "XAU", "name": "Золото",
            "price": 200.0, "change24h": -1.0, "spark": [190 + i for i in range(20)],
        }],
    },
    "fx": {"items": []},
}


class ForecastTest(unittest.TestCase):
    def test_crypto_forecast_parses_points(self):
        answer = json.dumps({
            "direction": "up", "confidence": 0.7, "bandPct": 4,
            "summary": "Рост", "points": [101, 102, 103, 104, 105, 106, 107],
            "support": 95, "resistance": 110,
        })
        with patch.object(server, "api_market", return_value=MARKET), patch.object(
            server, "_yandex_completion",
            return_value={"answer": answer, "model": "test", "usage": {}},
        ):
            result = server.api_forecast({"kind": "crypto", "id": "bitcoin"})
        self.assertEqual(len(result["points"]), 7)
        self.assertFalse(result["fallback"])
        self.assertEqual(result["direction"], "up")
        self.assertEqual(result["asset"]["unit"], "USD")
        self.assertAlmostEqual(result["changePct"], 7.0, places=1)

    def test_metal_forecast_horizon(self):
        answer = json.dumps({"points": [201] * 14, "summary": "Боковик"})
        with patch.object(server, "api_market", return_value=MARKET), patch.object(
            server, "_yandex_completion",
            return_value={"answer": answer, "model": "test", "usage": {}},
        ):
            result = server.api_forecast({"kind": "metal", "id": "XAU"})
        self.assertEqual(result["horizonDays"], 14)
        self.assertEqual(len(result["points"]), 14)
        self.assertEqual(result["asset"]["unit"], "RUB/g")

    def test_invalid_answer_falls_back(self):
        with patch.object(server, "api_market", return_value=MARKET), patch.object(
            server, "_yandex_completion",
            return_value={"answer": "не JSON", "model": "test", "usage": {}},
        ):
            result = server.api_forecast({"kind": "crypto", "id": "bitcoin"})
        self.assertTrue(result["fallback"])
        self.assertEqual(len(result["points"]), 7)

    def test_unknown_asset(self):
        with patch.object(server, "api_market", return_value=MARKET):
            with self.assertRaises(ValueError):
                server.api_forecast({"kind": "crypto", "id": "nope"})


if __name__ == "__main__":
    unittest.main()
