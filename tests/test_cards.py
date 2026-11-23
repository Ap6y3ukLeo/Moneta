import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

TYPES = {"debit", "credit", "business"}
REQUIRED = ("id", "type", "bank", "name", "benefit", "payout", "terms", "perks", "url")


class CardsTest(unittest.TestCase):
    def test_cards_dataset(self):
        data = server.api_cards()
        items = data["items"]
        self.assertGreaterEqual(len(items), 15)

        ids = [item["id"] for item in items]
        self.assertEqual(len(ids), len(set(ids)), "id должны быть уникальны")

        for item in items:
            for field in REQUIRED:
                self.assertIn(field, item, f"{item.get('id')}: нет поля {field}")
            self.assertIn(item["type"], TYPES)
            self.assertTrue(item["terms"], f"{item['id']}: нет условий")
            self.assertGreater(item["payout"], 0, f"{item['id']}: выплата должна быть больше нуля")
            self.assertTrue(item["url"].startswith("https://"))

        for kind in TYPES:
            self.assertTrue(any(item["type"] == kind for item in items), f"нет продуктов типа {kind}")

    def test_every_type_has_banks(self):
        items = server.api_cards()["items"]
        for kind in TYPES:
            banks = {item["bank"] for item in items if item["type"] == kind}
            self.assertGreaterEqual(len(banks), 4, f"{kind}: мало банков")


if __name__ == "__main__":
    unittest.main()
