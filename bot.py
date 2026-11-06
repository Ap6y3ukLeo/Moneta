"""Телеграм-бот «Монетка»: карточки категорий и графики.

Запуск: BOT_TOKEN=... MONETKA_TOKEN=... python3 bot.py
"""
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

SECTIONS = [
    [("Крипта", "crypto"), ("Акции", "stocks"), ("Металлы", "metals")],
    [("Валюта", "fx"), ("Вклады", "deposits"), ("Недвижимость", "realty")],
]

TITLES = {
    "crypto": "Криптовалюта",
    "stocks": "Акции",
    "metals": "Драгметаллы",
    "fx": "Валюта",
    "deposits": "Вклады",
    "realty": "Недвижимость",
}

CHART_ASSETS = {
    "crypto": [("BTC", "btc"), ("ETH", "eth"), ("SOL", "sol")],
    "stocks": [("SBER", "sber"), ("GAZP", "gazp")],
    "metals": [("XAU", "xau"), ("XAG", "xag")],
    "fx": [("USD", "usd"), ("EUR", "eur")],
}

SECTION_MAP = {label.lower(): key for row in SECTIONS for label, key in row}

PERIODS = [("1д", "1d"), ("7д", "7d"), ("1м", "1m"), ("3м", "3m"), ("1г", "1y")]

RANGE_TITLES = {
    "1d": "1 день",
    "7d": "7 дней",
    "1m": "месяц",
    "3m": "3 месяца",
    "1y": "год",
    "all": "всё время",
}

KEYBOARD = {
    "keyboard": [[{"text": label} for label, _ in row] for row in SECTIONS],
    "resize_keyboard": True,
    "is_persistent": True,
}

HELP = (
    "Монетка: карточки и графики.\n\n"
    "Кнопки внизу открывают карточку категории.\n"
    "Под карточкой кнопки тикеров, они открывают график.\n"
    "Период можно задать командой: /chart btc 1m\n"
    "Периоды: 1d, 7d, 1m, 3m, 1y."
)


class Bot:
    def __init__(self, token: str, api: str, api_token: str):
        self.token = token
        self.api = api.rstrip("/")
        self.api_token = api_token

    def call(self, method: str, **params):
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        body = json.dumps(params).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def send(self, chat_id, text, keyboard=None):
        params = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if keyboard:
            params["reply_markup"] = keyboard
        self.call("sendMessage", **params)

    def fetch(self, path: str):
        request = urllib.request.Request(f"{self.api}{path}", headers={"X-Monetka-Token": self.api_token})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            try:
                message = json.loads(exc.read().decode("utf-8")).get("error")
            except Exception:  # noqa: BLE001 - тело ошибки может быть не JSON
                message = None
            raise RuntimeError(message or f"HTTP {exc.code}") from None

    def chart(self, asset: str, period: str):
        return self.fetch(f"/api/chart?{urlencode({'id': asset, 'range': period})}")

    def card(self, category: str, limit: int = 12):
        return self.fetch(f"/api/card?{urlencode({'category': category, 'limit': limit})}")

    def send_photo(self, chat_id, png: bytes, caption: str, markup=None):
        boundary = f"----monetka{int(time.time() * 1000)}"
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode(),
        ]
        if markup:
            parts.append(
                (f'--{boundary}\r\nContent-Disposition: form-data; name="reply_markup"\r\n\r\n'
                 f"{json.dumps(markup)}\r\n").encode()
            )
        parts.append(
            (f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="card.png"\r\n'
             "Content-Type: image/png\r\n\r\n").encode() + png + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/sendPhoto",
            data=b"".join(parts), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def periods_keyboard(self, asset: str):
        return {"inline_keyboard": [[
            {"text": label, "callback_data": f"chart:{asset}:{code}"} for label, code in PERIODS
        ]]}

    def assets_keyboard(self, category: str):
        assets = CHART_ASSETS.get(category) or []
        if not assets:
            return None
        return {"inline_keyboard": [[
            {"text": label, "callback_data": f"chart:{code}:7d"} for label, code in assets
        ]]}

    def send_chart(self, chat_id, asset: str, period: str):
        asset = asset.strip().lower()
        try:
            png = self.chart(asset, period)
        except Exception as exc:  # noqa: BLE001 - бот не должен падать из-за источника
            self.send(chat_id, f"Не получилось: {exc}", KEYBOARD)
            return
        self.send_photo(chat_id, png, f"{asset.upper()} · {RANGE_TITLES.get(period, period)}",
                        self.periods_keyboard(asset))

    def send_card(self, chat_id, category: str):
        try:
            png = self.card(category)
        except Exception as exc:  # noqa: BLE001 - бот не должен падать из-за источника
            self.send(chat_id, f"Не получилось: {exc}", KEYBOARD)
            return
        self.send_photo(chat_id, png, TITLES[category], self.assets_keyboard(category))

    def on_callback(self, callback):
        self.call("answerCallbackQuery", callback_query_id=callback.get("id"))
        data = (callback.get("data") or "").split(":")
        if len(data) != 3 or data[0] != "chart":
            return
        chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
        if chat_id:
            self.send_chart(chat_id, data[1], data[2])

    def handle(self, chat_id, text):
        parts = str(text or "").strip().split()
        word = parts[0].lstrip("/").lower() if parts else ""
        if not parts or word in ("start", "help", "menu"):
            self.send(chat_id, HELP, KEYBOARD)
            return
        if word == "chart":
            if len(parts) < 2:
                self.send(chat_id, HELP, KEYBOARD)
                return
            period = parts[2].lower() if len(parts) > 2 else "7d"
            self.send_chart(chat_id, parts[1], period)
            return
        category = SECTION_MAP.get(word)
        if category:
            self.send_card(chat_id, category)
            return
        self.send_chart(chat_id, word, "7d")

    def run(self):
        offset = 0
        while True:
            try:
                result = self.call("getUpdates", offset=offset, timeout=30,
                                   allowed_updates=["message", "callback_query"])
            except Exception as exc:  # noqa: BLE001 - сеть/телеграм, повторяем
                print("telegram:", exc, flush=True)
                time.sleep(5)
                continue
            for update in result.get("result") or []:
                offset = update["update_id"] + 1
                try:
                    callback = update.get("callback_query")
                    if callback:
                        self.on_callback(callback)
                        continue
                    message = update.get("message") or {}
                    chat_id = (message.get("chat") or {}).get("id")
                    if chat_id:
                        self.handle(chat_id, message.get("text") or "")
                except Exception as exc:  # noqa: BLE001 - одно сообщение не должно ронять бота
                    print("update:", exc, flush=True)


def main():
    bot = Bot(
        token=os.environ["BOT_TOKEN"],
        api=os.environ.get("MONETKA_API", "http://127.0.0.1:8787"),
        api_token=os.environ.get("MONETKA_TOKEN", ""),
    )
    print("bot started:", bot.call("getMe")["result"]["username"], flush=True)
    bot.run()


if __name__ == "__main__":
    main()
