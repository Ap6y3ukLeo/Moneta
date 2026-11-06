import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def _boom(_html):
    raise RuntimeError("банк заблокировал сервер")


class DepositFallbackTest(unittest.TestCase):
    def test_blocked_bank_keeps_cached_rows(self):
        bank = ("vtb", "ВТБ", "https://example.com", _boom)
        cached = {"vtb": [["Вклад", 15.0, 10000, "1 год", "https://example.com/v"]]}
        with patch.object(server, "DIRECT_BANKS", [bank]), \
                patch.object(server, "BROWSER_BANK_KEYS", set()), \
                patch.object(server, "http_text", side_effect=_boom), \
                patch.object(server, "_load_bank_cache", return_value=cached), \
                patch.object(server, "_save_bank_cache"):
            items = server.build_direct_banks()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["bank"], "ВТБ")
        self.assertEqual(items[0]["rate"], 15.0)
        self.assertEqual(items[0]["termText"], "1 год")

    def test_blocked_bank_without_cache_is_skipped(self):
        bank = ("vtb", "ВТБ", "https://example.com", _boom)
        with patch.object(server, "DIRECT_BANKS", [bank]), \
                patch.object(server, "BROWSER_BANK_KEYS", set()), \
                patch.object(server, "http_text", side_effect=_boom), \
                patch.object(server, "_load_bank_cache", return_value={}), \
                patch.object(server, "_save_bank_cache"):
            with self.assertRaises(RuntimeError):
                server.build_direct_banks()


if __name__ == "__main__":
    unittest.main()
