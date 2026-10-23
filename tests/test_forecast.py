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
            "volume": 123456.0,
        }],
    },
    "metals": {
        "items": [{
            "id": "XAU", "code": "XAU", "name": "Золото",
            "price": 200.0, "change24h": -1.0, "spark": [190 + i for i in range(20)],
        }],
    },
    "fx": {
        "items": [{
            "code": "USD", "name": "Доллар США", "value": 81.0,
            "prev": 80.0, "change24h": 1.25,
        }],
    },
    "keyRate": {"value": 16.0},
}


class ForecastTest(unittest.TestCase):
    def test_crypto_forecast_uses_ensemble_and_commentary(self):
        with patch.object(server, "api_market", return_value=MARKET), patch.object(
            server, "_yandex_completion",
            return_value={"answer": "Комментарий AI", "model": "test", "usage": {}},
        ):
            result = server.api_forecast({"kind": "crypto", "id": "bitcoin"})
        self.assertEqual(len(result["points"]), 7)
        self.assertEqual(result["model"], "ensemble")
        self.assertEqual(result["commentary"], "Комментарий AI")
        self.assertIsNone(result["aiError"])
        self.assertGreater(result["backtest"]["samples"], 0)
        self.assertGreaterEqual(result["confidence"], 0.2)
        self.assertLessEqual(result["confidence"], 0.8)
        self.assertGreaterEqual(result["bandPct"], 1)
        self.assertEqual(result["asset"]["unit"], "USD")

    def test_forecast_survives_ai_error(self):
        with patch.object(server, "api_market", return_value=MARKET), patch.object(
            server, "_yandex_completion", side_effect=RuntimeError("ключ не задан"),
        ):
            result = server.api_forecast({"kind": "crypto", "id": "bitcoin"})
        self.assertEqual(len(result["points"]), 7)
        self.assertIsNone(result["commentary"])
        self.assertIn("ключ", result["aiError"])

    def test_metal_forecast_horizon(self):
        with patch.object(server, "api_market", return_value=MARKET), patch.object(
            server, "_yandex_completion",
            return_value={"answer": "Комментарий", "model": "test", "usage": {}},
        ):
            result = server.api_forecast({"kind": "metal", "id": "XAU"})
        self.assertEqual(result["horizonDays"], 14)
        self.assertEqual(len(result["points"]), 14)
        self.assertEqual(result["asset"]["unit"], "RUB/g")

    def test_fx_forecast_uses_cbr_history(self):
        with patch.object(server, "api_market", return_value=MARKET), patch.object(
            server, "_fx_history", return_value=[80 + i * 0.1 for i in range(20)]
        ), patch.object(
            server, "_yandex_completion",
            return_value={"answer": "Комментарий", "model": "test", "usage": {}},
        ):
            result = server.api_forecast({"kind": "fx", "id": "USD"})
        self.assertEqual(result["horizonDays"], 14)
        self.assertEqual(result["asset"]["unit"], "RUB")
        self.assertEqual(result["asset"]["price"], 81.0)
        self.assertEqual(len(result["history"]), 20)

    def test_unknown_asset(self):
        with patch.object(server, "api_market", return_value=MARKET):
            with self.assertRaises(ValueError):
                server.api_forecast({"kind": "crypto", "id": "nope"})


if __name__ == "__main__":
    unittest.main()
