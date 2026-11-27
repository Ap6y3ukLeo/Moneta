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
CARD_COLORS = {    "dark": ("Тёмный", "#24314f"),
    "blue": ("Синий", "#1f3a57"),
    "green": ("Зелёный", "#123c35"),
    "wine": ("Бордовый", "#4b1f2f"),
    "graphite": ("Графит", "#3a3f46"),
    "light": ("Светлый", "#e8eef2"),
}

# Сколько продуктов показывать на одной странице списка в боте.
PAGE_SIZE = 8

# Права в админке: ключ → подпись. Владельцы (env) имеют все.
ADMIN_SCOPES = {
    "cards": "Карточки",
    "links": "Ссылки",
    "push": "Пуши",
    "texts": "Тексты",
}

# Разделы и поля текстов сайта.
TEXT_SECTIONS = {"cards": "Карты и счета", "deposits": "Вклады банков", "realty": "Недвижимость"}
TEXT_FIELDS = {"title": "Заголовок", "sub": "Подзаголовок", "note": "Дисклеймер"}


class Bot:
    def __init__(self, token: str, api: str, api_token: str, admin_id: int = 0, admin_ids=None):
        self.token = token
        self.api = api.rstrip("/")
        self.api_token = api_token
        self.admin_ids = {int(value) for value in (admin_ids or [])}
        if admin_id:
            self.admin_ids.add(int(admin_id))
        self.pending = {}
        self.drafts = {}
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        self.admins_file = os.path.join(data_dir, "admins.json")
        self.log_file = os.path.join(data_dir, "admin_log.json")

    def read_json(self, path, default):
        try:
            with open(path, encoding="utf-8") as file:
                return json.load(file)
        except Exception:  # noqa: BLE001 - файла может не быть
            return default

    def write_json(self, path, value):
        try:
            with open(path + ".tmp", "w", encoding="utf-8") as file:
                json.dump(value, file, ensure_ascii=False, indent=1)
            os.replace(path + ".tmp", path)
        except OSError:
            pass

    def editors(self):
        data = self.read_json(self.admins_file, {})
        return data if isinstance(data, dict) else {}

    def scopes(self, chat_id):
        if int(chat_id) in self.admin_ids:
            return set(ADMIN_SCOPES)
        return set(self.editors().get(str(int(chat_id))) or [])

    def is_admin(self, chat_id) -> bool:
        return bool(self.scopes(chat_id))

    def can(self, chat_id, scope) -> bool:
        return scope in self.scopes(chat_id)

    def guard(self, chat_id, scope: str = "") -> bool:
        """True, если действие нужно прервать: не админ или нет нужного права."""
        if not self.is_admin(chat_id):
            self.send(chat_id, "Раздел только для администратора.")
            return True
        if scope and not self.can(chat_id, scope):
            self.send(chat_id, "Нет доступа к этому разделу.")
            return True
        return False

    def log(self, chat_id, action: str):
        try:
            entries = self.read_json(self.log_file, [])
            if not isinstance(entries, list):
                entries = []
            entries.append({"at": time.strftime("%d.%m %H:%M"), "by": str(chat_id), "action": action})
            self.write_json(self.log_file, entries[-300:])
        except Exception:  # noqa: BLE001 - журнал не должен ломать действие
            pass

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

    def products(self):
        return json.loads(self.fetch("/api/cards")).get("items") or []

    def admin_menu(self, chat_id):
        if not self.is_admin(chat_id):
            self.send(chat_id, "Раздел только для администратора.")
            return
        scopes = self.scopes(chat_id)
        rows = []
        if "cards" in scopes:
            rows.append([{"text": "📇 Карточки", "callback_data": "adm:cards"}])
        if "links" in scopes:
            rows.append([{"text": "🔗 Ссылки", "callback_data": "adm:links"}])
        if "push" in scopes:
            rows.append([{"text": "📣 Рассылка", "callback_data": "adm:push"}])
        tools = []
        if "cards" in scopes:
            tools.append({"text": "📊 Клики", "callback_data": "adm:clicks"})
        tools.append({"text": "👥 Аудитория", "callback_data": "adm:visits"})
        if "texts" in scopes:
            tools.append({"text": "📝 Тексты", "callback_data": "adm:texts"})
        if tools:
            rows.append(tools)
        if self._is_owner(chat_id):
            rows.append([{"text": "👥 Доступы", "callback_data": "adm:access"}])
        rows.append([{"text": "🧾 Журнал", "callback_data": "adm:journal"}])
        self.send(chat_id, "Панель управления. Выбери раздел.", {"inline_keyboard": rows})

    def admin_cards(self, chat_id, page: int = 0):
        if self.guard(chat_id, "cards"):
            return
        self.product_list(chat_id, page, "cards")

    def admin_links(self, chat_id, page: int = 0):
        if self.guard(chat_id, "links"):
            return
        self.product_list(chat_id, page, "links")

    def product_list(self, chat_id, page: int, mode: str):
        items = sorted(self.products(), key=lambda entry: (
            (entry.get("bank") or "").lower(), (entry.get("name") or "").lower()))
        pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(0, min(int(page), pages - 1))
        chunk = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
        rows = []
        if mode == "cards":
            rows.append([{"text": "➕ Новая карточка", "callback_data": "adm:new"}])
        for item in chunk:
            rows.append([{
                "text": f"{item['bank']} · {item['name']}"[:40],
                "callback_data": f"adm:open:{item['id']}",
            }])
        nav = []
        if page > 0:
            nav.append({"text": "◀️", "callback_data": f"adm:{mode}:{page - 1}"})
        nav.append({"text": f"{page + 1}/{pages}", "callback_data": "adm:noop"})
        if page < pages - 1:
            nav.append({"text": "▶️", "callback_data": f"adm:{mode}:{page + 1}"})
        rows.append(nav)
        rows.append([{"text": "← Меню", "callback_data": "adm:menu"}])
        title = "Карточки" if mode == "cards" else "Ссылки"
        self.send(chat_id, f"{title}: {len(items)} продуктов, страница {page + 1} из {pages}.",
                  {"inline_keyboard": rows})

    def admin_open(self, chat_id, product_id):
        if self.guard(chat_id):
            return
        item = next((entry for entry in self.products() if entry["id"] == product_id), None)
        if not item:
            self.send(chat_id, "Продукт не найден.")
            return
        terms = ", ".join(f"{term['label']}: {term['value']}" for term in item.get("terms") or [])
        pinned_note = "\n📌 Закреплён" if item.get("pinned") else ""
        text = (f"{item['bank']} · {item['name']}\n"
                f"Выплата: {item.get('payout')} ₽\n"
                f"Выгода: {item.get('benefit') or '—'}\n"
                f"Условия: {terms or '—'}\n"
                f"Ссылка: {item.get('url') or '—'}"
                f"{pinned_note}")
        rows = []
        if self.can(chat_id, "cards"):
            rows.append([{"text": "✏️ Редактировать", "callback_data": f"adm:edit:{product_id}"}])
            rows.append([{
                "text": "📌 Открепить" if item.get("pinned") else "📌 Закрепить",
                "callback_data": f"adm:pin:{product_id}",
            }])
        if self.can(chat_id, "links"):
            rows.append([{"text": "🔗 Изменить ссылку", "callback_data": f"adm:set:{product_id}"}])
            rows.append([{"text": "♻️ Сбросить ссылку", "callback_data": f"adm:reset:{product_id}"}])
        if self.can(chat_id, "cards") and product_id.startswith("custom-"):
            rows.append([{"text": "🗑 Удалить карточку", "callback_data": f"adm:drop:{product_id}"}])
        back = "adm:cards" if self.can(chat_id, "cards") else "adm:links"
        rows.append([{"text": "← Назад", "callback_data": back}])
        self.send(chat_id, text, {"inline_keyboard": rows})

    def admin_edit(self, chat_id, product_id):
        if self.guard(chat_id, "cards"):
            return
        item = next((entry for entry in self.products() if entry["id"] == product_id), None)
        if not item:
            self.send(chat_id, "Продукт не найден.")
            return
        keys = [key for key in EDIT_FIELDS if key != "url" or self.can(chat_id, "links")]
        rows = [
            [{"text": EDIT_FIELDS[key][0], "callback_data": f"adm:field:{product_id}:{key}"}
             for key in keys[start:start + 2]]
            for start in range(0, len(keys), 2)
        ]
        rows.append([{"text": "← Назад", "callback_data": f"adm:open:{product_id}"}])
        self.send(chat_id, f"Что меняем в «{item['bank']} · {item['name']}»?", {"inline_keyboard": rows})

    def admin_edit_field(self, chat_id, product_id, field):
        if self.guard(chat_id, "cards") or field not in EDIT_FIELDS:
            return
        if field == "url" and self.guard(chat_id, "links"):
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
        if self.guard(chat_id, "cards"):
            return
        if key not in CARD_COLORS:
            self.send(chat_id, "Неизвестный цвет.")
            return
        title, tint = CARD_COLORS[key]
        try:
            self.post("/api/card_update", {"id": product_id, "fields": {"tint": tint}})
            self.log(chat_id, f"Цвет {title.lower()} у {product_id}")
            self.send(chat_id, f"Цвет изменён: {title.lower()}.")
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")

    def admin_delete_ask(self, chat_id, product_id):
        if self.guard(chat_id, "cards"):
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
        if self.guard(chat_id, "cards"):
            return
        try:
            self.post("/api/card_delete", {"id": product_id})
            self.log(chat_id, f"Удалена карточка {product_id}")
            self.send(chat_id, "Карточка удалена.")
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")

    def admin_set_type(self, chat_id, product_id, kind):
        if self.guard(chat_id, "cards"):
            return
        if kind not in ("debit", "credit", "business"):
            self.send(chat_id, "Неизвестный тип.")
            return
        try:
            self.post("/api/card_update", {"id": product_id, "fields": {"type": kind}})
            self.log(chat_id, f"Тип {kind} у {product_id}")
            self.send(chat_id, "Тип изменён.")
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")

    def admin_pin(self, chat_id, product_id):
        if self.guard(chat_id, "cards"):
            return
        item = next((entry for entry in self.products() if entry["id"] == product_id), None)
        if not item:
            self.send(chat_id, "Продукт не найден.")
            return
        pinned = not item.get("pinned")
        try:
            self.post("/api/order", {"id": product_id, "pinned": pinned})
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")
            return
        self.log(chat_id, f"{'Закрепил' if pinned else 'Открепил'} {product_id}")
        self.send(chat_id, "Закреплено: продукт теперь выше в списке." if pinned else "Закрепление снято.")

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
            if self.guard(chat_id, "links"):
                self.pending.pop(chat_id, None)
                return
            if not raw.startswith("https://"):
                self.send(chat_id, "Ссылка должна начинаться с https://")
                return
            try:
                self.post("/api/links", {"id": product_id, "url": raw})
            except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
                self.send(chat_id, f"Не получилось: {exc}")
                return
            self.pending.pop(chat_id, None)
            self.log(chat_id, f"Ссылка у {product_id}")
            self.send(chat_id, "Ссылка обновлена.")
            return
        try:
            self.post("/api/card_update", {"id": product_id, "fields": {field: value}})
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")
            return
        self.pending.pop(chat_id, None)
        self.log(chat_id, f"Правка поля {field} у {product_id}")
        self.send(chat_id, "Сохранено.")

    def admin_await_link(self, chat_id, product_id):
        if self.guard(chat_id, "links"):
            return
        self.pending[chat_id] = {"mode": "link", "id": product_id}
        self.send(chat_id, "Пришли новую ссылку, начиная с https://\nОтмена: /cancel")

    def admin_new(self, chat_id):
        if self.guard(chat_id, "cards"):
            return
        self.pending[chat_id] = {"mode": "new", "step": "bank", "data": {}}
        self.send(chat_id, "Новая карточка, 1/7.\n\nБанк? Например: Т-Банк\nОтмена: /cancel")

    def admin_new_type(self, chat_id, kind):
        if self.guard(chat_id, "cards"):
            return
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
            self.log(chat_id, f"Новая карточка {data['bank']} · {data['name']}")
            self.send(chat_id, f"Готово. {data['bank']} · {data['name']} добавлена в раздел «Карты и счета».\n"
                               f"Выплата: {data['payout']} ₽\nid: {result.get('id')}")

    def admin_reset(self, chat_id, product_id):
        if self.guard(chat_id, "links"):
            return
        try:
            self.post("/api/links", {"id": product_id, "url": ""})
            self.log(chat_id, f"Сброс ссылки у {product_id}")
            self.send(chat_id, "Ссылка сброшена на исходную.")
        except Exception as exc:  # noqa: BLE001 - бот не должен падать
            self.send(chat_id, f"Не получилось: {exc}")

    def admin_clicks(self, chat_id):
        if self.guard(chat_id, "cards"):
            return
        try:
            data = json.loads(self.fetch("/api/clicks"))
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")
            return
        items = [item for item in data.get("items") or [] if item.get("clicks")][:15]
        if not items:
            self.send(chat_id, "Переходов по внешним ссылкам пока нет.")
            return
        lines = [f"{index}. [{item.get('section')}] {item.get('title')} — {item.get('clicks')}"
                 for index, item in enumerate(items, 1)]
        self.send(chat_id, f"Клики по внешним ссылкам, всего {data.get('total', 0)}:\n\n" + "\n".join(lines))

    def admin_push(self, chat_id):
        if self.guard(chat_id, "push"):
            return
        self.pending[chat_id] = {"mode": "push", "step": "title", "data": {}}
        self.send(chat_id, "Рассылка, 1/3.\n\nЗаголовок пуша? Коротко.\nОтмена: /cancel")

    def push_step(self, chat_id, pending, raw):
        data = pending["data"]
        step = pending["step"]
        if step == "title":
            data["title"] = raw[:80]
            pending["step"] = "body"
            self.send(chat_id, "2/3 Текст пуша? До 180 знаков.")
        elif step == "body":
            data["body"] = raw[:200]
            pending["step"] = "url"
            self.send(chat_id, "3/3 Куда ведёт пуш? Например /#/cards или https://...\n«-» — на главную.")
        elif step == "url":
            data["url"] = "/#/" if raw == "-" else raw
            pending["step"] = "confirm"
            self.send(chat_id, f"Пуш:\n\n{data['title']}\n{data['body']}\n\nСсылка: {data['url']}\n\n"
                               "Отправить всем подписчикам?", {"inline_keyboard": [
                [{"text": "📣 Отправить", "callback_data": "adm:pushsend"}],
                [{"text": "← Отмена", "callback_data": "adm:pushcancel"}],
            ]})
        else:
            self.send(chat_id, "Нажми кнопку под черновиком.")

    def admin_push_send(self, chat_id):
        if self.guard(chat_id, "push"):
            return
        pending = self.pending.get(chat_id)
        if not pending or pending.get("mode") != "push" or pending.get("step") != "confirm":
            self.send(chat_id, "Черновик потерян. Начни заново: /admin → «📣 Рассылка».")
            return
        try:
            result = self.post("/api/push_send", pending["data"])
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")
            return
        self.pending.pop(chat_id, None)
        self.log(chat_id, f"Рассылка «{pending['data']['title']}»: {result.get('sent')}")
        self.send(chat_id, f"Отправлено подписчикам: {result.get('sent')}.")

    def admin_push_cancel(self, chat_id):
        self.pending.pop(chat_id, None)
        self.send(chat_id, "Рассылка отменена.")

    def admin_texts(self, chat_id):
        if self.guard(chat_id, "texts"):
            return
        rows = [[{"text": title, "callback_data": f"adm:text:{key}"}] for key, title in TEXT_SECTIONS.items()]
        self.send(chat_id, "Тексты разделов. Выбери раздел:", {"inline_keyboard": rows})

    def admin_texts_section(self, chat_id, section):
        if self.guard(chat_id, "texts") or section not in TEXT_SECTIONS:
            return
        try:
            current = (json.loads(self.fetch("/api/texts")).get("items") or {}).get(section) or {}
        except Exception:  # noqa: BLE001 - без текущих текстов меню всё равно нужно
            current = {}
        lines = [f"{TEXT_FIELDS[field]}: {current.get(field) or '—'}" for field in TEXT_FIELDS]
        rows = [[{"text": TEXT_FIELDS[field], "callback_data": f"adm:textfield:{section}:{field}"}]
                for field in TEXT_FIELDS]
        rows.append([{"text": "← Назад", "callback_data": "adm:texts"}])
        self.send(chat_id, f"{TEXT_SECTIONS[section]}\n\n" + "\n".join(lines), {"inline_keyboard": rows})

    def admin_text_await(self, chat_id, section, field):
        if self.guard(chat_id, "texts") or section not in TEXT_SECTIONS or field not in TEXT_FIELDS:
            return
        self.pending[chat_id] = {"mode": "text", "section": section, "field": field}
        self.send(chat_id, f"{TEXT_FIELDS[field]} для «{TEXT_SECTIONS[section]}».\n"
                           "Пришли текст. «-» вернёт исходный вариант.\nОтмена: /cancel")

    def text_step(self, chat_id, pending, raw):
        try:
            result = self.post("/api/texts", {
                "section": pending["section"], "field": pending["field"], "value": raw,
            })
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")
            return
        self.pending.pop(chat_id, None)
        self.log(chat_id, f"Текст {pending['section']}.{pending['field']}")
        self.send(chat_id, "Сохранено." if result.get("value") else "Возвращён исходный текст.")

    def _is_owner(self, chat_id) -> bool:
        return int(chat_id) in self.admin_ids

    def access_keyboard(self, chat_id):
        draft = self.drafts.get(chat_id) or {}
        scopes = draft.get("scopes") or set()
        rows = [[{"text": f"{'✅' if scope in scopes else '⬜'} {title}", "callback_data": f"adm:acctoggle:{scope}"}]
                for scope, title in ADMIN_SCOPES.items()]
        rows.append([{"text": "💾 Сохранить", "callback_data": "adm:accsave"}])
        if draft.get("id") in self.editors():
            rows.append([{"text": "🗑 Убрать доступ", "callback_data": "adm:accdel"}])
        rows.append([{"text": "← Назад", "callback_data": "adm:access"}])
        return {"inline_keyboard": rows}

    def admin_access(self, chat_id):
        if not self._is_owner(chat_id):
            self.send(chat_id, "Управление доступами — только для владельца.")
            return
        editors = self.editors()
        lines = ["Владельцы: " + ", ".join(str(value) for value in sorted(self.admin_ids))]
        if editors:
            lines.append("\nРедакторы:")
            for key, scopes in sorted(editors.items()):
                titles = ", ".join(ADMIN_SCOPES.get(scope, scope) for scope in scopes) or "нет прав"
                lines.append(f"• {key} — {titles}")
        else:
            lines.append("\nРедакторов нет.")
        rows = [[{"text": f"✏️ {key}", "callback_data": f"adm:accopen:{key}"}] for key in sorted(editors)]
        rows.append([{"text": "➕ Добавить", "callback_data": "adm:accnew"}])
        self.send(chat_id, "\n".join(lines), {"inline_keyboard": rows})

    def admin_access_new(self, chat_id):
        if not self._is_owner(chat_id):
            self.send(chat_id, "Управление доступами — только для владельца.")
            return
        self.pending[chat_id] = {"mode": "access", "step": "id"}
        self.send(chat_id, "Пришли Telegram ID нового редактора.\n"
                           "Он узнает его командой /id.\nОтмена: /cancel")

    def access_step(self, chat_id, pending, raw):
        value = re.sub(r"[^\d]", "", raw)
        if not value:
            self.send(chat_id, "Нужен числовой Telegram ID.")
            return
        if self._is_owner(value):
            self.send(chat_id, "Этот ID уже владелец и имеет все права.")
            return
        self.drafts[chat_id] = {"id": value, "scopes": set(self.editors().get(value) or [])}
        self.pending.pop(chat_id, None)
        self.send(chat_id, f"Права для {value}:", self.access_keyboard(chat_id))

    def admin_access_open(self, chat_id, key):
        if not self._is_owner(chat_id):
            self.send(chat_id, "Управление доступами — только для владельца.")
            return
        editors = self.editors()
        if key not in editors:
            self.send(chat_id, "Редактор не найден.")
            return
        self.drafts[chat_id] = {"id": key, "scopes": set(editors[key])}
        self.send(chat_id, f"Права для {key}:", self.access_keyboard(chat_id))

    def admin_access_toggle(self, chat_id, scope):
        if not self._is_owner(chat_id) or scope not in ADMIN_SCOPES:
            return
        draft = self.drafts.get(chat_id)
        if not draft:
            self.send(chat_id, "Открой доступы заново: /admin → «👥 Доступы».")
            return
        draft["scopes"].symmetric_difference_update({scope})
        self.send(chat_id, f"Права для {draft['id']}:", self.access_keyboard(chat_id))

    def admin_access_save(self, chat_id):
        if not self._is_owner(chat_id):
            self.send(chat_id, "Управление доступами — только для владельца.")
            return
        draft = self.drafts.get(chat_id)
        if not draft:
            self.send(chat_id, "Нечего сохранять. Открой доступы заново.")
            return
        scopes = sorted(draft["scopes"])
        editors = self.editors()
        if scopes:
            editors[str(draft["id"])] = scopes
        else:
            editors.pop(str(draft["id"]), None)
        self.write_json(self.admins_file, editors)
        if sorted(self.editors().get(str(draft["id"])) or []) != scopes:
            self.send(chat_id, "Не удалось сохранить доступы на сервере.")
            return
        self.drafts.pop(chat_id, None)
        titles = ", ".join(ADMIN_SCOPES[scope] for scope in scopes) or "нет доступа"
        self.log(chat_id, f"Доступы {draft['id']}: {titles}")
        self.send(chat_id, f"Сохранено. {draft['id']}: {titles}.")

    def admin_access_delete(self, chat_id):
        if not self._is_owner(chat_id):
            self.send(chat_id, "Управление доступами — только для владельца.")
            return
        draft = self.drafts.get(chat_id)
        if not draft:
            self.send(chat_id, "Нечего удалять.")
            return
        editors = self.editors()
        editors.pop(str(draft["id"]), None)
        self.write_json(self.admins_file, editors)
        self.drafts.pop(chat_id, None)
        self.log(chat_id, f"Снят доступ у {draft['id']}")
        self.send(chat_id, f"Доступ у {draft['id']} убран.")

    def admin_visits(self, chat_id):
        if self.guard(chat_id):
            return
        try:
            data = json.loads(self.fetch("/api/visits"))
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки
            self.send(chat_id, f"Не получилось: {exc}")
            return
        days = data.get("items") or []
        if not days:
            self.send(chat_id, "Пока нет визитов.")
            return
        lines = []
        for row in days[-7:]:
            app = row.get("app") or {}
            web = row.get("browser") or {}
            lines.append(f"{row.get('date', '')[5:]}: приложение {app.get('visits', 0)} "
                         f"({app.get('users', 0)} чел.) · браузер {web.get('visits', 0)} ({web.get('users', 0)} чел.)")
        total = data.get("total") or {}
        self.send(chat_id, f"Визиты, последние {len(days[-7:])} дн.:\n\n" + "\n".join(lines)
                  + f"\n\nИтого: приложение {total.get('app', 0)} · браузер {total.get('browser', 0)}")

    def admin_journal(self, chat_id):
        if self.guard(chat_id):
            return
        entries = self.read_json(self.log_file, [])
        if not isinstance(entries, list) or not entries:
            self.send(chat_id, "Журнал пока пуст.")
            return
        lines = [f"{entry.get('at')} · {entry.get('by')} · {entry.get('action')}" for entry in entries[-15:]]
        self.send(chat_id, "Последние действия:\n\n" + "\n".join(lines))

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
        elif action == "cards":
            self.admin_cards(chat_id, int(data[2]) if len(data) > 2 and data[2].isdigit() else 0)
        elif action == "links":
            self.admin_links(chat_id, int(data[2]) if len(data) > 2 and data[2].isdigit() else 0)
        elif action == "noop":
            return
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
        elif action == "pin" and len(data) == 3:
            self.admin_pin(chat_id, data[2])
        elif action == "push":
            self.admin_push(chat_id)
        elif action == "pushsend":
            self.admin_push_send(chat_id)
        elif action == "pushcancel":
            self.admin_push_cancel(chat_id)
        elif action == "clicks":
            self.admin_clicks(chat_id)
        elif action == "visits":
            self.admin_visits(chat_id)
        elif action == "texts":
            self.admin_texts(chat_id)
        elif action == "text" and len(data) == 3:
            self.admin_texts_section(chat_id, data[2])
        elif action == "textfield" and len(data) == 4:
            self.admin_text_await(chat_id, data[2], data[3])
        elif action == "access":
            self.admin_access(chat_id)
        elif action == "accnew":
            self.admin_access_new(chat_id)
        elif action == "accopen" and len(data) == 3:
            self.admin_access_open(chat_id, data[2])
        elif action == "acctoggle" and len(data) == 3:
            self.admin_access_toggle(chat_id, data[2])
        elif action == "accsave":
            self.admin_access_save(chat_id)
        elif action == "accdel":
            self.admin_access_delete(chat_id)
        elif action == "journal":
            self.admin_journal(chat_id)
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
            if word in ("admin", "start", "menu"):
                # команда прерывает диалог, дальше обрабатывается как обычно
                self.pending.pop(chat_id, None)
            else:
                pending = self.pending[chat_id]
                if pending.get("mode") == "new":
                    self.new_step(chat_id, pending, raw)
                    return
                if pending.get("mode") == "edit":
                    self.edit_step(chat_id, pending, raw)
                    return
                if pending.get("mode") == "push":
                    self.push_step(chat_id, pending, raw)
                    return
                if pending.get("mode") == "text":
                    self.text_step(chat_id, pending, raw)
                    return
                if pending.get("mode") == "access":
                    self.access_step(chat_id, pending, raw)
                    return
                if raw.startswith("http"):
                    product_id = pending["id"]
                    try:
                        self.post("/api/links", {"id": product_id, "url": raw})
                        self.pending.pop(chat_id, None)
                        self.log(chat_id, f"Ссылка у {product_id}")
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
