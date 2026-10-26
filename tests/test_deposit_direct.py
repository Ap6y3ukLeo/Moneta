import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class DirectDepositsTest(unittest.TestCase):
    def test_term_normalization(self):
        self.assertEqual(server._direct_term("4 лет"), "4 г.")
        self.assertIsNone(server._direct_term_days("2-36 мес."))
        self.assertEqual(server._direct_term_days("3 мес."), 90)

    def test_bank_aliases(self):
        self.assertEqual(server._is_direct_bank("Тинькофф Банк"), "т")
        self.assertEqual(server._is_direct_bank("Банк ДОМ.РФ"), "домрф")

    def test_tbank_html(self):
        html = (
            "<p>Вклад со&nbsp;ставкой до&nbsp;12,3% годовых</p>"
            "<p>От&nbsp;1&nbsp;до&nbsp;24&nbsp;месяцев, от&nbsp;50&nbsp;000&nbsp;₽</p>"
        )
        rows = server._parse_tbank_deposits(html)
        self.assertEqual(rows[0][:3], ("Вклад", 12.3, 50000.0))


if __name__ == "__main__":
    unittest.main()
