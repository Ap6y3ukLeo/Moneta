import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

ALFA_TEXT = """Вклады
Альфа-Вклад
Высокая ставка на сумму до 1 000 000 ₽
До 14,5%
с капитализацией
От 500 000 ₽
минимальная сумма
3 месяца
срок
Подробнее
Открыть
Альфа‑Вклад Ключевой
Доход и ставка зависит от ставки ЦБ РФ
До 15,07% годовых
с капитализацией
От 10 000 ₽
минимальная сумма
От 3 месяцев до 3 лет
срок
Подробнее
Открыть
Социальный вклад
Специальные условия
24,74% годовых
ставка по вкладу
1 копейка
минимальная сумма
12 месяцев
срок
"""

OTP_TEXT = """Вклады и счета
Откройте вклад от 1 000 рублей
ОТКРЫТЬ ВКЛАД
Вклад «Горизонт»
Легко открыть — от 1 000 ₽ на удобный срок
До 13,6%
Ставка по вкладу
От 3 месяцев
Срок оформления
От 1 000 ₽
Сумма оформления
СМОТРЕТЬ УСЛОВИЯ
Вклад «Притяжение»
Выплата процентов каждый день
До 12,1%
Ставка по вкладу
От 6 месяцев
Срок оформления
От 20 000 ₽
Сумма оформления
"""


class DepositBanksTest(unittest.TestCase):
    def test_alfa_cards(self):
        rows = server._parse_alfa_deposits(ALFA_TEXT)
        by_name = {row[0]: row for row in rows}

        self.assertEqual(set(by_name), {"Альфа-Вклад", "Альфа‑Вклад Ключевой", "Социальный вклад"})
        self.assertEqual(by_name["Альфа-Вклад"][1], 14.5)
        self.assertEqual(by_name["Альфа-Вклад"][2], 500000)
        self.assertEqual(by_name["Альфа-Вклад"][3], "3 мес.")
        self.assertEqual(by_name["Альфа‑Вклад Ключевой"][1], 15.07)
        self.assertEqual(by_name["Социальный вклад"][1], 24.74)
        self.assertIsNone(by_name["Социальный вклад"][2])

    def test_otp_cards(self):
        rows = server._parse_otp_deposits(OTP_TEXT)

        self.assertEqual([row[0] for row in rows], ["Вклад «Горизонт»", "Вклад «Притяжение»"])
        self.assertEqual(rows[0][1], 13.6)
        self.assertEqual(rows[0][2], 1000)
        self.assertEqual(rows[0][3], "От 3 мес.")
        self.assertEqual(rows[1][1], 12.1)


if __name__ == "__main__":
    unittest.main()
