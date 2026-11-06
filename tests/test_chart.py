import io
import os
import sys
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

HISTORY = {
    "kind": "crypto", "id": "bitcoin", "name": "Bitcoin", "symbol": "BTC",
    "unit": "USD", "range": "7d", "source": "тест",
    "points": [{"t": f"2026-11-0{i + 1}T12:00:00+03:00", "c": 100 + i * 5} for i in range(6)],
}


class ChartTest(unittest.TestCase):
    def test_returns_png_of_expected_size(self):
        with patch.object(server, "api_history", return_value=HISTORY):
            body = server.api_chart({"kind": "crypto", "id": "bitcoin", "range": "7d"})
        self.assertTrue(body.startswith(b"\x89PNG"))
        image = Image.open(io.BytesIO(body))
        self.assertEqual(image.size, (server.CHART_WIDTH, server.CHART_HEIGHT))

    def test_requires_at_least_two_points(self):
        with patch.object(server, "api_history", return_value=dict(HISTORY, points=HISTORY["points"][:1])):
            with self.assertRaises(RuntimeError):
                server.api_chart({"kind": "crypto", "id": "bitcoin", "range": "7d"})

    def test_chart_ends_with_current_price(self):
        with patch.object(server, "_current_price", return_value=200.0):
            points = server._chart_points(dict(HISTORY))
        self.assertEqual(points[-1]["c"], 200.0)
        self.assertEqual(len(points), len(HISTORY["points"]) + 1)

    def test_no_extra_point_when_price_matches(self):
        last = HISTORY["points"][-1]["c"]
        with patch.object(server, "_current_price", return_value=last):
            points = server._chart_points(dict(HISTORY))
        self.assertEqual(len(points), len(HISTORY["points"]))


if __name__ == "__main__":
    unittest.main()
