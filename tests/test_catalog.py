import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class CatalogTest(unittest.TestCase):
    def test_coins_are_unique(self):
        ids = [coin[0] for coin in server.COINS]
        symbols = [coin[2] for coin in server.COINS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(symbols), len(set(symbols)))

    def test_every_fx_code_has_history_id(self):
        missing = set(server.FX_CODES) - set(server.FX_HISTORY_IDS)
        self.assertEqual(missing, set())

    def test_history_kind_guess(self):
        self.assertEqual(server._guess_history_kind("btc"), "crypto")
        self.assertEqual(server._guess_history_kind("TRY"), "fx")
        self.assertEqual(server._guess_history_kind("XAU"), "metal")
        self.assertEqual(server._guess_history_kind("SBER"), "stock")


if __name__ == "__main__":
    unittest.main()
