import json
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

    def test_page_url(self):
        self.assertEqual(server._page_url("https://example.test/list", 2), "https://example.test/list?p=2")
        self.assertEqual(server._page_url("https://example.test/list?region=2", 2), "https://example.test/list?region=2&p=2")

    def test_yandex_parse(self):
        state = {"search": {"offers": {"entities": [{
            "offerId": "42",
            "offerCategory": "APARTMENT",
            "offerType": "SELL",
            "price": {"value": 5_000_000},
            "area": {"value": 50},
            "roomsTotal": 2,
            "flatType": "SECONDARY",
            "minicardImages": ["//img.test/1"],
            "location": {
                "address": "Казань, Парковая улица, 12",
                "structuredAddress": {"component": [{"regionType": "CITY", "value": "Казань"}]},
                "metro": {"name": "Северный Вокзал"},
            },
        }]}}}
        html = "<script>window.INITIAL_STATE = " + json.dumps(state, ensure_ascii=False) + "</script>"
        rows = server._parse_yandex(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["city"], "Казань")
        self.assertEqual(rows[0]["priceM2"], 100_000)
        self.assertEqual(rows[0]["img"], "https://img.test/1")
        self.assertEqual(rows[0]["url"], "https://realty.yandex.ru/offer/42/")


if __name__ == "__main__":
    unittest.main()
