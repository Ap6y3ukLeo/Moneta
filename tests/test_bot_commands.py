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


if __name__ == "__main__":
    unittest.main()
