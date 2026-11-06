import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class FxMergeTest(unittest.TestCase):
    def test_newest_source_wins(self):
        old = {"USD": {"value": 80.0, "updated": "2026-11-06T12:00:00+03:00", "source": "open.er-api"}}
        new = {"USD": {"value": 82.0, "updated": "2026-11-06T12:05:00+03:00", "source": "currency-api"}}
        merged = server._merge_rates(old, new)
        self.assertEqual(merged["USD"]["value"], 82.0)
        self.assertEqual(merged["USD"]["source"], "currency-api")

    def test_fresh_moex_beats_aggregator(self):
        moex = {"USD": {"value": 82.4, "updated": "2026-11-06T12:00:00+03:00", "source": "MOEX"}}
        other = {"USD": {"value": 83.5, "updated": "2026-11-06T12:10:00+03:00", "source": "Coinbase"}}
        merged = server._merge_rates(moex, other)
        self.assertEqual(merged["USD"]["source"], "MOEX")

    def test_stale_moex_is_replaced(self):
        moex = {"USD": {"value": 82.4, "updated": "2026-11-06T12:00:00+03:00", "source": "MOEX"}}
        other = {"USD": {"value": 83.5, "updated": "2026-11-06T12:30:00+03:00", "source": "open.er-api"}}
        merged = server._merge_rates(moex, other)
        self.assertEqual(merged["USD"]["source"], "open.er-api")

    def test_codes_are_kept_from_all_sources(self):
        first = {"USD": {"value": 82.0, "updated": "2026-11-06T12:00:00+03:00"}}
        second = {"AED": {"value": 22.3, "updated": "2026-11-06T12:00:00+03:00"}}
        merged = server._merge_rates(first, second)
        self.assertEqual(set(merged), {"USD", "AED"})

    def test_missing_timestamp_does_not_win(self):
        broken = {"USD": {"value": 80.0, "updated": None, "source": "open.er-api"}}
        good = {"USD": {"value": 82.0, "updated": "2026-11-06T12:00:00+03:00", "source": "currency-api"}}
        merged = server._merge_rates(broken, good)
        self.assertEqual(merged["USD"]["value"], 82.0)


if __name__ == "__main__":
    unittest.main()
