import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class AvitoCityTest(unittest.TestCase):
    def test_region_forms(self):
        self.assertEqual(server._avito_city([], "Оренбургская обл., Оренбург", ""), "Оренбург")
        self.assertEqual(server._avito_city([], "Республика Марий Эл, Йошкар-Ола", ""), "Йошкар-Ола")
        self.assertEqual(server._avito_city([], "Хакасия, Абакан", ""), "Абакан")

    def test_slug_fallback(self):
        self.assertEqual(server._avito_city([], "", "https://www.avito.ru/groznyy/kvartiry/1"), "Грозный")
        self.assertEqual(server._avito_city([], "", "https://www.avito.ru/moskovskaya_oblast_krasnogorsk/kvartiry/1"), "Красногорск")

    def test_city_marker(self):
        self.assertEqual(server._avito_city([], "г.о. Сочи, ул. Ленина", ""), "Сочи")


if __name__ == "__main__":
    unittest.main()
