import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

BASE = {"items": [{
    "id": "base", "type": "debit", "bank": "Банк", "name": "Базовая",
    "terms": [{"label": "Обслуживание", "value": "0 ₽"}], "perks": [],
    "url": "https://bank.example", "payout": 100,
}]}

NEW = {
    "bank": "Тест-Банк",
    "name": "Тестовая",
    "type": "credit",
    "payout": 4500,
    "benefit": "100 дней без процентов",
    "terms": [{"label": "Льготный период", "value": "100 дней"}, {"label": "Обслуживание", "value": "0 ₽"}],
    "perks": ["Кэшбэк"],
    "url": "https://test.example/card",
}


class CustomCardsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cards_file = os.path.join(self.tmp.name, "cards.json")
        with open(self.cards_file, "w", encoding="utf-8") as file:
            json.dump(BASE, file, ensure_ascii=False)
        self.patches = [
            patch.object(server, "CARDS_FILE", self.cards_file),
            patch.object(server, "CUSTOM_FILE", os.path.join(self.tmp.name, "custom_cards.json")),
            patch.object(server, "LINKS_FILE", os.path.join(self.tmp.name, "links.json")),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_created_card_is_served(self):
        created = server.api_card_create(NEW)
        items = server.api_cards()["items"]
        self.assertEqual([item["id"] for item in items][0], "base")
        self.assertEqual(len(items), 2)
        card = items[-1]
        self.assertEqual(card["id"], created["id"])
        self.assertEqual(card["name"], "Тестовая")
        self.assertEqual(card["tint"], server.CARD_TINTS["credit"])
        self.assertEqual(card["terms"][0]["label"], "Льготный период")
        self.assertEqual(card["perks"], ["Кэшбэк"])

    def test_benefit_falls_back_to_first_term(self):
        payload = dict(NEW, benefit="")
        created = server.api_card_create(payload)
        card = next(item for item in server.api_cards()["items"] if item["id"] == created["id"])
        self.assertEqual(card["benefit"], "100 дней")

    def test_link_override_applies_to_custom_card(self):
        created = server.api_card_create(NEW)
        server.api_link_set({"id": created["id"], "url": "https://partner.example"})
        card = next(item for item in server.api_cards()["items"] if item["id"] == created["id"])
        self.assertEqual(card["url"], "https://partner.example")

    def test_validation(self):
        for broken in (
            dict(NEW, type="mortgage"),
            dict(NEW, url="http://test.example"),
            dict(NEW, payout=0),
            dict(NEW, payout="много"),
            dict(NEW, bank="  "),
            dict(NEW, terms=[]),
            dict(NEW, terms=[{"label": "", "value": "0 ₽"}]),
        ):
            with self.assertRaises(ValueError):
                server.api_card_create(broken)


if __name__ == "__main__":
    unittest.main()
