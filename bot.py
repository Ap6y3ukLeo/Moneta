"""Телеграм-бот «Монетка»: карточки категорий и графики.

Запуск: BOT_TOKEN=... MONETKA_TOKEN=... python3 bot.py
"""
import json
import os
import re
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

# Поля карточки, которые админ может править из бота: подпись и подсказка.
EDIT_FIELDS = {
    "bank": ("Банк", "Название банка. Например: Т-Банк"),
    "name": ("Название", "Название продукта. Например: Black"),
    "type": ("Тип", ""),
    "payout": ("Выплата", "Сколько клиент получит за оформление, в рублях? Например: 3000"),
    "benefit": ("Выгода", "Выгода одной строкой. Например: до 30% кэшбэка"),
    "terms": ("Условия", "Условия через запятую, в виде «Поле=Значение».\n"
                         "Например: Кэшбэк=до 5%, Обслуживание=0 ₽"),
    "tint": ("Цвет", ""),
    "url": ("Ссылка", "Ссылка на оформление, начиная с https://"),
}

# Палитра карточки: ключ → название и цвет.
CARD_COLORS = {
    "dark": ("Тёмный", "#24314f"),
    "blue": ("Синий", "#1f3a57"),
    "green": ("Зелёный", "#123c35"),
    "wine": ("Бордовый", "#4b1f2f"),
    "graphite": ("Графит", "#3a3f46"),
    "light": ("Светлый", "#e8eef2"),
}


class Bot:
    def __init__(self, token: str, api: str, api_token: str, admin_id: int = 0, admin_ids=None):
        self.token = token
        self.api = api.rstrip("/")
        self.api_token = api_token
        self.admin_ids = {int(value) for value in (admin_ids or [])}
        if admin_id:
            self.admin_ids.add(int(admin_id))
        self.pending = {}

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

    def post(self, path: str, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api}{path}",
            data=body,
            headers={"Content-Type": "application/json", "X-Monetka-Token": self.api_token},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                message = json.loads(exc.read().decode("utf-8")).get("error")
            except Exception:  # noqa: BLE001 - тело ошибки может быть не JSON
                message = None
            raise RuntimeError(message or f"HTTP {exc.code}") from None

    def is_admin(self, chat_id) -> bool:
        return int(chat_id) in self.admin_ids

    def products(self):
        return json.loads(self.fetch("/api/cards")).get("items") or []

    def admin_menu(self, chat_id):
        if not self.is_admin(chat_id):
            self.send(chat_id, "Раздел только для администратора.")
            return
        rows, row = [], []
        for item in self.products():
            row.append({"text": f"{item['bank']} · {item['name']}"[:28], "callback_data": f"adm:open:{item['id']}"})
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.insert(0, [{"text": "➕ Новая карточка", "callback_data": "adm:new"}])
        self.send(chat_id, "Панель управления. Выбери продукт, чтобы поменять ссылку «Оформить», "
                  "или создай новую карточку.", {"inline_keyboard": rows})

    def admin_open(self, chat_id, product_id):
        item = next((entry for entry in self.products() if entry["id"] == product_id), None)
        if not item:
            self.send(chat_id, "Продукт не найден.")
            return
        terms = ", ".join(f"{term['label']}: {term['value']}" for term in item.get("terms") or [])
        text = (f"{item['bank']} · {item['name']}\n"
                f"Выплата: {item.get('payout')} ₽\n"
                f"Выгода: {item.get('benefit') or '—'}\n"
                f"Условия: {terms or '—'}\n"
                f"Ссылка: {item.get('url') or '—'}")
        rows = [
            [{"text": "✏️ Редактировать", "callback_data": f"adm:edit:{product_id}"}],
            [{"text": "🔗 Изменить ссылку", "callback_data": f"adm:set:{product_id}"}],
            [{"text": "♻️ Сбросить ссылку", "callback_data": f"adm:reset:{product_id}"}],
        ]
        if product_id.startswith("custom-"):
            rows.append([{"text": "🗑 Удалить карточку", "callback_data": f"adm:drop:{product_id}"}])
        rows.append([{"text": "← Назад", "callback_data": "adm:menu"}])
        self.send(chat_id, text, {"inline_keyboard": rows})

    def admin_edit(self, chat_id, product_id):
        if not self.is_admin(chat_id):
            self.send(chat_id, "Раздел только для администратора.")
            return
        item = next((entry for entry in self.products() if entry["id"] == product_id), None)
        if not item:
            self.send(chat_id, "Продукт не найден.")
            return
        keys = list(EDIT_FIELDS)
        rows = [
            [{"text": EDIT_FIELDS[key][0], "callback_data": f"adm:field:{product_id}:{key}"}
             for key in keys[start:start + 2]]
            for start in range(0, len(keys), 2)
        ]
        rows.append([{"text": "← Назад", "callback_data": f"adm:open:{product_id}"}])
        self.send(chat_id, f"Что меняем в «{item['bank']} · {item['name']}»?", {"inline_keyboard": rows})

    def admin_edit_field(self, chat_id, product_id, field):
        if not self.is_admin(chat_id) or field not in EDIT_FIELDS:
            return
        if field == "type":
            self.send(chat_id, "Новый тип:", {"inline_keyboard": [
                [{"text": "Дебетовая", "callback_data": f"adm:type:{product_id}:debit"},
                 {"text": "Кредитная", "callback_data": f"adm:type:{product_id}:credit"}],
                [{"text": "Для бизнеса", "callback_data": f"adm:type:{product_id}:business"}],
            ]})
            return
        if field == "tint":
            keys = list(CARD_COLORS)
            rows = [
                [{"text": CARD_COLORS[key][0], "callback_data": f"adm:color:{product_id}:{key}"}
                 for key in keys[start:start + 3]]
                for start in range(0, len(keys), 3)
            ]
            self.send(chat_id, "Цвет карточки:", {"inline_keyboard": rows})
            return
        self.pending[chat_id] = {"mode": "edit", "id": product_id, "field": field}
        self.send(chat_id, EDIT_FIELDS[field][1] + "\nОтмена: /cancel")

    def admin_set_color(self, chat_id, product_id, key):
        if not self.is_admin(chat_id):
            return
        if key not in CARD_COLORS:
            self.send(chat_id, "Неизвестный цвет.")
            return
        title, tint = CARD_COLORS[key]
        try:
            self.post("/api/card_update", {"id": product_id, "fields": {"tint": tint}})
            self.send(chat_id, f"Цвет изменён: {title.lower()}.")
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")

    def admin_delete_ask(self, chat_id, product_id):
        if not self.is_admin(chat_id):
            return
        if not product_id.startswith("custom-"):
            self.send(chat_id, "Удалить можно только карточку, созданную из бота. "
                               "Продукты справочника не удаляются.")
            return
        self.send(chat_id, "Удалить карточку? Действие необратимо.", {"inline_keyboard": [
            [{"text": "🗑 Да, удалить", "callback_data": f"adm:del:{product_id}"}],
            [{"text": "← Отмена", "callback_data": f"adm:open:{product_id}"}],
        ]})

    def admin_delete(self, chat_id, product_id):
        if not self.is_admin(chat_id):
            return
        try:
            self.post("/api/card_delete", {"id": product_id})
            self.send(chat_id, "Карточка удалена.")
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")

    def admin_set_type(self, chat_id, product_id, kind):
        if not self.is_admin(chat_id):
            return
        if kind not in ("debit", "credit", "business"):
            self.send(chat_id, "Неизвестный тип.")
            return
        try:
            self.post("/api/card_update", {"id": product_id, "fields": {"type": kind}})
            self.send(chat_id, "Тип изменён.")
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")

    def edit_step(self, chat_id, pending, raw):
        field = pending["field"]
        product_id = pending["id"]
        value = raw
        if field == "payout":
            digits = re.sub(r"[^\d]", "", raw)
            if not digits or int(digits) <= 0:
                self.send(chat_id, "Нужна сумма числом, например 3000")
                return
            value = int(digits)
        elif field == "terms":
            value = []
            for chunk in re.split(r"[,\n;]", raw):
                if "=" not in chunk:
                    continue
                label, term = chunk.split("=", 1)
                if label.strip() and term.strip():
                    value.append({"label": label.strip(), "value": term.strip()})
            if not value:
                self.send(chat_id, "Не нашёл ни одного «Поле=Значение». Пришли ещё раз.")
                return
        elif field == "url":
            if not raw.startswith("https://"):
                self.send(chat_id, "Ссылка должна начинаться с https://")
                return
            try:
                self.post("/api/links", {"id": product_id, "url": raw})
            except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
                self.send(chat_id, f"Не получилось: {exc}")
                return
            self.pending.pop(chat_id, None)
            self.send(chat_id, "Ссылка обновлена.")
            return
        try:
            self.post("/api/card_update", {"id": product_id, "fields": {field: value}})
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")
            return
        self.pending.pop(chat_id, None)
        self.send(chat_id, "Сохранено.")

    def admin_await_link(self, chat_id, product_id):
        self.pending[chat_id] = {"mode": "link", "id": product_id}
        self.send(chat_id, "Пришли новую ссылку, начиная с https://\nОтмена: /cancel")

    def admin_new(self, chat_id):
        if not self.is_admin(chat_id):
            self.send(chat_id, "Раздел только для администратора.")
            return
        self.pending[chat_id] = {"mode": "new", "step": "bank", "data": {}}
        self.send(chat_id, "Новая карточка, 1/7.\n\nБанк? Например: Т-Банк\nОтмена: /cancel")

    def admin_new_type(self, chat_id, kind):
        pending = self.pending.get(chat_id)
        if not pending or pending.get("mode") != "new" or pending.get("step") != "type":
            self.send(chat_id, "Начни заново: /admin → «➕ Новая карточка».")
            return
        if kind not in ("debit", "credit", "business"):
            self.send(chat_id, "Неизвестный тип.")
            return
        pending["data"]["type"] = kind
        pending["step"] = "payout"
        self.send(chat_id, "4/7 Сколько клиент получит за оформление, в рублях? Например: 3000")

    def new_step(self, chat_id, pending, raw):
        step = pending["step"]
        data = pending["data"]
        if step == "bank":
            data["bank"] = raw
            pending["step"] = "name"
            self.send(chat_id, "2/7 Название продукта? Например: Black")
        elif step == "name":
            data["name"] = raw
            pending["step"] = "type"
            self.send(chat_id, "3/7 Тип продукта:", {"inline_keyboard": [[
                {"text": "Дебетовая", "callback_data": "adm:newtype:debit"},
                {"text": "Кредитная", "callback_data": "adm:newtype:credit"},
            ], [
                {"text": "Для бизнеса", "callback_data": "adm:newtype:business"},
            ]]})
        elif step == "type":
            self.send(chat_id, "Выбери тип кнопкой выше.")
        elif step == "payout":
            digits = re.sub(r"[^\d]", "", raw)
            if not digits or int(digits) <= 0:
                self.send(chat_id, "Нужна сумма числом, например 3000")
                return
            data["payout"] = int(digits)
            pending["step"] = "benefit"
            self.send(chat_id, "5/7 Выгода одной строкой. Например: до 30% кэшбэка")
        elif step == "benefit":
            data["benefit"] = raw
            pending["step"] = "terms"
            self.send(chat_id, "6/7 Условия через запятую, в виде «Поле=Значение».\n"
                               "Например: Кэшбэк=до 5%, Обслуживание=0 ₽")
        elif step == "terms":
            terms = []
            for chunk in re.split(r"[,\n;]", raw):
                if "=" not in chunk:
                    continue
                label, value = chunk.split("=", 1)
                if label.strip() and value.strip():
                    terms.append({"label": label.strip(), "value": value.strip()})
            if not terms:
                self.send(chat_id, "Не нашёл ни одного «Поле=Значение». Пришли ещё раз.")
                return
            data["terms"] = terms
            pending["step"] = "url"
            self.send(chat_id, "7/7 Ссылка на оформление, начиная с https://\nОтмена: /cancel")
        elif step == "url":
            if not raw.startswith("https://"):
                self.send(chat_id, "Ссылка должна начинаться с https://")
                return
            data["url"] = raw
            try:
                result = self.post("/api/cards", data)
            except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
                self.send(chat_id, f"Не получилось: {exc}")
                return
            self.pending.pop(chat_id, None)
            self.send(chat_id, f"Готово. {data['bank']} · {data['name']} добавлена в раздел «Карты и счета».\n"
                               f"Выплата: {data['payout']} ₽\nid: {result.get('id')}")

    def admin_reset(self, chat_id, product_id):
        try:
            self.post("/api/links", {"id": product_id, "url": ""})
            self.send(chat_id, "Ссылка сброшена на исходную.")
        except Exception as exc:  # noqa: BLE001 - бот не должен падать
            self.send(chat_id, f"Не получилось: {exc}")

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
        chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
        if not chat_id:
            return
        if data[0] == "chart" and len(data) == 3:
            self.send_chart(chat_id, data[1], data[2])
            return
        if data[0] != "adm":
            return
        action = data[1] if len(data) > 1 else ""
        if action == "menu":
            self.admin_menu(chat_id)
        elif action == "new":
            self.admin_new(chat_id)
        elif action == "edit" and len(data) == 3:
            self.admin_edit(chat_id, data[2])
        elif action == "field" and len(data) == 4:
            self.admin_edit_field(chat_id, data[2], data[3])
        elif action == "type" and len(data) == 4:
            self.admin_set_type(chat_id, data[2], data[3])
        elif action == "color" and len(data) == 4:
            self.admin_set_color(chat_id, data[2], data[3])
        elif action == "drop" and len(data) == 3:
            self.admin_delete_ask(chat_id, data[2])
        elif action == "del" and len(data) == 3:
            self.admin_delete(chat_id, data[2])
        elif action == "newtype" and len(data) == 3:
            self.admin_new_type(chat_id, data[2])
        elif action == "open" and len(data) == 3:
            self.admin_open(chat_id, data[2])
        elif action == "set" and len(data) == 3:
            self.admin_await_link(chat_id, data[2])
        elif action == "reset" and len(data) == 3:
            self.admin_reset(chat_id, data[2])

    def handle(self, chat_id, text):
        parts = str(text or "").strip().split()
        word = parts[0].lstrip("/").lower() if parts else ""
        raw = str(text or "").strip()

        if chat_id in self.pending:
            if word == "cancel":
                self.pending.pop(chat_id, None)
                self.send(chat_id, "Отменено.")
                return
            pending = self.pending[chat_id]
            if pending.get("mode") == "new":
                self.new_step(chat_id, pending, raw)
                return
            if pending.get("mode") == "edit":
                self.edit_step(chat_id, pending, raw)
                return
            if raw.startswith("http"):
                product_id = pending["id"]
                try:
                    self.post("/api/links", {"id": product_id, "url": raw})
                    self.pending.pop(chat_id, None)
                    self.send(chat_id, f"Сохранено.\n{raw}")
                except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
                    self.send(chat_id, f"Не получилось: {exc}")
                return

        if word == "admin":
            self.admin_menu(chat_id)
            return
        if word == "id":
            self.send(chat_id, f"Ваш Telegram ID: {chat_id}")
            return
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
    admin_ids = {int(value) for value in os.environ.get("MONETKA_ADMIN_IDS", "").replace(" ", "").split(",") if value.strip().isdigit()}
    single = int(os.environ.get("MONETKA_ADMIN_ID", "0") or 0)
    if single:
        admin_ids.add(single)

    bot = Bot(
        token=os.environ["BOT_TOKEN"],
        api=os.environ.get("MONETKA_API", "http://127.0.0.1:8787"),
        api_token=os.environ.get("MONETKA_TOKEN", ""),
        admin_ids=admin_ids,
    )
    print("bot started:", bot.call("getMe")["result"]["username"], flush=True)
    bot.run()


if __name__ == "__main__":
    main()
