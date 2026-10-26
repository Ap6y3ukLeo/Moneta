import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class FxLiveTest(unittest.TestCase):
    def test_moex_parser(self):
        payload = {
            "securities": {
                "columns": ["SECID", "SHORTNAME", "PREVPRICE", "FACEVALUE"],
                "data": [
                    ["USD000UTSTOM", "USDRUB_TOM", 80.0, 1],
                    ["USD000UTSTOM", "USDRUB_TOM", None, 1],
                    ["EUR_RUB__TOM", "EURRUB_TOM", 95.0, 1],
                    ["KZTRUB_TOM", "KZTRUB_TOM", 18.0, 100],
                ],
            },
            "marketdata": {
                "columns": ["SECID", "LAST", "MARKETPRICE", "WAPRICE", "SYSTIME"],
                "data": [
                    ["EUR_RUB__TOM", None, 90.0, None, "2026-10-26 10:00:00"],
                    ["USD000UTSTOM", 81.0, 80.5, 80.9, "2026-10-26 10:05:00"],
                    ["KZTRUB_TOM", 18.4, None, None, "2026-10-26 10:06:00"],
                ],
            },
        }
        rates = server._parse_moex_rates(payload)

        self.assertEqual(rates["USD"]["value"], 81.0)
        self.assertEqual(rates["USD"]["prev"], 80.0)
        self.assertTrue(rates["USD"]["traded"])
        self.assertEqual(rates["EUR"]["value"], 90.0)
        self.assertFalse(rates["EUR"]["traded"])
        self.assertAlmostEqual(rates["KZT"]["value"], 0.184)


if __name__ == "__main__":
    unittest.main()
