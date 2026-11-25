import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

BASE = {"items": [
    {"id": "a", "type": "debit", "bank": "Альфа", "name": "Первая", "benefit": "выгода",
     "terms": [{"label": "Обслуживание", "value": "0 ₽"}], "perks": [],
     "url": "https://a.example", "payout": 100},
    {"id": "b", "type": "debit", "bank": "Бета", "name": "Вторая", "benefit": "выгода",
     "terms": [{"label": "Обслуживание", "value": "0 ₽"}], "perks": [],
     "url": "https://b.example", "payout": 200},
]}


class AdminFeaturesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cards_file = os.path.join(self.tmp.name, "cards.json")
        with open(self.cards_file, "w", encoding="utf-8") as file:
            json.dump(BASE, file, ensure_ascii=False)
        self.paths = {}
        names = ("CUSTOM_FILE", "EDITS_FILE", "LINKS_FILE", "ORDER_FILE", "TEXTS_FILE", "CLICKS_FILE", "VISITS_FILE", "PUSH_SUBS")
        for name in names:
            path = os.path.join(self.tmp.name, name.lower() + ".json")
            self.paths[name] = path
        patches = [patch.object(server, "CARDS_FILE", self.cards_file)]
        patches += [patch.object(server, name, path) for name, path in self.paths.items()]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def cards(self):
        return server.api_cards()["items"]

    def test_pin_and_unpin(self):
        server.api_order_set({"id": "b", "pinned": True})
        self.assertTrue(next(item for item in self.cards() if item["id"] == "b")["pinned"])
        self.assertFalse(next(item for item in self.cards() if item["id"] == "a")["pinned"])
        server.api_order_set({"id": "b", "pinned": False})
        self.assertFalse(next(item for item in self.cards() if item["id"] == "b")["pinned"])

    def test_pin_validation(self):
        with self.assertRaises(ValueError):
            server.api_order_set({"id": "нет"})
        with self.assertRaises(ValueError):
            server.api_order_set({})

    def test_texts_override_and_clear(self):
        server.api_text_set({"section": "cards", "field": "title", "value": "Карты"})
        server.api_text_set({"section": "cards", "field": "note", "value": "Уточняйте условия"})
        self.assertEqual(server.api_texts()["items"]["cards"]["title"], "Карты")
        self.assertEqual(server.api_cards()["note"], "Уточняйте условия")
        server.api_text_set({"section": "cards", "field": "note", "value": "-"})
        self.assertNotIn("note", server.api_texts()["items"]["cards"])
        self.assertIsNone(server.api_cards()["note"])

    def test_text_validation(self):
        for payload in (
            {"section": "nope", "field": "title", "value": "x"},
            {"section": "cards", "field": "banner", "value": "x"},
        ):
            with self.assertRaises(ValueError):
                server.api_text_set(payload)

    def test_go_counts_clicks(self):
        self.assertEqual(server.api_go({"id": "a"})["url"], "https://a.example")
        server.api_go({"id": "a"})
        server.api_go({"id": "b"})
        stats = server.api_clicks()
        self.assertEqual(stats["total"], 3)
        counts = {item["key"]: item["clicks"] for item in stats["items"]}
        self.assertEqual(counts, {"cards:a": 2, "cards:b": 1})
        self.assertEqual(stats["items"][0]["section"], "Карты")
        self.assertIn("Альфа", stats["items"][0]["title"])
        with self.assertRaises(ValueError):
            server.api_go({"id": "нет"})

    def test_click_counts_any_section(self):
        server.api_click({"key": "deposits:direct:vtb:0", "title": "ВТБ · Вклад"})
        server.api_click({"key": "crypto:btc", "title": "Биткоин (BTC)"})
        server.api_click({"key": "realty:avito:1", "title": "1-к. квартира"})
        stats = server.api_clicks()
        self.assertEqual(stats["total"], 3)
        sections = {item["key"]: item["section"] for item in stats["items"]}
        self.assertEqual(sections["deposits:direct:vtb:0"], "Вклады")
        self.assertEqual(sections["crypto:btc"], "Криптовалюта")
        self.assertEqual(sections["realty:avito:1"], "Недвижимость")

    def test_click_validation(self):
        for payload in ({"key": "badkey"}, {"key": "unknown:x", "title": "x"}, {}):
            with self.assertRaises(ValueError):
                server.api_click(payload)

    def test_legacy_clicks_are_read_as_cards(self):
        with open(self.paths["CLICKS_FILE"], "w", encoding="utf-8") as file:
            json.dump({"debit-base": 4}, file)
        stats = server.api_clicks()
        self.assertEqual(stats["total"], 4)
        self.assertEqual(stats["items"][0]["key"], "cards:debit-base")

    def test_visits_counted_by_source(self):
        server.api_visit({"source": "app", "uid": "u1"})
        server.api_visit({"source": "app", "uid": "u1"})
        server.api_visit({"source": "browser", "uid": "u2"})
        data = server.api_visits()
        row = data["items"][-1]
        self.assertEqual(row["app"]["visits"], 2)
        self.assertEqual(row["app"]["users"], 1)
        self.assertEqual(row["browser"]["visits"], 1)
        self.assertEqual(data["total"]["app"], 2)
        self.assertEqual(data["total"]["browser"], 1)

    def test_manual_push(self):
        with open(self.paths["PUSH_SUBS"], "w", encoding="utf-8") as file:
            json.dump({"e1": {"subscription": {}}, "e2": {"subscription": {}}}, file)
        sent = []
        with patch.object(server, "_send_push", lambda subs, message: sent.append((len(subs), message))):
            result = server.api_push_send({"title": "Акция", "body": "Кэшбэк 30%", "url": "/#/cards"})
        self.assertEqual(result["sent"], 2)
        self.assertEqual(sent[0][0], 2)
        self.assertEqual(sent[0][1]["title"], "Акция")

    def test_manual_push_validation(self):
        with self.assertRaises(ValueError):
            server.api_push_send({"title": "", "body": "текст"})
        with self.assertRaises(ValueError):
            server.api_push_send({"title": "Т", "body": "текст", "url": "http://bad.example"})
        with self.assertRaises(ValueError):
            server.api_push_send({"title": "Т", "body": "текст"})


if __name__ == "__main__":
    unittest.main()
