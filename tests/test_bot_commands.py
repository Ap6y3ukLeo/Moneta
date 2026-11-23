import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot


class BotChartsTest(unittest.TestCase):
    def make(self):
        instance = bot.Bot("token", "http://api", "secret")
        calls = []
        instance.send = lambda chat_id, text, keyboard=None: calls.append(("text", text))
        instance.send_photo = lambda chat_id, png, caption, markup=None: calls.append(("photo", caption))
        instance.chart = lambda asset, period: calls.append(("chart", asset, period)) or b"\x89PNG"
        instance.card = lambda category, limit=12: calls.append(("card", category)) or b"\x89PNG"
        return instance, calls

    def test_section_button_sends_card(self):
        instance, calls = self.make()
        instance.handle(1, "Крипта")
        self.assertEqual(calls, [("card", "crypto"), ("photo", "Криптовалюта")])

    def test_asset_word_sends_chart(self):
        instance, calls = self.make()
        instance.handle(1, "BTC")
        self.assertEqual(calls, [("chart", "btc", "7d"), ("photo", "BTC · 7 дней")])

    def test_chart_command_with_period(self):
        instance, calls = self.make()
        instance.handle(1, "/chart sber 1m")
        self.assertEqual(calls, [("chart", "sber", "1m"), ("photo", "SBER · месяц")])

    def test_start_shows_help(self):
        instance, calls = self.make()
        instance.handle(1, "/start")
        self.assertEqual(calls, [("text", bot.HELP)])

    def test_empty_message_shows_help(self):
        instance, calls = self.make()
        instance.handle(1, "")
        self.assertEqual(calls, [("text", bot.HELP)])

    def test_callback_switches_period(self):
        instance, calls = self.make()
        instance.call = lambda method, **params: calls.append((method, params.get("callback_query_id")))
        instance.on_callback({"id": "cb1", "data": "chart:btc:1m", "message": {"chat": {"id": 5}}})
        self.assertEqual(calls[0], ("answerCallbackQuery", "cb1"))
        self.assertEqual(calls[1:], [("chart", "btc", "1m"), ("photo", "BTC · месяц")])

    def test_period_buttons(self):
        instance, _ = self.make()
        buttons = instance.periods_keyboard("btc")["inline_keyboard"][0]
        self.assertEqual([item["callback_data"] for item in buttons],
                         ["chart:btc:1d", "chart:btc:7d", "chart:btc:1m", "chart:btc:3m", "chart:btc:1y"])

    def test_card_chart_buttons(self):
        instance, _ = self.make()
        buttons = instance.assets_keyboard("crypto")["inline_keyboard"][0]
        self.assertEqual([item["callback_data"] for item in buttons],
                         ["chart:btc:7d", "chart:eth:7d", "chart:sol:7d"])
        self.assertIsNone(instance.assets_keyboard("deposits"))

    def test_section_keyboard(self):
        rows = [[button["text"] for button in row] for row in bot.KEYBOARD["keyboard"]]
        self.assertEqual(rows, [["Крипта", "Акции", "Металлы"], ["Валюта", "Вклады", "Недвижимость"]])

    def test_admin_only_for_configured_id(self):
        instance = bot.Bot("token", "http://api", "secret", admin_id=42)
        self.assertTrue(instance.is_admin(42))
        self.assertFalse(instance.is_admin(7))
        self.assertFalse(bot.Bot("token", "http://api", "secret").is_admin(42))

    def test_admin_list(self):
        instance = bot.Bot("token", "http://api", "secret", admin_ids=[849886384, 7592708940])
        self.assertTrue(instance.is_admin(849886384))
        self.assertTrue(instance.is_admin(7592708940))
        self.assertFalse(instance.is_admin(1))

    def test_new_card_wizard(self):
        instance, calls = self.make()
        instance.admin_ids = {1}
        instance.post = lambda path, payload: calls.append(("post", path, payload)) or {"id": "custom-1"}
        instance.admin_new(1)
        instance.handle(1, "Тест-Банк")
        instance.handle(1, "Тестовая")
        instance.admin_new_type(1, "credit")
        instance.handle(1, "4 500 ₽")
        instance.handle(1, "100 дней без процентов")
        instance.handle(1, "Льготный период=100 дней, Обслуживание=0 ₽")
        instance.handle(1, "https://test.example/card")
        posted = [entry for entry in calls if entry[0] == "post"][-1]
        self.assertEqual(posted[1], "/api/cards")
        self.assertEqual(posted[2]["payout"], 4500)
        self.assertEqual(posted[2]["type"], "credit")
        self.assertEqual(len(posted[2]["terms"]), 2)
        self.assertNotIn(1, instance.pending)

    def test_new_card_rejects_non_admin(self):
        instance, calls = self.make()
        instance.admin_new(5)
        self.assertEqual(calls, [("text", "Раздел только для администратора.")])
        self.assertNotIn(5, instance.pending)

    def test_edit_card_field(self):
        instance, calls = self.make()
        instance.admin_ids = {1}
        instance.post = lambda path, payload: calls.append(("post", path, payload)) or {"ok": True}
        instance.admin_edit_field(1, "debit-base", "payout")
        instance.handle(1, "1 200 ₽")
        posted = [entry for entry in calls if entry[0] == "post"][-1]
        self.assertEqual(posted, ("post", "/api/card_update", {"id": "debit-base", "fields": {"payout": 1200}}))
        self.assertNotIn(1, instance.pending)

    def test_edit_url_uses_links_endpoint(self):
        instance, calls = self.make()
        instance.admin_ids = {1}
        instance.post = lambda path, payload: calls.append(("post", path, payload)) or {"ok": True}
        instance.admin_edit_field(1, "debit-base", "url")
        instance.handle(1, "https://bank.example/new")
        posted = [entry for entry in calls if entry[0] == "post"][-1]
        self.assertEqual(posted, ("post", "/api/links", {"id": "debit-base", "url": "https://bank.example/new"}))

    def test_edit_terms_parsing(self):
        instance, calls = self.make()
        instance.admin_ids = {1}
        instance.post = lambda path, payload: calls.append(("post", path, payload)) or {"ok": True}
        instance.admin_edit_field(1, "debit-base", "terms")
        instance.handle(1, "Кэшбэк=до 5%, Обслуживание=0 ₽")
        posted = [entry for entry in calls if entry[0] == "post"][-1]
        self.assertEqual(posted[2]["fields"]["terms"],
                         [{"label": "Кэшбэк", "value": "до 5%"}, {"label": "Обслуживание", "value": "0 ₽"}])


if __name__ == "__main__":
    unittest.main()
