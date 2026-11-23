import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

BASE = {"items": [{
    "id": "debit-base", "type": "debit", "bank": "Банк", "name": "Базовая",
    "benefit": "до 5% кэшбэка", "terms": [{"label": "Обслуживание", "value": "0 ₽"}],
    "perks": [], "url": "https://bank.example", "payout": 100,
}]}


class CardEditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cards_file = os.path.join(self.tmp.name, "cards.json")
        with open(self.cards_file, "w", encoding="utf-8") as file:
            json.dump(BASE, file, ensure_ascii=False)
        self.patches = [
            patch.object(server, "CARDS_FILE", self.cards_file),
            patch.object(server, "CUSTOM_FILE", os.path.join(self.tmp.name, "custom_cards.json")),
            patch.object(server, "EDITS_FILE", os.path.join(self.tmp.name, "card_edits.json")),
            patch.object(server, "LINKS_FILE", os.path.join(self.tmp.name, "links.json")),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def card(self, item_id="debit-base"):
        return next(item for item in server.api_cards()["items"] if item["id"] == item_id)

    def test_edit_changes_fields(self):
        server.api_card_update({"id": "debit-base", "fields": {
            "bank": "Новый банк", "payout": 3000,
            "terms": [{"label": "Кэшбэк", "value": "до 30%"}],
            "perks": ["Снятие"],
        }})
        card = self.card()
        self.assertEqual(card["bank"], "Новый банк")
        self.assertEqual(card["payout"], 3000)
        self.assertEqual(card["terms"], [{"label": "Кэшбэк", "value": "до 30%"}])
        self.assertEqual(card["perks"], ["Снятие"])
        self.assertEqual(card["name"], "Базовая")

    def test_type_change_updates_tint(self):
        server.api_card_update({"id": "debit-base", "fields": {"type": "business"}})
        card = self.card()
        self.assertEqual(card["type"], "business")
        self.assertEqual(card["tint"], server.CARD_TINTS["business"])

    def test_edits_stack_and_keep_previous(self):
        server.api_card_update({"id": "debit-base", "fields": {"payout": 500}})
        server.api_card_update({"id": "debit-base", "fields": {"bank": "Второй"}})
        server.api_card_update({"id": "debit-base", "fields": {"payout": 700}})
        card = self.card()
        self.assertEqual(card["bank"], "Второй")
        self.assertEqual(card["payout"], 700)

    def test_custom_card_can_be_edited(self):
        created = server.api_card_create({
            "bank": "Тест", "name": "Своя", "type": "debit", "payout": 1000,
            "benefit": "выгода", "terms": [{"label": "Обслуживание", "value": "0 ₽"}],
            "perks": [], "url": "https://test.example",
        })
        server.api_card_update({"id": created["id"], "fields": {"name": "Своя 2", "payout": 2500}})
        card = self.card(created["id"])
        self.assertEqual(card["name"], "Своя 2")
        self.assertEqual(card["payout"], 2500)

    def test_link_override_still_wins(self):
        server.api_card_update({"id": "debit-base", "fields": {"payout": 900}})
        server.api_link_set({"id": "debit-base", "url": "https://partner.example"})
        self.assertEqual(self.card()["url"], "https://partner.example")
        self.assertEqual(self.card()["payout"], 900)

    def test_validation(self):
        for payload in (
            {"fields": {"payout": 100}},
            {"id": "нет-такого", "fields": {"payout": 100}},
            {"id": "debit-base", "fields": {}},
            {"id": "debit-base", "fields": {"url": "https://elsewhere.example"}},
            {"id": "debit-base", "fields": {"type": "mortgage"}},
            {"id": "debit-base", "fields": {"bank": "  "}},
            {"id": "debit-base", "fields": {"payout": 0}},
            {"id": "debit-base", "fields": {"payout": "много"}},
            {"id": "debit-base", "fields": {"terms": []}},
        ):
            with self.assertRaises(ValueError, msg=str(payload)):
                server.api_card_update(payload)


if __name__ == "__main__":
    unittest.main()
